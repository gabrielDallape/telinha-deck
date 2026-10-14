"""Achar e abrir apps: indice do Menu Iniciar, protocolos (spotify:), caminhos.
Peca do nucleo: os icones (icon_app), a deteccao de pacotes e o modulo janelas usam."""
import os
import subprocess
import threading
from pathlib import Path

_START_MENUS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]
_atalhos: dict | None = None
_atalhos_lock = threading.Lock()


def _indexar() -> dict:
    global _atalhos
    with _atalhos_lock:
        if _atalhos is None:
            idx = {}
            for raiz in _START_MENUS:
                if raiz.is_dir():
                    for lnk in raiz.rglob("*.lnk"):
                        idx.setdefault(lnk.stem.lower(), lnk)
            _atalhos = idx
        return _atalhos


def resolver_app(nome: str):
    """Atalho do Menu Iniciar pelo nome (exato, ou o menor que contem)."""
    idx = _indexar()
    alvo = nome.lower()
    if alvo in idx:
        return idx[alvo]
    parciais = [p for chave, p in idx.items() if alvo in chave]
    return min(parciais, key=lambda p: len(p.stem)) if parciais else None


def abrir_app(alvo: str) -> None:
    # "spotify:", "https://": protocolo - e assim que abre app da Store
    if ":" in alvo and not Path(alvo).drive and "\\" not in alvo and "/" not in alvo.split(":", 1)[0]:
        os.startfile(alvo)
        return
    p = Path(os.path.expandvars(alvo))
    if p.exists():
        os.startfile(str(p))
        return
    lnk = resolver_app(alvo)
    if lnk:
        os.startfile(str(lnk))
        return
    subprocess.Popen(["cmd", "/c", "start", "", alvo], shell=False)
