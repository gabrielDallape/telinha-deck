"""
Descobre QUE PEDACO de um card mudou, para mandar so ele.

O painel manda cada card como um JPEG inteiro. Isso e barato quando o card
aparece uma vez e fica, e caro quando o conteudo muda em uso: um card de
410x308 sao 16 KB, e quando quatro sessoes estao trabalhando - cada uma
trocando a linha do "agora" a cada ferramenta que roda - a serial de 38 KB/s
satura, a arte comeca a chegar corrompida e a tela pisca.

Mas o que muda num card quase nunca e o card. E uma faixa: a linha da
ferramenta, ou a barra de contexto, ou o sparkline. Aqui essa faixa e
localizada e recortada, e o resto nem sai do PC.

A ideia e a mesma do RemoteWebViewServer, que renderiza a pagina num Chromium
headless e manda so os tiles que mudaram. A diferenca e que aqui o "servidor"
ja sabe o que desenhou, entao o diff e exato e nao precisa de heuristica.
"""

from __future__ import annotations

from PIL import Image, ImageChops

FAIXAS = 10          # em quantas fatias horizontais o card e olhado
ALINHA = 8           # JPEG trabalha em blocos de 8: alinhar evita borda suja
LIMITE = 0.55        # acima disso, remendar sai mais caro que mandar inteiro


def _agrupa(indices: list, faixas: int, altura: int) -> list:
    """Faixas contiguas viram um retangulo so - menos remendos, menos idas."""
    if not indices:
        return []
    grupos, ini, ant = [], indices[0], indices[0]
    for i in indices[1:]:
        if i == ant + 1:
            ant = i
            continue
        grupos.append((ini, ant))
        ini = ant = i
    grupos.append((ini, ant))

    saida = []
    for a, b in grupos:
        y0 = a * altura // faixas
        y1 = (b + 1) * altura // faixas
        saida.append((y0, min(altura, y1)))
    return saida


def diferenca(antes: Image.Image, agora: Image.Image) -> list:
    """[(x0, y0, x1, y1)] do que mudou. Lista vazia = nada mudou.

    Devolve None quando nao vale a pena remendar (mudou demais, ou as imagens
    nem sao comparaveis) - a quem chama cabe mandar o card inteiro.
    """
    if antes is None or agora is None:
        return None
    if antes.size != agora.size or antes.mode != agora.mode:
        return None

    w, h = agora.size
    mudou = []
    for i in range(FAIXAS):
        y0 = i * h // FAIXAS
        y1 = (i + 1) * h // FAIXAS
        if y1 <= y0:
            continue
        a = antes.crop((0, y0, w, y1))
        b = agora.crop((0, y0, w, y1))
        if ImageChops.difference(a, b).getbbox() is not None:
            mudou.append(i)

    if not mudou:
        return []

    caixas = []
    area = 0
    for y0, y1 in _agrupa(mudou, FAIXAS, h):
        # dentro da faixa, olha tambem onde mudou na horizontal: uma barra de
        # contexto que cresce nao precisa levar junto a metade vazia do card
        faixa = ImageChops.difference(antes.crop((0, y0, w, y1)),
                                      agora.crop((0, y0, w, y1))).getbbox()
        x0, x1 = (0, w) if faixa is None else (faixa[0], faixa[2])
        x0 = max(0, (x0 // ALINHA) * ALINHA)
        x1 = min(w, -(-x1 // ALINHA) * ALINHA)
        y0 = max(0, (y0 // ALINHA) * ALINHA)
        y1 = min(h, -(-y1 // ALINHA) * ALINHA)
        if x1 <= x0 or y1 <= y0:
            continue
        caixas.append((x0, y0, x1, y1))
        area += (x1 - x0) * (y1 - y0)

    if not caixas or area > w * h * LIMITE:
        return None
    return caixas


def recorta(img: Image.Image, caixa: tuple) -> Image.Image:
    return img.crop(caixa)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import arte
    import sessoes

    ss = sessoes.vivas()
    if not ss:
        print("nenhuma sessao para testar")
        raise SystemExit(0)
    s = dict(ss[0])
    s["_modelo_curto"] = sessoes.modelo_curto(s.get("modelo", ""))
    s["_pulso"] = [1, 2, 0, 3]
    s["_agora"] = ("Bash", "cd C:/projetos/REDEA")
    a = arte.card_sessao(410, 308, s, True)
    s2 = dict(s, _agora=("Edit", "paginas.py"))
    b = arte.card_sessao(410, 308, s2, True)

    caixas = diferenca(a, b)
    inteiro = len(arte.para_jpeg(b))
    print("card inteiro: {} bytes".format(inteiro))
    if caixas is None:
        print("mudou demais: mandaria inteiro")
    else:
        total = sum(len(arte.para_jpeg(recorta(b, c))) for c in caixas)
        print("remendos: {} caixa(s), {} bytes -> {:.0f}% do card".format(
            len(caixas), total, total * 100.0 / inteiro))
        for c in caixas:
            print("   ", c)
