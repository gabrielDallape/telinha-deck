"""TELINHA na bandeja do Windows: liga, desliga, mostra se a placa esta falando.

Portada do agent/bandeja.py. Sobe com o Windows (atalho na pasta Inicializar),
fica na setinha ao lado do relogio e roda o NUCLEO (`python -m telinha rodar`)
como processo filho, sem console. Se ele cair, sobe de novo. O icone diz:

    verde   conectado a placa
    ambar   nucleo ligado, esperando a placa (cabo fora)
    cinza   desligado

O nucleo escreve DADOS/estado.json a cada segundo; a bandeja so le. Para
desligar, a bandeja escreve "dormir" em DADOS/comando.txt: o nucleo apaga a
tela da placa (backlight desligado, so a serial escutando) e sai.

Rodar a mao (de dentro de app/):  pythonw -m telinha bandeja
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw

from . import caminhos

INICIAR = (Path(os.environ.get("APPDATA", "")) /
           "Microsoft/Windows/Start Menu/Programs/Startup/TELINHA.lnk")
CREATE_NO_WINDOW = 0x08000000

VERDE, AMBAR, CINZA = (63, 217, 138), (245, 165, 36), (110, 118, 130)


def ambiente_limpo() -> dict:
    """Sem marcas de Claude Code nem de ferramentas que apagam cor (ver projetos)."""
    fora = {"CLAUDECODE", "NO_COLOR", "FORCE_COLOR", "GIT_TERMINAL_PROMPT", "CI",
            "WT_SESSION", "WT_PROFILE_ID"}
    return {k: v for k, v in os.environ.items()
            if not (k.startswith("CLAUDE_") or k.upper() in fora)}


def _icone(cor: tuple, ligado: bool) -> Image.Image:
    """Um T arredondado na cor do estado. 64 px; o Windows reduz."""
    L = 64
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, L - 5, L - 5], radius=16, fill=(22, 27, 35, 255),
                        outline=cor + (255,), width=4)
    c = cor + (255,) if ligado else (150, 158, 170, 255)
    d.rounded_rectangle([16, 15, 48, 23], radius=4, fill=c)
    d.rounded_rectangle([28, 15, 36, 49], radius=4, fill=c)
    return img


class Bandeja:
    def __init__(self):
        caminhos.prepara()
        self.proc: subprocess.Popen | None = None
        self.log = None
        self.estado: dict = {}
        self.icon = None

    # ------------------------------------------------------------- nucleo

    def ligado(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ligar(self) -> None:
        if self.ligado():
            return
        try:
            if caminhos.LOG.exists() and caminhos.LOG.stat().st_size > 2_000_000:
                caminhos.LOG.replace(caminhos.LOG.with_suffix(".1.log"))
        except OSError:
            pass
        self.log = open(caminhos.LOG, "a", encoding="utf-8", errors="replace")
        self.log.write(f"\n===== bandeja ligou o nucleo em {time.strftime('%d/%m %H:%M:%S')} =====\n")
        self.log.flush()
        self.proc = subprocess.Popen(
            [sys.executable.replace("pythonw.exe", "python.exe"), "-u", "-m", "telinha", "rodar"],
            cwd=str(caminhos.PROGRAMA), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW, env=ambiente_limpo())

    def desligar(self) -> None:
        if self.proc is not None:
            # pede ao nucleo que apague a tela e saia; so mata se nao obedecer em 6 s
            try:
                caminhos.COMANDO.write_text("dormir", encoding="utf-8")
                self.proc.wait(timeout=6)
            except Exception:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            try:
                caminhos.COMANDO.unlink()
            except OSError:
                pass
        self.proc = None
        if self.log:
            self.log.write(f"===== bandeja desligou o nucleo em {time.strftime('%d/%m %H:%M:%S')} =====\n")
            self.log.close()
            self.log = None
        try:
            caminhos.ESTADO.unlink()
        except OSError:
            pass

    def alternar(self, *_):
        if self.ligado():
            self.desligar()
        else:
            self.ligar()
        self.atualiza()

    # ----------------------------------------------------------- estado

    def le_estado(self) -> dict:
        try:
            e = json.loads(caminhos.ESTADO.read_text(encoding="utf-8"))
            if time.time() - e.get("quando", 0) > 6:
                e["conectado"] = False
                e["porta"] = ""
            return e
        except Exception:
            return {}

    def texto(self) -> str:
        if not self.ligado():
            return "TELINHA desligado - tela apagada"
        e = self.estado
        if e.get("conectado"):
            return f"TELINHA - {e.get('porta', '?')} - pagina {e.get('pagina', '?')}"
        return "TELINHA - esperando a placa"

    def atualiza(self) -> None:
        self.estado = self.le_estado() if self.ligado() else {}
        if not self.ligado():
            cor, lig = CINZA, False
        elif self.estado.get("conectado"):
            cor, lig = VERDE, True
        else:
            cor, lig = AMBAR, True
        if self.icon is not None:
            self.icon.icon = _icone(cor, lig)
            self.icon.title = self.texto()
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def vigia(self) -> None:
        while True:
            time.sleep(2)
            # o nucleo caiu sozinho (traceback): sobe de novo
            if self.proc is not None and self.proc.poll() not in (None, 0):
                self.log and self.log.write("===== nucleo caiu; subindo de novo =====\n")
                self.proc = None
                self.ligar()
            self.atualiza()

    # ---------------------------------------------------------- iniciar

    @staticmethod
    def inicia_com_windows() -> bool:
        return INICIAR.exists()

    def alterna_inicio(self, *_):
        if INICIAR.exists():
            INICIAR.unlink()
        else:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            ps = (f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{INICIAR}");'
                  f'$s.TargetPath="{pythonw}";$s.Arguments="-m telinha bandeja";'
                  f'$s.WorkingDirectory="{caminhos.PROGRAMA}";$s.Description="TELINHA na bandeja";$s.Save()')
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           creationflags=CREATE_NO_WINDOW)
        self.atualiza()

    # -------------------------------------------------------------- menu

    def abrir(self, caminho: Path):
        def f(*_):
            os.startfile(str(caminho))
        return f

    def janela(self, *_):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        subprocess.Popen([str(pythonw), "-m", "telinha", "janela"], cwd=str(caminhos.PROGRAMA),
                         creationflags=CREATE_NO_WINDOW)

    def sair(self, *_):
        self.desligar()
        if self.icon is not None:
            self.icon.stop()

    def roda(self) -> None:
        import pystray
        from pystray import Menu, MenuItem as Item

        menu = Menu(
            Item(lambda i: self.texto(), None, enabled=False),
            Menu.SEPARATOR,
            Item("Abrir TELINHA", self.janela, default=True),
            Item(lambda i: "Desligar painel" if self.ligado() else "Ligar painel", self.alternar),
            Item("Iniciar com o Windows", self.alterna_inicio, checked=lambda i: self.inicia_com_windows()),
            Menu.SEPARATOR,
            Item("Abrir perfil.json", self.abrir(caminhos.PERFIL)),
            Item("Abrir o log", self.abrir(caminhos.LOG)),
            Item("Abrir a pasta de dados", self.abrir(caminhos.DADOS)),
            Menu.SEPARATOR,
            Item("Sair", self.sair),
        )
        self.icon = pystray.Icon("TELINHA", _icone(AMBAR, True), self.texto(), menu)
        self.ligar()
        threading.Thread(target=self.vigia, daemon=True).start()
        self.icon.run()
