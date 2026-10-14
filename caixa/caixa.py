"""Caixa + suporte de monitor para a Waveshare ESP32-P4-WIFI6-Touch-LCD-5.

Medidas tiradas do STEP oficial (ESP32-P4-WIFI6-Touch-LCD-5_3d-20260812.stp,
github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-5/hardware/mechanical).

Sistema de coordenadas = o do STEP:
  x = lado curto (70,70 do vidro), +x = borda dos botões, -x = borda do header 40p
  y = lado longo (126,90),        -y = borda das USB-C, +y = borda do cartão SD
  z = espessura, frente do vidro em z=+3,0, traseira para -z

Uso:  python caixa.py            -> gera os STL em ./stl
      python caixa.py --checar placa.stp   -> também confere interferências
"""
import math, sys, pathlib
import cadquery as cq

AQUI = pathlib.Path(__file__).parent
OUT = AQUI / "stl"

# ---------------------------------------------------------------- placa (STEP)
VIDRO_X, VIDRO_Y = 70.70, 126.90
VIDRO_FRENTE, VIDRO_TRAS = 3.00, -2.30
FUNDO_COMPONENTES = -9.80            # header 40 pinos, o mais fundo
FUROS = [(sx * 28.50, y) for sx in (1, -1) for y in (-58.65, 53.35)]
ESPACADOR_FUNDO = -8.60              # face de baixo dos espaçadores M2,5
USB_X = (-8.97, 8.97)                # 8.97 = USB TO UART, -8.97 = USB OTG
BOTOES_Y = {"RST": 10.86, "BOOT": 22.55, "PWR": 34.24}   # haste lateral em +x
BOTAO_Z = -5.5
SD_X, SD_Z = 15.57, -5.85            # cartão entra pela borda +y

# ---------------------------------------------------------------- caixa
FOLGA = 0.35                         # vidro <-> parede
PAREDE = 2.4
PISO_INTERNO = -10.6                 # 0,8 mm abaixo do header
COSTAS = -16.0                       # face externa de trás (5,4 mm de fundo p/ o trilho)
RAIO_EXT = 4.0

CAV_X = VIDRO_X + 2 * FOLGA
CAV_Y = VIDRO_Y + 2 * FOLGA
EXT_X = CAV_X + 2 * PAREDE
EXT_Y = CAV_Y + 2 * PAREDE

# rabo-de-andorinha fêmea na traseira (dois canais, um perto de cada borda longa,
# assim tanto faz qual borda fica para cima)
CANAL_X = 16.0
CANAL_BOCA, CANAL_FUNDO, CANAL_PROF = 12.0, 16.0, 3.5
CANAL_Y0, CANAL_Y1 = -EXT_Y / 2 - 1, 25.0      # aberto no lado das USB, batente em y=25
FOLGA_TRILHO = 0.2

# parafuso M2,5 x 6: cabeça entra no rebaixo até z=-11, ponta para em z=-5
REBAIXO_Z = -11.0


def caixa():
    corpo = (cq.Workplane("XY").workplane(offset=COSTAS)
             .rect(EXT_X, EXT_Y).extrude(VIDRO_FRENTE - COSTAS)
             .edges("|Z").fillet(RAIO_EXT)
             .faces(">Z").edges().chamfer(0.6))
    cav = (cq.Workplane("XY").workplane(offset=PISO_INTERNO)
           .rect(CAV_X, CAV_Y).extrude(VIDRO_FRENTE - PISO_INTERNO + 1)
           .edges("|Z").fillet(2.5))
    corpo = corpo.cut(cav)

    # torres dos parafusos, do piso até encostar nos espaçadores
    for x, y in FUROS:
        torre = (cq.Workplane("XY").workplane(offset=PISO_INTERNO - 0.5)
                 .center(x, y).circle(3.6).extrude(ESPACADOR_FUNDO - PISO_INTERNO + 0.5))
        corpo = corpo.union(torre)
    for x, y in FUROS:
        furo = cq.Workplane("XY").workplane(offset=COSTAS - 1).center(x, y).circle(1.4).extrude(20)
        rebaixo = (cq.Workplane("XY").workplane(offset=COSTAS - 1).center(x, y)
                   .circle(2.7).extrude(REBAIXO_Z - COSTAS + 1))
        corpo = corpo.cut(furo).cut(rebaixo)

    # USB-C (lado -y): 13 x 7,2 para caber plugue com capa grossa
    for x in USB_X:
        janela = (cq.Workplane("XZ").workplane(offset=EXT_Y / 2 - 3)   # XZ olha para -y
                  .center(x, -5.9).rect(13.0, 7.2).extrude(6)
                  .edges("|Y").fillet(2.5))
        corpo = corpo.cut(janela)

    # cartão SD (lado +y)
    sd = (cq.Workplane("XZ").workplane(offset=-(EXT_Y / 2 + 1))
          .center(SD_X, SD_Z).rect(13.0, 3.4).extrude(PAREDE + 2)
          .edges("|Y").fillet(1.2))
    corpo = corpo.cut(sd)

    # furinhos dos botões (lado +x), para clipe/palito
    for nome, y in BOTOES_Y.items():
        f = (cq.Workplane("YZ").workplane(offset=CAV_X / 2 - 1)
             .center(y, BOTAO_Z).circle(1.2).extrude(PAREDE + 2))
        corpo = corpo.cut(f)
        txt = (cq.Workplane("YZ").workplane(offset=EXT_X / 2 - 0.4)
               .center(y, BOTAO_Z - 4.2)
               .text(nome, 2.6, 1.0, combine=False, halign="center", valign="center"))
        corpo = corpo.cut(txt)

    # ventilação no meio das costas, em cima do módulo ESP32-P4
    for i in range(-6, 7):
        v = (cq.Workplane("XY").workplane(offset=COSTAS - 1)
             .center(0, i * 5.0).slot2D(10.0, 2.0, angle=0).extrude(PISO_INTERNO - COSTAS + 2))
        corpo = corpo.cut(v)

    # canais rabo-de-andorinha
    for cx in (CANAL_X, -CANAL_X):
        perfil = (cq.Workplane("XZ").workplane(offset=-CANAL_Y1)   # XZ: extrude vai para -y
                  .polyline([(cx - CANAL_BOCA / 2, COSTAS - 0.01),
                             (cx + CANAL_BOCA / 2, COSTAS - 0.01),
                             (cx + CANAL_FUNDO / 2, COSTAS + CANAL_PROF),
                             (cx - CANAL_FUNDO / 2, COSTAS + CANAL_PROF)]).close()
                  .extrude(CANAL_Y1 - CANAL_Y0))
        corpo = corpo.cut(perfil)
    return corpo


# ---------------------------------------------------------------- suporte
LARG_SUPORTE = 50.0
ESP_PLACA = 4.0            # placa que cola no monitor
ALT_COLA = 45.0            # altura da área de cola acima da borda do monitor
FOLGA_MONITOR = 4.0        # vão entre o topo da caixa e a borda de baixo do monitor
ESP_BLOCO = 5.0            # bloco atrás da caixa que segura o trilho


def suporte(theta_graus):
    """Perfil 2D no plano (u=para a frente, v=para cima) extrudado na largura.

    A caixa fica com a tela inclinada theta para cima. Coordenadas locais da caixa
    (xc, zc) viram mundo por P = xc*(-sin, cos) + zc*(cos, sin).
    """
    t = math.radians(theta_graus)
    s, c = math.sin(t), math.cos(t)
    W = lambda xc, zc: (zc * c - xc * s, xc * c + zc * s)

    topo = EXT_X / 2
    # plano da traseira do monitor: logo atrás do canto traseiro-superior da caixa
    u_p = min(W(topo, COSTAS)[0], W(-topo, COSTAS)[0]) - 0.6
    # borda de baixo do monitor: acima do ponto mais alto da caixa
    v_m = max(W(topo, VIDRO_FRENTE)[1], W(topo, COSTAS)[1]) + FOLGA_MONITOR

    # bloco atrás da caixa, centrado no canal de cima
    x0, x1 = CANAL_X - 13, topo - 1.0
    z0, z1 = COSTAS - ESP_BLOCO, COSTAS - 0.1
    bloco = [W(x0, z0), W(x1, z0), W(x1, z1), W(x0, z1)]

    # trilho macho: pescoço reto dentro do bloco, depois acompanha o canal com folga
    b = CANAL_BOCA - 2 * FOLGA_TRILHO
    h = CANAL_PROF - FOLGA_TRILHO
    f = b + h * (CANAL_FUNDO - CANAL_BOCA) / CANAL_PROF
    trilho = [W(CANAL_X - b / 2, z1 - 1.0), W(CANAL_X + b / 2, z1 - 1.0),
              W(CANAL_X + b / 2, COSTAS), W(CANAL_X + f / 2, COSTAS + h),
              W(CANAL_X - f / 2, COSTAS + h), W(CANAL_X - b / 2, COSTAS)]

    # placa vertical de cola + braço até o bloco
    placa = [(u_p - ESP_PLACA, W(x0, z0)[1]), (u_p, W(x0, z0)[1] + 0),
             (u_p, v_m + ALT_COLA), (u_p - ESP_PLACA, v_m + ALT_COLA)]
    # a placa da frente (u_p) desce só até o bloco; atrás dela, mão-francesa até o bloco
    braco = [W(x0, z0), W(x1, z0), (u_p - ESP_PLACA, v_m + 12), (u_p - ESP_PLACA, W(x0, z0)[1])]

    # junta os pedaços no 2D: cantos de dentro ganham raio de 2 (reforço),
    # cantos de fora raio de 0,5 (o trilho entra mais fácil)
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    perfil = unary_union([Polygon(p) for p in (bloco, placa, braco)])
    perfil = perfil.buffer(2.0, join_style=1).buffer(-2.0, join_style=1)
    # o trilho entra depois do raio interno, senão o raio enche o pescoço do rabo-de-andorinha
    perfil = unary_union([perfil, Polygon(trilho)])
    perfil = perfil.buffer(-0.4, join_style=1).buffer(0.4, join_style=1)
    pts = list(perfil.exterior.coords)[:-1]
    peca = cq.Workplane("XY").polyline(pts).close().extrude(LARG_SUPORTE)
    info = dict(u_p=u_p, v_m=v_m)
    return peca, info


def _exportar(wp, nome):
    OUT.mkdir(exist_ok=True)
    p = OUT / nome
    cq.exporters.export(wp, str(p), tolerance=0.02, angularTolerance=0.15)
    bb = wp.val().BoundingBox()
    print(f"{nome:28s} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:5.1f} mm   vol {wp.val().Volume()/1000:5.1f} cm3")
    return p


def main():
    cx = caixa()
    _exportar(cx.translate((0, 0, -COSTAS)), "telinha_caixa.stl")   # costas na mesa
    for th in (15, 25, 35):
        sp, info = suporte(th)
        _exportar(sp, f"telinha_suporte_{th}graus.stl")
    if "--checar" in sys.argv:
        checar(cx, sys.argv[sys.argv.index("--checar") + 1])


def montar(forma, theta_graus):
    """Leva algo em coordenadas da caixa para o referencial do suporte (X=u, Y=v, Z=largura)."""
    t = math.radians(theta_graus)
    s, c = math.sin(t), math.cos(t)
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    tr = gp_Trsf()
    tr.SetValues(-s, 0, c, 0,  c, 0, s, 0,  0, 1, 0, LARG_SUPORTE / 2)
    return cq.Shape.cast(BRepBuilderAPI_Transform(forma.wrapped, tr, True).Shape())


def checar(cx, stp):
    """Interferência caixa x placa (STEP) e suporte x caixa montados."""
    placa = cq.importers.importStep(str(stp)).val()
    caixa_s = cx.val()
    ruins = 0
    for sol in placa.Solids():
        vol = caixa_s.intersect(sol).Volume()
        if vol > 1e-3:
            b = sol.BoundingBox(); ruins += 1
            print(f"  INTERFERE {vol:.3f} mm3  x{b.xmin:.1f}..{b.xmax:.1f} y{b.ymin:.1f}..{b.ymax:.1f} z{b.zmin:.1f}..{b.zmax:.1f}")
    print("caixa x placa: peças da placa que encostam =", ruins)
    for th in (15, 25, 35):
        sp, info = suporte(th)
        cm = montar(caixa_s, th)
        v = sp.val().intersect(cm).Volume()
        print(f"suporte {th}: interferência com a caixa {v:.3f} mm3   monitor: traseira u={info['u_p']:.1f}, borda v={info['v_m']:.1f}")


if __name__ == "__main__":
    main()
