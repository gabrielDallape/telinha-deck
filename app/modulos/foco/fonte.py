"""Pomodoro: minutos que faltam num arco. Vindo do vivos.py do agente."""

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

class Foco:
    """Pomodoro de um toque: toque comeca, toque de novo cancela.

    Tres estados - parado, rodando, acabou. O card mostra os minutos que faltam
    e muda de versao uma vez por minuto (um card de ~8 KB por minuto: nada).
    Quando acaba, `aviso()` devolve a mensagem UMA vez, para a barra da tela.
    """

    def __init__(self, minutos: int = 25):
        self.total = max(1, int(minutos)) * 60
        self.estado = "parado"
        self.fim = 0.0
        self.acabou_em = 0.0
        self._aviso = ""

    def _tick(self) -> None:
        agora = time.time()
        if self.estado == "rodando" and agora >= self.fim:
            self.estado = "acabou"
            self.acabou_em = agora
            self._aviso = f"Foco: {self.total // 60} min. Pausa!"
        elif self.estado == "acabou" and agora - self.acabou_em > 600:
            self.estado = "parado"      # dez minutos depois, volta sozinho

    def toque(self) -> str:
        self._tick()
        if self.estado == "parado":
            self.estado = "rodando"
            self.fim = time.time() + self.total
            return "comecou"
        self.estado = "parado"
        return "parou"

    def restante(self) -> int:
        self._tick()
        if self.estado != "rodando":
            return 0
        return max(0, int(self.fim - time.time()))

    @property
    def versao(self) -> str:
        self._tick()
        if self.estado == "rodando":
            return f"r{math.ceil(self.restante() / 60)}"
        return self.estado

    def dados(self) -> dict:
        self._tick()
        r = self.restante()
        return {"estado": self.estado,
                "restante_min": math.ceil(r / 60),
                "total_min": self.total // 60,
                "pct": 100.0 * (1 - r / self.total) if self.estado == "rodando"
                       else (100.0 if self.estado == "acabou" else 0.0)}

    def aviso(self) -> str:
        self._tick()
        a, self._aviso = self._aviso, ""
        return a


# -------------------------------------------------------------------- agenda
