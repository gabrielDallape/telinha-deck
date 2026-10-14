"""Renders de conferência (PNG) da caixa, do suporte e da montagem."""
import math, numpy as np, trimesh, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import cadquery as cq, caixa as k

def malha(shape, tol=0.08):
    v, f = shape.tessellate(tol, 0.3)
    return np.array([[p.x, p.y, p.z] for p in v]), np.array(f)

def desenha(ax, partes, elev, azim, titulo, lim=None):
    luz = np.array([0.4, -0.6, 0.8]); luz /= np.linalg.norm(luz)
    todos = []
    for (V, F, cor, a) in partes:
        tri = V[F]; n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        s = np.clip(np.abs(n @ luz), 0, 1) * 0.65 + 0.35
        pc = Poly3DCollection(tri, alpha=a); pc.set_facecolor(np.c_[s[:, None] * np.array(cor)[None, :]])
        pc.set_edgecolor("none"); ax.add_collection3d(pc); todos.append(V)
    V = np.vstack(todos); lo, hi = V.min(0), V.max(0); c = (lo + hi) / 2; r = (hi - lo).max() / 2 * 0.85
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev, azim); ax.set_title(titulo); ax.set_axis_off()

cx = k.caixa().val()
Vc, Fc = malha(cx)
vidro = cq.Workplane("XY").workplane(offset=k.VIDRO_TRAS).rect(k.VIDRO_X, k.VIDRO_Y).extrude(k.VIDRO_FRENTE - k.VIDRO_TRAS).val()
Vg, Fg = malha(vidro, 0.5)
AZUL, CINZA, PRETO, LARANJA = (0.35, 0.55, 0.9), (0.75, 0.75, 0.75), (0.12, 0.12, 0.15), (0.95, 0.55, 0.2)

fig = plt.figure(figsize=(16, 11))
desenha(fig.add_subplot(2, 3, 1, projection="3d"), [(Vc, Fc, AZUL, 1)], 35, -55, "caixa (frente)")
desenha(fig.add_subplot(2, 3, 2, projection="3d"), [(Vc, Fc, AZUL, 1)], -40, -60, "caixa (costas: trilhos, parafusos, ventilação)")
desenha(fig.add_subplot(2, 3, 3, projection="3d"), [(Vc, Fc, AZUL, 1)], 15, -100, "lado das USB-C")
desenha(fig.add_subplot(2, 3, 4, projection="3d"), [(Vc, Fc, AZUL, 1)], 15, 0, "lado dos botões RST/BOOT/PWR")
desenha(fig.add_subplot(2, 3, 5, projection="3d"), [(Vc, Fc, AZUL, 1), (Vg, Fg, PRETO, 1)], 35, -55, "com a placa")
desenha(fig.add_subplot(2, 3, 6, projection="3d"), [(Vc, Fc, AZUL, 1)], 15, 80, "lado do cartão SD")
plt.tight_layout(); plt.savefig("render_caixa.png", dpi=75); plt.close()

fig = plt.figure(figsize=(16, 6))
for i, th in enumerate((15, 25, 35)):
    sp, info = k.suporte(th)
    Vs, Fs = malha(sp.val())
    Vm, Fm = malha(k.montar(cx, th)); Vgl, Fgl = malha(k.montar(vidro, th), 0.5)
    mon = cq.Workplane("XY").box(25, 60, 90, centered=False).translate((info["u_p"], info["v_m"], -5)).val()
    Vmo, Fmo = malha(mon, 1)
    # plot com eixos: X=u (frente), Y=v (cima), Z=largura -> mapeia para (Z, X, Y) no matplotlib
    m = lambda V: V[:, [2, 0, 1]]
    ax = fig.add_subplot(1, 3, i + 1, projection="3d")
    desenha(ax, [(m(Vmo), Fmo, CINZA, 0.35), (m(Vs), Fs, LARANJA, 1), (m(Vm), Fm, AZUL, 1), (m(Vgl), Fgl, PRETO, 1)],
            8, -20, f"{th}° (cinza = monitor)")
plt.tight_layout(); plt.savefig("render_montagem.png", dpi=75); plt.close()

fig = plt.figure(figsize=(14, 5))
for i, th in enumerate((15, 25, 35)):
    sp, info = k.suporte(th); ax = fig.add_subplot(1, 3, i + 1)
    for S, cor in ((k.montar(cx, th), "tab:blue"), (sp.val(), "tab:orange"), (k.montar(vidro, th), "k")):
        sec = cq.Workplane("XY").add(S).section(25.0 if S is not sp.val() else 25.0)
        for e in sec.edges().vals():
            pts = np.array([[p.x, p.y] for p in e.positions(list(np.linspace(0, 1, 30)))]); ax.plot(pts[:, 0], pts[:, 1], color=cor, lw=1)
    ax.axhline(info["v_m"], color="gray", ls="--"); ax.axvline(info["u_p"], color="gray", ls="--")
    ax.fill_between([info["u_p"], info["u_p"] + 25], info["v_m"], info["v_m"] + 80, color="gray", alpha=0.2)
    ax.set_aspect("equal"); ax.set_title(f"corte lateral {th}°  (mm)"); ax.grid(alpha=0.3)
plt.tight_layout(); plt.savefig("render_corte.png", dpi=80); plt.close()
print("ok")
