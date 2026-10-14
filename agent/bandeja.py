"""TELINHA na bandeja do Windows: liga, desliga, mostra se a placa esta falando.

E o que substitui o TELINHA.bat na janela preta. Sobe com o Windows (atalho na
pasta Inicializar), fica na setinha ao lado do relogio e roda o agente como
processo filho, sem console. O icone diz o estado:

    verde   conectado a placa
    ambar   agente ligado, esperando a placa (cabo fora)
    cinza   desligado

O agente escreve `agent/estado.json` a cada segundo; a bandeja so le. Nao ha
canal de volta (bandeja -> agente): ligar e desligar e criar e matar o processo.

"Desligar" manda a placa dormir ({"ev":"dormir"}, firmware redea-1.1+ / telinha-1.1): a tela
apaga de verdade (backlight desligado) e a placa fica so escutando a serial.
"Ligar" sobe o agente, cuja primeira mensagem acorda a placa. A energia da
placa continua vindo do USB - nao existe chave por software numa porta comum -
mas com a tela apagada e o loop parado a diferenca e de miliamperes.

Rodar a mao:  pythonw agent/bandeja.py
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

BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent
ESTADO = BASE / "estado.json"
LOG = RAIZ / "telinha.log"
INICIAR = (Path(os.environ.get("APPDATA", "")) /
           "Microsoft/Windows/Start Menu/Programs/Startup/TELINHA.lnk")
CREATE_NO_WINDOW = 0x08000000

VERDE, AMBAR, CINZA, VERMELHO = (63, 217, 138), (245, 165, 36), (110, 118, 130), (229, 72, 77)


def ambiente_limpo() -> dict:
    """Sem marcas de Claude Code nem de ferramentas que apagam cor (ver projetos.py)."""
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
    # o "T": trave + haste
    d.rounded_rectangle([16, 15, 48, 23], radius=4, fill=c)
    d.rounded_rectangle([28, 15, 36, 49], radius=4, fill=c)
    return img


class Bandeja:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.log = None
        self.estado: dict = {}
        self.icon = None

    # ------------------------------------------------------------- agente

    def ligado(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ligar(self) -> None:
        if self.ligado():
            return
        try:
            if LOG.exists() and LOG.stat().st_size > 2_000_000:
                LOG.replace(LOG.with_suffix(".1.log"))
        except OSError:
            pass
        self.log = open(LOG, "a", encoding="utf-8", errors="replace")
        self.log.write(f"\n===== bandeja ligou o agente em {time.strftime('%d/%m %H:%M:%S')} =====\n")
        self.log.flush()
        self.proc = subprocess.Popen(
            [sys.executable.replace("pythonw.exe", "python.exe"), "-u", str(BASE / "telinha_agent.py")],
            cwd=str(BASE), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW, env=ambiente_limpo())

    def desligar(self) -> None:
        if self.proc is not None:
            # Pede ao agente que apague a tela da placa e saia (comando.txt ->
            # {"ev":"dormir"}). So mata se ele nao obedecer em 6 s.
            try:
                (BASE / "comando.txt").write_text("dormir", encoding="utf-8")
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
                (BASE / "comando.txt").unlink()
            except OSError:
                pass
        self.proc = None
        if self.log:
            self.log.write(f"===== bandeja desligou o agente em {time.strftime('%d/%m %H:%M:%S')} =====\n")
            self.log.close()
            self.log = None
        try:
            ESTADO.unlink()
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
            e = json.loads(ESTADO.read_text(encoding="utf-8"))
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
            # o agente caiu sozinho (traceback): sobe de novo, como o .bat fazia
            if self.proc is not None and self.proc.poll() not in (None, 0):
                self.log and self.log.write("===== agente caiu; subindo de novo =====\n")
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
                  f'$s.TargetPath="{pythonw}";$s.Arguments=\'"{BASE / "bandeja.py"}"\';'
                  f'$s.WorkingDirectory="{BASE}";$s.Description="TELINHA na bandeja";$s.Save()')
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           creationflags=CREATE_NO_WINDOW)
        self.atualiza()

    # -------------------------------------------------------------- menu

    def abrir(self, caminho: Path):
        def f(*_):
            os.startfile(str(caminho))
        return f

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
            Item(lambda i: "Desligar painel" if self.ligado() else "Ligar painel", self.alternar, default=True),
            Item("Iniciar com o Windows", self.alterna_inicio, checked=lambda i: self.inicia_com_windows()),
            Menu.SEPARATOR,
            Item("Abrir config.json", self.abrir(BASE / "config.json")),
            Item("Abrir o log", self.abrir(LOG)),
            Item("Abrir a pasta", self.abrir(RAIZ)),
            Menu.SEPARATOR,
            Item("Sair", self.sair),
        )
        self.icon = pystray.Icon("TELINHA", _icone(AMBAR, True), self.texto(), menu)
        self.ligar()
        threading.Thread(target=self.vigia, daemon=True).start()
        self.icon.run()


if __name__ == "__main__":
    Bandeja().roda()
