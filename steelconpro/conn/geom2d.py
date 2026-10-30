# -*- coding: utf-8 -*-
"""Geometria plana para las placas: triangulacion de un poligono con agujeros (ear clipping con puentes, como earcut), poligonos de circulos y ranuras,
y pruebas de pertenencia.  Todo en 2D (u, v)."""
from __future__ import annotations
import math


def circle_poly(cx, cy, r, n=24, start=0.0):
    return [(cx + r * math.cos(start + 2 * math.pi * k / n), cy + r * math.sin(start + 2 * math.pi * k / n)) for k in range(n)]


def obround_poly(cx, cy, L, W, rot=0.0, n_arc=10):
    """Ranura de extremos redondeados: largo total L (a lo largo de u), ancho W, girada `rot` grados alrededor de (cx, cy)."""
    r = W / 2.0
    a = max(L / 2.0 - r, 0.0)
    pts = []
    for k in range(n_arc + 1):                                    # semicirculo derecho (de -90 a +90)
        t = -math.pi / 2 + math.pi * k / n_arc
        pts.append((a + r * math.cos(t), r * math.sin(t)))
    for k in range(n_arc + 1):                                    # semicirculo izquierdo
        t = math.pi / 2 + math.pi * k / n_arc
        pts.append((-a + r * math.cos(t), r * math.sin(t)))
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in pts]


def area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))


def point_in_poly(p, poly):
    x, y = p
    ins = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-300) + x0:
            ins = not ins
    return ins


def ccw(poly):
    return list(poly) if area(poly) >= 0 else list(reversed(poly))


def cw(poly):
    return list(poly) if area(poly) <= 0 else list(reversed(poly))


# ---------------------------------------------------------------------------------------------------- triangulacion
class _N:
    __slots__ = ("i", "x", "y", "prev", "next", "steiner")

    def __init__(self, i, x, y):
        self.i, self.x, self.y = i, x, y
        self.prev = self.next = None
        self.steiner = False


def _link(pts, start, end, clockwise):
    last = None
    rng = range(start, end) if clockwise == (_signed(pts, start, end) > 0) else range(end - 1, start - 1, -1)
    for i in rng:
        last = _insert(i, pts[i][0], pts[i][1], last)
    if last and _eq(last, last.next):
        _remove(last)
        last = last.next
    return last


def _signed(pts, start, end):
    s = 0.0
    j = end - 1
    for i in range(start, end):
        s += (pts[j][0] - pts[i][0]) * (pts[i][1] + pts[j][1])
        j = i
    return s


def _insert(i, x, y, last):
    p = _N(i, x, y)
    if last is None:
        p.prev = p.next = p
    else:
        p.next = last.next
        p.prev = last
        last.next.prev = p
        last.next = p
    return p


def _remove(p):
    p.next.prev = p.prev
    p.prev.next = p.next


def _eq(a, b):
    return a.x == b.x and a.y == b.y


def _area3(p, q, r):
    return (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)


def _in_tri(ax, ay, bx, by, cx, cy, px, py):
    return (cx - px) * (ay - py) >= (ax - px) * (cy - py) and (ax - px) * (by - py) >= (bx - px) * (ay - py) and (bx - px) * (cy - py) >= (cx - px) * (by - py)


def _is_ear(ear):
    a, b, c = ear.prev, ear, ear.next
    if _area3(a, b, c) >= 0:
        return False
    p = ear.next.next
    while p is not ear.prev:
        if _in_tri(a.x, a.y, b.x, b.y, c.x, c.y, p.x, p.y) and _area3(p.prev, p, p.next) >= 0:
            return False
        p = p.next
    return True


def _filter(start, end=None):
    if start is None:
        return start
    end = end or start
    p = start
    again = True
    while again or p is not end:
        again = False
        if not p.steiner and (_eq(p, p.next) or _area3(p.prev, p, p.next) == 0):
            _remove(p)
            p = end = p.prev
            if p is p.next:
                break
            again = True
        else:
            p = p.next
    return end


def _ear_loop(ear, out, passno=0):
    if ear is None:
        return
    stop = ear
    guard = 0
    while ear.prev is not ear.next and guard < 200000:
        guard += 1
        prev, nxt = ear.prev, ear.next
        if _is_ear(ear):
            out.extend([prev.i, ear.i, nxt.i])
            _remove(ear)
            ear = nxt.next
            stop = nxt.next
            continue
        ear = nxt
        if ear is stop:
            if passno == 0:
                _ear_loop(_filter(ear), out, 1)
            elif passno == 1:
                _ear_loop(_split_fix(_filter(ear), out), out, 2)
            elif passno == 2:
                _split_ear(ear, out)
            break


def _split_fix(start, out):
    p = start
    while True:
        a, b = p.prev, p.next.next
        if not _eq(a, b) and _inter(a, p, p.next, b) and _locally_inside(a, b) and _locally_inside(b, a):
            out.extend([a.i, p.i, b.i])
            _remove(p)
            _remove(p.next)
            p = start = b
        p = p.next
        if p is start:
            break
    return _filter(p)


def _split_ear(start, out):
    a = start
    while True:
        b = a.next.next
        while b is not a.prev:
            if a.i != b.i and _valid_diag(a, b):
                c = _split_poly(a, b)
                a = _filter(a, a.next)
                c = _filter(c, c.next)
                _ear_loop(a, out)
                _ear_loop(c, out)
                return
            b = b.next
        a = a.next
        if a is start:
            break


def _sign(v):
    return 1 if v > 0 else -1 if v < 0 else 0


def _inter(p1, q1, p2, q2):
    o1, o2 = _sign(_area3(p1, q1, p2)), _sign(_area3(p1, q1, q2))
    o3, o4 = _sign(_area3(p2, q2, p1)), _sign(_area3(p2, q2, q1))
    return o1 != o2 and o3 != o4


def _locally_inside(a, b):
    if _area3(a.prev, a, a.next) < 0:
        return _area3(a, b, a.next) >= 0 and _area3(a, a.prev, b) >= 0
    return _area3(a, b, a.prev) < 0 or _area3(a, a.next, b) < 0


def _valid_diag(a, b):
    return a.next.i != b.i and a.prev.i != b.i and not _intersects_poly(a, b) and \
        (_locally_inside(a, b) and _locally_inside(b, a) and _middle_inside(a, b) and (_area3(a.prev, a, b.prev) or _area3(a, b.prev, b)) or
         _eq(a, b) and _area3(a.prev, a, a.next) > 0 and _area3(b.prev, b, b.next) > 0)


def _intersects_poly(a, b):
    p = a
    while True:
        if p.i != a.i and p.next.i != a.i and p.i != b.i and p.next.i != b.i and _inter(p, p.next, a, b):
            return True
        p = p.next
        if p is a:
            break
    return False


def _middle_inside(a, b):
    p = a
    ins = False
    px, py = (a.x + b.x) / 2, (a.y + b.y) / 2
    while True:
        if ((p.y > py) != (p.next.y > py)) and p.next.y != p.y and px < (p.next.x - p.x) * (py - p.y) / (p.next.y - p.y) + p.x:
            ins = not ins
        p = p.next
        if p is a:
            break
    return ins


def _split_poly(a, b):
    a2, b2 = _N(a.i, a.x, a.y), _N(b.i, b.x, b.y)
    an, bp = a.next, b.prev
    a.next = b
    b.prev = a
    a2.next = an
    an.prev = a2
    b2.next = a2
    a2.prev = b2
    bp.next = b2
    b2.prev = bp
    return b2


def _eliminate_holes(pts, hole_idx, outer):
    queue = []
    for k, start in enumerate(hole_idx):
        end = hole_idx[k + 1] if k + 1 < len(hole_idx) else len(pts)
        lst = _link(pts, start, end, False)
        if lst is None:
            continue
        if lst is lst.next:
            lst.steiner = True
        queue.append(_leftmost(lst))
    queue.sort(key=lambda n: n.x)
    for h in queue:
        outer = _eliminate_hole(h, outer)
    return outer


def _leftmost(start):
    p = start
    left = start
    while True:
        if p.x < left.x or (p.x == left.x and p.y < left.y):
            left = p
        p = p.next
        if p is start:
            break
    return left


def _eliminate_hole(hole, outer):
    bridge = _find_bridge(hole, outer)
    if bridge is None:
        return outer
    b2 = _split_poly(bridge, hole)
    _filter(b2, b2.next)
    return _filter(bridge, bridge.next)


def _find_bridge(hole, outer):
    p = outer
    hx, hy = hole.x, hole.y
    qx = -math.inf
    m = None
    while True:
        if hy <= p.y and hy >= p.next.y and p.next.y != p.y:
            x = p.x + (hy - p.y) * (p.next.x - p.x) / (p.next.y - p.y)
            if x <= hx and x > qx:
                qx = x
                m = p if p.x < p.next.x else p.next
                if x == hx:
                    return m
        p = p.next
        if p is outer:
            break
    if m is None:
        return None
    stop = m
    mx, my = m.x, m.y
    tan_min = math.inf
    p = m
    while True:
        if hx >= p.x and p.x >= mx and hx != p.x and _in_tri(hx if hy < my else qx, hy, mx, my, qx if hy < my else hx, hy, p.x, p.y):
            tan = abs(hy - p.y) / (hx - p.x)
            if _locally_inside(p, hole) and (tan < tan_min or (tan == tan_min and (p.x > m.x or (p.x == m.x and _sector_contains(m, p))))):
                m = p
                tan_min = tan
        p = p.next
        if p is stop:
            break
    return m


def _sector_contains(m, p):
    return _area3(m.prev, m, p.prev) < 0 and _area3(p.next, m, m.next) < 0


def triangulate(outer, holes=()):
    """Triangulos (i, j, k) de un poligono con agujeros; los indices numeran [exterior..., agujero 1..., agujero 2...]."""
    pts = list(outer)
    hole_idx = []
    for h in holes:
        hole_idx.append(len(pts))
        pts += list(h)
    n_out = len(outer)
    ring = _link(pts, 0, n_out, True)
    out = []
    if ring is None or ring.next is ring.prev:
        return out
    if hole_idx:
        ring = _eliminate_holes(pts, hole_idx, ring)
    _ear_loop(ring, out)
    return [tuple(out[i:i + 3]) for i in range(0, len(out), 3)]
