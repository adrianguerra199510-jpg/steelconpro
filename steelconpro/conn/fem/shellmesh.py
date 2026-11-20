# -*- coding: utf-8 -*-
"""Modelo de PLACAS (cascarones) del FEM: cada pieza del modelo 3D se reduce a su SUPERFICIE MEDIA con su espesor, como en IDEA StatiCa / RAM Connection.

· `build_plates(mdl)` convierte los prismas de cada pieza en placas (polígono plano en 3D + espesor + normal):
    - placa plana (espesor en la dirección de extrusión W): el polígono a mitad del espesor;
    - rectángulo delgado en su propio plano (alas y alma de un perfil I, paredes de un HSS, piernas de un ángulo): la superficie media de ese rectángulo extruido;
    - tubo redondo: facetas sobre el radio medio;
    - recortes planos (`cut_planes`) y agujeros (`holes_extra`, pernos y anclajes) se respetan.
· `snap_plates` lleva el borde de una placa hasta la superficie media de la placa perpendicular contra la que apoya (alma contra ala, placa soldada contra ala, pared de HSS contra pared):
  así las placas comparten arista (malla conforme y unión continua, como una soldadura de penetración completa en el modelo de placas).
· El mallado lo hace Gmsh en un proceso hijo (`run.py --meshs`): superficies planas fragmentadas (nodos compartidos), cuadriláteros cuando se puede.
"""
from __future__ import annotations
import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

TOL = 1e-6


def unit(v):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


@dataclass
class Plate:
    key: str                     # identificador unico
    part: str                    # pieza del modelo 3D a la que pertenece
    kind: str                    # tipo de la pieza (beam, plate, ...)
    P: np.ndarray                # vertices (n, 3) del contorno
    t: float                     # espesor
    n: np.ndarray                # normal de la superficie media
    holes: list = field(default_factory=list)       # [(m, 3)] agujeros (pernos, anclajes, aberturas)

    @property
    def c(self):
        return self.P.mean(axis=0)

    def basis(self):
        n = unit(self.n)
        a = unit(self.P[1] - self.P[0]) if len(self.P) > 1 else np.array([1.0, 0, 0])
        a = unit(a - n * float(a @ n))
        return a, np.cross(n, a), n


# ---------------------------------------------------------------------------------------------- geometria 2D
def _in_poly(pt, poly):
    x, y = pt
    ins = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-300) + x0:
            ins = not ins
    return ins


def _dist_poly(pt, poly):
    best = 1e18
    n = len(poly)
    p = np.asarray(pt, float)
    for i in range(n):
        a, b = np.asarray(poly[i], float), np.asarray(poly[(i + 1) % n], float)
        ab = b - a
        L2 = float(ab @ ab)
        s = 0.0 if L2 < 1e-18 else min(1.0, max(0.0, float((p - a) @ ab) / L2))
        best = min(best, float(np.linalg.norm(p - (a + s * ab))))
    return best


def _near_plate(pl: Plate, x, margin):
    """¿El punto 3D x (ya sobre el plano de `pl`) cae dentro del contorno de la placa o a menos de `margin` de él?"""
    a, b, _n = pl.basis()
    c = pl.c
    poly = [((q - c) @ a, (q - c) @ b) for q in pl.P]
    pt = ((x - c) @ a, (x - c) @ b)
    return _in_poly(pt, poly) or _dist_poly(pt, poly) <= margin


def _clip_plane(P, p0, nrm):
    """Recorta el poligono 3D P conservando nrm·(x − p0) <= 0 (Sutherland–Hodgman)."""
    out = []
    n = len(P)
    f = [float(nrm @ (q - p0)) for q in P]
    for i in range(n):
        q, r = P[i], P[(i + 1) % n]
        fq, fr = f[i], f[(i + 1) % n]
        if fq <= 0:
            out.append(q)
        if (fq < 0 < fr) or (fr < 0 < fq):
            s = fq / (fq - fr)
            out.append(q + s * (r - q))
    return np.array(out) if len(out) >= 3 else None


def _is_rect(poly):
    if len(poly) != 4:
        return None
    xs = sorted({round(float(q[0]), 7) for q in poly})
    ys = sorted({round(float(q[1]), 7) for q in poly})
    if len(xs) == 2 and len(ys) == 2:
        return xs[0], xs[1], ys[0], ys[1]
    return None


# ---------------------------------------------------------------------------------------------- prismas -> placas
def _oriented_rect(poly, tol=1e-6):
    """Si el poligono (u, v) es un rectangulo (con cualquier giro): (centro, e1, a, e2, b) con lados a (a lo largo de e1) y b (a lo largo de e2); si no, None."""
    if len(poly) != 4:
        return None
    P = [np.asarray(q, float) for q in poly]
    e = [P[(i + 1) % 4] - P[i] for i in range(4)]
    L = [float(np.linalg.norm(x)) for x in e]
    if min(L) < 1e-9:
        return None
    for i in range(4):
        if abs(float(e[i] @ e[(i + 1) % 4])) > 1e-5 * L[i] * L[(i + 1) % 4] + tol:
            return None
    return (sum(P) / 4.0, e[0] / L[0], L[0], e[1] / L[1], L[1])


def _skeleton(poly):
    """Linea media de un poligono delgado (u, v): [(p0, p1, espesor)].  Diagrama de Voronoi del contorno muestreado; se descartan las ramas que salen hacia las esquinas
    (aristas entre muestras vecinas del contorno), se podan los ramales cortos, se simplifican las cadenas y se prolongan los extremos libres hasta el borde."""
    from scipy.spatial import Voronoi, cKDTree
    from matplotlib.path import Path
    P = np.asarray(poly, float)
    n = len(P)
    A = 0.5 * abs(sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n)))
    per = sum(float(np.linalg.norm(P[(i + 1) % n] - P[i])) for i in range(n))
    if A < 1e-9 or per < 1e-9:
        return []
    t_est = 2.0 * A / per
    ds = max(t_est / 5.0, per / 900.0)
    pts = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        k = max(1, int(math.ceil(float(np.linalg.norm(b - a)) / ds)))
        for j in range(k):
            pts.append(a + (b - a) * j / k)
    pts = np.array(pts)
    m = len(pts)
    if m < 8:
        return []
    vor = Voronoi(pts)
    inside = Path(np.vstack([P, P[0]])).contains_points(vor.vertices)
    tree = cKDTree(pts)
    rad = tree.query(vor.vertices)[0]
    min_sep = 10                                                                   # muestras (~2 espesores) de separacion a lo largo del contorno
    edges = {}
    for (i, j), (v0, v1) in zip(vor.ridge_points, vor.ridge_vertices):
        if v0 < 0 or v1 < 0 or not inside[v0] or not inside[v1]:
            continue
        d = abs(int(i) - int(j))
        d = min(d, m - d)
        if d <= min_sep:
            continue
        edges.setdefault(int(v0), set()).add(int(v1))
        edges.setdefault(int(v1), set()).add(int(v0))
    if not edges:
        return []
    V = vor.vertices

    def length(a, b):
        return float(np.linalg.norm(V[a] - V[b]))
    # poda de ramales cortos: desde cada hoja se recorre la cadena hasta un nodo de bifurcacion; si mide menos de 1.5 veces el espesor local se elimina
    changed = True
    while changed:
        changed = False
        for leaf in [u for u, nb in edges.items() if len(nb) == 1]:
            if leaf not in edges or len(edges[leaf]) != 1:
                continue
            chain, prev, cur, L = [leaf], None, leaf, 0.0
            while True:
                nxt = [x for x in edges[cur] if x != prev]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                L += length(prev, cur)
                if len(edges[cur]) != 2:
                    break
                chain.append(cur)
            if len(edges[cur]) >= 3 and L < 1.5 * 2.0 * float(rad[cur]):
                for v in chain:
                    for w in list(edges[v]):
                        edges[w].discard(v)
                    del edges[v]
                changed = True
    for v in [u for u, nb in edges.items() if not nb]:
        del edges[v]
    if not edges:
        return []
    # cadenas entre nodos de grado distinto de 2
    seen, chains = set(), []
    nodes = [v for v, nb in edges.items() if len(nb) != 2]
    starts = nodes if nodes else [next(iter(edges))]
    for s0 in starts:
        for nb in edges[s0]:
            if (s0, nb) in seen:
                continue
            chain, prev, cur = [s0], s0, nb
            seen.add((s0, nb))
            while True:
                chain.append(cur)
                if len(edges[cur]) != 2 or cur == s0:
                    break
                nxt = [x for x in edges[cur] if x != prev][0]
                seen.add((cur, nxt))
                prev, cur = cur, nxt
            seen.add((chain[-1], chain[-2]))
            chains.append(chain)

    def dp(idx, tol):                                                                  # Douglas–Peucker sobre los indices de una cadena
        if len(idx) < 3:
            return idx
        a, b = V[idx[0]], V[idx[-1]]
        ab = b - a
        L = float(np.linalg.norm(ab))
        best, bi = -1.0, 0
        for k in range(1, len(idx) - 1):
            q = V[idx[k]] - a
            dist = abs(float(ab[0] * q[1] - ab[1] * q[0])) / L if L > 1e-12 else float(np.linalg.norm(q))
            if dist > best:
                best, bi = dist, k
        if best <= tol:
            return [idx[0], idx[-1]]
        return dp(idx[:bi + 1], tol)[:-1] + dp(idx[bi:], tol)
    deg = {v: len(nb) for v, nb in edges.items()}
    segs = []
    for ch in chains:
        rm = float(np.mean([rad[v] for v in ch]))
        simp = dp(ch, 0.25 * 2.0 * rm)
        for a, b in zip(simp[:-1], simp[1:]):
            ia, ib = ch.index(a), ch.index(b)
            rr = float(np.mean([rad[v] for v in ch[min(ia, ib):max(ia, ib) + 1]]))
            p0, p1 = V[a].copy(), V[b].copy()
            d = p1 - p0
            Ld = float(np.linalg.norm(d))
            if Ld < 1e-9:
                continue
            d /= Ld
            if deg[a] == 1:                                                           # extremo libre: se prolonga hasta el borde
                p0 = p0 - d * float(rad[a])
            if deg[b] == 1:
                p1 = p1 + d * float(rad[b])
            segs.append([p0, p1, 2.0 * rr])
    return _join_segments(segs)


def _join_segments(segs):
    """Une las placas de la linea media: quita los tramos cortos de las esquinas, lleva a la interseccion los extremos que quedan cerca de otro tramo (esquina en L) y
    parte el otro tramo donde llega un extremo libre (union en T), de modo que las placas compartan arista."""
    segs = [[np.asarray(a, float), np.asarray(b, float), float(t)] for a, b, t in segs]

    def seglen(sg):
        return float(np.linalg.norm(sg[1] - sg[0]))

    def line_x(p, d, q, e):                                   # interseccion de las rectas p + s d y q + u e (None si son casi paralelas)
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-6:
            return None
        w = q - p
        return float((w[0] * e[1] - w[1] * e[0]) / den), float((w[0] * d[1] - w[1] * d[0]) / den)
    # 1. tramos cortos de esquina: se eliminan si algun otro tramo termina cerca de cada uno de sus extremos
    changed = True
    while changed:
        changed = False
        for i, sg in enumerate(segs):
            if seglen(sg) < 1.7 * sg[2] and len(segs) > 2:
                segs.pop(i)
                changed = True
                break
    # 2. esquinas en L: extremos cercanos de dos tramos no paralelos -> a la interseccion de sus rectas
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            A, B = segs[i], segs[j]
            dA, dB = unit(A[1] - A[0]), unit(B[1] - B[0])
            if abs(float(dA[0] * dB[1] - dA[1] * dB[0])) < 0.2:
                continue
            for ka in (0, 1):
                for kb in (0, 1):
                    if float(np.linalg.norm(A[ka] - B[kb])) < 2.2 * max(A[2], B[2]):
                        r = line_x(A[ka], dA, B[kb], dB)
                        if r is None:
                            continue
                        X = A[ka] + r[0] * dA
                        if float(np.linalg.norm(X - A[ka])) < 3.0 * max(A[2], B[2]) and float(np.linalg.norm(X - B[kb])) < 3.0 * max(A[2], B[2]):
                            A[ka], B[kb] = X.copy(), X.copy()
    # 3. extremos libres que llegan a otro tramo: se prolongan hasta el y se parte el otro tramo (union en T)
    def free(p, skip):
        return all(float(np.linalg.norm(p - q)) > 1e-6 for k, sg in enumerate(segs) if k != skip for q in (sg[0], sg[1]))
    for i in range(len(segs)):
        for ka in (0, 1):
            A = segs[i]
            p = A[ka]
            if not free(p, i):
                continue
            d = unit(A[ka] - A[1 - ka])
            best = None
            for j, B in enumerate(segs):
                if j == i:
                    continue
                e = B[1] - B[0]
                Lb = float(np.linalg.norm(e))
                r = line_x(p, d, B[0], e / Lb)
                if r is None:
                    continue
                s_, u_ = r
                if -0.2 * A[2] <= s_ <= 2.5 * (A[2] + B[2]) and -0.3 * B[2] <= u_ <= Lb + 0.3 * B[2]:
                    if best is None or s_ < best[0]:
                        best = (s_, j, u_, Lb)
            if best is not None:
                s_, j, u_, Lb = best
                B = segs[j]
                X = p + s_ * d
                A[ka] = X.copy()
                u_ = min(max(u_, 0.0), Lb)
                if 0.4 * B[2] < u_ < Lb - 0.4 * B[2]:
                    segs.append([X.copy(), B[1].copy(), B[2]])
                    B[1] = X.copy()
                elif u_ <= 0.4 * B[2]:
                    B[0] = X.copy()
                else:
                    B[1] = X.copy()
    return [(a, b, t) for a, b, t in segs if float(np.linalg.norm(b - a)) > 1e-6]


def _prism_plates(part, ip, pr, notes):
    U, V, W = (np.asarray(x, float) for x in (pr.U, pr.V, pr.W))
    o = np.asarray(pr.o, float)
    w0, w1 = float(pr.w0), float(pr.w1)
    tw = w1 - w0
    g = lambda u, v, w: o + u * U + v * V + w * W                                  # noqa: E731
    out = []

    def add(k, P, t, n, holes=()):
        P = np.asarray(P, float)
        for pl_cut in pr.cut_planes:                                                 # recortes planos del prisma (bisel de cartela, inglete)
            p0, nrm = np.asarray(pl_cut[0], float), unit(pl_cut[1])
            P = _clip_plane(P, p0, nrm)
            if P is None:
                return
        P = _clean(P)                                                                # sin vertices colineales (si no, el ajuste de bordes deja astillas)
        if P is None:
            return
        out.append(Plate(f"{part.name}#{ip}.{k}", part.name, part.kind, P, float(t), unit(n), [np.asarray(h, float) for h in holes]))

    def facets(cx, cy, rm, t, ns=24, k0=0):                                          # cilindro de radio medio rm como facetas planas
        ang = 2 * math.pi * np.arange(ns + 1) / ns
        lo, hi = np.full(ns + 1, w0), np.full(ns + 1, w1)
        for cut in getattr(pr, "cut_cyls", None) or []:                              # boca de pez: cada arista de faceta se recorta donde cruza el cilindro de corte
            from .model3d import cyl_roots
            s1, s2, ok = cyl_roots(pr, cx + rm * np.cos(ang), cy + rm * np.sin(ang), cut)
            if int(cut[3]) < 0:
                lo = np.where(ok, np.maximum(lo, s2), lo)
            else:
                hi = np.where(ok, np.minimum(hi, s1), hi)
        hi = np.maximum(hi, lo)
        for k in range(ns):
            a0, a1 = ang[k], ang[k + 1]
            p00, p10 = g(cx + rm * math.cos(a0), cy + rm * math.sin(a0), lo[k]), g(cx + rm * math.cos(a1), cy + rm * math.sin(a1), lo[k + 1])
            p11, p01 = g(cx + rm * math.cos(a1), cy + rm * math.sin(a1), hi[k + 1]), g(cx + rm * math.cos(a0), cy + rm * math.sin(a0), hi[k])
            am = 0.5 * (a0 + a1)
            add(k0 + k, [p00, p10, p11, p01], t, math.cos(am) * U + math.sin(am) * V)

    if pr.circle is not None:                                                         # cilindro / tubo redondo: facetas sobre el radio medio
        ro, ri = pr.circle
        cx0, cy0 = 0.0, 0.0
        if ri > 0:
            facets(cx0, cy0, ro - (ro - ri) / 2.0, ro - ri)
        else:                                                                           # barra maciza: tubo equivalente de igual area (rm = ro/2, t = ro)
            notes.append(f"{part.name}: barra maciza; se modela como un tubo de igual área (las placas no representan un sólido).")
            facets(cx0, cy0, ro / 2.0, ro)
        return out
    poly = [(float(q[0]), float(q[1])) for q in pr.poly]
    if pr.holes:                                                                       # tubo poligonal: paredes entre exterior e interior
        inner = [(float(q[0]), float(q[1])) for q in pr.holes[0]]
        mid = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(poly, inner)]
        N = len(mid)
        for k in range(N):
            (u0, v0), (u1, v1) = mid[k], mid[(k + 1) % N]
            e = np.array([u1 - u0, v1 - v0])
            if float(np.linalg.norm(e)) < 1e-9:
                continue
            t = 0.5 * (math.hypot(poly[k][0] - inner[k][0], poly[k][1] - inner[k][1]) + math.hypot(poly[(k + 1) % N][0] - inner[(k + 1) % N][0], poly[(k + 1) % N][1] - inner[(k + 1) % N][1])) / 1.4142
            nn = unit(e[1] * U - e[0] * V)
            add(k, [g(u0, v0, w0), g(u1, v1, w0), g(u1, v1, w1), g(u0, v0, w1)], t, nn)
        return out
    rc = _oriented_rect(poly)
    if rc is not None:
        c, e1, a, e2, b = rc
        if min(a, b) < tw * 0.999:                                                      # delgado en su propio plano (ala, alma, pared), con cualquier giro
            e_thin, e_long, t, Ll = (e1, e2, a, b) if a <= b else (e2, e1, b, a)
            p0, p1 = c - e_long * Ll / 2.0, c + e_long * Ll / 2.0
            add(0, [g(p0[0], p0[1], w0), g(p1[0], p1[1], w0), g(p1[0], p1[1], w1), g(p0[0], p0[1], w1)], t, e_thin[0] * U + e_thin[1] * V)
            return out
    elif len(poly) == 6:                                                                # perfil L (angulo): dos piernas
        us = sorted({round(q[0], 7) for q in poly})
        vs = sorted({round(q[1], 7) for q in poly})
        if len(us) == 3 and len(vs) == 3 and min(us[1] - us[0], vs[1] - vs[0]) < tw:
            t = us[1] - us[0]
            leg_b, leg_a = us[2], vs[2]
            tv = vs[1] - vs[0]
            add(0, [g(t / 2, 0, w0), g(t / 2, leg_a, w0), g(t / 2, leg_a, w1), g(t / 2, 0, w1)], t, U)
            add(1, [g(t / 2, tv / 2, w0), g(leg_b, tv / 2, w0), g(leg_b, tv / 2, w1), g(t / 2, tv / 2, w1)], tv, V)
            return out
    area = 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))))
    per = sum(math.hypot(poly[i][0] - poly[(i + 1) % len(poly)][0], poly[i][1] - poly[(i + 1) % len(poly)][1]) for i in range(len(poly)))
    t_in = 2.0 * area / max(per, 1e-9)
    if t_in < tw * 0.999:                                                               # poligono delgado en su plano (perfil libre): linea media con su espesor
        segs = _skeleton(poly)
        if segs:
            for k, (p0, p1, t) in enumerate(segs):
                d = p1 - p0
                add(k, [g(p0[0], p0[1], w0), g(p1[0], p1[1], w0), g(p1[0], p1[1], w1), g(p0[0], p0[1], w1)], t, unit(d[1] * U - d[0] * V))
            return out
        ro_eq = math.sqrt(area / math.pi)                                                # compacto (poligono macizo): tubo equivalente de igual area
        cu, cv = sum(q[0] for q in poly) / len(poly), sum(q[1] for q in poly) / len(poly)
        notes.append(f"{part.name}: sección maciza; se modela como un tubo de igual área (las placas no representan un sólido).")
        facets(cu, cv, ro_eq / 2.0, ro_eq)
        return out
    # placa plana: el poligono a mitad del espesor
    holes = []
    for h in pr.holes_extra:
        holes.append([g(float(q[0]), float(q[1]), 0.5 * (w0 + w1)) for q in h])
    add(0, [g(u, v, 0.5 * (w0 + w1)) for (u, v) in poly], tw, W, holes)
    return out


def _clean(P, tol=1e-4):
    """Contorno sin vertices repetidos ni colineales; None si queda degenerado."""
    P = [np.asarray(q, float) for q in P]
    out = []
    for q in P:
        if not out or float(np.linalg.norm(q - out[-1])) > tol:
            out.append(q)
    if len(out) > 1 and float(np.linalg.norm(out[0] - out[-1])) <= tol:
        out.pop()
    changed = True
    while changed and len(out) >= 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            ab, bc = b - a, c - b
            if float(np.linalg.norm(np.cross(ab, bc))) <= 1e-6 * max(float(np.linalg.norm(ab)) * float(np.linalg.norm(bc)), 1e-12) + 1e-9:
                out.pop(i)
                changed = True
                break
    if len(out) < 3:
        return None
    A = np.zeros(3)
    for i in range(len(out)):
        A += np.cross(out[i], out[(i + 1) % len(out)])
    return np.array(out) if float(np.linalg.norm(A)) / 2.0 > 1e-4 else None


def build_plates(mdl):
    """(placas, notas) del modelo 3D."""
    plates, notes = [], []
    for part in mdl.parts:
        for ip, pr in enumerate(part.prisms):
            plates += _prism_plates(part, ip, pr, notes)
    snap_plates(plates)
    add_bolt_holes(mdl, plates)
    out = []
    for pl in plates:                                                                # tras el ajuste pueden quedar vertices repetidos o placas colapsadas
        P = _clean(pl.P)
        if P is None:
            msg = f"{pl.part}: una placa quedó degenerada y se omite del modelo de placas."
            if msg not in notes:
                notes.append(msg)
            continue
        pl.P = P
        out.append(pl)
    return out, notes


# ---------------------------------------------------------------------------------------------- uniones
def snap_plates(plates, gap_tol=0.06):
    """Lleva cada borde que apoya contra la superficie de otra placa (a menos de la mitad del espesor de esa placa) hasta su superficie media."""
    for P in plates:
        n = len(P.P)
        for i in range(n):
            a, b = P.P[i].copy(), P.P[(i + 1) % n].copy()
            e = b - a
            Le = float(np.linalg.norm(e))
            if Le < 1e-6:
                continue
            ed = e / Le
            m = np.cross(P.n, ed)
            best = None
            for Q in plates:
                if Q is P:
                    continue
                nq = Q.n
                if abs(float(P.n @ nq)) > 0.9:                                     # paralelas: contacto, no union
                    continue
                if abs(float(ed @ nq)) > 0.12:                                     # el borde debe ser paralelo al plano de Q
                    continue
                cq = Q.c
                da, db = float((a - cq) @ nq), float((b - cq) @ nq)
                if abs(da - db) > 0.05:
                    continue
                if abs(da) < 1e-5 or abs(da) > Q.t / 2.0 + gap_tol:
                    continue
                mn = float(m @ nq)
                if abs(mn) < 0.35:
                    continue
                s = -da / mn
                mid = 0.5 * (a + b) + s * m
                if not _near_plate(Q, mid - float((mid - cq) @ nq) * nq, Q.t + 0.1):
                    continue
                if best is None or abs(s) < abs(best):
                    best = s
            if best is not None:
                P.P[i] = a + best * m
                P.P[(i + 1) % n] = b + best * m
    return plates


def add_bolt_holes(mdl, plates, nseg=12):
    """Agujero circular en cada placa que atraviesa un perno o anclaje (eje perpendicular a la placa y dentro de ella)."""
    by_part = {}
    for pl in plates:
        by_part.setdefault(pl.part, []).append(pl)
    for b in mdl.bolts:
        ax = unit(b.axis)
        p0 = np.asarray(b.p, float)
        for (pn, _s0, _s1) in b.grip:
            for pl in by_part.get(pn, []):
                dn = float(ax @ pl.n)
                if abs(dn) < 0.9:
                    continue
                s = float((pl.c - p0) @ pl.n) / dn
                x = p0 + s * ax
                if not _near_plate(pl, x, 0.0):
                    continue
                if _dist_poly_3d(pl, x) < 0.55 * b.dh:
                    continue
                if any(float(np.linalg.norm(np.mean(h, axis=0) - x)) < 0.6 * b.dh for h in pl.holes):          # ya hay un agujero ahi (otro perno coincidente o el agujero de la placa)
                    break
                a, bb, n_ = pl.basis()
                ring = [x + 0.5 * b.dh * (math.cos(2 * math.pi * k / nseg) * a + math.sin(2 * math.pi * k / nseg) * bb) for k in range(nseg)]
                pl.holes.append(np.array(ring))
                break


def _dist_poly_3d(pl, x):
    a, b, _n = pl.basis()
    c = pl.c
    poly = [((q - c) @ a, (q - c) @ b) for q in pl.P]
    return _dist_poly(((x - c) @ a, (x - c) @ b), poly)


# ---------------------------------------------------------------------------------------------- mallado (proceso hijo)
def shell_params(fea, mdl, f: float = 1.0) -> dict:
    fine = str(getattr(fea, "mesh3d_mode", "")).startswith("Fina")
    manual = float(getattr(fea, "mesh3d", 0.0) or 0.0)
    near = manual if manual > 0 else (0.55 if fine else 0.9)
    near *= f
    return {"h_near": near, "h_far": max(2.5 * near, 2.0), "h_hole": max(0.45 * near, 0.25), "zone": list(mdl.zone) if mdl.zone else None, "transition": 4.0 * near}


def write_job(plates, params, path):
    data = {"plates": [{"key": p.key, "part": p.part, "kind": p.kind, "t": p.t, "n": p.n.tolist(), "P": p.P.tolist(), "holes": [h.tolist() for h in p.holes]} for p in plates],
            "params": params}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def mesh_job(job: dict, out_npz: str) -> dict:
    import gmsh
    plates, P = job["plates"], job["params"]
    gmsh.initialize(["gmsh", "-nopopup"], interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)                                # el mallado 2D es rapido y en paralelo falla de forma intermitente
        gmsh.model.add("placas")
        occ = gmsh.model.occ
        surfs = []
        for pl in plates:
            def loop(pts):
                ids = [occ.addPoint(*q) for q in pts]
                lns = [occ.addLine(ids[i], ids[(i + 1) % len(ids)]) for i in range(len(ids))]
                return occ.addCurveLoop(lns)
            loops = [loop(pl["P"])] + [loop(h) for h in pl["holes"]]
            try:
                sid = occ.addPlaneSurface(loops)
            except Exception:                                                        # contorno degenerado: se omite
                sid = None
            surfs.append((2, sid) if sid is not None else None)
        flat = [s for s in surfs if s is not None]
        _out, omap = occ.fragment(flat, [])
        occ.synchronize()
        res, k = {}, 0
        for i, s in enumerate(surfs):
            if s is None:
                continue
            res[i] = [d for d in omap[k] if d[0] == 2]
            k += 1
        fld = gmsh.model.mesh.field
        ids = []
        z = P.get("zone")
        if z:
            i = fld.add("Box")
            fld.setNumber(i, "VIn", P["h_near"]); fld.setNumber(i, "VOut", P["h_far"])
            for kk, (a, b) in enumerate(zip(z[0::2], z[1::2])):
                fld.setNumber(i, "XYZ"[kk] + "Min", float(a)); fld.setNumber(i, "XYZ"[kk] + "Max", float(b))
            fld.setNumber(i, "Thickness", P["transition"])
            ids.append(i)
        else:
            i = fld.add("MathEval"); fld.setString(i, "F", str(P["h_near"])); ids.append(i)
        # refinamiento alrededor de los agujeros
        hole_curves = []
        for pl, s in zip(plates, surfs):
            if s is None or not pl["holes"]:
                continue
            for h in pl["holes"]:
                c = np.mean(h, axis=0)
                r = float(np.max(np.linalg.norm(np.asarray(h) - c, axis=1)))
                for (d_, t_) in gmsh.model.getEntitiesInBoundingBox(*(c - r - 0.05), *(c + r + 0.05), 1):
                    hole_curves.append(t_)
        if hole_curves:
            dist = fld.add("Distance")
            fld.setNumbers(dist, "CurvesList", sorted(set(hole_curves)))
            fld.setNumber(dist, "Sampling", 20)
            th = fld.add("Threshold")
            fld.setNumber(th, "InField", dist)
            fld.setNumber(th, "SizeMin", P["h_hole"]); fld.setNumber(th, "SizeMax", 1e22)
            fld.setNumber(th, "DistMin", 0.1); fld.setNumber(th, "DistMax", 0.1 + 2.0 * P["h_hole"])
            ids.append(th)
        fm = fld.add("Min")
        fld.setNumbers(fm, "FieldsList", ids)
        fld.setAsBackgroundMesh(fm)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.05)
        gmsh.option.setNumber("Mesh.MeshSizeMax", max(P["h_far"], 1.0) * 2)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 0)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(2)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(tags)
        out = {"node_id": np.asarray(tags, np.int64)[order], "xyz": np.asarray(xyz, float).reshape(-1, 3)[order]}
        keys = []
        for i, pl in enumerate(plates):
            tri, quad = [], []
            for (_d, st) in res.get(i, []):
                et, _etag, enode = gmsh.model.mesh.getElements(2, st)
                for t_, en in zip(et, enode):
                    if t_ == 2:
                        tri.append(np.asarray(en, np.int64).reshape(-1, 3))
                    elif t_ == 3:
                        quad.append(np.asarray(en, np.int64).reshape(-1, 4))
            out[f"t_{i}"] = np.concatenate(tri) if tri else np.zeros((0, 3), np.int64)
            out[f"q_{i}"] = np.concatenate(quad) if quad else np.zeros((0, 4), np.int64)
            keys.append(pl["key"])
        out["keys"] = np.array(json.dumps(keys))
        out["parts"] = np.array(json.dumps([p["part"] for p in plates]))
        out["kinds"] = np.array(json.dumps([p["kind"] for p in plates]))
        out["thick"] = np.array([p["t"] for p in plates], float)
        np.savez_compressed(out_npz, **out)
        n_el = int(sum(len(out[f"t_{i}"]) + len(out[f"q_{i}"]) for i in range(len(plates))))
        return {"nodes": int(len(tags)), "elems": n_el}
    finally:
        gmsh.finalize()


def child(job_json: str, out_npz: str) -> int:
    with open(job_json, encoding="utf-8") as f:
        job = json.load(f)
    info = mesh_job(job, out_npz)
    print(json.dumps(info))
    return 0 if os.path.exists(out_npz) else 3


class ShellMesh:
    """Malla de placas leida del .npz: nodos, y por placa sus triangulos y cuadrilateros (indices a `xyz`)."""

    def __init__(self, path):
        z = np.load(path, allow_pickle=False)
        self.node_ids = z["node_id"]
        self.xyz = z["xyz"]
        self.keys = json.loads(str(z["keys"]))
        self.parts = json.loads(str(z["parts"]))
        self.kinds = json.loads(str(z["kinds"]))
        self.thick = z["thick"]
        self.tri = [z[f"t_{i}"] for i in range(len(self.keys))]
        self.quad = [z[f"q_{i}"] for i in range(len(self.keys))]
        self.index = {int(n): i for i, n in enumerate(self.node_ids)}

    @property
    def n_elems(self):
        return int(sum(len(t) for t in self.tri) + sum(len(q) for q in self.quad))

    def polygons(self, i):
        """Poligonos (3 o 4 vertices) de la placa i."""
        out = []
        for row in self.tri[i]:
            out.append([tuple(self.xyz[self.index[int(n)]]) for n in row])
        for row in self.quad[i]:
            out.append([tuple(self.xyz[self.index[int(n)]]) for n in row])
        return out
