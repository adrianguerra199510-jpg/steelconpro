# -*- coding: utf-8 -*-
"""Geometria 3D de los nudos (viga-columna, viga a viga, crucetas): miembro principal + miembros conectados con sus herrajes.

`build_model(prj) -> Model3D` arma las piezas (union de prismas), los pernos y las advertencias de colocacion.  Solo geometria: no hay
calculo.  Convenciones (in, grados):
    · el nudo esta en el origen; el miembro principal pasa por el con su eje a lo largo de Z (columna) o de X (viga, cordon);
    · cada miembro conectado sale de un punto del eje principal (pos, off) en la direccion (azimut, elevacion) y arranca donde esa recta
      sale de la seccion del principal (mas el retranqueo);
    · los ejes de cada seccion son (sx, sy, eje) con sx×sy = eje: sy es el peralte (d) y sx el ancho (bf) del catalogo.
"""
from __future__ import annotations
import math

import numpy as np

from .. import materials as M
from ..shapes import CATALOG, HSS_RECT, W_SHAPE
from .common import hole_std, bolt_db
from .fem.model3d import Model3D, Part, Bolt, Prism, unit
from .specs import (MODE_COL, MODE_BEAM, MODE_CHORD, CK_BLANK, CK_TAB, CK_DANG, CK_SEAT, CK_EP_FLUSH, CK_EP_EXT, CK_WELD, CK_GUSSET,
                    CK_GUSSET_W, GUSSET_KINDS, MAIN_NAMES)

EMBED = 0.35            # las placas entran un poco en el miembro principal para que no quede una rendija en las uniones esviadas
DIAG_MIN = 10.0         # elevacion (grados) desde la cual un miembro se considera diagonal (color y cartela por omision)


# ================================================================================================== secciones y marcos
def _v(a):
    return np.asarray(a, float)


def shape_of(label: str):
    s = CATALOG.get(label)
    return s if s is not None else CATALOG.get("W14X90") or next(iter(CATALOG.shapes.values()))


def frame(A, pref, roll_deg=0.0):
    """(A, sx, sy) ortonormales con sx×sy = A.  sy es la componente de `pref` perpendicular a A; roll gira la seccion sobre el eje."""
    A = unit(A)
    pref = _v(pref)
    sy = pref - float(np.dot(pref, A)) * A
    if float(np.linalg.norm(sy)) < 1e-6:
        alt = np.array([1.0, 0.0, 0.0]) if abs(A[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        sy = alt - float(np.dot(alt, A)) * A
    sy = unit(sy)
    sx = np.cross(sy, A)
    r = math.radians(roll_deg)
    if abs(r) > 1e-9:
        c, s = math.cos(r), math.sin(r)
        sx, sy = c * sx + s * sy, -s * sx + c * sy
    return A, sx, sy


def main_frame(nd):
    if nd.mode == MODE_COL:
        return frame([0, 0, 1], [1, 0, 0], nd.main_roll)
    e = math.radians(nd.main_slope)
    return frame([math.cos(e), 0.0, math.sin(e)], [0, 0, 1], nd.main_roll)


def member_dir(m):
    a, e = math.radians(m.az), math.radians(m.el)
    return unit([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def member_frame(m):
    d = member_dir(m)
    pref = [0, 0, 1] if abs(d[2]) < 0.995 else [1, 0, 0]
    return frame(d, pref, m.roll)


def section_prisms(shape, o, sx, sy, A, s0, s1):
    """Prismas de la seccion extruida de s0 a s1 a lo largo de A desde el origen `o` (la seccion tiene su centroide en `o`)."""
    o = tuple(map(float, o))
    U, V = tuple(map(float, sx)), tuple(map(float, sy))
    if shape.is_round:
        return [Prism(poly=[], o=o, U=U, V=V, w0=float(s0), w1=float(s1), circle=(shape.d / 2.0, max(shape.d / 2.0 - shape.tw, 0.0)))]
    return [Prism(poly=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], o=o, U=U, V=V, w0=float(s0), w1=float(s1)) for (x0, y0, x1, y1) in shape.rects()]


def outer_extent(shape):
    """Envolvente EXTERIOR de la seccion para saber donde un miembro toca al principal: ('circle', R) o rectangulos (x0, y0, x1, y1)."""
    if shape.is_round:
        return ("circle", shape.d / 2.0)
    if shape.kind == HSS_RECT:
        return [(-shape.bf / 2.0, -shape.d / 2.0, shape.bf / 2.0, shape.d / 2.0)]
    return shape.rects()


def ray_exit(ext, o2, d2):
    """Parametro s > 0 en el que el rayo o2 + s·d2 sale por ULTIMA vez de la seccion (= donde lo toca un miembro que llega desde fuera).
    None si no la cruza."""
    o2, d2 = (float(o2[0]), float(o2[1])), (float(d2[0]), float(d2[1]))
    if ext[0] == "circle":
        a = d2[0] ** 2 + d2[1] ** 2
        if a < 1e-12:
            return None
        b = 2.0 * (o2[0] * d2[0] + o2[1] * d2[1])
        c = o2[0] ** 2 + o2[1] ** 2 - ext[1] ** 2
        disc = b * b - 4.0 * a * c
        if disc < 0:
            return None
        s = (-b + math.sqrt(disc)) / (2.0 * a)
        return s if s > 0 else None
    best = None
    for (x0, y0, x1, y1) in ext:
        lo, hi = -1e18, 1e18
        for k, (a0, a1) in enumerate(((x0, x1), (y0, y1))):
            if abs(d2[k]) < 1e-12:
                if o2[k] < a0 or o2[k] > a1:
                    lo, hi = 1.0, -1.0
                    break
            else:
                t1, t2 = (a0 - o2[k]) / d2[k], (a1 - o2[k]) / d2[k]
                if t1 > t2:
                    t1, t2 = t2, t1
                lo, hi = max(lo, t1), min(hi, t2)
        if hi >= lo and hi > 0 and (best is None or hi > best):
            best = hi
    return best


def _steel(name, plate=False):
    try:
        m = M.find(M.PLATE_STEELS if plate else M.SHAPE_STEELS, name, 1 if plate else 0)
        return m.Fy, m.Fu
    except Exception:
        return (36.0, 58.0) if plate else (50.0, 65.0)


def _is_open(shape) -> bool:
    return not shape.is_hollow


def _halfw(shape) -> float:
    """Semiancho lateral (a lo largo de sx) donde se apoyan las placas laterales: media alma de un perfil abierto, medio ancho de un hueco."""
    return shape.bf / 2.0 if shape.is_hollow else shape.tw / 2.0


def _depth(shape) -> float:
    return shape.d


def _clear_depth(shape) -> float:
    """Peralte libre disponible para una fila de pernos en el alma / cara."""
    if shape.kind == W_SHAPE:
        return shape.d - 2.0 * shape.tf
    if shape.is_hollow:
        return shape.d - 2.0 * shape.tw
    return shape.d


def _bolt(tag, p, axis, db, head_s, nut_s, grip, grade):
    return Bolt(tag, tuple(map(float, p)), tuple(map(float, unit(axis))), db, hole_std(db), 0.9 * db, grip, head_s, nut_s, grade, 1)


def _plate_prism(poly, o, U, V, w0, w1):
    return Prism(poly=[(float(a), float(b)) for a, b in poly], o=tuple(map(float, o)), U=tuple(map(float, U)), V=tuple(map(float, V)),
                 w0=float(w0), w1=float(w1))


# ================================================================================================== herrajes de cada miembro
class _Ctx:
    """Datos de un miembro ya colocado, comunes a todos sus herrajes."""
    def __init__(self, m, shape, P0, Q, dirv, sx, sy, mshape, dmain):
        self.m, self.shape, self.P0, self.Q, self.dir, self.sx, self.sy = m, shape, P0, Q, dirv, sx, sy
        self.mshape, self.dmain = mshape, dmain
        self.db = bolt_db(m.bolt_size)
        self.t = max(float(m.plate_t), 0.125)
        self.parts, self.bolts, self.notes = [], [], []

    def at(self, s, lat=0.0, v=0.0):
        """Punto a `s` del apoyo Q a lo largo del miembro, `lat` en sx y `v` en sy."""
        return self.Q + s * self.dir + lat * self.sx + v * self.sy


def _n_rows(ctx, hmax, edge=1.5):
    """Numero de pernos de una fila que caben en `hmax`."""
    s = max(ctx.m.bolt_s, 3 * ctx.db * 0.8)
    n = max(1, int(ctx.m.n_bolts))
    fit = max(1, int((hmax - 2 * edge) / s) + 1)
    if n > fit:
        ctx.notes.append(f"{ctx.m.name}: caben {fit} pernos en {hmax:.1f} in; se dibujan {fit} de {n}.")
        n = fit
    return n, s


def _tab_geometry(ctx, tag):
    """Placa simple (pernos en una fila vertical).  Devuelve el largo de la placa desde Q."""
    m, shp = ctx.m, ctx.shape
    t = ctx.t
    n, s = _n_rows(ctx, _clear_depth(shp))
    sb = m.gap + 2.5                                   # fila de pernos: 2.5 in del extremo del miembro
    Lp = sb + 1.5
    H = (n - 1) * s + 3.0
    lat = (_halfw(shp) + t / 2.0) if _is_open(shp) else 0.0
    poly = [(-EMBED, -H / 2), (Lp, -H / 2), (Lp, H / 2), (-EMBED, H / 2)]
    # plano (dir, sy): U×V = dir×sy = -sx  → el espesor se mide hacia -sx; se coloca con o desplazado
    pr = _plate_prism(poly, ctx.Q + (lat + t / 2.0) * ctx.sx, ctx.dir, ctx.sy, 0.0, t)
    name = f"Placa {tag}"
    Fy, Fu = _steel(m.plate_steel, True)
    ctx.parts.append(Part(name, "plate", f"Placa simple PL {t:g}", Fy, Fu, [pr], t=t))
    zs = [(i - (n - 1) / 2.0) * s for i in range(n)]
    if _is_open(shp):
        grip = [(name, 0.0, t), (ctx.partname, t, t + shp.tw)]
        p0 = lat + t / 2.0
        nut = t + shp.tw
    else:
        grip = [(ctx.partname, 0.0, shp.bf)]
        p0 = shp.bf / 2.0
        nut = shp.bf
    for i, z in enumerate(zs):
        ctx.bolts.append(_bolt(f"{tag}-B{i + 1}", ctx.at(sb, p0, z), -ctx.sx, ctx.db, 0.0, nut, grip, m.bolt_grade))
    return Lp


def _dang_geometry(ctx, tag):
    m, shp = ctx.m, ctx.shape
    t = ctx.t
    n, s = _n_rows(ctx, _clear_depth(shp))
    sb = m.gap + 2.5
    la = sb + 1.5
    lo = 3.5
    H = (n - 1) * s + 3.0
    l0 = _halfw(shp)
    Fy, Fu = _steel(m.plate_steel, True)
    for k, sg in enumerate((1, -1)):
        poly = [(-EMBED, sg * l0), (la, sg * l0), (la, sg * (l0 + t)), (t, sg * (l0 + t)), (t, sg * (l0 + lo)), (-EMBED, sg * (l0 + lo))]
        pr = _plate_prism(poly, ctx.Q, ctx.dir, ctx.sx, -H / 2.0, H / 2.0)      # U×V = dir×sx = sy
        pr.o = tuple(map(float, ctx.Q))
        ctx.parts.append(Part(f"Angulo {tag}-{k + 1}", "angle", f"Angulo L {lo:g}x{la:g}x{t:g}", Fy, Fu, [pr], t=t))
    zs = [(i - (n - 1) / 2.0) * s for i in range(n)]
    grip = [(f"Angulo {tag}-1", 0.0, t), (ctx.partname, t, t + 2 * l0), (f"Angulo {tag}-2", t + 2 * l0, 2 * t + 2 * l0)]
    for i, z in enumerate(zs):
        ctx.bolts.append(_bolt(f"{tag}-B{i + 1}", ctx.at(sb, l0 + t, z), -ctx.sx, ctx.db, 0.0, 2 * t + 2 * l0, grip, m.bolt_grade))
        for k, sg in enumerate((1, -1)):                # pernos de las alas salientes hacia el soporte
            ctx.bolts.append(_bolt(f"{tag}-S{i + 1}{k + 1}", ctx.at(t, sg * (l0 + lo * 0.62), z), -ctx.dir, ctx.db, 0.0, t + 1.0,
                                   [(f"Angulo {tag}-{k + 1}", 0.0, t)], m.bolt_grade))
    return la


def _seat_geometry(ctx, tag):
    m, shp = ctx.m, ctx.shape
    t = max(ctx.t, 0.375)
    Lh, Lv = 5.0, 6.0
    W = min(max(shp.bf if shp.bf > 0 else 6.0, 4.0), 12.0)
    yb = -shp.d / 2.0
    g = m.gap
    poly = [(-EMBED, yb - Lv), (t, yb - Lv), (t, yb - t), (Lh, yb - t), (Lh, yb), (-EMBED, yb)]
    pr = _plate_prism(poly, ctx.Q, ctx.dir, ctx.sy, -W / 2.0, W / 2.0)        # U×V = dir×sy = -sx (simetrico)
    Fy, Fu = _steel(m.plate_steel, True)
    ctx.parts.append(Part(f"Asiento {tag}", "angle", f"Angulo de asiento L {Lh:g}x{Lv:g}x{t:g}", Fy, Fu, [pr], t=t))
    gauge = min(max(W - 2.5, 1.5), 4.0)
    for k, sg in enumerate((1, -1)):
        ctx.bolts.append(_bolt(f"{tag}-A{k + 1}", ctx.at(Lh * 0.62, sg * gauge / 2.0, yb - t), ctx.sy, ctx.db, 0.0, t + (shp.tf if shp.tf > 0 else 0.5),
                               [(f"Asiento {tag}", 0.0, t), (ctx.partname, t, t + (shp.tf if shp.tf > 0 else 0.5))], m.bolt_grade))
        ctx.bolts.append(_bolt(f"{tag}-S{k + 1}", ctx.at(t, sg * gauge / 2.0, yb - Lv * 0.6), -ctx.dir, ctx.db, 0.0, t + 1.0,
                               [(f"Asiento {tag}", 0.0, t)], m.bolt_grade))
    return max(g, 0.5)


def _endplate_geometry(ctx, tag, extended):
    m, shp = ctx.m, ctx.shape
    t = max(ctx.t, 0.5)
    d = shp.d
    bf = shp.bf if shp.bf > 0 else shp.d
    hollow = shp.is_hollow
    ext = max(m.ep_ext, 2.0) if (extended or hollow) else 0.5
    hh = d / 2.0 + ext
    gb = min(max(bf - 2.5, 2.5), 5.5)
    wide = max(bf + 1.5, gb + 3.0)
    poly = [(-wide / 2, -hh), (wide / 2, -hh), (wide / 2, hh), (-wide / 2, hh)]
    pr = _plate_prism(poly, ctx.Q - ctx.dir * (-EMBED * 0.0), ctx.sx, ctx.sy, 0.0, t)      # U×V = sx×sy = dir: extruye hacia el miembro
    Fy, Fu = _steel(m.plate_steel, True)
    ctx.parts.append(Part(f"Placa extrema {tag}", "plate", f"Placa extrema PL {t:g}", Fy, Fu, [pr], t=t))
    rows = []
    if hollow:
        rows = [hh - 1.5, -(hh - 1.5)]
    else:
        tf = shp.tf if shp.tf > 0 else 0.5
        if extended:
            rows = [d / 2.0 + ext - 1.5, d / 2.0 - tf - 1.75, -(d / 2.0 - tf - 1.75), -(d / 2.0 + ext - 1.5)]
        else:
            rows = [d / 2.0 - tf - 1.75, -(d / 2.0 - tf - 1.75)]
    for i, v in enumerate(rows):
        for k, sg in enumerate((1, -1)):
            ctx.bolts.append(_bolt(f"{tag}-B{i + 1}{k + 1}", ctx.at(t, sg * (gb / 2.0 if not hollow else wide / 2.0 - 1.25), v), -ctx.dir, ctx.db, 0.0, t + 1.0,
                                   [(f"Placa extrema {tag}", 0.0, t)], m.bolt_grade))
    return t


def _weld_geometry(ctx, tag):
    """Alas soldadas a tope contra el apoyo; el alma lleva una placa simple atornillada."""
    shp = ctx.shape
    if _is_open(shp):
        _tab_geometry(ctx, tag)
    return 0.12


def _continuity(ctx, nd, tag, main_frame_, mshape):
    """Placas de continuidad dentro de una columna I frente a las alas de una viga que llega a su ala."""
    if nd.mode != MODE_COL or mshape.kind != W_SHAPE:
        return []
    A, msx, msy = main_frame_
    d2 = (float(np.dot(ctx.dir, msx)), float(np.dot(ctx.dir, msy)))
    if abs(d2[1]) < 0.6 * max(math.hypot(*d2), 1e-9):       # no llega por la cara del ala (de lado a lo largo de d)
        return []
    t = max(ctx.shape.tf if ctx.shape.tf > 0 else 0.5, 0.375)
    out = []
    Fy, Fu = _steel("ASTM A36", True)
    dm, tfm = ctx.shape.d, (ctx.shape.tf if ctx.shape.tf > 0 else 0.5)
    for k, lv in enumerate((dm / 2.0 - tfm / 2.0, -(dm / 2.0 - tfm / 2.0))):
        zc = float((ctx.P0 + lv * ctx.sy)[2])
        for j, sg in enumerate((1, -1)):
            x0, x1 = sg * mshape.tw / 2.0, sg * mshape.bf / 2.0
            y0, y1 = -(mshape.d / 2.0 - mshape.tf), (mshape.d / 2.0 - mshape.tf)
            poly = [(min(x0, x1), y0), (max(x0, x1), y0), (max(x0, x1), y1), (min(x0, x1), y1)]
            pr = Prism(poly=poly, o=(0.0, 0.0, zc - t / 2.0), U=tuple(map(float, msx)), V=tuple(map(float, msy)), w0=0.0, w1=t)
            out.append(Part(f"Continuidad {tag}-{k + 1}{j + 1}", "stiff", f"Placa de continuidad PL {t:g}", Fy, Fu, [pr], t=t))
    return out


# ================================================================================================== cartelas (placa comun por plano)
def _hull(pts):
    """Envolvente convexa (Andrew) de puntos 2D."""
    P = sorted(set((round(p[0], 5), round(p[1], 5)) for p in pts))
    if len(P) <= 2:
        return P
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _gusset_outline(ctx):
    """Puntos (3D, en el plano de la cartela) del contorno de la cartela de un miembro: base sobre el principal y punta bajo el miembro."""
    m, shp = ctx.m, ctx.shape
    dm = max(min(shp.d if not shp.is_round else shp.d, 16.0), 4.0)
    hb = max(dm * 1.05, 7.0)
    hm = max(dm * 0.9, 5.0)
    rows = max(1, int(m.n_bolts))
    s = max(m.bolt_s, 2.5)
    ov = (rows - 1) * s + 3.0 + 1.0
    gl = 2.0 if m.conn == CK_GUSSET else 6.0
    tip = gl + (ov if m.conn == CK_GUSSET else 0.0)
    pts = [ctx.at(-EMBED, 0.0, -hb / 2.0), ctx.at(-EMBED, 0.0, hb / 2.0), ctx.at(tip, 0.0, hm / 2.0), ctx.at(tip, 0.0, -hm / 2.0)]
    return pts, gl, ov, hm


def _gusset_members(ctxs, nd):
    """Una cartela por plano: la envolvente de los contornos de los miembros que comparten plano (p. ej. las dos diagonales de una V)."""
    groups = []
    for c in ctxs:
        if c.m.conn not in GUSSET_KINDS:
            continue
        n = unit(c.sx)
        for g in groups:
            if abs(float(np.dot(g["n"], n))) > 0.999 and abs(float(np.dot(g["n"], c.P0 - g["P0"]))) < 0.05:
                g["items"].append(c)
                break
        else:
            groups.append({"n": n, "P0": c.P0, "items": [c]})
    return groups


def _build_gussets(ctxs, nd, mdl):
    for gi, g in enumerate(_gusset_members(ctxs, nd)):
        n = g["n"]
        ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        e1 = unit(np.cross(ref, n))
        e2 = np.cross(n, e1)                               # e1×e2 = n
        t = max(max(c.t for c in g["items"]), 0.375)
        # desplazamiento lateral comun: junto al alma de los miembros abiertos; centrada si todos son huecos
        lats = [(_halfw(c.shape) + t / 2.0) for c in g["items"] if _is_open(c.shape)]
        lat = max(lats) if lats else 0.0
        _A, msx, _msy = main_frame(nd)
        mshape = g["items"][0].mshape
        if _is_open(mshape) and abs(float(np.dot(n, msx))) > 0.99:       # el plano de la cartela coincide con el del alma del principal: se coloca a un lado
            lat = max(lat, mshape.tw / 2.0 + t / 2.0)
        pts2 = []
        for c in g["items"]:
            outline, *_ = _gusset_outline(c)
            for p in outline:
                q = np.asarray(p) - g["P0"]
                pts2.append((float(np.dot(q, e1)), float(np.dot(q, e2))))
        hull = _hull(pts2)
        if len(hull) < 3:
            continue
        o = g["P0"] + n * (lat - t / 2.0)
        pr = Prism(poly=hull, o=tuple(map(float, o)), U=tuple(map(float, e1)), V=tuple(map(float, e2)), w0=0.0, w1=t)
        Fy, Fu = _steel(g["items"][0].m.plate_steel, True)
        names = "+".join(c.m.name for c in g["items"])
        mdl.parts.append(Part(f"Cartela {gi + 1}", "gusset", f"Cartela PL {t:g} ({names})", Fy, Fu, [pr], t=t))
        for c in g["items"]:
            if c.m.conn != CK_GUSSET:
                continue
            m, shp = c.m, c.shape
            _, gl, ov, hm = _gusset_outline(c)
            rows = max(1, int(m.n_bolts))
            s = max(m.bolt_s, 2.5)
            gauge = max(min(hm * 0.5, 6.0), 2.5)
            if _is_open(shp):
                grip = [(f"Cartela {gi + 1}", 0.0, t), (c.partname, t, t + shp.tw)]
                p0, nut = lat + t / 2.0, t + shp.tw
            else:
                grip = [(c.partname, 0.0, shp.bf)]
                p0, nut = shp.bf / 2.0, shp.bf
            for i in range(rows):
                for k, sg in enumerate((1, -1)):
                    mdl.bolts.append(_bolt(f"{m.name}-B{i + 1}{k + 1}", c.at(gl + 1.5 + i * s, p0, sg * gauge / 2.0), -c.sx, c.db, 0.0, nut, grip, m.bolt_grade))


# ================================================================================================== modelo completo
def build_model(prj, vals=None) -> Model3D:
    from .specs import ATTR_OF
    nd = getattr(prj, ATTR_OF[prj.ctype])
    return build_nodo(nd, name=prj.element or prj.ctype)


def build_nodo(nd, name="Nudo", hardware=None) -> Model3D:
    hw = nd.show_hw if hardware is None else hardware
    mdl = Model3D(name)
    mshape = shape_of(nd.main_shape)
    A, msx, msy = main_frame(nd)
    lneg, lpos = nd.lengths()
    Fy, Fu = _steel(nd.main_steel)
    if lneg + lpos < 1.0:
        lneg = lpos = 24.0
    mdl.parts.append(Part(MAIN_NAMES[nd.mode], "column", f"{MAIN_NAMES[nd.mode]} {mshape.label}", Fy, Fu,
                          section_prisms(mshape, (0, 0, 0), msx, msy, A, -lneg, lpos), t=mshape.tw, stub=True))
    ext = outer_extent(mshape)
    ctxs = []
    for i, m in enumerate(nd.members):
        shp = shape_of(m.shape)
        dirv = member_dir(m)
        _, sx, sy = member_frame(m)
        P0 = A * m.pos + (msy * m.off if nd.mode != MODE_COL else 0.0)
        o2 = (0.0, float(m.off) if nd.mode != MODE_COL else 0.0)
        d2 = (float(np.dot(dirv, msx)), float(np.dot(dirv, msy)))
        s_ex = ray_exit(ext, o2, d2) if math.hypot(*d2) > 1e-6 else None
        if s_ex is None:
            mdl.notes.append(f"{m.name}: su eje no toca al miembro principal (revise el azimut, la elevación o la posición).")
            s_ex = 0.0
        Q = P0 + dirv * s_ex
        c = _Ctx(m, shp, P0, Q, dirv, sx, sy, mshape, mshape.d)
        c.partname = m.name
        diag = abs(m.el) >= DIAG_MIN
        conn = m.conn if hw else CK_BLANK
        ms = max(m.gap, 0.0)                          # distancia desde Q hasta el inicio del miembro
        tag = m.name
        if conn == CK_TAB:
            _tab_geometry(c, tag)
        elif conn == CK_DANG:
            _dang_geometry(c, tag)
        elif conn == CK_SEAT:
            _seat_geometry(c, tag)
        elif conn == CK_EP_FLUSH:
            ms = _endplate_geometry(c, tag, False)
        elif conn == CK_EP_EXT:
            ms = _endplate_geometry(c, tag, True)
        elif conn == CK_WELD:
            ms = _weld_geometry(c, tag)
            mdl.parts += _continuity(c, nd, tag, (A, msx, msy), mshape) if m.cont else []
        elif conn in GUSSET_KINDS:
            _, gl, ov, hm = _gusset_outline(c)
            ms = gl if conn == CK_GUSSET else gl + 0.1
        Fy_m, Fu_m = _steel(m.steel)
        mdl.parts.append(Part(m.name, "brace" if diag else "beam", f"{m.name} {shp.label}", Fy_m, Fu_m,
                              section_prisms(shp, Q + dirv * ms, sx, sy, dirv, 0.0, max(m.L, 1.0)), t=shp.tw, stub=True))
        for p in c.parts:
            mdl.parts.append(p)
        mdl.bolts += c.bolts
        mdl.notes += c.notes
        end = Q + dirv * (ms + max(m.L, 1.0))
        mdl.tags.append((tuple(map(float, end)), m.name))
        ctxs.append(c)
    _build_gussets(ctxs, nd, mdl)
    return mdl
