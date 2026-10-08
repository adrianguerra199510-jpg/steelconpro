# -*- coding: utf-8 -*-
"""Constructores del modelo 3D de cada tipologia: `build(prj, vals) -> Model3D` (vals = una combinacion de carga).

Convencion global (in): x desde la cara del soporte hacia la viga, y transversal horizontal, z hacia arriba.
Todas las piezas son union de prismas; los pernos tienen eje paralelo a un eje global.
"""
from __future__ import annotations
import math

import numpy as np

from ... import materials as M
from ...shapes import CATALOG, W_SHAPE
from ..common import bolt_db, hole_std
from ..specs import (CT_SHEAR_TAB, SUP_KINDS, CT_DOUBLE_ANGLE, CT_SEATED, CT_BEAM_SPLICE, CT_COL_SPLICE, CT_ENDPLATE, CT_GUSSET, CT_HSS,
                     CT_RBS, CT_BRIDGE)
from .. import beamend
from .model3d import (Model3D, Part, Bolt, Weld, FaceSel, Contact, Support, LoadApp, Prism, rect_prism, poly_prism, i_section, unit)

BIG = 1.0e4


def _steel(name, plate=False):
    m = M.find(M.PLATE_STEELS if plate else M.SHAPE_STEELS, name, 1 if plate else 0)
    return m.Fy, m.Fu


def _beam_prisms(beam, x0, x1, zc, ct=0.0, cb=0.0, cope_len=0.0, y0=0.0):
    """Viga I a lo largo de +x entre x0 y x1, con eje de la seccion en (y0, zc).  Alma y alas como prismas; cope superior/inferior opcional.
    Devuelve la lista de prismas (alma, ala superior, ala inferior)."""
    d, bf, tf, tw = beam.d, beam.bf, beam.tf, beam.tw
    zt, zb = zc + d / 2.0, zc - d / 2.0
    xc = x0 + max(cope_len, 0.0)
    ct, cb = max(ct, 0.0), max(cb, 0.0)
    pts = [(x0, zb + (cb if cb > 0 else 0.0))]
    if cb > 0:
        pts += [(xc, zb + cb), (xc, zb)]
    pts += [(x1, zb), (x1, zt)]
    if ct > 0:
        pts += [(xc, zt), (xc, zt - ct), (x0, zt - ct)]
    else:
        pts += [(x0, zt)]
    web = Prism(poly=pts, o=(0.0, y0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 0.0, 1.0), w0=-tw / 2.0, w1=tw / 2.0)       # U×V = -y
    out = [web]
    xt0 = xc if ct > 0 else x0
    xb0 = xc if cb > 0 else x0
    out.append(rect_prism(xt0, x1, y0 - bf / 2, y0 + bf / 2, zt - tf, zt))
    out.append(rect_prism(xb0, x1, y0 - bf / 2, y0 + bf / 2, zb, zb + tf))
    return out


def _support(kind, sup, steel, zc, half, beam_zt=None, flush=False):
    """Soporte (columna o viga maestra) con la cara del lado de la viga en x = 0.  Devuelve (Part, espesor local t, [FaceSel extremos])."""
    Fy, Fu = steel
    if sup is None:
        return None, 0.0, []
    if kind == SUP_KINDS[0]:                      # viga maestra: eje a lo largo de y, alma en el plano x = 0
        t = sup.tw
        zg = (beam_zt - sup.d / 2.0) if (flush and beam_zt is not None) else zc
        pr = Prism(poly=[(u, v) for (u, v) in i_section(sup)], o=(-sup.tw / 2.0, 0.0, zg), U=(1.0, 0.0, 0.0), V=(0.0, 0.0, 1.0), w0=-half,
                   w1=half)                       # U×V = -y: simetrico
        ends = [FaceSel("Soporte", (-BIG, BIG, half - 1e-3, half + 1e-3, -BIG, BIG), (0, 1, 0)),
                FaceSel("Soporte", (-BIG, BIG, -half - 1e-3, -half + 1e-3, -BIG, BIG), (0, -1, 0))]
    elif kind == SUP_KINDS[1]:                    # columna, la viga llega al alma: alas paralelas al plano x-z? (alma en el plano x = 0)
        t = sup.tw
        pr = Prism(poly=[(u, v) for (u, v) in i_section(sup)], o=(-sup.tw / 2.0, 0.0, zc), U=(1.0, 0.0, 0.0), V=(0.0, 1.0, 0.0), w0=-half, w1=half)
        ends = [FaceSel("Soporte", (-BIG, BIG, -BIG, BIG, zc + half - 1e-3, zc + half + 1e-3), (0, 0, 1)),
                FaceSel("Soporte", (-BIG, BIG, -BIG, BIG, zc - half - 1e-3, zc - half + 1e-3), (0, 0, -1))]
    else:                                         # columna, la viga llega al ala
        t = sup.tf
        pr = Prism(poly=[(u, v) for (u, v) in i_section(sup)], o=(-sup.d / 2.0, 0.0, zc), U=(0.0, 1.0, 0.0), V=(-1.0, 0.0, 0.0), w0=-half, w1=half)
        ends = [FaceSel("Soporte", (-BIG, BIG, -BIG, BIG, zc + half - 1e-3, zc + half + 1e-3), (0, 0, 1)),
                FaceSel("Soporte", (-BIG, BIG, -BIG, BIG, zc - half - 1e-3, zc - half + 1e-3), (0, 0, -1))]
    kindn = "support"
    return Part("Soporte", kindn, f"Soporte {sup.label}", Fy, Fu, [pr], stub=True, t=t), t, ends


def _bolt_row(tag, x, zs, y_head, y_nut, db, grip_plies, grade, planes=1):
    """Pernos en una fila vertical con el eje a lo largo de -y (de la cabeza, en y_head, a la tuerca, en y_nut)."""
    out = []
    dh = hole_std(db)
    for i, z in enumerate(zs):
        grip = []
        s = 0.0
        for (pn, thick) in grip_plies:
            grip.append((pn, s, s + thick))
            s += thick
        out.append(Bolt(f"{tag}{i + 1}", (x, y_head, z), (0.0, -1.0, 0.0), db, dh, 0.9 * db, grip, 0.0, s, grade, planes))
    return out


# =================================================================================================== placa simple de corte
def build_shear_tab(prj, vals) -> Model3D:
    st = prj.stab
    Vu = vals[0]
    beam, sup = CATALOG.get(st.beam), CATALOG.get(st.sup_label)
    g = beamend.geometry(beam, max(int(st.n), 1), st.s, st.a, st.gap, st.y_top, st.cope_top, st.cope_bot, st.cope_len)
    db = bolt_db(st.bolt_size)
    n = max(int(st.n), 1)
    ztop = beam.d / 2.0                              # el eje de la viga queda en z = 0
    zbolt0 = ztop - g["y_top"]
    zs = [zbolt0 - i * st.s for i in range(n)]
    Lb = (n - 1) * st.s
    x_end = st.a + st.leh_p + max(1.5 * beam.d, 12.0)
    bFy, bFu = _steel(st.beam_steel)
    pFy, pFu = _steel(st.plate_steel, True)
    mdl = Model3D("Placa simple de corte")
    # viga apoyada
    mdl.parts.append(Part("Viga", "beam", f"Viga {st.beam}", bFy, bFu,
                          _beam_prisms(beam, st.gap, x_end, 0.0, st.cope_top, st.cope_bot, st.cope_len), stub=True, t=beam.tw))
    # soporte
    half = max(2.0 * beam.d, 18.0) if st.sup_kind == SUP_KINDS[0] else max(1.5 * beam.d + 6.0, 20.0)
    sp, tsup, ends = _support(st.sup_kind, sup, _steel(st.sup_steel), 0.0, half, ztop, st.top_flush)
    if sp is not None:
        mdl.parts.append(sp)
    # placa
    ty = beam.tw / 2.0
    zp0, zp1 = zs[-1] - st.lev_p, zs[0] + st.lev_p
    mdl.parts.append(Part("Placa", "plate", f"Placa {st.tp:g} in", pFy, pFu, [rect_prism(0.0, st.a + st.leh_p, ty, ty + st.tp, zp0, zp1)], t=st.tp))
    # pernos (cabeza en la cara exterior de la placa, tuerca del lado opuesto del alma)
    mdl.bolts += _bolt_row("P", st.a, zs, ty + st.tp, -ty, db, [("Placa", st.tp), ("Viga", beam.tw)], st.bolt_grade, 1)
    # soldadura de filete a ambos lados de la placa, sobre la cara del soporte (x = 0)
    mdl.welds.append(Weld("Cordon exterior", "Placa", "Soporte", (0.0, ty + st.tp, zp0 + 0.02), (0.0, ty + st.tp, zp1 - 0.02), (0, 1, 0), (1, 0, 0),
                          st.weld_size, 70.0, "placa-soporte"))
    mdl.welds.append(Weld("Cordon interior", "Placa", "Soporte", (0.0, ty, zp0 + 0.02), (0.0, ty, zp1 - 0.02), (0, -1, 0), (1, 0, 0),
                          st.weld_size, 70.0, "placa-soporte"))
    # contactos: placa contra el alma de la viga y canto de la placa contra el soporte
    mdl.contacts.append(Contact("Placa-alma", FaceSel("Viga", (st.gap, x_end, ty - 1e-3, ty + 1e-3, zp0, zp1), (0, -1, 0)),
                                FaceSel("Placa", (st.gap, x_end, ty - 1e-3, ty + 1e-3, zp0, zp1), (0, -1, 0))))
    mdl.contacts.append(Contact("Placa-soporte", FaceSel("Placa", (-1e-3, 1e-3, -BIG, BIG, zp0, zp1), (-1, 0, 0)),
                                FaceSel("Soporte", (-1e-3, 1e-3, ty - 0.5, ty + st.tp + 0.5, zp0 - 0.5, zp1 + 0.5), (1, 0, 0))))
    # apoyos y carga (la fuerza actua en la cara del soporte: x = 0)
    for k, e in enumerate(ends):
        mdl.supports.append(Support(f"Extremo {k + 1}", e))
    mdl.loads.append(LoadApp("Reaccion de la viga", FaceSel("Viga", (x_end - 1e-3, x_end + 1e-3, -BIG, BIG, -BIG, BIG), (1, 0, 0)),
                             (0.0, 0.0, 0.0), (0.0, 0.0, -Vu), (0.0, 0.0, 0.0), show=(x_end, 0.0, 0.0)))
    mdl.zone = (-2.0, st.a + st.leh_p + 4.0, -beam.bf / 2 - 1.0, beam.bf / 2 + 1.0, zp0 - 2.0, zp1 + 2.0)
    return mdl


# =================================================================================================== doble angulo
def build_double_angle(prj, vals) -> Model3D:
    from .. import double_angle as DA
    st = prj.dang
    Vu = vals[0]
    g = DA.geometry(st)
    beam, sup, ang = g["beam"], g["sup"], g["ang"]
    db, n = g["db"], g["n"]
    ztop = beam.d / 2.0
    zs = [ztop - g["y_top"] - i * st.s for i in range(n)]
    x_end = st.gw + g["lw"] + max(1.5 * beam.d, 12.0)
    bFy, bFu = _steel(st.beam_steel)
    aFy, aFu = _steel(st.angle_steel, True)
    mdl = Model3D("Doble angulo")
    mdl.parts.append(Part("Viga", "beam", f"Viga {st.beam}", bFy, bFu, _beam_prisms(beam, st.gap, x_end, 0.0, st.cope_top, st.cope_bot, st.cope_len),
                          stub=True, t=beam.tw))
    half = max(2.0 * beam.d, 18.0) if st.sup_kind == SUP_KINDS[0] else max(1.5 * beam.d + 6.0, 20.0)
    sp, tsup, ends = _support(st.sup_kind, sup, _steel(st.sup_steel), 0.0, half, ztop, st.top_flush)
    mdl.parts.append(sp)
    t, lw, ls = g["t"], g["lw"], g["ls"]
    z1 = ztop - (g["y_top"] - g["lev_a"])
    z0 = z1 - st.L_ang
    tw = beam.tw
    for k, sg in enumerate((1, -1)):
        pts = [(0.0, sg * tw / 2), (lw, sg * tw / 2), (lw, sg * (tw / 2 + t)), (t, sg * (tw / 2 + t)), (t, sg * (tw / 2 + ls)), (0.0, sg * (tw / 2 + ls))]
        pr = Prism(poly=pts, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 1.0, 0.0), w0=z0, w1=z1)
        mdl.parts.append(Part(f"Angulo {k + 1}", "angle", f"Angulo {st.angle} ({'+' if sg > 0 else '-'}y)", aFy, aFu, [pr], t=t))
    # pernos del alma: doble corte
    mdl.bolts += _bolt_row("A", st.gw, zs, tw / 2 + t, -(tw / 2 + t), db, [("Angulo 1", t), ("Viga", tw), ("Angulo 2", t)], st.bolt_grade, 2)
    if not g["welded"]:                                       # pernos de la pierna del soporte
        for k, sg in enumerate((1, -1)):
            for i, z in enumerate(zs):
                mdl.bolts.append(Bolt(f"S{k + 1}{i + 1}", (t, sg * (tw / 2 + st.gs), z), (-1.0, 0.0, 0.0), db, g["dh"], 0.9 * db,
                                      [(f"Angulo {k + 1}", 0.0, t), ("Soporte", t, t + tsup)], 0.0, t + tsup, st.bolt_grade, 1))
    else:
        zlo, zhi = z0 + 0.02, z1 - 0.02
        for k, sg in enumerate((1, -1)):
            mdl.welds.append(Weld(f"Angulo {k + 1} exterior", f"Angulo {k + 1}", "Soporte", (0.0, sg * (tw / 2 + ls), zlo), (0.0, sg * (tw / 2 + ls), zhi),
                                  (0, sg, 0), (1, 0, 0), st.weld_size, 70.0, "angulos-soporte"))
            if st.weld_lines == 2 and st.gap >= st.weld_size + 0.05:
                mdl.welds.append(Weld(f"Angulo {k + 1} interior", f"Angulo {k + 1}", "Soporte", (0.0, sg * tw / 2, zlo), (0.0, sg * tw / 2, zhi),
                                      (0, -sg, 0), (1, 0, 0), st.weld_size, 70.0, "angulos-soporte"))
    for k, e in enumerate(ends):
        mdl.supports.append(Support(f"Extremo {k + 1}", e))
    mdl.loads.append(LoadApp("Reaccion de la viga", FaceSel("Viga", (x_end - 1e-3, x_end + 1e-3, -BIG, BIG, -BIG, BIG), (1, 0, 0)), (0.0, 0.0, 0.0),
                             (0.0, 0.0, -Vu), (0.0, 0.0, 0.0), show=(x_end, 0.0, 0.0)))
    mdl.zone = (-2.0, st.gw + lw + 4.0, -beam.bf / 2 - 1.0, beam.bf / 2 + 1.0, z0 - 2.0, z1 + 2.0)
    return mdl


# =================================================================================================== asiento
def build_seated(prj, vals) -> Model3D:
    from .. import seated as SE
    st = prj.seat
    R = vals[0]
    g = SE.geometry(st)
    beam, sup, ang = g["beam"], g["sup"], g["ang"]
    db = g["db"]
    zb = -beam.d / 2.0                                       # cara inferior de la viga = tope del asiento
    x_end = st.setback + st.N + max(1.5 * beam.d, 12.0)
    bFy, bFu = _steel(st.beam_steel)
    aFy, aFu = _steel(st.angle_steel, True)
    mdl = Model3D("Asiento")
    mdl.parts.append(Part("Viga", "beam", f"Viga {st.beam}", bFy, bFu, _beam_prisms(beam, st.setback, x_end, 0.0), stub=True, t=beam.tw))
    half = max(1.5 * beam.d + 8.0, 20.0)
    sp, tsup, ends = _support(st.sup_kind, sup, _steel(st.sup_steel), 0.0, half, beam.d / 2.0, False)
    mdl.parts.append(sp)
    W = st.L_seat
    if not g["stiffened"]:
        t, lh, lv = g["t"], g["lh"], g["lv"]
        pts = [(0.0, zb), (lh, zb), (lh, zb - t), (t, zb - t), (t, zb - lv), (0.0, zb - lv)]
        pr = Prism(poly=pts, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 0.0, 1.0), w0=-W / 2, w1=W / 2)          # U×V = -y
        mdl.parts.append(Part("Asiento", "angle", f"Angulo de asiento {st.angle}", aFy, aFu, [pr], t=t))
        zlo, zhi = zb - lv, zb
        if not g["welded"]:
            zs = [zb - lv + st.yb + i * st.s for i in range(g["n"])]
            for k, yy in enumerate((-st.gs / 2, st.gs / 2)):
                for i, z in enumerate(zs):
                    mdl.bolts.append(Bolt(f"S{k + 1}{i + 1}", (t, yy, z), (-1.0, 0.0, 0.0), db, g["dh"], 0.9 * db,
                                          [("Asiento", 0.0, t), ("Soporte", t, t + tsup)], 0.0, t + tsup, st.bolt_grade, 1))
        else:
            for k, sg in enumerate((1, -1)):
                mdl.welds.append(Weld(f"Lado {k + 1}", "Asiento", "Soporte", (0.0, sg * W / 2, zlo + 0.02), (0.0, sg * W / 2, zhi - 0.02), (0, sg, 0), (1, 0, 0),
                                      st.weld_size, 70.0, "asiento-soporte"))
            mdl.welds.append(Weld("Superior", "Asiento", "Soporte", (0.0, -W / 2 + 0.02, zb), (0.0, W / 2 - 0.02, zb), (0, 0, 1), (1, 0, 0), st.weld_size, 70.0,
                                  "asiento-soporte"))
        zone_z = (zb - lv - 2.0, zb + 6.0)
    else:
        tt = st.st_t
        plate = rect_prism(0.0, st.st_W, -W / 2, W / 2, zb - tt, zb)
        mdl.parts.append(Part("Placa de asiento", "plate", "Placa de asiento", *_steel(st.st_steel, True), [plate], t=tt))
        tri = Prism(poly=[(0.0, zb - tt), (st.st_W, zb - tt), (0.0, zb - tt - st.st_H)], o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 0.0, 1.0),
                    w0=-tt / 2, w1=tt / 2)
        mdl.parts.append(Part("Rigidizador", "stiff", "Rigidizador triangular", *_steel(st.st_steel, True), [tri], t=tt))
        mdl.bonded.append(("Rigidizador", "Placa de asiento"))
        zlo, zhi = zb - tt - st.st_H + 0.02, zb - tt - 0.02
        for k, sg in enumerate((1, -1)):
            mdl.welds.append(Weld(f"Lado {k + 1}", "Rigidizador", "Soporte", (0.0, sg * tt / 2, zlo), (0.0, sg * tt / 2, zhi), (0, sg, 0), (1, 0, 0), st.st_weld,
                                  70.0, "rigidizador-soporte"))
        zone_z = (zb - tt - st.st_H - 2.0, zb + 6.0)
    for k, e in enumerate(ends):
        mdl.supports.append(Support(f"Extremo {k + 1}", e))
    xr = g["eR"]
    mdl.loads.append(LoadApp("Reaccion de la viga", FaceSel("Viga", (x_end - 1e-3, x_end + 1e-3, -BIG, BIG, -BIG, BIG), (1, 0, 0)), (xr, 0.0, 0.0),
                             (0.0, 0.0, -R), (0.0, 0.0, 0.0), fix_ref=(1, 2), fix_rot=(3,),
                             show=(x_end, 0.0, 0.0)))               # la viga solo apoya (sin friccion): se fijan el deslizamiento y el giro en planta
    mdl.zone = (-2.0, st.setback + st.N + 4.0, -max(W, beam.bf) / 2 - 1.0, max(W, beam.bf) / 2 + 1.0, zone_z[0], zone_z[1])
    return mdl


BUILDERS = {CT_SHEAR_TAB: build_shear_tab, CT_DOUBLE_ANGLE: build_double_angle, CT_SEATED: build_seated}



def build_model(prj, vals=None) -> Model3D:
    """Modelo 3D de la conexion de `prj` para una combinacion (`vals` = fuerzas de la tabla de cargas; por defecto la primera)."""
    from .. import module_for
    mod = module_for(prj.ctype)
    if vals is None:
        vals = getattr(prj, mod.ATTR).loads()[0][1]
    from .builders2 import BUILDERS2
    fn = BUILDERS.get(prj.ctype) or BUILDERS2.get(prj.ctype)
    if fn is None:
        raise KeyError(f"Sin modelo 3D para la tipologia {prj.ctype}")
    return fn(prj, tuple(vals))
