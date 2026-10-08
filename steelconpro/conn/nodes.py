# -*- coding: utf-8 -*-
"""Los tres modulos de nudo (viga-columna, viga a viga, crucetas) vistos por la interfaz: identidad, texto de la lista y esquema (planta y elevacion).

Son solo geometria: `solve` devuelve un resultado vacio (sin verificaciones) y no se corre ningun analisis.
"""
from __future__ import annotations
import math

import numpy as np

from .specs import (CT_NODE, CT_B2B, CT_TRUSS, MODE_COL, MODE_BEAM, MODE_CHORD, MAIN_NAMES, MEMBER_NAMES, ATTR_OF)


class NodeModule:
    VISUAL = True                                  # solo geometria: sin calculo ni analisis

    def __init__(self, ctype, mode, tab, prefix, noun, plural):
        self.NAME, self.MODE, self.ATTR, self.TAB, self.PREFIX = ctype, mode, ATTR_OF[ctype], tab, prefix
        self.noun, self.plural = noun, plural      # "viga" / "vigas", "diagonal" / "diagonales"...

    def spec(self, prj):
        return getattr(prj, self.ATTR)

    def label(self, prj) -> str:
        nd = self.spec(prj)
        n = len(nd.members)
        return f"{nd.main_shape}  ·  {n} {self.noun if n == 1 else self.plural}"

    def solve(self, prj, detail: bool = True):
        from ..solver import Results
        R = Results()
        R.closed_form = True
        return R

    def input_rows(self, prj, us):
        nd = self.spec(prj)
        rows = [(MAIN_NAMES[nd.mode], nd.main_shape)]
        for m in nd.members:
            rows.append((m.name, f"{m.shape}, azimut {m.az:g}°, elevación {m.el:g}°, {m.conn}"))
        return rows

    def draw(self, fig, prj):
        draw_scheme(fig, self.spec(prj), self.TAB)


MODULES = {CT_NODE: NodeModule(CT_NODE, MODE_COL, "Nudo viga-columna", "NC", "viga", "vigas"),
           CT_B2B: NodeModule(CT_B2B, MODE_BEAM, "Viga a viga", "VV", "viga secundaria", "vigas secundarias"),
           CT_TRUSS: NodeModule(CT_TRUSS, MODE_CHORD, "Crucetas", "CR", "diagonal", "diagonales")}


# ================================================================================================== esquema (planta y elevacion)
def _silhouette(shape, o, sx, sy, A, s0, s1):
    """Los 8 vertices de la caja (bf × d × largo) de un miembro, en 3D."""
    hx = shape.bf / 2.0 if not shape.is_round else shape.d / 2.0
    hy = shape.d / 2.0
    pts = []
    for ax in (-hx, hx):
        for ay in (-hy, hy):
            for s in (s0, s1):
                pts.append(np.asarray(o, float) + ax * sx + ay * sy + s * A)
    return np.array(pts)


def _hull2(P):
    from .assembly import _hull
    return _hull([(float(p[0]), float(p[1])) for p in P])


def draw_scheme(fig, nd, title=""):
    from matplotlib.patches import Polygon
    from . import assembly as AS
    fig.clf()
    axp = fig.add_subplot(2, 1, 1)
    axe = fig.add_subplot(2, 1, 2)
    mshape = AS.shape_of(nd.main_shape)
    A, msx, msy = AS.main_frame(nd)
    lneg, lpos = nd.lengths()
    if lneg + lpos < 1.0:
        lneg = lpos = 24.0
    items = [(MAIN_NAMES[nd.mode], _silhouette(mshape, (0, 0, 0), msx, msy, A, -lneg, lpos), "#bdd7ee", "#1f3864")]
    ext = AS.outer_extent(mshape)
    for m in nd.members:
        shp = AS.shape_of(m.shape)
        dv = AS.member_dir(m)
        _, sx, sy = AS.member_frame(m)
        P0 = A * m.pos + (msy * m.off if nd.mode != MODE_COL else 0.0)
        d2 = (float(np.dot(dv, msx)), float(np.dot(dv, msy)))
        s_ex = AS.ray_exit(ext, (0.0, m.off if nd.mode != MODE_COL else 0.0), d2) if math.hypot(*d2) > 1e-6 else None
        Q = P0 + dv * (s_ex or 0.0)
        items.append((m.name, _silhouette(shp, Q + dv * max(m.gap, 0.0), sx, sy, dv, 0.0, max(m.L, 1.0)), "#9dc3e6", "#1f3864"))
    allp = np.vstack([it[1] for it in items])
    for ax, (i, j), nm, xl, yl in ((axp, (0, 1), "Planta (X–Y)", "X, in", "Y, in"), (axe, (0, 2), "Elevación (X–Z)", "X, in", "Z, in")):
        for name, P, fc, ec in items:
            hull = AS._hull([(float(p[i]), float(p[j])) for p in P])
            if len(hull) >= 3:
                ax.add_patch(Polygon(hull, closed=True, fc=fc, ec=ec, lw=0.9, alpha=0.9))
                cx = float(np.mean([h[0] for h in hull])); cy = float(np.mean([h[1] for h in hull]))
                ax.text(cx, cy, name, ha="center", va="center", fontsize=7.5, color="#10243f", weight="bold")
        ax.plot([0], [0], "o", ms=4, color="#c00000")
        pad = 0.08 * max(float(np.ptp(allp[:, i])), float(np.ptp(allp[:, j])), 1.0)
        ax.set_xlim(float(allp[:, i].min()) - pad, float(allp[:, i].max()) + pad)
        ax.set_ylim(float(allp[:, j].min()) - pad, float(allp[:, j].max()) + pad)
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_title(nm, fontsize=9, loc="left")
        ax.set_xlabel(xl, fontsize=7.5)
        ax.set_ylabel(yl, fontsize=7.5)
        ax.tick_params(labelsize=7)
        ax.grid(True, color="#dddddd", lw=0.5)
    fig.suptitle(title or "Nudo", fontsize=10, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
