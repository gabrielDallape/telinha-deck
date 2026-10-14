"""O relogio: hora, dia da semana e data. Vindo do vivos.py do agente."""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


class Relogio:
    @property
    def versao(self) -> str:
        return time.strftime("%H%M")

    def dados(self) -> dict:
        t = time.localtime()
        return {"hora": time.strftime("%H:%M", t),
                "dia_semana": DIAS[t.tm_wday],
                "data": f"{t.tm_mday} de {MESES[t.tm_mon - 1]}"}


# --------------------------------------------------------------------- clima
