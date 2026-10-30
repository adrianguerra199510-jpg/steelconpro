# -*- coding: utf-8 -*-
"""Operaciones generales del nudo: placa (refuerzo, cartela o rigidizador), pernos y soldaduras entre elementos elegidos, y corte de elementos.

A diferencia de las operaciones de conexion (placa simple, doble angulo...), que arman un herraje completo contra el miembro principal, estas eligen
sobre que elementos actuan:

  · una PLACA se coloca sobre una cara de un elemento padre (un miembro, la placa base u otra placa creada antes): paralela a la cara (refuerzo o cartela)
    o perpendicular a ella (rigidizador), soldada o atornillada; la nueva placa es a su vez un elemento y puede ser el padre de otras operaciones
    (por ejemplo, una placa que rigidiza otra placa);
  · PERNOS: un grupo de pernos que atraviesa los elementos elegidos;
  · SOLDADURA de filete entre una placa y la cara de su padre (ademas de la que lleva la placa al crearla);
  · CORTE: recorte (cope) de los extremos de los miembros elegidos.

Un elemento tiene un nombre y caras; una operacion depende de los elementos que nombra, y se calcula despues de las operaciones que los crean.
"""
from __future__ import annotations
import math

import numpy as np

from .specs import (OP_PLATE, OP_BOLTS, OP_FILLET, OP_CUT, OP_BASE, OP_HOLE, OP_ANGLE, OP_TRIM, PLATE_ROLES, PLATE_ORIENTS, PLATE_SHAPES, ATTACHES, FACES_I, FACES_BOX,
                    FACES_PLATE, FACES_ANGLE, FACES_END, HOLE_SHAPES, WELD_MODES, Operation)

# ================================================================================================== valores por omision
_DEFAULTS = {
    OP_PLATE: dict(role=PLATE_ROLES[0], orient=PLATE_ORIENTS[0], shape=PLATE_SHAPES[0], attach=ATTACHES[0], pl_L=12.0, pl_W=6.0, pl_s=12.0, pl_u=0.0, pl_rot=0.0,
                   plate_t=0.375, weld_size=0.1875, rows=2, cols=2, bolt_s=3.0, bolt_g=3.0, bolt_size="3/4", bolt_grade="A325-N", weld_all=True),
    OP_BOLTS: dict(rows=2, cols=2, bolt_s=3.0, bolt_g=3.0, bolt_size="3/4", bolt_grade="A325-N", pl_s=12.0, pl_u=0.0),
    OP_FILLET: dict(weld_size=0.1875, weld_all=True),
    OP_CUT: dict(cope_top=2.0, cope_bot=0.0, cope_len=4.5, cut_at="Inicio"),
}
_ROLE_DEFAULTS = {
    "Refuerzo": dict(orient=PLATE_ORIENTS[0], shape=PLATE_SHAPES[0], pl_L=12.0, pl_W=6.0),
    "Cartela": dict(orient=PLATE_ORIENTS[0], shape=PLATE_SHAPES[2], pl_L=12.0, pl_W=10.0, plate_t=0.5),
    "Rigidizador": dict(orient=PLATE_ORIENTS[1], shape=PLATE_SHAPES[2], pl_L=6.0, pl_W=6.0, pl_clip=1.0, plate_t=0.375),
}


def defaults(kind: str, role: str = "") -> dict:
    d = dict(_DEFAULTS.get(kind, {}))
    if kind == OP_PLATE:
        d.update(_ROLE_DEFAULTS.get(role or d["role"], {}))
        d["role"] = role or d["role"]
    return d


# ================================================================================================== elementos y caras
class FaceFrame:
    """Cara plana de un elemento: punto de referencia `O` (en la cara, al inicio del elemento y al centro de su ancho), eje `A` a lo largo del elemento,
    `U` a lo ancho (U = N × A), normal exterior `N`, largo (`L`) y semiancho (`uh`) de la cara, y espesor del elemento en ese lugar (`wall`)."""

    def __init__(self, O, A, N, L, uh, wall):
        self.O, self.A, self.N = np.asarray(O, float), np.asarray(A, float), np.asarray(N, float)
        self.U = np.cross(self.N, self.A)
        self.L, self.uh, self.wall = float(L), float(uh), float(wall)

    def point(self, s, u=0.0, n=0.0):
        return self.O + self.A * s + self.U * u + self.N * n


def face_kind(shape) -> str:
    return "I" if shape.kind == "W" else "box"


def member_faces(shape, start, end, A, sx, sy) -> dict:
    """{nombre de la cara: FaceFrame} de un miembro."""
    start, A = np.asarray(start, float), np.asarray(A, float)
    L = float(np.linalg.norm(np.asarray(end, float) - start))
    sx, sy = np.asarray(sx, float), np.asarray(sy, float)
    d, bf = float(shape.d), float(shape.bf if shape.bf > 0 else shape.d)
    out = {}
    if face_kind(shape) == "I":
        tf, tw = float(shape.tf), float(shape.tw)
        out["Ala superior"] = FaceFrame(start + sy * d / 2.0, A, sy, L, bf / 2.0, tf)
        out["Ala inferior"] = FaceFrame(start - sy * d / 2.0, A, -sy, L, bf / 2.0, tf)
        out["Alma +"] = FaceFrame(start + sx * tw / 2.0, A, sx, L, (d - 2 * tf) / 2.0, tw)
        out["Alma −"] = FaceFrame(start - sx * tw / 2.0, A, -sx, L, (d - 2 * tf) / 2.0, tw)
    else:
        t = float(shape.tw if shape.tw > 0 else 0.5)
        uh_x = (d / 2.0) if not shape.is_round else 0.35 * d
        uh_y = (bf / 2.0) if not shape.is_round else 0.35 * d
        out["Cara +X"] = FaceFrame(start + sx * bf / 2.0, A, sx, L, uh_x, t)
        out["Cara −X"] = FaceFrame(start - sx * bf / 2.0, A, -sx, L, uh_x, t)
        out["Cara +Y"] = FaceFrame(start + sy * d / 2.0, A, sy, L, uh_y, t)
        out["Cara −Y"] = FaceFrame(start - sy * d / 2.0, A, -sy, L, uh_y, t)
    wall = float(shape.tf if face_kind(shape) == "I" else (shape.tw if shape.tw > 0 else 0.5))
    end = np.asarray(end, float)
    out[FACES_END[0]] = FaceFrame(start - sx * bf / 2.0, sx, -A, bf, d / 2.0, wall)       # cara del extremo (plano de la seccion), normal hacia afuera del miembro
    out[FACES_END[1]] = FaceFrame(end - sx * bf / 2.0, sx, A, bf, d / 2.0, wall)
    return out


def plate_faces(center, e1, e2, e3, L1, L2, t) -> dict:
    """Caras de una placa (e1 y e2 en su plano, e3 = normal): la `Cara +` y la `Cara −` (con A = e1 y N = ±e3).  `center` es el centro de la placa."""
    c = np.asarray(center, float)
    e1, e3 = np.asarray(e1, float), np.asarray(e3, float)
    return {"Cara +": FaceFrame(c + e3 * t / 2.0 - e1 * L1 / 2.0, e1, e3, L1, L2 / 2.0, t),
            "Cara −": FaceFrame(c - e3 * t / 2.0 - e1 * L1 / 2.0, e1, -e3, L1, L2 / 2.0, t)}


def face_names_of(shape) -> list:
    return FACES_I if face_kind(shape) == "I" else FACES_BOX


def elements(prj) -> dict:
    """Elementos a los que se puede hacer referencia, con sus caras: miembros (el principal primero), placas creadas por operaciones y la placa base."""
    from . import assembly as AS
    nd = prj.node
    out = [{"name": nd.main_name, "type": "miembro", "main": True, "label": f"{nd.main_name} ({nd.main_shape})",
            "faces": face_names_of(AS.shape_of(nd.main_shape))}]
    for m in nd.members:
        out.append({"name": m.name, "type": "miembro", "main": False, "label": f"{m.name} ({m.shape})", "faces": face_names_of(AS.shape_of(m.shape))})
    for i, o in enumerate(nd.operations):
        if o.makes_element:
            if o.kind == OP_ANGLE:
                out.append({"name": o.name, "type": "ángulo", "main": False, "op": i, "label": f"{o.name} (ángulo L{o.leg_a:g}×{o.leg_b:g}×{o.plate_t:g})", "faces": list(FACES_ANGLE)})
            else:
                out.append({"name": o.name, "type": "placa", "main": False, "op": i, "label": f"{o.name} (placa {o.plate_t:g} in)", "faces": list(FACES_PLATE)})
    if nd.base_op() is not None:
        out.append({"name": "Placa base", "type": "placa base", "main": False, "label": "Placa base", "faces": ["Cara superior", "Cara inferior"]})
    return {"elements": out}


def unique_plate_name(nd, base="P") -> str:
    used = set(nd.element_names())
    k = 1
    while f"{base}{k}" in used:
        k += 1
    return f"{base}{k}"


# ================================================================================================== orden de calculo
def ordered(nd) -> list:
    """Operaciones generales en un orden que respeta las dependencias (una placa despues de su padre).  -> [(indice, operacion)]"""
    pending = [(i, o) for i, o in enumerate(nd.operations) if o.kind in (OP_PLATE, OP_BOLTS, OP_FILLET, OP_CUT, OP_HOLE, OP_ANGLE, OP_TRIM)]
    known = set(nd.names()) | ({"Placa base"} if nd.base_op() is not None else set())
    done, out, guard = set(), [], 0
    while pending and guard < 200:
        guard += 1
        moved = False
        for item in list(pending):
            i, o = item
            need = {o.parent} - {""} | set(o.targets or [])
            if o.kind == OP_CUT:
                need = set()                                       # el corte solo mira a los miembros
            if need <= (known | done):
                out.append(item)
                pending.remove(item)
                if o.makes_element:
                    done.add(o.name)
                moved = True
        if not moved:
            break
    return out, pending                                            # pending: las que dependen de algo que no existe


# ================================================================================================== geometria (ver plates.py)


def bolt_grid(rows, cols, s, g):
    """Posiciones (a lo largo, a lo ancho) de una cuadricula de pernos centrada."""
    return [((i - (rows - 1) / 2.0) * s, (j - (cols - 1) / 2.0) * g) for i in range(max(rows, 1)) for j in range(max(cols, 1))]


# ================================================================================================== verificaciones
def min_fillet(t_thick: float) -> float:
    """Cateto minimo del filete segun el espesor de la parte mas delgada que une (AISC 360-22, Tabla J2.4), in."""
    if t_thick <= 0.25:
        return 0.125
    if t_thick <= 0.5:
        return 0.1875
    if t_thick <= 0.75:
        return 0.25
    return 0.3125


def max_fillet(t_edge: float) -> float:
    """Cateto maximo en el borde de una placa de espesor t (AISC J2.2b): t si t < 1/4 in, t − 1/16 in si no."""
    return t_edge if t_edge < 0.25 else t_edge - 0.0625


# ================================================================================================== armado del modelo 3D
def _bolt_layers(reg, names, first_wall):
    """[(nombre de la pieza, espesor)] de las capas que atraviesan los pernos, de la cara hacia adentro."""
    out = []
    for nm in names:
        e = reg.get(nm)
        if e is None:
            continue
        out.append((nm, float(e.get("t", first_wall))))
    return out


def _mkweld(Weld, name, A, B, ln, size, group, kind):
    p0, p1, nA, nB = ln[0], ln[1], ln[2], ln[3]
    w = Weld(name, A, B, tuple(map(float, p0)), tuple(map(float, p1)), tuple(map(float, nA)), tuple(map(float, nB)), float(size), 70.0, group)
    w.kind = kind
    return w


def _shape_outline(shp):
    """Contorno exterior de la seccion de un miembro en (u = ancho, v = peralte), centrado: lista de puntos y grupos de segmentos."""
    from .fem.model3d import i_section
    from . import geom2d as G
    if shp.is_round:
        return G.circle_poly(0.0, 0.0, shp.d / 2.0, 36), [list(range(36))]
    if shp.kind == "W":
        pts = i_section(shp)
        return pts, [[k] for k in range(len(pts))]
    d, bf = shp.d, (shp.bf if shp.bf > 0 else shp.d)
    return [(-bf / 2, -d / 2), (bf / 2, -d / 2), (bf / 2, d / 2), (-bf / 2, d / 2)], [[0], [1], [2], [3]]


def member_contour_lines(frame, ff, edges=None):
    """Cordon alrededor de la seccion de un miembro en su extremo apoyado en la cara `ff`: [(p0, p1, nA, nB, segmento)]."""
    start, end, d, sx, sy, shp = frame
    n2, p2 = np.asarray(ff.N, float), np.asarray(ff.O, float)
    start, end, d, sx, sy = (np.asarray(x, float) for x in (start, end, d, sx, sy))
    ds, de = abs(float(np.dot(start - p2, n2))), abs(float(np.dot(end - p2, n2)))
    c, other = (start, end) if ds <= de else (end, start)
    den = float(np.dot(n2, d))
    if abs(den) < 1e-6:
        return []
    Q = c + d * (float(np.dot(p2 - c, n2)) / den)
    sgn = 1.0 if float(np.dot(other - Q, n2)) >= 0 else -1.0
    nB = n2 * sgn
    poly, groups = _shape_outline(shp)
    out = []
    n = len(poly)
    for gi, g in enumerate(groups):
        if edges is not None and gi not in edges:
            continue
        for k in g:
            a, b = poly[k % n], poly[(k + 1) % n]
            P0, P1 = Q + sx * a[0] + sy * a[1], Q + sx * b[0] + sy * b[1]
            t = P1 - P0
            ln = float(np.linalg.norm(t))
            if ln < 1e-9:
                continue
            nA3 = sx * (b[1] - a[1]) - sy * (b[0] - a[0])                   # normal hacia afuera de un contorno CCW (en el plano de la seccion)
            nA3 = nA3 / max(float(np.linalg.norm(nA3)), 1e-12)
            out.append((P0, P1, nA3, nB, gi))
    return out


def _punch_all(mdl):
    """Agujeros de todos los pernos en las piezas que atraviesan."""
    from . import plates as PL
    parts = {p.name: p for p in mdl.parts}
    for b in mdl.bolts:
        ax = np.asarray(b.axis, float)
        for (pn, s0, s1) in b.grip:
            part = parts.get(pn)
            if part is not None:
                PL.punch(part, np.asarray(b.p, float), ax, PL.circle_fn(float(b.dh), 20))


def build_generic(mdl, nd, reg: dict, hw: bool = True):
    """Arma en `mdl` las placas, angulos, pernos, soldaduras, huecos y cortes de las operaciones generales.  `reg` = {nombre: {type, faces, part, t, Fy, Fu}} de
    los elementos ya colocados (miembros y placa base); se completa con las placas que se van creando.  Devuelve la lista de entradas
    [{op, index, ok, note, plate, welds_len, bolts, layers, ff}] que usan las verificaciones."""
    from .assembly import _steel, _bolt
    from .common import bolt_db
    from .fem.model3d import Part, Weld, Prism
    from . import plates as PL
    entries = []
    order, orphans = ordered(nd)
    for i, o in orphans:
        mdl.notes.append(f"Operación {i + 1} «{o.kind}»: depende de un elemento que no existe ({o.parent or ', '.join(o.targets)}).")
    for i, o in order:
        ent = {"op": o, "index": i, "ok": False}
        entries.append(ent)
        if o.kind in (OP_CUT, OP_TRIM):
            ent["ok"] = True
            continue
        parent = reg.get(o.parent)
        if o.kind in (OP_PLATE, OP_BOLTS, OP_ANGLE, OP_HOLE) and (parent is None or o.face not in parent["faces"]):
            mdl.notes.append(f"Operación {i + 1} «{o.kind}»: elija el elemento y la cara a la que se une (cara «{o.face}» de «{o.parent}»).")
            continue
        db = bolt_db(o.bolt_size)
        wtype = o.weld_type
        if o.kind == OP_PLATE:
            ff = parent["faces"][o.face]
            geo = PL.make_geo(o, ff)
            PL.add_opening(geo, o, reg)
            pr, e1, e2, e3, centre = geo["prism"], geo["e1"], geo["e2"], geo["e3"], geo["centre"]
            spec = {"L1": o.pl_L, "L2": (o.pl_L if o.shape == PLATE_SHAPES[3] else o.pl_W), "t": geo["t"], "perp": geo["perp"]}
            Fy, Fu = _steel(o.plate_steel, True)
            nm = o.name
            if hw:
                mdl.parts.append(Part(nm, "stiff" if o.role == "Rigidizador" else "plate", f"{o.role} PL {spec['t']:g}", Fy, Fu, [pr], t=spec["t"]))
                mdl.parts[-1].owner = f"op:{i}"
            ent.update(ok=True, ff=ff, spec=spec, parent=parent, plate_name=nm, e=(e1, e2, e3), centre=centre, geo=geo)
            reg[nm] = {"type": "plate", "faces": plate_faces(centre, e1, e2, e3, spec["L1"], spec["L2"], spec["t"]), "part": nm, "t": spec["t"], "Fy": Fy, "Fu": Fu,
                       "geo": geo, "parent": o.parent, "parent_face": o.face, "parent_part": parent["part"]}
            edges = None if o.weld_all else set(o.weld_edges)
            lines = PL.weld_lines(geo, ff, edges, o.weld_a, o.weld_len)
            reg[nm]["lines"] = lines
            ent["weld_len"] = sum(float(np.linalg.norm(np.asarray(l[1]) - np.asarray(l[0]))) for l in lines)
            if (o.attach == ATTACHES[0] or spec["perp"]) and hw:
                for k, ln in enumerate(lines):
                    mdl.welds.append(_mkweld(Weld, f"{nm}-W{k + 1}", nm, parent["part"], ln, o.weld_size, nm, wtype))
            if o.attach == ATTACHES[1] and not spec["perp"] and hw:
                pts = bolt_grid(o.rows, o.cols, o.bolt_s, o.bolt_g)
                t = spec["t"]
                wall = parent["faces"][o.face].wall
                grade = o.bolt_grade
                for k, (a, b) in enumerate(pts):
                    p = ff.point(o.pl_s, o.pl_u) + e1 * a + e2 * b + ff.N * t
                    mdl.bolts.append(_bolt(f"{nm}-B{k + 1}", p, -ff.N, db, 0.0, t + wall, [(nm, 0.0, t), (parent["part"], t, t + wall)], grade))
                ent["bolts"] = len(pts)
            elif o.attach == ATTACHES[1] and spec["perp"]:
                mdl.notes.append(f"Operación {i + 1}: una placa perpendicular a la cara (rigidizador) se suelda; se dibuja la soldadura.")
        elif o.kind == OP_ANGLE:
            ff = parent["faces"][o.face]
            t = max(float(o.plate_t), 0.0625)
            a_, b_, L = float(o.leg_a), float(o.leg_b), float(o.pl_L)
            side = 1.0 if o.leg_side >= 0 else -1.0
            s0 = o.pl_s - L / 2.0
            if side > 0:
                poly = [(-a_ / 2, 0.0), (a_ / 2, 0.0), (a_ / 2, b_), (a_ / 2 - t, b_), (a_ / 2 - t, t), (-a_ / 2, t)]
            else:
                poly = [(a_ / 2, 0.0), (-a_ / 2, 0.0), (-a_ / 2, b_), (-a_ / 2 + t, b_), (-a_ / 2 + t, t), (a_ / 2, t)]
            o3 = ff.O + ff.A * s0 + ff.U * o.pl_u
            from .assembly import _plate_prism
            pr = _plate_prism(poly, o3, ff.U, ff.N, 0.0, L)
            Fy, Fu = _steel(o.plate_steel, True)
            nm = o.name
            if hw:
                mdl.parts.append(Part(nm, "angle", f"Ángulo L{a_:g}×{b_:g}×{t:g} × {L:g}", Fy, Fu, [pr], t=t))
                mdl.parts[-1].owner = f"op:{i}"
            Op = o3 - ff.A * s0 * 0
            fA = ff.A
            top = FaceFrame(ff.O + ff.U * o.pl_u + ff.N * t, fA, ff.N, L, a_ / 2.0, t)
            top.O = ff.O + ff.A * s0 + ff.U * o.pl_u + ff.N * t
            Nin, Nout = -side * ff.U, side * ff.U
            inner = FaceFrame(ff.O + ff.A * s0 + ff.U * (o.pl_u + side * (a_ / 2 - t)) + ff.N * ((t + b_) / 2.0), fA, Nin, L, (b_ - t) / 2.0, t)
            outer = FaceFrame(ff.O + ff.A * s0 + ff.U * (o.pl_u + side * a_ / 2) + ff.N * (b_ / 2.0), fA, Nout, L, b_ / 2.0, t)
            reg[nm] = {"type": "angulo", "faces": {FACES_ANGLE[0]: top, FACES_ANGLE[1]: inner, FACES_ANGLE[2]: outer}, "part": nm, "t": t, "Fy": Fy, "Fu": Fu,
                       "parent": o.parent, "parent_face": o.face, "parent_part": parent["part"], "lines": None}
            spec = {"L1": L, "L2": a_, "t": t, "perp": False}
            ent.update(ok=True, ff=ff, spec=spec, parent=parent, plate_name=nm, e=(fA, ff.U, ff.N), centre=o3)
            # unión: soldada (todo el contorno de la pierna sobre la cara) o atornillada (pernos a traves de la pierna)
            lines = []
            xs = [(-a_ / 2.0, 1), (a_ / 2.0, 2)]
            for u_edge, nu in ((-a_ / 2.0, -1.0), (a_ / 2.0, 1.0)):
                for sA, sgnA in ((s0, -1.0), (s0 + L, 1.0)):
                    pass
            P = lambda s_, u_, n_: ff.O + ff.A * s_ + ff.U * (o.pl_u + u_) + ff.N * n_     # noqa: E731
            lines = [(P(s0, -a_ / 2, 0), P(s0 + L, -a_ / 2, 0), -ff.U, ff.N), (P(s0, a_ / 2, 0), P(s0 + L, a_ / 2, 0), ff.U, ff.N),
                     (P(s0, -a_ / 2, 0), P(s0, a_ / 2, 0), -ff.A, ff.N), (P(s0 + L, -a_ / 2, 0), P(s0 + L, a_ / 2, 0), ff.A, ff.N)]
            reg[nm]["lines"] = [(l[0], l[1], l[2], l[3], k) for k, l in enumerate(lines)]
            ent["weld_len"] = sum(float(np.linalg.norm(np.asarray(l[1]) - np.asarray(l[0]))) for l in lines)
            if o.attach == ATTACHES[0] and hw:
                for k, ln in enumerate(lines):
                    mdl.welds.append(_mkweld(Weld, f"{nm}-W{k + 1}", nm, parent["part"], ln, o.weld_size, nm, wtype))
            elif hw:
                pts = bolt_grid(o.rows, o.cols, o.bolt_s, o.bolt_g)
                wall = parent["faces"][o.face].wall
                for k, (aa, bb) in enumerate(pts):
                    p = ff.O + ff.A * (o.pl_s + aa) + ff.U * (o.pl_u + bb) + ff.N * t
                    mdl.bolts.append(_bolt(f"{nm}-B{k + 1}", p, -ff.N, db, 0.0, t + wall, [(nm, 0.0, t), (parent["part"], t, t + wall)], o.bolt_grade))
                ent["bolts"] = len(pts)
        elif o.kind == OP_BOLTS:
            ff = parent["faces"][o.face]
            names = [o.parent] + [x for x in (o.targets or []) if x in reg]
            layers = _bolt_layers(reg, names, ff.wall)
            layers[0] = (layers[0][0], ff.wall) if reg[o.parent]["type"] == "miembro" else layers[0]
            total = sum(t for _n, t in layers)
            pts = bolt_grid(o.rows, o.cols, o.bolt_s, o.bolt_g)
            grip, s0 = [], 0.0
            for nm_, t_ in layers:
                grip.append((reg[nm_]["part"], s0, s0 + t_))
                s0 += t_
            if hw:
                for k, (a, b) in enumerate(pts):
                    p = ff.point(o.pl_s, o.pl_u) + ff.A * a + ff.U * b
                    mdl.bolts.append(_bolt(f"{o.name or 'B' + str(i + 1)}-B{k + 1}", p, -ff.N, db, 0.0, total, grip, o.bolt_grade))
            ent.update(ok=True, ff=ff, layers=layers, bolts=len(pts), parent=parent)
        elif o.kind == OP_HOLE:
            ff = parent["faces"][o.face]
            part = next((p for p in mdl.parts if p.name == parent["part"]), None)
            pts = bolt_grid(o.rows, o.cols, o.bolt_s, o.bolt_g)
            if o.hole_shape == HOLE_SHAPES[1]:
                fn = PL.slot_fn(float(o.hole_L), float(o.hole_D), float(o.hole_rot), ff.A)
            elif o.hole_shape == HOLE_SHAPES[2]:
                fn = PL.rect_fn(float(o.hole_L), float(o.hole_W), float(o.hole_rot), ff.A)
            else:
                fn = PL.circle_fn(float(o.hole_D), 24)
            n_ok = 0
            if part is not None:
                for a, b in pts:
                    p = ff.point(o.pl_s, o.pl_u) + ff.A * a + ff.U * b
                    n_ok += bool(PL.punch(part, p, -ff.N, fn))
            if not n_ok:
                mdl.notes.append(f"Operación {i + 1} «{o.kind}»: ningún hueco cae dentro del elemento «{o.parent}» (revise la posición).")
            ent.update(ok=True, holes=n_ok)
        elif o.kind == OP_FILLET:
            ents = []
            if o.weld_mode == WELD_MODES[1]:                                           # contorno de un miembro contra una cara
                tg = (o.targets or [""])[0]
                e = reg.get(tg)
                fr = e.get("frame_full") if e else None
                par = reg.get(o.parent)
                if fr is None or par is None or o.face not in par["faces"]:
                    mdl.notes.append(f"Operación {i + 1}: elija el miembro y la cara (elemento y cara) donde se suelda su contorno.")
                else:
                    lines = member_contour_lines(fr, par["faces"][o.face], None if o.weld_all else set(o.weld_edges))
                    for k, ln in enumerate(lines):
                        if hw:
                            mdl.welds.append(_mkweld(Weld, f"{tg}-S{i + 1}.{k + 1}", e["part"], par["part"], ln, o.weld_size, f"S{i + 1}", wtype))
                        ents.append(float(np.linalg.norm(np.asarray(ln[1]) - np.asarray(ln[0]))))
                    ent.update(ok=bool(ents), weld_len=sum(ents), plates=[tg], t_other=par.get("t", 0.375))
            else:
                for tg in (o.targets or []):
                    e = reg.get(tg)
                    if e is None or e.get("geo") is None and e.get("lines") is None:
                        mdl.notes.append(f"Operación {i + 1} «{o.kind}»: «{tg}» no es una placa de otra operación; use «Contorno del miembro» para soldar miembros.")
                        continue
                    other = reg.get(o.parent) if o.parent else None
                    if other is not None and o.face in other["faces"] and e.get("geo") is not None:
                        ffx = other["faces"][o.face]
                        lines = PL.weld_lines(e["geo"], ffx, None if o.weld_all else set(o.weld_edges), o.weld_a, o.weld_len)
                        partB = other["part"]
                    else:
                        lines = e["lines"] or []
                        if not o.weld_all:
                            lines = [l for l in lines if (len(l) < 5 or l[4] in set(o.weld_edges))]
                        partB = e["parent_part"]
                    for k, ln in enumerate(lines):
                        if hw:
                            mdl.welds.append(_mkweld(Weld, f"{tg}-S{i + 1}.{k + 1}", tg, partB, ln, o.weld_size, f"S{i + 1}", wtype))
                        ents.append(float(np.linalg.norm(np.asarray(ln[1]) - np.asarray(ln[0]))))
                ent.update(ok=bool(ents), weld_len=sum(ents), plates=[t for t in (o.targets or []) if t in reg])
    if hw:
        _punch_all(mdl)
    return entries


# ================================================================================================== verificaciones de las operaciones generales
def _chk(ck, grp, key, title, dem, cap, unit, ref, note="", skip=False):
    from ..design import Check
    c = Check(key, title, dem, cap, unit, ref, note, skip)
    c.group = grp
    ck.append(c)
    return c


def _bolt_checks(ck, grp, key, o, n, layers, edge, spacing_ok_rows, V, T, steels):
    """Verificaciones de un grupo de `n` pernos: separacion, distancia al borde, cortante, traccion, interaccion J3.7 y aplastamiento de cada capa.
    layers = [(nombre, espesor, Fu)]; edge = distancia minima al borde de las capas (in) o None."""
    from .common import (bolt_db, bolt_shear_rn, bolt_tension_rn, bolt_tension_shear, edge_min, hole_std, PHI_BOLT, FNT, FNV)
    db = bolt_db(o.bolt_size)
    Ab = math.pi * db ** 2 / 4.0
    grade = o.bolt_grade if o.bolt_grade in FNV else "A325-N"
    planes = max(len(layers) - 1, 1)
    s_min = min([x for x, on in ((o.bolt_s, o.rows > 1), (o.bolt_g, o.cols > 1)) if on], default=None)
    if s_min is not None:
        _chk(ck, grp, f"{key}_sep", "Separación de los pernos  s ≥ 2-2/3·db", (8.0 / 3.0) * db, s_min, "in", "AISC J3.3", "3·db es lo preferible")
    if edge is not None:
        _chk(ck, grp, f"{key}_edge", "Distancia del centro de un perno al borde", edge_min(db), edge, "in", "AISC Tabla J3.4")
    nb = max(int(n), 1)
    _chk(ck, grp, f"{key}_v", f"Pernos — cortante ({nb} × Ø{o.bolt_size} {grade}, {planes} plano{'s' if planes > 1 else ''} de corte)", V,
         nb * PHI_BOLT * bolt_shear_rn(db, grade) * planes, "kip", "AISC J3.6", "φ = 0.75; la fuerza de diseño se ingresa en la operación")
    _chk(ck, grp, f"{key}_t", "Pernos — tracción", T, nb * PHI_BOLT * bolt_tension_rn(db, grade), "kip", "AISC J3.6")
    if V > 0 and T > 0:
        frv = V / (nb * Ab * planes)
        _chk(ck, grp, f"{key}_int", "Pernos — interacción tracción-cortante", T, nb * bolt_tension_shear(db, grade, frv), "kip", "AISC J3.7")
    Lc_s = (s_min - hole_std(db)) if s_min is not None else None
    for nm, t, Fu in layers:
        Lc = min([x for x in ((edge - hole_std(db) / 2.0) if edge is not None else None, Lc_s) if x is not None] or [1.5 * db])
        rn = min(1.2 * max(Lc, 0.0) * t * Fu, 2.4 * db * t * Fu)
        _chk(ck, grp, f"{key}_br_{nm}", f"Aplastamiento y desgarramiento en «{nm}» (t = {t:g} in)", V, nb * PHI_BOLT * rn, "kip", "AISC J3.10")


def _weld_checks(ck, grp, key, w, Lw, V, T, t_plate, t_base, FEXX=70.0):
    from .common import PHI_WELD
    if Lw <= 1e-9:
        return
    _chk(ck, grp, f"{key}_wmin", "Cateto mínimo del filete", min_fillet(min(t_plate, t_base)), w, "in", "AISC Tabla J2.4")
    _chk(ck, grp, f"{key}_wmax", "Cateto máximo del filete en el borde de la placa", w, max(max_fillet(t_plate), 1e-6), "in", "AISC J2.2b")
    cap = PHI_WELD * 0.60 * FEXX * 0.707 * w * Lw
    _chk(ck, grp, f"{key}_w", f"Soldadura — resistencia ({Lw:g} in de filete {w:g} in)", math.hypot(V, T), cap, "kip", "AISC J2.4", "φ = 0.75; Fnw = 0.60·FEXX; sin el aumento por dirección de la carga")


def add_checks(prj, nd, R, rec, mdl):
    """Verificaciones de las operaciones generales (con las fuerzas de diseño que se ingresan en cada una).  `mdl` = modelo 3D ya armado (tiene los elementos)."""
    from .common import bolt_db
    from .assembly import _steel
    entries = getattr(mdl, "generic", [])
    for ent in entries:
        o, i = ent["op"], ent["index"]
        grp = f"{i + 1}. {o.kind} — {o.name or o.parent or o.member}"
        key = f"g{i}"
        if o.kind == OP_CUT:
            for tg in ([o.member] if not o.targets else o.targets):
                _chk(R.checks, grp, f"{key}_cut_{tg}", f"Recorte de «{tg}»: pandeo local del alma y flexión del miembro recortado — NO EVALUADO", 0.0, 1.0, "-",
                     "AISC Manual Parte 9", "El corte debe revisarse aparte (los herrajes ya consideran la geometría recortada).", skip=True)
            continue
        if o.kind in (OP_TRIM, OP_HOLE) and ent.get("ok"):
            continue                                                   # solo geometría: no hay nada que verificar
        if not ent.get("ok"):
            _chk(R.checks, grp, f"{key}_na", "La operación no se pudo armar (falta el elemento o la cara) — NO EVALUADO", 0.0, 1.0, "-", "", "Revise el elemento y la cara en la operación.", skip=True)
            continue
        V, T = float(o.force_V), float(o.force_T)
        if o.kind == OP_PLATE:
            spec, parent = ent["spec"], ent["parent"]
            t = spec["t"]
            Fy, Fu = _steel(o.plate_steel, True)
            width = spec["L2"] if not spec["perp"] else spec["L1"]
            Ag = width * t
            dh = bolt_db(o.bolt_size) + 0.125
            nh = o.cols if (o.attach == ATTACHES[1] and not spec["perp"]) else 0
            Ae = max(width - nh * dh, 0.0) * t
            if rec is not None:
                rec.section(f"OPERACION {i + 1}: {o.kind.upper()} — {o.name}")
                rec.text(f"{o.role} {spec['L1']:g} × {spec['L2']:g} × {t:g} in sobre «{o.parent}» ({o.face}); {o.attach.lower()}.")
            _chk(R.checks, grp, f"{key}_ty", "Placa — fluencia en tracción (sección bruta)", T, 0.90 * Fy * Ag, "kip", "AISC J4.1(a)", "φ = 0.90")
            _chk(R.checks, grp, f"{key}_tr", "Placa — rotura en tracción (sección neta)", T, 0.75 * Fu * Ae, "kip", "AISC J4.1(b)", "φ = 0.75")
            _chk(R.checks, grp, f"{key}_vy", "Placa — fluencia por cortante", V, 1.00 * 0.60 * Fy * spec["L1"] * t, "kip", "AISC J4.2(a)", "φ = 1.00")
            if o.role == "Rigidizador":
                lim = 0.56 * math.sqrt(29000.0 / Fy)
                _chk(R.checks, grp, f"{key}_slend", "Rigidizador — esbeltez del borde libre  h/t ≤ 0.56·√(E/Fy)", spec["L2"] / t, lim, "-", "AISC Tabla B4.1a, caso 1")
            ent_weld = o.attach == ATTACHES[0] or spec["perp"]
            if ent_weld:
                _weld_checks(R.checks, grp, key, float(o.weld_size), ent.get("weld_len", 0.0), V, T, t, parent["faces"][o.face].wall if o.face in parent["faces"] else t)
            else:
                ff = ent["ff"]
                edge_a = spec["L1"] / 2.0 - (o.rows - 1) * o.bolt_s / 2.0
                edge_b = spec["L2"] / 2.0 - (o.cols - 1) * o.bolt_g / 2.0
                edge = min(edge_a, edge_b)
                Fu_p = parent.get("Fu", Fu)
                _bolt_checks(R.checks, grp, key, o, o.rows * o.cols, [(o.name, t, Fu), (o.parent, ff.wall, Fu_p)], edge, True, V, T, None)
        elif o.kind == OP_ANGLE:
            spec, parent = ent["spec"], ent["parent"]
            t = spec["t"]
            Fy, Fu = _steel(o.plate_steel, True)
            Ag = (o.leg_a + o.leg_b - t) * t
            nh = o.cols if o.attach == ATTACHES[1] else 0
            Ae = Ag - nh * (bolt_db(o.bolt_size) + 0.125) * t
            if rec is not None:
                rec.section(f"OPERACION {i + 1}: {o.kind.upper()} — {o.name}")
                rec.text(f"Ángulo L{o.leg_a:g}×{o.leg_b:g}×{t:g} × {o.pl_L:g} in sobre «{o.parent}» ({o.face}); {o.attach.lower()}.")
            _chk(R.checks, grp, f"{key}_ty", "Ángulo — fluencia en tracción (sección bruta)", T, 0.90 * Fy * Ag, "kip", "AISC J4.1(a)", "φ = 0.90")
            _chk(R.checks, grp, f"{key}_tr", "Ángulo — rotura en tracción (sección neta)", T, 0.75 * Fu * Ae, "kip", "AISC J4.1(b)", "φ = 0.75")
            _chk(R.checks, grp, f"{key}_vy", "Ángulo — fluencia por cortante", V, 1.00 * 0.60 * Fy * o.pl_L * t, "kip", "AISC J4.2(a)", "φ = 1.00")
            if o.attach == ATTACHES[0]:
                _weld_checks(R.checks, grp, key, float(o.weld_size), ent.get("weld_len", 0.0), V, T, t, parent["faces"][o.face].wall if o.face in parent["faces"] else t)
            else:
                ff = ent["ff"]
                edge = min(o.pl_L / 2.0 - (o.rows - 1) * o.bolt_s / 2.0, o.leg_a / 2.0 - (o.cols - 1) * o.bolt_g / 2.0)
                _bolt_checks(R.checks, grp, key, o, o.rows * o.cols, [(o.name, t, Fu), (o.parent, ff.wall, parent.get("Fu", Fu))], edge, True, V, T, None)
        elif o.kind == OP_BOLTS:
            ff = ent["ff"]
            layers = [(nm, t, ent["parent"].get("Fu", 65.0) if k == 0 else 65.0) for k, (nm, t) in enumerate(ent["layers"])]
            edge_a = min(o.pl_s - (o.rows - 1) * o.bolt_s / 2.0, ff.L - o.pl_s - (o.rows - 1) * o.bolt_s / 2.0)
            edge_b = ff.uh - abs(o.pl_u) - (o.cols - 1) * o.bolt_g / 2.0
            if rec is not None:
                rec.section(f"OPERACION {i + 1}: {o.kind.upper()}")
                rec.text(f"{o.rows * o.cols} pernos Ø{o.bolt_size} {o.bolt_grade} desde la cara «{o.face}» de «{o.parent}» a través de {', '.join(n for n, _t in ent['layers'])}.")
            _bolt_checks(R.checks, grp, key, o, o.rows * o.cols, layers, min(edge_a, edge_b), True, V, T, None)
        elif o.kind == OP_FILLET:
            for tg in ent.get("plates", []):
                e = mdl.elems.get(tg, {})
                _weld_checks(R.checks, grp, f"{key}_{tg}", float(o.weld_size), ent.get("weld_len", 0.0), V, T, e.get("t", 0.375), 0.375)
            if not ent.get("plates"):
                _chk(R.checks, grp, f"{key}_na", "Elija las placas que se sueldan — NO EVALUADO", 0.0, 1.0, "-", "", skip=True)


# ================================================================================================== edicion de la lista de operaciones
def add_operation(nd, kind: str, **kw) -> Operation:
    """Agrega una operacion con sus valores tipicos.  Las placas reciben nombre; una placa base reemplaza a la anterior; una conexion de miembro reemplaza a
    la anterior del mismo miembro."""
    from .specs import GENERIC_OPS
    d = defaults(kind, kw.get("role", ""))
    d.update(kw)
    o = Operation(kind=kind, **d)
    if kind in (OP_PLATE, OP_BOLTS, OP_FILLET, OP_HOLE, OP_ANGLE, OP_TRIM) and "member" not in kw:
        o.member = ""                                    # estas operaciones se refieren a elementos por `parent` y `targets`, no a un miembro
    if kind == OP_BASE and "member" not in kw:
        o.member = nd.main_name                          # la placa base va, por defecto, en el extremo del miembro principal
    if kind in (OP_PLATE, OP_ANGLE) and not o.name:
        o.name = unique_plate_name(nd, "P" if kind == OP_PLATE else "A")
    if kind in (OP_PLATE, OP_ANGLE, OP_HOLE) and not o.parent:
        o.parent = nd.main_name
    if kind in (OP_PLATE, OP_ANGLE, OP_HOLE) and not o.face:
        from . import assembly as AS
        names = elements({"node": nd} if False else _Prj(nd))["elements"]
        e = next((e for e in names if e["name"] == o.parent), None)
        o.face = e["faces"][0] if e else ""
    if kind == OP_BOLTS and not o.parent:
        o.parent = nd.main_name
        o.face = o.face or "Ala superior"
    if kind in (OP_BOLTS, OP_HOLE, OP_ANGLE) and "pl_s" not in kw:
        pp = next((x for x in nd.operations if x.makes_element and x.name == o.parent), None)
        if pp is not None:
            o.pl_s, o.pl_u = pp.pl_L / 2.0, 0.0               # sobre una placa: en su centro
    if o.is_connection:
        nd.operations = [x for x in nd.operations if not (x.member == o.member and x.is_connection)]
    if kind == OP_BASE:
        nd.operations = [x for x in nd.operations if x.kind != OP_BASE]
    nd.operations.append(o)
    return o


class _Prj:
    """Envoltura minima para llamar a `elements` solo con el nudo."""
    def __init__(self, nd):
        self.node = nd


def delete_operation(nd, index: int) -> list:
    """Quita la operacion `index` y, en cascada, las que dependen del elemento que ella crea.  Devuelve la lista de operaciones quitadas (la primera es la pedida)."""
    if not (0 <= index < len(nd.operations)):
        return []
    removed = [nd.operations[index]]
    queue = [nd.operations[index]]
    while queue:
        o = queue.pop()
        if not o.makes_element:
            continue
        for i in nd.dependents(o.name):
            dep = nd.operations[i]
            if all(dep is not r for r in removed):
                removed.append(dep)
                queue.append(dep)
    nd.operations = [o for o in nd.operations if all(o is not r for r in removed)]
    return removed
