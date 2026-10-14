"""
Renderiza a arte dos botoes no PC, com Pillow, e entrega pronta para a tela.

POR QUE AQUI E NAO NO FIRMWARE: a LovyanGFX desenha rapido, mas desenha duro -
sem antialiasing em curva, sem gradiente, com fontes bitmap ASCII. Icone feito com
fillTriangle parece icone feito com fillTriangle. O Pillow tem supersampling,
alpha real, as fontes da Microsoft e o icone extraido do proprio .exe do app.

Entao o PC compoe o botao INTEIRO - fundo, canto arredondado, icone, texto - e a
placa so estampa o bitmap. A placa continua desenhando os estados (pressionado,
aceso) por cima, que precisam ser instantaneos e nao valem uma ida a serial.

Efeito colateral util: mexer no visual nao exige regravar a placa.
"""

from __future__ import annotations

import io as _io
import os
import math
import re
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import caminhos, icones

FONTES = Path("C:/Windows/Fonts")
F_ICONES = FONTES / "SegoeIcons.ttf"      # Segoe Fluent Icons (Windows 11) - reserva
F_BOLD   = FONTES / "segoeuib.ttf"
F_REG    = FONTES / "segoeui.ttf"
F_LIGHT  = FONTES / "segoeuil.ttf"        # Segoe UI Light: o relogio gigante
F_SEMI   = FONTES / "segoeuisl.ttf"       # Segoe UI Semilight: texto grande e calmo

# Phosphor Fill (MIT, fontes/LICENSE-Phosphor.txt): um so desenhista, traco e
# canto iguais em todos os glifos. Codepoints lidos de fontes/phosphor-fill.css
# e conferidos na folha de contatos - nao adivinhados.
F_PHOSPHOR = caminhos.FONTES / "Phosphor-Fill.ttf"
PH = {
    "play":         0xE3D0,   # play
    "pause":        0xE39E,   # pause
    "next":         0xE5A6,   # skip-forward
    "prev":         0xE5A4,   # skip-back
    "mic":          0xE326,   # microphone
    "mic_off":      0xE328,   # microphone-slash
    "spotify":      0xE66E,   # spotify-logo
    "falar":        0xE75C,   # microphone-stage
    "curtir":       0xE2A8,   # heart
    "aleatorio":    0xE422,   # shuffle
    "repetir":      0xE3F6,   # repeat
    "repetir_1":    0xE3F8,   # repeat-once
    "voltar15":     0xE6A8,   # rewind
    "avancar15":    0xE6A6,   # fast-forward
    "dispositivos": 0xEBA4,   # devices
    "musica":       0xE340,   # music-notes
    "youtube":      0xE4FC,   # youtube-logo
    # paginas por janela em foco (claude, discord)
    "aprovar":      0xE184,   # check-circle
    "recusar":      0xE4F8,   # x-circle
    "continuar":    0xE038,   # arrow-counter-clockwise
    "compactar":    0xEC54,   # broom
    "limpar":       0xE21E,   # eraser
    "fone":         0xE2A6,   # headphones
    "fone_off":     0xE584,   # headset (surdo)
    "terminal":     0xEAE8,   # terminal-window
    "parar":        0xE46E,   # stop-circle
    "celular":      0xE1E0,   # device-mobile = /remote-control
    "modelo":       0xE74E,   # brain = /model
    "usage":        0xE628,   # gauge = /usage
    "monitor":      0xE32E,   # monitor
    "volume":       0xE44A,   # speaker-high
    "volume_off":   0xE45A,   # speaker-slash
    "volume_up":    0xE44A,   # speaker-high
    "volume_down":  0xE44C,   # speaker-low
    "snip":         0xE69C,   # selection-plus = recorte de tela
    "image":        0xE69C,
    "lua":          0xE58E,   # moon-stars = descansar
    "lock":         0xE308,   # lock-simple
    "chip":         0xE610,   # cpu
    "camera":       0xE10E,   # camera
    "search":       0xE30C,   # magnifying-glass
    "back":         0xE058,   # arrow-left
    "mais":         0xE3D4,   # plus
    "menos":        0xE32A,   # minus
    # tempo e tela de descanso
    "sol":          0xE472,   # sun
    "lua_cheia":    0xE330,   # moon
    "nuvem":        0xE1AA,   # cloud
    "neblina":      0xE53C,   # cloud-fog
    "floco":        0xE5AA,   # snowflake
    "raio":         0xE2DE,   # lightning
    "gota":         0xE210,   # drop
    "vento":        0xE5D2,   # wind
    "guarda_chuva": 0xE684,   # umbrella
    "pino":         0xE316,   # map-pin
    "calendario":   0xE10A,   # calendar-blank
    "calendario_ok": 0xE712,  # calendar-check
    "calendario_x": 0xE10C,   # calendar-x
    "relogio":      0xE19A,   # clock
    "termometro":   0xE5C6,   # thermometer
    # pacotes: apps, soundboard, live
    "apps":         0xE464,   # squares-four
    "waveform":     0xE802,   # waveform = um som do soundboard
    "megafone":     0xE324,   # megaphone
    "stop":         0xE46C,   # stop
    "broadcast":    0xE0F2,   # broadcast = ao vivo
    "gravar":       0xE3EE,   # record
    "pausa_circ":   0xE3A0,   # pause-circle
    "film":         0xE8C2,   # film-slate = cena
    "replay":       0xE038,   # arrow-counter-clockwise
}

SS = 2                 # supersampling: desenha em 2x e reduz. E o antialiasing.
RGB_TELA = 0x0E1116    # fundo da tela, atras dos cantos arredondados

# Glyphs escolhidos conferindo a folha de contatos, nao pelo nome do codepoint.
GLYPHS = {
    "mic":          0xE720,   # microfone
    "mic_off":      0xEC54,   # microfone com proibido
    "volume":       0xE767,   # alto-falante, tres ondas
    "volume_off":   0xE74F,   # alto-falante com X
    "volume_down":  0xE993,   # alto-falante, uma onda
    "volume_up":    0xE767,
    "play":         0xE768,
    "pause":        0xE769,
    "next":         0xE893,
    "prev":         0xE892,
    "snip":         0xE924,   # recorte tracejado = Win+Shift+S
    "image":        0xE924,
    "back":         0xE72B,
    "search":       0xE721,
    "camera":       0xE722,
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


def _cobre(img: Image.Image, alvo: tuple, foco: float = 0.5) -> Image.Image:
    """Redimensiona e recorta para preencher `alvo` (o mesmo que object-fit: cover)."""
    escala = max(alvo[0] / img.width, alvo[1] / img.height)
    img = img.resize((max(1, int(img.width * escala)),
                      max(1, int(img.height * escala))), Image.LANCZOS)
    ex = (img.width - alvo[0]) // 2
    ey = int((img.height - alvo[1]) * foco)
    return img.crop((ex, ey, ex + alvo[0], ey + alvo[1]))


def _placa(w: int, h: int, cor: int, aceso: bool, raio: int = 26) -> Image.Image:
    """A pastilha do botao: gradiente vertical suave e canto arredondado real."""
    base = 0xE5484D if aceso else cor
    topo = _mistura(base, RGB_TELA, 30 if aceso else 20)
    baixo = _mistura(base, RGB_TELA, 14 if aceso else 9)

    grande = (w * SS, h * SS)
    grad = Image.new("RGB", (1, grande[1]))
    gp = grad.load()
    for y in range(grande[1]):
        k = y / max(1, grande[1] - 1)
        gp[0, y] = tuple(int(topo[i] + (baixo[i] - topo[i]) * k) for i in range(3))
    grad = grad.resize(grande)

    mascara = Image.new("L", grande, 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, grande[0] - 1, grande[1] - 1], radius=raio * SS, fill=255)

    img = Image.new("RGB", grande, _rgb(RGB_TELA))
    img.paste(grad, (0, 0), mascara)

    # aro interno claro: da volume sem precisar de sombra externa
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, grande[0] - 1, grande[1] - 1], radius=raio * SS,
                        outline=_mistura(base, 0xFFFFFF, 62 if aceso else 42),
                        width=2 * SS)
    return img.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------- conteudos

def _glyph_rgba(nome: str, lado: int, cor: tuple) -> Image.Image | None:
    cp = GLYPHS.get(nome)
    if cp is None:
        return None
    img = Image.new("RGBA", (lado * SS, lado * SS), (0, 0, 0, 0))
    f = _fonte(F_ICONES, int(lado * SS * 0.82))
    ImageDraw.Draw(img).text((lado * SS // 2, lado * SS // 2), chr(cp),
                             font=f, fill=cor + (255,), anchor="mm")
    return img.resize((lado, lado), Image.LANCZOS)


def _arredonda(img: Image.Image, raio_pct: float = 0.23) -> Image.Image:
    """Recorta canto arredondado em imagem OPACA.

    Um icon_file sem alpha (PNG de fundo solido) colado cru no botao vira um
    quadrado em volta do desenho. Imagem com alpha de verdade (icone extraido
    de .exe) passa intacta.
    """
    alpha = img.split()[3]
    if alpha.getextrema()[0] < 250:          # ja tem transparencia: nao mexer
        return img
    w, h = img.size
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1],
                                        radius=int(min(w, h) * SS * raio_pct),
                                        fill=255)
    img.putalpha(m.resize((w, h), Image.LANCZOS))
    return img


def _logo_rgba(spec: dict, lado: int) -> Image.Image | None:
    """Logo real do app: `icon_exe` (caminho de um .exe, para app sem atalho no
    Menu Iniciar - Store, ~/.local/bin), `icon_app` (nome no Menu Iniciar) ou
    `icon_file` (imagem). Nessa ordem; o primeiro que der certo vence."""
    if spec.get("icon_exe"):
        p = caminhos.arquivo_do_usuario(spec["icon_exe"])   # relativo = em DADOS
        if p.exists():
            try:
                img = icones.icone_rgba(str(p), 256)
                if img is not None:
                    return _arredonda(img.resize((lado, lado), Image.LANCZOS))
            except Exception:
                pass
    if spec.get("icon_file"):
        p = caminhos.arquivo_do_usuario(spec["icon_file"])
        if p.exists():
            img = Image.open(p).convert("RGBA").resize((lado, lado), Image.LANCZOS)
            return _arredonda(img)
        return None
    if spec.get("icon_app"):
        exe = icones.resolver_exe(spec["icon_app"])
        if not exe:
            return None
        img = icones.icone_rgba(exe, 256)      # sempre no maior, reduz depois
        return _arredonda(img.resize((lado, lado), Image.LANCZOS)) if img else None
    return None


def _badge(img: Image.Image, sinal: str, cor: tuple) -> None:
    """Cola um + ou - grande no canto do icone.

    E o que separa Vol+ de Vol-: os glyphs de uma e tres ondas do Fluent sao
    parecidos demais para um toque de relance.
    """
    w, h = img.size
    r = int(min(w, h) * 0.30)
    cx, cy = w - r - 2, h - r - 2
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(14, 17, 22, 255))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cor + (255,), width=max(2, r // 7))
    e = int(r * 0.86)
    g = max(3, r // 4)
    d.rounded_rectangle([cx - e // 2, cy - g // 2, cx + e // 2, cy + g // 2],
                        radius=g // 2, fill=cor + (255,))
    if sinal == "+":
        d.rounded_rectangle([cx - g // 2, cy - e // 2, cx + g // 2, cy + e // 2],
                            radius=g // 2, fill=cor + (255,))


# ------------------------------------------------------------------ botoes

# ------------------------------------------------------------------- paleta
FUNDO     = 0x0E1116
GRAFITE_A = 0x232B37      # topo da placa neutra
GRAFITE_B = 0x151B23      # base da placa neutra
ARO       = 0x39434F
TEXTO     = 0xE6EDF3
FRACO     = 0x8B949E
LARANJA   = 0xF5A524      # acento ambar: avisos, medidor apertado
VERDE     = 0x30A46C
VERDE_AR  = 0x3FD98A      # o verde de "tocando", mais alto que o #30A46C
VERMELHO  = 0xE5484D
MORTO     = 0x4A525E      # o cinza de pausado / apagado

# Solidos achados na folha de contatos do Segoe Fluent. Traco cheio le a um
# metro; o contorno fino do E768/E767 nao le.
GLYPHS.update({
    "play":        0xF5B0,   # PlaySolid
    "pause":       0xF8AE,   # PauseSolid
    "next":        0xF8AD,   # NextSolid
    "prev":        0xF8AC,
    "mic":         0xF8B1,   # MicSolid
    "mic_off":     0xEC56,   # MicSolid com X
    "volume":      0xF8B2,   # SpeakerSolid
    "volume_off":  0xF8B3,   # SpeakerSolid mudo
    "volume_up":   0xF8B2,
    "volume_down": 0xF8B2,
    "mais":        0xF8AA,
    "menos":       0xF8AB,
    "chip":        0xE950,   # placa/CPU - a pagina de sistema
})


def _ascii(s: str) -> str:
    """As fontes da tela cobrem so ASCII; o ordinal (1o) vira 'o' em vez de tofu."""
    return (str(s).replace("\u00ba", "o").replace("\u00aa", "a")
            .encode("ascii", "ignore").decode())


def _ph(nome: str, lado: int, cor: tuple, alpha: int = 255) -> Image.Image | None:
    """Glifo do Phosphor Fill, em RGBA com `lado` px, centrado pela caixa real.

    Centrar pelo `anchor="mm"` usa a metrica da fonte, e numa fonte de icones a
    metrica nao tem nada a ver com o desenho: o glifo saia deslocado. Aqui a
    caixa do desenho e medida e centrada de verdade.
    """
    cp = PH.get(nome)
    if cp is None or not F_PHOSPHOR.exists():
        return None
    f = _fonte(F_PHOSPHOR, int(lado * 0.92))
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = d.textbbox((0, 0), chr(cp), font=f)
    d.text(((lado - (x1 - x0)) / 2 - x0, (lado - (y1 - y0)) / 2 - y0), chr(cp),
           font=f, fill=cor + (alpha,))
    return img


def _glyph(nome: str, lado: int, cor: tuple, engrossa: int = 0) -> Image.Image | None:
    """Icone por nome. Phosphor primeiro; o Segoe Fluent fica de reserva para um
    nome que o Phosphor nao tenha (`engrossa` dilata o contorno fino dele)."""
    if nome in PH:
        img = _ph(nome, lado * SS, cor)
        return img.resize((lado, lado), Image.LANCZOS) if img is not None else None
    cp = GLYPHS.get(nome)
    if cp is None:
        return None
    img = Image.new("RGBA", (lado * SS, lado * SS), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((lado * SS // 2, lado * SS // 2), chr(cp),
                             font=_fonte(F_ICONES, int(lado * SS * 0.86)),
                             fill=cor + (255,), anchor="mm")
    if engrossa:
        a = img.split()[3].filter(ImageFilter.MaxFilter(engrossa * 2 + 1))
        cheio = Image.new("RGBA", img.size, cor + (255,))
        cheio.putalpha(a)
        img = cheio
    return img.resize((lado, lado), Image.LANCZOS)


def _pastilha(D: int, fundo: tuple, aro: tuple, nome: str, tinta: tuple,
              sinal: str = "", cor_sinal: tuple | None = None,
              fundo_card: tuple = (0, 0, 0)) -> Image.Image:
    """Disco tingido com o glifo dentro. E o que faz os controles parecerem de
    uma familia: mesmo circulo, mesmo tamanho de glifo, so a cor muda.

    `sinal` cola um selo redondo com + ou - no canto: a diferenca entre Vol- e
    Vol+ vira um objeto, nao dois glifos parecidos.
    """
    img = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, D - 1, D - 1], fill=fundo + (255,))
    d.ellipse([0, 0, D - 1, D - 1], outline=aro + (255,), width=max(2, D // 64))
    gl = _ph(nome, int(D * 0.64), tinta)
    if gl is not None:
        p = (D - gl.size[0]) // 2
        img.alpha_composite(gl, (p, p))
    if sinal:
        r = int(D * 0.17)
        cx = cy = int(D * 0.79)
        borda = max(3, D // 40)
        d = ImageDraw.Draw(img)
        d.ellipse([cx - r - borda, cy - r - borda, cx + r + borda, cy + r + borda],
                  fill=fundo_card + (255,))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(cor_sinal or tinta) + (255,))
        t, e = max(3, int(r * 0.28)), int(r * 1.05)
        d.rounded_rectangle([cx - e / 2, cy - t / 2, cx + e / 2, cy + t / 2],
                            radius=t / 2, fill=(255, 255, 255, 255))
        if sinal == "+":
            d.rounded_rectangle([cx - t / 2, cy - e / 2, cx + t / 2, cy + e / 2],
                                radius=t / 2, fill=(255, 255, 255, 255))
    return img


def _mascara(tam: tuple, raio: int) -> Image.Image:
    m = Image.new("L", tam, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, tam[0] - 1, tam[1] - 1],
                                        radius=raio, fill=255)
    return m


def _fecha(img: Image.Image, w: int, h: int, raio: int) -> Image.Image:
    fora = Image.new("RGB", img.size, _rgb(FUNDO))
    fora.paste(img, (0, 0), _mascara(img.size, raio * SS))
    return fora.resize((w, h), Image.LANCZOS)


def _placa_grad(w: int, h: int, topo, baixo, aro, raio: int = 22) -> Image.Image:
    g = (w * SS, h * SS)
    grad = Image.new("RGB", (1, g[1]))
    gp = grad.load()
    for y in range(g[1]):
        k = y / max(1, g[1] - 1)
        gp[0, y] = tuple(int(topo[i] + (baixo[i] - topo[i]) * k) for i in range(3))
    img = Image.new("RGB", g, _rgb(FUNDO))
    img.paste(grad.resize(g), (0, 0), _mascara(g, raio * SS))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, g[0] - 1, g[1] - 1],
                                          radius=raio * SS, outline=aro, width=2 * SS)
    return img


def _chip(d, xy, texto, fonte, fundo, tinta, pad=(14, 7), raio=None):
    """Pilula solida com texto dentro. Le como forma antes de ler como texto."""
    x, y = xy
    l = d.textlength(texto, font=fonte)
    a = fonte.size
    cx0, cy0 = x, y
    cx1, cy1 = x + l + pad[0] * 2, y + a + pad[1] * 2
    r = raio if raio is not None else int((cy1 - cy0) / 2)
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=r, fill=fundo)
    d.text(((cx0 + cx1) / 2, (cy0 + cy1) / 2 + 1), texto, font=fonte,
           fill=tinta, anchor="mm")
    return cx1 - cx0, cy1 - cy0


def _sombra(img, conteudo, pos, forca=0.5, desloca=3, borrao=5):
    s = Image.new("RGBA", img.size, (0, 0, 0, 0))
    preto = Image.new("RGBA", conteudo.size, (0, 0, 0, 255))
    preto.putalpha(conteudo.split()[3].point(lambda a: int(a * forca)))
    s.paste(preto, (pos[0], pos[1] + desloca), preto)
    return Image.alpha_composite(img.convert("RGBA"), s.filter(
        ImageFilter.GaussianBlur(borrao)))


# ------------------------------------------------------- planta enquadrada

_cache_corte: dict = {}


# --------------------------------------------------------------- home

PESOS = {"destino", "controle", "estado"}


def _peso(spec: dict) -> str:
    """Destino = leva para outro lugar (app ou pagina). Estado = le o PC. O
    resto e controle. `type: page` conta como destino: o card do Claude navega
    igual ao Discord e tem de pesar igual a ele, nao igual ao vol-."""
    if spec.get("peso") in PESOS:
        return spec["peso"]
    if spec.get("icon_app") or spec.get("icon_file") or spec.get("type") == "page":
        return "destino"
    return "estado" if spec.get("state_key") else "controle"


def _texto_espacado(d, xy, texto, fonte, tinta, esp, anchor="ls"):
    """Caixa alta com espaco entre letras: curto e grande le a um metro."""
    x, y = xy
    letras = list(texto)
    larg = sum(d.textlength(c, font=fonte) for c in letras) + esp * (len(letras) - 1)
    x = x - larg / 2
    for c in letras:
        d.text((x, y), c, font=fonte, fill=tinta, anchor=anchor)
        x += d.textlength(c, font=fonte) + esp
    return larg


def _barra_nivel(d, g, y, nivel: int, aceso_cor: tuple, apagado_cor: tuple,
                 segmentos: int = 10) -> None:
    """Dez gomos, os acesos contam o volume. Gomo le a um metro; numero nao."""
    nivel = max(0, min(100, int(nivel)))
    pad = int(g[0] * 0.12)
    larg = g[0] - 2 * pad
    gap = 4 * SS
    seg = (larg - gap * (segmentos - 1)) / segmentos
    alt = 12 * SS
    acesos = int(round(nivel / 100 * segmentos))
    if nivel > 0 and acesos == 0:
        acesos = 1
    for k in range(segmentos):
        x0 = pad + k * (seg + gap)
        d.rounded_rectangle([x0, y - alt / 2, x0 + seg, y + alt / 2],
                            radius=3 * SS, fill=aceso_cor if k < acesos else apagado_cor)


def botao_icone(w: int, h: int, spec: dict, aceso: bool = False) -> Image.Image:
    """Home em tres pesos: destino colorido, controle grafite, estado que grita.

    So os destinos (Discord, Chrome, Claude) sao coloridos; o resto e grafite, e
    a unica outra coisa acesa na tela e um estado de verdade (mic mudo = campo
    vermelho). O card e alto (240x308) e o conteudo ganha tres andares: icone
    grande, rotulo em caixa alta, e uma linha fraca embaixo que so aparece
    quando tem algo a dizer - `sub` ("monitor 2", "5 projetos") ou `nivel`, que
    vira uma barra de dez gomos com o volume atual.
    """
    peso = _peso(spec)
    cor = int(str(spec.get("color", "#3E63DD")).lstrip("#"), 16)
    raio = 22
    sub = _tela(spec.get("sub", "") or "")
    nivel = spec.get("nivel")
    if aceso:
        nivel = None            # mudo: o campo vermelho ja diz tudo

    if aceso:
        topo, baixo, aro = _rgb(0xF05056), _rgb(0xB92B31), _rgb(0xFF8C90)
        tinta_glifo, tinta_txt = (255, 255, 255), (255, 236, 236)
        tinta_sub = (255, 205, 207)
        disco, disco_aro = _rgb(0xC9353B), (255, 255, 255)
    elif peso == "destino":
        topo, baixo = _mistura(cor, FUNDO, 52), _mistura(cor, FUNDO, 28)
        aro = _mistura(cor, 0xFFFFFF, 52)
        tinta_glifo, tinta_txt = _mistura(cor, 0xFFFFFF, 92), _mistura(cor, 0xFFFFFF, 96)
        tinta_sub = _mistura(cor, 0xFFFFFF, 70)
        disco, disco_aro = _mistura(cor, FUNDO, 40), _mistura(cor, 0xFFFFFF, 40)
    else:
        topo, baixo, aro = _rgb(GRAFITE_A), _rgb(GRAFITE_B), _rgb(ARO)
        # o glifo leva a cor do botao, clareada ate ler em fundo escuro; a
        # pastilha e a mesma cor bem mais funda. Slate (#5B6572) vira quase
        # branco sobre grafite: e o neutro dos cards de estado, de proposito.
        tinta_glifo = _mistura(cor, 0xFFFFFF, 42) if peso == "controle" else _rgb(TEXTO)
        tinta_txt = _mistura(cor, 0xFFFFFF, 72) if peso == "controle" else _rgb(TEXTO)
        tinta_sub = _rgb(FRACO)
        disco, disco_aro = _mistura(cor, GRAFITE_B, 36), _mistura(cor, GRAFITE_B, 66)

    img = _placa_grad(w, h, topo, baixo, aro, raio)
    g = img.size
    tem_rodape = bool(sub)
    rotulo_txt = (spec.get("label_on") if (aceso and spec.get("label_on")) else spec.get("label", "")) or ""
    # Card so de icone (sem rotulo nem sub): o icone vai para o centro e cresce.
    # A pedido do dono: "os icones ja estao bem definidos, nao precisa da escrita".
    so_icone = not rotulo_txt.strip() and not sub
    escala = 0.74 if so_icone else 0.62
    cy = int(g[1] * (0.5 if so_icone else (0.375 if tem_rodape else 0.415)))

    icone = spec.get("icon", "")
    logo = _logo_rgba(spec, int(min(w, h) * (escala - 0.02)) * SS) if peso == "destino" else None
    if logo is not None:
        conteudo, lado = logo, logo.size[0]
    elif icone == "claude":
        # sem logo real (icon_exe), o Clawd em pixel art faz o papel
        conteudo = clawd(int(min(w, h) * escala) * SS)
        lado = conteudo.size[0]
    else:
        # controle e estado: pastilha redonda, glifo Phosphor dentro. Mesmo
        # disco em todos = uma familia; a cor do glifo e o que muda.
        lado = int(min(w, h) * escala) * SS
        nome = icone
        if aceso and icone == "mic":
            nome = "mic_off"
        elif aceso and icone in ("volume", "volume_up", "volume_down"):
            nome = "volume_off"
        sinal = {"volume_up": "+", "volume_down": "-"}.get(icone, "") if not aceso else ""
        if nome in PH:
            conteudo = _pastilha(lado, disco, disco_aro, nome, tinta_glifo, sinal,
                                 cor_sinal=_mistura(cor, 0xFFFFFF, 78),
                                 fundo_card=_mistura(GRAFITE_A, GRAFITE_B, 50))
        else:
            conteudo = _glyph(nome, lado, tinta_glifo, engrossa=3)

    if conteudo is not None:
        pos = ((g[0] - lado) // 2, cy - lado // 2)
        img = _sombra(img, conteudo, pos, 0.55, 5 * SS, 9 * SS)
        # logo opaco (icon_file sem alpha): um aro
        # na cor do card transforma o quadrado acidental em pastilha de proposito
        if logo is not None and logo.split()[3].getextrema()[0] >= 250:
            ImageDraw.Draw(img).rounded_rectangle(
                [pos[0] - 2 * SS, pos[1] - 2 * SS,
                 pos[0] + lado + 2 * SS - 1, pos[1] + lado + 2 * SS - 1],
                radius=int(lado * 0.23) + 2 * SS,
                outline=_mistura(cor, 0xFFFFFF, 88) + (255,), width=3 * SS)
        img.paste(conteudo, pos, conteudo)
        img = img.convert("RGB")

    d = ImageDraw.Draw(img)
    rotulo = _tela(spec.get("label_on") if (aceso and spec.get("label_on"))
                   else spec.get("label", "")).upper()
    y_rot = int(g[1] * (0.775 if tem_rodape else 0.855))
    if rotulo:
        f = _fonte(F_BOLD, 24 * SS)
        _texto_espacado(d, (g[0] / 2, y_rot), rotulo, f, tinta_txt, 2 * SS)

    if sub:
        f_sub = _fonte(F_REG, 15 * SS)
        d.text((g[0] / 2, int(g[1] * 0.855)), sub, font=f_sub, fill=tinta_sub,
               anchor="ms")

    # A base do card e onde mora o estado. Com nivel, a barra de gomos ocupa
    # essa vaga: "nao esta mudo, esta em 60" e uma leitura so. Sem nivel, o
    # trilho: vermelho aceso, apagado quando nao. Ausencia tambem e leitura.
    if nivel is not None:
        _barra_nivel(d, g, g[1] - 15 * SS, int(nivel), tinta_glifo, _rgb(0x2C3542))
    elif peso == "estado":
        cor_t = _rgb(VERMELHO) if aceso else _rgb(0x2C3542)
        d.rounded_rectangle([int(g[0] * 0.20), g[1] - 13 * SS,
                             int(g[0] * 0.80), g[1] - 8 * SS],
                            radius=3 * SS, fill=cor_t)

    return _fecha(img, w, h, raio)


# --------------------------------------------------------------- para a tela

def para_jpeg(img: Image.Image, q: int = 90) -> bytes:
    """JPEG em vez de RGB565 cru: 35 KB no lugar de 252 KB por card.

    Nao e so economia de tempo - a 38 KB/s, RGB565 cru seria 6,5 s por card.
    A placa decodifica uma vez para um sprite na PSRAM, entao o custo do JPEG e
    pago no primeiro desenho e nunca mais.

    Os cantos arredondados ja vem preenchidos com a cor do fundo da tela, o que
    dispensa alpha - que o JPEG nao teria.
    """
    from io import BytesIO
    buf = BytesIO()
    # 4:4:4 por padrao: logo colorido pequeno borra em 4:2:0. Um card pode pedir
    # 4:2:0 por `img.info["jpeg_subsampling"] = 2` - o relogio da tela de
    # descanso faz isso: texto quase branco em ceu escuro nao tem croma para
    # perder, e sao ~4 KB a menos por minuto.
    sub = int(img.info.get("jpeg_subsampling", 0)) if getattr(img, "info", None) else 0
    img.convert("RGB").save(buf, format="JPEG", quality=q, subsampling=sub,
                            optimize=True)
    return buf.getvalue()


def para_rgb565(img: Image.Image) -> bytes:
    """RGB opaco -> RGB565 little-endian, do jeito que lgfx::rgb565_t espera."""
    px = img.convert("RGB").load()
    w, h = img.size
    out = bytearray(w * h * 2)
    i = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = v & 0xFF
            out[i + 1] = (v >> 8) & 0xFF
            i += 2
    return bytes(out)



def _arco(d, caixa, ini, fim, cor, largura):
    """Arco grosso com ponta redonda - o pieslice da Pillow nao tem cap."""
    d.arc(caixa, ini, fim, fill=cor, width=largura)


def botao_medidor(w: int, h: int, rotulo: str, valor: float, unidade: str,
                  pct: float, detalhe: str = "", cor_base: int = 0x3E63DD
                  ) -> Image.Image:
    """Medidor de velocimetro: o numero grande, o arco conta a historia.

    A cor sai do proprio valor - azul tranquilo, ambar apertado, vermelho no
    talo. E o que deixa a pagina legivel de canto de olho: voce nao le seis
    numeros, voce ve se tem alguma coisa vermelha.
    """
    pct = max(0.0, min(100.0, float(pct)))
    if pct >= 90:
        cor = 0xE5484D
    elif pct >= 70:
        cor = 0xF5A524
    else:
        cor = cor_base

    img = _placa_grad(w, h, _rgb(GRAFITE_A), _rgb(GRAFITE_B), _rgb(ARO), 22)
    img = img.resize((w * SS, h * SS), Image.LANCZOS)
    g = img.size
    d = ImageDraw.Draw(img, "RGBA")

    # Arco de 270 graus, abrindo para baixo: a boca vazia embaixo e onde o
    # rotulo entra sem disputar espaco com o numero.
    lado = int(min(g) * 0.62)
    cx, cy = g[0] // 2, int(g[1] * 0.44)
    caixa = [cx - lado // 2, cy - lado // 2, cx + lado // 2, cy + lado // 2]
    grosso = max(3, int(lado * 0.11))

    _arco(d, caixa, 135, 405, _rgb(0x232B37) + (255,), grosso)
    if pct > 0.5:
        _arco(d, caixa, 135, 135 + int(270 * pct / 100), _rgb(cor) + (255,), grosso)

    f_num = _fonte(F_BOLD, int(lado * 0.36))
    txt = f"{valor:.0f}" if valor >= 10 or valor == int(valor) else f"{valor:.1f}"
    lt = d.textlength(txt, font=f_num)
    f_un = _fonte(F_REG, int(lado * 0.15))
    lu = d.textlength(unidade, font=f_un) if unidade else 0
    x0 = cx - (lt + lu) / 2
    d.text((x0, cy - f_num.size * 0.62), txt, font=f_num, fill=_rgb(TEXTO))
    if unidade:
        d.text((x0 + lt + 2 * SS, cy - f_num.size * 0.62 + f_num.size * 0.42),
               unidade, font=f_un, fill=_rgb(FRACO))

    f_rot = _fonte(F_BOLD, int(13 * SS))
    r = _ascii(rotulo).upper()
    d.text(((g[0] - d.textlength(r, font=f_rot)) / 2, int(g[1] * 0.745)),
           r, font=f_rot, fill=_mistura(cor, 0xFFFFFF, 55))

    if detalhe:
        f_det = _fonte(F_REG, int(12 * SS))
        dt = _ascii(detalhe)
        d.text(((g[0] - d.textlength(dt, font=f_det)) / 2, int(g[1] * 0.845)),
               dt, font=f_det, fill=_rgb(FRACO))

    # _fecha ja reduz de SS para 1x; reduzir antes dava canto de 38 px
    # serrilhado contra os 11 px lisos do resto da tela.
    return _fecha(img, w, h, 22)


# ------------------------------------------------------------ cards vivos

GLYPHS["lock"] = 0xE72E     # cadeado (Win+L)


def _placa_neutra(w: int, h: int, aro=None) -> Image.Image:
    img = _placa_grad(w, h, _rgb(GRAFITE_A), _rgb(GRAFITE_B), aro or _rgb(ARO), 22)
    return img.resize((w * SS, h * SS), Image.LANCZOS) if img.size != (w * SS, h * SS) else img


def _encaixa(d, texto, fonte_path, tam, largura, minimo=12):
    """Fonte que faz `texto` caber em `largura`, encolhendo ate `minimo`."""
    while tam > minimo and d.textlength(texto, font=_fonte(fonte_path, tam * SS)) > largura:
        tam -= 1
    return _fonte(fonte_path, tam * SS)


def botao_relogio(w: int, h: int, hora: str, dia_semana: str, data: str) -> Image.Image:
    """A hora grande, o dia embaixo. E o card que se le do outro lado da sala.

    Sem segundos de proposito: um card por minuto custa 8 KB; um por segundo
    seria um quinto da serial so para um numero que ninguem le a um metro.
    """
    img = _placa_neutra(w, h)
    g = img.size
    d = ImageDraw.Draw(img)

    f_hora = _encaixa(d, hora, F_BOLD, int(h * 0.42), g[0] - 28 * SS, 30)
    d.text((g[0] / 2, int(g[1] * 0.40)), hora, font=f_hora, fill=_rgb(TEXTO), anchor="mm")

    # traco fino entre a hora e a data: separa sem pesar
    d.rounded_rectangle([int(g[0] * 0.34), int(g[1] * 0.635), int(g[0] * 0.66),
                         int(g[1] * 0.635) + 2 * SS], radius=SS, fill=_rgb(0x2C3542))

    f_dia = _encaixa(d, dia_semana, F_BOLD, 17, g[0] - 28 * SS)
    d.text((g[0] / 2, int(g[1] * 0.745)), dia_semana, font=f_dia,
           fill=_mistura(TEXTO, FUNDO, 80), anchor="mm")
    f_data = _encaixa(d, data, F_REG, 15, g[0] - 28 * SS)
    d.text((g[0] / 2, int(g[1] * 0.865)), data, font=f_data, fill=_rgb(FRACO), anchor="mm")
    return _fecha(img, w, h, 22)


def botao_clima(w: int, h: int, d: dict) -> Image.Image:
    """Tempo agora: o desenho e a temperatura grandes, o dia resumido embaixo.

    Sem dados (rede caiu antes da primeira leitura) o card diz isso em vez de
    ficar em branco - ausencia silenciosa parece bug.
    """
    img = _placa_neutra(w, h)
    g = img.size
    dr = ImageDraw.Draw(img)

    if not d:
        dr.text((g[0] / 2, g[1] * 0.42), "sem clima", font=_fonte(F_BOLD, 22 * SS),
                fill=_rgb(FRACO), anchor="mm")
        dr.text((g[0] / 2, g[1] * 0.60), "esperando a rede", font=_fonte(F_REG, 14 * SS),
                fill=_rgb(MORTO), anchor="mm")
        return _fecha(img, w, h, 22)

    lado = int(g[1] * 0.46)
    gl = glifo_tempo(lado, d.get("familia", "nuvem"), d.get("dia", True))
    pos = (14 * SS, int(g[1] * 0.06))
    img = _sombra(img, gl, pos, 0.4, 3 * SS, 5 * SS)
    img.paste(gl, pos, gl)
    img = img.convert("RGB")
    dr = ImageDraw.Draw(img)

    temp = f"{d['temp']}°"
    f_t = _encaixa(dr, temp, F_BOLD, int(h * 0.30), g[0] - lado - 30 * SS, 28)
    dr.text((g[0] - 16 * SS, int(g[1] * 0.30)), temp, font=f_t, fill=_rgb(TEXTO), anchor="rm")

    texto = d.get("texto", "")
    f_c = _encaixa(dr, texto, F_BOLD, 17, g[0] - 28 * SS)
    dr.text((14 * SS, int(g[1] * 0.60)), texto, font=f_c, fill=_mistura(TEXTO, FUNDO, 82),
            anchor="lm")

    f_s = _fonte(F_REG, 14 * SS)
    faixa = f"máx {d['max']}°  mín {d['min']}°"
    dr.text((14 * SS, int(g[1] * 0.745)), faixa, font=f_s, fill=_rgb(FRACO), anchor="lm")

    # chuva so aparece quando importa: e um chip azul, forma antes de texto
    if d.get("chuva", 0) >= 30:
        f_ch = _fonte(F_BOLD, 12 * SS)
        txt = f"chuva {d['chuva']}%"
        larg = dr.textlength(txt, font=f_ch) + 20 * SS
        _chip(dr, (g[0] - 14 * SS - larg, int(g[1] * 0.70)), txt, f_ch,
              _mistura(0x3E63DD, FUNDO, 55), (214, 226, 255), pad=(10 * SS, 4 * SS))

    rodape = d.get("cidade") or ""
    extra = f"sensação {d['sensacao']}°" if abs(d.get("sensacao", d["temp"]) - d["temp"]) >= 2 \
        else f"umidade {d.get('umidade', 0)}%"
    rodape = f"{rodape}  ·  {extra}" if rodape else extra
    f_r = _encaixa(dr, rodape, F_REG, 12, g[0] - 28 * SS, 10)
    dr.text((14 * SS, int(g[1] * 0.885)), rodape, font=f_r, fill=_rgb(MORTO), anchor="lm")
    return _fecha(img, w, h, 22)


def botao_foco(w: int, h: int, d: dict) -> Image.Image:
    """O pomodoro em cima do medidor: arco que enche, minutos que faltam."""
    estado = d.get("estado", "parado")
    if estado == "rodando":
        return botao_medidor(w, h, "Foco", d["restante_min"], "min", d["pct"],
                             "toque para parar", cor_base=VERDE)
    if estado == "acabou":
        return botao_medidor(w, h, "Foco", 0, "min", 100, "acabou - pausa!")
    return botao_medidor(w, h, "Foco", d.get("total_min", 25), "min", 0,
                         "toque para começar", cor_base=0x3E63DD)


# --------------------------------------------------------- tela de descanso

GLYPHS["lua"] = 0xE708      # reserva Segoe; o Phosphor moon-stars entra primeiro

# O CEU. Um so gradiente atravessa os tres cards: cada um recorta a sua fatia
# (col/ncol) de uma composicao de 1264 px, e o halo que nasce no alto a direita
# ilumina a agenda de perto e o relogio de longe. Os vaos de 16 px ficam - sao
# tres janelas para o mesmo ceu, nao tres caixas. A cor segue a hora do dia
# (azul-noite, dourado de manha, laranja no fim da tarde) e o tempo puxa para o
# cinza quando esta fechado.
_CEU = [  # hora, topo, base, halo
    (0.0,  0x0C1328, 0x0E1116, 0x2A3F80),
    (5.0,  0x171A38, 0x0E1116, 0x6B3F78),
    (6.5,  0x2C3E7C, 0x141A26, 0xE8A040),
    (8.5,  0x2A58B4, 0x141C2C, 0xF3C86A),
    (12.0, 0x2F6CC8, 0x152334, 0xF7DD90),
    (16.0, 0x3060B0, 0x16202F, 0xF4B25A),
    (18.0, 0x4E2E62, 0x1A1319, 0xF07A3E),
    (19.5, 0x1C1F48, 0x0F1218, 0x8A4C9A),
    (21.0, 0x0E1634, 0x0E1116, 0x2E4386),
    (24.0, 0x0C1328, 0x0E1116, 0x2A3F80),
]
_CINZA_CEU = {"nuvem": 0x2A3140, "chuva": 0x24303F, "neve": 0x2E3644,
              "neblina": 0x2B313C, "tempestade": 0x1E232E}
VAO_DESCANSO = 16           # 2 x MARGEM do paginas.py: o fundo entre dois cards

# O ultimo clima que passou por um card de clima. O relogio nao recebe o tempo
# e mesmo assim tem de pintar o mesmo ceu que o card do lado - senao chove num
# card e faz sol no outro. Fica um minuto atrasado no pior caso.
_tempo_visto: dict = {}
ESCALA_RELOGIO = 0.64       # tamanho do digito em fracao da largura do card
N_ESTRELAS = 42


def _lerp_cor(a: tuple, b: tuple, k: float) -> tuple:
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


def _paleta_ceu(hora: float | None = None, familia: str | None = None) -> dict:
    if hora is None:
        t = time.localtime()
        hora = t.tm_hour + t.tm_min / 60.0
    if familia is None:
        familia = _tempo_visto.get("familia", "sol")
    topo, base, halo = _rgb(_CEU[0][1]), _rgb(_CEU[0][2]), _rgb(_CEU[0][3])
    for (h0, t0, b0, l0), (h1, t1, b1, l1) in zip(_CEU, _CEU[1:]):
        if h0 <= hora <= h1:
            k = (hora - h0) / (h1 - h0)
            topo = _lerp_cor(_rgb(t0), _rgb(t1), k)
            base = _lerp_cor(_rgb(b0), _rgb(b1), k)
            halo = _lerp_cor(_rgb(l0), _rgb(l1), k)
            break
    cinza = _CINZA_CEU.get(familia)
    if cinza:
        topo = _lerp_cor(topo, _rgb(cinza), 0.6)
        halo = _lerp_cor(halo, (0x8A, 0x96, 0xA8), 0.7)
    return {"topo": topo, "base": base, "halo": halo,
            "noite": hora < 5.5 or hora >= 19.5,
            "limpo": familia in ("sol", "sol_nuvem"),
            "acento": _lerp_cor(halo, (255, 255, 255), 0.5),
            "fraco": _lerp_cor(topo, (255, 255, 255), 0.55),
            "aro": _lerp_cor(topo, (255, 255, 255), 0.18)}


def _placa_ceu(w: int, h: int, col: int, ncol: int = 3, pal: dict | None = None
               ) -> Image.Image:
    """A fatia `col` do ceu, ja em SS, com canto arredondado e aro."""
    import numpy as np
    pal = pal or _paleta_ceu()
    W = ncol * w + (ncol - 1) * VAO_DESCANSO
    x0 = col * (w + VAO_DESCANSO)
    ys = np.linspace(0.0, 1.0, h)[:, None]
    xs = (np.arange(w)[None, :] + x0) / W
    topo, base, halo = (np.array(pal[k], dtype=float) for k in ("topo", "base", "halo"))
    k = (ys ** 0.85)[..., None]
    grad = np.broadcast_to(topo * (1 - k) + base * k, (h, w, 3)).copy()
    # o halo: uma fonte de luz fora da tela, no alto a direita da composicao
    dx = xs - 0.84
    dy = (ys + 0.28) * (h / W)
    dist = np.sqrt(dx * dx + dy * dy)
    inten = (np.clip(1 - dist / 0.78, 0, 1) ** 2 * 0.55)[..., None]
    grad = grad * (1 - inten) + halo * inten
    ceu = Image.fromarray(grad.clip(0, 255).astype("uint8"), "RGB")
    g = (w * SS, h * SS)
    ceu = ceu.resize(g, Image.BICUBIC)

    if pal["noite"] and pal["limpo"]:
        # estrelas: poucas, pequenas, so no ceu limpo. Semente por coluna para o
        # relogio nao trocar de estrelas a cada minuto.
        import random
        rnd = random.Random(7 + col)
        d = ImageDraw.Draw(ceu, "RGBA")
        for _ in range(N_ESTRELAS):
            x, y = rnd.random() * g[0], rnd.random() ** 1.4 * g[1] * 0.42
            r = rnd.choice((1, 1, 1.5, 1.5, 2.2)) * SS
            a = rnd.randint(70, 210)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(228, 234, 255, a))

    img = Image.new("RGB", g, _rgb(FUNDO))
    img.paste(ceu, (0, 0), _mascara(g, 22 * SS))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, g[0] - 1, g[1] - 1], radius=22 * SS,
                                          outline=pal["aro"], width=2 * SS)
    return img


def _caixa(d, texto, fonte):
    """(largura, altura, dx, dy) da caixa REAL do texto - a fonte Light tem
    respiro em cima que, num numero de 270 px, vira 60 px de ar."""
    x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=fonte)
    return x1 - x0, y1 - y0, x0, y0


def _texto_caixa(d, xy, texto, fonte, cor, centro_x=False):
    """Desenha com o canto superior da caixa real em `xy` (ou centrado em x)."""
    lw, lh, dx, dy = _caixa(d, texto, fonte)
    x, y = xy
    if centro_x:
        x = x - lw / 2
    d.text((x - dx, y - dy), texto, font=fonte, fill=cor)
    return lw, lh


def _quebra(d, texto, fonte, largura, max_linhas=2):
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = (atual + " " + palavra).strip()
        if d.textlength(teste, font=fonte) > largura and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = teste
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip(".,") + "..."
    return linhas


def _centrado(d, y, texto, fonte, cor, g):
    d.text((g[0] / 2, y), texto, font=fonte, fill=cor, anchor="mm")


def botao_relogio_grande(w: int, h: int, hora: str, dia_semana: str, data: str) -> Image.Image:
    """O relogio da tela de descanso: hora em cima, minuto embaixo, em Light.

    Empilhado porque e o que cabe grande: '23:40' numa linha de 410 px da um
    digito de 100 px; empilhado da 190. E o card que se le do sofa. E o unico
    que muda a cada minuto, entao e so gradiente e texto - fica em ~20 KB.
    """
    pal = _paleta_ceu()
    img = _placa_ceu(w, h, 0, pal=pal)
    g = img.size
    d = ImageDraw.Draw(img)
    hh, _, mm = hora.partition(":")

    f_n = _fonte(F_LIGHT, int(w * ESCALA_RELOGIO) * SS)
    lw, lh, _, _ = _caixa(d, "88", f_n)
    gap = 10 * SS
    y = int(g[1] * 0.085)
    _texto_caixa(d, (g[0] / 2, y), hh, f_n, (242, 245, 250), centro_x=True)
    y += lh + gap
    _texto_caixa(d, (g[0] / 2, y), mm or "", f_n, pal["acento"], centro_x=True)
    y += lh

    # um traco curto na cor do acento separa o numero da data
    d.rounded_rectangle([g[0] / 2 - 22 * SS, y + 30 * SS, g[0] / 2 + 22 * SS, y + 33 * SS],
                        radius=2 * SS, fill=pal["acento"])

    f_dia = _fonte(F_BOLD, 19 * SS)
    _texto_espacado(d, (g[0] / 2, y + 74 * SS), _ascii(dia_semana).upper(), f_dia,
                    pal["acento"], 4 * SS)
    f_data = _encaixa(d, data, F_SEMI, 34, g[0] - 40 * SS)
    _centrado(d, y + 108 * SS, data, f_data, (236, 240, 246), g)
    out = _fecha(img, w, h, 22)
    out.info["jpeg_subsampling"] = 2      # vai a cada minuto: croma nao importa aqui
    return out


# ----------------------------------------------------------- o tempo, desenhado

SOL_COR, LUA_COR = (0xF6, 0xC4, 0x53), (0xE6, 0xE9, 0xF4)
NUVEM_F, NUVEM_T = (0xE2, 0xE7, 0xEF), (0x94, 0xA0, 0xB4)
CHUVA_COR, RAIO_COR = (0x7F, 0xB0, 0xFF), (0xFF, 0xD5, 0x4A)
NEVE_COR, NEBLINA_COR = (0xF4, 0xF7, 0xFF), (0xB7, 0xC0, 0xCE)


def _brilho(img: Image.Image, cx: float, cy: float, r: float, cor: tuple, alfa: int) -> None:
    """Halo suave atras de um sol ou uma lua: e o que separa 'icone' de 'ilustracao'."""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor + (alfa,))
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.55))
    img.alpha_composite(glow)


def _cola(img: Image.Image, nome: str, lado: float, cx: float, cy: float, cor: tuple) -> None:
    gl = _ph(nome, int(lado), cor)
    if gl is not None:
        img.alpha_composite(gl, (int(cx - lado / 2), int(cy - lado / 2)))


def ilustra_tempo(lado: int, familia: str, dia: bool) -> Image.Image:
    """O tempo como ilustracao: glifos do Phosphor compostos em duas ou tres
    cores, com halo. Sol e nuvem juntos, nuvem na frente da lua, gotas azuis
    embaixo da nuvem - o que um glifo so, de uma cor so, nao consegue dizer.
    """
    L = lado
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    if familia == "sol":
        if dia:
            _brilho(img, L * 0.5, L * 0.5, L * 0.36, SOL_COR, 110)
            _cola(img, "sol", L * 0.70, L * 0.5, L * 0.5, SOL_COR)
        else:
            _brilho(img, L * 0.5, L * 0.5, L * 0.34, (0xA0, 0xB0, 0xFF), 70)
            _cola(img, "lua", L * 0.66, L * 0.5, L * 0.5, LUA_COR)
    elif familia == "sol_nuvem":
        if dia:
            _brilho(img, L * 0.34, L * 0.38, L * 0.26, SOL_COR, 100)
            _cola(img, "sol", L * 0.48, L * 0.34, L * 0.38, SOL_COR)
        else:
            _brilho(img, L * 0.34, L * 0.38, L * 0.22, (0xA0, 0xB0, 0xFF), 60)
            _cola(img, "lua_cheia", L * 0.40, L * 0.34, L * 0.38, LUA_COR)
        _cola(img, "nuvem", L * 0.64, L * 0.58, L * 0.62, NUVEM_F)
    elif familia == "nuvem":
        _cola(img, "nuvem", L * 0.50, L * 0.36, L * 0.44, NUVEM_T)
        _cola(img, "nuvem", L * 0.66, L * 0.58, L * 0.60, NUVEM_F)
    elif familia == "chuva":
        _cola(img, "nuvem", L * 0.66, L * 0.5, L * 0.42, NUVEM_F)
        for k, x in enumerate((0.34, 0.50, 0.66)):
            _cola(img, "gota", L * 0.15, L * x, L * (0.80 if k == 1 else 0.74), CHUVA_COR)
    elif familia == "neve":
        _cola(img, "nuvem", L * 0.66, L * 0.5, L * 0.42, NUVEM_F)
        for k, x in enumerate((0.34, 0.50, 0.66)):
            _cola(img, "floco", L * 0.13, L * x, L * (0.80 if k == 1 else 0.74), NEVE_COR)
    elif familia == "tempestade":
        _cola(img, "nuvem", L * 0.66, L * 0.5, L * 0.42, (0x8F, 0x9B, 0xAE))
        _cola(img, "raio", L * 0.32, L * 0.56, L * 0.76, RAIO_COR)
    else:
        _cola(img, "neblina", L * 0.68, L * 0.5, L * 0.52, NEBLINA_COR)
    return img


def glifo_tempo(lado: int, familia: str, dia: bool) -> Image.Image:
    """Nome antigo, desenho novo: o card pequeno de clima usa o mesmo tempo."""
    return ilustra_tempo(lado, familia, dia)


def _coluna_dado(d, img, cx, y, nome, valor, rotulo, pal, g):
    """Glifo em cima, numero no meio, rotulo embaixo: uma coluna de dado."""
    gl = _ph(nome, 28 * SS, pal["acento"])
    if gl is not None:
        img.alpha_composite(gl, (int(cx - 14 * SS), int(y)))
    d.text((cx, y + 52 * SS), valor, font=_fonte(F_SEMI, 26 * SS), fill=(240, 244, 250), anchor="mm")
    d.text((cx, y + 78 * SS), rotulo, font=_fonte(F_REG, 14 * SS), fill=pal["fraco"], anchor="mm")


def botao_clima_grande(w: int, h: int, d: dict) -> Image.Image:
    """O tempo na tela de descanso: ilustracao grande, temperatura em Light,
    tres colunas de dado embaixo. Registra o tempo para o ceu dos vizinhos."""
    if d:
        _tempo_visto.update({"familia": d.get("familia", "sol"), "dia": d.get("dia", True)})
    pal = _paleta_ceu()
    img = _placa_ceu(w, h, 1, pal=pal).convert("RGBA")
    g = img.size
    if not d:
        gl = _ph("nuvem", 120 * SS, pal["fraco"], 120)
        img.alpha_composite(gl, ((g[0] - gl.size[0]) // 2, int(g[1] * 0.30)))
        dr = ImageDraw.Draw(img)
        _centrado(dr, g[1] * 0.56, "sem clima", _fonte(F_SEMI, 32 * SS), (236, 240, 246), g)
        _centrado(dr, g[1] * 0.62, "esperando a rede", _fonte(F_REG, 17 * SS), pal["fraco"], g)
        return _fecha(img.convert("RGB"), w, h, 22)

    L = int(w * 0.54) * SS
    il = ilustra_tempo(L, d.get("familia", "nuvem"), d.get("dia", True))
    pos = ((g[0] - L) // 2, int(g[1] * 0.185) - L // 2)
    img = _sombra(img, il, pos, 0.45, 5 * SS, 10 * SS)
    img.alpha_composite(il, pos)
    dr = ImageDraw.Draw(img)

    temp = f"{d['temp']}°"
    f_t = _fonte(F_LIGHT, int(w * 0.36) * SS)
    lw, lh, _, _ = _caixa(dr, temp, f_t)
    _texto_caixa(dr, (g[0] / 2, int(g[1] * 0.395)), temp, f_t, (244, 246, 250), centro_x=True)

    texto = d.get("texto", "")
    _centrado(dr, int(g[1] * 0.60), texto, _encaixa(dr, texto, F_SEMI, 30, g[0] - 40 * SS),
              (236, 240, 246), g)
    _centrado(dr, int(g[1] * 0.665), f"máx {d['max']}°   ·   mín {d['min']}°",
              _fonte(F_REG, 21 * SS), pal["acento"], g)

    y = int(g[1] * 0.755)
    _coluna_dado(dr, img, g[0] * 0.22, y, "gota", f"{d.get('umidade', 0)}%", "umidade", pal, g)
    _coluna_dado(dr, img, g[0] * 0.50, y, "vento", f"{d.get('vento', 0)}", "km/h", pal, g)
    _coluna_dado(dr, img, g[0] * 0.78, y, "guarda_chuva", f"{d.get('chuva', 0)}%", "chuva", pal, g)

    if d.get("cidade"):
        f_c = _fonte(F_REG, 16 * SS)
        cid = d["cidade"]
        lw = dr.textlength(cid, font=f_c)
        x = (g[0] - lw - 20 * SS) / 2
        gl = _ph("pino", 16 * SS, pal["fraco"])
        if gl is not None:
            img.alpha_composite(gl, (int(x), int(g[1] * 0.945) - 8 * SS))
        dr.text((x + 20 * SS, int(g[1] * 0.945)), cid, font=f_c, fill=pal["fraco"], anchor="lm")
    return _fecha(img.convert("RGB"), w, h, 22)


def _quando(e: dict) -> str:
    """'14:00', 'amanhã 09:30', 'qui 14:00', 'hoje (dia inteiro)'."""
    ini = e["inicio"]
    hora = "" if e.get("dia_inteiro") else ini.strftime("%H:%M")
    if e.get("hoje"):
        return hora or "hoje, dia inteiro"
    if e.get("amanha"):
        return f"amanhã {hora}".strip()
    dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    return f"{dias[ini.weekday()]} {ini.day:02d}/{ini.month:02d} {hora}".strip()


def _quando_partes(e: dict) -> tuple:
    """('14:00', '') hoje; ('09:30', 'amanhã'); ('14:00', 'qui 25/09'); ('dia inteiro', 'amanhã')."""
    ini = e["inicio"]
    hora = "dia inteiro" if e.get("dia_inteiro") else ini.strftime("%H:%M")
    if e.get("hoje"):
        return hora, ""
    if e.get("amanha"):
        return hora, "amanhã"
    dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    return hora, f"{dias[ini.weekday()]} {ini.day:02d}/{ini.month:02d}"


def _falta(e: dict) -> tuple:
    """(texto, cor) do quanto falta - ou (None, None) se e longe."""
    if e.get("rolando"):
        return "agora", VERMELHO
    m = e.get("em_min", 999)
    if m <= 15:
        return f"em {m} min", LARANJA
    if m < 180:
        return (f"em {m // 60} h {m % 60:02d}" if m >= 60 else f"em {m} min"), VERDE
    return None, None


def _agenda_vazia(img, pal, g, nome, titulo, linhas, cor_glifo=None):
    gl = _ph(nome, 120 * SS, cor_glifo or pal["fraco"], 150)
    img.alpha_composite(gl, ((g[0] - gl.size[0]) // 2, int(g[1] * 0.30)))
    dr = ImageDraw.Draw(img)
    _centrado(dr, g[1] * 0.56, titulo, _fonte(F_SEMI, 32 * SS), (236, 240, 246), g)
    y = g[1] * 0.625
    for l in linhas:
        _centrado(dr, y, l, _fonte(F_REG, 17 * SS), pal["fraco"], g)
        y += 26 * SS


def botao_agenda(w: int, h: int, d: dict) -> Image.Image:
    """A agenda como linha do tempo: um trilho, um ponto por reuniao, a proxima
    grande e com o 'em 34 min' colorido, as duas seguintes menores."""
    pal = _paleta_ceu()
    img = _placa_ceu(w, h, 2, pal=pal).convert("RGBA")
    g = img.size
    dr = ImageDraw.Draw(img, "RGBA")

    x_cab, y_cab = 30 * SS, 30 * SS
    gl = _ph("calendario", 24 * SS, pal["acento"])
    if gl is not None:
        img.alpha_composite(gl, (x_cab, y_cab))
    f_cab = _fonte(F_BOLD, 16 * SS)
    xx = x_cab + 34 * SS
    for c in "AGENDA":
        dr.text((xx, y_cab + 12 * SS), c, font=f_cab, fill=pal["acento"], anchor="lm")
        xx += dr.textlength(c, font=f_cab) + 3 * SS

    if not d.get("configurado"):
        _agenda_vazia(img, pal, g, "calendario_x", "Sem agenda ligada",
                      ["Cole a URL .ics da sua agenda em", "config.json  ›  agenda  ›  ics_url"])
        return _fecha(img.convert("RGB"), w, h, 22)
    if d.get("erro") and not d.get("proximos"):
        _agenda_vazia(img, pal, g, "calendario_x", "Agenda fora do ar", [_ascii(d["erro"])[:40]])
        return _fecha(img.convert("RGB"), w, h, 22)
    if not d.get("lido"):
        _agenda_vazia(img, pal, g, "calendario", "Lendo a agenda...", [])
        return _fecha(img.convert("RGB"), w, h, 22)
    ps = d.get("proximos") or []
    if not ps:
        _agenda_vazia(img, pal, g, "calendario_ok", "Nada agendado",
                      [f"nos próximos dias"], cor_glifo=_mistura(VERDE, 0xFFFFFF, 60))
        return _fecha(img.convert("RGB"), w, h, 22)

    trilho_x = 46 * SS
    x_txt = 78 * SS
    larg = g[0] - x_txt - 26 * SS
    y = int(g[1] * 0.175)
    pontos = []
    for i, e in enumerate(ps[:3]):
        primeiro = i == 0
        hora_txt, dia_txt = _quando_partes(e)
        f_q = _fonte(F_BOLD, (38 if primeiro else 24) * SS)
        cor_q = (244, 246, 250) if primeiro else _lerp_cor((244, 246, 250), pal["base"], 0.25)
        dr.text((x_txt, y), hora_txt, font=f_q, fill=cor_q, anchor="la")
        lq = dr.textlength(hora_txt, font=f_q)
        if dia_txt:
            f_d = _fonte(F_REG, (20 if primeiro else 16) * SS)
            dr.text((x_txt + lq + 12 * SS, y + f_q.size * 0.78), dia_txt, font=f_d,
                    fill=pal["acento"], anchor="ls")
        pontos.append((y + f_q.size * 0.52, primeiro, e))
        y += int(f_q.size * 1.22)

        f_t = _fonte(F_SEMI, (27 if primeiro else 21) * SS)
        cor_t = (236, 240, 246) if primeiro else pal["fraco"]
        for l in _quebra(dr, e["titulo"], f_t, larg, 2 if primeiro else 1):
            dr.text((x_txt, y), l, font=f_t, fill=cor_t, anchor="la")
            y += int(f_t.size * 1.22)

        if primeiro:
            txt, cor = _falta(e)
            if txt:
                f_c = _fonte(F_BOLD, 17 * SS)
                _, alt = _chip(dr, (x_txt, y + 8 * SS), txt, f_c, _mistura(cor, FUNDO, 55),
                               _mistura(cor, 0xFFFFFF, 85), pad=(14 * SS, 6 * SS))
                y += alt + 8 * SS
            y += 30 * SS
        else:
            y += 22 * SS
        if y > g[1] * 0.92:
            break

    # o trilho: uma linha fina ligando os pontos, pontos por cima
    if len(pontos) > 1:
        dr.line([(trilho_x, pontos[0][0]), (trilho_x, pontos[-1][0])],
                fill=pal["aro"], width=2 * SS)
    for py, primeiro, e in pontos:
        if primeiro:
            _, cor = _falta(e)
            c = _rgb(cor) if cor else pal["acento"]
            r = 9 * SS
            dr.ellipse([trilho_x - r - 4 * SS, py - r - 4 * SS, trilho_x + r + 4 * SS, py + r + 4 * SS],
                       fill=c + (70,))
            dr.ellipse([trilho_x - r, py - r, trilho_x + r, py + r], fill=c + (255,))
        else:
            r = 6 * SS
            dr.ellipse([trilho_x - r, py - r, trilho_x + r, py + r], fill=pal["base"] + (255,),
                       outline=pal["fraco"] + (255,), width=2 * SS)
    return _fecha(img.convert("RGB"), w, h, 22)


# ---------------------------------------------------------------- player

def _mmss(seg: float) -> str:
    seg = max(0, int(seg))
    return f"{seg // 60}:{seg % 60:02d}"


def _nome_app(app: str) -> str:
    a = (app or "").lower()
    if "spotify" in a:
        return "Spotify"
    if "chrome" in a:
        return "Chrome"
    if "msedge" in a or "edge" in a:
        return "Edge"
    if "firefox" in a:
        return "Firefox"
    return ""



_EXT_MIDIA = re.compile(r"\.(mp4|mkv|mp3|m4a|webm|wav|flac|mov|avi|ogg|aac)$", re.I)


def _titulo_limpo(t: str) -> str:
    """Nome de arquivo vira titulo: 'NANO_AA_TEASER.mp4' -> 'Nano AA Teaser'.

    So mexe na caixa quando o texto e TODO em caixa alta (nao inventa nada), e
    sigla curta (AA, DJ, EP) fica como esta. Um titulo ja bem escrito passa
    intacto.
    """
    s = _EXT_MIDIA.sub("", str(t or "").strip())
    s = re.sub(r"_+", " ", s)
    s = re.sub(r"(?<=\w)-(?=\w)", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    letras = [c for c in s if c.isalpha()]
    if letras and all(c.isupper() for c in letras):
        s = " ".join(p if len(p) <= 2 else p.capitalize() for p in s.split(" "))
    return s


def _tela(s: str) -> str:
    """Texto que vai para o JPEG: Segoe UI tem acento; o que ela nao tem cai."""
    return (str(s or "").replace("\u00ba", "o").replace("\u00aa", "a")
            .encode("latin-1", "ignore").decode("latin-1"))


def _fundo_midia(g: tuple, capa: Image.Image | None, raio: int) -> tuple:
    """Fundo full-bleed do card de midia: a arte borrada ate virar textura de
    cor, escurecida, com scrim mais pesado embaixo. Uma miniatura de 150 px
    vira luz, nao pixel. Sem arte: grafite com um glifo de musica esmaecido.

    Devolve (imagem RGBA ja no tamanho g, cor de acento tirada da arte).
    """
    if capa is not None:
        peq = _cobre(capa, (max(8, g[0] // 8), max(8, g[1] // 8)), 0.5)
        peq = peq.filter(ImageFilter.GaussianBlur(7))
        fundo = peq.resize(g, Image.BICUBIC)
        fundo = ImageEnhance.Color(fundo).enhance(1.35)
        fundo = ImageEnhance.Brightness(fundo).enhance(0.58)
        media = capa.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        # o acento vem da capa, mas puxado para claro: le sobre o proprio fundo
        acento = _lerp_cor(media, (255, 255, 255), 0.45)
    else:
        fundo = _placa_grad(g[0] // SS, g[1] // SS, _rgb(GRAFITE_A), _rgb(GRAFITE_B),
                            _rgb(ARO), raio).resize(g, Image.LANCZOS)
        acento = _rgb(FRACO)
    fundo = fundo.convert("RGBA")
    if capa is None:
        L = int(g[1] * 0.95)
        gl = _ph("musica", L, (255, 255, 255), 22)
        if gl is not None:
            fundo.alpha_composite(gl, (g[0] - int(L * 0.78), int(g[1] * 0.28)))
    # scrim: quase nada no topo, pesado na base, onde moram a barra e o texto
    scrim = Image.new("L", (1, g[1]))
    sp = scrim.load()
    for y in range(g[1]):
        k = y / max(1, g[1] - 1)
        sp[0, y] = int(28 + 140 * (k ** 1.6))
    veu = Image.new("RGBA", g, (4, 6, 10, 255))
    veu.putalpha(scrim.resize(g))
    fundo.alpha_composite(veu)
    # a placa: canto arredondado e aro fino na cor do acento
    img = Image.new("RGBA", g, _rgb(FUNDO) + (255,))
    img.paste(fundo, (0, 0), _mascara(g, raio * SS))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, g[0] - 1, g[1] - 1], radius=raio * SS,
                                          outline=acento + (110,), width=2 * SS)
    return img, acento


def _miniatura(capa: Image.Image, max_w: int, max_h: int, raio: int) -> Image.Image:
    """A arte no aspecto ORIGINAL (16:9 fica 16:9), no maximo ~2x do tamanho
    real na tela, canto arredondado, aro claro. Ampliar 4x um frame de 150 px e
    o que deixava o card borrado."""
    teto = 2.0 * SS                     # 2x na tela = 2*SS no espaco de desenho
    esc = min(max_w / capa.width, max_h / capa.height, teto)
    tw, th = max(1, int(capa.width * esc)), max(1, int(capa.height * esc))
    mini = capa.resize((tw, th), Image.LANCZOS).convert("RGBA")
    mini.putalpha(_mascara((tw, th), raio))
    ImageDraw.Draw(mini).rounded_rectangle([0, 0, tw - 1, th - 1], radius=raio,
                                           outline=(255, 255, 255, 70), width=SS)
    return mini


def _cola_miniatura(img: Image.Image, mini: Image.Image, pos: tuple) -> Image.Image:
    img = _sombra(img, mini, pos, 0.65, 8 * SS, 14 * SS)
    img.alpha_composite(mini, pos)
    return img


def _titulo_que_cabe(d, texto, largura, tams, linhas=2):
    """Maior fonte da lista em que o titulo cabe em `linhas` sem cortar."""
    for t in tams:
        f = _fonte(F_BOLD, t * SS)
        ls = _quebra(d, texto, f, largura, linhas)
        if not ls[-1].endswith("...") and len(ls) <= linhas:
            return f, ls
    f = _fonte(F_BOLD, tams[-1] * SS)
    return f, _quebra(d, texto, f, largura, linhas)


def _barra_progresso(d, x0, x1, cy, frac, cor, grosso):
    """Trilho claro translucido, preenchimento na cor do estado, ponto na
    posicao. Ponta redonda dos dois lados: forma, nao formulario."""
    r = grosso / 2
    d.rounded_rectangle([x0, cy - r, x1, cy + r], radius=r, fill=(255, 255, 255, 55))
    xp = x0 + (x1 - x0) * frac
    if frac > 0:
        d.rounded_rectangle([x0, cy - r, max(x0 + grosso, xp), cy + r], radius=r, fill=cor + (255,))
    rp = grosso * 0.95
    d.ellipse([xp - rp - 2 * SS, cy - rp - 2 * SS, xp + rp + 2 * SS, cy + rp + 2 * SS],
              fill=(8, 10, 14, 200))
    d.ellipse([xp - rp, cy - rp, xp + rp, cy + rp], fill=cor + (255,))


def _chip_escuro(d, xy, texto, tam, tinta=(236, 240, 246)):
    f = _fonte(F_BOLD, tam * SS)
    return _chip(d, xy, texto, f, (6, 8, 12, 150), tinta, pad=(10 * SS, 4 * SS))



def botao_player(w: int, h: int, capa: bytes | None, titulo: str, artista: str,
                 tocando: bool, pos: float | None, dur: float | None,
                 app: str = "") -> Image.Image:
    """Tocando agora: a arte manda no card - borrada como fundo, nitida e no
    aspecto certo como miniatura - e o texto le a um metro.

    Largo (624x308): miniatura a esquerda, texto a direita, barra atravessando
    a base. Estreito (410 ou 304): miniatura em cima, texto embaixo. Sem
    duracao (player que nao informa), a barra some e o estado vira chip.
    """
    g = (w * SS, h * SS)
    raio = 22
    pad = 22 * SS
    img_capa = None
    if capa:
        try:
            img_capa = Image.open(_io.BytesIO(capa)).convert("RGB")
        except Exception:
            img_capa = None
    img, acento = _fundo_midia(g, img_capa, raio)
    d = ImageDraw.Draw(img, "RGBA")

    tem_barra = pos is not None and bool(dur)
    cor_estado = _rgb(VERDE_AR) if tocando else _rgb(MORTO)
    alt_rodape = 34 * SS if tem_barra else 0
    largo = w >= 1.5 * h
    topo, base = pad, g[1] - pad - alt_rodape - (10 * SS if tem_barra else 0)

    # miniatura
    mini, mpos = None, None
    if img_capa is not None:
        if largo:
            mini = _miniatura(img_capa, int(g[0] * 0.46), base - topo, 14 * SS)
            mpos = (pad, topo + (base - topo - mini.height) // 2)
        else:
            mini = _miniatura(img_capa, g[0] - 2 * pad, int(g[1] * 0.40), 14 * SS)
            mpos = (pad, topo)
        img = _cola_miniatura(img, mini, mpos)
        d = ImageDraw.Draw(img, "RGBA")

    # coluna de texto
    if largo and mini is not None:
        x0 = mpos[0] + mini.width + 24 * SS
        y_ini, y_fim = topo, base
    elif mini is not None:
        x0 = pad
        y_ini, y_fim = mpos[1] + mini.height + 16 * SS, base
    else:
        x0 = pad
        y_ini, y_fim = topo, base
    larg = g[0] - x0 - pad

    chips = []
    nome_app = _nome_app(app)
    if nome_app:
        chips.append((nome_app.upper(), (236, 240, 246)))
    if titulo and (not tem_barra or not tocando):
        chips.append(("TOCANDO" if tocando else "PAUSADO",
                      _lerp_cor(cor_estado, (255, 255, 255), 0.45)))

    tit = _tela(_titulo_limpo(titulo)) or "Nada tocando"
    cor_tit = (248, 250, 253, 255) if titulo else (160, 170, 184, 255)
    tams = [34, 31, 28] if largo else ([30, 27, 24] if w >= 380 else [26, 24, 22])
    f_t, linhas = _titulo_que_cabe(d, tit, larg, tams)
    art = _tela(artista).strip()
    f_a = _fonte(F_REG, 20 * SS if w >= 380 else 18 * SS)
    alt_chip = 13 * SS + 8 * SS
    bloco = (alt_chip + 12 * SS if chips else 0) + len(linhas) * int(f_t.size * 1.12) \
        + (int(f_a.size * 1.5) if art else 0)
    y = y_ini + max(0, (y_fim - y_ini - bloco) // 2) if largo else y_ini
    if chips:
        x = x0
        for texto, tinta in chips:
            cw, _ = _chip_escuro(d, (x, y), texto, 13, tinta)
            x += cw + 8 * SS
        y += alt_chip + 12 * SS
    for l in linhas:
        d.text((x0, y), l, font=f_t, fill=cor_tit)
        y += int(f_t.size * 1.12)
    if art:
        y += 4 * SS
        for l in _quebra(d, art, f_a, larg, 1):
            d.text((x0, y), l, font=f_a, fill=(200, 210, 222, 255))

    # rodape: tempo tocado, barra, tempo que falta - numa linha so
    if tem_barra:
        frac = max(0.0, min(1.0, pos / dur))
        cy = g[1] - pad - 8 * SS
        f_h = _fonte(F_REG, 17 * SS)
        t_esq, t_dir = _mmss(pos), "-" + _mmss(dur - pos)
        l_esq = d.textlength(t_esq, font=f_h)
        l_dir = d.textlength("-" + _mmss(dur), font=f_h)      # largura fixa: a barra nao pula
        d.text((pad, cy), t_esq, font=f_h, fill=(214, 222, 232, 255), anchor="lm")
        d.text((g[0] - pad, cy), t_dir, font=f_h, fill=(214, 222, 232, 255), anchor="rm")
        _barra_progresso(d, pad + l_esq + 16 * SS, g[0] - pad - l_dir - 16 * SS, cy,
                         frac, cor_estado, 11 * SS)

    out = _fecha(img.convert("RGB"), w, h, raio)
    out.info["jpeg_subsampling"] = 2      # vai a cada 10 s: fundo borrado nao tem croma fino
    return out



def botao_musica(w: int, h: int, capa: bytes | None, titulo: str, artista: str,
                 tocando: bool = True, app: str = "") -> Image.Image:
    """O card da home quando toca algo: mesma lingua do player, em pe. Fundo
    borrado da arte, miniatura no aspecto certo, titulo em duas linhas, e no
    rodape o chip do app de origem e o ponto verde (tocando) ou cinza (pausado).
    Diz de onde vem a musica em vez de fingir que e sempre Spotify.
    """
    g = (w * SS, h * SS)
    raio = 22
    pad = 16 * SS
    img_capa = None
    if capa:
        try:
            img_capa = Image.open(_io.BytesIO(capa)).convert("RGB")
        except Exception:
            img_capa = None
    img, acento = _fundo_midia(g, img_capa, raio)
    d = ImageDraw.Draw(img, "RGBA")

    # Deitado (304x200 na home 4x3): miniatura a esquerda, texto a direita.
    # Em pe (240x308): miniatura em cima, texto embaixo.
    deitado = w >= h * 1.25
    x0 = pad
    y = pad
    if img_capa is not None:
        if deitado:
            mini = _miniatura(img_capa, int(g[0] * 0.44), g[1] - 2 * pad, 10 * SS)
            mpos = (pad, (g[1] - mini.height) // 2)
            x0 = pad + mini.width + 14 * SS
            y = pad + 2 * SS
        else:
            mini = _miniatura(img_capa, g[0] - 2 * pad, int(g[1] * 0.46), 12 * SS)
            mpos = ((g[0] - mini.width) // 2, pad)
            y = pad + mini.height + 14 * SS
        img = _cola_miniatura(img, mini, mpos)
        d = ImageDraw.Draw(img, "RGBA")
    else:
        y = int(g[1] * 0.40) if not deitado else pad + 8 * SS

    larg = g[0] - x0 - pad
    pad_x = x0
    tit = _tela(_titulo_limpo(titulo)) or "Nada tocando"
    f_t, linhas = _titulo_que_cabe(d, tit, larg, [20, 18, 16] if deitado else [22, 20, 18])
    for l in linhas:
        d.text((pad_x, y), l, font=f_t, fill=(248, 250, 253, 255))
        y += int(f_t.size * 1.15)
    art = _tela(artista).strip()
    if art:
        f_a = _fonte(F_REG, (14 if deitado else 15) * SS)
        d.text((pad_x, y + 2 * SS), _quebra(d, art, f_a, larg, 1)[0], font=f_a,
               fill=(200, 210, 222, 255))

    # rodape: chip do app a esquerda, ponto de estado a direita
    cor = _rgb(VERDE_AR) if tocando else _rgb(MORTO)
    yb = g[1] - pad - 11 * SS
    nome_app = _nome_app(app)
    if nome_app:
        _chip_escuro(d, (pad_x, yb - 11 * SS), nome_app.upper(), 12)
    r = 7 * SS
    cx = g[0] - pad - r
    if tocando:
        d.ellipse([cx - r * 2, yb - r * 2, cx + r * 2, yb + r * 2], fill=cor + (60,))
    d.ellipse([cx - r, yb - r, cx + r, yb + r], fill=cor + (255,))
    out = _fecha(img.convert("RGB"), w, h, raio)
    out.info["jpeg_subsampling"] = 2
    return out



CLAUDE_LARANJA = 0xD97757


def simbolo_claude(lado: int, cor: tuple, raios: int = 11) -> Image.Image:
    """O asterisco do Claude Code, desenhado - nao ha fonte que o tenha.

    Onze petalas finas que afinam da ponta ate o centro. Desenhado em 4x e
    reduzido, porque poligono fino sem supersampling vira serrilha pura.
    """
    import math
    mag = 4
    L = lado * mag
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


def clawd(lado: int, cor: int = CLAUDE_LARANJA) -> Image.Image:
    """O bichinho do Claude, em pixel art. Grid de 18x14 blocos.

    Desenhado bloco a bloco de proposito: escalar um PNG de pixel art borra as
    bordas, e a graca dele e justamente a borda dura.
    """
    G, H = 18, 14
    px = max(1, lado // G)
    img = Image.new("RGBA", (px * G, px * H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = _rgb(cor) + (255,)
    preto = (0, 0, 0, 255)

    def b(x0, y0, x1, y1, cor_bloco=c):
        d.rectangle([x0 * px, y0 * px, (x1 + 1) * px - 1, (y1 + 1) * px - 1],
                    fill=cor_bloco)

    b(3, 0, 14, 9)                      # corpo
    b(0, 3, 17, 6)                      # bracos
    b(5, 2, 6, 3, preto)                # olhos
    b(11, 2, 12, 3, preto)
    for x in (3, 6, 9, 12):             # quatro pernas
        b(x, 10, x + 1, 13)
    return img


# Doze cores que aguentam fundo escuro e se distinguem entre si a um metro.
CORES_PROJETO = [0x5865F2, 0xF5A524, 0x30A46C, 0xE5484D, 0x8E4EC6, 0x3E63DD,
                 0xE93D82, 0x12A594, 0xF76B15, 0x6E56CF, 0x0091FF, 0xBDEE63]


def cor_projeto(nome: str) -> int:
    """Cor pelo hash do nome, nao pela posicao na lista: reordenar ou apagar um
    projeto nao troca a cor dos outros, e o olho aprende 'TELINHA e azul'."""
    import hashlib
    h = int(hashlib.sha1(_ascii(nome).lower().encode()).hexdigest(), 16)
    return CORES_PROJETO[h % len(CORES_PROJETO)]


def monograma(nome: str) -> str:
    """Duas letras que representam o nome: iniciais se tem duas palavras
    ('Norfolk AI' -> NA), senao as duas primeiras ('TELINHA' -> TE)."""
    partes = [p for p in re.split(r"[\s_\-\.]+", _ascii(nome)) if p]
    if len(partes) >= 2:
        return (partes[0][0] + partes[1][0]).upper()
    s = partes[0] if partes else "?"
    return s[:2].upper()


def _luminancia(cor: int) -> float:
    r, g, b = _rgb(cor)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def botao_projeto(w: int, h: int, nome: str, cor: int, sub: str = "",
                  branch: str = "", idade: str = "") -> Image.Image:
    """Card de projeto: pastilha colorida com o monograma, nome grande, branch e
    ha quanto tempo foi mexido. O Clawd fica pequeno no canto: e a marca de
    'abre com o Claude', igual em todos, e por isso nao pode ser a identidade.

    A identidade e a cor + duas letras. Cinco cards com o mesmo bicho laranja
    eram cinco cards iguais; cinco pastilhas de cor diferente com NA, JO, RE,
    GP, AR se distinguem de canto de olho antes de ler o nome.
    """
    img = _placa_grad(w, h, _rgb(GRAFITE_A), _rgb(GRAFITE_B),
                      _mistura(cor, 0xFFFFFF, 30), 22)
    img = img.resize((w * SS, h * SS), Image.LANCZOS)
    g = img.size
    d = ImageDraw.Draw(img, "RGBA")
    pad = 24 * SS

    # pastilha do monograma: grande, centrada na altura
    lado = int(g[1] * 0.56)
    x0, y0 = pad + 2 * SS, (g[1] - lado) // 2
    d.rounded_rectangle([x0, y0, x0 + lado, y0 + lado], radius=int(lado * 0.20),
                        fill=_mistura(cor, FUNDO, 88))
    d.rounded_rectangle([x0, y0, x0 + lado, y0 + lado], radius=int(lado * 0.20),
                        outline=_mistura(cor, 0xFFFFFF, 40), width=2 * SS)
    tinta_mono = (18, 21, 27) if _luminancia(cor) > 0.6 else (255, 255, 255)
    f_mono = _fonte(F_BOLD, int(lado * 0.50))
    _texto_espacado(d, (x0 + lado / 2, y0 + lado * 0.5 + f_mono.size * 0.36),
                    monograma(nome), f_mono, tinta_mono, 2 * SS)

    # coluna da direita: nome / branch / idade, centrada na altura
    xn = x0 + lado + 22 * SS
    larg_txt = g[0] - xn - pad
    f_nome = _fonte(F_BOLD, int(30 * SS))
    txt = _ascii(nome)
    while d.textlength(txt, font=f_nome) > larg_txt and f_nome.size > 20 * SS:
        f_nome = _fonte(F_BOLD, f_nome.size - 2)
    while d.textlength(txt, font=f_nome) > larg_txt and len(txt) > 4:
        txt = txt[:-1]
    if txt != _ascii(nome):
        txt = txt.rstrip() + "..."
    f_br = _fonte(F_BOLD, int(15 * SS))
    f_sub = _fonte(F_REG, int(17 * SS))
    br = _ascii(branch) if branch else "sem git"
    while d.textlength(br, font=f_br) > larg_txt - 24 * SS and len(br) > 4:
        br = br[:-1]
    rod = _ascii(idade or sub)

    alt_nome = int(f_nome.size * 1.15)
    alt_chip = f_br.size + 10 * SS
    alt_rod = int(f_sub.size * 1.3) if rod else 0
    bloco = alt_nome + 12 * SS + alt_chip + (14 * SS + alt_rod if rod else 0)
    y = (g[1] - bloco) // 2
    d.text((xn, y), txt, font=f_nome, fill=_rgb(TEXTO))
    y += alt_nome + 12 * SS
    # branch numa pilula: le como forma. "sem git" e informacao tambem.
    if branch:
        fundo_chip, tinta_chip = (0x2C, 0x35, 0x42, 255), _mistura(cor, 0xFFFFFF, 68) + (255,)
    else:
        fundo_chip, tinta_chip = (0x1C, 0x22, 0x2B, 255), _rgb(FRACO) + (255,)
    _chip(d, (xn, y), br, f_br, fundo_chip, tinta_chip, pad=(12 * SS, 5 * SS))
    y += alt_chip + 14 * SS
    if rod:
        d.text((xn, y), rod, font=f_sub, fill=_rgb(FRACO))

    # o Clawd pequeno no canto: a marca de "abre com o Claude", igual em todos
    sim = clawd(34 * SS)
    img.paste(sim, (g[0] - 18 * SS - sim.size[0], 18 * SS), sim)

    # _fecha ja reduz de SS para 1x; reduzir antes dava canto de 38 px
    # serrilhado contra os 11 px lisos do resto da tela.
    return _fecha(img, w, h, 22)
