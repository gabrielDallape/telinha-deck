"""
Achar a janela de uma sessao do Claude e falar com ela.

O pulo do gato: o pid que o CLI grava em sessions/<pid>.json e do node, que NAO
tem janela. Quem tem janela e o terminal que o hospeda - WindowsTerminal.exe,
pwsh, cmd - que e ANCESTRAL desse node. Entao aqui se sobe a arvore de pais e
se procura uma janela visivel em cada degrau.

Limite conhecido e assumido: o Windows Terminal poe varias abas num processo so.
Focar traz a JANELA para a frente, nao a aba exata. Nao ha API publica para
escolher a aba, e o caminho que existiria - falar pelo named pipe que o CLI
expoe em "messagingSocketPath" - depende de um protocolo interno nao publicado.
Digitar por SendInput funciona em qualquer terminal e nao quebra quando o CLI
muda de versao.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

TH32CS_SNAPPROCESS = 0x00000002
SW_RESTORE = 9
SW_SHOW = 5


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def _pais() -> dict:
    """pid -> ppid, para o processo todo da maquina."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return {}
    mapa = {}
    e = PROCESSENTRY32()
    e.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        ok = kernel32.Process32First(snap, ctypes.byref(e))
        while ok:
            mapa[int(e.th32ProcessID)] = int(e.th32ParentProcessID)
            ok = kernel32.Process32Next(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return mapa


def _janelas_por_pid() -> dict:
    """pid -> [hwnd] de janelas de topo visiveis e com titulo."""
    achadas: dict = {}
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                  ctypes.POINTER(wintypes.LPARAM))

    def visita(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, 4):       # GW_OWNER: dialogo, nao a janela
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        achadas.setdefault(int(pid.value), []).append(hwnd)
        return True

    user32.EnumWindows(EnumProc(visita), 0)
    return achadas


def hwnd_da_sessao(pid: int, degraus: int = 6):
    """Janela do terminal que hospeda este pid, subindo a arvore de pais."""
    janelas = _janelas_por_pid()
    if pid in janelas:
        return janelas[pid][0]
    pais = _pais()
    atual = int(pid)
    for _ in range(degraus):
        atual = pais.get(atual, 0)
        if not atual or atual == 4:         # 4 = System, chegou no topo
            return None
        if atual in janelas:
            return janelas[atual][0]
    return None


def focar(hwnd) -> bool:
    """Traz a janela para a frente.

    SetForegroundWindow sozinho e recusado pelo Windows quando quem chama nao
    tem o foco - que e exatamente o caso aqui, o agente e um processo de fundo.
    Grudar no thread de quem esta na frente contorna isso; e o truque padrao.
    """
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)

    alvo = user32.GetWindowThreadProcessId(hwnd, None)
    frente = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    if alvo != frente:
        user32.AttachThreadInput(frente, alvo, True)
        ok = user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(frente, alvo, False)
    else:
        ok = user32.SetForegroundWindow(hwnd)
    return bool(ok)


def focar_sessao(pid: int) -> bool:
    return focar(hwnd_da_sessao(pid))


# ------------------------------------------------------------------ teclado

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK = {"enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
      "up": 0x26, "down": 0x28, "ctrl": 0x11, "shift": 0x10,
      "win": 0x5B, "s": 0x53,
      # teclas de midia: valem para o sistema todo, nao precisam de foco
      "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_ubyte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _manda(entradas: list) -> None:
    n = len(entradas)
    if not n:
        return
    arr = (INPUT * n)(*entradas)
    user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _unicode(ch: str, solta: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if solta else 0)
    ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
    return INPUT(INPUT_KEYBOARD, _U(ki=ki))


def _virtual(vk: int, solta: bool) -> INPUT:
    ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if solta else 0, 0, None)
    return INPUT(INPUT_KEYBOARD, _U(ki=ki))


def digitar(texto: str) -> None:
    """Texto literal, por codepoint.

    KEYEVENTF_UNICODE em vez de VkKeyScan: assim acento, emoji e simbolo saem
    iguais em qualquer layout de teclado, e nao ha risco de o painel mandar
    'ç' e o terminal receber outra coisa.
    """
    entradas = []
    for ch in texto:
        entradas.append(_unicode(ch, False))
        entradas.append(_unicode(ch, True))
    _manda(entradas)


def tecla(nome: str) -> None:
    vk = VK.get(nome.lower())
    if vk is None:
        raise ValueError("tecla desconhecida: " + nome)
    _manda([_virtual(vk, False), _virtual(vk, True)])


def combo(*nomes: str) -> None:
    """Atalho com modificador, tipo ctrl+tab."""
    vks = [VK[n.lower()] for n in nomes]
    entradas = [_virtual(v, False) for v in vks]
    entradas += [_virtual(v, True) for v in reversed(vks)]
    _manda(entradas)


# ---------------------------------------------------------------- abas

def titulo_janela(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _limpa(s: str) -> str:
    """Tira os simbolos de estado que o CLI poe na frente do titulo da aba."""
    return s.strip(" \t◐◑◒◓●○*-•").strip().lower()


def aba_certa(hwnd, alvo: str) -> bool:
    if not alvo:
        return False
    return _limpa(alvo)[:40] in _limpa(titulo_janela(hwnd))


def garantir_aba(pid: int, alvo: str, tentativas: int = 10) -> bool:
    """Gira as abas ate o titulo bater com o da sessao pedida.

    O Windows Terminal poe varias abas num processo so, entao focar a janela
    nao basta: digitar ali podia cair na sessao ERRADA. O titulo da janela e o
    da aba ativa - e o Claude Code poe o ai-title nele -, entao da para conferir
    onde se esta e andar com ctrl+tab ate chegar. Se nao chegar, nao digita.
    """
    hwnd = hwnd_da_sessao(pid)
    if not hwnd or not focar(hwnd):
        return False
    time.sleep(0.1)
    if not alvo:
        return True                     # sem titulo para conferir: so focou
    for _ in range(tentativas):
        if aba_certa(hwnd, alvo):
            return True
        combo("ctrl", "tab")
        time.sleep(0.09)                # o WT anima a troca; ler antes da lixo
    return aba_certa(hwnd, alvo)


def mandar_para(pid: int, texto: str = "", enter: bool = True,
                alvo: str = "", antes: float = 0.12) -> None:
    """Foca a sessao (e a aba certa) e digita. O caminho ate o prompt do CLI."""
    if not garantir_aba(pid, alvo):
        raise RuntimeError("nao achei a aba desta sessao")
    # O terminal precisa de um instante para virar o foco de teclado depois do
    # SetForegroundWindow; sem esta pausa os primeiros caracteres se perdem.
    time.sleep(antes)
    if texto:
        digitar(texto)
        time.sleep(0.05)
    if enter:
        tecla("enter")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import sessoes
    for s in sessoes.vivas():
        h = hwnd_da_sessao(s["pid"])
        titulo = ""
        if h:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            titulo = buf.value
        print("{:18s} pid={:<6d} hwnd={} {}".format(
            s["nome"], s["pid"], h, titulo))
