"""
Toda a aparencia do painel mora aqui, composta no Pillow, no PC.

A placa nao desenha nada: recebe o card pronto em JPEG e estampa. E o que deixa
usar antialiasing, alpha, gradiente e as fontes da Microsoft numa tela que, por
si, so sabe desenhar retangulo duro - e o que permite mexer no visual sem
regravar a placa uma vez sequer.

Tudo e desenhado em 2x e reduzido no fim (SS): e o antialiasing do pobre, e e
a diferenca entre texto que se le a um metro e texto serrilhado.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTES = Path("C:/Windows/Fonts")
F_ICONES = FONTES / "SegoeIcons.ttf"      # Segoe Fluent Icons (Windows 11)
F_BLACK = FONTES / "seguibl.ttf"
F_BOLD = FONTES / "segoeuib.ttf"
F_SEMI = FONTES / "seguisb.ttf"
F_REG = FONTES / "segoeui.ttf"

SS = 2
FUNDO = 0x0E1116          # o fundo da tela, atras dos cantos arredondados

# Paleta. Mesma familia do JOQUEI para os dois paineis conviverem na mesa.
GRAFITE_A = 0x232B37
GRAFITE_B = 0x151B23
ARO = 0x2C3542
TEXTO = 0xF0F3F7
TEXTO_FRACO = 0x8B95A3
TEXTO_MORTO = 0x5B6572

LARANJA = 0xD97757        # o laranja do Claude
VERDE = 0x30A46C
AMBAR = 0xF5A524
VERMELHO = 0xE5484D
AZUL = 0x3E63DD
ROXO = 0x8E4EC6

# Cor e rotulo de cada estado de sessao. Um lugar so: o card, a pastilha e a
# barra leem daqui, entao nao ha como a tela dizer verde e escrever OCUPADA.
ESTADOS = {
    "trabalhando": (LARANJA, "TRABALHANDO"),
    "pronta": (VERDE, "PRONTA"),
    "parada": (TEXTO_MORTO, "PARADA"),
}

GLYPHS = {
    "focar": 0xE8A7,      # janela para a frente
    "seguir": 0xE768,     # play
    "parar": 0xE71A,      # stop
    "pasta": 0xE838,
    "voltar": 0xE72B,
    "mais": 0xE710,
    "terminal": 0xE756,
    "raio": 0xE945,
    "aprovar": 0xE73E,    # check
    "recusar": 0xE711,    # X
    "relogio": 0xE823,
    "ramo": 0xE9D5,
}

_cache_fonte: dict = {}


def _fonte(caminho: Path, tam: int):
    chave = (str(caminho), tam)
    if chave not in _cache_fonte:
        _cache_fonte[chave] = ImageFont.truetype(str(caminho), tam)
    return _cache_fonte[chave]


def _rgb(v: int) -> tuple:
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def _mistura(a: int, b: int, pct: int) -> tuple:
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return (int(ar * pct / 100 + br * (100 - pct) / 100),
            int(ag * pct / 100 + bg * (100 - pct) / 100),
            int(ab * pct / 100 + bb * (100 - pct) / 100))


# ------------------------------------------------------------------ pecas

def _mascara(tam: tuple, raio: int) -> Image.Image:
    m = Image.new("L", tam, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, tam[0] - 1, tam[1] - 1],
                                        radius=raio, fill=255)
    return m


def _placa(w: int, h: int, topo, baixo, aro, raio: int = 22) -> Image.Image:
    """A base de todo card: gradiente vertical, canto redondo, aro de 1 px.

    Os cantos ja vem preenchidos com a cor da tela, o que dispensa alpha - que
    o JPEG nao teria de qualquer forma.
    """
    g = (w * SS, h * SS)
    grad = Image.new("RGB", (1, g[1]))
    gp = grad.load()
    for y in range(g[1]):
        k = y / max(1, g[1] - 1)
        gp[0, y] = tuple(int(topo[i] + (baixo[i] - topo[i]) * k) for i in range(3))
    img = Image.new("RGB", g, _rgb(FUNDO))
    img.paste(grad.resize(g), (0, 0), _mascara(g, raio * SS))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, g[0] - 1, g[1] - 1], radius=raio * SS, outline=aro, width=2 * SS)
    return img


def _fim(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((w, h), Image.LANCZOS)


def _chip(d, xy, texto, fonte, fundo, tinta, pad=(16, 8)):
    """Pilula solida com texto dentro. Le como forma antes de ler como texto."""
    x, y = xy
    larg = d.textlength(texto, font=fonte)
    x1, y1 = x + larg + pad[0] * 2, y + fonte.size + pad[1] * 2
    d.rounded_rectangle([x, y, x1, y1], radius=(y1 - y) / 2, fill=fundo)
    d.text(((x + x1) / 2, (y + y1) / 2), texto, font=fonte, fill=tinta,
           anchor="mm")
    return x1 - x, y1 - y


def _quebra(d, texto: str, fonte, largura: float, linhas: int) -> list:
    """Quebra por palavra e corta com reticencias na ultima linha."""
    if not texto:
        return []
    palavras, saida, atual = texto.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if d.textlength(teste, font=fonte) <= largura or not atual:
            atual = teste
        else:
            saida.append(atual)
            atual = p
            if len(saida) == linhas:
                break
    if len(saida) < linhas and atual:
        saida.append(atual)
    if len(saida) == linhas and (len(saida) < len(palavras)):
        ult = saida[-1]
        while ult and d.textlength(ult + "...", font=fonte) > largura:
            ult = ult[:-1]
        resto = " ".join(palavras)
        if d.textlength(resto, font=fonte) > largura * linhas:
            saida[-1] = ult.rstrip() + "..."
    return saida[:linhas]


def simbolo_claude(lado: int, cor: tuple, raios: int = 11) -> Image.Image:
    """O asterisco do Claude Code, desenhado - nao ha fonte que o tenha.

    Onze petalas finas que afinam da ponta ate o centro, em 4x e reduzidas:
    poligono fino sem supersampling vira serrilha pura.
    """
    mag = 4
    L = max(4, lado * mag)
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = L / 2
    R = L * 0.47
    fino = 0.22
    for k in range(raios):
        a = math.pi * 2 * k / raios - math.pi / 2
        d.polygon([(cx, cy),
                   (cx + math.cos(a - fino) * R * 0.34,
                    cy + math.sin(a - fino) * R * 0.34),
                   (cx + math.cos(a) * R, cy + math.sin(a) * R),
                   (cx + math.cos(a + fino) * R * 0.34,
                    cy + math.sin(a + fino) * R * 0.34)], fill=cor)
    return img.resize((lado, lado), Image.LANCZOS)


def _glyph(nome: str, lado: int, cor: tuple):
    cp = GLYPHS.get(nome)
    if cp is None or not F_ICONES.exists():
        return None
    f = _fonte(F_ICONES, lado)
    img = Image.new("RGBA", (int(lado * 1.6), int(lado * 1.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((img.width / 2, img.height / 2), chr(cp), font=f, fill=cor + (255,),
           anchor="mm")
    return img.crop(img.getbbox() or (0, 0, 1, 1))


def _barra_ctx(d, x, y, larg, alt, fracao: float, cor):
    """Quanto da janela de contexto ja encheu."""
    d.rounded_rectangle([x, y, x + larg, y + alt], radius=alt / 2,
                        fill=_mistura(FUNDO, GRAFITE_A, 60))
    cheio = max(alt, larg * max(0.0, min(1.0, fracao)))
    d.rounded_rectangle([x, y, x + cheio, y + alt], radius=alt / 2, fill=cor)


# ------------------------------------------------------------------ cards

def _sparkline(d, x, y, larg, alt, valores, cor, cor_fraca):
    """Atividade por minuto, em barrinhas.

    E o que separa um painel de um LED: a FORMA ja diz se a sessao esta a todo
    vapor, so respirando, ou parada ha um tempo - antes de voce ler uma palavra.
    Muda no maximo uma vez por minuto, entao nao pesa na serial.
    """
    n = len(valores) or 1
    teto = max(valores) or 1
    passo = larg / n
    barra = max(2.0, passo * 0.62)
    for i, v in enumerate(valores):
        bx = x + i * passo
        # balde vazio vira um tracinho na base, para a linha do tempo existir
        a = max(2.0, alt * (v / teto)) if v else 2.0
        d.rounded_rectangle([bx, y + alt - a, bx + barra, y + alt],
                            radius=barra / 2, fill=cor if v else cor_fraca)


def card_sessao(w: int, h: int, s: dict, aceso: bool = False) -> Image.Image:
    """Uma sessao do Claude Code, com o que ela esta fazendo agora.

    O card inteiro e o estado: quando a sessao esta trabalhando, a placa troca
    para a versao acesa sem ida a serial (art_on + state_key no firmware).

    O que entra aqui e escolhido pelo custo na serial. Nome e titulo mudam quase
    nunca. O sparkline muda uma vez por minuto. A linha "agora" muda a cada
    ferramenta - uns 16 KB por vez, 3% da banda numa sessao a todo vapor - e
    vale o preco: e a diferenca entre "TRABALHANDO ha 10 min" e "Bash: npm
    test". O que muda a cada segundo continua fora: vai para a barra.
    """
    cor, rotulo = ESTADOS.get(s.get("estado", "pronta"), ESTADOS["pronta"])
    if aceso:
        topo = _mistura(cor, GRAFITE_A, 22)
        baixo = _mistura(cor, GRAFITE_B, 10)
        aro = _mistura(cor, ARO, 55)
    else:
        topo, baixo, aro = _rgb(GRAFITE_A), _rgb(GRAFITE_B), _rgb(ARO)

    img = _placa(w, h, topo, baixo, aro)
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 20 * SS
    escala = min(1.0, w / 300)

    d.rounded_rectangle([pad, pad, pad + 7 * SS, H - pad], radius=4 * SS,
                        fill=_rgb(cor))

    x = pad + 20 * SS
    dir_ = W - pad
    f_nome = _fonte(F_BLACK, int(29 * SS * escala))
    f_rot = _fonte(F_BOLD, int(12 * SS))
    f_tit = _fonte(F_SEMI, int(16 * SS))
    f_pe = _fonte(F_REG, int(13 * SS))
    f_agora = _fonte(F_SEMI, int(14 * SS))

    _chip(d, (x, pad), rotulo, f_rot,
          _rgb(cor) if aceso else _mistura(cor, GRAFITE_B, 28),
          _rgb(0x101418) if aceso else _rgb(cor), pad=(6 * SS, 4 * SS))

    sim = simbolo_claude(int(24 * SS), _mistura(cor, GRAFITE_A, 70) + (255,))
    img.paste(sim, (dir_ - sim.width, pad + 2 * SS), sim)

    y = pad + int(30 * SS)
    d.text((x, y), (s.get("nome") or "?")[:18], font=f_nome, fill=_rgb(TEXTO))
    y += int(f_nome.size * 1.12)

    titulo = s.get("titulo") or s.get("prompt") or "sessao sem titulo"
    for linha in _quebra(d, titulo, f_tit, dir_ - x, 2):
        d.text((x, y), linha, font=f_tit, fill=_rgb(TEXTO_FRACO))
        y += int(f_tit.size * 1.3)

    # --- o que ela esta fazendo agora
    ferr, resumo = s.get("_agora") or ("", "")
    if ferr:
        y += int(6 * SS)
        larg_chip, _a = _chip(d, (x, y), ferr[:12], f_pe,
                              _mistura(cor, GRAFITE_B, 22), _rgb(cor),
                              pad=(6 * SS, 3 * SS))
        if resumo:
            tx = x + larg_chip + int(8 * SS)
            corte = resumo
            while corte and d.textlength(corte, font=f_agora) > dir_ - tx:
                corte = corte[:-1]
            if corte != resumo and corte:
                corte = corte[:-1] + "\u2026"
            d.text((tx, y + int(3 * SS)), corte, font=f_agora,
                   fill=_rgb(TEXTO_FRACO))

    # --- rodape: sparkline, modelo e contexto
    base = H - pad
    ctx = int(s.get("ctx") or 0)
    janela = max(1, int(s.get("janela") or 1))
    pct = ctx / janela
    cor_ctx = VERMELHO if pct > 0.85 else (AMBAR if pct > 0.6 else cor)

    # O rodape tem altura reservada: barra de contexto encostada na base, a
    # linha de texto acima dela, e o sparkline apoiado em cima do conjunto.
    y_barra = base - int(6 * SS)
    y_texto = y_barra - int(10 * SS) - f_pe.size
    modelo = s.get("_modelo_curto") or ""
    if modelo:
        eff = (s.get("effort") or "").strip()
        d.text((x, y_texto),
               modelo + ("  " + eff if eff and eff != "medium" else ""),
               font=f_pe, fill=_rgb(TEXTO_MORTO))
    if ctx:
        d.text((dir_, y_texto), "{}k".format(ctx // 1000), font=f_pe,
               fill=_rgb(cor_ctx), anchor="ra")
        _barra_ctx(d, x, y_barra, dir_ - x, 6 * SS, pct, _rgb(cor_ctx))

    pulso = s.get("_pulso") or []
    alt_spark = 0
    if pulso:
        alt_spark = max(int(16 * SS), min(int(38 * SS), y_texto - y - int(40 * SS)))
        _sparkline(d, x, y_texto - int(10 * SS) - alt_spark, dir_ - x, alt_spark,
                   pulso, _mistura(cor, GRAFITE_A, 75),
                   _mistura(TEXTO_MORTO, GRAFITE_A, 30))

    # o vao que sobra entre o cabecalho e o sparkline: os arquivos tocados.
    # Era o maior vazio do card, e o dado ja vem de graca do transcript.
    arqs = s.get("_arquivos") or []
    teto = y_texto - int(16 * SS) - alt_spark
    if arqs and teto - y > int(26 * SS):
        f_arq = _fonte(F_REG, int(13 * SS))
        ax, ay = x, y + int(8 * SS)
        for nome in arqs[:4]:
            larg = d.textlength(nome, font=f_arq) + int(18 * SS)
            if ax + larg > dir_:
                ax = x
                ay += int(24 * SS)
                if ay + int(20 * SS) > teto:
                    break
            d.rounded_rectangle([ax, ay, ax + larg, ay + int(20 * SS)],
                                radius=int(6 * SS),
                                fill=_mistura(cor, GRAFITE_B, 14))
            d.text((ax + int(9 * SS), ay + int(2 * SS)), nome, font=f_arq,
                   fill=_mistura(TEXTO_FRACO, GRAFITE_A, 80))
            ax += larg + int(7 * SS)
    return _fim(img, w, h)


def card_timeline(w: int, h: int, itens: list,
                  titulo: str = "o que rodou") -> Image.Image:
    """As ultimas ferramentas da sessao, com hora. A fita do que aconteceu."""
    import time as _t
    img = _placa(w, h, _rgb(0x1A2130), _rgb(0x11161F), _rgb(ARO))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 20 * SS

    f_rot = _fonte(F_BOLD, int(12 * SS))
    f_n = _fonte(F_BOLD, int(14 * SS))
    f_t = _fonte(F_REG, int(13 * SS))
    d.text((pad, pad), titulo.upper(), font=f_rot, fill=_rgb(TEXTO_MORTO))

    y = pad + int(26 * SS)
    passo = int(30 * SS)
    for hora, nome, resumo in itens[:6]:
        if y + passo > H - pad + int(8 * SS):
            break
        d.ellipse([pad, y + int(6 * SS), pad + int(7 * SS), y + int(13 * SS)],
                  fill=_rgb(AZUL))
        tx = pad + int(16 * SS)
        d.text((tx, y), nome[:11], font=f_n, fill=_rgb(TEXTO))
        lx = tx + int(d.textlength(nome[:11], font=f_n)) + int(8 * SS)
        if hora:
            d.text((W - pad, y + int(1 * SS)),
                   _t.strftime("%H:%M", _t.localtime(hora)), font=f_t,
                   fill=_rgb(TEXTO_MORTO), anchor="ra")
        if resumo:
            espaco = W - pad - lx - int(44 * SS)
            corte = resumo
            while corte and d.textlength(corte, font=f_t) > espaco:
                corte = corte[:-1]
            d.text((lx, y + int(2 * SS)), corte, font=f_t,
                   fill=_rgb(TEXTO_FRACO))
        y += passo
    if not itens:
        d.text((W / 2, H / 2), "nada ainda", font=f_t, fill=_rgb(TEXTO_MORTO),
               anchor="mm")
    return _fim(img, w, h)


def card_arquivos(w: int, h: int, nomes: list, branch: str = "",
                  turno: float = 0.0) -> Image.Image:
    """Os arquivos que a sessao mexeu. E o que se quer saber antes de aprovar."""
    img = _placa(w, h, _rgb(0x181F2B), _rgb(0x10151D), _rgb(ARO))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 20 * SS

    f_rot = _fonte(F_BOLD, int(12 * SS))
    f_n = _fonte(F_SEMI, int(16 * SS))
    f_t = _fonte(F_REG, int(13 * SS))
    d.text((pad, pad), "ARQUIVOS TOCADOS", font=f_rot, fill=_rgb(TEXTO_MORTO))
    if branch:
        d.text((W - pad, pad), branch[:16], font=f_rot, fill=_rgb(VERDE),
               anchor="ra")

    y = pad + int(28 * SS)
    for nome in nomes[:6]:
        if y + int(26 * SS) > H - pad - int(16 * SS):
            break
        d.rounded_rectangle([pad, y + int(7 * SS), pad + int(5 * SS),
                             y + int(16 * SS)], radius=2 * SS, fill=_rgb(AMBAR))
        d.text((pad + int(14 * SS), y), nome[:26], font=f_n, fill=_rgb(TEXTO))
        y += int(26 * SS)
    if not nomes:
        d.text((W / 2, H / 2 - int(10 * SS)), "nenhum arquivo ainda", font=f_t,
               fill=_rgb(TEXTO_MORTO), anchor="mm")
    if turno:
        d.text((pad, H - pad - f_t.size - int(4 * SS)),
               "turno tipico {:.0f}s".format(turno), font=f_t,
               fill=_rgb(TEXTO_MORTO))
    return _fim(img, w, h)


def card_acao(w: int, h: int, rotulo: str, sub: str, icone: str,
              cor: int, aceso: bool = False) -> Image.Image:
    """Botao de acao: icone grande em cima, rotulo embaixo."""
    if aceso:
        topo, baixo, aro = (_mistura(cor, GRAFITE_A, 40),
                            _mistura(cor, GRAFITE_B, 24), _rgb(cor))
    else:
        topo, baixo, aro = _rgb(GRAFITE_A), _rgb(GRAFITE_B), _rgb(ARO)
    img = _placa(w, h, topo, baixo, aro)
    W, H = w * SS, h * SS

    g = _glyph(icone, int(min(W, H) * 0.34), _rgb(cor))
    if g is not None:
        img.paste(g, ((W - g.width) // 2, int(H * 0.38) - g.height // 2), g)

    d = ImageDraw.Draw(img)
    f = _fonte(F_BOLD, int(22 * SS * min(1.0, w / 300)))
    d.text((W / 2, H * (0.70 if sub else 0.74)), rotulo, font=f,
           fill=_rgb(TEXTO), anchor="mm")
    if sub:
        fs = _fonte(F_REG, int(14 * SS))
        d.text((W / 2, H * 0.83), sub[:28], font=fs, fill=_rgb(TEXTO_MORTO),
               anchor="mm")
    return _fim(img, w, h)


def card_info(w: int, h: int, s: dict) -> Image.Image:
    """O card que nao e botao: o detalhe da sessao, em texto.

    Aqui entra justamente o que NAO pode entrar no card da home - o ultimo
    prompt, o ramo do git, a duracao do turno -, porque esta pagina so existe
    enquanto voce esta olhando para ela.
    """
    cor, rotulo = ESTADOS.get(s.get("estado", "pronta"), ESTADOS["pronta"])
    img = _placa(w, h, _rgb(0x1B2230), _rgb(0x11161F), _mistura(cor, ARO, 35))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 22 * SS

    f_rot = _fonte(F_BOLD, int(13 * SS))
    f_tit = _fonte(F_BOLD, int(19 * SS))
    f_txt = _fonte(F_REG, int(15 * SS))
    f_pe = _fonte(F_REG, int(13 * SS))

    _chip(d, (pad, pad), rotulo, f_rot, _mistura(cor, GRAFITE_B, 30), _rgb(cor),
          pad=(6 * SS, 5 * SS))

    y = pad + int(32 * SS)
    for linha in _quebra(d, s.get("titulo") or "sem titulo", f_tit,
                         W - 2 * pad, 2):
        d.text((pad, y), linha, font=f_tit, fill=_rgb(TEXTO))
        y += int(f_tit.size * 1.3)

    y += int(6 * SS)
    prompt = s.get("prompt") or ""
    if prompt:
        d.text((pad, y), "ultimo pedido", font=f_pe, fill=_rgb(TEXTO_MORTO))
        y += int(f_pe.size * 1.5)
        for linha in _quebra(d, prompt, f_txt, W - 2 * pad, 3):
            d.text((pad, y), linha, font=f_txt, fill=_rgb(TEXTO_FRACO))
            y += int(f_txt.size * 1.3)

    # rodape de metadados, tudo em uma linha
    pes = []
    if s.get("_modelo_curto"):
        pes.append(s["_modelo_curto"] + (" " + s["effort"] if s.get("effort") else ""))
    if s.get("branch"):
        pes.append(s["branch"])
    if s.get("turno_ms"):
        pes.append("turno {:.0f}s".format(s["turno_ms"] / 1000.0))
    if s.get("permissao"):
        pes.append("permissao " + s["permissao"])
    if pes:
        d.text((pad, H - pad - f_pe.size), "   ".join(pes)[:70], font=f_pe,
               fill=_rgb(TEXTO_MORTO))
    return _fim(img, w, h)


def card_projeto(w: int, h: int, nome: str, cor: int) -> Image.Image:
    """Pasta onde voce ja rodou o Claude: um toque abre o terminal com ele."""
    img = _placa(w, h, _mistura(cor, GRAFITE_A, 18), _rgb(GRAFITE_B),
                 _mistura(cor, ARO, 40))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 22 * SS

    sim = simbolo_claude(int(30 * SS), _rgb(cor) + (255,))
    img.paste(sim, (pad, pad), sim)

    f = _fonte(F_BLACK, int(30 * SS * min(1.0, w / 300)))
    y = pad + int(48 * SS)
    for linha in _quebra(d, nome, f, W - 2 * pad, 2):
        d.text((pad, y), linha, font=f, fill=_rgb(TEXTO))
        y += int(f.size * 1.16)

    fp = _fonte(F_REG, int(14 * SS))
    d.text((pad, H - pad - fp.size - int(4 * SS)), "abrir com claude", font=fp,
           fill=_rgb(TEXTO_MORTO))
    return _fim(img, w, h)


def card_uso(w: int, h: int, uso: dict) -> Image.Image:
    """O dia: mensagens, ferramentas e tokens, do stats-cache do proprio CLI."""
    img = _placa(w, h, _rgb(0x1C2430), _rgb(0x121820), _rgb(ARO))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 22 * SS

    f_rot = _fonte(F_BOLD, int(13 * SS))
    d.text((pad, pad), (uso.get("dia") or "sem dados").upper(), font=f_rot,
           fill=_rgb(TEXTO_MORTO))

    tok = uso.get("tokens") or 0
    grande = "{:.1f}M".format(tok / 1e6) if tok >= 1e6 else "{:.0f}k".format(tok / 1e3)
    f_num = _fonte(F_BLACK, int(46 * SS * min(1.0, w / 300)))
    d.text((pad, pad + int(22 * SS)), grande, font=f_num, fill=_rgb(AZUL))

    f = _fonte(F_REG, int(15 * SS))
    y = pad + int(22 * SS) + int(f_num.size * 1.1)
    d.text((pad, y), "tokens", font=f, fill=_rgb(TEXTO_FRACO))
    d.text((pad, H - pad - f.size - int(4 * SS)),
           "{} msgs   {} tools".format(uso.get("msgs", 0), uso.get("tools", 0)),
           font=f, fill=_rgb(TEXTO_MORTO))
    return _fim(img, w, h)


def card_vazio(w: int, h: int, titulo: str, sub: str = "") -> Image.Image:
    img = _placa(w, h, _rgb(0x161C26), _rgb(0x10151C), _rgb(0x1E2530))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    sim = simbolo_claude(int(38 * SS), _mistura(TEXTO_MORTO, GRAFITE_A, 60) + (255,))
    img.paste(sim, ((W - sim.width) // 2, int(H * 0.28)), sim)
    f = _fonte(F_BOLD, int(20 * SS))
    d.text((W / 2, H * 0.62), titulo, font=f, fill=_rgb(TEXTO_FRACO), anchor="mm")
    if sub:
        fs = _fonte(F_REG, int(14 * SS))
        d.text((W / 2, H * 0.73), sub, font=fs, fill=_rgb(TEXTO_MORTO), anchor="mm")
    return _fim(img, w, h)


def _barra_grossa(d, x, y, larg, alt, fracao, cor, fundo=None):
    r = alt / 2
    d.rounded_rectangle([x, y, x + larg, y + alt], radius=r,
                        fill=fundo or _mistura(FUNDO, GRAFITE_A, 55))
    cheio = max(alt, larg * max(0.0, min(1.0, fracao)))
    d.rounded_rectangle([x, y, x + cheio, y + alt], radius=r, fill=cor)


def card_app_som(w: int, h: int, app: dict, aceso: bool = False) -> Image.Image:
    """Um aplicativo no mixer. Tocar muta; o card aceso e o app mudo.

    O deej resolveu volume por app com potenciometro e virou padrao do nicho.
    A tela mostra o que o potenciometro nao mostra: o nome de quem esta fazendo
    barulho, e quanto.
    """
    mudo = app.get("mudo")
    cor = VERMELHO if mudo else (VERDE if app.get("pico", 0) > 0.001 else AZUL)
    if aceso or mudo:
        topo, baixo, aro = (_mistura(cor, GRAFITE_A, 30),
                            _mistura(cor, GRAFITE_B, 16), _rgb(cor))
    else:
        topo, baixo, aro = _rgb(GRAFITE_A), _rgb(GRAFITE_B), _rgb(ARO)
    img = _placa(w, h, topo, baixo, aro)
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 20 * SS

    f_n = _fonte(F_BLACK, int(26 * SS * min(1.0, w / 300)))
    f_v = _fonte(F_BLACK, int(34 * SS * min(1.0, w / 300)))
    f_t = _fonte(F_REG, int(13 * SS))

    d.text((pad, pad + int(4 * SS)), app.get("nome", "?")[:14], font=f_n,
           fill=_rgb(TEXTO))
    d.text((pad, H / 2 - int(6 * SS)),
           "MUDO" if mudo else "{}".format(app.get("vol", 0)),
           font=f_v, fill=_rgb(cor))
    if not mudo:
        d.text((pad + d.textlength(str(app.get("vol", 0)), font=f_v) + int(6 * SS),
                H / 2 + int(14 * SS)), "%", font=f_t, fill=_rgb(TEXTO_MORTO))

    y_dica = H - pad - f_t.size - int(2 * SS)
    _barra_grossa(d, pad, y_dica - int(10 * SS) - 8 * SS, W - 2 * pad, 8 * SS,
                  0 if mudo else app.get("vol", 0) / 100.0, _rgb(cor))
    d.text((pad, y_dica), "tocar para mutar", font=f_t, fill=_rgb(TEXTO_MORTO))
    return _fim(img, w, h)


def card_musica(w: int, h: int, capa: bytes, titulo: str, artista: str,
                tocando: bool = True) -> Image.Image:
    """O que esta tocando, com a CAPA cobrindo o card.

    Sem a capa isto seria mais um botao de play com texto. Com ela da para ver
    do outro lado da mesa o que esta tocando - e e o tipo de coisa que so um
    painel com a arte composta no PC consegue fazer.
    """
    from io import BytesIO
    W, H = w * SS, h * SS
    if capa:
        try:
            fundo = Image.open(BytesIO(capa)).convert("RGB")
            # cobre o card inteiro sem distorcer
            k = max(W / fundo.width, H / fundo.height)
            fundo = fundo.resize((max(1, int(fundo.width * k)),
                                  max(1, int(fundo.height * k))), Image.LANCZOS)
            ex = (fundo.width - W) // 2
            ey = (fundo.height - H) // 2
            img = fundo.crop((ex, ey, ex + W, ey + H))
        except Exception:
            img = None
    else:
        img = None
    if img is None:
        img = _placa(w * 1, h * 1, _rgb(0x24303F), _rgb(0x141A22), _rgb(ARO))
    else:
        # escurece a base para o texto ter onde pousar
        veu = Image.new("L", (1, H))
        vp = veu.load()
        for y in range(H):
            k = y / max(1, H - 1)
            vp[0, y] = int(235 * max(0.0, (k - 0.34) / 0.66) ** 1.25)
        preto = Image.new("RGB", (W, H), (6, 8, 11))
        img = Image.composite(preto, img, veu.resize((W, H)))
        fora = Image.new("RGB", (W, H), _rgb(FUNDO))
        fora.paste(img, (0, 0), _mascara((W, H), 22 * SS))
        img = fora

    d = ImageDraw.Draw(img)
    pad = 20 * SS
    f_t = _fonte(F_BLACK, int(24 * SS * min(1.0, w / 300)))
    f_a = _fonte(F_SEMI, int(16 * SS))
    f_r = _fonte(F_BOLD, int(12 * SS))

    _chip(d, (pad, pad), "TOCANDO" if tocando else "PAUSADO", f_r,
          _rgb(VERDE) if tocando else _mistura(TEXTO_MORTO, GRAFITE_B, 40),
          _rgb(0x0B0E12) if tocando else _rgb(TEXTO_FRACO), pad=(6 * SS, 4 * SS))

    y = H - pad - int(f_a.size * 1.5)
    if artista:
        d.text((pad, y), artista[:30], font=f_a, fill=_rgb(TEXTO_FRACO))
    linhas = _quebra(d, titulo or "nada tocando", f_t, W - 2 * pad, 2)
    y -= int(f_t.size * 1.15) * len(linhas)
    for l in linhas:
        d.text((pad, y), l, font=f_t, fill=_rgb(TEXTO))
        y += int(f_t.size * 1.15)
    return _fim(img, w, h)


def card_navegar(w: int, h: int, titulo: str, sub: str, icone: str,
                 cor: int, destaque: str = "", linhas=None) -> Image.Image:
    """Card que leva a outra pagina.

    Alem do numero grande, aceita `linhas` - [(rotulo, fracao, cor)] - que viram
    mini-barras no miolo. Sem elas o card e uma porta com um numero; com elas
    ja responde a pergunta antes de voce abrir a pagina.
    """
    img = _placa(w, h, _mistura(cor, GRAFITE_A, 16), _rgb(GRAFITE_B),
                 _mistura(cor, ARO, 35))
    d = ImageDraw.Draw(img)
    W, H = w * SS, h * SS
    pad = 20 * SS

    g = _glyph(icone, int(min(W, H) * 0.20), _rgb(cor))
    if g is not None:
        img.paste(g, (pad, pad), g)

    f_n = _fonte(F_BLACK, int(28 * SS * min(1.0, w / 300)))
    f_s = _fonte(F_REG, int(14 * SS))
    f_d = _fonte(F_BLACK, int(40 * SS * min(1.0, w / 300)))

    if destaque:
        d.text((W - pad, pad + int(2 * SS)), destaque, font=f_d,
               fill=_rgb(cor), anchor="ra")

    y_sub = H - pad - f_s.size - int(4 * SS)
    y_tit = y_sub - int(6 * SS) - f_n.size
    if linhas:
        # o bloco tem de TERMINAR acima do titulo, senao a ultima barra passa
        # por baixo dele - foi o que aconteceu na primeira versao
        f_l = _fonte(F_SEMI, int(13 * SS))
        alt = int(7 * SS)
        passo = int(30 * SS)
        y = y_tit - int(12 * SS) - passo * len(linhas)
        for rotulo, frac, c in linhas:
            d.text((pad, y), rotulo, font=f_l, fill=_rgb(TEXTO_FRACO))
            d.text((W - pad, y), "{:.0f}%".format(frac * 100), font=f_l,
                   fill=_rgb(c), anchor="ra")
            _barra_grossa(d, pad, y + int(17 * SS), W - 2 * pad, alt, frac,
                          _rgb(c))
            y += passo
    d.text((pad, y_tit), titulo, font=f_n, fill=_rgb(TEXTO))
    d.text((pad, y_sub), sub[:32], font=f_s, fill=_rgb(TEXTO_MORTO))
    return _fim(img, w, h)


# --------------------------------------------------------------- para a tela

def para_jpeg(img: Image.Image, q: int = 90) -> bytes:
    """JPEG em vez de RGB565 cru: ~35 KB no lugar de 252 KB por card.

    A placa decodifica uma vez para um sprite na PSRAM, entao o custo e pago no
    primeiro desenho e nunca mais. Com a serial a 38 KB/s, mandar cru seria
    quase sete segundos por card.
    """
    from io import BytesIO
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=q, subsampling=0,
                            optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    # Folha de contato: gera um PNG com todos os cards para olhar sem a placa.
    import sessoes
    W, H = 410, 308
    vivas = sessoes.vivas()
    exemplo = vivas[0] if vivas else {
        "nome": "joquei", "titulo": "Pesquisa de projetos similares no GitHub",
        "prompt": "monta uma parada muito maneira ai com tudo isso",
        "estado": "trabalhando", "ctx": 173000, "janela": 200000,
        "effort": "high", "branch": "main", "turno_ms": 184091,
        "permissao": "auto"}
    exemplo = dict(exemplo)
    exemplo["_modelo_curto"] = sessoes.modelo_curto(exemplo.get("modelo", ""))

    parado = dict(exemplo, estado="pronta", nome="otimizacao-pc",
                  titulo="Verificacao do desktopcommander.app")
    cards = [card_sessao(W, H, exemplo, True), card_sessao(W, H, parado, False),
             card_info(W, H, exemplo),
             card_acao(W, H, "Focar", "traz a janela", "focar", AZUL),
             card_acao(W, H, "Continuar", "manda 'continua'", "seguir", VERDE),
             card_acao(W, H, "Parar", "manda esc", "parar", VERMELHO),
             card_projeto(W, H, "Norfolk AI", ROXO),
             card_uso(W, H, sessoes.uso_hoje()),
             card_vazio(W, H, "Nenhuma sessao", "abra o claude em algum projeto")]
    folha = Image.new("RGB", (3 * (W + 16) + 16, 3 * (H + 16) + 16), _rgb(FUNDO))
    for i, c in enumerate(cards):
        folha.paste(c, (16 + (i % 3) * (W + 16), 16 + (i // 3) * (H + 16)))
    folha.save("folha.png")
    print("folha.png:", folha.size)
