# -*- coding: utf-8 -*-
"""Caras de un `Prism` para el visor: una superficie CERRADA, con orientación hacia afuera, para cualquier combinación de contorno, huecos y recortes.

Método (todo exacto sobre piezas convexas, así no hay casos especiales por tipo de pieza):
  1. Región 2D = contorno − unión de los huecos (`holes` + `holes_extra`).  Los huecos que tocan o cruzan el borde de la placa o se superponen entre sí se
     resuelven con una resta de polígonos general (arreglo de segmentos); los demás (la inmensa mayoría: agujeros de pernos) pasan directo.
  2. La región se descompone en piezas convexas (triángulos; con recortes se unen en polígonos convexos, Hertel–Mehlhorn).  Un tubo (contorno y hueco con el
     mismo número de vértices) se descompone en trapecios.
  3. Cada pieza es un poliedro convexo (tapa, fondo y paredes).  Los planos de recorte `(punto, normal)` conservan n·(x − punto) ≤ 0: el poliedro
     convexo se recorta cara por cara y la tapa del corte es el polígono convexo que forman los puntos sobre el plano.  Las paredes entre piezas vecinas
     (internas) solo existen mientras se recorta y se descartan al final: la unión de las piezas queda como una sola superficie cerrada.
Orientación: todas las caras salen en sentido antihorario visto desde afuera (normal saliente por la regla de la mano derecha).
"""
from __future__ import annotations
import math

import numpy as np

EPS_D = 1e-7                   # in: «sobre el plano» de recorte
Q_KEY = 1e-7                   # in: celda para unir puntos iguales


# ================================================================================================ 2D básico
def area(poly):
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))


def _clean(poly):
    """Contorno sin puntos repetidos consecutivos (ni el de cierre)."""
    out = []
    for q in poly:
        q = (float(q[0]), float(q[1]))
        if not out or abs(q[0] - out[-1][0]) + abs(q[1] - out[-1][1]) > 1e-9:
            out.append(q)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) + abs(out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def _ccw(poly):
    return list(poly) if area(poly) >= 0 else list(reversed(poly))


def _cw(poly):
    return list(poly) if area(poly) <= 0 else list(reversed(poly))


def _pip_many(P, loop):
    """Paridad (par-impar) de los puntos P (m, 2) respecto de un contorno."""
    P = np.asarray(P, float).reshape(-1, 2)
    L = np.asarray(loop, float)
    ins = np.zeros(len(P), bool)
    x, y = P[:, 0], P[:, 1]
    n = len(L)
    for i in range(n):
        x0, y0 = L[i]
        x1, y1 = L[(i + 1) % n]
        if y0 == y1:
            continue
        c = (y0 > y) != (y1 > y)
        xi = (x1 - x0) * (y - y0) / (y1 - y0) + x0
        ins ^= c & (x < xi)
    return ins


def _pip(pt, loop):
    return bool(_pip_many([pt], loop)[0])


def _is_convex(poly, tol=1e-10):
    n = len(poly)
    if n < 3:
        return False
    sgn = 0
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if cr > tol:
            if sgn < 0:
                return False
            sgn = 1
        elif cr < -tol:
            if sgn > 0:
                return False
            sgn = -1
    return sgn != 0


# ================================================================================================ región = contorno − huecos
def _seg_hit(a, b, c, d, eps=1e-9):
    """¿Los segmentos a-b y c-d se tocan o se cruzan (cerrados, con tolerancia)?"""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    lr, ls = math.hypot(*r), math.hypot(*s)
    if lr < 1e-12 or ls < 1e-12:
        return False
    den = r[0] * s[1] - r[1] * s[0]
    qp = (c[0] - a[0], c[1] - a[1])
    if abs(den) > 1e-12 * lr * ls:
        t = (qp[0] * s[1] - qp[1] * s[0]) / den
        u = (qp[0] * r[1] - qp[1] * r[0]) / den
        return -eps / lr <= t <= 1 + eps / lr and -eps / ls <= u <= 1 + eps / ls
    if abs(qp[0] * r[1] - qp[1] * r[0]) > eps * lr:                      # paralelos no colineales
        return False
    t0 = (qp[0] * r[0] + qp[1] * r[1]) / (lr * lr)
    t1 = ((d[0] - a[0]) * r[0] + (d[1] - a[1]) * r[1]) / (lr * lr)
    lo, hi = min(t0, t1), max(t0, t1)
    return hi >= -eps / lr and lo <= 1 + eps / lr


def _bbox(loop):
    L = np.asarray(loop, float)
    return L[:, 0].min(), L[:, 1].min(), L[:, 0].max(), L[:, 1].max()


def _complex_holes(outer, holes, m=1e-6):
    """Índices de los huecos que no son «simples»: tocan o cruzan el contorno, quedan fuera, o su caja se cruza con la de otro hueco."""
    cplx = set()
    bb = np.array([_bbox(h) for h in holes])
    if len(holes) > 1:
        ov = ((bb[:, None, 0] <= bb[None, :, 2] + m) & (bb[None, :, 0] <= bb[:, None, 2] + m) &
              (bb[:, None, 1] <= bb[None, :, 3] + m) & (bb[None, :, 1] <= bb[:, None, 3] + m))
        np.fill_diagonal(ov, False)
        cplx |= set(int(i) for i in np.nonzero(ov.any(axis=1))[0])
    O = np.asarray(outer, float)
    ob = np.concatenate([np.minimum(O, np.roll(O, -1, axis=0)), np.maximum(O, np.roll(O, -1, axis=0))], axis=1)    # xmin ymin xmax ymax de cada arista
    for i, h in enumerate(holes):
        if i in cplx:
            continue
        if not _pip(h[0], outer):
            cplx.add(i)
            continue
        x0, y0, x1, y1 = bb[i]
        near = np.nonzero((ob[:, 0] <= x1 + m) & (ob[:, 2] >= x0 - m) & (ob[:, 1] <= y1 + m) & (ob[:, 3] >= y0 - m))[0]
        hit = False
        for e in near:
            a, b = outer[e], outer[(e + 1) % len(outer)]
            for k in range(len(h)):
                if _seg_hit(a, b, h[k], h[(k + 1) % len(h)]):
                    hit = True
                    break
            if hit:
                break
        if hit:
            cplx.add(i)
    return cplx


def _split_simple(path):
    """Parte un recorrido que pasa dos veces por un mismo vértice (agujeros que se tocan en un punto) en lazos simples."""
    out, stack, pos = [], [], {}
    for k in path:
        if k in pos:
            i = pos[k]
            out.append(stack[i:])
            for kk in stack[i + 1:]:
                pos.pop(kk, None)
            stack = stack[:i + 1]
        else:
            pos[k] = len(stack)
            stack.append(k)
    out.append(stack)
    return out


def _inner_pt(loop):
    """Punto representativo de un lazo (centro de sus vértices): sirve para saber en qué contorno cae."""
    n = len(loop)
    return (sum(q[0] for q in loop) / n, sum(q[1] for q in loop) / n)


def _arrangement(outer, holes):
    """Contorno − unión de huecos por arreglo de segmentos: devuelve [(contorno CCW, [huecos CW])] (varias piezas si los huecos parten la placa)."""
    loops = [outer] + list(holes)
    segs = []
    for L in loops:
        n = len(L)
        for i in range(n):
            a, b = L[i], L[(i + 1) % n]
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1e-12:
                segs.append((a, b))
    S = np.array([[a[0], a[1], b[0], b[1]] for a, b in segs], float)
    n = len(S)
    lo = np.minimum(S[:, 0:2], S[:, 2:4]) - 1e-7
    hi = np.maximum(S[:, 0:2], S[:, 2:4]) + 1e-7
    ov = ((lo[:, None, 0] <= hi[None, :, 0]) & (lo[None, :, 0] <= hi[:, None, 0]) &
          (lo[:, None, 1] <= hi[None, :, 1]) & (lo[None, :, 1] <= hi[:, None, 1]))
    ii, jj = np.nonzero(np.triu(ov, 1))
    ts = [[0.0, 1.0] for _ in range(n)]
    for i, j in zip(ii.tolist(), jj.tolist()):
        a = S[i, 0:2]
        r = S[i, 2:4] - a
        c = S[j, 0:2]
        s = S[j, 2:4] - c
        lr, ls = math.hypot(*r), math.hypot(*s)
        den = r[0] * s[1] - r[1] * s[0]
        qp = c - a
        if abs(den) > 1e-12 * lr * ls:
            t = (qp[0] * s[1] - qp[1] * s[0]) / den
            u = (qp[0] * r[1] - qp[1] * r[0]) / den
            if -1e-9 / lr <= t <= 1 + 1e-9 / lr and -1e-9 / ls <= u <= 1 + 1e-9 / ls:
                ts[i].append(min(max(t, 0.0), 1.0))
                ts[j].append(min(max(u, 0.0), 1.0))
        elif abs(qp[0] * r[1] - qp[1] * r[0]) <= 1e-9 * lr:                       # colineales: los extremos de uno parten al otro
            for p in (c, c + s):
                t = float((p - a) @ r) / (lr * lr)
                if 1e-9 < t < 1 - 1e-9:
                    ts[i].append(t)
            for p in (a, a + r):
                u = float((p - c) @ s) / (ls * ls)
                if 1e-9 < u < 1 - 1e-9:
                    ts[j].append(u)
    coords, edges = {}, set()

    def key(p):
        return (int(round(p[0] / Q_KEY)), int(round(p[1] / Q_KEY)))
    for k in range(n):
        a = S[k, 0:2]
        r = S[k, 2:4] - a
        prev = None
        for t in sorted(ts[k]):
            p = a + t * r
            kp = key(p)
            coords.setdefault(kp, (float(p[0]), float(p[1])))
            if prev is not None and prev != kp:
                edges.add((min(prev, kp), max(prev, kp)))
            prev = kp
    edges = sorted(edges)
    if not edges:
        return []
    A = np.array([coords[e[0]] for e in edges])
    B = np.array([coords[e[1]] for e in edges])
    D = B - A
    Ln = np.maximum(np.hypot(D[:, 0], D[:, 1]), 1e-30)
    Nl = np.stack([-D[:, 1], D[:, 0]], axis=1) / Ln[:, None]
    M = 0.5 * (A + B)
    delta = 1e-5

    def inside(P):
        m = _pip_many(P, outer)
        for h in holes:
            m &= ~_pip_many(P, h)
        return m
    inl, inr = inside(M + delta * Nl), inside(M - delta * Nl)
    kept = []
    for e, (l_, r_) in enumerate(zip(inl, inr)):
        if l_ and not r_:
            kept.append((edges[e][0], edges[e][1]))
        elif r_ and not l_:
            kept.append((edges[e][1], edges[e][0]))
    out, used = {}, set()
    for (u, v) in kept:
        out.setdefault(u, []).append(v)

    def ang(p, q):
        return math.atan2(coords[q][1] - coords[p][1], coords[q][0] - coords[p][0])
    res = []
    for e0 in kept:
        if e0 in used:
            continue
        path, cur, ok = [], e0, True
        while True:
            used.add(cur)
            path.append(cur[0])
            u, v = cur
            cands = [w for w in out.get(v, []) if (v, w) not in used or (v, w) == e0]
            if not cands:
                ok = False
                break
            if len(cands) > 1:
                rev = ang(v, u)
                cands.sort(key=lambda w: ((rev - ang(v, w)) % (2 * math.pi)) or 2 * math.pi)
            nxt = (v, cands[0])
            if nxt == e0:
                break
            cur = nxt
            if len(path) > 4 * len(kept) + 8:
                ok = False
                break
        if ok and len(path) >= 3:
            for sub in _split_simple(path):
                if len(sub) >= 3:
                    res.append(_clean([coords[k] for k in sub]))
    pos = [(area(L), L) for L in res if len(L) >= 3 and area(L) > 1e-10]
    neg = [L for L in res if len(L) >= 3 and area(L) < -1e-10]
    pos.sort(key=lambda t: t[0])
    groups = [(L, []) for _a, L in pos]
    for h in neg:
        for (L, hs) in groups:                                  # el contorno de menor área que lo contiene
            if _pip(_inner_pt(h), L):
                hs.append(h)
                break
    return groups


def _unpinch(L, hl, eps=2e-5):
    """Agujeros que se tocan en un vértice (con otro agujero o con el contorno) darían una región degenerada para el triangulador: se separa el vértice
    común `eps` (2e-5 in, invisible) hacia el centro del agujero."""
    seen = {}
    for loop in [L] + hl:
        for q in loop:
            seen[(round(q[0] / Q_KEY), round(q[1] / Q_KEY))] = seen.get((round(q[0] / Q_KEY), round(q[1] / Q_KEY)), 0) + 1
    if all(c == 1 for c in seen.values()):
        return L, hl
    out = []
    for h in hl:
        cx, cy = _inner_pt(h)
        nh = []
        for q in h:
            if seen[(round(q[0] / Q_KEY), round(q[1] / Q_KEY))] > 1:
                d = math.hypot(cx - q[0], cy - q[1])
                if d > 1e-9:
                    q = (q[0] + eps * (cx - q[0]) / d, q[1] + eps * (cy - q[1]) / d)
            nh.append(q)
        out.append(nh)
    return L, out


def region_loops(outer, holes):
    """Región = contorno − unión de huecos: [(contorno CCW, [huecos CW])]."""
    outer = _clean(outer)
    if len(outer) < 3 or abs(area(outer)) < 1e-12:
        return []
    outer = _ccw(outer)
    hs = []
    for h in holes:
        h = _clean(h)
        if len(h) >= 3 and abs(area(h)) > 1e-10:
            hs.append(_cw(h))
    if not hs:
        return [(outer, [])]
    cplx = _complex_holes(outer, hs)
    if not cplx:
        return [(outer, hs)]
    simple = [h for i, h in enumerate(hs) if i not in cplx]
    groups = _arrangement(outer, [hs[i] for i in sorted(cplx)])
    groups = [_unpinch(L, hl) for (L, hl) in groups]
    for h in simple:
        for (L, hl) in sorted(groups, key=lambda g: area(g[0])):
            if _pip(_inner_pt(h), L) and not any(_pip(_inner_pt(h), q) for q in hl):
                hl.append(h)
                break
    return groups


# ================================================================================================ descomposición convexa
def _tri_ccw(pts, t):
    a, b, c = pts[t[0]], pts[t[1]], pts[t[2]]
    cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(cr) < 1e-14:
        return None
    return list(t) if cr > 0 else [t[0], t[2], t[1]]


def _ring_quads(P, H):
    """Tubo: contorno P y hueco H con el mismo número de vértices (H[k] frente a P[k]) -> trapecios, o None si no se puede."""
    n = len(P)
    if n < 3 or len(H) != n:
        return None
    if area(P) < 0:
        P, H = P[::-1], H[::-1]
    for Hc in (H, H[::-1]):
        if area(Hc) < 0:
            continue
        tot, ok = 0.0, True
        polys = []
        for k in range(n):
            q = [P[k], P[(k + 1) % n], Hc[(k + 1) % n], Hc[k]]
            a = area(q)
            if a <= 1e-12 or not _is_convex_loose(q):
                ok = False
                break
            tot += a
            polys.append(q)
        if ok and abs(tot - (area(P) - area(Hc))) <= 1e-6 * max(area(P), 1e-9):
            return P, Hc
    return None


def _is_convex_loose(q):
    n = len(q)
    for i in range(n):
        a, b, c = q[i], q[(i + 1) % n], q[(i + 2) % n]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) < -1e-10:
            return False
    return True


def _merge_convex(pts, polys, bnd):
    """Une polígonos vecinos mientras el resultado siga siendo convexo (Hertel–Mehlhorn)."""
    polys = [list(p) for p in polys]
    alive = [True] * len(polys)
    emap = {}

    def reg(pi):
        p = polys[pi]
        for k in range(len(p)):
            e = (p[k], p[(k + 1) % len(p)])
            if e not in bnd:
                emap[e] = pi

    def convex_ids(ids):
        if len(set(ids)) != len(ids):
            return False
        m = len(ids)
        for i in range(m):
            a, b, c = pts[ids[i]], pts[ids[(i + 1) % m]], pts[ids[(i + 2) % m]]
            if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) < -1e-10:
                return False
        return True
    for pi in range(len(polys)):
        reg(pi)
    for pi in range(len(polys)):
        if not alive[pi]:
            continue
        again = True
        while again:
            again = False
            p = polys[pi]
            for k in range(len(p)):
                i, j = p[k], p[(k + 1) % len(p)]
                if (i, j) in bnd:
                    continue
                qi = emap.get((j, i))
                if qi is None or qi == pi or not alive[qi]:
                    continue
                q = polys[qi]
                kp = p.index(j)
                pc = p[kp:] + p[:kp]                          # j ... i
                kq = q.index(i)
                qc = q[kq:] + q[:kq]                          # i ... j
                merged = pc + qc[1:-1]
                if convex_ids(merged):
                    for e in [(p[x], p[(x + 1) % len(p)]) for x in range(len(p))] + [(q[x], q[(x + 1) % len(q)]) for x in range(len(q))]:
                        emap.pop(e, None)
                    polys[pi] = merged
                    alive[qi] = False
                    reg(pi)
                    again = True
                    break
    return [p for p, a in zip(polys, alive) if a]


def decompose(O, Hs, merge=False, ring=None):
    """(pts, piezas, borde): piezas convexas CCW (listas de índices de pts) que cubren la región; `borde` = aristas dirigidas del contorno (material a la izquierda)."""
    from ..geom2d import triangulate
    pts = list(O) + [q for h in Hs for q in h]
    bnd, off = set(), 0
    for loop in [O] + list(Hs):
        n = len(loop)
        for k in range(n):
            bnd.add((off + k, off + (k + 1) % n))
        off += n
    if not Hs:
        if _is_convex(O):
            return pts, [list(range(len(O)))], bnd
    elif ring is not None:                                                # tubo: trapecios entre contorno y hueco
        P, Hc = ring
        n = len(P)
        pts = list(P) + list(reversed(Hc))
        hi = lambda k: n + (n - 1 - (k % n))                              # noqa: E731
        bnd = {(k, (k + 1) % n) for k in range(n)} | {(n + j, n + (j + 1) % n) for j in range(n)}
        return pts, [[k, (k + 1) % n, hi(k + 1), hi(k)] for k in range(n)], bnd
    nO = len(O)
    for amp in (0.0, 2e-6, 2e-5, 2e-4):
        if amp:                                                           # vertices de agujeros alineados dan triangulos planos: se perturban apenas (invisible)
            rng = np.random.default_rng(int(amp * 1e7))
            jit = rng.uniform(-amp, amp, (len(pts) - nO, 2))
            pts = list(pts[:nO]) + [(q[0] + jit[k][0], q[1] + jit[k][1]) for k, q in enumerate(pts[nO:])]
            O2, Hs2, off = pts[:nO], [], nO
            for h in Hs:
                Hs2.append(pts[off:off + len(h)])
                off += len(h)
        else:
            O2, Hs2 = O, Hs
        polys = _triangles(pts, O2, Hs2, triangulate, bnd)
        if _conforming(polys, bnd) and abs(sum(abs(area([pts[i] for i in p])) for p in polys) - (area(O) + sum(area(h) for h in Hs))) < 1e-6 * max(1.0, abs(area(O))):
            break
    else:                                                                  # el triangulador no logra una malla conforme: franjas verticales (exacto)
        return _slab_decompose(O, Hs, merge)
    if merge:
        polys = _merge_convex(pts, polys, bnd)
    return pts, polys, bnd


def _slab_decompose(O, Hs, merge):
    """Descomposicion por franjas verticales entre abscisas consecutivas de vertices: en cada franja la region son trapecios entre aristas consecutivas
    (par-impar).  Se insertan en los lados verticales los puntos de las franjas vecinas para que la malla sea conforme."""
    loops = [O] + list(Hs)
    edges = []
    for L in loops:
        n = len(L)
        for i in range(n):
            a, b = L[i], L[(i + 1) % n]
            if abs(a[0] - b[0]) > 1e-9:
                edges.append((a, b) if a[0] < b[0] else (b, a))
    xs = sorted({round(q[0] / Q_KEY) * Q_KEY for L in loops for q in L})
    reg, pts = {}, []

    def vid(x, y):
        k = (round(x / Q_KEY), round(y / Q_KEY))
        if k not in reg:
            reg[k] = len(pts)
            pts.append((x, y))
        return reg[k]
    traps = []
    for x0, x1 in zip(xs[:-1], xs[1:]):
        if x1 - x0 < 1e-9:
            continue
        xm = 0.5 * (x0 + x1)
        cut = []
        for (a, b) in edges:
            if a[0] <= x0 + 1e-9 and b[0] >= x1 - 1e-9:
                t0, t1, tm = (x0 - a[0]) / (b[0] - a[0]), (x1 - a[0]) / (b[0] - a[0]), (xm - a[0]) / (b[0] - a[0])
                cut.append((a[1] + tm * (b[1] - a[1]), a[1] + t0 * (b[1] - a[1]), a[1] + t1 * (b[1] - a[1])))
        cut.sort()
        for k in range(0, len(cut) - 1, 2):
            lo, hi = cut[k], cut[k + 1]
            traps.append((x0, x1, lo[1], lo[2], hi[1], hi[2]))
    ys = {}
    for (x0, x1, l0, l1, h0, h1) in traps:
        for x, ya in ((x0, (l0, h0)), (x1, (l1, h1))):
            ys.setdefault(round(x / Q_KEY), set()).update(round(y / Q_KEY) for y in ya)
    ysl = {k: sorted(v) for k, v in ys.items()}
    pieces = []
    for (x0, x1, l0, l1, h0, h1) in traps:
        ring = [vid(x0, l0), vid(x1, l1)]
        for yk in ysl[round(x1 / Q_KEY)]:
            y = yk * Q_KEY
            if l1 + 1e-9 < y < h1 - 1e-9:
                ring.append(vid(x1, y))
        ring += [vid(x1, h1), vid(x0, h0)]
        for yk in reversed(ysl[round(x0 / Q_KEY)]):
            y = yk * Q_KEY
            if l0 + 1e-9 < y < h0 - 1e-9:
                ring.append(vid(x0, y))
        ring = [v for k, v in enumerate(ring) if v != ring[k - 1]]
        if len(ring) >= 3 and abs(area([pts[i] for i in ring])) > 1e-12:
            pieces.append(ring)
    ed = {(p[k], p[(k + 1) % len(p)]) for p in pieces for k in range(len(p))}
    bnd = {e for e in ed if (e[1], e[0]) not in ed}
    if merge:
        pieces = _merge_convex(pts, pieces, bnd)
    return pts, pieces, bnd


def _conforming(polys, bnd):
    """Cada arista del contorno aparece una vez y cada arista interna tiene su pareja en sentido contrario."""
    ed = {}
    for p in polys:
        for k in range(len(p)):
            e = (p[k], p[(k + 1) % len(p)])
            ed[e] = ed.get(e, 0) + 1
    if any(c != 1 for c in ed.values()):
        return False
    if any(e not in ed for e in bnd):
        return False
    return all(e in bnd or (e[1], e[0]) in ed for e in ed)


def _triangles(pts, O, Hs, triangulate, bnd):
    tris = [t for t in (_tri_ccw(pts, t) for t in triangulate(O, Hs)) if t]
    polys = [list(t) for t in tris]
    used = {i for t in polys for i in t}
    if len(used) < len(pts):                                              # el triangulador quita los vértices alineados: se devuelven a su triángulo
        eix = {}
        for pi, t in enumerate(polys):
            for k in range(len(t)):
                eix[(t[k], t[(k + 1) % len(t)])] = pi
        off = 0
        for loop in [O] + list(Hs):
            n = len(loop)
            ids = list(range(off, off + n))
            kept = [i for i in ids if i in used]
            for x in range(len(kept)):
                a, b = kept[x], kept[(x + 1) % len(kept)]
                ia, ib = a - off, b - off
                run = [off + (ia + s) % n for s in range(1, (ib - ia) % n)] if len(kept) > 1 else []
                if run and (a, b) in eix:
                    t = polys[eix[(a, b)]]
                    pos = t.index(a)
                    polys[eix[(a, b)]] = t[:pos + 1] + run + t[pos + 1:]
            off += n
    return polys


# ================================================================================================ prisma -> caras
def _ring_pts(r, nseg):
    return [(r * math.cos(2 * math.pi * k / nseg), r * math.sin(2 * math.pi * k / nseg)) for k in range(nseg)]


def prism_regions(pr, nseg=36, merge=False):
    """[(pts, piezas, borde)] de la sección del prisma (puede haber varias regiones si los huecos la parten)."""
    if pr.circle is not None:
        ro, ri = pr.circle
        outer = _ring_pts(ro, nseg)
        holes = [_ring_pts(ri, nseg)] if ri > 0 else []
        extra = [h for h in pr.holes_extra if len(h) >= 3]
    else:
        outer = list(pr.poly)
        holes = [h for h in pr.holes if len(h) >= 3]
        extra = [h for h in pr.holes_extra if len(h) >= 3]
    if len(outer) < 3:
        return []
    ring = None
    if len(holes) == 1 and not extra:
        O0 = _clean(outer)
        H0 = _clean(holes[0])
        if len(O0) == len(outer) and len(H0) == len(holes[0]):
            ring = _ring_quads(O0, H0)
    if ring is not None:
        P, Hc = ring
        return [decompose(P, [list(reversed(Hc))], merge=merge, ring=ring)]
    out = []
    for (O, Hs) in region_loops(outer, holes + extra):
        out.append(decompose(O, Hs, merge=merge))
    return out


def _unit(v):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def prism_faces(pr, nseg=36):
    """Caras (listas de puntos (x, y, z)) del prisma, ya recortado por sus `cut_planes`; superficie cerrada con normales hacia afuera."""
    o = np.asarray(pr.o, float)
    U = np.asarray(pr.U, float)
    V = np.asarray(pr.V, float)
    W = np.cross(U, V)
    w0, w1 = float(pr.w0), float(pr.w1)
    if w1 < w0:
        w0, w1 = w1, w0                                            # extrusion «al reves»: mismo solido
    planes = []
    for (pt, nrm) in pr.cut_planes:
        nn = _unit(nrm)
        if float(np.linalg.norm(nn)) < 0.5:
            continue
        planes.append((nn, float(nn @ np.asarray(pt, float))))
    out = []
    if abs(w1 - w0) < 1e-12:
        return out
    # ¿el prisma entero queda de un lado de cada plano?
    if planes:
        C = pr.corners() if pr.circle is None else _circle_corners(pr)
        live = []
        for (nn, D) in planes:
            d = C @ nn - D
            if d.max() <= EPS_D:
                continue                                           # no toca
            if d.min() >= -EPS_D:
                return []                                          # se lo lleva entero
            live.append((nn, D))
        planes = live
    regions = prism_regions(pr, nseg, merge=bool(planes))
    for (pts2, pieces, bnd) in regions:
        P = np.asarray(pts2, float).reshape(-1, 2)
        L0 = o + P[:, 0:1] * U + P[:, 1:2] * V + w0 * W
        L1 = o + P[:, 0:1] * U + P[:, 1:2] * V + w1 * W
        if planes:
            dl = [L0 @ nn - D for nn, D in planes]
            dh = [L1 @ nn - D for nn, D in planes]
        emap = {}
        for pi, piece in enumerate(pieces if planes else ()):
            m = len(piece)
            for k in range(m):
                e = (piece[k], piece[(k + 1) % m])
                if e not in bnd:
                    emap[e] = pi
        status = []                                              # 'drop' | 'plain' | 'clip' por pieza
        clipped = {}
        for pi, piece in enumerate(pieces):
            idx = piece
            need = []
            drop = False
            for k in range(len(planes)):
                vmax = max(dl[k][idx].max(), dh[k][idx].max())
                vmin = min(dl[k][idx].min(), dh[k][idx].min())
                if vmin >= -EPS_D:
                    drop = True
                    break
                if vmax > EPS_D:
                    need.append(k)
            if drop:
                status.append("drop")
                continue
            if not need:
                status.append("plain")
                continue
            m = len(idx)
            faces = [(L1[idx], 0), (L0[list(reversed(idx))], 0)]
            for k in range(m):
                i, j = idx[k], idx[(k + 1) % m]
                faces.append((np.array([L0[i], L0[j], L1[j], L1[i]]), 0 if (i, j) in bnd else 1))
            for k in need:
                faces = _clip_convex(faces, *planes[k])
                if len(faces) < 4:
                    faces = []
                    break
            if faces:
                status.append("clip")
                clipped[pi] = faces
            else:
                status.append("drop")
        for pi, piece in enumerate(pieces):
            idx = piece
            m = len(idx)
            if status[pi] == "plain":
                out.append([tuple(L1[i]) for i in idx])
                out.append([tuple(L0[i]) for i in reversed(idx)])
                for k in range(m):
                    i, j = idx[k], idx[(k + 1) % m]
                    if (i, j) in bnd:
                        out.append([tuple(L0[i]), tuple(L0[j]), tuple(L1[j]), tuple(L1[i])])
                    else:
                        qi = emap.get((j, i))
                        if qi is not None and status[qi] == "drop":      # el vecino se fue: esta pared interna cae sobre el plano de corte y es la tapa
                            out.append([tuple(L0[i]), tuple(L0[j]), tuple(L1[j]), tuple(L1[i])])
            elif status[pi] == "clip":
                for (F, tag) in clipped[pi]:
                    if tag == 0:
                        out.append([tuple(q) for q in F])
    return out


def _circle_corners(pr):
    ro = pr.circle[0]
    o = np.asarray(pr.o, float)
    U, V = np.asarray(pr.U, float), np.asarray(pr.V, float)
    W = np.cross(U, V)
    pts = []
    for w in (pr.w0, pr.w1):
        for a in range(0, 360, 15):
            pts.append(o + ro * math.cos(math.radians(a)) * U + ro * math.sin(math.radians(a)) * V + w * W)
    return np.array(pts)


def _clip_convex(faces, n, D):
    """Recorta un poliedro convexo (caras con etiqueta) conservando n·x − D ≤ 0 y le agrega la tapa del corte."""
    out, cap = [], {}
    for (P, tag) in faces:
        d = P @ n - D
        s = np.where(d > EPS_D, 1, np.where(d < -EPS_D, -1, 0))
        if (s <= 0).all():
            out.append((P, tag))
            for q in P[s == 0]:
                cap.setdefault((round(q[0] / Q_KEY), round(q[1] / Q_KEY), round(q[2] / Q_KEY)), q)
            continue
        if (s >= 0).all():
            continue
        k = len(P)
        res = []
        for i in range(k):
            j = (i + 1) % k
            if s[i] <= 0:
                res.append(P[i])
                if s[i] == 0:
                    cap.setdefault((round(P[i][0] / Q_KEY), round(P[i][1] / Q_KEY), round(P[i][2] / Q_KEY)), P[i])
            if s[i] * s[j] < 0:
                a, b, da, db = P[i], P[j], d[i], d[j]
                if tuple(a) > tuple(b):                                # mismo punto desde las dos caras vecinas
                    a, b, da, db = b, a, db, da
                q = a + (da / (da - db)) * (b - a)
                res.append(q)
                cap.setdefault((round(q[0] / Q_KEY), round(q[1] / Q_KEY), round(q[2] / Q_KEY)), q)
        if len(res) >= 3:
            out.append((np.array(res), tag))
    if len(cap) >= 3:
        Q = np.array(list(cap.values()))
        c = Q.mean(axis=0)
        ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = _unit(np.cross(n, ref))
        e2 = np.cross(n, e1)
        ang = np.arctan2((Q - c) @ e2, (Q - c) @ e1)
        Qs = Q[np.argsort(ang)]
        a2 = 0.5 * float(np.dot(n, sum(np.cross(Qs[i], Qs[(i + 1) % len(Qs)]) for i in range(len(Qs)))))
        if a2 > 1e-9:
            out.append((Qs, 0))
    return out
