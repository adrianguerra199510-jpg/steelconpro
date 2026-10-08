# -*- coding: utf-8 -*-
"""Constructores 3D: empalmes, placa extrema, cartela, nudos HSS, RBS y empalme de puente (ver builders.py)."""
from __future__ import annotations
import math

import numpy as np

from ...shapes import CATALOG
from ..common import bolt_db, hole_std
from ..specs import (CT_BEAM_SPLICE, CT_COL_SPLICE, CT_ENDPLATE, CT_GUSSET, CT_HSS, CT_RBS, CT_BRIDGE, SUP_KINDS, EP_FLANGE_WELD, GUS_CONN, HSS_SHAPES,
                     HSS_TYPES)
from .model3d import (Model3D, Part, Bolt, Weld, FaceSel, Support, LoadApp, Prism, rect_prism, poly_prism, i_section, unit, rect_tube)
from .builders import _steel, _beam_prisms, _support, BIG


def _face(part, x=None, y=None, z=None, nrm=(1, 0, 0), pad=1e-3):
    """Cara plana de una pieza en x, y o z = cte (caja ancha)."""
    b = [-BIG, BIG, -BIG, BIG, -BIG, BIG]
    for k, v in enumerate((x, y, z)):
        if v is not None:
            b[2 * k], b[2 * k + 1] = v - pad, v + pad
    return FaceSel(part, tuple(b), nrm)


# =================================================================================================== empalmes de viga y de columna
def build_splice(prj, vals, is_col: bool) -> Model3D:
    from .. import splice_core as C
    sp = prj.csp if is_col else prj.bsp
    if is_col:
        P, Mu, Vu = vals
        Fx = -P                                   # compresion: empuja hacia el otro tramo
    else:
        Mu, Vu, Nu = vals
        Fx = Nu                                   # + traccion
    g = C.geometry(sp)
    sh = g["sh"]
    d, tf, tw, bf = sh.d, sh.tf, sh.tw, sh.bf
    half = sp.gap / 2.0
    Lp2 = g["Lplate"] / 2.0
    Ls = Lp2 + max(1.5 * d, 12.0)
    mFy, mFu = _steel(sp.steel)
    pFy, pFu = _steel(sp.plate_steel, True)
    db, dbw = g["db"], g["dbw"]
    mdl = Model3D("Empalme de columna" if is_col else "Empalme de viga")
    mdl.parts.append(Part("Perfil izq.", "column" if is_col else "beam", f"{sp.shape} (izq.)", mFy, mFu, _beam_prisms(sh, -Ls, -half, 0.0), stub=True, t=tw))
    mdl.parts.append(Part("Perfil der.", "column" if is_col else "beam", f"{sp.shape} (der.)", mFy, mFu, _beam_prisms(sh, half, Ls, 0.0), stub=True, t=tw))
    zt, zb = d / 2.0, -d / 2.0
    # ---- placas de ala (exterior arriba/abajo) e interiores (a cada lado del alma)
    for nm, zc0, sgn in (("sup.", zt, 1), ("inf.", zb, -1)):
        z0, z1 = (zc0, zc0 + sp.fo_t) if sgn > 0 else (zc0 - sp.fo_t, zc0)
        mdl.parts.append(Part(f"Placa ext. {nm}", "plate", f"Placa de ala exterior {nm}", pFy, pFu, [rect_prism(-Lp2, Lp2, -sp.fo_b / 2, sp.fo_b / 2, z0, z1)],
                              t=sp.fo_t))
        if g["has_inner"]:
            ycen = (tw / 2 + bf / 2) / 2.0
            zi0, zi1 = (zc0 - tf - sp.fi_t, zc0 - tf) if sgn > 0 else (zc0 + tf, zc0 + tf + sp.fi_t)
            for k, sy in enumerate((1, -1)):
                mdl.parts.append(Part(f"Placa int. {nm} {k + 1}", "plate", f"Placa de ala interior {nm} ({'+' if sy > 0 else '-'}y)", pFy, pFu,
                                      [rect_prism(-Lp2, Lp2, sy * ycen - sp.fi_b / 2, sy * ycen + sp.fi_b / 2, zi0, zi1)], t=sp.fi_t))
    # ---- pernos de las alas
    cols = [(c - (sp.f_cols - 1) / 2.0) * sp.f_g for c in range(sp.f_cols)]
    for nm, zc0, sgn in (("sup.", zt, 1), ("inf.", zb, -1)):
        for side, sx in (("izq.", -1), ("der.", 1)):
            for r in range(sp.f_rows):
                x = sx * (half + sp.f_end + r * sp.f_s)
                for ic, y in enumerate(cols):
                    grip = [(f"Placa ext. {nm}", sp.fo_t), (f"Perfil {side}", tf)]
                    planes = 1
                    if g["has_inner"]:
                        ycen = (tw / 2 + bf / 2) / 2.0
                        inner_k = 1 if y > 0 else 2
                        if abs(abs(y) - ycen) <= sp.fi_b / 2:
                            grip.append((f"Placa int. {nm} {inner_k}", sp.fi_t))
                            planes = 2
                    zh = zc0 + sgn * sp.fo_t                           # cara exterior de la placa: aqui apoya la cabeza
                    tot = sum(t_ for _n, t_ in grip)
                    s0, gl = 0.0, []
                    for pn, t_ in grip:
                        gl.append((pn, s0, s0 + t_))
                        s0 += t_
                    mdl.bolts.append(Bolt(f"F{nm[:3]}{side[:3]}{r + 1}{ic + 1}", (x, y, zh), (0.0, 0.0, -float(sgn)), db, g["dh"], 0.9 * db, gl, 0.0, tot,
                                          sp.bolt_grade, planes))
    # ---- placas de alma (dos) y sus pernos
    wx = half + sp.w_end + (sp.w_nh - 1) * sp.w_sh + sp.w_pend
    for k, sy in enumerate((1, -1)):
        y0, y1 = (tw / 2, tw / 2 + sp.w_t) if sy > 0 else (-tw / 2 - sp.w_t, -tw / 2)
        mdl.parts.append(Part(f"Placa alma {k + 1}", "plate", f"Placa de alma ({'+' if sy > 0 else '-'}y)", pFy, pFu,
                              [rect_prism(-wx, wx, y0, y1, -sp.w_h / 2, sp.w_h / 2)], t=sp.w_t))
    for side, sx in (("izq.", -1), ("der.", 1)):
        for c in range(sp.w_nh):
            x = sx * (half + sp.w_end + c * sp.w_sh)
            for r in range(sp.w_nv):
                z = (r - (sp.w_nv - 1) / 2.0) * sp.w_sv
                grip = [("Placa alma 1", 0.0, sp.w_t), (f"Perfil {side}", sp.w_t, sp.w_t + tw), ("Placa alma 2", sp.w_t + tw, 2 * sp.w_t + tw)]
                mdl.bolts.append(Bolt(f"W{side[:3]}{c + 1}{r + 1}", (x, tw / 2 + sp.w_t, z), (0.0, -1.0, 0.0), dbw, g["dhw"], 0.9 * dbw, grip, 0.0,
                                      2 * sp.w_t + tw, sp.bolt_grade, 2))
    mdl.supports.append(Support("Extremo izq.", _face("Perfil izq.", x=-Ls, nrm=(-1, 0, 0)), (1, 3)))
    mdl.supports[-1].dofs = (1, 3)
    mdl.supports[-1] = Support("Extremo izq.", _face("Perfil izq.", x=-Ls, nrm=(-1, 0, 0)))
    mdl.loads.append(LoadApp("Esfuerzos del empalme", _face("Perfil der.", x=Ls, nrm=(1, 0, 0)), (0.0, 0.0, 0.0), (Fx, 0.0, -Vu), (0.0, Mu, 0.0), show=(Ls, 0.0, 0.0)))
    mdl.zone = (-Lp2 - 3.0, Lp2 + 3.0, -bf / 2 - 1.0, bf / 2 + 1.0, zb - sp.fo_t - 1.0, zt + sp.fo_t + 1.0)
    return mdl


# =================================================================================================== placa extrema a momento
def build_endplate(prj, vals) -> Model3D:
    from .. import endplate as EP
    st = prj.epl
    Mu, Vu = vals
    g = EP.geometry(st)
    beam, col = g["beam"], g["col"]
    d, tf, bf, tw, tp = beam.d, beam.tf, beam.bf, beam.tw, st.tp
    db = g["db"]
    yt = d / 2 + (st.pfo + st.e_ext if st.ext_t else 0.0)
    yb = -(d / 2 + (st.pfo + st.e_ext if st.ext_c else 0.0))
    bFy, bFu = _steel(st.beam_steel)
    pFy, pFu = _steel(st.plate_steel, True)
    x_end = tp + max(1.5 * d, 12.0)
    mdl = Model3D("Placa extrema a momento")
    mdl.parts.append(Part("Viga", "beam", f"Viga {st.beam}", bFy, bFu, _beam_prisms(beam, tp, x_end, 0.0), stub=True, t=tw))
    half = max(0.5 * (yt - yb) + d, 20.0)
    sp, tsup, ends = _support(SUP_KINDS[2], col, _steel(st.col_steel), 0.0, half, d / 2.0, False)
    mdl.parts.append(sp)
    mdl.parts.append(Part("Placa extrema", "plate", f"Placa extrema {st.bp:g}×{tp:g}", pFy, pFu, [rect_prism(0.0, tp, -st.bp / 2, st.bp / 2, yb, yt)], t=tp))
    mdl.bonded.append(("Viga", "Placa extrema"))              # soldadura viga-placa: union continua (equivale a CJP)
    if g["fillet"]:
        mdl.notes.append("La soldadura de filete viga-placa se modela como union continua (equivale a penetracion completa): el cordon no se verifica en el 3D.")
    if st.cont_plates:
        for zc0 in (d / 2 - tf / 2, -d / 2 + tf / 2):
            for k, sy in enumerate((1, -1)):
                y0, y1 = (col.tw / 2, col.bf / 2) if sy > 0 else (-col.bf / 2, -col.tw / 2)
                mdl.parts.append(Part(f"Continuidad {'sup' if zc0 > 0 else 'inf'} {k + 1}", "stiff", "Placa de continuidad", pFy, pFu,
                                      [rect_prism(-col.d + col.tf, -col.tf, y0, y1, zc0 - tf / 2, zc0 + tf / 2)], t=tf))
                mdl.bonded.append((f"Continuidad {'sup' if zc0 > 0 else 'inf'} {k + 1}", "Soporte"))
    # pernos: horizontales, de la cabeza (cara de la placa del lado de la viga) a la tuerca (cara posterior del ala de la columna)
    rows = []
    for sgn, ext in ((1, st.ext_t), (-1, st.ext_c)):
        rows.append(sgn * (d / 2 - tf - st.pfi))
        if ext:
            rows.append(sgn * (d / 2 + st.pfo))
    for i, z in enumerate(rows):
        for j, y in enumerate((-st.g / 2, st.g / 2)):
            mdl.bolts.append(Bolt(f"B{i + 1}{j + 1}", (tp, y, z), (-1.0, 0.0, 0.0), db, g["dh"], 0.9 * db,
                                  [("Placa extrema", 0.0, tp), ("Soporte", tp, tp + col.tf)], 0.0, tp + col.tf, st.bolt_grade, 1))
    for k, e in enumerate(ends):
        mdl.supports.append(Support(f"Extremo {k + 1}", e))
    mdl.loads.append(LoadApp("Esfuerzos de la viga", _face("Viga", x=x_end, nrm=(1, 0, 0)), (0.0, 0.0, 0.0), (0.0, 0.0, -Vu), (0.0, Mu, 0.0), show=(x_end, 0.0, 0.0)))
    mdl.zone = (-col.d - 1.0, tp + 6.0, -max(st.bp, col.bf) / 2 - 1.0, max(st.bp, col.bf) / 2 + 1.0, yb - 3.0, yt + 3.0)
    return mdl


# =================================================================================================== cartela de arriostramiento
def _clip_poly(poly, nx, nz, c):
    """Recorta un poligono (x, z) al semiplano nx·x + nz·z >= c (Sutherland-Hodgman)."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        fa, fb = nx * a[0] + nz * a[1] - c, nx * b[0] + nz * b[1] - c
        if fa >= 0:
            out.append(a)
        if (fa >= 0) != (fb >= 0):
            tt = fa / (fa - fb)
            out.append((a[0] + tt * (b[0] - a[0]), a[1] + tt * (b[1] - a[1])))
    return out


def _dist_in_poly(poly, px, pz) -> float:
    """Distancia del punto al borde del poligono si esta dentro; negativa si esta fuera."""
    n = len(poly)
    inside = False
    dmin = 1e18
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > pz) != (b[1] > pz) and px < (b[0] - a[0]) * (pz - a[1]) / (b[1] - a[1] + 1e-300) + a[0]:
            inside = not inside
        abx, abz = b[0] - a[0], b[1] - a[1]
        L2 = abx * abx + abz * abz
        tt = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, ((px - a[0]) * abx + (pz - a[1]) * abz) / L2))
        dmin = min(dmin, math.hypot(px - (a[0] + tt * abx), pz - (a[1] + tt * abz)))
    return dmin if inside else -dmin


def build_gusset(prj, vals) -> Model3D:
    from .. import gusset as GU
    st = prj.gus
    P0 = vals[0]                                              # + traccion
    g = GU.geometry(st)
    beam, col = g["beam"], g["col"]
    th = g["th"]
    t = st.t
    ec, eb, Lc = g["ec"], g["eb"], g["Lc"]
    u = np.array([math.sin(th), 0.0, -math.cos(th)])          # eje del arriostramiento, desde el nudo hacia afuera
    v = np.array([math.cos(th), 0.0, math.sin(th)])
    WP = np.array([-ec, 0.0, eb])
    bolted = g["bolted"]
    if bolted:
        nlines, bg = st.n_lines, (st.n_lines - 1) * st.g_t
        s_first = st.D1
        s_last = st.D1 + (st.n_rows - 1) * st.s
        s_end = s_last + st.lg_end
        wbr = bg + 2 * max(st.Le, 1.25)
        planes = st.m_planes
    else:
        bg = st.g_t
        s_first = st.D1
        s_end = st.D1 + st.Lw + 0.5
        wbr = bg + 2 * 1.0
        planes = 2 if st.nlw == 4 else 1
    # ---- cartela: casco convexo del triangulo L_b x L_c y del borde libre, recortado a x >= 0 y z <= 0
    F = WP + u * s_end
    hw = 0.5 * wbr + 0.5
    P3, P4 = F + v * hw, F - v * hw
    pts = [(0.0, 0.0), (st.L_b, 0.0), (P3[0], P3[2]), (P4[0], P4[2]), (0.0, -Lc)]
    from scipy.spatial import ConvexHull
    arr = np.array(pts)
    hull = arr[ConvexHull(arr).vertices]
    poly = [tuple(q) for q in hull]
    poly = _clip_poly(poly, 0.0, -1.0, 0.0)                   # z <= 0
    poly = _clip_poly(poly, 1.0, 0.0, 0.0)                    # x >= 0
    gFy, gFu = _steel(st.steel, True)
    bFy, bFu = _steel(st.beam_steel)
    cFy, cFu = _steel(st.col_steel)
    mdl = Model3D("Cartela de arriostramiento")
    gus = Prism(poly=poly, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 0.0, 1.0), w0=-t / 2, w1=t / 2)            # U×V = -y
    mdl.parts.append(Part("Cartela", "gusset", f"Cartela {t:g} in", gFy, gFu, [gus], t=t))
    x_end = max(st.L_b, P3[0]) + max(1.5 * beam.d, 18.0)
    mdl.parts.append(Part("Viga", "beam", f"Viga {st.beam}", bFy, bFu, _beam_prisms(beam, 0.0, x_end, eb), stub=True, t=beam.tw))
    half = max(0.5 * (Lc + beam.d) + 18.0, 30.0)
    zcol = 0.5 * (eb * 2 - Lc)
    sp, tsup, ends = _support(SUP_KINDS[2], col, (cFy, cFu), zcol, half, None, False)
    mdl.parts.append(sp)
    mdl.bonded.append(("Viga", "Soporte"))                    # la viga se une a la columna sin detallar (la conexion viga-columna no es objeto del analisis)
    # ---- soldaduras cartela-viga y cartela-columna (a ambos lados)
    for k, sy in enumerate((1, -1)):
        mdl.welds.append(Weld(f"Cartela-viga {k + 1}", "Cartela", "Viga", (0.02, sy * t / 2, 0.0), (st.L_b - 0.02, sy * t / 2, 0.0), (0, sy, 0), (0, 0, -1), st.w_gb, 70.0,
                              "cartela-viga"))
        mdl.welds.append(Weld(f"Cartela-columna {k + 1}", "Cartela", "Soporte", (0.0, sy * t / 2, -Lc + 0.02), (0.0, sy * t / 2, -0.02), (0, sy, 0), (1, 0, 0), st.w_gc,
                              70.0, "cartela-columna"))
    # ---- arriostramiento: placas a cada lado (o una) de espesor t_br / planos
    tb = st.t_br / max(planes, 1)
    s_ini = s_first - st.Le
    s_far = s_end + max(2.0 * wbr, 10.0)
    brace_names = []
    ys = [(t / 2, t / 2 + tb), (-t / 2 - tb, -t / 2)] if planes == 2 else [(t / 2, t / 2 + tb)]
    for k, (y0, y1) in enumerate(ys):
        poly_b = [(s_ini, -wbr / 2), (s_far, -wbr / 2), (s_far, wbr / 2), (s_ini, wbr / 2)]
        # las placas no pueden entrar en la viga (z > 0) ni en la columna (x < 0)
        poly_b = _clip_poly(poly_b, math.cos(th), -math.sin(th), 0.1 + eb)
        poly_b = _clip_poly(poly_b, math.sin(th), math.cos(th), 0.1 + ec)
        if len(poly_b) < 3:
            continue
        pr = Prism(poly=poly_b, o=tuple(WP), U=tuple(u), V=tuple(v), w0=-y1, w1=-y0)                # u×v = -y
        nm = f"Arriostramiento {k + 1}"
        mdl.parts.append(Part(nm, "brace", f"Placa del arriostramiento {k + 1}", 50.0, st.Fu_br, [pr], t=tb))
        brace_names.append(nm)
    skipped = 0
    if bolted:
        db = g["db"]
        for r in range(st.n_rows):
            for c in range(nlines):
                a = s_first + r * st.s
                b = (c - (nlines - 1) / 2.0) * st.g_t
                pos = WP + u * a + v * b
                if _dist_in_poly(poly, pos[0], pos[2]) < db / 2 + 0.3 or _dist_in_poly(poly_b, a, b) < db / 2 + 0.3:
                    skipped += 1
                    continue
                # eje de los pernos: -y desde la cara exterior de la primera placa (+y) hasta la ultima
                tot = planes * tb + t
                if planes == 2:
                    grip = [(brace_names[0], 0.0, tb), ("Cartela", tb, tb + t), (brace_names[1], tb + t, 2 * tb + t)]
                else:
                    grip = [(brace_names[0], 0.0, tb), ("Cartela", tb, tb + t)]
                mdl.bolts.append(Bolt(f"B{r + 1}{c + 1}", (pos[0], t / 2 + tb, pos[2]), (0.0, -1.0, 0.0), db, g["dh"], 0.9 * db, grip, 0.0, tot, st.bolt_grade, planes))
        if skipped:
            mdl.notes.append(f"{skipped} perno(s) del arriostramiento caen fuera de la cartela o de las placas y no se modelan en el 3D: revise D1 y L_b.")
    else:
        # filetes entre los bordes de las placas y la cartela: lineas de largo Lw a lo largo del eje
        for k, nm in enumerate(brace_names):
            sy = 1 if k == 0 else -1
            for e, sb in enumerate((-1, 1)):
                b = sb * bg / 2
                p0 = WP + u * s_first + v * b
                p1 = WP + u * (s_first + st.Lw) + v * b
                # superficie A: cara lateral de la placa (normal sb·v, hacia afuera) ; B: cara de la cartela (normal sy·y)
                mdl.welds.append(Weld(f"Arriostr. {k + 1}.{e + 1}", nm, "Cartela", tuple(p0 + np.array([0, sy * (t / 2), 0])), tuple(p1 + np.array([0, sy * (t / 2), 0])),
                                      tuple(sb * v), (0, sy, 0), st.w_br, 70.0, "arriostramiento"))
    for k, e in enumerate(ends):
        mdl.supports.append(Support(f"Extremo columna {k + 1}", e))
    mdl.supports.append(Support("Extremo viga", _face("Viga", x=x_end, nrm=(1, 0, 0))))
    Fv = P0 * u                                               # + traccion: tira del nudo hacia afuera
    sels = [FaceSel(nm, (WP[0] + s_far * u[0] - wbr, WP[0] + s_far * u[0] + wbr, -BIG, BIG, WP[2] + s_far * u[2] - wbr, WP[2] + s_far * u[2] + wbr), tuple(u))
            for nm in brace_names]
    ref = WP + u * s_far
    mdl.loads.append(LoadApp("Fuerza del arriostramiento", sels, tuple(ref), tuple(Fv), (0.0, 0.0, 0.0)))
    xm = max(P3[0], st.L_b) + 4.0
    mdl.zone = (-col.d - 1.0, xm, -max(wbr, beam.bf) / 2 - 1.0 - tb, max(wbr, beam.bf) / 2 + 1.0 + tb, min(P4[2], -Lc) - 3.0, beam.d * 1.0 + 2.0)
    return mdl


# =================================================================================================== nudos HSS a HSS
def build_hss(prj, vals) -> Model3D:
    from .. import hss_joint as HS
    from .model3d import cyl_prism
    st = prj.hss
    P1, P2 = vals                                             # compresion +
    g = HS.geometry(st)
    ch = g["ch"]
    rnd = g["rnd"]
    D = g["D"]
    two = HS._two(st)
    kj = HS._kj(st)
    mFy, mFu = _steel(st.chord_steel)
    brs = [(g["b1"], st.theta1, st.br1_steel, P1)] + ([(g["b2"], st.theta2, st.br2_steel, P2)] if two else [])
    th1 = math.radians(st.theta1)
    # direccion de cada diagonal (desde el nudo hacia afuera, en el plano x-z)
    dirs = []
    if st.jt == HSS_TYPES[1]:                                  # X: dos diagonales opuestas
        dirs = [np.array([math.cos(th1), 0.0, math.sin(th1)]), np.array([-math.cos(th1), 0.0, -math.sin(th1)])]
        nodes = [np.zeros(3), np.zeros(3)]
    elif kj:                                                    # K / N con separacion: las dos diagonales del mismo lado
        th2 = math.radians(st.theta2)
        Db1 = HS._bdim(brs[0][0], rnd)[0]
        Db2 = HS._bdim(brs[1][0], rnd)[0]
        a = 0.5 * (st.gap + Db1 / (2 * math.sin(th1)) + Db2 / (2 * math.sin(th2)))
        dirs = [np.array([math.cos(th1), 0.0, math.sin(th1)]), np.array([-math.cos(th2), 0.0, math.sin(th2)])]
        nodes = [np.array([a, 0.0, 0.0]), np.array([-a, 0.0, 0.0])]
    else:
        dirs = [np.array([math.cos(th1), 0.0, math.sin(th1)])]
        nodes = [np.zeros(3)]
    Dmax = max([D] + [HS._bdim(b[0], rnd)[0] for b in brs])
    xs = [n[0] for n in nodes]
    Lc = max(3.0 * Dmax, 24.0) + max(abs(x) for x in xs)
    mdl = Model3D("Nudo HSS a HSS")
    if rnd:
        chord_p = cyl_prism((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), ch.d / 2, 2 * Lc, ri=ch.d / 2 - ch.tw)
        chord_solid = cyl_prism((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), ch.d / 2, 2 * Lc)
    else:
        outer, inner = _rect(ch)
        chord_p = Prism(poly=outer, holes=[inner], o=(0.0, 0.0, 0.0), U=(0.0, 1.0, 0.0), V=(0.0, 0.0, 1.0), w0=-Lc, w1=Lc)
        chord_solid = Prism(poly=outer, o=(0.0, 0.0, 0.0), U=(0.0, 1.0, 0.0), V=(0.0, 0.0, 1.0), w0=-Lc, w1=Lc)
    mdl.parts.append(Part("Cordon", "hss", f"Cordon {st.chord}", mFy, mFu, [chord_p], stub=True, t=ch.tw))
    toes = 0.0
    for k, ((sh, th, steel, Pk), dvec, nd) in enumerate(zip(brs, dirs, nodes)):
        Fy, Fu = _steel(steel)
        Db, Hb, tb = HS._bdim(sh, rnd)
        Lb = max(3.0 * Hb, 14.0)
        if rnd:
            bp = cyl_prism(nd + dvec * Lb / 2.0, dvec, sh.d / 2, Lb, ri=sh.d / 2 - sh.tw)
        else:
            ob, ib = _rect(sh)
            U = np.array([0.0, 1.0, 0.0])
            V = np.cross(dvec, U)
            bp = Prism(poly=ob, holes=[ib], o=tuple(nd), U=tuple(U), V=tuple(V), w0=0.0, w1=Lb)
        part = Part(f"Diagonal {k + 1}", "brace", f"Diagonal {k + 1} {sh.label}", Fy, Fu, [bp], stub=True, t=tb, cuts=[chord_solid])
        mdl.parts.append(part)
        mdl.bonded.append((f"Diagonal {k + 1}", "Cordon"))
        end = nd + dvec * Lb
        sel = FaceSel(f"Diagonal {k + 1}", (end[0] - Hb, end[0] + Hb, -BIG, BIG, end[2] - Hb, end[2] + Hb), tuple(dvec))
        mdl.loads.append(LoadApp(f"Diagonal {k + 1}", sel, tuple(end), tuple(-Pk * dvec), (0.0, 0.0, 0.0)))
    mdl.notes.append("Las diagonales se unen al cordon con union continua (equivale a penetracion completa); la soldadura de filete no se verifica en el 3D.")
    # cordon: extremo izquierdo con la fuerza axial y fijo en y, z; extremo derecho empotrado
    mdl.loads.append(LoadApp("Axial del cordon", _face("Cordon", x=-Lc, nrm=(-1, 0, 0)), (-Lc, 0.0, 0.0), (st.chord_P, 0.0, 0.0), (0.0, 0.0, 0.0), (2, 3), (1, 2, 3)))
    mdl.supports.append(Support("Extremo del cordon", _face("Cordon", x=Lc, nrm=(1, 0, 0))))
    zmax = max(Hb * 1.2, 0.5 * D + 4.0) + max(3.0 * Dmax * 0.5, 8.0)
    mdl.zone = (min(xs) - 1.2 * Dmax - 2.0, max(xs) + 1.2 * Dmax + 2.0, -Dmax, Dmax, -(0.5 * D + 3.0) if st.jt != HSS_TYPES[1] else -zmax, zmax)
    return mdl


def _rect(sh):
    """(exterior, interior) de un HSS rectangular: ancho B a lo largo de u (fuera del plano) y alto H a lo largo de v."""
    return rect_tube(sh)


# =================================================================================================== RBS
def build_rbs(prj, vals) -> Model3D:
    from .. import rbs as RB
    st = prj.rbs
    Vg, Puc = vals
    g = RB.geometry(st)
    beam, col = g["beam"], g["col"]
    bm, cm = g["bm"], g["cm"]
    d, bf, tf, tw = beam.d, beam.bf, beam.tf, beam.tw
    Mpr, sh, Lh = g["Mpr"], g["sh"], g["Lh"]
    Vrbs = 2 * Mpr / Lh                                       # cortante que forma la rotula en el centro de la RBS (el de gravedad queda del lado de la seguridad en el cerrado)
    x_inf = sh + Lh / 2.0                                     # punto de inflexion (a mitad de la luz libre) medido desde la cara de la columna
    x_e = min(x_inf, sh + max(3.0 * d, 36.0))
    Me = Vrbs * (x_inf - x_e)                                 # momento que sustituye al tramo de viga que se recorta
    mdl = Model3D("Conexion RBS")
    # ---- viga con ala reducida: alma (rectangulo) y alas en planta con el recorte circular
    R_ = g["R"]
    xm = st.a + st.b / 2.0
    N = 14
    arc = []
    for i in range(N + 1):
        x = st.a + st.b * i / N
        yy = (bf / 2 - st.c + R_) - math.sqrt(max(R_ * R_ - (x - xm) ** 2, 0.0))
        arc.append((x, yy))
    top = [(0.0, bf / 2), (st.a, bf / 2)] + arc[1:-1] + [(st.a + st.b, bf / 2), (x_e, bf / 2)]
    bot = [(x, -y) for (x, y) in reversed(top)]
    flange_poly = top + bot
    web = _beam_prisms(beam, 0.0, x_e, d / 2.0)[0]
    zt, zb = d, 0.0
    fl_top = Prism(poly=flange_poly, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 1.0, 0.0), w0=zt - tf, w1=zt)
    fl_bot = Prism(poly=flange_poly, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 1.0, 0.0), w0=zb, w1=zb + tf)
    Ryb = g["Ryb"]
    hard = (Ryb * bm.Fy, 1.03 * g["Cpr"] * Ryb * bm.Fy, 0.04)          # endurecimiento: Mpr se alcanza con ~2 % de deformacion en la fibra extrema
    bFy, bFu = bm.Fy, bm.Fu
    mdl.parts.append(Part("Viga", "beam", f"Viga RBS {st.beam}", bFy, bFu, [web, fl_top, fl_bot], stub=True, t=tw, hard=hard, no_peeq=True))
    half = max(d + 30.0, 36.0)
    cz = d / 2.0
    cFy, cFu = bm.Fy, bm.Fu
    cm_ = cm
    sp, tsup, ends = _support(SUP_KINDS[2], col, (cm_.Fy, cm_.Fu), cz, half, None, False)
    sp.hard = (cm_.Fy, cm_.Fy * 1.0005, 0.25)                 # diseno por capacidad (AISC 341): la columna se verifica con Fy sin φ
    mdl.parts.append(sp)
    mdl.bonded.append(("Viga", "Soporte"))
    if st.cont_plates:
        for zc0 in (d - tf / 2, tf / 2):
            for k, sy in enumerate((1, -1)):
                y0, y1 = (col.tw / 2, col.bf / 2) if sy > 0 else (-col.bf / 2, -col.tw / 2)
                nm = f"Continuidad {'sup' if zc0 > d / 2 else 'inf'} {k + 1}"
                mdl.parts.append(Part(nm, "stiff", "Placa de continuidad", cm_.Fy, cm_.Fu, [rect_prism(-col.d + col.tf, -col.tf, y0, y1, zc0 - tf / 2, zc0 + tf / 2)],
                                      t=tf, hard=(cm_.Fy, cm_.Fy * 1.0005, 0.25)))
                mdl.bonded.append((nm, "Soporte"))
    mdl.loads.append(LoadApp("Cortante de la RBS", _face("Viga", x=x_e, nrm=(1, 0, 0)), (x_e, 0.0, cz), (0.0, 0.0, -Vrbs), (0.0, Me, 0.0), show=(x_e, 0.0, cz)))
    if st.n_beams == 2:
        # segunda viga al otro lado de la columna (cara x = -d_col), en sentido contrario: el panel recibe los momentos de las dos vigas
        sx = -col.d
        flp2 = [(sx - x, y) for (x, y) in flange_poly]
        web2 = Prism(poly=[(sx - x, z) for (x, z) in web.poly], o=web.o, U=web.U, V=web.V, w0=web.w0, w1=web.w1)
        fl2t = Prism(poly=flp2, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 1.0, 0.0), w0=zt - tf, w1=zt)
        fl2b = Prism(poly=flp2, o=(0.0, 0.0, 0.0), U=(1.0, 0.0, 0.0), V=(0.0, 1.0, 0.0), w0=zb, w1=zb + tf)
        mdl.parts.append(Part("Viga 2", "beam", f"Viga RBS 2 {st.beam}", bFy, bFu, [web2, fl2t, fl2b], stub=True, t=tw, hard=hard, no_peeq=True))
        mdl.bonded.append(("Viga 2", "Soporte"))
        mdl.loads.append(LoadApp("Cortante de la RBS 2", _face("Viga 2", x=sx - x_e, nrm=(-1, 0, 0)), (sx - x_e, 0.0, cz), (0.0, 0.0, Vrbs), (0.0, Me, 0.0)))
    # columna: arriba carga axial (compresion), abajo empotrada; si no hay columna superior, el tope queda libre
    mdl.supports.append(Support("Pie de la columna", ends[1]))
    if st.two_cols:
        mdl.loads.append(LoadApp("Axial de la columna", _face("Soporte", z=cz + half, nrm=(0, 0, 1)), (-col.d / 2, 0.0, cz + half), (0.0, 0.0, -Puc), (0.0, 0.0, 0.0),
                                 (1, 2), (1, 2, 3)))
    mdl.zone = (-col.d - 2.0, st.a + st.b + 6.0, -bf / 2 - 1.0, bf / 2 + 1.0, -6.0, d + 6.0)
    if st.n_beams == 2:
        mdl.zone = (-col.d - st.a - st.b - 6.0, st.a + st.b + 6.0, mdl.zone[2], mdl.zone[3], mdl.zone[4], mdl.zone[5])
    return mdl


# =================================================================================================== empalme de puente (ala con pernos pretensados)
def build_bridge(prj, vals) -> Model3D:
    from .. import bridge_splice as BS
    st = prj.brs
    Fs, Fv = vals
    g = BS.geometry(st)
    db = g["db"]
    fFy, fFu = _steel(st.fl_steel, True)
    pFy, pFu = _steel(st.sp_steel, True)
    half = 0.25
    Lp2 = half + st.e_end + (st.n_rows - 1) * st.s + st.e_pend
    Ls = Lp2 + max(2.0 * st.fl_b, 14.0)
    mdl = Model3D("Empalme de puente")
    mdl.parts.append(Part("Ala izq.", "beam", "Ala (izq.)", fFy, fFu, [rect_prism(-Ls, -half, -st.fl_b / 2, st.fl_b / 2, 0.0, st.fl_t)], stub=True, t=st.fl_t))
    mdl.parts.append(Part("Ala der.", "beam", "Ala (der.)", fFy, fFu, [rect_prism(half, Ls, -st.fl_b / 2, st.fl_b / 2, 0.0, st.fl_t)], stub=True, t=st.fl_t))
    mdl.parts.append(Part("Placa exterior", "plate", "Placa exterior", pFy, pFu, [rect_prism(-Lp2, Lp2, -st.po_b / 2, st.po_b / 2, st.fl_t, st.fl_t + st.po_t)], t=st.po_t))
    inner = g["has_inner"]
    if inner:
        gapw = 0.25
        for k, sy in enumerate((1, -1)):
            y0, y1 = (gapw, gapw + st.pi_b) if sy > 0 else (-gapw - st.pi_b, -gapw)
            mdl.parts.append(Part(f"Placa interior {k + 1}", "plate", f"Placa interior ({'+' if sy > 0 else '-'}y)", pFy, pFu,
                                  [rect_prism(-Lp2, Lp2, y0, y1, -st.pi_t, 0.0)], t=st.pi_t))
    cols = [(c - (st.n_cols - 1) / 2.0) * st.g for c in range(st.n_cols)]
    for side, sx in (("izq.", -1), ("der.", 1)):
        for r in range(st.n_rows):
            x = sx * (half + st.e_end + r * st.s)
            for ic, y in enumerate(cols):
                grip = [("Placa exterior", 0.0, st.po_t), (f"Ala {side}", st.po_t, st.po_t + st.fl_t)]
                tot = st.po_t + st.fl_t
                planes = 1
                if inner:
                    k = 1 if y > 0 else 2
                    grip.append((f"Placa interior {k}", tot, tot + st.pi_t))
                    tot += st.pi_t
                    planes = 2
                mdl.bolts.append(Bolt(f"B{side[:3]}{r + 1}{ic + 1}", (x, y, st.fl_t + st.po_t), (0.0, 0.0, -1.0), db, g["dh"], 0.9 * db, grip, 0.0, tot,
                                      st.bolt_grade, planes))
    mdl.supports.append(Support("Extremo izq.", _face("Ala izq.", x=-Ls, nrm=(-1, 0, 0))))
    mdl.loads.append(LoadApp("Fuerza del ala", _face("Ala der.", x=Ls, nrm=(1, 0, 0)), (Ls, 0.0, st.fl_t / 2), (Fs, 0.0, 0.0), (0.0, 0.0, 0.0), show=(Ls, 0.0, st.fl_t / 2)))
    mdl.notes.append("Pernos pretensados de deslizamiento critico: el 3D los trata como pernos de aplastamiento sin pretension; el deslizamiento se verifica en el calculo cerrado (AASHTO 6.13.2.8).")
    mdl.zone = (-Lp2 - 3.0, Lp2 + 3.0, -st.fl_b / 2 - 1.0, st.fl_b / 2 + 1.0, -st.pi_t - 1.0, st.fl_t + st.po_t + 1.0)
    return mdl


BUILDERS2 = {CT_HSS: build_hss, CT_RBS: build_rbs, CT_BRIDGE: build_bridge, CT_GUSSET: build_gusset, CT_BEAM_SPLICE: lambda prj, vals: build_splice(prj, vals, False), CT_COL_SPLICE: lambda prj, vals: build_splice(prj, vals, True),
             CT_ENDPLATE: build_endplate}
