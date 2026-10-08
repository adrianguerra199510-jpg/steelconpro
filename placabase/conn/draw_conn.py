# -*- coding: utf-8 -*-
"""Dibujos de la conexion de corte con placa simple (matplotlib): elevacion y planta con cotas.

Ejes de la elevacion: x a lo largo de la viga desde la cara del soporte (x = 0), y hacia abajo desde el tope de
la viga.  Se mira la conexion desde el lado de la placa (la placa queda delante del alma).
"""
from __future__ import annotations

from matplotlib.patches import Circle, Rectangle, Polygon

from ..draw import _dim, C_DIM
from ..units import float_to_frac
from .shear_tab import geometry
from .specs import SUP_KINDS

C_BEAM = "#9dc3e6"
C_BEAM_EDGE = "#1f3864"
C_PLATE = "#f4b183"
C_PLATE_EDGE = "#843c0c"
C_SUP = "#bfbfbf"
C_WELD = "#c00000"
C_BOLT = "#1f3864"


def _hatched(ax, x0, y0, x1, y1, fc=C_SUP, z=1):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fc, ec="#555555", lw=0.8, hatch="////", zorder=z))


def elevation(ax, prj, show_dims=True):
    """Alzado de la conexion con cope, placa, pernos y soldadura."""
    st = prj.stab
    g = geometry(st)
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    beam, sup = g["beam"], g["sup"]
    if beam is None:
        ax.text(0.5, 0.5, f"Perfil '{st.beam}' no encontrado", ha="center", va="center", transform=ax.transAxes)
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    d, tf, tw = beam.d, beam.tf, beam.tw
    a, gap, ct, cb, cl = st.a, st.gap, g["ct"], g["cb"], max(st.cope_len, 0.0)
    n, s, y_top, Lb = g["n"], st.s, g["y_top"], g["Lb"]
    Lshow = max(a + st.leh_p + 3.0, gap + cl + 3.0)
    xr = gap + Lshow

    # ---- soporte
    if sup is not None and st.sup_kind == SUP_KINDS[0] and st.top_flush:
        # viga maestra vista de punta, tope a ras: alma y alas (el ala sobresale hacia la viga apoyada)
        tws, tfs, bfs, ds = sup.tw, sup.tf, sup.bf, sup.d
        _hatched(ax, -tws, 0, 0, ds)
        _hatched(ax, -tws / 2 - bfs / 2, 0, -tws / 2 + bfs / 2, tfs)
        _hatched(ax, -tws / 2 - bfs / 2, ds - tfs, -tws / 2 + bfs / 2, ds)
        sx0 = -tws / 2 - bfs / 2
    else:
        _hatched(ax, -1.2, -0.8, 0, d + 0.8)
        sx0 = -1.2

    # ---- viga apoyada: alma y alas (de canto), con el cope
    ax.add_patch(Rectangle((gap, ct), Lshow, d - ct - cb, fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((gap + (cl if ct > 0 else 0.0), 0), xr - gap - (cl if ct > 0 else 0.0), tf,
                           fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((gap + (cl if cb > 0 else 0.0), d - tf), xr - gap - (cl if cb > 0 else 0.0), tf,
                           fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.0, zorder=2))
    # linea de rotura a la derecha
    ax.plot([xr, xr], [-0.1, d + 0.1], color="#666666", lw=0.8, ls=(0, (6, 3)), zorder=3)

    # ---- placa (delante del alma), soldadura y pernos
    py0, py1 = y_top - st.lev_p, y_top + Lb + st.lev_p
    ax.add_patch(Rectangle((0, py0), a + st.leh_p, py1 - py0, fc=C_PLATE, ec=C_PLATE_EDGE, lw=1.2, alpha=0.62, zorder=4))
    ax.plot([0, 0], [py0, py1], color=C_WELD, lw=3.2, solid_capstyle="butt", zorder=5)
    dh = g["dh"]
    for i in range(n):
        yb = y_top + i * s
        ax.add_patch(Circle((a, yb), dh / 2, fc="white", ec=C_BOLT, lw=1.3, zorder=6))
        ax.plot([a - dh / 2 - 0.15, a + dh / 2 + 0.15], [yb, yb], color=C_BOLT, lw=0.6, zorder=7)
        ax.plot([a, a], [yb - dh / 2 - 0.15, yb + dh / 2 + 0.15], color=C_BOLT, lw=0.6, zorder=7)

    # ---- cotas
    if show_dims:
        yd0 = -0.9
        _dim(ax, (0, 0), (gap, 0), yd0, q(gap) if gap > 0 else "")
        _dim(ax, (0, 0), (a, 0), yd0 - 1.6, f"a = {q(a)}")
        _dim(ax, (a, 0), (a + st.leh_p, 0), yd0 - 1.6, q(st.leh_p))
        if cl > 0 and (ct > 0 or cb > 0):
            _dim(ax, (gap, 0), (gap + cl, 0), yd0 - 3.2, f"c = {q(cl)}")
        _dim(ax, (xr, py0), (xr, py1), 1.6, f"Lp = {q(py1 - py0)}", horizontal=False)
        if n > 1:
            _dim(ax, (xr, y_top), (xr, y_top + Lb), 3.4, f"{n - 1}×{q(s)} = {q(Lb)}", horizontal=False)
        if ct > 0:
            _dim(ax, (sx0, 0), (sx0, ct), -1.6, f"cope sup. = {q(ct)}", horizontal=False)
        if cb > 0:
            _dim(ax, (sx0, d - cb), (sx0, d), -1.6, f"cope inf. = {q(cb)}", horizontal=False)
        _dim(ax, (sx0, 0), (sx0, y_top), -4.4, f"y = {q(y_top)}", horizontal=False)
        ax.text(0.2, d + 0.9,
                f"Placa {q(py1 - py0)} × {q(a + st.leh_p)} × {q(st.tp)} {us.L}   (lev = {q(st.lev_p)})",
                fontsize=7.5, color=C_PLATE_EDGE, va="top")
        ax.text(0.2, d + 1.7,
                f"{n} Ø{st.bolt_size}\" {st.bolt_grade} — filete {float_to_frac(st.weld_size)}\" {st.electrode} (ambos lados)",
                fontsize=7.5, color=C_BOLT, va="top")
    ax.set_xlim(sx0 - 6.0, xr + 7.5)
    ax.set_ylim(d + 3.4, -6.2)
    ax.set_title(f"Elevacion — {st.beam} sobre {st.sup_label} ({st.sup_kind.lower()})", fontsize=9)


def plan(ax, prj, show_dims=True):
    """Planta: el alma de la viga, la placa a un lado, los pernos y la soldadura al soporte."""
    st = prj.stab
    g = geometry(st)
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    beam, sup = g["beam"], g["sup"]
    if beam is None:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    tw, bf = beam.tw, beam.bf
    a, gap, cl = st.a, st.gap, max(st.cope_len, 0.0)
    tws = _support_t(st, sup)
    Lshow = max(a + st.leh_p + 3.0, gap + cl + 3.0)
    xr = gap + Lshow
    zp0 = tw / 2                    # la placa va del lado +z
    # soporte (alma o ala): banda ancha
    _hatched(ax, -tws, -bf / 2 - 1.0, 0, bf / 2 + 1.0 + st.tp)
    # ala superior (vista desde arriba tapa el alma): se dibuja tenue; con cope superior empieza en el cope
    x_fl = gap + (cl if g["ct"] > 0 else 0.0)
    ax.add_patch(Rectangle((x_fl, -bf / 2), xr - x_fl, bf, fc=C_BEAM, ec=C_BEAM_EDGE, lw=0.9, alpha=0.45, zorder=2))
    ax.add_patch(Rectangle((gap, -tw / 2), xr - gap, tw, fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.2, zorder=3))
    ax.add_patch(Rectangle((0, zp0), a + st.leh_p, st.tp, fc=C_PLATE, ec=C_PLATE_EDGE, lw=1.2, zorder=4))
    # soldadura: triangulos en el encuentro placa-soporte (ambos lados de la placa)
    w = st.weld_size
    ax.add_patch(Polygon([(0, zp0), (w, zp0), (0, zp0 - w)], fc=C_WELD, ec=C_WELD, zorder=5))
    ax.add_patch(Polygon([(0, zp0 + st.tp), (w, zp0 + st.tp), (0, zp0 + st.tp + w)], fc=C_WELD, ec=C_WELD, zorder=5))
    # perno: vastago
    db = g["db"]
    ax.add_patch(Rectangle((a - db / 2, -tw / 2 - 0.35), db, tw + st.tp + 0.7, fc="white", ec=C_BOLT, lw=1.2, zorder=6))
    ax.plot([xr, xr], [-bf / 2 - 0.2, bf / 2 + 0.2], color="#666666", lw=0.8, ls=(0, (6, 3)), zorder=3)
    if show_dims:
        _dim(ax, (0, -bf / 2), (a, -bf / 2), -1.2, f"a = {q(a)}")
        _dim(ax, (a, -bf / 2), (a + st.leh_p, -bf / 2), -1.2, q(st.leh_p))
        if gap > 0:
            _dim(ax, (0, -bf / 2), (gap, -bf / 2), -2.7, q(gap))
        ax.text(xr - 0.2, zp0 + st.tp + 0.9, f"placa tp = {q(st.tp)}\nalma tw = {q(tw)}", fontsize=7.0, color=C_DIM,
                ha="right", va="bottom")
        ax.text(w + 0.15, zp0 + st.tp + w + 0.25, f"filete {float_to_frac(w)}\"", fontsize=7.0, color=C_WELD)
    ax.set_xlim(-tws - 1.5, xr + 4.5)
    ax.set_ylim(-bf / 2 - 3.6, bf / 2 + st.tp + 2.2)
    ax.set_title("Planta (vista desde arriba)", fontsize=9)


def _support_t(st, sup) -> float:
    if sup is None:
        return 0.5
    return sup.tf if st.sup_kind == SUP_KINDS[2] else sup.tw
