"""
Onde mora cada coisa. Programa e dados separados desde o primeiro dia: o
programa pode ser trocado por uma versao nova sem levar junto o perfil, as
contas e o cache de quem usa.

    PROGRAMA   app/ (no desenvolvimento) ou a pasta instalada
    DADOS      %APPDATA%\\TELINHA, ou TELINHA_DADOS se definida (testes)
      perfil.json        paginas e botoes (esquema 2)
      perfil.hist/       as ultimas versoes do perfil, para desfazer
      segredos/          tokens (Spotify, Google)
      cache/             JPEGs ja desenhados
      modulos/<id>/      o que cada modulo guarda
      pacotes/           pacotes de app do usuario (alem dos que vem prontos)
      arquivos/          imagens e .exe usados como icone ("arquivos/x.png")
      estado.json        o nucleo escreve; a bandeja le
      comando.txt        a bandeja escreve ("dormir"); o nucleo le
      telinha.log
"""

from __future__ import annotations

import os
from pathlib import Path

PROGRAMA = Path(__file__).resolve().parent.parent
MODULOS = PROGRAMA / "modulos"
PACOTES = PROGRAMA / "pacotes"
FONTES = Path(__file__).resolve().parent / "fontes"

DADOS = Path(os.environ.get("TELINHA_DADOS")
             or Path(os.environ.get("APPDATA", Path.home())) / "TELINHA")
PERFIL = DADOS / "perfil.json"
HISTORICO = DADOS / "perfil.hist"
SEGREDOS = DADOS / "segredos"
CACHE = DADOS / "cache"
DADOS_MODULOS = DADOS / "modulos"
PACOTES_USUARIO = DADOS / "pacotes"
ARQUIVOS = DADOS / "arquivos"
ESTADO = DADOS / "estado.json"
COMANDO = DADOS / "comando.txt"
API = DADOS / "api.json"          # porta e token da API local (para a janela)
LOG = DADOS / "telinha.log"


def prepara() -> None:
    for p in (DADOS, HISTORICO, SEGREDOS, CACHE, DADOS_MODULOS, PACOTES_USUARIO, ARQUIVOS):
        p.mkdir(parents=True, exist_ok=True)


def arquivo_do_usuario(p: str) -> Path:
    """Caminho de icone/som escrito no perfil: absoluto, com %VAR%, ou relativo
    a DADOS ("arquivos/spotify.png")."""
    q = Path(os.path.expandvars(os.path.expanduser(p)))
    return q if q.is_absolute() else DADOS / q
