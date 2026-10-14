"""
A placa, de mentira, do jeito que o firmware (telinha_p4.ino) se comporta:

  - "quem" -> hello (com a pagina que esta na tela, ou "" se acabou de ligar)
  - img i=-1 (sondagem) -> imgok i=-1, tem=true se ja tem esse id com esse tamanho
  - img com dados -> guarda no deslocamento `off`; no ultimo pedaco confere o
    tamanho e se o JPEG abre, e so ENTAO confirma (imgbad + imgok se falhou)
  - layout, state, barra, brilho, ack, err -> guardados para o teste olhar

Fala com o nucleo pela mesma interface do pyserial (write, read, in_waiting).
`corromper` faz o proximo pedaco de uma arte chegar estragado, como a CH343
fazia a 2 Mbps.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import time


class PlacaFalsa:
    port = "FALSA"

    def __init__(self, pagina_inicial: str = ""):
        self._rx = b""              # placa -> PC
        self._tx = b""              # PC -> placa (linha incompleta)
        self._lock = threading.Lock()
        self.fechada = False
        self.pagina = pagina_inicial
        self.layout: dict = {}
        self.sprites: dict = {}     # id -> tamanho do JPEG
        self._montando: dict = {}   # id -> bytearray
        self._contados: dict = {}   # id -> bytes recebidos (o firmware conta)
        self.estado: dict = {}
        self.barra = ""
        self.brilho = None
        self.acks: list = []
        self.erros: list = []
        self.eventos: list = []
        self.corromper: set = set()
        self.bytes_recebidos = 0
        self.ruins = 0

    # ------------------------------------------------------- lado do PC

    @property
    def in_waiting(self) -> int:
        self._checa()
        with self._lock:
            return len(self._rx)

    def read(self, n: int = 1) -> bytes:
        self._checa()
        with self._lock:
            if not self._rx:
                pass
            dados, self._rx = self._rx[:n], self._rx[n:]
        if not dados:
            time.sleep(0.005)       # o timeout de 5 ms da serial de verdade
        return dados

    def write(self, dados: bytes) -> int:
        self._checa()
        self.bytes_recebidos += len(dados)
        self._tx += dados
        while b"\n" in self._tx:
            linha, self._tx = self._tx.split(b"\n", 1)
            self._trata(json.loads(linha))
        return len(dados)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.fechada = True

    def _checa(self) -> None:
        if self.fechada:
            import serial
            raise serial.SerialException("placa falsa desligada")

    # ------------------------------------------------------ lado da placa

    def _manda(self, obj: dict) -> None:
        with self._lock:
            self._rx += (json.dumps(obj) + "\n").encode()

    def toque(self, bid: str) -> None:
        self._manda({"cmd": "btn", "page": self.pagina, "id": bid})

    def voltar(self) -> None:
        self._manda({"cmd": "page", "id": self.layout.get("back") or "home"})

    def reinicia(self) -> None:
        """A placa reiniciou: perdeu tudo e pede a home."""
        self.sprites.clear()
        self.pagina = ""
        self._manda({"cmd": "hello", "fw": "falsa-1", "page": ""})

    def _trata(self, m: dict) -> None:
        ev = m.get("ev")
        self.eventos.append(ev)
        if ev == "quem":
            self._manda({"cmd": "hello", "fw": "falsa-1", "page": self.pagina})
        elif ev == "layout":
            self.layout = m
            self.pagina = m["page"]
        elif ev == "img":
            self._img(m)
        elif ev == "state":
            self.estado = {k: v for k, v in m.items() if k != "ev"}
        elif ev == "barra":
            self.barra = m["txt"]
        elif ev == "brilho":
            self.brilho = m["v"]
        elif ev == "ack":
            self.acks.append(m["id"])
        elif ev == "err":
            self.erros.append((m["id"], m.get("msg", "")))

    def _img(self, m: dict) -> None:
        aid, i, n = m["id"], m["i"], m["n"]
        if i == -1:
            tem = self.sprites.get(aid) == m["len"]
            self._manda({"cmd": "imgok", "i": -1, "tem": tem})
            return
        buf = self._montando.setdefault(aid, bytearray(m["len"]))
        pedaco = base64.b64decode(m["d"])
        if aid in self.corromper:
            self.corromper.discard(aid)
            pedaco = pedaco[:-15]       # "faltaram 15 bytes", como na vida real
        buf[m["off"]:m["off"] + len(pedaco)] = pedaco
        self._contados[aid] = self._contados.get(aid, 0) + len(pedaco)
        if i < n - 1:
            self._manda({"cmd": "imgok", "i": i})
            return
        dados = bytes(self._montando.pop(aid))
        ok = self._contados.pop(aid, 0) == m["len"]
        if ok:
            try:
                from PIL import Image
                Image.open(io.BytesIO(dados)).load()
            except Exception:
                ok = False
        if ok:
            self.sprites[aid] = m["len"]
        else:
            self.ruins += 1
            self._manda({"cmd": "imgbad", "id": aid})
        self._manda({"cmd": "imgok", "i": i})

    # --------------------------------------------------------- consultas

    def pagina_completa(self) -> bool:
        """Todas as artes da pagina na tela estao na placa?"""
        bs = self.layout.get("buttons", [])
        return bool(bs) and all(b["art"] in self.sprites for b in bs)
