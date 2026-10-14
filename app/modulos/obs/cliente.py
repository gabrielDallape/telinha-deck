"""
OBS Studio pelo obs-websocket (vem embutido no OBS 28+: Ferramentas >
Configuracoes do servidor WebSocket). Config:

    "obs": {"host": "localhost", "porta": 4455, "senha": ""}

Uma thread consulta o OBS a cada segundo - cena atual, live, gravacao - e so
tenta conectar enquanto ele estiver aberto, para nao encher o log de recusa.
Consulta em vez de eventos de proposito: o cliente de eventos morre calado
quando o OBS fecha, e a consulta descobre isso na volta seguinte.

O estado sai como chaves do `state` da placa: `obs_live`, `obs_rec`,
`obs_pausa`, e `obsc_<hash>` para cada cena (acesa a que esta no ar). E isso
que pinta os botoes sem regravar nada.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time

logging.getLogger("obsws_python").setLevel(logging.CRITICAL)


def chave_cena(nome: str) -> str:
    """state_key da cena. O firmware guarda 19 caracteres; o hash cabe."""
    return "obsc_" + hashlib.sha1(nome.encode("utf-8")).hexdigest()[:6]


class Obs:
    def __init__(self, cfg: dict | None):
        c = cfg or {}
        self.host = c.get("host", "localhost")
        self.porta = int(c.get("porta", 4455))
        self.senha = c.get("senha", "")
        self.cli = None
        self.lock = threading.Lock()
        self.conectado = False
        self.cena = ""
        self.cenas: list = []
        self.live = self.rec = self.pausa = False
        self.versao_cenas = 0
        self._erro_avisado = ""

    def comeca(self) -> "Obs":
        threading.Thread(target=self._vigia, daemon=True, name="obs").start()
        return self

    # ------------------------------------------------------------- conexao

    def _aberto(self) -> bool:
        from telinha import janelas
        return janelas.rodando("obs64") or janelas.rodando("OBS ")

    def _conecta(self) -> None:
        import obsws_python
        self.cli = obsws_python.ReqClient(host=self.host, port=self.porta,
                                          password=self.senha, timeout=3)
        self.conectado = True
        self._erro_avisado = ""
        print(f"[obs] conectado em {self.host}:{self.porta}")

    def _cai(self, e: Exception | None = None) -> None:
        if self.conectado:
            print(f"[obs] desconectado{': ' + str(e) if e else ''}")
        self.conectado = False
        self.cli = None
        self.live = self.rec = self.pausa = False

    def _vigia(self) -> None:
        volta = 0
        while True:
            try:
                if not self.conectado:
                    if self._aberto():
                        with self.lock:
                            self._conecta()
                    else:
                        time.sleep(3)
                        continue
                with self.lock:
                    self.cena = self.cli.get_current_program_scene().current_program_scene_name
                    self.live = bool(self.cli.get_stream_status().output_active)
                    r = self.cli.get_record_status()
                    self.rec, self.pausa = bool(r.output_active), bool(r.output_paused)
                    if volta % 5 == 0:
                        nomes = [s["sceneName"] for s in reversed(self.cli.get_scene_list().scenes)]
                        if nomes != self.cenas:
                            self.cenas = nomes
                            self.versao_cenas += 1
                volta += 1
                time.sleep(1)
            except Exception as e:
                msg = str(e)
                if msg != self._erro_avisado:
                    print(f"[obs] {msg}")
                    self._erro_avisado = msg
                with self.lock:
                    self._cai()
                time.sleep(5)

    # ------------------------------------------------------------- estado

    def estado(self) -> dict:
        e = {"obs_live": self.live, "obs_rec": self.rec, "obs_pausa": self.pausa}
        for nome in self.cenas:
            e[chave_cena(nome)] = nome == self.cena
        return e

    # -------------------------------------------------------------- acoes

    def executa(self, acao: dict) -> None:
        if not self.conectado:
            raise RuntimeError("OBS fechado ou WebSocket desligado")
        op = acao.get("op", "")
        with self.lock:
            c = self.cli
            if op == "cena":
                c.set_current_program_scene(acao["cena"])
                self.cena = acao["cena"]
            elif op == "live":
                c.toggle_stream()
            elif op == "gravar":
                c.toggle_record()
            elif op == "pausar":
                c.toggle_record_pause()
            elif op == "replay":
                c.save_replay_buffer()
            elif op == "mute":
                c.toggle_input_mute(acao["fonte"])
            elif op == "camera_virtual":
                c.toggle_virtual_cam()
            else:
                raise ValueError(f"op do obs desconhecida: {op!r}")
