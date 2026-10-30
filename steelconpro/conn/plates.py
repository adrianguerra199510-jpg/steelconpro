# -*- coding: utf-8 -*-
"""Geometria de las placas y de lo que se les hace: contornos (rectangulo, triangulo, esquina recortada, circulo, trapecio, ranura, poligono libre),
aberturas, agujeros (pernos y huecos), y cordones de soldadura por bordes.

Una placa se define en su sistema local (u, v) y se extruye `t` a lo largo de w.  `geo` (diccionario) guarda todo lo necesario para ubicar puntos
en 3D, elegir bordes y trazar cordones:

    poly      contorno CCW en (u, v)            groups   lista de grupos de segmentos = «bordes» que el usuario elige (segmento k = poly[k] -> poly[k+1])
    o, e1, e2, e3   origen y ejes del sistema local de la placa (e3 = e1 × e2) y w0 = 0 ... t
"""
from __future__ import annotations
import math

import numpy as np

from . import geom2d as G
from .specs import PLATE_SHAPES, PLATE_ORIENTS, OPENINGS, HOLE_SHAPES

SH = {n: i for i, n in enumerate(PLATE_SHAPES)}


def _ccw_groups(poly, groups):
    """Orienta el contorno CCW; si hay que invertirlo, los grupos de segmentos se reasignan."""
    if G.area(poly) >= 0:
        return list(poly), groups
    n = len(poly)
    rev = list(reversed(poly))
    # el segmento k del original (k -> k+1) pasa a ser el segmento n-2-k del invertido
    new = [[(n - 2 - k) % n for k in g] for g in groups]
    return rev, new


def outline(op, perp: bool):
    """(contorno, grupos de segmentos) de la placa de la operacion `op`.  Paralela: centrado en (0, 0).  Perpendicular: base en v = 0, altura hacia +v."""
    L1, L2 = float(op.pl_L), float(op.pl_W)
    shape = op.shape
    if shape == PLATE_SHAPES[0] or shape not in PLATE_SHAPES:
        poly = [(-L1 / 2, 0.0), (L1 / 2, 0.0), (L1 / 2, L2), (-L1 / 2, L2)] if perp else [(-L1 / 2, -L2 / 2), (L1 / 2, -L2 / 2), (L1 / 2, L2 / 2), (-L1 / 2, L2 / 2)]
        return poly, [[0], [1], [2], [3]]
    if shape == PLATE_SHAPES[1]:
        poly = [(-L1 / 2, 0.0), (L1 / 2, 0.0), (-L1 / 2, L2)] if perp else [(-L1 / 2, -L2 / 2), (L1 / 2, -L2 / 2), (-L1 / 2, L2 / 2)]
        return poly, [[0], [1], [2]]
    if shape == PLATE_SHAPES[2]:
        c = min(float(op.pl_clip), 0.45 * min(L1, L2))
        y0, y1 = (0.0, L2) if perp else (-L2 / 2, L2 / 2)
        x0, x1 = -L1 / 2, L1 / 2
        if c <= 1e-6:
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [[0], [1], [2], [3]]
        if perp:
            poly = [(x0, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c)]
            return poly, [[k] for k in range(6)]
        poly = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]
        return poly, [[k] for k in range(8)]
    if shape == PLATE_SHAPES[3]:                                          # circular: diametro = L1
        cy = L1 / 2 if perp else 0.0
        poly = G.circle_poly(0.0, cy, L1 / 2.0, 48, start=-math.pi / 2)
        return poly, [list(range(48))]
    if shape == PLATE_SHAPES[4]:                                          # trapecio: base L1, altura L2, ancho superior pl_L2
        Lt = float(op.pl_L2) if op.pl_L2 > 0 else 0.5 * L1
        y0, y1 = (0.0, L2) if perp else (-L2 / 2, L2 / 2)
        return [(-L1 / 2, y0), (L1 / 2, y0), (Lt / 2, y1), (-Lt / 2, y1)], [[0], [1], [2], [3]]
    if shape == PLATE_SHAPES[5]:                                          # ranura: largo L1, ancho L2
        n = 10
        if perp:
            pts = G.obround_poly(0.0, L1 / 2.0, L1, min(L2, L1), 90.0, n)
            return _ccw_groups(pts, [list(range(n)), [n], list(range(n + 1, 2 * n + 1)), [2 * n + 1]])
        pts = G.obround_poly(0.0, 0.0, L1, min(L2, L1), 0.0, n)
        return _ccw_groups(pts, [list(range(n)), [n], list(range(n + 1, 2 * n + 1)), [2 * n + 1]])
    pts = [(float(a), float(b)) for a, b in (op.pts or [])]                      # poligono libre
    if len(pts) < 3:
        return outline_default(L1, L2, perp)
    poly, groups = _ccw_groups(pts, [[k] for k in range(len(pts))])
    return poly, groups


def outline_default(L1, L2, perp):
    poly = [(-L1 / 2, 0.0), (L1 / 2, 0.0), (L1 / 2, L2), (-L1 / 2, L2)] if perp else [(-L1 / 2, -L2 / 2), (L1 / 2, -L2 / 2), (L1 / 2, L2 / 2), (-L1 / 2, L2 / 2)]
    return poly, [[0], [1], [2], [3]]


def edge_lengths(op) -> list:
    """Largo de cada borde elegible de la placa, in: [{index, length, label}] (para la interfaz)."""
    perp = op.orient != PLATE_ORIENTS[0]
    poly, groups = outline(op, perp)
    out = []
    n = len(poly)
    for gi, g in enumerate(groups):
        L = sum(math.dist(poly[k % n], poly[(k + 1) % n]) for k in g)
        out.append({"index": gi, "length": float(L)})
    return out


# ------------------------------------------------------------------------------------------------ colocacion en 3D
def make_geo(op, ff):
    """Geometria de la placa de la operacion sobre la cara `ff`: dict con el prisma, el sistema local y el contorno."""
    from .assembly import _plate_prism
    t = max(float(op.plate_t), 0.0625)
    base = ff.point(op.pl_s, op.pl_u)
    rot = math.radians(op.pl_rot)
    perp = op.orient != PLATE_ORIENTS[0]
    c, s = math.cos(rot), math.sin(rot)
    if not perp:
        e1 = c * ff.A + s * ff.U
        e2 = np.cross(ff.N, e1)
        o = base
        centre = base + ff.N * t / 2.0
    else:
        if op.orient == PLATE_ORIENTS[1]:
            e1 = c * ff.U + s * ff.A
        else:
            e1 = c * ff.A + s * ff.U
        e2 = ff.N
        e3 = np.cross(e1, e2)
        o = base - e3 * t / 2.0
        centre = base + e2 * op.pl_W / 2.0
    e3 = np.cross(e1, e2)
    poly, groups = outline(op, perp)
    pr = _plate_prism(poly, o, e1, e2, 0.0, t)
    return {"prism": pr, "o": np.asarray(o, float), "e1": np.asarray(e1, float), "e2": np.asarray(e2, float), "e3": np.asarray(e3, float), "t": t, "perp": perp,
            "poly": poly, "groups": groups, "centre": np.asarray(centre, float), "L1": float(op.pl_L), "L2": float(op.pl_W), "base": np.asarray(base, float)}


def point3(geo, u, v, w):
    return geo["o"] + geo["e1"] * u + geo["e2"] * v + geo["e3"] * w


def add_opening(geo, op, reg):
    """Agrega a la placa la abertura elegida (circular, rectangular o la que rodea a un miembro)."""
    pr = geo["prism"]
    kind = op.opening
    if kind == OPENINGS[1]:
        pr.holes_extra.append(G.circle_poly(float(op.op_x), float(op.op_y), float(op.op_D) / 2.0, 40))
    elif kind == OPENINGS[2]:
        w, h = float(op.op_W) / 2.0, float(op.op_H) / 2.0
        x, y = float(op.op_x), float(op.op_y)
        pr.holes_extra.append([(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h)])
    elif kind == OPENINGS[3] and op.op_member in reg and reg[op.op_member].get("frame"):
        O, d, sx, sy, shp = reg[op.op_member]["frame"]
        O, d, sx, sy = (np.asarray(x, float) for x in (O, d, sx, sy))
        # punto del eje del miembro en el plano de la placa
        Q = O + d * float(np.dot(geo["o"] - O, d))
        cl = float(op.op_clear)

        def uv(p):
            q = np.asarray(p, float) - geo["o"]
            return (float(np.dot(q, geo["e1"])), float(np.dot(q, geo["e2"])))
        if shp.is_round:
            r = shp.d / 2.0 + cl
            cu, cv = uv(Q)
            pr.holes_extra.append(G.circle_poly(cu, cv, r, 40))
        else:
            hb, hd = shp.bf / 2.0 + cl, shp.d / 2.0 + cl
            pr.holes_extra.append([uv(Q + sx * a + sy * b) for a, b in ((-hb, -hd), (hb, -hd), (hb, hd), (-hb, hd))])


# ------------------------------------------------------------------------------------------------ agujeros
def _inside_prism(pr, u, v):
    if pr.circle is not None:
        return False
    if not G.point_in_poly((u, v), pr.poly):
        return False
    for h in list(pr.holes) + list(pr.holes_extra):
        if G.point_in_poly((u, v), h):
            return False
    return True


def punch(part, p0, axis, poly_fn):
    """Hace un agujero en los prismas de `part` que cruza la recta p0 + axis·s.  `poly_fn(prisma, u, v)` -> poligono del agujero en (u, v) del prisma."""
    p0, axis = np.asarray(p0, float), np.asarray(axis, float)
    hit = False
    for pr in part.prisms:
        if pr.circle is not None:
            continue
        U, V = np.asarray(pr.U, float), np.asarray(pr.V, float)
        W = np.cross(U, V)
        den = float(np.dot(axis, W))
        if abs(den) < 0.5:
            continue
        o = np.asarray(pr.o, float)
        wmid = 0.5 * (pr.w0 + pr.w1)
        s = (wmid - float(np.dot(p0 - o, W))) / den
        q = p0 + axis * s - o
        u, v = float(np.dot(q, U)), float(np.dot(q, V))
        if _inside_prism(pr, u, v):
            pr.holes_extra.append([(float(a), float(b)) for a, b in poly_fn(pr, u, v)])
            hit = True
    return hit


def circle_fn(diam, n=20):
    return lambda pr, u, v: G.circle_poly(u, v, diam / 2.0, n)


def slot_fn(L, W, ang_deg, ref_dir):
    """Ranura o hueco rectangular girado `ang_deg` respecto de la direccion `ref_dir` (3D) proyectada en el plano del prisma."""
    def fn(pr, u, v):
        a = math.atan2(float(np.dot(ref_dir, pr.V)), float(np.dot(ref_dir, pr.U)))
        rot = math.degrees(a) + ang_deg
        return G.obround_poly(u, v, L, min(W, L), rot, 8)
    return fn


def rect_fn(L, W, ang_deg, ref_dir):
    def fn(pr, u, v):
        a = math.atan2(float(np.dot(ref_dir, pr.V)), float(np.dot(ref_dir, pr.U))) + math.radians(ang_deg)
        c, s = math.cos(a), math.sin(a)
        return [(u + x * c - y * s, v + x * s + y * c) for x, y in ((-L / 2, -W / 2), (L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2))]
    return fn


# ------------------------------------------------------------------------------------------------ soldaduras
def _slice(P, a, L):
    """Tramo de una poligonal 3D (lista de puntos): desde la distancia `a` del inicio, de largo `L` (0 = hasta el final)."""
    P = [np.asarray(p, float) for p in P]
    seg = [float(np.linalg.norm(P[k + 1] - P[k])) for k in range(len(P) - 1)]
    tot = sum(seg)
    if a <= 1e-9 and (L <= 1e-9 or L >= tot - 1e-9):
        return P
    a = max(0.0, min(a, tot))
    b = tot if L <= 1e-9 else min(tot, a + L)
    out, acc = [], 0.0
    for k, ln in enumerate(seg):
        s0, s1 = acc, acc + ln
        if s1 <= a + 1e-12 or s0 >= b - 1e-12:
            acc = s1
            continue
        t0 = max(a, s0)
        t1 = min(b, s1)
        p0 = P[k] + (P[k + 1] - P[k]) * ((t0 - s0) / ln)
        p1 = P[k] + (P[k + 1] - P[k]) * ((t1 - s0) / ln)
        if not out:
            out.append(p0)
        out.append(p1)
        acc = s1
    return out


def _decimate(pts, maxseg=16):
    n = len(pts) - 1
    if n <= maxseg:
        return pts
    k = int(math.ceil(n / maxseg))
    out = pts[::k]
    if out[-1] is not pts[-1]:
        out.append(pts[-1])
    return out


def weld_lines(geo, ff, edges, a=0.0, L=0.0, tol=0.03):
    """Cordones de la placa contra la cara `ff` de otro elemento: [(p0, p1, nA, nB, borde)].  `edges`: indices de los bordes (None = todos).
    Placa apoyada en la cara (paralela): el cordon corre por el borde, sobre la cara.  Placa que llega a la cara por un borde (perpendicular): un cordon a cada lado."""
    poly, groups, t = geo["poly"], geo["groups"], geo["t"]
    n2 = np.asarray(ff.N, float)
    p2 = np.asarray(ff.O, float)
    n = len(poly)
    cen = point3(geo, float(np.mean([p[0] for p in poly])), float(np.mean([p[1] for p in poly])), t / 2.0)
    sgn = 1.0 if float(np.dot(cen - p2, n2)) >= 0 else -1.0
    nB = n2 * sgn
    out = []
    for gi, g in enumerate(groups):
        if edges is not None and gi not in edges:
            continue
        # poligonal del borde (vertices consecutivos del grupo)
        idx = [g[0]] + [(k + 1) % n for k in g]
        uv = [poly[i % n] for i in idx]
        d0 = [float(np.dot(point3(geo, u, v, 0.0) - p2, n2)) for u, v in uv]
        dt = [float(np.dot(point3(geo, u, v, t) - p2, n2)) for u, v in uv]
        if all(abs(x) < tol for x in d0) and all(abs(x) < tol for x in dt):                    # el borde llega a la cara: T
            for w, nA in ((0.0, -geo["e3"]), (t, geo["e3"])):
                P = _decimate(_slice([point3(geo, u, v, w) for u, v in uv], a, L))
                for k in range(len(P) - 1):
                    out.append((P[k], P[k + 1], nA, nB, gi))
        elif all(abs(x) < tol for x in d0) or all(abs(x) < tol for x in dt):                  # placa apoyada en la cara: traslape
            w = 0.0 if all(abs(x) < tol for x in d0) else t
            P2 = [(u, v) for u, v in uv]
            P3 = _slice([point3(geo, u, v, w) for u, v in P2], a, L)
            P3 = _decimate(P3)
            for k in range(len(P3) - 1):
                tvec = P3[k + 1] - P3[k]
                ln = float(np.linalg.norm(tvec))
                if ln < 1e-9:
                    continue
                tvec = tvec / ln
                nA = np.cross(tvec, geo["e3"])                           # normal en el plano de la placa, hacia afuera si el contorno es CCW
                nA = nA / max(float(np.linalg.norm(nA)), 1e-12)
                if float(np.dot(nA, (P3[k] + P3[k + 1]) / 2.0 - cen)) < 0:
                    nA = -nA
                out.append((P3[k], P3[k + 1], nA, nB, gi))
    return out
