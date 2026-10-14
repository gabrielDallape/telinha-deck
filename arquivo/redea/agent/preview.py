"""
A tela inteira, do jeito que a placa vai desenhar, num PNG.

Nao e enfeite: o ciclo "mexe no card, grava a placa, olha" leva minutos; aqui
leva um segundo. Como a placa so estampa o que o Pillow compoe, este PNG e
fiel - a barra e o unico pedaco desenhado no firmware, e esta redesenhada aqui
com a mesma geometria e as mesmas cores.

    python preview.py                 a home
    python preview.py ses/10164       uma pagina especifica
    python preview.py --todas         todas as paginas, um PNG cada
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import arte
import paginas
import redea_agent

BARRA = 0x151A21          # JQ_BARRA do firmware
LINHA = 0x21262D
SAIDA = Path(__file__).resolve().parent / "preview"


def _barra(img: Image.Image, titulo: str, back: str, txt: str) -> None:
    d = ImageDraw.Draw(img)
    W, H = paginas.TELA_W, paginas.BARRA_H
    d.rectangle([0, 0, W, H], fill=arte._rgb(BARRA))
    d.rectangle([0, H - 2, W, H], fill=arte._rgb(LINHA))

    x = 24
    if back:
        # a seta de voltar, desenhada em linhas como no firmware
        cx, cy = 44, H // 2
        for i in range(5):
            d.line([(cx + 11, cy - 15 + i), (cx - 6 + i, cy)],
                   fill=arte._rgb(arte.TEXTO))
            d.line([(cx - 6 + i, cy), (cx + 11, cy + 15 - i)],
                   fill=arte._rgb(arte.TEXTO))
        d.line([(cx + 46, 14), (cx + 46, H - 14)], fill=arte._rgb(0x30363D))
        x = 72

    f = arte._fonte(arte.F_BOLD, 26)
    d.text((x, H / 2), titulo or "REDEA", font=f, fill=arte._rgb(arte.TEXTO),
           anchor="lm")
    d.ellipse([paginas.TELA_W - 37, H // 2 - 9, paginas.TELA_W - 19, H // 2 + 9],
              fill=arte._rgb(arte.VERDE))
    fp = arte._fonte(arte.F_REG, 15)
    d.text((paginas.TELA_W - 46, H / 2), txt, font=fp,
           fill=arte._rgb(arte.TEXTO_FRACO), anchor="rm")


def desenha(painel, pid: str) -> Image.Image:
    pag = painel.pagina(pid)
    if not pag:
        raise SystemExit("pagina desconhecida: " + pid)
    cols, rows = pag["grid"]["cols"], pag["grid"]["rows"]
    w, h = painel.tamanho_card(cols, rows)
    cw = paginas.TELA_W // cols
    ch = (paginas.TELA_H - paginas.BARRA_H) // rows

    tela = Image.new("RGB", (paginas.TELA_W, paginas.TELA_H), arte._rgb(arte.FUNDO))
    _barra(tela, pag.get("title", ""), pag.get("back", ""), painel.resumo())

    acesos = painel.estado()
    for i, b in enumerate(pag["buttons"]):
        chave = b["art"]
        if b.get("state_key") and acesos.get(b["state_key"]) and b.get("art_on"):
            chave = b["art_on"]
        dados = painel.arte(chave, w, h)
        if not dados:
            continue
        card = Image.open(io.BytesIO(dados))
        x = (i % cols) * cw + paginas.MARGEM
        y = paginas.BARRA_H + (i // cols) * ch + paginas.MARGEM
        tela.paste(card, (x, y))
    return tela


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = redea_agent.carregar_config()
    painel = paginas.Painel(cfg)
    SAIDA.mkdir(exist_ok=True)

    argv = sys.argv[1:]
    alvos = painel.paginas_conhecidas() if (argv and argv[0] == "--todas") \
        else (argv or ["home"])
    for pid in alvos:
        img = desenha(painel, pid)
        nome = pid.replace("/", "_") + ".png"
        img.save(SAIDA / nome)
        print("preview/{}  {}x{}".format(nome, img.width, img.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
