"""CPU e RAM (psutil). Vindo do vivos.py do agente."""

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

class Sistema:
    """CPU e memoria, via psutil, numa thread. Versao em degraus de 5%: o card
    so e remandado quando o numero que aparece muda."""

    def __init__(self, intervalo: float = 5.0):
        self.intervalo = intervalo
        self._d = {"cpu": 0.0, "ram": 0.0, "ram_gb": 0.0, "ram_total_gb": 0.0}
        self._lock = threading.Lock()
        self._vivo = False

    def comeca(self) -> None:
        if self._vivo:
            return
        self._vivo = True
        threading.Thread(target=self._roda, daemon=True, name="sistema").start()

    def _roda(self) -> None:
        import psutil
        psutil.cpu_percent(None)
        while True:
            try:
                m = psutil.virtual_memory()
                d = {"cpu": psutil.cpu_percent(interval=1.0), "ram": m.percent,
                     "ram_gb": (m.total - m.available) / 2**30, "ram_total_gb": m.total / 2**30}
                with self._lock:
                    self._d = d
            except Exception as e:
                print(f"[sistema] {e}")
            time.sleep(max(0.5, self.intervalo - 1.0))

    def dados(self) -> dict:
        with self._lock:
            return dict(self._d)

    @property
    def versao(self) -> str:
        d = self.dados()
        return f"{int(d['cpu'] // 5) * 5}|{int(d['ram'] // 5) * 5}"
