"""
O coletor de estado: uma thread que pergunta aos modulos ligados como esta o
PC (mic mudo, volume, OBS ao vivo...) a cada `ajustes.estado_ms`, ou na hora
quando alguem pede (`agora()` - depois de um toque, por exemplo). A thread
serial so le o ultimo retrato; nunca chama modulo.
"""

from __future__ import annotations

import threading
import time


class Coletor:
    def __init__(self, nucleo):
        self.n = nucleo
        self._retrato: dict = {}
        self._versao = 0
        self._lock = threading.Lock()
        self._acorda = threading.Event()

    def comeca(self) -> None:
        threading.Thread(target=self._roda, daemon=True, name="estado").start()

    def agora(self) -> None:
        self._acorda.set()

    def ultimo(self) -> tuple:
        with self._lock:
            return self._versao, self._retrato

    def _roda(self) -> None:
        try:
            from comtypes import CoInitialize
            CoInitialize()
        except Exception:
            pass
        while True:
            t0 = time.monotonic()
            try:
                retrato = self.n.hosp.estado()
                self.n.hosp.tick(t0)
            except Exception as e:
                print(f"[estado] {e}")
                retrato = {}
            with self._lock:
                if retrato != self._retrato:
                    self._retrato = retrato
                self._versao += 1
            intervalo = float(self.n.ajuste("estado_ms", 1000)) / 1000.0
            self._acorda.wait(timeout=max(0.05, intervalo - (time.monotonic() - t0)))
            self._acorda.clear()
