"""
O perfil: paginas e botoes, no esquema 2.

Um botao do esquema 1 (o config.json do agente antigo) misturava tres coisas.
Aqui elas sao separadas, porque cada uma e uma peca diferente no editor:

    {
      "id": "mic",
      "aparencia": {"widget": "icone", "icon": "mic", "color": "#5B6572"},
      "toque": [{"type": "mic_toggle"},
                {"type": "key_app", "app": "discord", "target": "ctrl+alt+shift+m"}],
      "depois": "player",          (opcional) pagina para onde ir depois
      "aceso": "mic_muted"         (opcional) chave de estado que acende o botao
    }

Pagina: {"titulo", "voltar", "grade": {"cols","rows"}, "quando_foco": [...],
"gerar": "modulo.provedor" (+ parametros), "brilho", "botoes": [...]}.

Perfil: {"esquema": 2, "inicio": "home", "ajustes": {...}, "modulos": {id: cfg},
"pacotes": {"desligados": [], "forcar": []}, "paginas": {...}}.

Salvar guarda a versao anterior em perfil.hist/ (as ultimas 50): desfazer e
"voltar para ontem" saem de graca, e um perfil quebrado nunca deixa a tela
inutilizavel.

Pacotes de app (pacotes/<app>/pacote.json, ja no esquema 2) sao juntados na
carga - ver `com_pacotes`.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import time
from pathlib import Path

from . import caminhos

ESQUEMA = 2
VISUAL = ("icon", "icon_app", "icon_exe", "icon_file", "label", "label_on", "sub",
          "color", "peso", "estilo", "nivel_de")
WIDGETS_VIVOS = ("relogio", "clima", "musica", "foco", "agenda", "sistema")
GERAR_NOVO = {"sons": "soundboard.sons", "obs_cenas": "obs.cenas"}
MAX_HIST = 50


# ------------------------------------------------------- esquema 1 -> 2

def converte_botao(b: dict) -> dict:
    if "pacote" in b and "type" not in b:
        return dict(b)                       # atalho de pacote, resolvido na carga
    ap = {k: b[k] for k in VISUAL if k in b}
    ap["widget"] = b["live"] if b.get("live") else "icone"
    for k in ("icon_exe", "icon_file"):
        if isinstance(ap.get(k), str) and ap[k].startswith("logos/"):
            ap[k] = "arquivos/" + ap[k][len("logos/"):]
    if b.get("type") == "sequence":
        toque = [dict(p) for p in b.get("steps", [])]
    else:
        acao = {k: v for k, v in b.items()
                if k not in VISUAL and k not in ("id", "live", "state_key", "_off", "then",
                                                 "_comment", "_comment_nivel", "_pacote")}
        toque = [acao] if acao.get("type") else []
    novo = {"id": b["id"], "aparencia": ap, "toque": toque}
    if b.get("then"):
        novo["depois"] = b["then"]
    if b.get("state_key"):
        novo["aceso"] = b["state_key"]
    if b.get("_off"):
        novo["desligado"] = True
    for k in ("_comment", "_pacote"):
        if k in b:
            novo[k] = b[k]
    return novo


def converte_pagina(p: dict) -> dict:
    novo = {}
    ren = {"title": "titulo", "back": "voltar", "grid": "grade", "buttons": "botoes"}
    for k, v in p.items():
        if k == "buttons":
            novo["botoes"] = [converte_botao(b) for b in v]
        elif k == "gerar":
            novo["gerar"] = GERAR_NOVO.get(v, v)
        else:
            novo[ren.get(k, k)] = v
    novo.setdefault("botoes", [])
    return novo


def do_config(cfg: dict) -> dict:
    """config.json do agente antigo -> perfil esquema 2."""
    paginas = {pid: converte_pagina(p) for pid, p in (cfg.get("pages") or {}).items()}
    if "dev" not in paginas:
        paginas["dev"] = {"titulo": "Projetos", "voltar": "home",
                          "gerar": "projetos.lista", "botoes": []}
    desc = cfg.get("descanso") or {}
    if "descanso" in paginas and desc.get("brilho"):
        paginas["descanso"]["brilho"] = int(desc["brilho"])
    modulos = {
        "clima": cfg.get("clima") or {},
        "agenda": cfg.get("agenda") or {},
        "midia": {"spotify": cfg.get("spotify") or {}},
        "projetos": cfg.get("projetos") or {},
        "soundboard": cfg.get("sons") or {},
        "obs": cfg.get("obs") or {},
        "foco": {"min": cfg.get("foco_min", 25)},
    }
    return {
        "esquema": ESQUEMA,
        "inicio": "home",
        "ajustes": {
            "porta": cfg.get("port", "auto"),
            "baud": cfg.get("baud", 921600),
            "estado_ms": cfg.get("state_interval_ms", 1000),
            "jpeg_qualidade": cfg.get("jpeg_quality", 90),
            "barra_relogio": cfg.get("barra_relogio", True),
            "brilho": cfg.get("brilho", 200),
            "descanso": {"pagina": "descanso", "apos_min": desc.get("apos_min", 15)},
        },
        "modulos": {k: v for k, v in modulos.items() if v},
        "pacotes": {k: v for k, v in (cfg.get("pacotes") or {}).items() if k != "_comment"},
        "paginas": paginas,
    }


def importa_agente(agente: Path) -> dict:
    """Primeira abertura: traz o config.json, os tokens e os logos do agente antigo."""
    cfg = json.loads((agente / "config.json").read_text(encoding="utf-8"))
    perfil = do_config(cfg)
    caminhos.prepara()
    for nome in ("spotify_token.json", "google_token.json", "google_client_secret.json"):
        org = agente / "segredos" / nome
        if org.exists() and not (caminhos.SEGREDOS / nome).exists():
            shutil.copy2(org, caminhos.SEGREDOS / nome)
    ag = perfil["modulos"].get("agenda") or {}
    if str(ag.get("google_client_secret", "")).startswith("segredos/"):
        ag["google_client_secret"] = ag["google_client_secret"][len("segredos/"):]
    if (agente / "logos").is_dir():
        for f in (agente / "logos").iterdir():
            if f.is_file() and not (caminhos.ARQUIVOS / f.name).exists():
                shutil.copy2(f, caminhos.ARQUIVOS / f.name)
    return perfil


# ----------------------------------------------------------- disco

def ler() -> dict | None:
    try:
        p = json.loads(caminhos.PERFIL.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if p.get("esquema") != ESQUEMA:
        raise ValueError(f"perfil esquema {p.get('esquema')} (esperado {ESQUEMA})")
    return p


def salvar(perfil: dict) -> None:
    """Grava atomico (arquivo temporario + replace) e guarda o anterior."""
    caminhos.prepara()
    if caminhos.PERFIL.exists():
        destino = caminhos.HISTORICO / time.strftime("perfil-%Y%m%d-%H%M%S.json")
        shutil.copy2(caminhos.PERFIL, destino)
        velhos = sorted(caminhos.HISTORICO.glob("perfil-*.json"))
        for v in velhos[:-MAX_HIST]:
            v.unlink(missing_ok=True)
    tmp = caminhos.PERFIL.with_suffix(".tmp")
    tmp.write_text(json.dumps(perfil, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, caminhos.PERFIL)


# --------------------------------------------------------- pacotes

def _pacotes() -> list:
    saida = []
    for raiz in (caminhos.PACOTES, caminhos.PACOTES_USUARIO):
        if not raiz.is_dir():
            continue
        for arq in sorted(raiz.glob("*/pacote.json")):
            try:
                pac = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[pacotes] {arq.parent.name}: pacote.json invalido ({e})")
                continue
            pac.setdefault("id", arq.parent.name)
            pac["_dir"] = str(arq.parent)
            saida = [p for p in saida if p["id"] != pac["id"]] + [pac]   # do usuario ganha
    return saida


def instalado(pac: dict, resolver_app=None) -> bool:
    """Barato de proposito (stat e indice do Menu Iniciar): roda a cada hello."""
    import shutil as _sh
    d = pac.get("detectar") or {}
    if d.get("sempre"):
        return True
    for c in d.get("caminhos", []):
        if Path(os.path.expandvars(os.path.expanduser(c))).exists():
            return True
    if any(_sh.which(cmd) for cmd in d.get("comando", [])):
        return True
    if resolver_app and any(resolver_app(n) for n in d.get("app", [])):
        return True
    if d.get("processo"):
        from . import janelas
        if any(janelas.rodando(p) for p in d["processo"]):
            return True
    return False


def _reescreve(obj, nomes: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("page", "depois", "voltar") and isinstance(v, str) and v in nomes:
                obj[k] = nomes[v]
            else:
                _reescreve(v, nomes)
    elif isinstance(obj, list):
        for v in obj:
            _reescreve(v, nomes)


def _entrada(pac: dict, inicio: str, bid: str) -> dict:
    ap = {"widget": "icone", "icon": "apps", "label": pac.get("nome", pac["id"]),
          **(pac.get("entrada") or {})}
    return {"id": bid, "aparencia": ap, "toque": [{"type": "page", "page": inicio}],
            "_pacote": pac["id"]}


def com_pacotes(perfil: dict, resolver_app=None) -> dict:
    """Perfil efetivo: o do usuario + as paginas dos pacotes ativos.

    Nomes: a pagina de inicio do pacote ganha o id dele ("obs"), as outras
    "<pacote>.<pagina>"; botao vira "<pacote>.<botao>" (o id do botao e a base
    do id da arte - dois "mic" nao podem se confundir). Pagina do usuario com o
    mesmo id ganha da do pacote. `{"pacote": "obs"}` no lugar de um botao vira
    a entrada do pacote, ou some. A pagina `apps` lista as entradas.
    """
    ef = copy.deepcopy(perfil)
    paginas = ef.setdefault("paginas", {})
    opc = ef.get("pacotes") or {}
    desligados, forcar = set(opc.get("desligados", [])), set(opc.get("forcar", []))
    resumo, entradas = [], {}

    for pac in _pacotes():
        pid = pac["id"]
        inst = instalado(pac, resolver_app)
        ativo = (inst or pid in forcar) and pid not in desligados
        resumo.append({"id": pid, "nome": pac.get("nome", pid), "instalado": inst, "ativo": ativo})
        pags = pac.get("paginas") or {}
        if not ativo or not pags:
            continue
        inicio = pac.get("inicio") or next(iter(pags))
        nomes = {p: (pid if p == inicio else f"{pid}.{p}") for p in pags}
        ids = [b["id"] for pg in pags.values() for b in pg.get("botoes", [])]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            print(f"[pacotes] {pid}: id de botao repetido entre paginas: {', '.join(repetidos)}")
        for p, pag in pags.items():
            nome = nomes[p]
            if nome in paginas:
                continue
            pag = copy.deepcopy(pag)
            _reescreve(pag, nomes)
            pag.setdefault("voltar", "home" if p == inicio else nomes[inicio])
            pag["_pacote"], pag["_dir"] = pid, pac["_dir"]
            for b in pag.get("botoes", []):
                b["id"] = f"{pid}.{b['id']}"
                b["_pacote"] = pid
            paginas[nome] = pag
        entradas[pid] = (pac, nomes[inicio])

    for nome, pag in paginas.items():
        botoes = []
        for b in pag.get("botoes", []):
            if "pacote" in b and "toque" not in b:
                if b["pacote"] in entradas:
                    pac, ini = entradas[b["pacote"]]
                    botoes.append(_entrada(pac, ini, f"{nome}.ir.{pac['id']}"))
                continue
            botoes.append(b)
        pag["botoes"] = botoes

    if entradas and "apps" not in paginas:
        paginas["apps"] = {"titulo": "Apps", "voltar": "home",
                           "botoes": [_entrada(pac, ini, f"apps.{pid}")
                                      for pid, (pac, ini) in entradas.items()]}
    ef["_pacotes"] = resumo
    return ef
