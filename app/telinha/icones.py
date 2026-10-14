"""
Extrai o icone REAL de um app do Windows e converte para o formato da tela.

Por que nao desenhar os logos a mao no firmware: cada logo novo custaria codigo,
e "coloca o logo do Chrome" tem de valer para qualquer app que o Gabriel adicionar
depois, sem eu ter que redesenhar nada. O Windows ja guarda o icone bonito dentro
do executavel - basta pedir no tamanho certo.

O alpha e recuperado desenhando o icone DUAS vezes, sobre preto e sobre branco:

    sobre_preto  P = C*a
    sobre_branco B = C*a + (1-a)*255   =>   a = 1 - (B-P)/255   e   C = P/a

Isso funciona tanto para os icones PNG modernos de 32 bits quanto para os antigos
com mascara, sem depender de o GDI preservar o canal alpha num DDB - que e onde a
abordagem obvia (ler o hbmColor direto) falha em algumas maquinas.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image

user32 = ctypes.windll.user32
user32.PrivateExtractIconsW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT),
    wintypes.UINT, wintypes.DWORD,
]
user32.PrivateExtractIconsW.restype = wintypes.UINT

COR_CHAVE = 0xF81F   # magenta puro em RGB565: o "vazio" do icone na tela


# ------------------------------------------------------------------- resolucao

def resolver_exe(alvo: str) -> str | None:
    """Aceita caminho de .exe, caminho de .lnk ou nome do Menu Iniciar."""
    p = Path(os.path.expandvars(alvo))
    if p.suffix.lower() == ".lnk" and p.exists():
        return _alvo_do_atalho(p)
    if p.exists():
        return str(p)

    from .apps import resolver_app     # o indice do Menu Iniciar
    lnk = resolver_app(alvo)
    if lnk:
        return _alvo_do_atalho(lnk) or str(lnk)
    return None


def _alvo_do_atalho(lnk: Path) -> str | None:
    try:
        import win32com.client
        sh = win32com.client.Dispatch("WScript.Shell")
        destino = sh.CreateShortcut(str(lnk)).TargetPath
        return destino if destino and os.path.exists(destino) else None
    except Exception:
        return None


# --------------------------------------------------------------------- extracao

def _desenha_sobre(hicon, tam: int, cor_fundo: int) -> Image.Image:
    """Desenha o icone sobre uma cor solida e devolve RGB. cor_fundo e 0x00BBGGRR."""
    hdc_tela = win32gui.GetDC(0)
    dc = win32ui.CreateDCFromHandle(hdc_tela)
    memdc = dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dc, tam, tam)
    memdc.SelectObject(bmp)
    try:
        memdc.FillSolidRect((0, 0, tam, tam), cor_fundo)
        win32gui.DrawIconEx(memdc.GetHandleOutput(), 0, 0, hicon,
                            tam, tam, 0, None, win32con.DI_NORMAL)
        bits = bmp.GetBitmapBits(True)
        return Image.frombuffer("RGB", (tam, tam), bits, "raw", "BGRX", 0, 1).copy()
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        memdc.DeleteDC()
        dc.DeleteDC()
        win32gui.ReleaseDC(0, hdc_tela)


def icone_rgba(exe: str, tam: int = 128) -> Image.Image | None:
    """Devolve o icone do executavel como RGBA no tamanho pedido."""
    h = (wintypes.HICON * 1)()
    ids = (wintypes.UINT * 1)()
    n = user32.PrivateExtractIconsW(exe, 0, tam, tam, h, ids, 1, 0)
    if n < 1 or not h[0]:
        return None
    hicon = h[0]
    try:
        sobre_preto  = _desenha_sobre(hicon, tam, 0x000000)
        sobre_branco = _desenha_sobre(hicon, tam, 0xFFFFFF)
    finally:
        win32gui.DestroyIcon(hicon)

    P, B = sobre_preto.load(), sobre_branco.load()
    saida = Image.new("RGBA", (tam, tam))
    S = saida.load()
    for y in range(tam):
        for x in range(tam):
            pr, pg, pb = P[x, y]
            br, bg, bb = B[x, y]
            # o alpha e o mesmo nos tres canais; a media absorve o arredondamento
            dif = ((br - pr) + (bg - pg) + (bb - pb)) / 3.0
            a = max(0.0, min(1.0, 1.0 - dif / 255.0))
            if a <= 0.004:
                S[x, y] = (0, 0, 0, 0)
            else:
                S[x, y] = (min(255, int(pr / a)), min(255, int(pg / a)),
                           min(255, int(pb / a)), int(round(a * 255)))
    return saida


# ------------------------------------------------------------- para a tela

def para_rgb565(img: Image.Image, fundo_rgb: int) -> bytes:
    """RGBA -> RGB565 big-endian, com COR_CHAVE onde o icone e transparente.

    O semitransparente e composto sobre `fundo_rgb` (a cor normal do botao) em vez
    de virar chave: sem isso, todo icone com borda suave ganha um serrilhado duro.
    """
    fr, fg, fb = (fundo_rgb >> 16) & 0xFF, (fundo_rgb >> 8) & 0xFF, fundo_rgb & 0xFF
    px = img.load()
    w, h = img.size
    out = bytearray(w * h * 2)
    i = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 16:
                v = COR_CHAVE
            else:
                if a < 255:
                    k = a / 255.0
                    r = int(r * k + fr * (1 - k))
                    g = int(g * k + fg * (1 - k))
                    b = int(b * k + fb * (1 - k))
                v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                if v == COR_CHAVE:
                    v = 0xF81E          # nao deixa um pixel real virar buraco
            # little-endian: e como lgfx::rgb565_t guarda na memoria, entao a
            # placa aponta pushImage direto no buffer sem reordenar nada.
            out[i] = v & 0xFF
            out[i + 1] = (v >> 8) & 0xFF
            i += 2
    return bytes(out)


def icone_para_tela(alvo: str, tam: int, fundo_rgb: int,
                    salvar_png: str | None = None) -> bytes | None:
    """Caminho completo: nome do app -> bytes RGB565 prontos para a serial."""
    exe = resolver_exe(alvo)
    if not exe:
        return None
    img = icone_rgba(exe, tam)
    if img is None:
        return None
    if salvar_png:
        img.save(salvar_png)
    return para_rgb565(img, fundo_rgb)
