"""Abrir e trazer apps para a frente (no monitor certo), atalhos de teclado,
teclas de midia e digitar no terminal - sempre conferindo a janela antes."""
import ctypes
import os
import subprocess
import threading
import time
from pathlib import Path

from telinha import janelas
from telinha.sdk import Modulo, acao

user32 = ctypes.windll.user32
KEYEVENTF_KEYUP = 0x0002
VK = {
    "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "tab": 0x09, "esc": 0x1B, "enter": 0x0D, "space": 0x20,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "prtsc": 0x2C, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22, "del": 0x2E, "ins": 0x2D,
    "backspace": 0x08, "capslock": 0x14,
}


def _vk(nome: str) -> int:
    nome = nome.strip().lower()
    if nome in VK:
        return VK[nome]
    if len(nome) == 1:
        return user32.VkKeyScanW(ord(nome.upper())) & 0xFF
    raise ValueError(f"tecla desconhecida: {nome}")


def send_key(combo: str) -> None:
    teclas = [_vk(p) for p in combo.split("+") if p.strip()]
    for k in teclas:
        user32.keybd_event(k, 0, 0, 0)
    for k in reversed(teclas):
        user32.keybd_event(k, 0, KEYEVENTF_KEYUP, 0)


from telinha.apps import abrir_app, resolver_app  # noqa: E402,F401


class Janelas(Modulo):
    @acao("focus_or_launch")
    def focus_or_launch(self, p):
        if not janelas.focar_ou_none(p["target"], p.get("monitor"), p.get("maximize", True)):
            # `launch` quando o que abre nao e o que se foca (Store: foca
            # "Spotify", abre "spotify:")
            abrir_app(p.get("launch") or p["target"])

    @acao("focus")
    def focus(self, p):
        if not janelas.focar_ou_none(p["target"], p.get("monitor"), p.get("maximize", True)):
            raise RuntimeError("janela nao encontrada")

    @acao("launch")
    def launch(self, p):
        abrir_app(p["target"])

    @acao("url")
    def url(self, p):
        os.startfile(p["target"])

    @acao("shell")
    def shell(self, p):
        subprocess.Popen(p["target"], shell=True)

    @acao("key")
    def key(self, p):
        send_key(p["target"])

    @acao("media")
    def media(self, p):
        send_key(p["key"])

    @acao("key_app")
    def key_app(self, p):
        """Atalho global de um app, so se ele estiver aberto: solto, cairia em
        quem estiver na frente."""
        if janelas.rodando(p["app"]):
            send_key(p["target"])
        elif p.get("exigir", True):
            raise RuntimeError(f"{p['app']} nao esta aberto")

    @acao("digitar")
    def digitar(self, p):
        """Digita na janela em foco - SO se ela for a esperada. Solto, um
        "/clear" + Enter cairia no Discord."""
        regra = p.get("exigir", {"exe": "windowsterminal.exe"})
        if regra and not janelas.frente_bate(regra):
            raise RuntimeError(p.get("erro", "janela certa nao esta na frente"))
        if p.get("texto"):
            janelas.digitar(p["texto"])
        if p.get("tecla"):
            janelas.atalho([_vk(t) for t in p["tecla"].split("+") if t.strip()])
        elif p.get("enter", False):
            janelas.atalho([VK["enter"]])
        if p.get("confirmar"):
            # o /model no meio da conversa abre um dialogo que pede Enter. Numa
            # thread a parte: o toque termina (e navega) sem esperar o dialogo.
            def confirma(espera=float(p["confirmar"]), regra=regra):
                time.sleep(espera)
                if not regra or janelas.frente_bate(regra):
                    janelas.atalho([VK["enter"]])
            threading.Thread(target=confirma, daemon=True).start()
