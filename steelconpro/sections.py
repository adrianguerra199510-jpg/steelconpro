# -*- coding: utf-8 -*-
"""Secciones de forma libre (Section Designer): geometria y propiedades de una seccion armada con componentes.

Una seccion es una lista de componentes (diccionarios, en in, en un sistema de ejes cualquiera: X horizontal, Y vertical):

    {"t": "rect", "x": cx, "y": cy, "w": ancho, "h": alto, "rot": grados}      rectangulo centrado en (x, y), girado `rot`
    {"t": "circ", "x": cx, "y": cy, "d": diametro}                             circulo macizo
    {"t": "ring", "x": cx, "y": cy, "d": diametro exterior, "ti": espesor}     tubo (anillo)
    {"t": "poly", "pts": [[x, y], ...]}                                       poligono simple (convexo o no)

Las propiedades (A, centroide, I, S, Z, ejes principales, J aproximada) se calculan con las formulas exactas de poligonos y circulos;
el modulo plastico Z sale del eje neutro plastico (area igual a cada lado) con recortes exactos de los poligonos.
No hay dependencias de Qt: lo usan el modelo (`shapes.py`), la geometria 3D y el Section Designer.
"""
from __future__ import annotations
import math
from typing import Callable

STEEL_LB_IN3 = 0.2836            # peso del acero, lb/in³ (490 lb/ft³)
N_CIRC = 48                      # lados del poligono que representa un circulo en el dibujo 3D
N_PLASTIC = 720                  # lados con los que se recortan circulos en el modulo plastico


# ================================================================================================== poligonos
def _ccw(poly):
    a = _area(poly)
    return list(poly) if a >= 0 else list(reversed(poly))


def _area(poly) -> float:
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))


def poly_props(poly):
    """(A, cx, cy, Ixx, Iyy, Ixy) de un poligono simple; I respecto de su propio centroide (Ixx = ∫y², Iyy = ∫x²)."""
    P = _ccw(poly)
    n = len(P)
    a = cx = cy = ixx = iyy = ixy = 0.0
    for i in range(n):
        x0, y0 = P[i]
        x1, y1 = P[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
        ixx += (y0 * y0 + y0 * y1 + y1 * y1) * c
        iyy += (x0 * x0 + x0 * x1 + x1 * x1) * c
        ixy += (x0 * y1 + 2 * x0 * y0 + 2 * x1 * y1 + x1 * y0) * c
    A = a / 2.0
    if abs(A) < 1e-14:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    cx, cy = cx / (6 * A), cy / (6 * A)
    ixx, iyy, ixy = ixx / 12.0, iyy / 12.0, ixy / 24.0
    return A, cx, cy, ixx - A * cy * cy, iyy - A * cx * cx, ixy - A * cx * cy


def clip_half(poly, axis: int, pos: float, above: bool):
    """Parte del poligono con coordenada `axis` (0 = x, 1 = y) mayor (above) o menor que `pos` (Sutherland-Hodgman)."""
    sgn = 1.0 if above else -1.0
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        dp, dq = sgn * (p[axis] - pos), sgn * (q[axis] - pos)
        if dp >= 0:
            out.append(p)
        if (dp >= 0) != (dq >= 0):
            t = dp / (dp - dq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def regular_polygon(cx, cy, r, n, rot=0.0):
    return [(cx + r * math.cos(math.radians(rot) + 2 * math.pi * k / n), cy + r * math.sin(math.radians(rot) + 2 * math.pi * k / n)) for k in range(n)]


# ================================================================================================== componentes
def rect_poly(c):
    w, h, r = float(c["w"]), float(c["h"]), math.radians(float(c.get("rot", 0.0)))
    cs, sn = math.cos(r), math.sin(r)
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [(float(c["x"]) + u * cs - v * sn, float(c["y"]) + u * sn + v * cs) for u, v in pts]


def comp_outline(c, n=N_CIRC):
    """Contorno exterior del componente como poligono."""
    t = c["t"]
    if t == "rect":
        return rect_poly(c)
    if t == "poly":
        return [(float(x), float(y)) for x, y in c["pts"]]
    return regular_polygon(float(c["x"]), float(c["y"]), float(c["d"]) / 2.0, n)


def _signed_parts(c, n):
    """[(signo, poligono)]: el anillo es un circulo menos otro."""
    t = c["t"]
    if t == "ring":
        ro = float(c["d"]) / 2.0
        ri = max(ro - float(c["ti"]), 0.0)
        out = [(1.0, regular_polygon(float(c["x"]), float(c["y"]), ro, n))]
        if ri > 1e-9:
            out.append((-1.0, regular_polygon(float(c["x"]), float(c["y"]), ri, n)))
        return out
    return [(1.0, comp_outline(c, n))]


def comp_props(c):
    """(A, cx, cy, Ixx, Iyy, Ixy) del componente respecto de su centroide; circulos y anillos con formulas exactas."""
    t = c["t"]
    if t in ("circ", "ring"):
        ro = float(c["d"]) / 2.0
        ri = max(ro - float(c.get("ti", ro)), 0.0) if t == "ring" else 0.0
        A = math.pi * (ro * ro - ri * ri)
        I = math.pi / 4.0 * (ro ** 4 - ri ** 4)
        return A, float(c["x"]), float(c["y"]), I, I, 0.0
    return poly_props(comp_outline(c))


def comp_J(c) -> float:
    """Constante de torsion de Saint-Venant del componente aislado (rectangulo: (1/3)·b·t³·(1 − 0.63·t/b); circulo y anillo: exacto)."""
    t = c["t"]
    if t == "circ":
        return math.pi * float(c["d"]) ** 4 / 32.0
    if t == "ring":
        ro = float(c["d"]) / 2.0
        ri = max(ro - float(c["ti"]), 0.0)
        return math.pi / 2.0 * (ro ** 4 - ri ** 4)
    if t == "rect":
        b, tt = max(float(c["w"]), float(c["h"])), min(float(c["w"]), float(c["h"]))
        return b * tt ** 3 / 3.0 * (1.0 - 0.63 * tt / b) if b > 0 else 0.0
    P = comp_outline(c)
    A = abs(_area(P))
    per = sum(math.hypot(P[(i + 1) % len(P)][0] - P[i][0], P[(i + 1) % len(P)][1] - P[i][1]) for i in range(len(P)))
    if per <= 0:
        return 0.0
    tt = 2.0 * A / per                                   # espesor equivalente de una placa delgada con el mismo area y perimetro
    return (per / 2.0) * tt ** 3 / 3.0


def comp_bounds(c):
    """(xmin, ymin, xmax, ymax) del componente."""
    t = c["t"]
    if t in ("circ", "ring"):
        r = float(c["d"]) / 2.0
        return float(c["x"]) - r, float(c["y"]) - r, float(c["x"]) + r, float(c["y"]) + r
    P = comp_outline(c)
    xs, ys = [p[0] for p in P], [p[1] for p in P]
    return min(xs), min(ys), max(xs), max(ys)


def valid_comp(c) -> str:
    """Texto con el problema del componente, o vacio si esta bien."""
    try:
        t = c["t"]
        if t == "rect":
            if float(c["w"]) <= 0 or float(c["h"]) <= 0:
                return "el rectangulo necesita ancho y alto positivos"
        elif t == "circ":
            if float(c["d"]) <= 0:
                return "el circulo necesita diametro positivo"
        elif t == "ring":
            if float(c["d"]) <= 0 or float(c["ti"]) <= 0 or float(c["ti"]) >= float(c["d"]) / 2.0 + 1e-9:
                return "el tubo necesita diametro positivo y un espesor menor que el radio"
        elif t == "poly":
            pts = c.get("pts") or []
            if len(pts) < 3 or abs(_area(pts)) < 1e-9:
                return "el poligono necesita al menos 3 vertices y area distinta de cero"
            if _self_intersects(pts):
                return "el poligono se cruza a si mismo"
        else:
            return f"tipo de componente desconocido: {t}"
    except (KeyError, TypeError, ValueError) as e:
        return f"datos incompletos ({e})"
    return ""


def _self_intersects(pts) -> bool:
    n = len(pts)

    def ccw(a, b, c_):
        return (c_[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c_[0] - a[0])

    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if abs(i - j) in (1, n - 1):
                continue
            c_, d_ = pts[j], pts[(j + 1) % n]
            if ccw(a, c_, d_) * ccw(b, c_, d_) < 0 and ccw(a, b, c_) * ccw(a, b, d_) < 0:
                return True
    return False


# ================================================================================================== seccion completa
def _points_for_extent(comps):
    xs0, ys0, xs1, ys1 = [], [], [], []
    for c in comps:
        a, b, c1, d1 = comp_bounds(c)
        xs0.append(a); ys0.append(b); xs1.append(c1); ys1.append(d1)
    return min(xs0), min(ys0), max(xs1), max(ys1)


def section_props(comps) -> dict:
    """Propiedades de la seccion armada: A, centroide, Ix, Iy, Ixy, Sx, Sy, Zx, Zy, rx, ry, J, ejes principales, ancho y alto, peso por pie.

    Ix = ∫(y − cy)², Iy = ∫(x − cx)² (ejes del dibujo por el centroide)."""
    comps = [c for c in comps if not valid_comp(c)]
    if not comps:
        return {}
    A = sx = sy = 0.0
    for c in comps:
        a, cx, cy = comp_props(c)[:3]
        A += a; sx += a * cx; sy += a * cy
    cx, cy = sx / A, sy / A
    Ix = Iy = Ixy = 0.0
    for c in comps:
        a, ccx, ccy, ixx, iyy, ixy = comp_props(c)
        Ix += ixx + a * (ccy - cy) ** 2
        Iy += iyy + a * (ccx - cx) ** 2
        Ixy += ixy + a * (ccx - cx) * (ccy - cy)
    x0, y0, x1, y1 = _points_for_extent(comps)
    W, H = x1 - x0, y1 - y0
    cmax_y, cmax_x = max(y1 - cy, cy - y0), max(x1 - cx, cx - x0)
    avg = (Ix + Iy) / 2.0
    rad = math.sqrt(((Ix - Iy) / 2.0) ** 2 + Ixy ** 2)
    out = dict(A=A, cx=cx, cy=cy, Ix=Ix, Iy=Iy, Ixy=Ixy, I1=avg + rad, I2=avg - rad,
               theta=0.5 * math.degrees(math.atan2(-2.0 * Ixy, Ix - Iy)), W=W, H=H,
               xmin=x0 - cx, xmax=x1 - cx, ymin=y0 - cy, ymax=y1 - cy,
               Sx=Ix / cmax_y if cmax_y > 0 else 0.0, Sy=Iy / cmax_x if cmax_x > 0 else 0.0,
               rx=math.sqrt(Ix / A), ry=math.sqrt(Iy / A), J=sum(comp_J(c) for c in comps),
               Zx=_plastic(comps, 1), Zy=_plastic(comps, 0), weight=A * 12.0 * STEEL_LB_IN3)
    return out


def _plastic(comps, axis: int) -> float:
    """Modulo plastico respecto del eje que pasa por el eje neutro plastico (area igual a ambos lados); axis = 1: flexion en X (divide en Y)."""
    parts = []
    for c in comps:
        parts += _signed_parts(c, N_PLASTIC if c["t"] in ("circ", "ring") else N_CIRC)
    A = sum(s * _area(_ccw(p)) for s, p in parts)
    lo = min(q[axis] for _s, p in parts for q in p)
    hi = max(q[axis] for _s, p in parts for q in p)

    def above(pos):
        a = m = 0.0
        for s, p in parts:
            q = clip_half(_ccw(p), axis, pos, True)
            if len(q) >= 3:
                pa, c0, c1 = poly_props(q)[:3]
                a += s * pa
                m += s * pa * (c1 if axis == 1 else c0)
        return a, m

    for _ in range(80):                                       # biseccion sobre el area por encima de la posicion
        mid = 0.5 * (lo + hi)
        if above(mid)[0] > A / 2.0:
            lo = mid
        else:
            hi = mid
    pna = 0.5 * (lo + hi)
    a1, m1 = above(pna)
    a2 = A - a1
    mt = sum(s * _area(_ccw(p)) * (poly_props(p)[2] if axis == 1 else poly_props(p)[1]) for s, p in parts)
    m2 = mt - m1
    return abs(m1 - a1 * pna) + abs(a2 * pna - m2)


def overlap_area(comps, n=260) -> float:
    """Area (in²) donde dos o mas componentes se superponen (se cuenta doble en las propiedades); muestreo regular."""
    import numpy as np
    from matplotlib.path import Path
    ok = [c for c in comps if not valid_comp(c)]
    if len(ok) < 2:
        return 0.0
    x0, y0, x1, y1 = _points_for_extent(ok)
    xs = np.linspace(x0, x1, n)
    ys = np.linspace(y0, y1, n)
    X, Y = np.meshgrid((xs[:-1] + xs[1:]) / 2.0, (ys[:-1] + ys[1:]) / 2.0)
    pts = np.column_stack([X.ravel(), Y.ravel()])
    cnt = np.zeros(len(pts), int)
    for c in ok:
        ins = np.zeros(len(pts), bool)
        for s, p in _signed_parts(c, N_CIRC * 2):
            inside = Path(p).contains_points(pts)
            ins = ins | inside if s > 0 else ins & ~inside
        cnt += ins
    cell = (x1 - x0) / (n - 1) * (y1 - y0) / (n - 1)
    return float((cnt > 1).sum()) * cell


def shear_area(comps, props=None) -> float:
    """Area de cortante para la verificacion de miembros: lo que aportan las piezas mas altas que anchas (almas, paredes); si no hay, 0.5·A."""
    A = 0.0
    tot = 0.0
    for c in comps:
        if valid_comp(c):
            continue
        a = comp_props(c)[0]
        tot += a
        x0, y0, x1, y1 = comp_bounds(c)
        if c["t"] == "ring":
            A += a / 2.0
        elif (y1 - y0) >= (x1 - x0):
            A += a
    return A if A > 0 else 0.5 * tot


def pieces(comps, cx: float, cy: float):
    """Piezas para el 3D, centradas en el centroide (cx, cy): [("poly", [(u, v)...]) | ("circle", u, v, ro, ri)]."""
    out = []
    for c in comps:
        if valid_comp(c):
            continue
        if c["t"] in ("circ", "ring"):
            ro = float(c["d"]) / 2.0
            ri = max(ro - float(c["ti"]), 0.0) if c["t"] == "ring" else 0.0
            out.append(("circle", float(c["x"]) - cx, float(c["y"]) - cy, ro, ri))
        else:
            out.append(("poly", [(p[0] - cx, p[1] - cy) for p in _ccw(comp_outline(c))]))
    return out


# ================================================================================================== plantillas
def _R(x, y, w, h, rot=0.0):
    return {"t": "rect", "x": x, "y": y, "w": w, "h": h, "rot": rot}


def t_i_shape(d=14.0, bf=10.0, tf=0.75, tw=0.4, bf2=0.0, tf2=0.0):
    bf2 = bf2 or bf
    tf2 = tf2 or tf
    return [_R(0, d / 2 - tf / 2, bf, tf), _R(0, -d / 2 + tf2 / 2, bf2, tf2), _R(0, (tf2 - tf) / 2, tw, d - tf - tf2)]


def t_box(b=10.0, h=12.0, tw=0.5, tf=0.5):
    return [_R(0, h / 2 - tf / 2, b, tf), _R(0, -h / 2 + tf / 2, b, tf), _R(-b / 2 + tw / 2, 0, tw, h - 2 * tf), _R(b / 2 - tw / 2, 0, tw, h - 2 * tf)]


def t_channel(d=10.0, bf=3.0, tf=0.4, tw=0.3):
    return [_R(tw / 2, 0, tw, d - 2 * tf), _R(bf / 2, d / 2 - tf / 2, bf, tf), _R(bf / 2, -d / 2 + tf / 2, bf, tf)]


def t_tee(d=8.0, bf=8.0, tf=0.5, tw=0.4):
    return [_R(0, d / 2 - tf / 2, bf, tf), _R(0, -tf / 2, tw, d - tf)]


def t_angle(a=6.0, b=4.0, t=0.5):
    return [_R(t / 2, a / 2, t, a), _R((t + b) / 2, t / 2, b - t, t)]


def t_double_angle(a=4.0, b=4.0, t=0.375, gap=0.375):
    return [_R(gap / 2 + t / 2, a / 2, t, a), _R(gap / 2 + (t + b) / 2, t / 2, b - t, t),
            _R(-gap / 2 - t / 2, a / 2, t, a), _R(-gap / 2 - (t + b) / 2, t / 2, b - t, t)]


def t_double_channel(d=10.0, bf=3.0, tf=0.4, tw=0.3, gap=0.5):
    c = t_channel(d, bf, tf, tw)
    right = [dict(q, x=q["x"] + gap / 2) for q in c]
    left = [dict(q, x=-q["x"] - gap / 2) for q in c]
    return right + left


def t_tube(d=8.0, t=0.5):
    return [{"t": "ring", "x": 0, "y": 0, "d": d, "ti": t}]


def t_round_bar(d=4.0):
    return [{"t": "circ", "x": 0, "y": 0, "d": d}]


def t_cross(L=10.0, t=0.5):
    return [_R(0, 0, t, L), _R((L + t) / 4, 0, (L - t) / 2, t), _R(-(L + t) / 4, 0, (L - t) / 2, t)]


def t_cover_plated_i(d=14.0, bf=8.0, tf=0.6, tw=0.4, cw=10.0, ct=0.5):
    return t_i_shape(d, bf, tf, tw) + [_R(0, d / 2 + ct / 2, cw, ct), _R(0, -d / 2 - ct / 2, cw, ct)]


def t_polygon(n=6, d=8.0):
    return [{"t": "poly", "pts": [list(p) for p in regular_polygon(0, 0, d / 2, int(n))]}]


def t_tube_rect_hss(h=12.0, b=8.0, t=0.375):
    return t_box(b, h, t, t)


TEMPLATES = {
    "Perfil I armado (alas distintas)": ([("d", "Peralte total d", 14.0), ("bf", "Ancho del ala superior", 10.0), ("tf", "Espesor del ala superior", 0.75), ("tw", "Espesor del alma", 0.4),
                                          ("bf2", "Ancho del ala inferior", 10.0), ("tf2", "Espesor del ala inferior", 0.75)], t_i_shape),
    "Perfil I con cubreplacas": ([("d", "Peralte del perfil", 14.0), ("bf", "Ancho de ala", 8.0), ("tf", "Espesor de ala", 0.6), ("tw", "Espesor del alma", 0.4),
                                  ("cw", "Ancho de la cubreplaca", 10.0), ("ct", "Espesor de la cubreplaca", 0.5)], t_cover_plated_i),
    "Cajón soldado": ([("b", "Ancho exterior", 10.0), ("h", "Alto exterior", 12.0), ("tw", "Espesor de las almas", 0.5), ("tf", "Espesor de las alas", 0.5)], t_box),
    "Canal armado": ([("d", "Peralte", 10.0), ("bf", "Ancho de ala", 3.0), ("tf", "Espesor de ala", 0.4), ("tw", "Espesor del alma", 0.3)], t_channel),
    "Doble canal (espalda con espalda)": ([("d", "Peralte", 10.0), ("bf", "Ancho de ala", 3.0), ("tf", "Espesor de ala", 0.4), ("tw", "Espesor del alma", 0.3),
                                           ("gap", "Separacion entre almas", 0.5)], t_double_channel),
    "Te armada": ([("d", "Altura total", 8.0), ("bf", "Ancho del ala", 8.0), ("tf", "Espesor del ala", 0.5), ("tw", "Espesor del alma", 0.4)], t_tee),
    "Angulo de lados desiguales": ([("a", "Lado vertical", 6.0), ("b", "Lado horizontal", 4.0), ("t", "Espesor", 0.5)], t_angle),
    "Doble angulo espalda con espalda": ([("a", "Lado vertical", 4.0), ("b", "Lado horizontal", 4.0), ("t", "Espesor", 0.375), ("gap", "Separacion", 0.375)], t_double_angle),
    "Tubo circular": ([("d", "Diametro exterior", 8.0), ("t", "Espesor de pared", 0.5)], t_tube),
    "Tubo rectangular (placas)": ([("h", "Alto", 12.0), ("b", "Ancho", 8.0), ("t", "Espesor", 0.375)], t_tube_rect_hss),
    "Barra circular maciza": ([("d", "Diametro", 4.0)], t_round_bar),
    "Cruz (dos placas)": ([("L", "Largo de cada placa", 10.0), ("t", "Espesor", 0.5)], t_cross),
    "Poligono regular": ([("n", "Numero de lados", 6), ("d", "Diametro circunscrito", 8.0)], t_polygon),
}
LENGTH_PARAMS = {"n"}                # parametros que no son longitudes (no se convierten de unidades)


def build_template(name: str, **vals):
    spec, fn = TEMPLATES[name]
    kw = {k: v for k, _lbl, v in spec}
    kw.update(vals)
    return fn(**kw)


# ================================================================================================== conversion desde perfiles estandar
def comps_of_shape(shape):
    """Componentes equivalentes de un perfil del catalogo (para abrirlo en el Section Designer y editarlo como copia)."""
    if getattr(shape, "comps", None):
        return [dict(c, **({"pts": [list(p) for p in c["pts"]]} if c.get("t") == "poly" else {})) for c in shape.comps]
    if shape.is_round:
        return [{"t": "ring", "x": 0.0, "y": 0.0, "d": float(shape.d), "ti": float(shape.tw)}]
    out = []
    for (x0, y0, x1, y1) in shape.rects() or []:
        out.append(_R((x0 + x1) / 2.0, (y0 + y1) / 2.0, x1 - x0, y1 - y0))
    return out
