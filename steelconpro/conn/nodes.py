# -*- coding: utf-8 -*-
"""El modulo de nudo vista por la interfaz: identidad, texto de la lista y esquema (planta y elevacion).

`solve` corre las verificaciones por codigo (conn/checks); el analisis 3D por elementos finitos se agrega despues.
"""
from __future__ import annotations
import math

import numpy as np

from .specs import CT_NODE, ATTR_OF


class NodeModule:
    VISUAL = False                                 # tiene verificaciones por codigo (ver conn/checks); el analisis 3D llega despues
    NORMS = "AISC 360-22 (Especificacion), AISC Steel Construction Manual 15a ed., AISC 341/358 donde aplique"

    def __init__(self, ctype, tab, prefix):
        self.NAME, self.ATTR, self.TAB, self.PREFIX = ctype, ATTR_OF[ctype], tab, prefix
        self.TITLE = tab

    def spec(self, prj):
        return getattr(prj, self.ATTR)

    def label(self, prj) -> str:
        nd = self.spec(prj)
        n = len(nd.members)
        return f"principal {nd.main_name} {nd.main_shape}  ·  {n} miembro{'' if n == 1 else 's'} conectado{'' if n == 1 else 's'}  ·  {len(nd.operations)} op."

    def signature(self, prj) -> str:
        """Huella de todo lo que cambia el resultado (miembros, operaciones, cargas y unidades): detecta resultados desactualizados."""
        import dataclasses, hashlib, json
        d = dataclasses.asdict(self.spec(prj))
        d["_u"] = [prj.u_len, prj.u_force, prj.u_stress, prj.u_moment]
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()

    def solve(self, prj, detail: bool = True):
        """Verificaciones por codigo de todas las operaciones con todos los casos de carga."""
        from .checks import adapters
        return adapters.run(prj, self.spec(prj))

    def input_rows(self, prj, us):
        from .assembly import shape_of
        nd = self.spec(prj)
        rows = [(f"{nd.main_name} (principal)", f"{nd.main_shape}, {nd.main_steel}; eje: azimut {nd.main_az:g}°, elevación {nd.main_el:g}°; {nd.main_end}")]
        for m in nd.members:
            ops = "; ".join(o.kind for o in nd.ops_of(m.name)) or "sin operaciones"
            rows.append((m.name, f"{m.shape} ({m.steel}), azimut {m.az:g}°, elevación {m.el:g}°, posición {us.q('L', m.pos)}: {ops}"))
        for o in nd.operations:
            if o.is_connection and "Cartela" not in o.kind and "Corte" not in o.kind:
                rows.append((f"{o.member} — {o.kind}", f"pernos {o.n_bolts} × Ø{o.bolt_size} {o.bolt_grade}, separación {us.q('L', o.bolt_s)}, "
                             f"placa/ángulo t = {us.q('L', o.plate_t)} ({o.plate_steel}), soldadura {us.q('L', o.weld_size)}"))
            elif o.kind.startswith("Cartela"):
                rows.append((f"{o.member} — {o.kind}", f"{o.n_bolts} filas de Ø{o.bolt_size} {o.bolt_grade}, separación {us.q('L', o.bolt_s)}, "
                             f"cartela t = {us.q('L', o.plate_t)} ({o.plate_steel}), soldadura {us.q('L', o.weld_size)}"))
            else:
                rows.append((f"{o.member} — {o.kind}", ""))
        for x in nd.loads:
            rows.append((f"Carga «{x.case}» — {x.member}", f"N {us.fmt('F', x.N)}, Vy {us.fmt('F', x.Vy)}, Vz {us.fmt('F', x.Vz)} {us.F}; "
                         f"T {us.fmt('M', x.T)}, My {us.fmt('M', x.My)}, Mz {us.fmt('M', x.Mz)} {us.M}"))
        return rows

    def draw(self, fig, prj):
        draw_scheme(fig, self.spec(prj), self.TAB, prj.units())


MODULES = {CT_NODE: NodeModule(CT_NODE, "Conexión de nudo", "CN")}


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


def draw_scheme(fig, nd, title="", us=None):
    """Planta (X–Y) y elevacion (X–Z) de los miembros, con las cotas en las unidades del proyecto."""
    from matplotlib.patches import Polygon
    from matplotlib.ticker import FuncFormatter
    from . import assembly as AS
    fig.clf()
    axp = fig.add_subplot(2, 1, 1)
    axe = fig.add_subplot(2, 1, 2)
    fl = us.fl if us is not None else 1.0
    ul = us.L if us is not None else "in"
    mshape = AS.shape_of(nd.main_shape)
    A, msx, msy = AS.main_frame(nd)
    lneg, lpos = nd.lengths()
    if lneg + lpos < 1.0:
        lneg = lpos = 24.0
    items = [(nd.main_name, _silhouette(mshape, (0, 0, 0), msx, msy, A, -lneg, lpos), "#bdd7ee", "#1f3864", True)]
    ext = AS.outer_extent(mshape)
    for m in nd.members:
        shp = AS.shape_of(m.shape)
        dv = AS.member_dir(m)
        _, sx, sy = AS.member_frame(m)
        P0, o2 = AS.attach_point(nd, m, (A, msx, msy))
        d2 = (float(np.dot(dv, msx)), float(np.dot(dv, msy)))
        s_ex = AS.exit_dist(ext, o2, d2)
        Q = P0 + dv * (s_ex or 0.0)
        items.append((m.name, _silhouette(shp, Q + dv * max(m.gap, 0.0), sx, sy, dv, 0.0, max(m.L, 1.0)), "#9dc3e6", "#1f3864", False))
    allp = np.vstack([it[1] for it in items])
    fmt = FuncFormatter(lambda v, _p: f"{v / fl:g}")
    for ax, (i, j), nm, xl, yl in ((axp, (0, 1), "Planta (X–Y)", "X", "Y"), (axe, (0, 2), "Elevación (X–Z)", "X", "Z")):
        for name, P, fc, ec, is_main in items:
            hull = AS._hull([(float(p[i]), float(p[j])) for p in P])
            if len(hull) >= 3:
                ax.add_patch(Polygon(hull, closed=True, fc=fc, ec=ec, lw=0.9, alpha=0.9))
                # el nombre va en el extremo libre (el mas lejos del nudo): asi no se amontonan los textos sobre el nudo
                far = max(P, key=lambda p: math.hypot(float(p[i]), float(p[j])))
                tx, ty = float(far[i]), float(far[j])
                ax.annotate(name, (tx, ty), xytext=(3, 3), textcoords="offset points", fontsize=7.5, color="#10243f", weight="bold",
                            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
        ax.plot([0], [0], "o", ms=4, color="#c00000")
        pad = 0.08 * max(float(np.ptp(allp[:, i])), float(np.ptp(allp[:, j])), 1.0)
        ax.set_xlim(float(allp[:, i].min()) - pad, float(allp[:, i].max()) + pad)
        ax.set_ylim(float(allp[:, j].min()) - pad, float(allp[:, j].max()) + pad)
        ax.set_aspect("equal", adjustable="datalim")
        ax.xaxis.set_major_formatter(fmt)
        ax.yaxis.set_major_formatter(fmt)
        ax.set_title(nm, fontsize=9, loc="left")
        ax.set_xlabel(f"{xl}, {ul}", fontsize=7.5)
        ax.set_ylabel(f"{yl}, {ul}", fontsize=7.5)
        ax.tick_params(labelsize=7)
        ax.grid(True, color="#dddddd", lw=0.5)
    fig.suptitle(title or "Nudo", fontsize=10, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
