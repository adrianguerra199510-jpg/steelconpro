# -*- coding: utf-8 -*-
"""Geometria 3D del nudo: miembro principal (el que designa el usuario) + miembros conectados con sus herrajes.

`build_model(prj) -> Model3D` arma las piezas (union de prismas), los pernos y las advertencias de colocacion.  Solo geometria: no hay
calculo.  Convenciones (in, grados):
    · el nudo esta en el origen; el miembro principal pasa por el con su eje segun su azimut y su elevacion (vertical = 90°, a lo largo de Z);
    · cada miembro conectado sale de un punto del eje principal (pos, off, off2) en la direccion (azimut, elevacion) y arranca donde esa recta
      sale de la seccion del principal (mas el retranqueo);
    · los ejes de cada seccion son (sx, sy, eje) con sx×sy = eje: sy es el peralte (d) y sx el ancho (bf) del catalogo.
"""
from __future__ import annotations
import copy
import math

import numpy as np

from .. import materials as M
from ..shapes import CATALOG, HSS_RECT, W_SHAPE, GEN
from .common import hole_std, bolt_db
from .fem.model3d import Model3D, Part, Bolt, Prism, Weld, unit
from . import ops as OPS
from .ops import member_faces, FaceFrame
from .specs import (GENERIC_OPS, OP_CUT, OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET, OP_GUSSET_W,
                    OP_COPE, OP_CONT, TAB_MODES, OP_BASE, GUSSET_OPS, END_LABELS, Operation, Member)

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


def axis_dir(az, el):
    a, e = math.radians(az), math.radians(el)
    return unit([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def main_frame(nd):
    """(eje A, sx, sy) del miembro principal: A segun su azimut y elevacion; sy hacia arriba (hacia +X si es vertical) y sx = sy × A."""
    A = axis_dir(nd.main_az, nd.main_el)
    return frame(A, [0, 0, 1] if abs(A[2]) < 0.995 else [1, 0, 0], nd.main_roll)


def attach_point(nd, m, frm=None):
    """Punto del eje de `m` donde se mide su llegada al principal, y su desplazamiento (off2, off) en el plano de la seccion del principal."""
    A, msx, msy = frm or main_frame(nd)
    return A * m.pos + msx * m.off2 + msy * m.off, (float(m.off2), float(m.off))


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
    if shape.kind == GEN:                                   # seccion libre (Section Designer): una pieza por componente
        out = []
        for pc in shape.pieces():
            if pc[0] == "circle":
                _, u, v, ro, ri = pc
                oc = tuple(float(q) for q in (np.asarray(o) + u * np.asarray(U) + v * np.asarray(V)))
                out.append(Prism(poly=[], o=oc, U=U, V=V, w0=float(s0), w1=float(s1), circle=(ro, ri)))
            else:
                out.append(Prism(poly=[(float(a), float(b)) for a, b in pc[1]], o=o, U=U, V=V, w0=float(s0), w1=float(s1)))
        return out
    if shape.is_round:
        return [Prism(poly=[], o=o, U=U, V=V, w0=float(s0), w1=float(s1), circle=(shape.d / 2.0, max(shape.d / 2.0 - shape.tw, 0.0)))]
    return [Prism(poly=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], o=o, U=U, V=V, w0=float(s0), w1=float(s1)) for (x0, y0, x1, y1) in shape.rects()]


def outer_extent(shape):
    """Envolvente EXTERIOR de la seccion para saber donde un miembro toca al principal: ('circle', R) o rectangulos (x0, y0, x1, y1)."""
    if shape.is_round:
        return ("circle", shape.d / 2.0)
    if shape.kind == GEN:
        polys = []
        for pc in shape.pieces():
            if pc[0] == "circle":
                _, u, v, ro, _ri = pc
                polys.append([(u + ro * math.cos(2 * math.pi * k / 48), v + ro * math.sin(2 * math.pi * k / 48)) for k in range(48)])
            else:
                polys.append(list(pc[1]))
        return ("polys", polys)
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
    if ext[0] == "polys":                                   # ultimo cruce del rayo con el contorno de cualquier pieza
        for poly in ext[1]:
            n = len(poly)
            for i in range(n):
                (ax_, ay_), (bx_, by_) = poly[i], poly[(i + 1) % n]
                ex, ey = bx_ - ax_, by_ - ay_
                den = d2[0] * ey - d2[1] * ex
                if abs(den) < 1e-12:
                    continue
                t = ((ax_ - o2[0]) * ey - (ay_ - o2[1]) * ex) / den
                u_ = ((ax_ - o2[0]) * d2[1] - (ay_ - o2[1]) * d2[0]) / den
                if t > 1e-9 and -1e-9 <= u_ <= 1 + 1e-9 and (best is None or t > best):
                    best = t
        return best
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
    def __init__(self, m, op, shape, P0, Q, dirv, sx, sy, mshape, dmain):
        self.m, self.op, self.shape, self.P0, self.Q, self.dir, self.sx, self.sy = m, op or Operation(), shape, P0, Q, dirv, sx, sy
        self.mshape, self.dmain = mshape, dmain
        self.db = bolt_db(self.op.bolt_size)
        self.t = max(float(self.op.plate_t), 0.125)
        self.parts, self.bolts, self.notes = [], [], []
        self.welds = []
        self.extra = 0.0                # placa simple hasta las alas del principal: retroceso de la viga
        self.main_name = ""

    def at(self, s, lat=0.0, v=0.0):
        """Punto a `s` del apoyo Q a lo largo del miembro, `lat` en sx y `v` en sy."""
        return self.Q + s * self.dir + lat * self.sx + v * self.sy


def _n_rows(ctx, hmax, edge=1.5):
    """Numero de pernos de una fila que caben en `hmax`."""
    s = max(ctx.op.bolt_s, 3 * ctx.db * 0.8)
    n = max(1, int(ctx.op.n_bolts))
    fit = max(1, int((hmax - 2 * edge) / s) + 1)
    if n > fit:
        ctx.notes.append(f"{ctx.m.name}: caben {fit} pernos en {hmax:.1f} in; se dibujan {fit} de {n}.")
        n = fit
    return n, s


def gap_eff(m) -> float:
    """Separacion del extremo del miembro a la cara del principal para las conexiones de corte: 1/2 in más el desplazamiento sobre el eje del miembro."""
    return max(0.5 + float(m.gap), 0.0)


def support_normal(nd, m):
    """Normal (hacia afuera del principal) de la cara del principal en la que llega el miembro `m`, o None si no la toca."""
    mshape = shape_of(nd.main_shape)
    A, msx, msy = main_frame(nd)
    dirv = member_dir(m)
    P0, o2 = attach_point(nd, m, (A, msx, msy))
    d2 = (float(np.dot(dirv, msx)), float(np.dot(dirv, msy)))
    s_ex = exit_dist(outer_extent(mshape), o2, d2)
    if s_ex is None:
        return None
    x, y = o2[0] + s_ex * d2[0], o2[1] + s_ex * d2[1]
    if mshape.kind == W_SHAPE:
        flange = abs(y) >= mshape.d / 2.0 - 1e-6
    else:
        flange = abs(y) / max(mshape.d / 2.0, 1e-6) >= abs(x) / max(mshape.bf / 2.0 if mshape.bf > 0 else mshape.d / 2.0, 1e-6)
    return (msy * (1.0 if y >= 0 else -1.0)) if flange else (msx * (1.0 if x >= 0 else -1.0))


def aligned_frame(nd, m, op, dirv, sx, sy):
    """Ejes (dirección de salida, ancho, alto) de la placa de una conexión de corte o de momento según el elemento al que se alinea.
    «» = el propio miembro; el principal = paralela a la cara del principal en la que llega; otro miembro = sus propios ejes."""
    if not getattr(op, "align_to", ""):
        return None
    if op.align_to == nd.main_name:
        n = support_normal(nd, m)
        if n is None:
            return None
        d2 = unit(n)
        up = sy - d2 * float(np.dot(sy, d2))
        if np.linalg.norm(up) < 1e-6:
            up = sx - d2 * float(np.dot(sx, d2))
        up = unit(up)
        return d2, unit(np.cross(up, d2)), up                    # sx'×sy' = dir'
    o = nd.member_named(op.align_to)
    if o is None or o is m:
        return None
    _, osx, osy = member_frame(o)
    return member_dir(o), osx, osy


def tab_extra(nd, m, op) -> float:
    """Placa simple «hasta el interior de las alas»: cuánto se saca la viga del principal (del alma al borde de las alas) para que no choque con ellas.
    0 si no aplica (el principal no es un perfil I o la viga no llega por el alma)."""
    from .specs import TAB_MODES
    if op is None or op.kind != OP_TAB or op.tab_mode == TAB_MODES[0] and not op.tab_mode.startswith("Dos placas"):
        return 0.0
    ms = shape_of(nd.main_shape)
    if ms.kind != W_SHAPE or attach_info(nd, m).get("face") != "alma":
        return 0.0
    return max(float(ms.bf) / 2.0 - float(ms.tw) / 2.0, 0.0)


def _tab_split(op, ctx=None) -> bool:
    """Dos placas arriba y abajo: solo con «hasta el interior de las alas» y el principal vertical (los archivos con la opción antigua también la conservan)."""
    return bool(op.tab_split or str(op.tab_mode).startswith("Dos placas"))


def tab_dims(op, m, shp, db, extra=0.0):
    """Medidas de la placa simple: (filas, separacion, columnas, separacion entre columnas, alto, ancho, a) en in; `a` = distancia de la soldadura a la primera columna."""
    s = max(op.bolt_s, 3 * db * 0.8)
    n = max(1, int(op.n_bolts))
    g = max(op.bolt_g, 3 * db * 0.8)
    cols = max(1, int(getattr(op, "n_cols", 1)))
    a = gap_eff(m) + extra + 2.5
    H = op.tab_H if op.tab_H > 0 else (n - 1) * s + 3.0
    Wd = op.tab_W if op.tab_W > 0 else a + (cols - 1) * g + 1.5
    if getattr(op, 'beam_conn', 'Atornillada') == 'Soldada' and op.tab_W <= 0:
        Wd = gap_eff(m) + extra + 5.0                                  # soldada: la placa se traslapa 5 in sobre el alma de la viga
    return n, s, cols, g, H, Wd, a


def _tab_geometry(ctx, tag):
    """Placa simple sobre la cara del soporte (soldada con filete a ambos lados) y atornillada al alma de la viga: filas × columnas de pernos."""
    m, shp = ctx.m, ctx.shape
    t = ctx.t
    extra = float(getattr(ctx, 'extra', 0.0))
    n, s, cols, g, H, Wd, a = tab_dims(ctx.op, m, shp, ctx.db, extra)
    Hf = (float(ctx.mshape.d) - 2.0 * float(ctx.mshape.tf)) if extra > 0 else H      # altura de la placa entre las alas del principal (llena el espacio hasta las alas)
    hmax = _clear_depth(shp)
    if n > 1 and (n - 1) * s + 2 * 1.0 > hmax + 1e-9:
        fit = max(1, int((hmax - 2.0) / s) + 1)
        ctx.notes.append(f"{ctx.m.name}: caben {fit} pernos en {hmax:.1f} in; se dibujan {fit} de {n}.")
        n = fit
        H = min(H, (n - 1) * s + 3.0) if ctx.op.tab_H <= 0 else H
    lat = (_halfw(shp) + t / 2.0) if _is_open(shp) else 0.0
    Lp = Wd
    ty = float(getattr(ctx.op, 'tab_y', 0.0))
    tyc = 0.0                                                      # centro de la placa respecto del eje de la viga (los pernos siguen al eje de la viga)
    if extra > 0:                                                  # la placa se centra en el alma del principal, no en el eje de la viga
        Aax = np.asarray(ctx.dmain_axis, float) if getattr(ctx, 'dmain_axis', None) is not None else None
        qperp = ctx.Q - (Aax * float(np.dot(ctx.Q, Aax)) if Aax is not None else 0.0)
        tyc = -float(np.dot(qperp, ctx.sy))
    ty_p = ty + tyc
    clip = float(ctx.op.tab_clip)
    clip = 0.0 if clip < 0 else clip                                    # recorte opcional de las esquinas junto al soporte
    if extra > 0:                                                       # placa escalonada: llena el espacio entre las alas y, fuera de ellas, se reduce a la placa de los pernos
        e = min(extra, Lp - 0.5)
        Ht = min(H, Hf) if ctx.op.tab_H <= 0 else H
        two = _tab_split(ctx.op, ctx)
        if two:                                                         # placa de pernos sola; las placas de arriba y abajo se agregan aparte
            poly = [(0.0, ty - Ht / 2), (Lp, ty - Ht / 2), (Lp, ty + Ht / 2), (0.0, ty + Ht / 2)]
        else:
            poly = [(0.0, ty_p - Hf / 2), (e, ty_p - Hf / 2), (e, ty - Ht / 2), (Lp, ty - Ht / 2), (Lp, ty + Ht / 2), (e, ty + Ht / 2), (e, ty_p + Hf / 2), (0.0, ty_p + Hf / 2)]
        H = Ht
    else:
        clip = min(clip, H / 2.0 - 0.1, Lp - 0.1)
        if clip > 1e-6:
            poly = [(0.0, ty_p - H / 2 + clip), (clip, ty_p - H / 2), (Lp, ty_p - H / 2), (Lp, ty_p + H / 2), (clip, ty_p + H / 2), (0.0, ty_p + H / 2 - clip)]
        else:
            poly = [(0.0, ty_p - H / 2), (Lp, ty_p - H / 2), (Lp, ty_p + H / 2), (0.0, ty_p + H / 2)]            # la placa nace en la cara del soporte (x = 0)
    pr = _plate_prism(poly, ctx.Q + (lat + t / 2.0) * ctx.sx, ctx.dir, ctx.sy, 0.0, t)
    name = f"Placa {tag}"
    Fy, Fu = _steel(ctx.op.plate_steel, True)
    two_plates = extra > 0 and _tab_split(ctx.op, ctx)
    if two_plates:                                                      # dos placas horizontales (como placas de continuidad) a la altura de las alas de la viga: del alma a las alas del principal
        tp = float(ctx.op.tp_t) if ctx.op.tp_t > 0 else t
        dflt = (float(shp.d) - 2.0 * float(shp.tf)) if getattr(shp, "tf", 0) else H
        sep = max(float(ctx.op.tp_sep) if ctx.op.tp_sep > 0 else dflt, 0.5)           # distancia libre entre las dos placas (a lo largo del peralte de la viga)
        e2 = min(extra, Lp - 0.5)
        Aax2 = np.asarray(ctx.dmain_axis, float) if getattr(ctx, 'dmain_axis', None) is not None else None
        qp = ctx.Q - (Aax2 * float(np.dot(ctx.Q, Aax2)) if Aax2 is not None else 0.0)
        lc = -float(np.dot(qp, ctx.sx))                                  # centro del alma del principal respecto del eje de la viga, en sentido lateral
        hw2 = Hf / 2.0                                                   # medio ancho libre entre las alas del principal
        wsg = 1.0 if float(np.dot(np.cross(ctx.dir, ctx.sx), ctx.sy)) >= 0 else -1.0
        for sgn in (1.0, -1.0):
            yc = ty + sgn * (sep / 2.0 + tp / 2.0)                       # la cara interior de la placa queda a «sep / 2» del eje
            ya, yb = sorted((yc - tp / 2.0, yc + tp / 2.0))
            w0, w1 = sorted((wsg * ya, wsg * yb))
            pp = _plate_prism([(0.0, lc - hw2), (e2, lc - hw2), (e2, lc + hw2), (0.0, lc + hw2)], ctx.Q, ctx.dir, ctx.sx, w0, w1)
            nm = f"Placa {tag}-{'S' if sgn > 0 else 'I'}"
            ctx.parts.append(Part(nm, "plate", f"Placa PL {tp:g} × {Hf:g} × {e2:g}", Fy, Fu, [pp], t=tp))
            if ctx.main_name:
                w2 = float(ctx.op.weld_size)
                for ysd, nsy in ((ya, -1.0), (yb, 1.0)):                 # cordones por las dos caras de la placa
                    P0 = ctx.Q + ctx.sy * ysd + ctx.sx * (lc - hw2)       # contra el alma del principal (borde x = 0)
                    P1 = ctx.Q + ctx.sy * ysd + ctx.sx * (lc + hw2)
                    ctx.welds.append(Weld(f"{nm}-W{'1' if nsy > 0 else '2'}", nm, ctx.main_name, tuple(map(float, P0)), tuple(map(float, P1)), tuple(map(float, ctx.sy * nsy)), tuple(map(float, ctx.dir)), w2, 70.0, tag))
                    for sl, lat_ in ((1.0, lc + hw2), (-1.0, lc - hw2)):   # contra la cara interna de cada ala
                        P0 = ctx.Q + ctx.sy * ysd + ctx.sx * lat_
                        ctx.welds.append(Weld(f"{nm}-F{'a' if sl > 0 else 'b'}{'1' if nsy > 0 else '2'}", nm, ctx.main_name, tuple(map(float, P0)), tuple(map(float, P0 + ctx.dir * e2)),
                                              tuple(map(float, ctx.sy * nsy)), tuple(map(float, -ctx.sx * sl)), w2, 70.0, tag))
    ctx.parts.append(Part(name, "plate", f"Placa simple PL {t:g} × {max(H, Hf):g} × {Wd:g}", Fy, Fu, [pr], t=t))
    if ctx.op.tab_H <= 0 or True:
        pass
    zs = [ty + (i - (n - 1) / 2.0) * s for i in range(n)]
    if _is_open(shp):
        grip = [(name, 0.0, t), (ctx.partname, t, t + shp.tw)]
        p0 = lat + t / 2.0
        nut = t + shp.tw
    else:
        grip = [(ctx.partname, 0.0, shp.bf)]
        p0 = shp.bf / 2.0
        nut = shp.bf
    welded_beam = ctx.op.beam_conn == "Soldada" and _is_open(shp)
    k = 0
    for j in range(cols):
        for i, z in enumerate(zs):
            if welded_beam:
                break
            k += 1
            ctx.bolts.append(_bolt(f"{tag}-B{k}", ctx.at(a + j * g, p0, z), -ctx.sx, ctx.db, 0.0, nut, grip, ctx.op.bolt_grade))
    if welded_beam:                                                # filetes de la placa al alma de la viga: borde superior, borde inferior y borde del extremo
        wv = float(ctx.op.weld_size)
        s0_ = gap_eff(m) + extra
        yt, yb = ty + H / 2.0, ty - H / 2.0
        webf = _halfw(shp)                                          # cara del alma por la que se apoya la placa
        for k_, (vv, nsy) in enumerate(((yt, 1.0), (yb, -1.0))):
            P0 = ctx.Q + ctx.dir * s0_ + ctx.sx * webf + ctx.sy * vv
            P1 = ctx.Q + ctx.dir * Wd + ctx.sx * webf + ctx.sy * vv
            ctx.welds.append(Weld(f"{name}-V{k_ + 1}", name, ctx.partname, tuple(map(float, P0)), tuple(map(float, P1)), tuple(map(float, ctx.sy * nsy)), tuple(map(float, ctx.sx)), wv, 70.0, tag))
        Pa = ctx.Q + ctx.dir * Wd + ctx.sx * webf + ctx.sy * yb
        Pb = ctx.Q + ctx.dir * Wd + ctx.sx * webf + ctx.sy * yt
        ctx.welds.append(Weld(f"{name}-V3", name, ctx.partname, tuple(map(float, Pa)), tuple(map(float, Pb)), tuple(map(float, ctx.dir)), tuple(map(float, ctx.sx)), wv, 70.0, tag))
    # soldaduras de filete en la cara del soporte, una a cada lado de la placa
    if ctx.main_name:
        w = float(ctx.op.weld_size)
        for sg, lat_face in ((1.0, lat + t / 2.0), (-1.0, lat - t / 2.0)):
            hw_ = (Hf if extra > 0 else H) / 2.0
            p0_ = ctx.Q + lat_face * ctx.sx + ctx.sy * (ty_p - hw_ + (0.0 if extra > 0 else clip))
            p1_ = ctx.Q + lat_face * ctx.sx + ctx.sy * (ty_p + hw_ - (0.0 if extra > 0 else clip))
            ctx.welds.append(Weld(f"{name}-W{'1' if sg > 0 else '2'}", name, ctx.main_name, tuple(map(float, p0_)), tuple(map(float, p1_)),
                                  tuple(map(float, ctx.sx * sg)), tuple(map(float, ctx.dir)), w, 70.0, tag))
        if extra > 0 and not two_plates:                           # filetes de los bordes superior e inferior de la placa contra la cara interna de las alas del principal
            for k_, (vs, nfl) in enumerate(((ty_p + Hf / 2.0, -1.0), (ty_p - Hf / 2.0, 1.0))):
                for sg, lat_face in ((1.0, lat + t / 2.0), (-1.0, lat - t / 2.0)):
                    p0_ = ctx.Q + lat_face * ctx.sx + ctx.sy * vs
                    p1_ = p0_ + ctx.dir * max(min(extra, Lp - 0.5), 0.1)
                    ctx.welds.append(Weld(f"{name}-F{k_ + 1}{'a' if sg > 0 else 'b'}", name, ctx.main_name, tuple(map(float, p0_)), tuple(map(float, p1_)),
                                          tuple(map(float, ctx.sx * sg)), tuple(map(float, ctx.sy * nfl)), w, 70.0, tag))
    return Lp


def _dang_geometry(ctx, tag):
    m, shp = ctx.m, ctx.shape
    t = ctx.t
    n, s = _n_rows(ctx, _clear_depth(shp))
    sb = gap_eff(m) + 2.5
    la = ctx.op.dang_la if ctx.op.dang_la > 0 else sb + 1.5
    lo = max(ctx.op.dang_lo, 1.5)
    H = ctx.op.dang_H if ctx.op.dang_H > 0 else (n - 1) * s + 3.0
    l0 = _halfw(shp)
    Fy, Fu = _steel(ctx.op.plate_steel, True)
    for k, sg in enumerate((1, -1)):
        poly = [(-EMBED, sg * l0), (la, sg * l0), (la, sg * (l0 + t)), (t, sg * (l0 + t)), (t, sg * (l0 + lo)), (-EMBED, sg * (l0 + lo))]
        pr = _plate_prism(poly, ctx.Q, ctx.dir, ctx.sx, -H / 2.0, H / 2.0)      # U×V = dir×sx = sy
        pr.o = tuple(map(float, ctx.Q))
        ctx.parts.append(Part(f"Angulo {tag}-{k + 1}", "angle", f"Angulo L {lo:g}x{la:g}x{t:g}", Fy, Fu, [pr], t=t))
    zs = [(i - (n - 1) / 2.0) * s for i in range(n)]
    grip = [(f"Angulo {tag}-1", 0.0, t), (ctx.partname, t, t + 2 * l0), (f"Angulo {tag}-2", t + 2 * l0, 2 * t + 2 * l0)]
    for i, z in enumerate(zs):
        ctx.bolts.append(_bolt(f"{tag}-B{i + 1}", ctx.at(sb, l0 + t, z), -ctx.sx, ctx.db, 0.0, 2 * t + 2 * l0, grip, ctx.op.bolt_grade))
        for k, sg in enumerate((1, -1)):                # pernos de las alas salientes hacia el soporte
            ctx.bolts.append(_bolt(f"{tag}-S{i + 1}{k + 1}", ctx.at(t, sg * (l0 + lo * 0.62), z), -ctx.dir, ctx.db, 0.0, t + 1.0,
                                   [(f"Angulo {tag}-{k + 1}", 0.0, t)], ctx.op.bolt_grade))
    return la


def _seat_geometry(ctx, tag):
    m, shp = ctx.m, ctx.shape
    t = max(ctx.t, 0.375)
    Lh, Lv = max(ctx.op.seat_Lh, 2.0), max(ctx.op.seat_Lv, 2.0)
    W = ctx.op.seat_W if ctx.op.seat_W > 0 else min(max(shp.bf if shp.bf > 0 else 6.0, 4.0), 12.0)
    yb = -shp.d / 2.0
    g = gap_eff(m)
    poly = [(-EMBED, yb - Lv), (t, yb - Lv), (t, yb - t), (Lh, yb - t), (Lh, yb), (-EMBED, yb)]
    pr = _plate_prism(poly, ctx.Q, ctx.dir, ctx.sy, -W / 2.0, W / 2.0)        # U×V = dir×sy = -sx (simetrico)
    Fy, Fu = _steel(ctx.op.plate_steel, True)
    ctx.parts.append(Part(f"Asiento {tag}", "angle", f"Angulo de asiento L {Lh:g}x{Lv:g}x{t:g}", Fy, Fu, [pr], t=t))
    gauge = min(max(W - 2.5, 1.5), 4.0)
    for k, sg in enumerate((1, -1)):
        ctx.bolts.append(_bolt(f"{tag}-A{k + 1}", ctx.at(Lh * 0.62, sg * gauge / 2.0, yb - t), ctx.sy, ctx.db, 0.0, t + (shp.tf if shp.tf > 0 else 0.5),
                               [(f"Asiento {tag}", 0.0, t), (ctx.partname, t, t + (shp.tf if shp.tf > 0 else 0.5))], ctx.op.bolt_grade))
        ctx.bolts.append(_bolt(f"{tag}-S{k + 1}", ctx.at(t, sg * gauge / 2.0, yb - Lv * 0.6), -ctx.dir, ctx.db, 0.0, t + 1.0,
                               [(f"Asiento {tag}", 0.0, t)], ctx.op.bolt_grade))
    return max(g, 0.5)


def endplate_layout(op, shp, extended):
    """Medidas de la placa extrema: espesor, semialto, gramil, ancho y posicion vertical de cada fila de pernos (respecto del centro de la viga)."""
    t = max(op.plate_t, 0.5)
    d = shp.d
    bf = shp.bf if shp.bf > 0 else shp.d
    hollow = shp.is_hollow
    ext = max(op.ep_ext, 2.0) if (extended or hollow) else 0.5
    hh = op.ep_h / 2.0 if op.ep_h > 0 else d / 2.0 + ext
    gb = op.ep_g if op.ep_g > 0 else min(max(bf - 2.5, 2.5), 5.5)
    wide = op.ep_w if op.ep_w > 0 else max(bf + 1.5, gb + 3.0)
    if op.ep_rows:
        rows = [float(v) for v in op.ep_rows]
    elif hollow:
        rows = [hh - 1.5, -(hh - 1.5)]
    else:
        tf = shp.tf if shp.tf > 0 else 0.5
        if extended:
            rows = [d / 2.0 + ext - 1.5, d / 2.0 - tf - 1.75, -(d / 2.0 - tf - 1.75), -(d / 2.0 + ext - 1.5)]
        else:
            rows = [d / 2.0 - tf - 1.75, -(d / 2.0 - tf - 1.75)]
    return {"t": t, "hh": hh, "gb": gb, "wide": wide, "rows": rows, "hollow": hollow, "bf": bf}


def beam_end_welds(ctx, tag, B_name, s_face, faces=("top", "bot", "web")):
    """Cordones del contorno de la sección del miembro contra la placa (o el soporte) en `s_face` (distancia desde Q a lo largo de ctx.dir), uno por segmento
    del contorno, con el tipo elegido por cara del miembro: ala superior, ala inferior y alma.  Devuelve los Weld."""
    from .fem.model3d import i_section, rect_tube
    from .specs import WELD_TYPES
    shp, op = ctx.shape, ctx.op
    d, bf = float(shp.d), float(shp.bf if shp.bf > 0 else shp.d)
    if shp.kind == W_SHAPE:
        poly = i_section(shp)
        tf = float(shp.tf)
        face_of = lambda y: "top" if y > d / 2.0 - tf - 1e-6 else ("bot" if y < -d / 2.0 + tf + 1e-6 else "web")      # noqa: E731
    elif shp.is_round:
        return []
    else:
        poly = rect_tube(shp)[0]
        face_of = lambda y: "top" if y > d / 2.0 - 1e-6 else ("bot" if y < -d / 2.0 + 1e-6 else "web")                # noqa: E731
    types = {"top": op.wf_top, "bot": op.wf_bot, "web": op.wf_web}
    tmap = {"top": min(float(getattr(shp, "tf", 0.5)) or 0.5, 0.375), "bot": min(float(getattr(shp, "tf", 0.5)) or 0.5, 0.375), "web": float(op.weld_size)}
    out = []
    n = len(poly)
    nB = ctx.dir
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        ym = 0.5 * (a[1] + b[1])
        f = face_of(ym)
        if f not in faces:
            continue
        if f == "web" and abs(a[1] - b[1]) < 1e-9:
            pass
        P0 = ctx.at(s_face, a[0], a[1])
        P1 = ctx.at(s_face, b[0], b[1])
        if float(np.linalg.norm(P1 - P0)) < 0.05:
            continue
        nA = ctx.sx * (b[1] - a[1]) - ctx.sy * (b[0] - a[0])
        nA = nA / max(float(np.linalg.norm(nA)), 1e-12)
        ty = types[f]
        size = float(op.weld_size) if ty == WELD_TYPES[0] else (tmap[f] if ty == WELD_TYPES[1] else 0.5 * tmap[f])
        w = Weld(f"{tag}-W{k + 1}", ctx.partname, B_name, tuple(map(float, P0)), tuple(map(float, P1)), tuple(map(float, nA)), tuple(map(float, nB)), float(size), 70.0, tag)
        w.kind = ty
        out.append(w)
    return out


def _endplate_geometry(ctx, tag, extended):
    m, shp = ctx.m, ctx.shape
    L = endplate_layout(ctx.op, shp, extended)
    t, hh, gb, wide, rows, hollow = L["t"], L["hh"], L["gb"], L["wide"], L["rows"], L["hollow"]
    poly = [(-wide / 2, -hh), (wide / 2, -hh), (wide / 2, hh), (-wide / 2, hh)]
    pr = _plate_prism(poly, ctx.Q - ctx.dir * (-EMBED * 0.0), ctx.sx, ctx.sy, 0.0, t)      # U×V = sx×sy = dir: extruye hacia el miembro
    Fy, Fu = _steel(ctx.op.plate_steel, True)
    ctx.parts.append(Part(f"Placa extrema {tag}", "plate", f"Placa extrema PL {t:g}", Fy, Fu, [pr], t=t))
    for i, v in enumerate(rows):
        for k, sg in enumerate((1, -1)):
            ctx.bolts.append(_bolt(f"{tag}-B{i + 1}{k + 1}", ctx.at(t, sg * (gb / 2.0 if not hollow else wide / 2.0 - 1.25), v), -ctx.dir, ctx.db, 0.0, t + 1.0,
                                   [(f"Placa extrema {tag}", 0.0, t)], ctx.op.bolt_grade))
    ctx.welds += beam_end_welds(ctx, tag, f"Placa extrema {tag}", t)           # soldadura de la viga a la placa, con el tipo elegido por cara
    return t


def _weld_geometry(ctx, tag):
    """Alas soldadas a tope contra el apoyo; el alma lleva una placa simple atornillada."""
    shp = ctx.shape
    if _is_open(shp):
        _tab_geometry(ctx, tag)
    if ctx.main_name:
        ctx.welds += beam_end_welds(ctx, f"{tag}f", ctx.main_name, 0.12, faces=("top", "bot"))      # alas soldadas al soporte con el tipo elegido por ala
    return 0.12


def _continuity(ctx, nd, tag, main_frame_, mshape, t):
    """Placas de continuidad dentro de una columna I frente a las alas de la viga que llega a su ala (operacion «Placas de continuidad»)."""
    if mshape.kind != W_SHAPE:
        return []
    A, msx, msy = main_frame_
    d2 = (float(np.dot(ctx.dir, msx)), float(np.dot(ctx.dir, msy)))
    if abs(d2[1]) < 0.6 * max(math.hypot(*d2), 1e-9):       # no llega por la cara del ala (de lado a lo largo de d)
        return []
    t = max(float(t), 0.25)
    out = []
    Fy, Fu = _steel("ASTM A36", True)
    dm, tfm = ctx.shape.d, (ctx.shape.tf if ctx.shape.tf > 0 else 0.5)
    for k, lv in enumerate((dm / 2.0 - tfm / 2.0, -(dm / 2.0 - tfm / 2.0))):
        base = ctx.P0 + lv * ctx.sy                       # punto del eje principal a la altura de esa ala
        zc = float(np.dot(base, A))
        for j, sg in enumerate((1, -1)):
            x0, x1 = sg * mshape.tw / 2.0, sg * mshape.bf / 2.0
            y0, y1 = -(mshape.d / 2.0 - mshape.tf), (mshape.d / 2.0 - mshape.tf)
            poly = [(min(x0, x1), y0), (max(x0, x1), y0), (max(x0, x1), y1), (min(x0, x1), y1)]
            pr = Prism(poly=poly, o=tuple(map(float, A * (zc - t / 2.0))), U=tuple(map(float, msx)), V=tuple(map(float, msy)), w0=0.0, w1=t)
            out.append(Part(f"Continuidad {tag}-{k + 1}{j + 1}", "stiff", f"Placa de continuidad PL {t:g}", Fy, Fu, [pr], t=t))
    return out


def cope_prisms(shape, o, sx, sy, A, s0, s1, ct, cb, cl):
    """Viga I con corte (cope) en el extremo: alma como poligono con las muescas y alas acortadas.  Profundidades ct / cb y longitud cl en in."""
    d, bf, tf, tw = shape.d, shape.bf, shape.tf, shape.tw
    ct, cb, cl = max(ct, 0.0), max(cb, 0.0), max(cl, 0.0)
    # el alma va solo ENTRE las alas (las alas son prismas aparte): si el alma llegara hasta el borde exterior, sus caras coincidirían con las de las alas
    # (parpadeo y líneas de más en el visor, y volumen repetido en la malla); en la zona del corte sube o baja hasta la profundidad del corte
    top_in, bot_in = d / 2 - tf, -d / 2 + tf
    pts = []
    if cb > 0:
        pts += [(s0, -d / 2 + cb), (s0 + cl, -d / 2 + cb), (s0 + cl, bot_in)]
    else:
        pts += [(s0, bot_in)]
    pts += [(s1, bot_in), (s1, top_in)]
    if ct > 0:
        pts += [(s0 + cl, top_in), (s0 + cl, d / 2 - ct), (s0, d / 2 - ct)]
    else:
        pts += [(s0, top_in)]
    o = tuple(map(float, o))
    web = Prism(poly=[(float(a), float(b)) for a, b in pts], o=o, U=tuple(map(float, A)), V=tuple(map(float, sy)), w0=-tw / 2.0, w1=tw / 2.0)
    U, V = tuple(map(float, sx)), tuple(map(float, sy))
    st = s0 + (cl if ct > 0 else 0.0)
    sb = s0 + (cl if cb > 0 else 0.0)
    return [web,
            Prism(poly=[(-bf / 2, d / 2 - tf), (bf / 2, d / 2 - tf), (bf / 2, d / 2), (-bf / 2, d / 2)], o=o, U=U, V=V, w0=float(st), w1=float(s1)),
            Prism(poly=[(-bf / 2, -d / 2), (bf / 2, -d / 2), (bf / 2, -d / 2 + tf), (-bf / 2, -d / 2 + tf)], o=o, U=U, V=V, w0=float(sb), w1=float(s1))]


def _in_prism(pr, P, c=0.0):
    """Mascara de los puntos P (N, 3) que caen dentro del prisma `pr` (envolvente de su poligono) inflado en c (in)."""
    o, U, V = np.asarray(pr.o, float), np.asarray(pr.U, float), np.asarray(pr.V, float)
    W = np.cross(U, V)
    d = P - o
    u, v, w = d @ U, d @ V, d @ W
    inw = (w >= pr.w0 - c) & (w <= pr.w1 + c)
    if pr.circle is not None:
        return inw & (np.hypot(u, v) <= pr.circle[0] + c)
    poly = np.asarray(pr.poly, float)
    return inw & (u >= poly[:, 0].min() - c) & (u <= poly[:, 0].max() + c) & (v >= poly[:, 1].min() - c) & (v <= poly[:, 1].max() + c)


def auto_cope(shp, base, dirv, sx, sy, solids, c=0.5, step=0.25):
    """Corte (cope) minimo de una viga I para que sus alas y su alma libren los solidos `solids` (prismas del miembro principal) con una holgura `c`.
    `base` = punto donde empieza la viga (su extremo), `dirv` = hacia afuera; las coordenadas (x, y) de la seccion son (sx, sy).  -> (ct, cb, cl) en in."""
    pts, ys, ss = [], [], []
    ss_ = np.arange(step / 2.0, 18.0, step)
    for (x0, y0, x1, y1) in shp.rects():
        xs_ = np.arange(x0 + step / 2.0, x1, step) if x1 - x0 > step else np.array([(x0 + x1) / 2.0])
        ys_ = np.arange(y0 + step / 2.0, y1, step) if y1 - y0 > step else np.array([(y0 + y1) / 2.0])
        X, Y, S = np.meshgrid(xs_, ys_, ss_, indexing="ij")
        X, Y, S = X.ravel(), Y.ravel(), S.ravel()
        pts.append(base + np.outer(S, dirv) + np.outer(X, sx) + np.outer(Y, sy))
        ys.append(Y)
        ss.append(S)
    if not pts:
        return 0.0, 0.0, 0.0
    P, Y, S = np.vstack(pts), np.concatenate(ys), np.concatenate(ss)
    hit = np.zeros(len(P), bool)
    for pr in solids:
        hit |= _in_prism(pr, P, c)
    if not hit.any():
        return 0.0, 0.0, 0.0
    Yh, Sh = Y[hit], S[hit]
    top, bot = Yh[Yh > 0], Yh[Yh <= 0]
    up = lambda v: math.ceil(v / 0.25 - 1e-9) * 0.25            # noqa: E731
    ct = up(shp.d / 2.0 - float(top.min())) if len(top) else 0.0
    cb = up(float(bot.max()) + shp.d / 2.0) if len(bot) else 0.0
    ct = max(ct, up(shp.tf)) if ct > 0 else 0.0
    cb = max(cb, up(shp.tf)) if cb > 0 else 0.0
    cl = up(float(Sh.max()) + step / 2.0)
    return ct, cb, cl


def auto_cope_for(nd, m, op=None):
    """Cope automatico de la viga `m` (viga I que llega al principal con placa simple o doble angulo): (ct, cb, cl) o None si no hace falta o no aplica."""
    op = op or next((o for o in nd.operations if o.is_connection and o.member == m.name), None)
    if op is None or op.kind not in (OP_TAB, OP_DANG) or not getattr(op, "cope_auto", False) or tab_extra(nd, m, op) > 0:
        return None
    shp = shape_of(m.shape)
    if shp.kind != W_SHAPE or any(o.kind in (OP_COPE, OP_CUT) and (o.member == m.name or m.name in (o.targets or [])) for o in nd.operations):
        return None
    mshape = shape_of(nd.main_shape)
    A, msx, msy = main_frame(nd)
    lneg, lpos = nd.lengths()
    if lneg + lpos < 1.0:
        lneg = lpos = 24.0
    solids = section_prisms(mshape, (0, 0, 0), msx, msy, A, -lneg, lpos)
    info = attach_info(nd, m)
    if not info["touches"]:
        return None
    _, sx, sy = member_frame(m)
    ct, cb, cl = auto_cope(shp, info["Q"] + info["dir"] * gap_eff(m), info["dir"], sx, sy, solids)
    return (ct, cb, cl) if (ct > 0 or cb > 0) else None


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
    """Puntos (3D, en el plano de la cartela) del contorno de la cartela de un miembro: base sobre el principal y punta bajo el miembro.
    Las medidas (largo, ancho de la base, ancho de la punta y corte de esquinas) se pueden fijar en la operación; 0 = automático."""
    m, shp, op = ctx.m, ctx.shape, ctx.op
    dm = max(min(shp.d if not shp.is_round else shp.d, 16.0), 4.0)
    hb = op.gus_hb if op.gus_hb > 0 else max(dm * 1.05, 7.0)
    hm = op.gus_hm if op.gus_hm > 0 else max(dm * 0.9, 5.0)
    rows = max(1, int(op.n_bolts))
    s = max(op.bolt_s, 2.5)
    ov = (rows - 1) * s + 3.0 + 1.0
    gl = 2.0 if op.kind == OP_GUSSET else 6.0
    tip = gl + (ov if op.kind == OP_GUSSET else 0.0)
    if op.gus_L > 0:
        if op.kind == OP_GUSSET:
            tip = op.gus_L                                       # la cartela se alarga, el miembro queda donde estaba
        else:
            gl = tip = op.gus_L                                  # soldada: el miembro termina donde termina la cartela
    cut = min(max(op.gus_cut, 0.0), hm / 2.0, max(tip, 0.1))
    pts = [ctx.at(-EMBED, 0.0, -hb / 2.0), ctx.at(-EMBED, 0.0, hb / 2.0)]
    if cut > 1e-6:
        pts += [ctx.at(tip - cut, 0.0, hm / 2.0), ctx.at(tip, 0.0, hm / 2.0 - cut), ctx.at(tip, 0.0, -hm / 2.0 + cut), ctx.at(tip - cut, 0.0, -hm / 2.0)]
    else:
        pts += [ctx.at(tip, 0.0, hm / 2.0), ctx.at(tip, 0.0, -hm / 2.0)]
    return pts, gl, ov, hm


def _gusset_members(ctxs, nd):
    """Una cartela por plano: la envolvente de los contornos de los miembros que comparten plano (p. ej. las dos diagonales de una V)."""
    groups = []
    for c in ctxs:
        if c.op.kind not in GUSSET_OPS:
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
        Fy, Fu = _steel(g["items"][0].op.plate_steel, True)
        names = "+".join(c.m.name for c in g["items"])
        mdl.parts.append(Part(f"Cartela {gi + 1}", "gusset", f"Cartela PL {t:g} ({names})", Fy, Fu, [pr], t=t))
        for c in g["items"]:
            if c.op.kind != OP_GUSSET:
                continue
            m, shp = c.m, c.shape
            _, gl, ov, hm = _gusset_outline(c)
            rows = max(1, int(c.op.n_bolts))
            s = max(c.op.bolt_s, 2.5)
            gauge = max(min(hm * 0.5, 6.0), 2.5)
            if _is_open(shp):
                grip = [(f"Cartela {gi + 1}", 0.0, t), (c.partname, t, t + shp.tw)]
                p0, nut = lat + t / 2.0, t + shp.tw
            else:
                grip = [(c.partname, 0.0, shp.bf)]
                p0, nut = shp.bf / 2.0, shp.bf
            for i in range(rows):
                for k, sg in enumerate((1, -1)):
                    mdl.bolts.append(_bolt(f"{m.name}-B{i + 1}{k + 1}", c.at(gl + 1.5 + i * s, p0, sg * gauge / 2.0), -c.sx, c.db, 0.0, nut, grip, c.op.bolt_grade))


# ================================================================================================== modelo completo
def exit_dist(ext, o2, d2):
    """Distancia desde el punto de llegada hasta la cara del principal que toca el miembro, o None si no lo toca.  Un miembro que sigue el eje del
    principal (paralelo y sobre el) arranca en el propio punto de llegada: distancia 0."""
    if math.hypot(d2[0], d2[1]) > 1e-6:
        return ray_exit(ext, o2, d2)
    return 0.0 if math.hypot(o2[0], o2[1]) < 1e-6 else None


def attach_info(nd, m) -> dict:
    """Como llega un miembro al principal: punto de contacto Q, distancia s_ex desde el eje, cara ('ala' | 'alma' | 'cara') y direccion."""
    mshape = shape_of(nd.main_shape)
    A, msx, msy = main_frame(nd)
    dirv = member_dir(m)
    P0, o2 = attach_point(nd, m, (A, msx, msy))
    d2 = (float(np.dot(dirv, msx)), float(np.dot(dirv, msy)))
    s_ex = exit_dist(outer_extent(mshape), o2, d2)
    face = "cara"
    if s_ex is not None and mshape.kind == W_SHAPE:
        y = o2[1] + s_ex * d2[1]
        face = "ala" if abs(y) >= mshape.d / 2.0 - 1e-6 else "alma"
    return {"Q": P0 + dirv * (s_ex or 0.0), "s": s_ex, "face": face, "dir": dirv, "P0": P0, "main": mshape, "touches": s_ex is not None}


def _angles(v):
    """(azimut, elevacion) en grados de un vector."""
    v = unit(v)
    return (math.degrees(math.atan2(v[1], v[0])) % 360.0 if math.hypot(v[0], v[1]) > 1e-9 else 0.0), math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))


def set_main(nd, name) -> list:
    """Designa como principal al miembro `name` (como el miembro de apoyo de IDEA StatiCa): el nudo se mueve al punto donde ese miembro llegaba al
    principal anterior, el miembro toma el lugar del principal (seccion, acero, eje y giro) y el principal anterior pasa a ser miembro conectado
    (dos miembros si pasaba por el nudo) con la misma geometria global.  El miembro designado pasa por el nudo y termina en el: queda del lado de
    donde venia.  Sus operaciones y sus cargas dejan de tener sentido (eran su conexion al principal anterior) y se descartan; las de los demas
    miembros se conservan.  Devuelve los avisos para el usuario."""
    m = nd.member_named(name)
    if m is None:
        return []
    notes = []
    old = copy.copy(nd)
    A, msx, msy = main_frame(nd)
    info = attach_info(nd, m)
    O_old = np.zeros(3)
    Pnew = info["P0"]
    s_ex = info["s"] or 0.0
    if not info["touches"]:
        notes.append(f"El eje de «{name}» no tocaba al principal anterior: el nudo se coloca en el punto de su posición ({m.pos:g}).")
    lneg, lpos = old.lengths()
    # ---- el principal anterior se vuelve miembro (o dos, si pasaba por el nudo)
    t_att = float(np.dot(info["P0"] - O_old, A))                      # altura del punto de llegada sobre el eje del principal anterior
    olds = []
    for sgn, ln in ((1.0, lpos), (-1.0, lneg)):
        if ln - sgn * t_att > 1e-6:                                    # queda cuerpo del principal anterior de ese lado del punto de llegada
            olds.append((sgn, ln))
    others = [x for x in nd.members if x is not m]
    new_members = []
    # ---- el miembro designado toma el lugar del principal
    nd.main_name, nd.main_shape, nd.main_steel = m.name, m.shape, m.steel
    nd.main_az, nd.main_el, nd.main_roll = m.az, m.el, m.roll
    nd.main_end = END_LABELS[2]
    nd.main_len_neg, nd.main_len_pos = 0.0, max(s_ex + gap_eff(m) + m.L, 1.0)
    A2, msx2, msy2 = main_frame(nd)
    frm2 = (A2, msx2, msy2)

    def rel(P):
        D = np.asarray(P, float) - Pnew
        return float(np.dot(D, A2)), float(np.dot(D, msy2)), float(np.dot(D, msx2))

    mshape2 = shape_of(nd.main_shape)
    ext2 = outer_extent(mshape2)
    new_sides = []
    for k, (sgn, ln) in enumerate(olds):
        t0 = float(np.dot(Pnew - O_old, A))                   # altura del punto de llegada sobre el eje del principal anterior
        P0 = O_old + A * t0
        dirv = sgn * A
        pos, off, off2 = rel(P0)
        d2 = (float(np.dot(dirv, msx2)), float(np.dot(dirv, msy2)))
        s2 = exit_dist(ext2, (off2, off), d2)
        if s2 is None:
            notes.append(f"El principal anterior ({old.main_name}) no toca al nuevo principal: no se conserva su lado {'+' if sgn > 0 else '−'}.")
            continue
        Lfree = ln - sgn * t0 - s2
        if Lfree < 1.0:
            continue
        az, el = _angles(dirv)
        new_members.append(Member(name="", shape=old.main_shape, steel=old.main_steel, az=az, el=el, pos=pos, off=off, off2=off2, L=Lfree, roll=old.main_roll, gap=-0.5))      # sin separación: toca al nuevo principal
        new_sides.append(sgn)
    for mm, sgn in zip(new_members, new_sides):               # un solo tramo conserva el nombre; dos llevan + y −
        mm.name = old.main_name if len(new_members) == 1 else f"{old.main_name}{'+' if sgn > 0 else '−'}"
    # ---- los demas miembros conservan su geometria global (nuevo origen y ejes)
    moved = []
    for x in others:
        io = attach_info(old, x)
        x.pos, x.off, x.off2 = rel(io["P0"])
        d2 = (float(np.dot(io["dir"], msx2)), float(np.dot(io["dir"], msy2)))
        s_new = exit_dist(ext2, (x.off2, x.off), d2)
        gap = (io["s"] or 0.0) + x.gap - (s_new or 0.0)                    # el extremo del miembro queda donde estaba
        if s_new is None:
            notes.append(f"«{x.name}» no toca al nuevo principal (su eje no cruza la sección); revise su posición.")
        if gap > 1e-6 and abs(gap - x.gap) > 1e-6:
            moved.append(x.name)
        x.gap = gap
    if moved:
        notes.append("Quedan separados del nuevo principal (retranqueo) para no cambiar su posición: " + ", ".join(moved)
                     + ". Acérquelos o cambie sus operaciones.")
    nd.members = new_members + others
    # ---- la placa base sigue al extremo libre donde estaba: la del miembro designado queda en su extremo (lado +); la del principal anterior pasa al tramo
    #      del lado donde estaba
    bop = nd.base_op()
    if bop is not None and bop.member == old.main_name:
        want = -1.0 if bop.end < 0 else 1.0                              # lado del eje del principal anterior
        tgt = next((x for x in new_members if float(np.dot(member_dir(x), A)) * want > 0.5), None)
        if tgt is None:
            nd.operations = [o for o in nd.operations if o is not bop]
            notes.append("Se descartó la placa base: el tramo del principal anterior donde estaba ya no existe.")
        else:
            bop.member, bop.end = tgt.name, -1
            notes.append(f"La placa base pasa a «{tgt.name}» (el mismo extremo libre).")
    elif bop is not None and bop.member == m.name:
        bop.end = 1
        notes.append("La placa base queda en el extremo libre del nuevo principal (lado +).")
    # ---- operaciones y cargas
    for nmx in (m.name,):
        dropped_ops = [o for o in nd.operations if o.member == nmx and o.kind != OP_BASE]
        dropped_loads = [x for x in nd.loads if x.member == nmx]
        nd.operations = [o for o in nd.operations if o.member != nmx or o.kind == OP_BASE]
        nd.loads = [x for x in nd.loads if x.member != nmx]
    if dropped_ops or dropped_loads:
        notes.append(f"Se descartaron {len(dropped_ops)} operación(es) y {len(dropped_loads)} carga(s) de «{m.name}»: eran su conexión al principal anterior; "
                     f"defínalas de nuevo en los miembros que ahora llegan a él.")
    if new_members:
        notes.append("El principal anterior pasa a ser miembro conectado: " + ", ".join(x.name for x in new_members) + " (sin operaciones ni cargas todavía).")
    return notes


def workplane_frame(o):
    """Cara (FaceFrame) del plano de trabajo de la operación: pasa por (x, y, z) y su normal tiene azimut `wp_az` y elevación `wp_el`."""
    from .ops import FaceFrame
    az, el = math.radians(o.wp_az), math.radians(o.wp_el)
    n = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = unit(np.cross(ref, n))
    L = max(float(o.wp_size), 1.0)
    return FaceFrame(np.array([o.wp_x, o.wp_y, o.wp_z], float) - e1 * L / 2.0, e1, n, L, L / 2.0, 0.0)


def resolve_aligns(nd, prj=None, iters=6):
    """Operaciones «Alinear cara»: mueve cada miembro conectado hasta que la cara elegida quede en el plano de la cara de referencia (o de un plano de trabajo),
    a la distancia `al_offset`.  Devuelve una copia del nudo con `pos`, `off`, `off2` y `gap` de esos miembros ajustados (y `_resolved` = True)."""
    import copy
    from .specs import OP_ALIGN
    aligns = [(i, o) for i, o in enumerate(nd.operations) if o.kind == OP_ALIGN]
    if not aligns or getattr(nd, "_resolved", False):
        return nd, []
    nd2 = copy.deepcopy(nd)
    work = copy.deepcopy(nd)
    work.operations = [o for o in work.operations if o.kind != OP_ALIGN]
    work._resolved = True
    notes = []
    A, msx, msy = main_frame(nd2)
    for i, o in aligns:
        mem = nd2.member_named(o.member)
        if mem is None or o.member == nd2.main_name:
            notes.append(f"Operación {i + 1} «Alinear cara»: elija un miembro conectado (el principal no se mueve).")
            continue
        wm = work.member_named(o.member)
        for _ in range(iters):
            mdl = build_nodo(work, prj=prj)
            reg = mdl.elems
            e, r = reg.get(o.member), reg.get(o.parent)
            if e is None or r is None or o.face not in e["faces"] or not (o.ref_face in r["faces"] or "Plano" in r["faces"]):
                notes.append(f"Operación {i + 1} «Alinear cara»: elija la cara del miembro y la referencia.")
                break
            ff = e["faces"][o.face]
            fr = r["faces"].get(o.ref_face) or r["faces"].get("Plano")
            n = unit(np.asarray(fr.N, float))
            delta = float(np.dot(np.asarray(ff.O, float) - np.asarray(fr.O, float), n)) - float(o.al_offset)
            if abs(delta) < 1e-4:
                break
            d = -delta * n
            dirv = member_dir(wm)
            dax = float(np.dot(d, dirv))
            dper = d - dax * dirv
            for mm in (mem, wm):
                mm.gap += dax
                mm.pos += float(np.dot(dper, A))
                mm.off2 += float(np.dot(dper, msx))
                mm.off += float(np.dot(dper, msy))
        else:
            notes.append(f"Operación {i + 1} «Alinear cara»: la cara no es paralela al plano de referencia; se alineó lo mejor posible.")
    nd2._resolved = True
    return nd2, notes


def build_model(prj, vals=None) -> Model3D:
    """Modelo 3D de la conexion.  `vals` = {"case": i} arma el modelo del analisis FEM del caso de carga i (miembros recortados, apoyo y cargas)."""
    from .specs import ATTR_OF
    nd = getattr(prj, ATTR_OF[prj.ctype])
    return build_nodo(nd, name=prj.element or prj.ctype, prj=prj, fem=vals if isinstance(vals, dict) else None)


FEM_LEN = 30.0        # largo de miembro que se modela en el analisis FEM (in): mas alla, el esfuerzo ya no depende del nudo


def build_nodo(nd, name="Nudo", hardware=None, prj=None, fem=None) -> Model3D:
    """Modelo 3D del nudo: el miembro principal, los miembros conectados y el resultado de aplicar las operaciones en el orden de la lista.
    Con `fem` ({"case": i}) los miembros se recortan a `FEM_LEN` y se agregan el apoyo del principal y las cargas del caso (analisis nodal)."""
    hw = True if fem is not None else (nd.show_hw if hardware is None else hardware)
    nd, align_notes = resolve_aligns(nd, prj)
    mdl = Model3D(name)
    mdl.notes += align_notes
    mshape = shape_of(nd.main_shape)
    A, msx, msy = main_frame(nd)
    lneg, lpos = nd.lengths()
    Fy, Fu = _steel(nd.main_steel)
    if lneg + lpos < 1.0:
        lneg = lpos = 24.0
    L_cap = None
    if fem is not None:
        L_cap = float(fem.get("L", FEM_LEN))
        # el tramo modelado del principal rodea a los puntos donde llegan los miembros (no al origen del nudo): de (menor posicion − L) a (mayor + L)
        pos = [float(m.pos) for m in nd.members] or [0.0]
        lo, hi = max(min(pos) - L_cap, -lneg), min(max(pos) + L_cap, lpos)
        if hi - lo < 2.0 * L_cap * 0.25:
            lo, hi = max(-lneg, min(pos) - L_cap), min(lpos, max(pos) + L_cap)
        lneg, lpos = -lo, hi                                    # lneg puede ser negativo: el tramo empieza por encima del origen
    fem_ends = {}
    mdl.parts.append(Part(nd.main_name, "column", f"{nd.main_name} {mshape.label}", Fy, Fu,
                          section_prisms(mshape, (0, 0, 0), msx, msy, A, -lneg, lpos), t=mshape.tw, stub=True))
    ext = outer_extent(mshape)
    names = {m.name for m in nd.members}
    for o in nd.operations:
        if o.member not in names and not (o.kind == OP_BASE and o.member == nd.main_name) and not (o.kind in GENERIC_OPS and not o.member):
            mdl.notes.append(f"Operación «{o.kind}»: el miembro «{o.member}» no existe.")
    ctxs = []
    shapes_by_name = {}
    reg = {}                                            # elementos con caras para las operaciones generales: nombre -> {type, faces, part, t, Fy, Fu}
    reg[nd.main_name] = {"type": "miembro", "part": nd.main_name, "t": mshape.tw, "Fy": Fy, "Fu": Fu,
                         "faces": member_faces(mshape, A * (-lneg), A * lpos, A, msx, msy)}
    free_ends, frames = {}, {}                          # nombre -> (inicio, fin, direccion) y nombre -> marco de la seccion, para la placa base
    axes = []                                           # (nombre, inicio, fin, punto sobre el eje principal, posicion) de cada miembro conectado, para las cotas
    for i, m in enumerate(nd.members):
        shp = shape_of(m.shape)
        dirv = member_dir(m)
        _, sx, sy = member_frame(m)
        P0, o2 = attach_point(nd, m, (A, msx, msy))
        d2 = (float(np.dot(dirv, msx)), float(np.dot(dirv, msy)))
        s_ex = exit_dist(ext, o2, d2)
        if s_ex is None:
            mdl.notes.append(f"{m.name}: su eje no toca al miembro principal (revise el azimut, la elevación o la posición).")
            s_ex = 0.0
        Q = P0 + dirv * s_ex
        Lm = max(min(m.L, L_cap) if L_cap else m.L, 1.0)
        ops = nd.ops_of(m.name)
        conns = [o for o in ops if o.is_connection] if hw else []
        conn_op = conns[0] if conns else None
        diag = abs(m.el) >= DIAG_MIN
        ctxs_m, mss = [], []
        align = None
        for k, cop in enumerate(conns or [None]):                 # cada operacion de conexion del miembro se arma en el orden de la lista
            c = _Ctx(m, cop, shp, P0, Q, dirv, sx, sy, mshape, mshape.d)
            c.partname = m.name
            c.main_name = nd.main_name
            tag = m.name if k == 0 else f"{m.name}.{k + 1}"
            kind = cop.kind if cop else None
            if cop is not None and kind in (OP_EP_FLUSH, OP_EP_EXT, OP_SEAT):
                fr = aligned_frame(nd, m, cop, dirv, sx, sy)
                if fr is not None:                                 # la placa se alinea con otro elemento (p. ej. la cara de la columna) y no con el miembro conectado
                    c.dir, c.sx, c.sy = fr
                    align = (fr[0], k)
            ms_k = None                                           # distancia que exige esta operacion desde Q hasta el inicio del miembro (sin el desplazamiento del usuario)
            if kind == OP_TAB:
                c.extra = tab_extra(nd, m, cop)
                c.dmain_axis = A
                _tab_geometry(c, tag)
                if c.extra > 0:
                    ms_k = 0.5 + c.extra                          # la viga queda fuera de las alas del principal
            elif kind == OP_DANG:
                _dang_geometry(c, tag)
            elif kind == OP_SEAT:
                _seat_geometry(c, tag)
            elif kind == OP_EP_FLUSH:
                ms_k = _endplate_geometry(c, tag, False)
            elif kind == OP_EP_EXT:
                ms_k = _endplate_geometry(c, tag, True)
            elif kind == OP_WELD:
                ms_k = _weld_geometry(c, tag)
            elif kind in GUSSET_OPS:
                _, gl, ov, hm = _gusset_outline(c)
                ms_k = gl if kind == OP_GUSSET else gl + 0.1
            if ms_k is not None:
                mss.append(ms_k)
            ctxs_m.append(c)
        c = ctxs_m[0]
        ms = (max(mss) + float(m.gap)) if mss else gap_eff(m)       # el desplazamiento sobre el eje (m.gap) mueve el miembro hacia atrás (+) o hacia adelante (−)
        tag = m.name
        for o in ops:
            if o.kind == OP_CONT and hw:
                pl = _continuity(c, nd, tag, (A, msx, msy), mshape, o.cont_t)
                if not pl:
                    mdl.notes.append(f"{m.name}: las placas de continuidad solo se dibujan en una columna I a la que llega el miembro por la cara del ala.")
                mdl.parts += pl
        acut = None
        if align is not None:                                       # extremo del miembro cortado por el plano de la placa alineada con otro elemento
            d2 = align[0]
            cth = float(np.dot(dirv, d2))
            if abs(cth) > 0.05 and cth < 0.9999:
                extra = (max(shp.d, shp.bf) / 2.0) * math.sqrt(max(1.0 - cth * cth, 0.0)) / abs(cth) + 0.5
                acut = (tuple(map(float, Q + d2 * ms)), tuple(map(float, -d2)))
                ms -= extra
                Lm += extra
        Fy_m, Fu_m = _steel(m.steel)
        cope = next((o for o in nd.operations if o.kind in (OP_COPE, OP_CUT) and (o.member == m.name or m.name in (o.targets or []))), None)
        if cope is not None and any(c_.extra > 0 for c_ in ctxs_m) and not (cope.kind == OP_CUT and cope.cut_at == "Fin"):
            mdl.notes.append(f"{m.name}: con la placa simple «hasta el interior de las alas» la viga no se corta; se ignora el corte del extremo.")
            cope = None
        if cope is not None and shp.kind == W_SHAPE and (cope.cope_top > 0 or cope.cope_bot > 0):
            if 0 < cope.cope_top < shp.tf or 0 < cope.cope_bot < shp.tf:
                mdl.notes.append(f"{m.name}: el corte es menos profundo que el espesor del ala ({shp.tf:g} in): el ala no queda eliminada.")
            if cope.kind == OP_CUT and cope.cut_at == "Fin":                  # corte en el extremo libre: se recorta el miembro visto desde su otro extremo
                end_pt = Q + dirv * (ms + Lm)
                prisms = cope_prisms(shp, end_pt, sx, -sy, -dirv, 0.0, Lm, cope.cope_bot, cope.cope_top, cope.cope_len)
            else:
                prisms = cope_prisms(shp, Q + dirv * ms, sx, sy, dirv, 0.0, Lm, cope.cope_top, cope.cope_bot, cope.cope_len)
        else:
            if cope is not None and shp.kind != W_SHAPE:
                mdl.notes.append(f"{m.name}: el corte solo se dibuja en perfiles I.")
            auto = auto_cope_for(nd, m, conn_op) if (conn_op is not None and cope is None) else None
            if auto is not None:
                ct_, cb_, cl_ = auto
                mdl.notes.append(f"{m.name}: corte automático para librar las alas de «{nd.main_name}» (superior {ct_:g} in, inferior {cb_:g} in, largo {cl_:g} in).")
                prisms = cope_prisms(shp, Q + dirv * ms, sx, sy, dirv, 0.0, Lm, ct_, cb_, cl_)
            else:
                prisms = section_prisms(shp, Q + dirv * ms, sx, sy, dirv, 0.0, Lm)
        mdl.parts.append(Part(m.name, "brace" if diag else "beam", f"{m.name} {shp.label}", Fy_m, Fu_m, prisms, t=shp.tw, stub=True))
        mdl.parts[-1].owner = m.name
        if acut is not None:
            for pr_ in mdl.parts[-1].prisms:
                pr_.cut_planes = list(pr_.cut_planes) + [acut]
        for c_ in ctxs_m:
            for p in c_.parts:
                p.owner = m.name
                mdl.parts.append(p)
            mdl.bolts += c_.bolts
            mdl.welds += c_.welds
            mdl.notes += c_.notes
        end = Q + dirv * (ms + Lm)
        mdl.tags.append((tuple(map(float, end)), m.name))
        fem_ends[m.name] = (end, dirv, max(shp.d, shp.bf) / 2.0 + 1.0)
        axes.append((m.name, Q + dirv * ms, end, P0, float(m.pos)))
        free_ends[m.name], frames[m.name] = (Q + dirv * ms, end, dirv), (dirv, sx, sy)
        shapes_by_name[m.name] = shp
        reg[m.name] = {"type": "miembro", "part": m.name, "t": shp.tw, "Fy": Fy_m, "Fu": Fu_m, "faces": member_faces(shp, Q + dirv * ms, end, dirv, sx, sy)}
        ctxs.extend(ctxs_m)
    _build_gussets(ctxs, nd, mdl)
    bop = nd.base_op()
    if bop is not None and prj is not None and hw and fem is None:
        from . import baseplate as BP
        place = BP.end_of_member(nd, bop, free_ends, frames)
        if place is None:
            mdl.notes.append(f"Placa base: el miembro «{bop.member}» no existe o no tiene extremo libre de ese lado.")
        else:
            E, A_in, bsx, bsy = place
            bpd = BP.derive(prj, nd)
            mdl.extra += BP.plate_faces(bpd, E, A_in, bsx, bsy)
            Ob, Fb = BP.plate_transform(bpd, E, A_in, bsx, bsy)
            tpb = float(bpd.plate.tp)
            Bw = float(bpd.plate.Dp if bpd.plate.shape == "Circular" else bpd.plate.B)
            Nw = float(bpd.plate.Dp if bpd.plate.shape == "Circular" else bpd.plate.N)
            Fy_b, Fu_b = _steel(bpd.plate.steel, True)
            reg["Placa base"] = {"type": "placa base", "part": "Placa base", "t": tpb, "Fy": Fy_b, "Fu": Fu_b, "faces": {
                "Cara superior": FaceFrame(Ob + Fb @ np.array([0.0, 0.0, tpb]) - Fb[:, 0] * Bw / 2.0, Fb[:, 0], Fb[:, 2], Bw, Nw / 2.0, tpb),
                "Cara inferior": FaceFrame(Ob - Fb[:, 0] * Bw / 2.0, Fb[:, 0], -Fb[:, 2], Bw, Nw / 2.0, tpb)}}
    for nm_, (s_, e_, d_) in free_ends.items():
        reg[nm_]["ends"] = (s_, e_, d_)
        _d, _sx, _sy = frames[nm_]
        _shp = shapes_by_name[nm_]
        reg[nm_]["frame"] = (s_, _d, _sx, _sy, _shp)
        reg[nm_]["frame_full"] = (s_, e_, _d, _sx, _sy, _shp)
    reg[nd.main_name]["ends"] = (A * (-lneg), A * lpos, A)
    reg[nd.main_name]["frame"] = (np.zeros(3), A, msx, msy, mshape)
    reg[nd.main_name]["frame_full"] = (A * (-lneg), A * lpos, A, msx, msy, mshape)
    mdl.generic = OPS.build_generic(mdl, nd, reg, hw)
    _apply_trims(mdl, nd, reg, hw)
    mdl.elems = reg
    if fem is not None:
        _fem_setup(mdl, nd, fem, fem_ends, lneg, lpos, mshape)
    _node_dims(mdl, A * (-lneg), A * lpos, axes)
    return mdl


def _apply_trims(mdl, nd, reg, hw=True):
    """Recortes de un miembro contra otro elemento: plano de la cara del elemento (con holgura) o plano de inglete entre dos miembros."""
    from .specs import OP_TRIM, TRIM_MODES
    for i, o in enumerate(nd.operations):
        if o.kind != OP_TRIM:
            continue
        tgt = o.targets[0] if o.targets else ""
        mem = reg.get(tgt)
        part = next((p for p in mdl.parts if p.name == (mem or {}).get("part")), None)
        if mem is None or part is None or mem.get("type") != "miembro" or "ends" not in mem:
            mdl.notes.append(f"Operación {i + 1} «{o.kind}»: elija el miembro que se recorta.")
            continue
        s_, e_, d_ = (np.asarray(x, float) for x in mem["ends"])
        P, away = (s_, d_) if o.trim_end == "Inicio" else (e_, -d_)          # punto del extremo y direccion hacia el interior del miembro
        if o.trim_mode == TRIM_MODES[1]:
            oth = reg.get(o.parent)
            if oth is None or "ends" not in oth or oth.get("type") != "miembro" or o.parent == tgt:
                mdl.notes.append(f"Operación {i + 1}: el inglete necesita otro miembro (elemento al que se une).")
                continue
            s2, e2, d2 = (np.asarray(x, float) for x in oth["ends"])
            Q2, away2 = (s2, d2) if np.linalg.norm(s2 - P) <= np.linalg.norm(e2 - P) else (e2, -d2)
            n = away - away2
            if np.linalg.norm(n) < 1e-6:
                mdl.notes.append(f"Operación {i + 1}: los miembros son colineales; no hay inglete.")
                continue
            n = n / np.linalg.norm(n)
            pt, keep = P + away * 0.0, -n                                         # se conserva n·(x − P) ≥ 0  ->  (−n)·(x − P) ≤ 0
        else:
            par = reg.get(o.parent)
            if par is None or o.face not in par["faces"]:
                mdl.notes.append(f"Operación {i + 1}: elija el elemento y la cara contra la que se recorta.")
                continue
            ff = par["faces"][o.face]
            nn = np.asarray(ff.N, float)
            pt, keep = np.asarray(ff.O, float) + nn * float(o.trim_gap), -nn      # el miembro queda del lado exterior de la cara
        keep_n = np.asarray(keep, float)
        for pr in part.prisms:
            # el miembro se alarga por el extremo recortado hasta pasar el plano; luego el plano lo corta y cierra la sección con una tapa
            W = np.asarray(pr.W, float)
            if pr.circle is None and abs(float(W @ d_)) > 0.99:
                end_sign = -1.0 if o.trim_end == "Inicio" else 1.0                 # el extremo recortado está en w0 (inicio) o en w1 (fin)
                w_end = pr.w0 if end_sign < 0 else pr.w1
                rows = [np.asarray(pr.to_global(u, v, w_end), float) for (u, v) in pr.poly]
                den = float(W @ -keep_n) * end_sign                                 # avance del extremo respecto de la normal exterior nn = −keep al alargar
                need = 0.0
                for c_ in rows:
                    sdist = float((c_ - np.asarray(pt, float)) @ -keep_n)               # > 0: la esquina está del lado que se conserva (fuera de la cara)
                    if den < -1e-6 and sdist > 0:
                        need = max(need, sdist / -den)
                need += 0.5 if need > 0 else 0.0
                if end_sign < 0:
                    pr.w0 -= need
                else:
                    pr.w1 += need
            pr.cut_planes = list(pr.cut_planes) + [(tuple(pt), tuple(keep))]
        if o.trim_weld and mem.get("frame_full") is not None:           # soldadura del contorno del miembro contra la cara del recorte
            from types import SimpleNamespace
            other = reg.get(o.parent) or {}
            ffp = SimpleNamespace(N=tuple(-keep_n), O=tuple(pt))
            lines = OPS.member_contour_lines(mem["frame_full"], ffp, None)
            tot = 0.0
            for k, ln in enumerate(lines):
                tot += float(np.linalg.norm(np.asarray(ln[1]) - np.asarray(ln[0])))
                if hw:
                    mdl.welds.append(OPS._mkweld(Weld, f"{tgt}-R{i + 1}.{k + 1}", mem["part"], other.get("part", mem["part"]), ln, o.weld_size, f"R{i + 1}", o.weld_type))
            if not lines:
                mdl.notes.append(f"Operación {i + 1}: no se pudo generar la soldadura del recorte.")
            else:
                ffo = (other.get("faces") or {}).get(o.face) if o.trim_mode != TRIM_MODES[1] else None
                mdl.trim_welds = getattr(mdl, "trim_welds", {})
                mdl.trim_welds[i] = {"L": tot, "t_main": OPS._t_element(mem), "t_to": OPS._t_element(other, ffo) if other else OPS._t_element(mem), "to": o.parent}


def _fem_setup(mdl, nd, fem, ends, lneg, lpos, mshape):
    """Zona refinada del analisis FEM, apoyo del miembro principal y cargas del caso de carga `fem['case']` (analisis nodal)."""
    from . import nodal
    cases = nodal.cases_of(nd)
    pts = [np.asarray(b.p, float) for b in mdl.bolts] + [np.asarray(w.p0, float) for w in mdl.welds] + [np.asarray(w.p1, float) for w in mdl.welds]
    for p in mdl.parts:
        if not p.stub:
            for pr in p.prisms:
                pts += list(pr.corners())
    if pts:
        P = np.asarray(pts)
        lo, hi = P.min(axis=0) - 3.0, P.max(axis=0) + 3.0
        r = max(mshape.d, mshape.bf) / 2.0 + 3.0
        lo, hi = np.minimum(lo, -r), np.maximum(hi, r)
    else:
        lo, hi = np.full(3, -12.0), np.full(3, 12.0)
    mdl.zone = (float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]), float(lo[2]), float(hi[2]))
    i = int(fem.get("case", 0))
    if not cases:
        mdl.notes.append("Sin casos de carga: el análisis FEM necesita cargas (agréguelas en «Cargas»).")
        sups, lds = nodal.fem_conditions(nd, [], ends, lneg, lpos, mshape)
    else:
        sups, lds = nodal.fem_conditions(nd, cases[min(i, len(cases) - 1)][1], ends, lneg, lpos, mshape)
    mdl.supports += sups
    mdl.loads += lds


_PLANES = {"plan": (0, 1), "front": (0, 2), "side": (1, 2)}


def _dim_views(mdl, a, b, value, span, center, k=1.0):
    """Cota entre a y b en las vistas ortograficas (planta, frontal, lateral) donde el tramo se ve de verdad (no de punta); cada cota va en su plano,
    desplazada hacia afuera del conjunto.  `value` = valor real (in) que se rotula."""
    a, b, center = np.asarray(a, float), np.asarray(b, float), np.asarray(center, float)
    v = b - a
    n = float(np.linalg.norm(v))
    if n < 1e-6:
        return
    for view, (i, j) in _PLANES.items():
        pv = np.array([v[i], v[j]])
        pn = float(np.linalg.norm(pv))
        if pn < 0.35 * n or pn < 1.0:
            continue
        t = pv / pn
        o2 = np.array([-t[1], t[0]])
        mid = (a + b) / 2.0
        if float(o2 @ np.array([mid[i] - center[i], mid[j] - center[j]])) < 0:
            o2 = -o2
        off = np.zeros(3)
        off[i], off[j] = o2[0] * span * 0.07 * k, o2[1] * span * 0.07 * k
        mdl.dims.append((tuple(a), tuple(b), tuple(off), float(value), [view]))


def _node_dims(mdl, m0, m1, axes):
    """Cotas del nudo para el visor: largos del miembro principal a cada lado del nudo y largo y posicion de cada miembro conectado."""
    pts = [np.asarray(m0, float), np.asarray(m1, float)] + [np.asarray(q, float) for _n, s_, e_, _p, _pos in axes for q in (s_, e_)]
    P = np.array(pts)
    span = float(np.ptp(P, axis=0).max()) or 1.0
    center = P.mean(axis=0)
    o = np.zeros(3)
    for end in (m0, m1):
        L = float(np.linalg.norm(np.asarray(end, float)))
        if L > 1.0:
            _dim_views(mdl, o, end, L, span, center, 1.3)
    for _name, s_, e_, p0, pos in axes:
        _dim_views(mdl, s_, e_, float(np.linalg.norm(np.asarray(e_, float) - np.asarray(s_, float))), span, center)
        if abs(pos) > 1e-6:
            _dim_views(mdl, o, p0, abs(pos), span, center, 2.2)
