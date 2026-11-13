# -*- coding: utf-8 -*-
"""Resta de polígonos convexos en 2D (P − C) para recortar placas contra la sección de otro elemento.

`subtract(P, C)` devuelve [(contorno, huecos, bordes_de_contacto)]: los polígonos que quedan de P (CCW), los huecos (CW) si C queda dentro de P, y los
segmentos del contorno de C que forman parte del borde del resultado (donde la placa apoya contra el elemento: ahí va la soldadura).
"""
from __future__ import annotations
import math

EPS = 1e-9


def area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))


def ccw(poly):
    return list(poly) if area(poly) >= 0 else list(reversed(poly))


def hull(pts):
    P = sorted(set((round(float(p[0]), 7), round(float(p[1]), 7)) for p in pts))
    if len(P) <= 2:
        return P
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])      # noqa: E731
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 1e-12:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 1e-12:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def inside_convex(pt, C, tol=1e-9):
    """¿El punto está dentro (estricto, con tolerancia) del polígono convexo CCW C?"""
    n = len(C)
    for i in range(n):
        a, b = C[i], C[(i + 1) % n]
        if (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0]) <= tol:
            return False
    return True


def _seg_int(p, p2, q, q2):
    """Intersección de los segmentos p-p2 y q-q2: (t sobre p, u sobre q) o None."""
    rx, ry = p2[0] - p[0], p2[1] - p[1]
    sx, sy = q2[0] - q[0], q2[1] - q[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    qpx, qpy = q[0] - p[0], q[1] - p[1]
    t = (qpx * sy - qpy * sx) / den
    u = (qpx * ry - qpy * rx) / den
    if t <= EPS or t >= 1 - EPS or u <= EPS or u >= 1 - EPS:
        return None
    return t, u


def _clip_halfplane(poly, a, b, keep_left=True):
    """Parte de `poly` a la izquierda (o derecha) de la recta a→b (Sutherland–Hodgman)."""
    sgn = 1.0 if keep_left else -1.0
    f = lambda p: sgn * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))     # noqa: E731
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = f(p), f(q)
        if fp >= 0:
            out.append(p)
        if (fp > 0 > fq) or (fq > 0 > fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def intersect_convex(P, C):
    """P ∩ C para convexos (CCW)."""
    out = list(P)
    n = len(C)
    for i in range(n):
        if len(out) < 3:
            return []
        out = _clip_halfplane(out, C[i], C[(i + 1) % n], True)
    return out if len(out) >= 3 and abs(area(out)) > 1e-9 else []


def subtract(P, C):
    """P − C con P y C polígonos simples CCW (C convexo).  -> [(contorno, huecos, bordes de contacto)]"""
    P, C = ccw(P), ccw(C)
    nP, nC = len(P), len(C)
    # nodos de P y de C con las intersecciones insertadas
    pe = [[] for _ in range(nP)]
    ce = [[] for _ in range(nC)]
    pts = []
    for i in range(nP):
        for j in range(nC):
            r = _seg_int(P[i], P[(i + 1) % nP], C[j], C[(j + 1) % nC])
            if r:
                t, u = r
                k = len(pts)
                pts.append((P[i][0] + t * (P[(i + 1) % nP][0] - P[i][0]), P[i][1] + t * (P[(i + 1) % nP][1] - P[i][1])))
                pe[i].append((t, k))
                ce[j].append((u, k))
    if not pts:
        c_in_p = all(_point_in_poly(c, P) for c in C)
        p_in_c = all(inside_convex(p, C, -1e-9) or _on_or_in(p, C) for p in P)
        if p_in_c and not c_in_p:
            return []
        if c_in_p:
            return [(P, [list(reversed(C))], [(C[i], C[(i + 1) % nC]) for i in range(nC)])]
        return [(P, [], [])]
    # lista circular de P: ('v', punto) o ('i', k)
    Pl = []
    for i in range(nP):
        Pl.append(("v", P[i]))
        for t, k in sorted(pe[i]):
            Pl.append(("i", k))
    Cl = []
    for j in range(nC):
        Cl.append(("v", C[j]))
        for u, k in sorted(ce[j]):
            Cl.append(("i", k))
    pt_of = lambda it: it[1] if it[0] == "v" else pts[it[1]]            # noqa: E731
    posP = {it[1]: n for n, it in enumerate(Pl) if it[0] == "i"}
    posC = {it[1]: n for n, it in enumerate(Cl) if it[0] == "i"}
    # entra en C: el tramo que sigue a la intersección está dentro de C
    def goes_inside(n):
        a, b = pt_of(Pl[n]), pt_of(Pl[(n + 1) % len(Pl)])
        return _on_or_in(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), C, strict=True)
    enters = [n for n, it in enumerate(Pl) if it[0] == "i" and goes_inside(n)]
    exits = [n for n, it in enumerate(Pl) if it[0] == "i" and not goes_inside(n)]
    if not exits:
        return [] if all(_on_or_in(p, C) for p in P) else [(P, [], [])]
    out, used = [], set()
    for s in exits:
        if s in used:
            continue
        loop, contact = [], []
        n = s
        guard = 0
        while guard < 4 * (len(Pl) + len(Cl)):
            guard += 1
            used.add(n)
            loop.append(pt_of(Pl[n]))
            n = (n + 1) % len(Pl)
            while Pl[n][0] == "v" or n in exits:
                if Pl[n][0] == "i":
                    break
                loop.append(pt_of(Pl[n]))
                n = (n + 1) % len(Pl)
            # llegamos a una intersección que entra en C
            if n == s:
                break
            loop.append(pt_of(Pl[n]))
            k = Pl[n][1]
            m = posC[k]
            # recorre C en sentido horario (hacia atrás) hasta la siguiente intersección
            prev = pt_of(Pl[n])
            m = (m - 1) % len(Cl)
            while Cl[m][0] == "v":
                p = pt_of(Cl[m])
                contact.append((prev, p))
                loop.append(p)
                prev = p
                m = (m - 1) % len(Cl)
            contact.append((prev, pts[Cl[m][1]]))
            n = posP[Cl[m][1]]
            if n == s:
                break
        loop = _dedup(loop)
        if len(loop) >= 3 and abs(area(loop)) > 1e-9:
            out.append((ccw(loop), [], contact))
    return out


def _dedup(poly):
    out = []
    for p in poly:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def _on_or_in(pt, C, strict=False):
    n = len(C)
    for i in range(n):
        a, b = C[i], C[(i + 1) % n]
        c = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
        if c < (1e-12 if strict else -1e-9):
            return False
    return True


def _point_in_poly(p, poly):
    x, y = p
    ins = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-300) + x0:
            ins = not ins
    return ins
