# -*- coding: utf-8 -*-
"""Piezas de dibujo compartidas por las tipologias (matplotlib): soporte, viga con cope, pernos y cotas."""
from __future__ import annotations

from matplotlib.patches import Circle, Rectangle

from ..draw import _dim, C_DIM  # noqa: F401  (reexportadas)

C_BEAM = "#9dc3e6"
C_BEAM_EDGE = "#1f3864"
C_PLATE = "#f4b183"
C_PLATE_EDGE = "#843c0c"
C_SUP = "#bfbfbf"
C_WELD = "#c00000"
C_BOLT = "#1f3864"
C_ANGLE = "#c5e0b4"
C_ANGLE_EDGE = "#375623"


def hatched(ax, x0, y0, x1, y1, fc=C_SUP, z=1):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fc, ec="#555555", lw=0.8, hatch="////", zorder=z))


def support_and_beam(ax, beam, sup, sup_is_girder_web, top_flush, g, gap, Lshow):
    """Soporte (viga maestra vista de punta o banda) y viga apoyada con su cope, en elevacion.
    Devuelve (sx0, xr): x del borde izquierdo del soporte y de la linea de rotura."""
    d, tf = beam.d, beam.tf
    ct, cb = g["ct"], g["cb"]
    cl = g["x_cope"] - gap
    xr = gap + Lshow
    if sup is not None and sup_is_girder_web and top_flush:
        tws, tfs, bfs, ds = sup.tw, sup.tf, sup.bf, sup.d
        hatched(ax, -tws, 0, 0, ds)
        hatched(ax, -tws / 2 - bfs / 2, 0, -tws / 2 + bfs / 2, tfs)
        hatched(ax, -tws / 2 - bfs / 2, ds - tfs, -tws / 2 + bfs / 2, ds)
        sx0 = -tws / 2 - bfs / 2
    else:
        hatched(ax, -1.2, -0.8, 0, d + 0.8)
        sx0 = -1.2
    ax.add_patch(Rectangle((gap, ct), Lshow, d - ct - cb, fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((gap + (cl if ct > 0 else 0.0), 0), xr - gap - (cl if ct > 0 else 0.0), tf,
                           fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((gap + (cl if cb > 0 else 0.0), d - tf), xr - gap - (cl if cb > 0 else 0.0), tf,
                           fc=C_BEAM, ec=C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.plot([xr, xr], [-0.1, d + 0.1], color="#666666", lw=0.8, ls=(0, (6, 3)), zorder=3)
    return sx0, xr


def bolt(ax, x, y, dh, z=6):
    ax.add_patch(Circle((x, y), dh / 2, fc="white", ec=C_BOLT, lw=1.3, zorder=z))
    ax.plot([x - dh / 2 - 0.15, x + dh / 2 + 0.15], [y, y], color=C_BOLT, lw=0.6, zorder=z + 1)
    ax.plot([x, x], [y - dh / 2 - 0.15, y + dh / 2 + 0.15], color=C_BOLT, lw=0.6, zorder=z + 1)


def blank(ax):
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
