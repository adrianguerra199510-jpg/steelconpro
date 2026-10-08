# -*- coding: utf-8 -*-
"""Dibujo en planta y elevacion de la placa base (matplotlib)."""
from __future__ import annotations
import math
import warnings
import logging
logging.getLogger("matplotlib.axes._base").setLevel(logging.ERROR)
import numpy as np
from matplotlib.patches import Circle, Rectangle, Polygon

from .model import Project
from . import geometry as G
from .units import float_to_frac, UnitSet

C_PLATE = "#1f3864"
C_PROF = "#c00000"
C_HOLE = "#0070c0"
C_LUG = "#00843d"
C_STIF = "#b26b00"
C_DIM = "#555555"


warnings.filterwarnings(
    "ignore", message="Ignoring fixed .* limits to fulfill fixed data aspect")


def _dim(ax, a, b, off, text, horizontal=True, fs=7.0):
    """Cota entre los puntos a y b (x, y), desplazada `off` de la linea que los une, con flechas y texto."""
    (x1, y1), (x2, y2) = a, b
    if horizontal:
        yy = y1 + off
        ax.plot([x1, x1], [y1, yy + 0.25 * off], color=C_DIM, lw=0.5, zorder=2)
        ax.plot([x2, x2], [y2, yy + 0.25 * off], color=C_DIM, lw=0.5, zorder=2)
        ax.annotate("", xy=(x1, yy), xytext=(x2, yy),
                    arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=0.8, shrinkA=0, shrinkB=0), zorder=3)
        ax.text((x1 + x2) / 2, yy + (0.012 if off > 0 else -0.012) * abs(off) * 8, text, ha="center",
                va="bottom" if off > 0 else "top", fontsize=fs, color=C_DIM, zorder=4,
                bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.8))
    else:
        xx = x1 + off
        ax.plot([x1, xx + 0.25 * off], [y1, y1], color=C_DIM, lw=0.5, zorder=2)
        ax.plot([x2, xx + 0.25 * off], [y2, y2], color=C_DIM, lw=0.5, zorder=2)
        ax.annotate("", xy=(xx, y1), xytext=(xx, y2),
                    arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=0.8, shrinkA=0, shrinkB=0), zorder=3)
        ax.text(xx + (0.012 if off > 0 else -0.012) * abs(off) * 8, (y1 + y2) / 2, text, ha="left" if off > 0 else "right",
                va="center", fontsize=fs, color=C_DIM, rotation=90, zorder=4,
                bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.8))


def _plan_dims(ax, prj, pos, k, u):
    """Cotas de la placa y de la disposicion de pernos (distancias al borde y entre pernos)."""
    p = prj.plate
    circ = p.shape == "Circular"
    W = (p.Dp if circ else p.B) / k
    H = (p.Dp if circ else p.N) / k
    d = 0.07 * max(W, H)
    f = lambda v: u.fmt("L", v * k)
    # placa: ancho abajo, largo a la derecha (el modelo lleva Y arriba)
    _dim(ax, (-W / 2, -H / 2), (W / 2, -H / 2), -2.6 * d, ("Ø " if circ else "B = ") + f(W))
    if not circ:
        _dim(ax, (W / 2, -H / 2), (W / 2, H / 2), 2.6 * d, "N = " + f(H), horizontal=False)
    cdx, cdy = G.col_shift(prj)                        # columna descentrada: cotas desde el centro de la placa
    if not circ and abs(cdx) > 1e-9:
        _dim(ax, (0.0, -H / 2), (cdx / k, -H / 2), -1.2 * d, "cx = " + f(cdx / k))
    if not circ and abs(cdy) > 1e-9:
        _dim(ax, (W / 2, 0.0), (W / 2, cdy / k), 1.2 * d, "cy = " + f(cdy / k), horizontal=False)
    xs = sorted({round(x / k, 4) for x, _ in pos})
    ys = sorted({round(y / k, 4) for _, y in pos})
    if circ or not pos or len(xs) > 7 or len(ys) > 7:
        return
    # cadena de cotas en X (arriba): borde - pernos - borde
    ch = [-W / 2] + xs + [W / 2]
    for a_, b_ in zip(ch[:-1], ch[1:]):
        if b_ - a_ > 1e-6:
            _dim(ax, (a_, H / 2), (b_, H / 2), 1.2 * d, f(b_ - a_))
    # cadena en Y (izquierda)
    cv = [-H / 2] + ys + [H / 2]
    for a_, b_ in zip(cv[:-1], cv[1:]):
        if b_ - a_ > 1e-6:
            _dim(ax, (-W / 2, a_), (-W / 2, b_), -1.2 * d, f(b_ - a_), horizontal=False)


def plan_view(ax, prj: Project, show_dims=True, labels=True):
    ax.clear()
    p, b = prj.plate, prj.bolts
    u = prj.units()
    k = u.fl                      # factor interno -> unidad mostrada

    # --- placa
    out = G.plate_outline(prj)
    ax.plot([q[0] / k for q in out], [q[1] / k for q in out], color=C_PLATE,
            lw=2.4, zorder=3, label="Placa base")

    # --- perfil
    for i, poly in enumerate(G.section_polys(prj)):
        ax.plot([q[0] / k for q in poly], [q[1] / k for q in poly], color=C_PROF,
                lw=2.0 if i == 0 or prj.section.generic else 1.2, zorder=4,
                label="Perfil" if i == 0 else None)

    # --- rigidizadores
    for idx, (x1, y1, x2, y2) in enumerate(G.stiffener_lines(prj)):
        ax.plot([x1 / k, x2 / k], [y1 / k, y2 / k], color=C_STIF, lw=3.0,
                solid_capstyle="butt", zorder=5,
                label="Rigidizador" if idx == 0 else None)

    # --- llave de corte
    for idx, poly in enumerate(G.lug_outline(prj)):
        ax.add_patch(Polygon([(a / k, b_ / k) for a, b_ in poly], closed=True,
                             fill=True, facecolor=C_LUG, alpha=0.30,
                             edgecolor=C_LUG, lw=1.8, zorder=2,
                             label="Llave de corte" if idx == 0 else None))

    # --- agujeros
    g = b.geom()
    pos = G.bolt_positions(prj)
    for idx, (x, y) in enumerate(pos):
        ax.add_patch(Circle((x / k, y / k), g.dh / 2 / k, fill=False, color=C_HOLE,
                            lw=1.4, zorder=6, label="Agujero" if idx == 0 else None))
        ax.plot([x / k], [y / k], marker="+", color=C_HOLE, ms=5, mew=1.0, zorder=6)
        if labels:
            ax.annotate(f"P{idx + 1}", (x / k, y / k),
                        textcoords="offset points", xytext=(0, -3),
                        ha="center", va="top", fontsize=7.5, fontweight="bold",
                        color="#00407a", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.12", fc="white",
                                  ec="none", alpha=0.75))

    # --- escala y ejes
    if p.shape == "Circular":
        Lm = p.Dp
    else:
        Lm = max(p.N, p.B)
    if show_dims:
        _plan_dims(ax, prj, pos, k, u)
    Lm = (1.7 if show_dims else 1.16) * max(Lm, 1.0) / k
    ax.set_xlim(-Lm / 2, Lm / 2)
    ax.set_ylim(-Lm / 2, Lm / 2)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(False)
    ax.set_axis_off()
    ax.set_xlabel(f"X — direccion B  ({u.L})")
    ax.set_ylabel(f"Y — direccion N  ({u.L})   ↑ lado traccionado por Mux")

    if show_dims:
        txt = []
        if p.shape == "Circular":
            txt.append(f"Ø{u.fmt('L', p.Dp)} × {u.q('L', p.tp)}")
        else:
            txt.append(f"{u.fmt('L', p.N)} × {u.fmt('L', p.B)} × {u.q('L', p.tp)}")
        txt.append(f"{prj.section.describe(u, short=True)}  (rot {prj.section.rotation:g}°)")
        txt.append(f"{len(pos)} pernos Ø{b.size}\"  {b.atype.split('(')[0].strip()}")
        if prj.stiff.enabled:
            txt.append(f"{prj.stiff.count} rigidizadores {u.q('L', prj.stiff.t)}")
        if prj.lug.enabled:
            txt.append(f"Llave {u.fmt('L', prj.lug.W)}×{u.fmt('L', prj.lug.H)}×"
                       f"{u.q('L', prj.lug.t)}")
        ax.set_title("PLANTA — " + "   |   ".join(txt), fontsize=9, loc="left")
    ax.legend(loc="lower center" if show_dims else "upper right", ncol=4 if show_dims else 1, fontsize=7, framealpha=0.9)


def elevation_view(ax, prj: Project):
    """Corte vertical: perfil, placa, mortero, pedestal y anclajes."""
    ax.clear()
    p, b, c = prj.plate, prj.bolts, prj.conc
    g = b.geom()
    u = prj.units()
    k = u.fl                      # interno (in) -> unidad mostrada
    Bx = (p.Dp if p.shape == "Circular" else p.B) / k
    hef = b.hef / k
    tp = p.tp / k
    B2 = c.B2 / k
    gr = p.grout / k
    m = 1.0 / k                   # una pulgada, en unidades de dibujo

    # de arriba hacia abajo: placa, separacion libre (stand-off), mortero y, debajo, el elemento de concreto
    so = max(0.0, getattr(b, "standoff", 0.0)) / k
    zc = -(gr + so)                       # cara superior del concreto (hef se mide desde aqui)
    from .ubar import ubar
    ub = ubar(prj)
    hc = hef + 6 * m
    if ub is not None:                    # el bloque debe contener las patas de las U
        hc = max(hc, (ub["depth"] + ub["leg"]) / k + 3 * m)
    ax.add_patch(Rectangle((-B2 / 2, zc - hc), B2, hc,
                           facecolor="#e8e8e8", edgecolor="#999999", lw=1.0, zorder=1))
    if gr > 0:
        ax.add_patch(Rectangle((-Bx / 2, zc), Bx, gr,
                               facecolor="#d9d2c5", edgecolor="#8a8172", lw=0.8,
                               hatch="//", zorder=2))
    ax.add_patch(Rectangle((-Bx / 2, 0), Bx, tp,
                           facecolor="#b9c6de", edgecolor=C_PLATE, lw=1.8, zorder=4))

    bw, bh = G.profile_bbox(prj)
    bw, bh = bw / k, max(bh, 10.0) / k
    ax.add_patch(Rectangle((-bw / 2, tp), bw, bh,
                           facecolor="#f2c3c3", edgecolor=C_PROF, lw=1.8, zorder=3))

    if prj.stiff.enabled:
        st = prj.stiff
        for sgn in (1, -1):
            pts = [(sgn * (bw / 2 + x / k), tp + y / k) for x, y in st.outline()]
            ax.add_patch(Polygon(pts, closed=True, facecolor="#ffe0b0",
                                 edgecolor=C_STIF, lw=1.4, zorder=5))

    if prj.lug.enabled:
        Lg = prj.lug
        _lx = [q[0] for P in G.lug_outline(prj) for q in P] or [-Lg.t / 2, Lg.t / 2]
        _x0, _w = min(_lx), max(_lx) - min(_lx)
        ax.add_patch(Rectangle((_x0 / k, -Lg.H / k), _w / k, Lg.H / k,
                               facecolor="#bfe3cd", edgecolor=C_LUG, lw=1.6, zorder=5))

    # --- anclajes
    Fh = g.Fhex / k
    xs_b = sorted({round(x / k, 4) for x, _ in G.bolt_positions(prj)})
    for x in xs_b:
        _hook = b.atype.startswith("Gancho")
        ax.plot([x, x], [tp + 2 * m, zc - hef + (2.0 * g.db / k if _hook else 0.0)], color="#333333", lw=2.0,
                zorder=6)                                                  # vastago (con gancho: hasta el doblez)
        from .params3d import washer_radius, washer_thickness
        tw_ = max(washer_thickness(prj), 0.0) / k
        if tw_ > 0:                                                        # arandela
            rw_ = washer_radius(prj) / k
            ax.add_patch(Rectangle((x - rw_, tp), 2 * rw_, tw_, facecolor="#aab2bb", edgecolor="#555555",
                                   lw=0.8, zorder=6))
        ax.plot([x - Fh / 2, x + Fh / 2], [tp + tw_ + 0.9 * m, tp + tw_ + 0.9 * m],
                color="#333333", lw=3.5, solid_capstyle="butt", zorder=7)   # tuerca
        if so > 0:                                                         # tuerca de nivelacion
            ax.plot([x - Fh / 2, x + Fh / 2], [-0.4 * m, -0.4 * m],
                    color="#333333", lw=3.5, solid_capstyle="butt", zorder=7)
        t = b.atype
        if t.startswith("Con cabeza"):
            ax.plot([x - Fh / 2, x + Fh / 2], [zc - hef, zc - hef],
                    color="#333333", lw=4.0, solid_capstyle="butt", zorder=7)
        elif t.startswith("Gancho en L") or t.startswith("Gancho en J"):
            from .params3d import hook_profile
            eh_ = b.eh if b.eh > 0 else 3 * g.db
            prof, rc = hook_profile("gancho_L" if t.startswith("Gancho en L") else "gancho_J", g.db, eh_)
            ax.plot([x + s_ / k for s_, _ in prof], [zc - hef + z_ / k for _, z_ in prof],
                    color="#333333", lw=2.0, zorder=7, solid_joinstyle="round")

    if ub is not None:
        xl, xr = ub["xl"] / k, ub["xr"] / k
        zt = zc - ub["depth"] / k
        zb = zt - ub["leg"] / k
        rb_ = min(ub["rb"] / k, 0.4 * (ub["leg"] / k), 0.4 * (xr - xl))
        omega = ub["kind"] == "OMEGA"
        tl = ub["tail"] / k
        # recorrido con esquinas redondeadas (radio al eje del doblez)
        def arc(cx, cz, a0, a1):
            th = np.radians(np.linspace(a0, a1, 10))
            return list(zip(cx + rb_ * np.cos(th), cz + rb_ * np.sin(th)))
        up_l = arc(xl + rb_, zt - rb_, 180, 90)           # esquina superior izquierda
        up_r = arc(xr - rb_, zt - rb_, 90, 0)             # esquina superior derecha
        if omega:                                         # gancho estandar de 90° hacia afuera en cada pata
            hk_l = arc(xl - rb_, zb + rb_, 0, -90)        # pata izquierda: baja y gira hacia la izquierda
            hk_r = arc(xr + rb_, zb + rb_, 180, 270)      # pata derecha: baja y gira hacia la derecha
            pts = [(xl - tl, zb)] + hk_l[::-1] + [(xl, zt - rb_)] + up_l + up_r + [(xr, zb + rb_)] + hk_r + [(xr + tl, zb)]
        else:
            pts = [(xl, zb), (xl, zt - rb_)] + up_l + up_r + [(xr, zb)]
        ax.plot([q[0] for q in pts], [q[1] for q in pts], color="#d43c3c", lw=2.4, zorder=6, solid_joinstyle="round")
        ax.plot([xl, xr] if not omega else [xl - tl, xr + tl], [zb, zb], ls="none", marker="s", ms=3, color="#d43c3c", zorder=6)
        xd = xl - (tl if omega else 0.0) - 1.2 * m
        ax.annotate("", xy=(xd, zt), xytext=(xd, zb),
                    arrowprops=dict(arrowstyle="<->", color="#d43c3c", lw=0.9))
        zcr = zc - ub["z_cross"] / k
        ax.text(xd - 0.6 * m, (zt + zb) / 2, f"{'ldh' if omega else 'ld'} = {u.q('L', ub['below'])}",
                fontsize=8, color="#d43c3c", rotation=90, va="center", ha="right")
        ax.plot([xd - 0.5 * m, xd + 0.5 * m], [zcr, zcr], color="#d43c3c", lw=0.8)
        ax.text(0.0, zt - 1.0 * m, f"{ub['n']} {'Omega' if omega else 'U'} {ub['size']}", fontsize=8, color="#d43c3c",
                ha="center", va="top")
    ax.annotate("", xy=(Bx / 2 + 2 * m, zc), xytext=(Bx / 2 + 2 * m, zc - hef),
                arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=0.9))
    ax.text(Bx / 2 + 2.6 * m, zc - hef / 2, f"hef = {u.q('L', b.hef)}", fontsize=8,
            color=C_DIM, rotation=90, va="center")

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlim(-B2 / 2 - 2 * m - (6 * m if ub is not None else 0), B2 / 2 + 8 * m)
    ax.set_ylim(zc - hc - 2 * m, tp + bh + 2 * m)
    ax.set_xlabel(f"X  ({u.L})")
    ax.set_ylabel(f"Z  ({u.L})")
    ax.set_title("ELEVACION (esquematica)", fontsize=9, loc="left")
    ax.grid(False)
    ax.set_axis_off()


def stiffener_detail(ax, prj):
    """Detalle a escala de una pletina rigidizadora."""
    ax.clear()
    st = prj.stiff
    if not st.enabled:
        ax.text(0.5, 0.5, "Rigidizadores desactivados", ha="center", va="center",
                transform=ax.transAxes, fontsize=10, color="#777777")
        ax.set_xticks([]); ax.set_yticks([])
        return
    u = prj.units()
    k = u.fl
    L, h, tp = st.L / k, st.h / k, prj.plate.tp / k
    root = st.clip_root / k

    pts = [(x / k, y / k) for x, y in st.outline()[:-1]]
    ax.add_patch(Polygon(pts, closed=True, facecolor="#ffe0b0",
                         edgecolor=C_STIF, lw=2.0, zorder=3))

    # columna y placa de referencia
    ax.add_patch(Rectangle((-0.30 * L, 0), 0.30 * L, h * 1.15,
                           facecolor="#f2c3c3", edgecolor=C_PROF, lw=1.5, zorder=2))
    ax.add_patch(Rectangle((-0.30 * L, -tp), L * 1.45, tp,
                           facecolor="#b9c6de", edgecolor=C_PLATE, lw=1.5, zorder=2))

    # soldaduras
    ax.plot([root, st.weld_len_plate / k + root], [0, 0],
            color="#0070c0", lw=4.0, solid_capstyle="butt", zorder=5)
    ax.plot([0, 0], [root, st.weld_len_col / k + root],
            color="#0070c0", lw=4.0, solid_capstyle="butt", zorder=5)

    d = 0.09 * max(L, h)          # separacion de las cotas, a escala del dibujo
    ax.annotate("", xy=(0, -tp - d), xytext=(L, -tp - d),
                arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=0.9))
    ax.text(L / 2, -tp - 1.7 * d, f"L = {u.q('L', st.L)}", ha="center",
            fontsize=8, color=C_DIM)
    ax.annotate("", xy=(L * 1.18, 0), xytext=(L * 1.18, h),
                arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=0.9))
    ax.text(L * 1.24, h / 2, f"h = {u.q('L', st.h)}", rotation=90, va="center",
            fontsize=8, color=C_DIM)

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlim(-0.45 * L, L * 1.55)
    ax.set_ylim(-tp - 2.6 * d, h * 1.25)
    ax.set_title(f"DETALLE DEL RIGIDIZADOR — {st.shape}, t = {u.q('L', st.t)}, "
                 f"destaje {u.q('L', st.clip_root)}", fontsize=9, loc="left")
    ax.set_xlabel(f"Proyeccion desde la cara del perfil  ({u.L})")
    ax.set_ylabel(f"Altura sobre la placa  ({u.L})")
    ax.grid(False)
    ax.set_axis_off()
