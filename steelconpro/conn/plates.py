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
        if not g:
            continue
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


def _add_hole(geo, poly):
    """Abertura de la placa: agujero del prisma y borde elegible para soldar (después de los bordes del contorno)."""
    h = [(float(a), float(b)) for a, b in poly]
    geo["prism"].holes_extra.append(h)
    geo.setdefault("holes", []).append(G.cw(h))


def add_opening(geo, op, reg):
    """Agrega a la placa la abertura elegida (circular, rectangular o la que rodea a un miembro)."""
    pr = geo["prism"]
    kind = op.opening
    if kind == OPENINGS[1]:
        _add_hole(geo, G.circle_poly(float(op.op_x), float(op.op_y), float(op.op_D) / 2.0, 40))
    elif kind == OPENINGS[2]:
        w, h = float(op.op_W) / 2.0, float(op.op_H) / 2.0
        x, y = float(op.op_x), float(op.op_y)
        _add_hole(geo, [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h)])
    elif kind == OPENINGS[3] and op.op_member in reg and reg[op.op_member].get("frame"):
        O, d, sx, sy, shp = reg[op.op_member]["frame"]
        O, d, sx, sy = (np.asarray(x, float) for x in (O, d, sx, sy))
        mid = geo["o"] + geo["e3"] * (geo["t"] / 2.0)                       # plano medio de la placa
        den = float(np.dot(d, geo["e3"]))
        if abs(den) < 0.1:
            return                                                          # el miembro corre casi paralelo a la placa: no la atraviesa
        cl = float(op.op_clear)

        def uv(p):
            p = np.asarray(p, float)
            X = p + d * (float(np.dot(mid - p, geo["e3"])) / den)           # el contorno de la sección se lleva al plano de la placa siguiendo el eje del miembro
            q = X - geo["o"]
            return (float(np.dot(q, geo["e1"])), float(np.dot(q, geo["e2"])))
        Q = O + d * (float(np.dot(mid - O, geo["e3"])) / den)
        if shp.is_round:
            r = shp.d / 2.0 + cl
            _add_hole(geo, [uv(Q + sx * r * math.cos(a_) + sy * r * math.sin(a_)) for a_ in [2 * math.pi * k / 40 for k in range(40)]])
        else:
            hb, hd = shp.bf / 2.0 + cl, shp.d / 2.0 + cl
            _add_hole(geo, [uv(Q + sx * a + sy * b) for a, b in ((-hb, -hd), (hb, -hd), (hb, hd), (-hb, hd))])


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
    """Tramo de una poligonal (lista de puntos): desde la distancia `a` del inicio, de largo `L` (0 = hasta el final)."""
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


def _slice_runs(runs, a, L):
    """Como `_slice` pero sobre varias poligonales seguidas (un borde cortado en varios tramos): la distancia se cuenta a lo largo de todas."""
    if len(runs) == 1:
        return [_slice(runs[0], a, L)]
    lens = [sum(float(np.linalg.norm(np.asarray(r[k + 1], float) - np.asarray(r[k], float))) for k in range(len(r) - 1)) for r in runs]
    tot = sum(lens)
    if a <= 1e-9 and (L <= 1e-9 or L >= tot - 1e-9):
        return [[np.asarray(p, float) for p in r] for r in runs]
    b = tot if L <= 1e-9 else min(tot, a + L)
    out, acc = [], 0.0
    for r, ln in zip(runs, lens):
        lo, hi = max(a - acc, 0.0), min(b - acc, ln)
        if hi - lo > 1e-9:
            out.append(_slice(r, lo, hi - lo))
        acc += ln
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


def _seg_runs(g, n):
    """Tramos de segmentos consecutivos de un grupo de bordes (un borde recortado puede quedar en varios tramos)."""
    ks = sorted({int(k) % n for k in g})
    runs, cur = [], []
    for k in ks:
        if cur and k == cur[-1] + 1:
            cur.append(k)
        else:
            if cur:
                runs.append(cur)
            cur = [k]
    if cur:
        runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n - 1:
        runs[0] = runs[-1] + runs[0]
        runs.pop()
    return runs


def _poly_dist(p, poly):
    n = len(poly)
    best = 1e18
    P = np.asarray(p, float)
    for i in range(n):
        a, b = np.asarray(poly[i], float), np.asarray(poly[(i + 1) % n], float)
        e = b - a
        L2 = float(e @ e)
        t = 0.0 if L2 < 1e-18 else min(1.0, max(0.0, float((P - a) @ e) / L2))
        best = min(best, float(np.linalg.norm(P - (a + t * e))))
    return best


def _seg_polygon_intervals(a, b, poly, tol):
    """Intervalos (t0, t1) del segmento a-b (2D) que quedan dentro del polígono `poly` o a menos de `tol` de su borde."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    ts = [0.0, 1.0]
    n = len(poly)
    for i in range(n):
        p, q = np.asarray(poly[i], float), np.asarray(poly[(i + 1) % n], float)
        e = q - p
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        w = p - a
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if 0.0 < t < 1.0 and -1e-9 <= u <= 1.0 + 1e-9:
            ts.append(float(t))
    ts = sorted(set(ts))
    out = []
    for t0, t1 in zip(ts[:-1], ts[1:]):
        if t1 - t0 < 1e-9:
            continue
        m = a + d * (0.5 * (t0 + t1))
        mm = (float(m[0]), float(m[1]))
        if G.point_in_poly(mm, poly) or _poly_dist(mm, poly) <= tol:
            if out and abs(out[-1][1] - t0) < 1e-9:
                out[-1] = (out[-1][0], t1)
            else:
                out.append((t0, t1))
    return out


def face_region(entry, ff):
    """Polígono (s, u) de la cara `ff` de un elemento donde hay material: el contorno de una placa (proyectado en su cara) o el rectángulo de la cara."""
    if getattr(ff, "A", None) is None or getattr(ff, "U", None) is None:
        return None
    geo = entry.get("geo") if entry else None
    O, A, U = np.asarray(ff.O, float), np.asarray(ff.A, float), np.asarray(ff.U, float)
    if geo is not None and abs(float(np.dot(np.asarray(ff.N, float), geo["e3"]))) > 0.99:
        pts = [point3(geo, u, v, 0.0) for u, v in geo["poly"]]
        return [(float((p - O) @ A), float((p - O) @ U)) for p in pts]
    fr = entry.get("frame_full") if entry else None
    if fr is not None and abs(float(np.dot(np.asarray(ff.N, float), np.asarray(fr[2], float)))) > 0.99:       # extremo de un miembro: el material es la sección, no el rectángulo
        from .ops import _shape_outline
        start, end, d, sx, sy, shp = (np.asarray(x, float) if k < 5 else x for k, x in enumerate(fr))
        Q = start if abs(float((start - O) @ np.asarray(ff.N, float))) <= abs(float((end - O) @ np.asarray(ff.N, float))) else end
        pts, _g = _shape_outline(shp)
        out = []
        for a, b in pts:
            q = Q + sx * a + sy * b
            out.append((float((q - O) @ A), float((q - O) @ U)))
        return out
    L, uh = float(ff.L), float(ff.uh)
    return [(0.0, -uh), (L, -uh), (L, uh), (0.0, uh)]


def _clip_lines(lines, ff, region, info, tol=0.06):
    """Recorta los cordones a la región de la cara donde hay material (la placa puede sobresalir de la cara)."""
    if region is None or getattr(ff, "A", None) is None:
        return lines
    O, A, U = np.asarray(ff.O, float), np.asarray(ff.A, float), np.asarray(ff.U, float)
    out, tot, kept = [], 0.0, 0.0
    for ln in lines:
        p0, p1 = np.asarray(ln[0], float), np.asarray(ln[1], float)
        a = (float((p0 - O) @ A), float((p0 - O) @ U))
        b = (float((p1 - O) @ A), float((p1 - O) @ U))
        tot += float(np.linalg.norm(p1 - p0))
        for t0, t1 in _seg_polygon_intervals(a, b, region, tol):
            q0, q1 = p0 + (p1 - p0) * t0, p0 + (p1 - p0) * t1
            if float(np.linalg.norm(q1 - q0)) < 0.05:
                continue
            kept += float(np.linalg.norm(q1 - q0))
            out.append((q0, q1) + tuple(ln[2:]))
    if info is not None:
        info["total"], info["clipped"] = tot, tot - kept
    return out


def weld_lines(geo, ff, edges, a=0.0, L=0.0, tol=0.03, region=None, info=None):
    """Cordones de la placa contra la cara `ff` de otro elemento: [(p0, p1, nA, nB, borde)].  `edges`: indices de los bordes (None = todos; los bordes de
    las aberturas siguen a los del contorno).  Se decide tramo por tramo: un tramo que llega a la cara por el borde (placa perpendicular) lleva un cordón a
    cada lado; uno apoyado en la cara (placa paralela) lleva el cordón por el borde, sobre la cara.  `region` = polígono (s, u) de la cara donde hay
    material: los cordones se recortan a él (una placa que sobresale de la cara no suelda en el aire).  `info` recibe {total, clipped} (in)."""
    poly, groups, t = geo["poly"], geo["groups"], geo["t"]
    n2 = np.asarray(ff.N, float)
    p2 = np.asarray(ff.O, float)
    n = len(poly)
    cen = point3(geo, float(np.mean([p[0] for p in poly])), float(np.mean([p[1] for p in poly])), t / 2.0)
    sgn = 1.0 if float(np.dot(cen - p2, n2)) >= 0 else -1.0
    nB = n2 * sgn
    cuts = geo.get("cuts") or {}
    loops = []                                                           # (indice de borde, [poligonales (u, v)])
    for gi, g in enumerate(groups):
        if edges is not None and gi not in edges:
            continue
        loops.append((gi, [[poly[k % n] for k in run] + [poly[(run[-1] + 1) % n]] for run in _seg_runs(g, n)]))
    for k, hp in enumerate(geo.get("holes") or []):
        gi = len(groups) + k
        if edges is not None and gi not in edges:
            continue
        loops.append((gi, [list(hp) + [hp[0]]]))
    out = []
    for gi, runs in loops:
        cut = cuts.get(gi)
        exact = cut is not None and abs(float(np.dot(cut["N"], n2))) > 0.999 and abs(float(np.dot(np.asarray(cut["P"], float) - p2, n2))) < 1e-3
        for r in _slice_runs(runs, a, L):
            uv = [(float(q[0]), float(q[1])) for q in r]
            if len(uv) < 2:
                continue
            cls = []
            for k in range(len(uv) - 1):
                d0 = [float(np.dot(point3(geo, u, v, 0.0) - p2, n2)) for u, v in (uv[k], uv[k + 1])]
                dt = [float(np.dot(point3(geo, u, v, t) - p2, n2)) for u, v in (uv[k], uv[k + 1])]
                on0, ont = all(abs(x) < tol for x in d0), all(abs(x) < tol for x in dt)
                cls.append("T" if (on0 and ont) or exact else ("0" if on0 else ("t" if ont else "")))
            k = 0
            while k < len(cls):
                if not cls[k]:
                    k += 1
                    continue
                k2 = k
                while k2 + 1 < len(cls) and cls[k2 + 1] == cls[k]:
                    k2 += 1
                seg_uv = uv[k:k2 + 2]
                if cls[k] == "T":
                    for w, nA in ((0.0, -geo["e3"]), (t, geo["e3"])):
                        P = [point3(geo, u, v, w) for u, v in seg_uv]
                        if exact:                                       # recorte contra el plano de esta cara: el cordón queda exactamente sobre el plano
                            Nc = np.asarray(cut["N"], float)
                            g_ = Nc - geo["e3"] * float(np.dot(Nc, geo["e3"]))
                            gn = float(np.linalg.norm(g_))
                            if gn > 1e-9:
                                g_ = g_ / gn
                                P = [q + g_ * (float(np.dot(np.asarray(cut["P"], float) - q, Nc)) / float(np.dot(g_, Nc))) for q in P]
                        P = _decimate(P)
                        for j in range(len(P) - 1):
                            out.append((P[j], P[j + 1], nA, nB, gi))
                else:
                    w = 0.0 if cls[k] == "0" else t
                    P3 = _decimate([point3(geo, u, v, w) for u, v in seg_uv])
                    for j in range(len(P3) - 1):
                        tvec = P3[j + 1] - P3[j]
                        ln = float(np.linalg.norm(tvec))
                        if ln < 1e-9:
                            continue
                        tvec = tvec / ln
                        nA = np.cross(tvec, geo["e3"])                           # normal en el plano de la placa, hacia afuera si el contorno es CCW
                        nA = nA / max(float(np.linalg.norm(nA)), 1e-12)
                        if float(np.dot(nA, (P3[j] + P3[j + 1]) / 2.0 - cen)) < 0:
                            nA = -nA
                        out.append((P3[j], P3[j + 1], nA, nB, gi))
                k = k2 + 1
    return _clip_lines(out, ff, region, info)


def edge_lengths_geo(geo) -> list:
    """Largo de cada borde elegible de la placa ya armada (contorno recortado y aberturas): [{index, length}]."""
    poly, groups = geo["poly"], geo["groups"]
    n = len(poly)
    out = [{"index": gi, "length": float(sum(math.dist(poly[k % n], poly[(k + 1) % n]) for k in g))} for gi, g in enumerate(groups)]
    for k, hp in enumerate(geo.get("holes") or []):
        out.append({"index": len(groups) + k, "length": float(sum(math.dist(hp[i], hp[(i + 1) % len(hp)]) for i in range(len(hp)))), "hole": True})
    return out


# ------------------------------------------------------------------------------------------------ recorte de una placa contra un plano o un volumen
def clip_outline(poly, groups, nu, nv, d0, keep_sign):
    """Recorta el contorno (u, v) conservando keep_sign·(nu·u + nv·v + d0) ≥ 0.  Los bordes que se conservan mantienen su número de grupo y el borde nuevo
    (sobre el plano) recibe el siguiente.  -> (contorno, grupos)"""
    n = len(poly)
    seg_g = {}
    for gi, g in enumerate(groups):
        for k in g:
            seg_g[k % n] = gi
    cut_id = len(groups)
    f = lambda p: keep_sign * (nu * p[0] + nv * p[1] + d0)                      # noqa: E731
    out, gid = [], []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        fa, fb = f(a), f(b)
        g = seg_g.get(k, 0)
        if fa >= 0 and fb >= 0:
            out.append(a)
            gid.append(g)
        elif fa >= 0 > fb:                                                      # sale del semiplano
            out.append(a)
            if fa > 0:
                gid.append(g)
                t = fa / (fa - fb)
                out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                gid.append(cut_id)
            else:
                gid.append(cut_id)
        elif fa < 0 <= fb:                                                      # entra al semiplano
            if fb > 0:
                t = fa / (fa - fb)
                out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                gid.append(g)
    if len(out) < 3:
        return [], []
    new_groups = [[k for k, x in enumerate(gid) if x == gi] for gi in range(cut_id + 1)]
    return out, [g for g in new_groups]


def _regroup(new_poly, old_poly, old_groups):
    """Grupos de bordes de un contorno nuevo: cada tramo que cae sobre un borde del contorno anterior conserva su número; el resto es el borde nuevo (corte)."""
    n, m = len(old_poly), len(new_poly)
    seg_g = {}
    for gi, g in enumerate(old_groups):
        for k in g:
            seg_g[k % n] = gi
    cut_id = len(old_groups)
    gid = []
    for k in range(m):
        a, b = np.asarray(new_poly[k], float), np.asarray(new_poly[(k + 1) % m], float)
        found = cut_id
        for j in range(n):
            p, q = np.asarray(old_poly[j], float), np.asarray(old_poly[(j + 1) % n], float)
            e = q - p
            L2 = float(e @ e)
            if L2 < 1e-18:
                continue
            ta, tb = float((a - p) @ e) / L2, float((b - p) @ e) / L2
            if -1e-6 <= ta <= 1 + 1e-6 and -1e-6 <= tb <= 1 + 1e-6 and float(np.linalg.norm(a - (p + e * ta))) < 1e-6 and float(np.linalg.norm(b - (p + e * tb))) < 1e-6:
                found = seg_g.get(j, cut_id)
                break
        gid.append(found)
    return [[k for k, x in enumerate(gid) if x == gi] for gi in range(cut_id + 1)]


def _tname(o):
    return (o.targets or [""])[0]


def apply_trims(geo, trims, reg, mdl=None, own=None):
    """Recorta la placa `geo` (de nombre `own`) contra los planos de las caras o contra el volumen de otros elementos.  `trims`: [operaciones de recorte].
    Devuelve los avisos.  El recorte es recto a través del espesor: se corta el contorno (u, v), y con él se calculan bordes, cordones, pernos y aberturas."""
    from .specs import TRIM_MODES
    notes = []
    for o in trims:
        if o.trim_mode == TRIM_MODES[2]:
            notes += _trim_volume(geo, o, reg, mdl, own)
            continue
        if o.trim_mode == TRIM_MODES[1]:
            notes.append(f"Recorte de «{_tname(o)}»: el inglete solo se aplica a miembros; use «contra una cara» o «contra el volumen» para una placa.")
            continue
        par = reg.get(o.parent)
        if par is None or o.face not in par["faces"]:
            notes.append(f"Recorte de «{_tname(o)}»: elija el elemento y la cara contra la que se recorta.")
            continue
        if o.parent == own:
            notes.append(f"Recorte de «{_tname(o)}»: una placa no se corta con su propia cara.")
            continue
        ff = par["faces"][o.face]
        N = np.asarray(ff.N, float)
        e1, e2, e3, org, t = geo["e1"], geo["e2"], geo["e3"], geo["o"], geo["t"]
        nu, nv = float(N @ e1), float(N @ e2)
        if math.hypot(nu, nv) < 1e-6:
            notes.append(f"Recorte de «{_tname(o)}»: el plano es paralelo a la placa y no la corta.")
            continue
        gap = float(o.trim_gap)
        P0 = np.asarray(ff.O, float)
        kside = 1.0 if float(N @ (geo["centre"] - P0)) >= 0 else -1.0       # por omisión se conserva el lado donde queda el centro de la placa
        keep = -kside if o.trim_flip else kside
        P = P0 + N * (gap * keep)                                           # la holgura se mide hacia el lado que se conserva
        d_mid = float(N @ (org + e3 * (t / 2.0) - P))
        shift = abs(float(N @ e3)) * t / 2.0                                # corte recto: en un plano oblicuo se toma el borde más holgado (sin holgura: toca) o el más cerrado (con holgura: libra)
        d0 = d_mid + keep * shift * (1.0 if gap <= 1e-9 else -1.0)
        poly, groups = clip_outline(geo["poly"], geo["groups"], nu, nv, d0, keep)
        if len(poly) < 3:
            notes.append(f"Recorte de «{_tname(o)}»: el plano se lleva toda la placa (pruebe «conservar el otro lado»).")
            continue
        if len(poly) == len(geo["poly"]) and all(math.dist(a, b) < 1e-9 for a, b in zip(poly, geo["poly"])):
            notes.append(f"Recorte de «{_tname(o)}»: el plano no toca la placa.")
            continue
        cut_id = len(geo["groups"])
        geo["poly"], geo["groups"] = poly, groups
        geo["prism"].poly = [(float(a), float(b)) for a, b in poly]
        geo.setdefault("cuts", {})[cut_id] = {"N": N, "P": P}
    return notes


# ---- recorte contra el volumen de otro elemento
def _convex_hull(pts):
    from .polyclip import hull
    return hull(pts)


def offset_convex(poly, d):
    """Polígono convexo CCW desplazado `d` hacia afuera (negativo: hacia adentro); [] si desaparece."""
    P = G.ccw(poly)
    n = len(P)
    if abs(d) < 1e-12:
        return P
    lines = []
    for i in range(n):
        a, b = np.asarray(P[i], float), np.asarray(P[(i + 1) % n], float)
        e = b - a
        L = float(np.linalg.norm(e))
        if L < 1e-12:
            continue
        nrm = np.array([e[1], -e[0]]) / L                                           # normal hacia afuera de un contorno CCW
        lines.append((a + nrm * d, e / L))
    out = []
    m = len(lines)
    for i in range(m):
        p1, d1 = lines[i - 1]
        p2, d2 = lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            out.append((float(p2[0]), float(p2[1])))
            continue
        w = p2 - p1
        t = (w[0] * d2[1] - w[1] * d2[0]) / den
        q = p1 + d1 * t
        out.append((float(q[0]), float(q[1])))
    if len(out) < 3 or G.area(out) <= 1e-9 or (d < 0 and G.area(out) > G.area(P)):
        return []
    return out


def cutter_pieces(entry, mdl):
    """Cajas (prismas convexos) que forman el volumen de un elemento: [(o, U, V, W, polígono convexo CCW en (u, v), w0, w1)].  Miembro: su caja envolvente
    (rectángulo de la sección o círculo); placa o ángulo: la envolvente convexa de cada uno de sus prismas."""
    out = []
    fr = entry.get("frame_full")
    if entry.get("type") == "miembro" and fr is not None:
        start, end, d, sx, sy, shp = fr
        L = float(np.linalg.norm(np.asarray(end, float) - np.asarray(start, float)))
        if shp.is_round:
            poly = G.circle_poly(0.0, 0.0, shp.d / 2.0, 36)
        else:
            d_, bf = float(shp.d), float(shp.bf if shp.bf > 0 else shp.d)
            poly = [(-bf / 2, -d_ / 2), (bf / 2, -d_ / 2), (bf / 2, d_ / 2), (-bf / 2, d_ / 2)]
        out.append((np.asarray(start, float), np.asarray(sx, float), np.asarray(sy, float), np.asarray(d, float), poly, 0.0, L))
        return out
    part = next((p for p in (mdl.parts if mdl is not None else []) if p.name == entry.get("part")), None)
    for pr in (part.prisms if part is not None else []):
        U, V = np.asarray(pr.U, float), np.asarray(pr.V, float)
        if pr.circle is not None:
            poly = G.circle_poly(0.0, 0.0, pr.circle[0], 36)
        else:
            poly = _convex_hull(pr.poly)
        if len(poly) >= 3:
            out.append((np.asarray(pr.o, float), U, V, np.cross(U, V), G.ccw(poly), float(pr.w0), float(pr.w1)))
    return out


def _clip_half(poly, c0, c1, c2):
    """Parte de `poly` (u, v) con c0 + c1·u + c2·v ≥ 0 (Sutherland–Hodgman)."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = c0 + c1 * p[0] + c2 * p[1], c0 + c1 * q[0] + c2 * q[1]
        if fp >= 0:
            out.append(p)
        if (fp > 0 > fq) or (fq > 0 > fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _section_in_plate(piece, org, e1, e2, e3, w):
    """Sección del prisma convexo `piece` con el plano de la placa a la altura `w` (sistema local de la placa): polígono convexo (u, v) o []."""
    O, U, V, W, poly, w0, w1 = piece
    c = np.asarray(org, float) + e3 * w - O
    cu, cv, cw = float(c @ U), float(c @ V), float(c @ W)
    a11, a12, a21, a22 = float(e1 @ U), float(e2 @ U), float(e1 @ V), float(e2 @ V)
    b1, b2 = float(e1 @ W), float(e2 @ W)
    det = a11 * a22 - a12 * a21
    if abs(det) > 1e-6:
        inv = np.array([[a22, -a12], [-a21, a11]]) / det
        Q = [(float((inv @ np.array([p[0] - cu, p[1] - cv]))[0]), float((inv @ np.array([p[0] - cu, p[1] - cv]))[1])) for p in poly]
        Q = G.ccw(Q)
        Q = _clip_half(Q, cw - w0, b1, b2)
        if len(Q) >= 3:
            Q = _clip_half(Q, w1 - cw, -b1, -b2)
        return Q if len(Q) >= 3 and abs(G.area(Q)) > 1e-9 else []
    nb = math.hypot(b1, b2)                                                         # el plano de la placa contiene al eje del prisma
    if nb < 1e-9:
        return []
    dW = np.array([b1, b2]) / nb
    dn = np.array([-dW[1], dW[0]])
    en = dn[0] * e1 + dn[1] * e2
    g = np.array([float(en @ U), float(en @ V)])
    base = np.array([cu, cv])
    lo, hi = -1e9, 1e9
    m = len(poly)
    for i in range(m):                                                              # Cyrus–Beck: la recta base + q·g dentro del polígono convexo CCW
        a, b = np.asarray(poly[i], float), np.asarray(poly[(i + 1) % m], float)
        nrm = np.array([b[1] - a[1], -(b[0] - a[0])])
        den = float(nrm @ g)
        num = float(nrm @ (a - base))
        if abs(den) < 1e-12:
            if num < 0:
                return []
            continue
        q = num / den
        if den > 0:
            hi = min(hi, q)
        else:
            lo = max(lo, q)
    if hi - lo < 1e-9:
        return []
    s0, s1 = (w0 - cw) / nb, (w1 - cw) / nb
    pts = [dW * s + dn * q for s, q in ((s0, lo), (s1, lo), (s1, hi), (s0, hi))]
    return G.ccw([(float(p[0]), float(p[1])) for p in pts])


def _trim_volume(geo, o, reg, mdl, own):
    """Quita de la placa lo que queda dentro de la caja del elemento `parent` más la holgura `trim_gap` (con `trim_flip`, conserva solo lo que queda dentro)."""
    from . import polyclip as PC
    tn = _tname(o)
    other = reg.get(o.parent)
    if other is None or (other.get("part") is None) or other.get("type") in ("plano", "placa base"):
        return [f"Recorte de «{tn}»: elija el elemento (miembro, placa o ángulo) cuyo volumen corta la placa."]
    if o.parent == own:
        return [f"Recorte de «{tn}»: una placa no se corta con ella misma."]
    pieces = cutter_pieces(other, mdl)
    if not pieces:
        return [f"Recorte de «{tn}»: no se pudo obtener el volumen de «{o.parent}»."]
    gap = float(o.trim_gap)
    e1, e2, e3, org, t = geo["e1"], geo["e2"], geo["e3"], geo["o"], geo["t"]
    regions = []
    for O, U, V, W, poly, w0, w1 in pieces:
        pg = offset_convex(poly, gap)
        if not pg:
            continue
        pc = (O, U, V, W, pg, w0 - gap, w1 + gap)
        pts = []
        for w in (0.0, t / 2.0, t):
            pts += _section_in_plate(pc, org, e1, e2, e3, w)
        if len(pts) >= 3:
            h = _convex_hull(pts)
            if len(h) >= 3:
                regions.append(G.ccw(h))
    if not regions:
        return [f"Recorte de «{tn}»: el volumen de «{o.parent}»{' con su holgura' if gap else ''} no toca la placa."]
    poly0 = G.ccw(list(geo["poly"]))
    items = [(poly0, [])]
    if o.trim_flip:
        keep = []
        for P_, _H in items:
            for C in regions:
                I = PC.intersect_convex(P_, C)
                if I:
                    keep.append((I, []))
        items = keep
    else:
        for C in regions:
            new = []
            for P_, H_ in items:
                for (cont, holes, _contact) in PC.subtract(P_, C):
                    new.append((cont, list(H_) + [list(h) for h in holes]))
            items = new
    if not items:
        return [f"Recorte de «{tn}»: el volumen de «{o.parent}» se lleva toda la placa (pruebe «conservar el otro lado»)."]
    notes = []
    best = next((it for it in items if G.point_in_poly((0.0, 0.0), it[0])), None)
    if best is None:
        best = max(items, key=lambda it: abs(G.area(it[0])))
    if len(items) > 1:
        notes.append(f"Recorte de «{tn}»: el volumen de «{o.parent}» deja la placa en {len(items)} partes; se conserva la que contiene su centro (o la mayor).")
    cont, holes = best
    if len(cont) == len(poly0) and all(math.dist(a, b) < 1e-9 for a, b in zip(cont, poly0)) and not holes:
        return [f"Recorte de «{tn}»: el volumen de «{o.parent}»{' con su holgura' if gap else ''} no toca la placa."]
    groups = _regroup(cont, geo["poly"], geo["groups"])
    geo["poly"], geo["groups"] = list(cont), groups
    geo["prism"].poly = [(float(a), float(b)) for a, b in cont]
    for h in holes:
        hh = [(float(a), float(b)) for a, b in G.cw(h)]
        geo["prism"].holes_extra.append(hh)
        geo.setdefault("holes", []).append(hh)
    return notes


# ---- recorte de ángulos (prismas de sección en L extruidos a lo largo del eje W)
def clip_segment_halfspaces(p0, p1, halfs):
    """Parte del segmento p0-p1 que cumple n·(x − pt) ≤ 0 en todos los semiespacios (pt, n); None si no queda nada."""
    a, b = np.asarray(p0, float), np.asarray(p1, float)
    t0, t1 = 0.0, 1.0
    for pt, nrm in halfs:
        n, pt = np.asarray(nrm, float), np.asarray(pt, float)
        fa, fb = float(n @ (a - pt)), float(n @ (b - pt))
        if fa > 0 and fb > 0:
            return None
        if fa > 0:
            t0 = max(t0, fa / (fa - fb))
        elif fb > 0:
            t1 = min(t1, fa / (fa - fb))
    if t1 - t0 < 1e-6:
        return None
    return a + (b - a) * t0, a + (b - a) * t1


def clip_to_region(lines, ff, region):
    return _clip_lines(lines, ff, region, None)


def _in_piece(piece, P, gap):
    """Máscara de los puntos P (n, 3) dentro del prisma convexo `piece` inflado en `gap`."""
    O, U, V, W, poly, w0, w1 = piece
    pg = offset_convex(poly, gap)
    if not pg:
        return np.zeros(len(P), bool)
    d = P - O
    u, v, w = d @ U, d @ V, d @ W
    m = (w >= w0 - gap) & (w <= w1 + gap)
    n = len(pg)
    for i in range(n):
        a, b = pg[i], pg[(i + 1) % n]
        m &= ((b[0] - a[0]) * (v - a[1]) - (b[1] - a[1]) * (u - a[0])) >= -1e-9
    return m


def trim_angle(pr, trims, reg, mdl, own):
    """Recortes de un ángulo (prisma `pr`): contra el plano de una cara (plano de corte; se conserva el lado donde queda el ángulo, o el contrario con
    `trim_flip`) o contra el volumen de otro elemento (se le quita el tramo del eje que queda dentro de la caja del otro más la holgura).
    -> (avisos, semiespacios [(punto, normal)] que se conservan con n·(x − punto) ≤ 0, nuevo w0, nuevo w1)"""
    from .specs import TRIM_MODES
    notes, halfs = [], []
    U, V = np.asarray(pr.U, float), np.asarray(pr.V, float)
    W = np.cross(U, V)
    o_ = np.asarray(pr.o, float)
    sec = [tuple(q) for q in pr.poly]
    for o in trims:
        tn = _tname(o)
        w0, w1 = float(pr.w0), float(pr.w1)
        par = reg.get(o.parent)
        if o.parent == own:
            notes.append(f"Recorte de «{tn}»: un ángulo no se corta con él mismo.")
            continue
        if o.trim_mode == TRIM_MODES[1]:
            notes.append(f"Recorte de «{tn}»: el inglete solo se aplica a miembros.")
            continue
        gap = float(o.trim_gap)
        if o.trim_mode == TRIM_MODES[2]:
            if par is None or par.get("part") is None or par.get("type") in ("plano", "placa base"):
                notes.append(f"Recorte de «{tn}»: elija el elemento (miembro, placa o ángulo) cuyo volumen corta al ángulo.")
                continue
            pieces = cutter_pieces(par, mdl)
            ws = np.linspace(w0, w1, max(int(math.ceil((w1 - w0) / 0.02)) + 1, 2))
            rem = np.zeros(len(ws), bool)
            for (u, v) in sec:
                Pn = o_ + u * U + v * V + np.outer(ws, W)
                for pc in pieces:
                    rem |= _in_piece(pc, Pn, gap)
            runs, i = [], 0
            while i < len(ws):                                            # tramos (de índices) que se conservan
                if not rem[i]:
                    j = i
                    while j + 1 < len(ws) and not rem[j + 1]:
                        j += 1
                    runs.append((i, j))
                    i = j + 1
                else:
                    i += 1
            if not rem.any():
                notes.append(f"Recorte de «{tn}»: el volumen de «{o.parent}»{' con su holgura' if gap else ''} no toca al ángulo.")
                continue
            if o.trim_flip:                                               # se conserva lo que queda dentro
                runs, i = [], 0
                while i < len(ws):
                    if rem[i]:
                        j = i
                        while j + 1 < len(ws) and rem[j + 1]:
                            j += 1
                        runs.append((i, j))
                        i = j + 1
                    else:
                        i += 1
            if not runs:
                notes.append(f"Recorte de «{tn}»: el volumen de «{o.parent}» se lleva todo el ángulo (pruebe «conservar el otro lado»).")
                continue
            mid = 0.5 * (w0 + w1)
            best = next((r for r in runs if ws[r[0]] <= mid <= ws[r[1]]), None) or max(runs, key=lambda r: r[1] - r[0])
            if len(runs) > 1:
                notes.append(f"Recorte de «{tn}»: el volumen de «{o.parent}» deja al ángulo en {len(runs)} tramos; se conserva el que contiene su centro (o el mayor).")
            step = float(ws[1] - ws[0]) if len(ws) > 1 else 0.0
            nw0 = w0 if best[0] == 0 else float(ws[best[0]]) - 0.5 * step
            nw1 = w1 if best[1] == len(ws) - 1 else float(ws[best[1]]) + 0.5 * step
            pr.w0, pr.w1 = nw0, nw1
            continue
        if par is None or o.face not in par["faces"]:
            notes.append(f"Recorte de «{tn}»: elija el elemento y la cara contra la que se recorta.")
            continue
        ff = par["faces"][o.face]
        N = np.asarray(ff.N, float)
        P0 = np.asarray(ff.O, float)
        cen = pr.corners().mean(axis=0)
        kside = 1.0 if float(N @ (cen - P0)) >= 0 else -1.0
        keep = -kside if o.trim_flip else kside
        P = P0 + N * (gap * keep)
        n = -keep * N                                                     # se conserva n·(x − P) ≤ 0
        dist = [float(n @ (o_ + u * U + v * V + w * W - P)) for (u, v) in sec for w in (w0, w1)]
        if max(dist) <= 1e-6:
            notes.append(f"Recorte de «{tn}»: el plano no toca al ángulo.")
            continue
        if min(dist) >= -1e-6:
            notes.append(f"Recorte de «{tn}»: el plano se lleva todo el ángulo (pruebe «conservar el otro lado»).")
            continue
        lo_, hi_ = 1e18, -1e18
        nW = float(n @ W)
        for (u, v) in sec:                                                # tramo de cada arista longitudinal que se conserva
            d0 = float(n @ (o_ + u * U + v * V + w0 * W - P))
            ends = []
            if d0 <= 1e-9:
                ends.append(w0)
            d1 = d0 + nW * (w1 - w0)
            if d1 <= 1e-9:
                ends.append(w1)
            if (d0 > 1e-9) != (d1 > 1e-9) and abs(nW) > 1e-12:
                ends.append(w0 + (-d0 / nW))
            if ends:
                lo_, hi_ = min(lo_, min(ends)), max(hi_, max(ends))
        pr.cut_planes = list(pr.cut_planes) + [(tuple(map(float, P)), tuple(map(float, n)))]
        halfs.append((P, n))
        if lo_ < hi_:
            pr.w0, pr.w1 = max(w0, lo_), min(w1, hi_)
    return notes, halfs, float(pr.w0), float(pr.w1)
