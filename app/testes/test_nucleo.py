"""
O nucleo inteiro contra a placa falsa, com o perfil importado do agente antigo.
As acoes que mexem no PC (mic, teclas, abrir app) sao trocadas por gravadores:
o teste confere que o toque chegou na acao certa, sem mutar o seu microfone.

    cd app && python -m pytest testes -q
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "testes"))

DADOS = Path(tempfile.mkdtemp(prefix="telinha_teste_"))
os.environ["TELINHA_DADOS"] = str(DADOS)

from placa_falsa import PlacaFalsa  # noqa: E402


def espera(cond, prazo=20.0, passo=0.02):
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(passo)
    return False


@pytest.fixture(scope="module")
def sistema():
    from telinha.nucleo import Nucleo
    n = Nucleo()
    chamadas = []
    for nome, (mid, fn) in list(n.hosp.acoes.items()):
        def grava(passo, nome=nome):
            chamadas.append((nome, dict(passo)))
        n.hosp.acoes[nome] = (mid, grava)
    # a janela da frente aqui e o terminal desta sessao do Claude: o perfil por
    # foco abriria a pagina Claude no meio do teste. Vigias de janela e de
    # ociosidade ficam desligados.
    n.rot.vigia = lambda agora: None
    placa = PlacaFalsa()
    t = threading.Thread(target=n.rodar, kwargs={"ser_fabrica": lambda: placa}, daemon=True)
    t.start()
    yield n, placa, chamadas
    placa.close()
    t.join(timeout=3)
    shutil.rmtree(DADOS, ignore_errors=True)


def test_home_chega_inteira(sistema):
    n, placa, _ = sistema
    assert espera(lambda: placa.pagina == "home" and placa.pagina_completa()), placa.layout
    assert "home" in [p for p in n.comp.paginas()]
    assert placa.estado, "o estado (mic, volume) tem de ir junto"


def test_barra_tem_a_hora(sistema):
    _, placa, _ = sistema
    assert espera(lambda: placa.barra[:2].isdigit() and placa.barra[2] == ":")


def test_toque_roda_acao_e_responde(sistema):
    n, placa, chamadas = sistema
    antes = len(chamadas)
    t0 = time.monotonic()
    placa.toque("mic")
    assert espera(lambda: "mic" in placa.acks)
    ms = (time.monotonic() - t0) * 1000
    tipos = [c[0] for c in chamadas[antes:]]
    assert tipos == ["mic_toggle", "key_app"], tipos
    assert ms < 300, f"toque levou {ms:.0f} ms"


def test_navega_e_volta(sistema):
    n, placa, _ = sistema
    placa.toque("dev")
    assert espera(lambda: placa.pagina == "dev" and placa.pagina_completa())
    placa.voltar()
    assert espera(lambda: placa.pagina == "home")


def test_descanso_baixa_o_brilho(sistema):
    n, placa, _ = sistema
    placa.toque("descansar")
    assert espera(lambda: placa.pagina == "descanso")
    assert espera(lambda: placa.brilho == 40)
    placa.voltar()
    assert espera(lambda: placa.pagina == "home" and placa.brilho == 200)


def test_card_vivo_troca_no_lugar(sistema):
    """O volume mudou de degrau: so o card SOM vai de novo, sem layout novo."""
    n, placa, _ = sistema
    assert espera(lambda: placa.pagina == "home" and placa.pagina_completa())
    som = next(b["art"] for b in placa.layout["buttons"] if b["id"] == "sysmute")
    layouts = placa.eventos.count("layout")
    tam = placa.sprites.get(som)
    n.comp.niveis["sys_vol"] = 7 if (n.comp.niveis.get("sys_vol") or 0) > 50 else 93
    assert espera(lambda: placa.sprites.get(som) != tam, prazo=5)
    assert placa.eventos.count("layout") == layouts


def test_arte_corrompida_e_remandada(sistema):
    n, placa, _ = sistema
    placa.toque("apps")
    assert espera(lambda: placa.pagina == "apps")
    alvo = next(b["art"] for b in placa.layout["buttons"])
    placa.sprites.pop(alvo, None)
    n.lig.enviadas.discard(alvo)
    placa.corromper.add(alvo)
    ruins = placa.ruins
    assert espera(lambda: placa.ruins > ruins, prazo=10)
    assert espera(lambda: alvo in placa.sprites, prazo=10)
    placa.voltar()


def test_pacote_soundboard(sistema):
    n, placa, chamadas = sistema
    placa.toque("apps")
    assert espera(lambda: placa.pagina == "apps")
    placa.toque("apps.soundboard")
    assert espera(lambda: placa.pagina == "soundboard" and placa.pagina_completa())
    som = next(b["id"] for b in placa.layout["buttons"] if ".som:" in b["id"])
    antes = len(chamadas)
    placa.toque(som)
    assert espera(lambda: len(chamadas) > antes)
    assert chamadas[-1][0] == "som" and chamadas[-1][1]["arquivo"].endswith(".wav")


def test_botao_desconhecido_responde_erro(sistema):
    _, placa, _ = sistema
    placa.toque("nao_existe")
    assert espera(lambda: any(e[0] == "nao_existe" for e in placa.erros))


def test_placa_reinicia_e_recebe_tudo_de_novo(sistema):
    _, placa, _ = sistema
    placa.reinicia()
    assert espera(lambda: placa.pagina == "home" and placa.pagina_completa())


def test_perfil_salvo_em_dados(sistema):
    import json
    p = json.loads((DADOS / "perfil.json").read_text(encoding="utf-8"))
    assert p["esquema"] == 2
    mic = next(b for b in p["paginas"]["home"]["botoes"] if b["id"] == "mic")
    assert mic["aceso"] == "mic_muted" and [s["type"] for s in mic["toque"]] == ["mic_toggle", "key_app"]


def test_precarga_leva_todas_as_paginas(sistema):
    """Com a fila vazia, toda pagina (vivos inclusive) tem de acabar na placa:
    a navegacao fica instantanea."""
    n, placa, _ = sistema

    def faltando():
        falta = []
        for pid in n.comp.paginas():
            for b in n.comp.pagina(pid)["buttons"]:
                for a in (b["art"], b["art_on"]):
                    if a and a not in placa.sprites and a not in n.lig.versao_placa:
                        falta.append(a)
        return falta
    assert espera(lambda: not faltando(), prazo=30), faltando()


def test_editar_perfil_vale_no_proximo_hello(sistema):
    """Mudou o perfil (a mao ou pelo editor): a placa reinicia e o botao vem
    com arte nova - o id da arte muda junto com a aparencia."""
    import json
    n, placa, _ = sistema
    arq = DADOS / "perfil.json"
    p = json.loads(arq.read_text(encoding="utf-8"))
    snip = next(b for b in p["paginas"]["home"]["botoes"] if b["id"] == "snip")
    snip["aparencia"]["color"] = "#FF00AA"
    from telinha import perfil
    perfil.salvar(p)
    assert list((DADOS / "perfil.hist").glob("perfil-*.json")), "a versao anterior fica no historico"
    antes = next(b["art"] for b in placa.layout["buttons"] if b["id"] == "snip") \
        if placa.pagina == "home" else None
    placa.reinicia()
    assert espera(lambda: placa.pagina == "home" and placa.pagina_completa())
    depois = next(b["art"] for b in placa.layout["buttons"] if b["id"] == "snip")
    assert antes is None or depois != antes


def _api(caminho, corpo=None):
    import json
    import urllib.request
    info = json.loads((DADOS / "api.json").read_text(encoding="utf-8"))
    req = urllib.request.Request(f"http://127.0.0.1:{info['porta']}{caminho}",
                                 data=None if corpo is None else json.dumps(corpo).encode(),
                                 headers={"x-token": info["token"], "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read() if "arte" in caminho else json.loads(r.read())


def test_janela_espelha_e_edita(sistema):
    """A API da janela: espelho da placa, arte, toque e edicao de botao."""
    n, placa, chamadas = sistema
    assert espera(lambda: placa.pagina == "home" and placa.pagina_completa())
    t = _api("/api/tudo")
    assert t["conectado"] and t["pagina"] == "home" and len(t["layout"]["buttons"]) == 12
    art = t["layout"]["buttons"][0]["art"]
    assert _api(f"/api/arte?c={art}")[:2] == bytes([0xFF, 0xD8])          # JPEG
    import urllib.error
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{__import__('json').loads((DADOS / 'api.json').read_text())['porta']}/api/tudo", timeout=5)
        assert False, "sem token tinha de recusar"
    except urllib.error.HTTPError as e:
        assert e.code == 401
    # toque pela janela = toque na placa
    antes = len(chamadas)
    _api("/api/toque", {"pagina": "home", "botao": "snip"})
    assert espera(lambda: len(chamadas) > antes and chamadas[-1][0] == "key")
    # editar: rotulo novo -> id da arte novo -> a placa recebe
    det = _api("/api/pagina/home")
    snip = next(b for b in det["botoes"] if b["id"] == "snip")
    snip["aparencia"]["label"] = "Recorte"
    snip.pop("_fixo", None)
    _api("/api/botao", {"pagina": "home", "botao": snip})
    assert espera(lambda: any(b["id"] == "snip" and b["art"] != next(x["art"] for x in t["layout"]["buttons"] if x["id"] == "snip")
                              for b in placa.layout.get("buttons", [])))
    assert espera(lambda: placa.pagina_completa())
    # botao novo num quadrado vazio, depois apagado
    _api("/api/botao", {"pagina": "apps", "botao": {"id": "teste_novo", "aparencia": {"widget": "icone", "icon": "mais"},
                                                     "toque": [{"type": "page", "page": "home"}]}})
    assert espera(lambda: any(b["id"] == "teste_novo" for b in _api("/api/pagina/apps")["botoes"]))
    _api("/api/apagar", {"pagina": "apps", "botao": "teste_novo"})
    assert espera(lambda: not any(b["id"] == "teste_novo" for b in _api("/api/pagina/apps")["botoes"]))

def _ids(pagina):
    return [b and b["id"] for b in _api(f"/api/pagina/{pagina}")["botoes"]]


def test_editor_organiza_a_placa(sistema):
    """Arrastar troca de lugar, buraco vira quadrado vazio, pasta cria pagina,
    desfazer volta tudo."""
    n, placa, chamadas = sistema
    cat = _api("/api/catalogo")
    assert any(i["id"] == "audio.mic" for i in cat["biblioteca"])
    assert any(a["id"] == "key" and a["campos"]["target"]["tipo"] == "tecla" for a in cat["acoes"])
    assert any(i["nome"] == "mic" and i["cp"] > 0xE000 for i in cat["icones"])

    nova = _api("/api/pagina_nova", {"titulo": "Teste Live"})["pagina"]
    assert espera(lambda: nova in [p["id"] for p in _api("/api/tudo")["paginas"]])
    item = next(i for i in cat["biblioteca"] if i["id"] == "audio.mic")
    _api("/api/botao", {"pagina": nova, "botao": dict(item["botao"]), "pos": 0})
    _api("/api/botao", {"pagina": nova, "botao": {"aparencia": {"widget": "icone", "icon": "stop", "label": "B"},
                                                   "toque": [{"type": "som_parar"}]}, "pos": 5})
    assert espera(lambda: len(_ids(nova)) == 6)
    ids = _ids(nova)
    assert ids[1:5] == [None] * 4, ids            # buracos entre 0 e 5

    # arrastar o da posicao 0 para a 5: os dois trocam
    _api("/api/mover", {"pagina": nova, "botao": ids[0], "pos": 5})
    assert espera(lambda: _ids(nova)[0] == ids[5] and _ids(nova)[5] == ids[0])

    # na placa, o buraco e um quadrado vazio que nao reclama do toque
    _api("/api/navegar", {"pagina": nova})
    assert espera(lambda: placa.pagina == nova and placa.pagina_completa())
    assert sum(b["id"] == "_vazio" for b in placa.layout["buttons"]) == 4
    erros = len(placa.erros)
    placa.toque("_vazio")
    time.sleep(0.3)
    assert len(placa.erros) == erros

    # pasta: pagina nova + botao que leva a ela; soltar um botao dentro
    r = _api("/api/pasta", {"pagina": nova, "pos": 2, "titulo": "Cenas"})
    assert espera(lambda: r["id"] in _ids(nova))
    _api("/api/para_pasta", {"pagina": nova, "botao": ids[0], "destino": r["pagina"]})
    assert espera(lambda: ids[0] in _ids(r["pagina"]) and ids[0] not in _ids(nova))

    # previa: desenha sem salvar
    jpeg = None
    import urllib.request
    info = __import__("json").loads((DADOS / "api.json").read_text())
    req = urllib.request.Request(f"http://127.0.0.1:{info['porta']}/api/previa",
                                 data=__import__("json").dumps({"pagina": nova, "botao": item["botao"]}).encode(),
                                 headers={"x-token": info["token"], "content-type": "application/json"})
    jpeg = urllib.request.urlopen(req, timeout=10).read()
    assert jpeg[:2] == bytes([0xFF, 0xD8])

    # desfazer volta o botao para fora da pasta; refazer põe de novo
    assert _api("/api/desfazer", {})["ok"]
    assert espera(lambda: ids[0] in _ids(nova))
    assert _api("/api/refazer", {})["ok"]
    assert espera(lambda: ids[0] not in _ids(nova))

    # grade nova e apagar a pagina
    _api("/api/pagina_editar", {"pagina": nova, "titulo": "Live", "grade": {"cols": 3, "rows": 2}})
    assert espera(lambda: _api(f"/api/pagina/{nova}")["grid"] == {"cols": 3, "rows": 2})
    _api("/api/pagina_apagar", {"pagina": nova})
    assert espera(lambda: nova not in [p["id"] for p in _api("/api/tudo")["paginas"]])
    assert espera(lambda: placa.pagina != nova)


def test_desligar_pela_bandeja_apaga_a_tela(sistema):
    """Por ultimo: encerra o nucleo."""
    n, placa, _ = sistema
    (DADOS / "comando.txt").write_text("dormir", encoding="utf-8")
    assert espera(lambda: "dormir" in placa.eventos, prazo=5)
    import json
    assert espera(lambda: json.loads((DADOS / "estado.json").read_text()).get("dormindo"), prazo=5)
