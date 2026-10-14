"""Os seus projetos, num toque: abre o terminal na pasta certa com o Claude ja rodando.

O caminho manual e sempre o mesmo - achar a pasta, abrir terminal, `cd`, digitar
`claude`. Sao quinze segundos e a vontade de comecar ja passou. Aqui e um toque.

A lista sai do `config.json`. Se estiver vazia, o painel varre a area de trabalho
e pega o que TEM CARA DE PROJETO - pasta com `.git`, `CLAUDE.md`, `package.json`
ou codigo solto. Pasta de fotos e "Nova pasta (2)" ficam de fora sozinhas.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

# Ordem importa: e ela que decide a cor e o rotulo quando nada foi configurado.
_MARCAS = ("CLAUDE.md", ".git", "package.json", "pyproject.toml", "Cargo.toml")

_CORES = ["#5865F2", "#F5A524", "#30A46C", "#E5484D", "#8E4EC6",
          "#3E63DD", "#E93D82", "#12A594", "#F76B15", "#6E56CF"]


_CODIGO = (".py", ".ino", ".ts", ".tsx", ".js", ".cs", ".cpp", ".rs", ".go")


def _tem_codigo(p: Path) -> bool:
    try:
        return any(f.suffix.lower() in _CODIGO for f in p.iterdir() if f.is_file())
    except OSError:
        return False


def _eh_projeto(p: Path, fundo: bool = True) -> bool:
    """Pasta de projeto. `fundo` deixa olhar um nivel abaixo.

    Sem descer um nivel a varredura perdia justamente os dois projetos mais
    usados desta maquina: a TELINHA guarda o codigo em `agent/` e `firmware/`, e
    o dos mapas mora em `r6/r6-tatica`. Uma pasta nao deixa de ser projeto por
    ter a raiz arrumada.
    """
    if not p.is_dir() or p.name.startswith("."):
        return False
    if any((p / m).exists() for m in _MARCAS) or _tem_codigo(p):
        return True
    if not fundo:
        return False
    try:
        return any(_eh_projeto(sub, fundo=False) for sub in p.iterdir() if sub.is_dir())
    except OSError:
        return False


def _resolver(p: Path) -> Path:
    """`r6` sozinho nao serve de nada; o que se abre e `r6/r6-tatica`."""
    if any((p / m).exists() for m in _MARCAS) or _tem_codigo(p):
        return p
    # So desce quando a subpasta tem marca FORTE (.git, CLAUDE.md, package.json).
    # Codigo solto nao basta: o JOQUEI tem `agent/*.py`, e descer ali abriria o
    # terminal dentro de agent em vez da raiz do projeto.
    try:
        dentro = [s for s in p.iterdir()
                  if s.is_dir() and any((s / m).exists() for m in _MARCAS)]
    except OSError:
        return p
    return dentro[0] if len(dentro) == 1 else p


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:      # pasta sumiu, placeholder do OneDrive, rede caida
        return 0.0


def descobrir(raiz: Path) -> list:
    try:
        if not raiz.is_dir():
            return []
        achados = [_resolver(p) for p in sorted(raiz.iterdir()) if _eh_projeto(p)]
    except OSError:
        return []
    # mais recentemente mexido primeiro: e quase sempre o que voce quer abrir
    achados.sort(key=_mtime, reverse=True)
    return achados


def ambiente_limpo() -> dict:
    """Ambiente para o terminal novo, sem as marcas de uma sessao do Claude.

    Se o agente foi iniciado de dentro de uma sessao do Claude Code (o Claude
    subindo o TELINHA.bat, por exemplo), ele herda CLAUDECODE, CLAUDE_CODE_*,
    CLAUDE_PID... e repassa tudo ao `claude` que o card abre. O filho entao se
    acha uma sub-sessao: "Transcript saving is off - inherited
    CLAUDE_CODE_CHILD_SESSION marker", e a conversa nao vai para o disco - nem
    aparece no REDEA. O terminal do card tem de nascer como se fosse aberto a
    mao.
    """
    # NO_COLOR / FORCE_COLOR / GIT_TERMINAL_PROMPT / CI vem das ferramentas do
    # Claude Code e deixavam o terminal do card todo cinza. WT_SESSION e
    # WT_PROFILE_ID sao da janela de quem lancou; a janela nova define as suas.
    fora = {"CLAUDECODE", "NO_COLOR", "FORCE_COLOR", "GIT_TERMINAL_PROMPT", "CI",
            "WT_SESSION", "WT_PROFILE_ID"}
    return {k: v for k, v in os.environ.items()
            if not (k.startswith("CLAUDE_") or k.upper() in fora)}


class Projetos:
    def __init__(self, cfg: dict):
        c = cfg.get("projetos") or {}
        self.raiz = Path(os.path.expandvars(
            c.get("raiz") or (Path.home() / "Desktop")))
        self.comando = c.get("comando", "claude")
        self.lista_fixa = c.get("lista") or []
        self.max = int(c.get("max", 15))
        self._cache: list = []
        self._ate = 0.0

    def itens(self) -> list:
        """[(id, rotulo, caminho, cor)] - o que vai virar card.

        Guardado por 30 s: a varredura custa 35 ms e era refeita uma vez por
        card DESENHADO e outra a cada toque - 16 varreduras so para abrir a
        pagina, dentro do loop serial. Pasta nova aparece no proximo minuto.
        """
        agora = time.monotonic()
        if self._cache and agora < self._ate:
            return self._cache
        if self.lista_fixa:
            caminhos = []
            for nome in self.lista_fixa:
                p = Path(os.path.expandvars(nome))
                if not p.is_absolute():
                    p = self.raiz / nome
                if p.is_dir():
                    caminhos.append(p)
        else:
            caminhos = descobrir(self.raiz)

        saida, usados = [], set()
        for i, p in enumerate(caminhos[:self.max]):
            pid = "".join(ch if ch.isalnum() else "_" for ch in p.name.lower())
            # 'mercado livre+++' e 'mercado-livre---' normalizam para o mesmo id
            base, n = pid, 2
            while pid in usados:
                pid = f"{base}{n}"
                n += 1
            usados.add(pid)
            saida.append((pid, p.name, p, _CORES[i % len(_CORES)]))
        self._cache, self._ate = saida, agora + 30.0
        return saida

    def caminho(self, pid: str):
        for i, rot, p, cor in self.itens():
            if i == pid:
                return p
        return None

    def abrir(self, pid: str) -> None:
        """Abre o Windows Terminal na pasta e ja dispara o comando."""
        p = self.caminho(pid)
        if p is None:
            raise RuntimeError("projeto nao encontrado")

        # O `wt -d <pasta>` abre a aba JA na pasta, entao nao precisa de `cd`. O
        # `-NoExit` mantem o terminal vivo depois que o comando sair, senao a
        # janela fecha na cara de quem tocou.
        wt = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WindowsApps/wt.exe"
        if wt.exists():
            subprocess.Popen(
                [str(wt), "-d", str(p), "pwsh", "-NoExit", "-Command", self.comando],
                close_fds=True, env=ambiente_limpo())
        else:
            subprocess.Popen(
                ["cmd", "/c", "start", "", "cmd", "/k",
                 f'cd /d "{p}" && {self.comando}'],
                close_fds=True, env=ambiente_limpo())
