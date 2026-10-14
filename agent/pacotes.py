"""
Pacotes de app: cada app que o painel conhece mora numa pasta em `pacotes/`,
com um `pacote.json` que diz como achar o app instalado e que paginas e
atalhos ele traz.

    pacotes/obs/pacote.json
    {
      "id": "obs", "nome": "OBS Studio",
      "detectar": {"app": ["OBS Studio"], "processo": ["obs64.exe"]},
      "entrada": {"icon": "broadcast", "color": "#7C66DC", "label": "OBS"},
      "inicio": "obs",
      "paginas": {"obs": {...}, "cenas": {...}}
    }

O carregador roda junto com a leitura do config.json e devolve UM config so: as
paginas dos pacotes ativos entram em `pages` como se tivessem sido escritas a
mao. Daqui para frente nada no agente sabe que pacote existe - foco por janela,
cards vivos, cache de arte e acoes funcionam igual.

Nomes. A pagina de inicio do pacote ganha o id do pacote ("obs"); as outras,
"<pacote>.<pagina>" ("obs.cenas"). Botao vira "<pacote>.<botao>": dois pacotes
podem ter um "mic" sem que um roube a arte do outro (o id do botao E o id da
arte). Referencias a paginas do proprio pacote em `page`, `then` e `back` sao
reescritas; as de fora ("home", "dev", outro pacote) ficam como estao.

Ativo = detectado no PC, menos `pacotes.desligados`, mais `pacotes.forcar`.
Pagina do config.json com o mesmo id ganha do pacote: e assim que se personaliza
um pacote sem mexer na pasta dele.

Atalho de pacote em qualquer pagina: `{"pacote": "obs"}` no lugar de um botao
vira a `entrada` do pacote, ou some se ele nao estiver ativo. A pagina `apps` e
gerada com a entrada de todos os ativos.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

PASTA = Path(__file__).resolve().parent / "pacotes"
_REFS = ("page", "then")


def _ler(arq: Path) -> dict | None:
    try:
        pac = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"[pacotes] {arq.parent.name}: pacote.json invalido ({e})")
        return None
    pac.setdefault("id", arq.parent.name)
    pac["_dir"] = str(arq.parent)
    return pac


def todos() -> list:
    if not PASTA.is_dir():
        return []
    return [p for p in (_ler(a) for a in sorted(PASTA.glob("*/pacote.json"))) if p]


def instalado(pac: dict, resolver_app=None) -> bool:
    """Barato de proposito (stat e indice do Menu Iniciar): roda a cada hello."""
    d = pac.get("detectar") or {}
    if d.get("sempre"):
        return True
    for c in d.get("caminhos", []):
        if Path(os.path.expandvars(os.path.expanduser(c))).exists():
            return True
    for cmd in d.get("comando", []):
        if shutil.which(cmd):
            return True
    if resolver_app:
        for nome in d.get("app", []):
            if resolver_app(nome):
                return True
    if d.get("processo"):
        import janelas
        if any(janelas.rodando(p) for p in d["processo"]):
            return True
    return False


def _reescreve(obj, nomes: dict):
    """page/then que apontam para uma pagina do pacote ganham o nome global."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _REFS and isinstance(v, str) and v in nomes:
                obj[k] = nomes[v]
            else:
                _reescreve(v, nomes)
    elif isinstance(obj, list):
        for v in obj:
            _reescreve(v, nomes)


def _entrada(pac: dict, nome_inicio: str, bid: str) -> dict:
    e = dict(pac.get("entrada") or {})
    e.setdefault("label", pac.get("nome", pac["id"]))
    e.setdefault("icon", "apps")
    return {**e, "id": bid, "type": "page", "page": nome_inicio,
            "_pacote": pac["id"]}


def aplicar(cfg: dict, resolver_app=None) -> dict:
    """Junta as paginas dos pacotes ativos ao config. Muda e devolve `cfg`."""
    opc = cfg.get("pacotes") or {}
    desligados = set(opc.get("desligados", []))
    forcar = set(opc.get("forcar", []))
    paginas = cfg.setdefault("pages", {})
    resumo, entradas = [], {}

    for pac in todos():
        pid = pac["id"]
        inst = instalado(pac, resolver_app)
        ativo = (inst or pid in forcar) and pid not in desligados
        resumo.append({"id": pid, "nome": pac.get("nome", pid),
                       "instalado": inst, "ativo": ativo})
        if not ativo:
            continue
        pags = pac.get("paginas") or {}
        if not pags:
            continue
        inicio = pac.get("inicio") or next(iter(pags))
        nomes = {p: (pid if p == inicio else f"{pid}.{p}") for p in pags}
        ids = [b["id"] for pag in pags.values() for b in pag.get("buttons", [])]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            # o id do botao e o id da arte: o segundo herdaria o desenho do primeiro
            print(f"[pacotes] {pid}: id de botao repetido entre paginas: {', '.join(repetidos)}")
        for p, pag in pags.items():
            nome = nomes[p]
            if nome in paginas:
                print(f"[pacotes] {pid}: pagina '{nome}' ja existe no config.json, fica a de la")
                continue
            pag = copy.deepcopy(pag)
            _reescreve(pag, nomes)
            if pag.get("back") in nomes:
                pag["back"] = nomes[pag["back"]]
            pag.setdefault("back", "home" if p == inicio else nomes[inicio])
            pag["_pacote"], pag["_dir"] = pid, pac["_dir"]
            for b in pag.get("buttons", []):
                b["id"] = f"{pid}.{b['id']}"
                b["_pacote"] = pid
            paginas[nome] = pag
        entradas[pid] = (pac, nomes[inicio])

    # {"pacote": "obs"} em qualquer pagina vira a entrada (ou some)
    for nome, pag in paginas.items():
        botoes = []
        for b in pag.get("buttons", []):
            if "pacote" in b and "type" not in b:
                if b["pacote"] in entradas:
                    pac, ini = entradas[b["pacote"]]
                    botoes.append({**_entrada(pac, ini, f"{nome}.ir.{pac['id']}"),
                                   **{k: v for k, v in b.items() if k != "pacote"}})
                continue
            botoes.append(b)
        pag["buttons"] = botoes

    if entradas and "apps" not in paginas:
        paginas["apps"] = {
            "title": "Apps", "back": "home",
            "buttons": [_entrada(pac, ini, f"apps.{pid}")
                        for pid, (pac, ini) in entradas.items()],
        }

    cfg["_pacotes"] = resumo
    return cfg
