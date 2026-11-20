# -*- coding: utf-8 -*-
"""
Geometria en planta.  Origen en el centroide de la placa.
Eje X = direccion B (ancho).   Eje Y = direccion N (largo).
El momento Mux produce traccion en el lado +Y.
"""
from __future__ import annotations
import math
import numpy as np

from .model import Project
from .shapes import W_SHAPE, HSS_RECT, HSS_ROUND, PIPE


# ------------------------------------------------------------------ helpers
def _rot(pts, deg):
    if abs(deg) < 1e-9:
        return pts
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def circle(r, n=72, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


def col_shift(prj: Project):
    """Desplazamiento (dx, dy) del centro de la columna respecto al centro de la placa."""
    return float(prj.section.cx), float(prj.section.cy)


def _mv(pts, prj: Project):
    """Traslada una lista de puntos a la posicion real de la columna sobre la placa."""
    dx, dy = col_shift(prj)
    if dx == 0.0 and dy == 0.0:
        return pts
    return [(x + dx, y + dy) for x, y in pts]


# ============================================================ contorno perfil
def profile_outline(prj: Project):
    """Devuelve (exterior, interior|None) ya rotados, en coordenadas de placa
    (con el desplazamiento de la columna respecto al centro de la placa)."""
    ext, inn = _profile_outline0(prj)
    return _mv(ext, prj), (_mv(inn, prj) if inn else None)


def _profile_outline0(prj: Project):
    s = prj.section.shape()
    rot = prj.section.rotation
    if s.kind == W_SHAPE:
        d, bf, tf, tw = s.d, s.bf, s.tf, s.tw
        ext = [(-bf / 2, -d / 2), (bf / 2, -d / 2), (bf / 2, -d / 2 + tf),
               (tw / 2, -d / 2 + tf), (tw / 2, d / 2 - tf), (bf / 2, d / 2 - tf),
               (bf / 2, d / 2), (-bf / 2, d / 2), (-bf / 2, d / 2 - tf),
               (-tw / 2, d / 2 - tf), (-tw / 2, -d / 2 + tf), (-bf / 2, -d / 2 + tf),
               (-bf / 2, -d / 2)]
        return _rot(ext, rot), None
    if s.kind == HSS_RECT:
        Ht, B, t = s.d, s.bf, s.tw
        ext = [(-B / 2, -Ht / 2), (B / 2, -Ht / 2), (B / 2, Ht / 2),
               (-B / 2, Ht / 2), (-B / 2, -Ht / 2)]
        Bi, Hi = B / 2 - t, Ht / 2 - t
        inn = [(-Bi, -Hi), (Bi, -Hi), (Bi, Hi), (-Bi, Hi), (-Bi, -Hi)]
        return _rot(ext, rot), _rot(inn, rot)
    r = s.d / 2
    return circle(r), circle(r - s.tw)


def rect_poly(r):
    a, b, c, e = r
    return [(a, b), (c, b), (c, e), (a, e), (a, b)]


def section_rects(prj: Project):
    """Rectangulos de la seccion en planta, ya rotados (lista de poligonos).
    None si la seccion es redonda."""
    r = prj.section.local_rects()
    if r is None:
        return None
    return [_mv(_rot(rect_poly(q), prj.section.rotation), prj) for q in r]


def section_polys(prj: Project):
    """Poligonos para dibujar la seccion (rectangulos o circulos)."""
    rs = section_rects(prj)
    if rs is not None:
        if not prj.section.generic:
            ext, inn = profile_outline(prj)
            return [ext] + ([inn] if inn else [])
        return rs
    ext, inn = profile_outline(prj)
    return [ext] + ([inn] if inn else [])


def profile_bbox(prj: Project):
    """(ancho X, alto Y) del perfil ya rotado - usado por las formulas de DG1."""
    pts = [q for poly in section_polys(prj) for q in poly]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def inside_section(prj: Project, x, y) -> bool:
    rs = section_rects(prj)
    if rs is not None and prj.section.generic:
        return any(_inside(x, y, poly) for poly in rs)
    ext, _ = profile_outline(prj)
    return _inside(x, y, ext) and not prj.section.shape().is_hollow


def boundary_points(polys, ds=0.25):
    """Puntos sobre el contorno EXTERIOR de la union de rectangulos (las
    costuras internas entre piezas se descartan).  -> [(x, y, dL, tx, ty)]"""
    out = []
    eps = 1e-3
    for P in polys:
        for i in range(len(P) - 1):
            (x1, y1), (x2, y2) = P[i], P[i + 1]
            L = math.hypot(x2 - x1, y2 - y1)
            if L < 1e-9:
                continue
            tx, ty = (x2 - x1) / L, (y2 - y1) / L
            # normal hacia afuera del rectangulo (poligonos antihorarios)
            nx, ny = ty, -tx
            n = max(1, int(math.ceil(L / ds)))
            dL = L / n
            for k in range(n):
                xm = x1 + (k + 0.5) * dL * tx
                ym = y1 + (k + 0.5) * dL * ty
                if any(_inside(xm + nx * eps, ym + ny * eps, Q) for Q in polys):
                    continue            # costura interna entre dos piezas
                out.append((xm, ym, dL, tx, ty))
    return out


def profile_footprint(prj: Project):
    """Puntos de la linea media de las paredes/alas donde el perfil entrega
    carga a la placa.  Se usa para repartir P y M en el FEA."""
    s = prj.section.shape()
    rot = prj.section.rotation
    pts = []
    if s.kind == W_SHAPE:
        d, bf, tf, tw = s.d, s.bf, s.tf, s.tw
        for yy in (-(d - tf) / 2, (d - tf) / 2):          # alas
            for i in range(9):
                pts.append((-bf / 2 + bf * i / 8, yy))
        for i in range(1, 8):                              # alma
            pts.append((0.0, -(d / 2 - tf) + (d - 2 * tf) * i / 8))
    elif s.kind == HSS_RECT:
        Ht, B, t = s.d, s.bf, s.tw
        a, b = B / 2 - t / 2, Ht / 2 - t / 2
        for i in range(12):
            u = i / 12.0
            pts += [(-a + 2 * a * u, -b), (a, -b + 2 * b * u),
                    (a - 2 * a * u, b), (-a, b - 2 * b * u)]
    else:
        r = s.d / 2 - s.tw / 2
        pts = circle(r, 36)[:-1]
    if prj.section.generic:
        pts = []
        for a, b, c, e in prj.section.local_rects():
            if (c - a) >= (e - b):
                ym = (b + e) / 2
                pts += [(a + (c - a) * i / 8, ym) for i in range(9)]
            else:
                xm = (a + c) / 2
                pts += [(xm, b + (e - b) * i / 8) for i in range(9)]
    return _mv(_rot(pts, rot), prj)


def plate_outline(prj: Project):
    p = prj.plate
    if p.shape == "Circular":
        return circle(p.Dp / 2)
    return [(-p.B / 2, -p.N / 2), (p.B / 2, -p.N / 2), (p.B / 2, p.N / 2),
            (-p.B / 2, p.N / 2), (-p.B / 2, -p.N / 2)]


# ================================================================== pernos
def bolt_positions(prj: Project):
    """Lista de (x, y) de los centros de perno."""
    b, p = prj.bolts, prj.plate
    out = []
    if b.pattern.startswith("Coordenadas"):
        return [(float(q[0]), float(q[1])) for q in b.coords if len(q) >= 2]
    if p.shape == "Circular" or b.pattern == "Circular":
        R = (p.Dp / 2 if p.shape == "Circular" else min(p.B, p.N) / 2) - max(b.ex, b.ey)
        n = max(3, b.n_circ)
        for i in range(n):
            a = 2 * math.pi * i / n + math.pi / n
            out.append((R * math.cos(a), R * math.sin(a)))
        return out

    X = p.B / 2 - b.ex
    Y = p.N / 2 - b.ey
    nx, ny = max(2, b.n_major), max(2, b.n_minor)
    xs = [-X + 2 * X * i / (nx - 1) for i in range(nx)]
    ys = [-Y + 2 * Y * j / (ny - 1) for j in range(ny)]

    if b.pattern.startswith("Perimetral"):
        for x in xs:
            out.append((x, -Y))
            out.append((x, Y))
        for y in ys[1:-1]:
            out.append((-X, y))
            out.append((X, y))
    elif "mayor" in b.pattern:
        for x in xs:
            out += [(x, -Y), (x, Y)]
    else:
        for y in ys:
            out += [(-X, y), (X, y)]
    # elimina duplicados por redondeo
    uniq = []
    for q in out:
        if not any(abs(q[0] - u[0]) < 1e-6 and abs(q[1] - u[1]) < 1e-6 for u in uniq):
            uniq.append(q)
    return uniq


def tension_group(prj: Project, positions=None):
    """Pernos del lado traccionado (+Y).  -> (lista, n, f, xmin, xmax, ymin, ymax)"""
    pos = positions if positions is not None else bolt_positions(prj)
    tol = 1e-3 * max(prj.plate.Nc, 1.0)
    grp = [q for q in pos if q[1] > tol]
    if not grp:
        grp = [max(pos, key=lambda q: q[1])] if pos else [(0.0, 0.0)]
    ys = [q[1] for q in grp]
    xs = [q[0] for q in grp]
    return grp, len(grp), sum(ys) / len(ys), min(xs), max(xs), min(ys), max(ys)


# ============================================================== llave de corte
def lug_rects(prj: Project):
    """Rectangulos en planta de la llave de corte (poligonos rotados).
    Devuelve (lista, es_redonda, radio_ext, espesor)."""
    L = prj.lug
    if not L.enabled:
        return [], False, 0.0, 0.0
    if L.is_section:
        sh = L.shape()
        r = sh.rects()
        if r is None:
            return [], True, sh.d / 2.0, sh.tw
        return [_rot(rect_poly(q), L.rotation) for q in r], False, 0.0, 0.0
    return lug_outline(prj), False, 0.0, 0.0


def lug_outline(prj: Project):
    """Rectangulos en planta que ocupa la llave (para el dibujo)."""
    L = prj.lug
    if not L.enabled:
        return []
    if L.is_section:
        rs, rnd, ro, t = lug_rects(prj)
        return rs if not rnd else [circle(ro), circle(ro - t)]
    out = []
    if "X" in L.direction or "Ambos" in L.direction:
        out.append([(-L.W / 2, -L.t / 2), (L.W / 2, -L.t / 2),
                    (L.W / 2, L.t / 2), (-L.W / 2, L.t / 2), (-L.W / 2, -L.t / 2)])
    if "Y" in L.direction or "Ambos" in L.direction:
        out.append([(-L.t / 2, -L.W / 2), (L.t / 2, -L.W / 2),
                    (L.t / 2, L.W / 2), (-L.t / 2, L.W / 2), (-L.t / 2, -L.W / 2)])
    return out


# ============================================================== rigidizadores
def _face_offsets(prj: Project, span: float, along_bolts_axis: str):
    """Posiciones (a lo largo de la cara del perfil) de las pletinas de un lado."""
    st = prj.stiff
    n = max(1, st.count // (4 if (st.position.startswith("Perimetro") or
                                  (prj.section.shape().is_hollow and st.position == "Ambos"))
                            else 2))
    mode = st.spacing_mode

    if mode.startswith("Alineado"):
        idx = 0 if along_bolts_axis == "x" else 1
        vals = sorted({round(q[idx] - col_shift(prj)[idx], 4) for q in bolt_positions(prj)})
        vals = [v for v in vals if abs(v) <= span / 2.0 + 1e-9]
        if vals:
            if len(vals) > n:            # se queda con las n mas repartidas
                step = (len(vals) - 1) / (n - 1) if n > 1 else 0
                vals = [vals[int(round(i * step))] for i in range(n)]
            return [v + st.offset for v in vals]
        mode = "Automatico (repartido)"

    if mode.startswith("Separacion"):
        s_ = max(1e-3, st.spacing)
        base = -(n - 1) * s_ / 2.0
        return [base + i * s_ + st.offset for i in range(n)]

    if n == 1:
        return [st.offset]
    return [-span / 2.0 + span * i / (n - 1) + st.offset for i in range(n)]


def stiffener_lines(prj: Project):
    """Lineas (x1,y1,x2,y2) en planta donde apoyan las pletinas rigidizadoras.
    (No se generan para secciones genericas: angulos, canales, tes, pletinas o
    secciones dobles.)

    Se generan en el sistema LOCAL del perfil (sin rotar) y luego se giran con
    el perfil, de modo que las pletinas quedan siempre soldadas a sus caras.
    """
    if prj.section.generic:
        return []
    st = prj.stiff
    if not st.enabled or st.count <= 0:
        return []
    s = prj.section.shape()
    if s.is_round:                       # columna circular: disposicion RADIAL
        n = max(1, st.count)
        r0 = s.d / 2.0
        res = []
        for k in range(n):
            a = 2 * math.pi * k / n + math.radians(st.offset_angle)
            c, sn = math.cos(a), math.sin(a)
            (a, b), (c2, d2) = _mv([(r0 * c, r0 * sn), ((r0 + st.L) * c, (r0 + st.L) * sn)], prj)
            res.append(_clip_to_plate(prj, a, b, c2, d2))
        return [r for r in res if r is not None]
    bw, bh = (s.d, s.d) if s.is_round else (s.bf, s.d)     # dimensiones locales
    out = []
    pos = st.position

    if pos.startswith("Perimetro") or (s.is_hollow and pos == "Ambos"):
        for sign in (1, -1):
            for off in _face_offsets(prj, bw, "x"):
                y0 = sign * (bh / 2 if not s.is_round else
                             (bh / 2) * max(0.0, 1 - min(1.0, (off / (bh / 2)) ** 2)) ** 0.5)
                out.append((off, y0, off, sign * (bh / 2 + st.L)))
        for sign in (1, -1):
            for off in _face_offsets(prj, bh, "y"):
                x0 = sign * (bw / 2 if not s.is_round else
                             (bw / 2) * max(0.0, 1 - min(1.0, (off / (bw / 2)) ** 2)) ** 0.5)
                out.append((x0, off, sign * (bw / 2 + st.L), off))
    else:
        if pos.startswith("Alas") or pos == "Ambos":
            for x in _face_offsets(prj, bw, "x"):
                out.append((x, bh / 2, x, bh / 2 + st.L))
                out.append((x, -bh / 2, x, -bh / 2 - st.L))
        if pos.startswith("Alma") or pos == "Ambos":
            x0 = s.tw / 2 if s.kind == W_SHAPE else bw / 2
            for y in _face_offsets(prj, bh, "y"):
                out.append((x0, y, bw / 2 + st.L, y))
                out.append((-x0, y, -bw / 2 - st.L, y))

    rot = prj.section.rotation
    res = []
    for (x1, y1, x2, y2) in out:
        (a, b), (c, d) = _mv(_rot([(x1, y1), (x2, y2)], rot), prj)
        res.append(_clip_to_plate(prj, a, b, c, d))
    return [r for r in res if r is not None]


def _clip_to_plate(prj: Project, x1, y1, x2, y2):
    """Recorta el extremo exterior de la pletina al contorno de la placa."""
    p = prj.plate

    def inside(x, y):
        if p.shape == "Circular":
            return x * x + y * y <= (p.Dp / 2) ** 2 + 1e-9
        return abs(x) <= p.B / 2 + 1e-9 and abs(y) <= p.N / 2 + 1e-9

    if not inside(x1, y1):
        return None
    if inside(x2, y2):
        return (x1, y1, x2, y2)
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if inside(x1 + (x2 - x1) * mid, y1 + (y2 - y1) * mid):
            lo = mid
        else:
            hi = mid
    return (x1, y1, x1 + (x2 - x1) * lo, y1 + (y2 - y1) * lo)


def cantilever_reduction(prj: Project):
    """Voladizos efectivos (mx, my) cuando hay rigidizadores.

    El panel de placa entre dos rigidizadores queda apoyado en tres lados
    (cara del perfil + dos pletinas) y trabaja en la direccion corta.  Se toma:
        m_ef = max( m - L ,  min(m, s/2) )
    donde s es la separacion libre entre pletinas en esa cara.  Asi, pletinas
    muy separadas (p.ej. en las puntas de un ala ancha) casi no reducen el
    voladizo, que es lo que tambien muestra el modelo de elementos finitos.
    """
    st = prj.stiff
    s = prj.section.shape()
    bw, bh = profile_bbox(prj)
    cdx, cdy = col_shift(prj)
    Nc, Bc = prj.plate.Nc + 2 * abs(cdy), prj.plate.Bc + 2 * abs(cdx)    # columna descentrada: manda el voladizo del lado mas largo
    if prj.section.generic:
        return (Bc - 0.95 * bw) / 2.0, (Nc - 0.95 * bh) / 2.0      # (mx, my)
    my = (Nc - 0.95 * bh) / 2.0
    mx = (Bc - 0.95 * bw) / 2.0
    if not st.enabled or st.count <= 0:
        return mx, my
    if s.is_round:                       # radiales: separacion en arco a media proyeccion
        sp = 2 * math.pi * (s.d / 2.0 + st.L / 2.0) / max(1, st.count)
        m_ef = lambda m: max(m - st.L, min(m, sp / 2.0), 0.0)
        return m_ef(mx), m_ef(my)

    def eff(m, span, axis):
        offs = sorted(_face_offsets(prj, span, axis))
        if len(offs) > 1:
            sp = max(offs[i + 1] - offs[i] for i in range(len(offs) - 1))
        else:
            sp = span / 2.0
        return max(m - st.L, min(m, sp / 2.0), 0.0)

    lw, lh = (s.d, s.d) if s.is_round else (s.bf, s.d)
    pos = st.position
    if pos.startswith("Perimetro") or (s.is_hollow and pos == "Ambos"):
        my = eff(my, lw, "x")
        mx = eff(mx, lh, "y")
    else:
        if pos.startswith("Alas") or pos == "Ambos":
            my = eff(my, lw, "x")
        if pos.startswith("Alma") or pos == "Ambos":
            mx = eff(mx, lh, "y")
    return mx, my


# ============================================================ interferencias
def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _inside(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n - 1):
        (x1, y1), (x2, y2) = poly[i], poly[i + 1]
        if (y1 > py) != (y2 > py):
            if px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-15) + x1:
                c = not c
    return c


def bolt_clashes(prj: Project, clearance: float | None = None):
    """Pernos cuya tuerca/arandela interfiere con el perfil.

    Holgura minima = mitad del ancho entre caras de la tuerca + 1/2 in para
    acceso de llave y soldadura.  Devuelve lista de (indice, x, y, distancia).
    """
    g = prj.bolts.geom()
    clr = clearance if clearance is not None else g.Fhex / 2.0 + 0.5
    polys = section_polys(prj)
    out = []
    for k, (x, y) in enumerate(bolt_positions(prj)):
        d = min(_seg_dist(x, y, *P[i], *P[i + 1]) for P in polys for i in range(len(P) - 1))
        inside = inside_section(prj, x, y)
        if inside:
            out.append((k + 1, x, y, -d))
        elif d < clr and not (prj.section.shape().is_hollow and not prj.section.generic
                              and _inside(x, y, polys[0])):
            out.append((k + 1, x, y, d))
    return out


def bolt_edge_distances(prj: Project):
    """Distancia minima de cada centro de perno al borde de la placa."""
    out = plate_outline(prj)
    res = []
    for (x, y) in bolt_positions(prj):
        d = min(_seg_dist(x, y, *out[i], *out[i + 1]) for i in range(len(out) - 1))
        res.append(d if _inside(x, y, out) else -d)
    return res
