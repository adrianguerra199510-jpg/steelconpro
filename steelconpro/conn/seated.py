# -*- coding: utf-8 -*-
"""Conexion de asiento (seated): la viga descansa sobre un angulo de asiento sin rigidizar o sobre una placa de asiento
con rigidizador; el angulo superior solo da estabilidad lateral y no se calcula.

La reaccion R actua a e = retranqueo + N/2 de la cara del soporte (apoyo uniforme de la viga en la longitud N).
Verificaciones (AISC 360-22, LRFD):
  viga: fluencia local del alma J10.2 (extremo) y aplastamiento del alma J10.3 (extremo);
  asiento sin rigidizar: flexion plastica de la pierna horizontal en el pie del filete (seccion a k del respaldo),
    cortante, traccion de la pierna vertical (fluencia y rotura en la fila de pernos),
    pernos al soporte con cortante R/nb y traccion por el momento R·e con el eje neutro en el borde inferior
    (J3.7, conservador) o soldadura en C (top + dos lados) con cortante y momento fuera del plano;
  asiento rigidizado: la placa rigidizadora como mensula (M = R·e, V = R, interaccion plastica) y su soldadura
    de dos lineas verticales al soporte (excentricidad e).
NO se evalua: la placa horizontal del asiento rigidizado, el angulo superior, la union del ala inferior de la viga,
el pandeo del rigidizador (aviso por esbeltez) ni la reaccion de los pernos del asiento por prying.
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from ..units import float_to_frac
from .base import run_combos, add_check
from .common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, PHI_FLEX, FNV, E_STEEL, bolt_db, hole_std, hole_net, edge_min,
                     bolt_shear_rn, bolt_tension_shear, bearing_rn, web_local_yielding, web_crippling,
                     weld_segments_oop, weld_lines_vertical)
from .formspec import G, N, num, intf, combo, check
from .specs import CT_SEATED, SUP_KINDS, BOLT_GRADES, SHEAR_BOLT_SIZES, SEAT_TYPES, SEAT_ATTACH

NAME = CT_SEATED


def geometry(st):
    beam = CATALOG.get(st.beam)
    sup = CATALOG.get(st.sup_label)
    ang = CATALOG.get(st.angle)
    db = bolt_db(st.bolt_size)
    g = dict(beam=beam, sup=sup, ang=ang, db=db, dh=hole_std(db), dhn=hole_net(db), n=max(int(st.n), 1),
             stiffened=st.seat_type == SEAT_TYPES[1], welded=st.attach == SEAT_ATTACH[1])
    g["eR"] = st.setback + st.N / 2.0                            # de la cara del soporte a la reaccion
    if ang is not None:
        long_, short = max(ang.d, ang.bf), min(ang.d, ang.bf)
        g["lh"] = long_ if st.long_horizontal else short         # pierna horizontal (recibe la viga)
        g["lv"] = short if st.long_horizontal else long_         # pierna vertical (contra el soporte)
        g["t"] = ang.tw
        g["k"] = ang.kdes if ang.kdes > 0 else ang.tw + 0.375
    return g


def _t_support(st, sup):
    if sup is None:
        return 0.0
    return sup.tf if st.sup_kind == SUP_KINDS[2] else sup.tw


def check_input(st) -> list:
    g = geometry(st)
    w = []
    beam, sup, ang = g["beam"], g["sup"], g["ang"]
    if beam is None or beam.kind != "W":
        return [f"** La viga '{st.beam}' debe ser un perfil I del catalogo. **"]
    if sup is None:
        w.append(f"** Perfil del soporte '{st.sup_label}' no encontrado en el catalogo. **")
    if st.bolt_grade not in FNV:
        w.append(f"** Calidad de perno '{st.bolt_grade}' no reconocida. **")
    if st.N <= 0 or st.L_seat <= 0:
        w.append("** La longitud de apoyo N y el ancho del asiento deben ser positivos. **")
    if beam.bf > st.L_seat + 1e-9:
        w.append(f"Ancho del asiento ({st.L_seat:g} in) menor que el ancho del ala de la viga ({beam.bf:g} in).")
    if not g["stiffened"]:
        if ang is None or ang.kind != "L":
            return w + [f"** Angulo de asiento '{st.angle}' no encontrado en el catalogo (use un perfil L). **"]
        if st.N > g["lh"] - st.setback + 1e-9:
            w.append(f"** La longitud de apoyo N ({st.N:g} in) no cabe en la pierna horizontal "
                     f"({g['lh']:g} in − retranqueo {st.setback:g} in). **")
        if st.setback < g["t"] + 0.25 - 1e-9:
            w.append(f"Retranqueo menor que t + 1/4 in ({g['t'] + 0.25:.3f} in): la viga puede chocar con la pierna vertical.")
        if not g["welded"]:
            if st.bolt_size not in SHEAR_BOLT_SIZES or not (1 <= st.n <= 8):
                w.append("** Pernos del soporte: diametro no valido o numero de filas fuera de 1 a 8. **")
            if st.yb + (g["n"] - 1) * st.s + edge_min(g["db"]) > g["lv"] + 1e-9:
                w.append("** Los pernos no caben en la pierna vertical (altura insuficiente). **")
            if st.gs + 2 * edge_min(g["db"]) > st.L_seat + 1e-9:
                w.append("** Las dos columnas de pernos no caben en el ancho del asiento. **")
        w.append("Angulo superior, union del ala inferior y pernos del asiento por prying: no se verifican.")
    else:
        if st.N > st.st_W - st.setback + 1e-9:
            w.append(f"** La longitud de apoyo N ({st.N:g} in) no cabe en el rigidizador (W = {st.st_W:g} in − retranqueo). **")
        if st.st_W / max(st.st_t, 1e-9) > 0.56 * math.sqrt(E_STEEL / M.find(M.PLATE_STEELS, st.st_steel, 1).Fy) + 1e-9:
            w.append("W/t del rigidizador mayor que 0.56·√(E/Fy): riesgo de pandeo local del borde libre (no se verifica).")
        w.append("La placa horizontal del asiento, el angulo superior y la union del ala inferior no se verifican.")
    return w


def solve_one(prj, name, vals, rec):
    R = vals[0]
    st = prj.seat
    g = geometry(st)
    ck = []
    beam, sup = g["beam"], g["sup"]
    if beam is None or sup is None or beam.kind != "W":
        return ck
    u = prj.units()
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    sp = M.find(M.SHAPE_STEELS, st.sup_steel)
    FEXX = M.find(M.ELECTRODES, st.electrode, 1).FEXX
    N_, eR = st.N, g["eR"]
    tw, tf, d, kk = beam.tw, beam.tf, beam.d, beam.kdes if beam.kdes > 0 else beam.tf + 0.5
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Viga", st.beam, f"{st.beam_steel}: Fy = {rec.f('S', bm.Fy)}, Fu = {rec.f('S', bm.Fu)}; d = {rec.f('L', d)}, tw = {rec.f('L', tw)}, "
                f"tf = {rec.f('L', tf)}, k = {rec.f('L', kk)}", None)
        rec.add("Soporte", f"{st.sup_label} — {st.sup_kind}", st.sup_steel, None)
        rec.add("Asiento", st.seat_type, f"ancho {rec.f('L', st.L_seat)}, retranqueo {rec.f('L', st.setback)}, apoyo N = {rec.f('L', N_)}", None)
        rec.add("R", "reaccion factorizada", "", R, "F")
        rec.add("e", "retranqueo + N/2", f"{rec.n('L', st.setback)} + {rec.n('L', N_)}/2", eR, "L", note="de la cara del soporte a la reaccion")

    # ----------------------------------------------------------------- alma de la viga (J10)
    Rwy = PHI_YIELD * web_local_yielding(bm.Fy, tw, kk, N_, True)
    Rwc = 0.75 * web_crippling(bm.Fy, tw, tf, d, N_, True)
    if rec:
        rec.section("ALMA DE LA VIGA SOBRE EL ASIENTO")
        rec.add("φRn,fluencia", "1.00·Fyw·tw·(2.5k + N)", f"{rec.n('S', bm.Fy)}·{rec.n('L', tw)}·(2.5·{rec.n('L', kk)} + {rec.n('L', N_)})", Rwy, "F", "AISC J10.2")
        rec.add("φRn,aplastamiento", "0.75·J10-5 (extremo)", f"N/d = {N_ / d:.3f}", Rwc, "F", "AISC J10.3")
    add_check(ck, rec, "web_yield", "Alma de la viga — fluencia local en el apoyo", R, Rwy, "kip", "AISC J10.2", f"N = {u.q('L', N_)}")
    add_check(ck, rec, "web_crip", "Alma de la viga — aplastamiento (crippling) en el apoyo", R, Rwc, "kip", "AISC J10.3", f"N/d = {N_ / d:.3f}")

    if not g["stiffened"]:
        ang = g["ang"]
        am = M.find(M.SHAPE_STEELS, st.angle_steel)
        t, kA, Ls = g["t"], g["k"], st.L_seat
        # ---- flexion de la pierna horizontal
        arm = max(0.0, eR - kA)
        Mu = R * arm
        phiMp = PHI_FLEX * am.Fy * Ls * t ** 2 / 4.0
        if rec:
            rec.section("ANGULO DE ASIENTO")
            rec.add("Mu", "R·(e − k)", f"{rec.n('F', R)}·({rec.n('L', eR)} − {rec.n('L', kA)})", Mu, "M", "Manual Parte 10", note="seccion critica en el pie del filete (a k del respaldo)")
            rec.add("φMp", "0.90·Fy·L·t²/4", f"0.9·{rec.n('S', am.Fy)}·{rec.n('L', Ls)}·{rec.n('L', t)}²/4", phiMp, "M", "AISC F11")
        add_check(ck, rec, "seat_flex", "Angulo de asiento — flexion de la pierna horizontal", Mu, phiMp, "kip·in", "AISC F11 / Manual Parte 10", f"e − k = {u.q('L', arm)}")
        add_check(ck, rec, "seat_shear", "Angulo de asiento — cortante de la pierna horizontal", R, PHI_YIELD * 0.6 * am.Fy * Ls * t, "kip", "AISC J4.2(a)")
        # ---- pierna vertical: traccion entre la esquina y los pernos
        nbc = 2 if not g["welded"] else 0
        An = t * (Ls - nbc * g["dhn"])
        add_check(ck, rec, "leg_tens_y", "Angulo — fluencia por traccion de la pierna vertical", R, 0.9 * am.Fy * t * Ls, "kip", "AISC D2(a)")
        if nbc:
            add_check(ck, rec, "leg_tens_r", "Angulo — rotura por traccion de la pierna vertical (fila de pernos)", R, 0.75 * am.Fu * An, "kip", "AISC D2(b)")
        if not g["welded"]:
            db, n, s = g["db"], g["n"], st.s
            nb = 2 * n
            ys = [st.yb + i * s for i in range(n)]                 # alturas de las filas sobre el fondo del asiento
            M_ = R * eR
            Sy2 = sum(2 * y * y for y in ys)
            Tmax = M_ * max(ys) / Sy2 if Sy2 > 0 else 0.0           # traccion del perno superior (eje neutro en el borde inferior)
            frv = (R / nb) / (math.pi * db ** 2 / 4)
            Ta = bolt_tension_shear(db, st.bolt_grade, frv)
            rn1 = bolt_shear_rn(db, st.bolt_grade)
            if rec:
                rec.section("PERNOS AL SOPORTE (pierna vertical)")
                rec.add("M", "R·e", f"{rec.n('F', R)}·{rec.n('L', eR)}", M_, "M", note="el eje neutro se supone en el borde inferior del asiento (conservador)")
                rec.add("T,max", "M·y,max / Σ(2·y²)", "", Tmax, "F")
                rec.add("frv", "(R/nb)/Ab", "", frv, "S")
                rec.add("φ·F'nt·Ab", "φ·(1.3·Fnt − Fnt/(φ·Fnv)·frv)·Ab ≤ φ·Fnt·Ab", "", Ta, "F", "AISC J3.7")
            add_check(ck, rec, "bolt_v", "Pernos al soporte — cortante", R / nb, PHI_BOLT * rn1, "kip", "AISC J3.6", f"{nb} pernos Ø{st.bolt_size}")
            add_check(ck, rec, "bolt_t", "Pernos al soporte — traccion con cortante", Tmax, Ta, "kip", "AISC J3.7", "T por el momento R·e; sin efecto palanca")
            ts = _t_support(st, sup)
            wv = max((R / nb) / max(PHI_BOLT * bearing_rn(db, tt, Fu_, (s - g["dh"])), 1e-9)
                     for tt, Fu_ in ((t, am.Fu), (ts, sp.Fu)))
            add_check(ck, rec, "brg_bolts", "Pernos — aplastamiento en el angulo y en el soporte", R / nb, R / nb / wv if wv > 0 else 0.0, "kip", "AISC J3.10")
        else:
            lv = g["lv"]
            segs = [(-Ls / 2, lv, Ls / 2, lv), (-Ls / 2, 0.0, -Ls / 2, lv), (Ls / 2, 0.0, Ls / 2, lv)]
            wr = weld_segments_oop(segs, R, R * eR, st.weld_size, FEXX, st.weld_dir)
            if rec:
                rec.section("SOLDADURA DEL ANGULO AL SOPORTE (C: borde superior y dos lados)")
                rec.add("Lw", "longitud de la soldadura", "", wr["L"], "L")
                rec.add("f,max", "resultante en el punto critico", f"θ = {wr['theta']:.0f}°", wr["f"], "LF")
            add_check(ck, rec, "weld", "Soldadura del angulo al soporte — cortante y momento fuera del plano", wr["f"], wr["cap"], "kip/in", "AISC J2.4",
                      f"w = {float_to_frac(st.weld_size)}\", {st.electrode}; θ = {wr['theta']:.0f}°; metodo elastico")
            ts = _t_support(st, sup)
            add_check(ck, rec, "weld_base_s", "Metal base del soporte (bajo el cordon)", wr["f"], PHI_RUPT * 0.6 * sp.Fu * ts, "kip/in", "AISC J4.2")
            add_check(ck, rec, "weld_base_a", "Metal base del angulo (bajo el cordon)", wr["f"], PHI_RUPT * 0.6 * am.Fu * t, "kip/in", "AISC J4.2")
            add_check(ck, rec, "weld_min", "Tamano minimo del filete", M.min_fillet(min(t, ts) if ts > 0 else t), st.weld_size, "in", "AISC Tabla J2.4")
    else:
        pm = M.find(M.PLATE_STEELS, st.st_steel, 1)
        t, Hs = st.st_t, st.st_H
        Mu = R * eR
        Z = t * Hs ** 2 / 4.0
        phiMp = PHI_FLEX * pm.Fy * Z
        phiVp = PHI_YIELD * 0.6 * pm.Fy * t * Hs
        if rec:
            rec.section("RIGIDIZADOR (placa vertical como mensula)")
            rec.add("Mu", "R·e", f"{rec.n('F', R)}·{rec.n('L', eR)}", Mu, "M")
            rec.add("φMp", "0.90·Fy·t·H²/4", "", phiMp, "M", "AISC F11")
        add_check(ck, rec, "st_flex", "Rigidizador — flexion en la cara del soporte", Mu, phiMp, "kip·in", "AISC F11")
        add_check(ck, rec, "st_shear", "Rigidizador — fluencia por cortante", R, phiVp, "kip", "AISC J4.2(a)")
        add_check(ck, rec, "st_vm", "Rigidizador — interaccion flexion-cortante (plastica)", Mu / max(phiMp, 1e-9) + (R / max(phiVp, 1e-9)) ** 2, 1.0, "-",
                  "Criterio del programa", "M/φMp + (R/φVp)² ≤ 1: forma conservadora")
        f, cap, th, fv, fh = weld_lines_vertical(R, eR, Hs, st.st_weld, FEXX, 2, st.weld_dir)
        add_check(ck, rec, "weld", "Soldadura del rigidizador al soporte — dos lineas verticales", f, cap, "kip/in", "AISC J2.4",
                  f"w = {float_to_frac(st.st_weld)}\", {st.electrode}; θ = {th:.0f}°; metodo elastico, e = {u.q('L', eR)}")
        ts = _t_support(st, sup)
        add_check(ck, rec, "weld_base_s", "Metal base del soporte (bajo el cordon)", 2 * f, PHI_RUPT * 0.6 * sp.Fu * ts, "kip/in", "AISC J4.2",
                  "ambos cordones sobre la misma pared del soporte")
        add_check(ck, rec, "weld_min", "Tamano minimo del filete", M.min_fillet(min(t, ts) if ts > 0 else t), st.st_weld, "in", "AISC Tabla J2.4")
        add_check(ck, rec, "weld_max", "Tamano maximo del filete en el canto del rigidizador", st.st_weld, M.max_fillet(t), "in", "AISC J2.2b")
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.seat, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "seat"
TAB = "Asiento"
PREFIX = "AS"
TITLE = "CONEXION DE ASIENTO (SEATED)"
NORMS = "AISC 360-22 (cap. D, F, J) · AISC Steel Construction Manual 15a Ed., Parte 10"
LOADS = [("R", "F")]
LOADS_NOTE = "Cada fila es una combinacion con la reaccion vertical R de la viga (ya factorizada)."

_unst = lambda p: p.seat.seat_type == SEAT_TYPES[0]
_stf = lambda p: p.seat.seat_type == SEAT_TYPES[1]
_bolted = lambda p: _unst(p) and p.seat.attach == SEAT_ATTACH[0]
_welded = lambda p: _unst(p) and p.seat.attach == SEAT_ATTACH[1]
FORM = [
    G("Viga apoyada"),
    combo("Perfil", "seat.beam", "@I", editable=True),
    combo("Acero", "seat.beam_steel", "@steel_shape"),
    G("Soporte"),
    combo("Tipo de soporte", "seat.sup_kind", SUP_KINDS),
    combo("Perfil del soporte", "seat.sup_label", "@I", editable=True),
    combo("Acero del soporte", "seat.sup_steel", "@steel_shape"),
    G("Asiento"),
    combo("Tipo de asiento", "seat.seat_type", SEAT_TYPES),
    num("Ancho del asiento", "seat.L_seat", 2, 40, uk="L", help="Longitud del asiento a lo largo del soporte. Debe cubrir el ancho del ala de la viga."),
    num("Retranqueo (del soporte al extremo de la viga)", "seat.setback", 0, 4, uk="L", help="Se mide desde la cara del soporte. Usual 3/4 in."),
    num("Longitud de apoyo N", "seat.N", 0.5, 20, uk="L", help="Longitud de la viga que apoya sobre el asiento (se supone presion uniforme); la reaccion actua a retranqueo + N/2."),
    G("Angulo de asiento", show=_unst),
    combo("Angulo", "seat.angle", "@L", editable=True, show=_unst),
    combo("Acero del angulo", "seat.angle_steel", "@steel_shape", show=_unst),
    check("Pierna larga horizontal", "seat.long_horizontal", help="La pierna horizontal recibe a la viga; la vertical va contra el soporte.", show=_unst),
    combo("Union al soporte", "seat.attach", SEAT_ATTACH, show=_unst),
    G("Pernos al soporte (dos columnas por fila)", show=_bolted),
    combo("Diametro", "seat.bolt_size", SHEAR_BOLT_SIZES, show=_bolted),
    combo("Calidad", "seat.bolt_grade", BOLT_GRADES, show=_bolted),
    intf("Filas de pernos", "seat.n", 1, 8, show=_bolted),
    num("Separacion vertical  s", "seat.s", 0.5, 12, uk="L", show=_bolted),
    num("Del fondo del asiento a la fila inferior", "seat.yb", 0.5, 20, uk="L", show=_bolted),
    num("Separacion entre las dos columnas", "seat.gs", 1, 30, uk="L", show=_bolted),
    G("Soldadura del angulo al soporte", show=_welded),
    num("Cateto del filete", "seat.weld_size", 0.0625, 1, uk="L", show=_welded),
    combo("Electrodo", "seat.electrode", "@electrode", show=lambda p: _welded(p) or _stf(p)),
    check("Incremento direccional (AISC J2-5)", "seat.weld_dir", show=lambda p: _welded(p) or _stf(p)),
    G("Rigidizador", show=_stf),
    num("Ancho (proyeccion) W", "seat.st_W", 1, 20, uk="L", show=_stf),
    num("Altura H", "seat.st_H", 2, 40, uk="L", show=_stf),
    num("Espesor", "seat.st_t", 0.125, 3, uk="L", show=_stf),
    combo("Acero del rigidizador", "seat.st_steel", "@steel_plate", show=_stf),
    num("Cateto del filete al soporte", "seat.st_weld", 0.0625, 1, uk="L", show=_stf),
    N("El angulo superior y la union del ala inferior son solo de estabilidad y no se calculan."),
]


def label(prj) -> str:
    st = prj.seat
    return f"{st.beam} sobre asiento en {st.sup_label}  ({'rigidizado' if st.seat_type == SEAT_TYPES[1] else st.angle})"


def input_rows(prj, us) -> list:
    st = prj.seat
    g = geometry(st)
    rows = [("Viga", f"{st.beam} ({st.beam_steel})"), ("Soporte", f"{st.sup_label} ({st.sup_steel}) — {st.sup_kind}"),
            ("Asiento", f"{st.seat_type}; ancho {us.q('L', st.L_seat)}, retranqueo {us.q('L', st.setback)}, N = {us.q('L', st.N)}")]
    if g["stiffened"]:
        rows.append(("Rigidizador", f"{us.q('L', st.st_W)} × {us.q('L', st.st_H)} × {us.q('L', st.st_t)} ({st.st_steel}); filete {us.q('L', st.st_weld)} {st.electrode}"))
    else:
        rows.append(("Angulo de asiento", f"{st.angle} ({st.angle_steel}); {st.attach}"))
        rows.append(("Union", (f"{2 * st.n} pernos Ø{st.bolt_size} in {st.bolt_grade}; s = {us.q('L', st.s)}, yb = {us.q('L', st.yb)}, gs = {us.q('L', st.gs)}"
                               if not g["welded"] else f"filete {us.q('L', st.weld_size)} {st.electrode} en C")))
    rows.append(("Cargas (LRFD)", "; ".join(f"{n}: R = {us.q('F', v[0])}" for n, v in st.loads())))
    return rows


def draw(fig, prj):
    from . import drawing as D
    from matplotlib.patches import Rectangle, Polygon
    st = prj.seat
    g = geometry(st)
    beam, sup = g["beam"], g["sup"]
    gs_ = fig.add_gridspec(2, 1, height_ratios=[1.5, 1])
    ax, ax2 = fig.add_subplot(gs_[0]), fig.add_subplot(gs_[1])
    D.blank(ax); D.blank(ax2)
    if beam is None:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    d, tf, tw, bf = beam.d, beam.tf, beam.tw, beam.bf
    Lshow = max(st.setback + st.N + 4.0, 10.0)
    ts = _t_support(st, sup) or 0.5
    # elevacion (y hacia arriba; el tope del asiento en y = 0)
    lv = g.get("lv", st.st_H)
    ax.add_patch(Rectangle((-ts, -lv - 1.0), ts, lv + d + 2.5, fc=D.C_SUP, ec="#555555", lw=0.8, hatch="////", zorder=1))
    ax.add_patch(Rectangle((st.setback, tf), Lshow, d - 2 * tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((st.setback, 0), Lshow, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((st.setback, d - tf), Lshow, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    if not g["stiffened"]:
        t = g["t"]
        ax.add_patch(Polygon([(0, 0), (g["lh"], 0), (g["lh"], -t), (t, -t), (t, -lv), (0, -lv)], closed=True, fc=D.C_ANGLE, ec=D.C_ANGLE_EDGE, lw=1.2, zorder=4))
        if not g["welded"]:
            for i in range(g["n"]):
                ax.plot([t / 2], [-(lv - st.yb - i * st.s)], marker="o", mfc="white", mec=D.C_BOLT, ms=6, zorder=6)
        else:
            ax.plot([0, 0], [-lv, 0], color=D.C_WELD, lw=3.0, zorder=5)
        ax.text(0.2, -lv - 1.2, f"{st.angle} × {q(st.L_seat)} {us.L}  —  {st.attach}", fontsize=7.5, color=D.C_ANGLE_EDGE, va="top")
    else:
        ax.add_patch(Polygon([(0, 0), (st.st_W, 0), (0, -st.st_H)], closed=True, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.2, zorder=4))
        ax.plot([0, 0], [-st.st_H, 0], color=D.C_WELD, lw=3.0, zorder=5)
        ax.text(0.2, -st.st_H - 1.2, f"Rigidizador {q(st.st_W)} × {q(st.st_H)} × {q(st.st_t)} {us.L} — filete {float_to_frac(st.st_weld)}\"", fontsize=7.5, color=D.C_PLATE_EDGE, va="top")
    # reaccion
    xr_ = g["eR"]
    ax.annotate("", xy=(xr_, 0.0), xytext=(xr_, 2.8), arrowprops=dict(arrowstyle="-|>", color="#c00000", lw=1.6), zorder=8)
    ax.text(xr_ + 0.2, 2.4, "R", color="#c00000", fontsize=9)
    D._dim(ax, (0, d + 0.6), (st.setback, d + 0.6), 0.9, q(st.setback))
    D._dim(ax, (st.setback, d + 0.6), (st.setback + st.N, d + 0.6), 2.4, f"N = {q(st.N)}")
    ax.set_xlim(-ts - 5, st.setback + Lshow + 3)
    ax.set_ylim(-lv - 4.0, d + 5.0)
    ax.set_title(f"Elevacion — {st.beam} sobre asiento ({'rigidizado' if g['stiffened'] else st.angle})", fontsize=9)
    # planta: asiento y huella de la viga
    W_ = st.st_W if g["stiffened"] else g.get("lh", st.N + st.setback)
    ax2.add_patch(Rectangle((-ts, -st.L_seat / 2 - 1.5), ts, st.L_seat + 3, fc=D.C_SUP, ec="#555555", lw=0.8, hatch="////", zorder=1))
    ax2.add_patch(Rectangle((0, -st.L_seat / 2), W_, st.L_seat, fc=D.C_ANGLE if not g["stiffened"] else D.C_PLATE, ec="#555555", lw=1.2, alpha=0.7, zorder=2))
    ax2.add_patch(Rectangle((st.setback, -bf / 2), Lshow, bf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.2, alpha=0.55, zorder=3))
    ax2.add_patch(Rectangle((st.setback, -tw / 2), Lshow, tw, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.2, zorder=4))
    D._dim(ax2, (0, -st.L_seat / 2), (0, st.L_seat / 2), -1.8, f"{q(st.L_seat)}", horizontal=False)
    D._dim(ax2, (st.setback, -st.L_seat / 2), (st.setback + st.N, -st.L_seat / 2), -1.6, f"N = {q(st.N)}")
    ax2.set_xlim(-ts - 5, st.setback + Lshow + 3)
    ax2.set_ylim(-st.L_seat / 2 - 4.5, st.L_seat / 2 + 2.5)
    ax2.set_title("Planta (vista desde arriba)", fontsize=9)
