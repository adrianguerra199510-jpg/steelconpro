# -*- coding: utf-8 -*-
"""Conexion de corte con doble angulo: viga secundaria a viga maestra o a columna.

Dos angulos a ambos lados del alma de la viga. Los pernos del alma (grupo A) trabajan en doble corte y reciben la
reaccion con la excentricidad a = gw (de la cara del soporte a la fila de pernos): centro instantaneo.  La pierna que
va al soporte se atornilla (grupo B: dos columnas de pernos, cortante concentrico, V/(2·n) por perno, simple corte) o
se suelda (lineas verticales con la misma excentricidad).  Se verifica ademas: aplastamiento y desgarramiento en
alma, angulos y soporte; cortante, rotura y bloque de cortante de los angulos; alma de la viga (cope incluido).

NO se evalua: pandeo local por cope, flexion de las piernas de los angulos (conexion simple: se supone que la flexibilidad
de los angulos acomoda la rotacion), carga axial, agujeros ranurados ni deslizamiento critico.
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from ..units import float_to_frac
from . import beamend
from .base import run_combos, add_check
from .common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, FNV, bolt_db, hole_std, hole_net, edge_min, bolt_shear_rn,
                     ic_vertical_line, block_shear_rn, bearing_group, bearing_rn, weld_lines_vertical)
from .formspec import G, N, num, intf, combo, check
from .specs import CT_DOUBLE_ANGLE, SUP_KINDS, BOLT_GRADES, SHEAR_BOLT_SIZES, DA_ATTACH

NAME = CT_DOUBLE_ANGLE


def geometry(st):
    beam = CATALOG.get(st.beam)
    sup = CATALOG.get(st.sup_label)
    ang = CATALOG.get(st.angle)
    db = bolt_db(st.bolt_size)
    n = max(int(st.n), 1)
    g = dict(beam=beam, sup=sup, ang=ang, db=db, dh=hole_std(db), dhn=hole_net(db), n=n, Lb=(n - 1) * st.s)
    if ang is not None:
        long_, short = max(ang.d, ang.bf), min(ang.d, ang.bf)
        g["lw"] = short if st.long_on_support else long_            # pierna contra el alma de la viga
        g["ls"] = long_ if st.long_on_support else short            # pierna contra el soporte
        g["t"] = ang.tw
    g["lev_a"] = (st.L_ang - g["Lb"]) / 2.0                          # distancia vertical al borde del angulo
    g["welded"] = st.attach == DA_ATTACH[1]
    g.update(beamend.geometry(beam, n, st.s, st.gw, st.gap, st.y_top, st.cope_top, st.cope_bot, st.cope_len))
    return g


def _t_support(st, sup):
    if sup is None:
        return 0.0
    return sup.tf if st.sup_kind == SUP_KINDS[2] else sup.tw


def check_input(st) -> list:
    g = geometry(st)
    w = []
    beam, sup, ang = g["beam"], g["sup"], g["ang"]
    if beam is None:
        return [f"** Perfil de la viga '{st.beam}' no encontrado en el catalogo. **"]
    if sup is None:
        w.append(f"** Perfil del soporte '{st.sup_label}' no encontrado en el catalogo. **")
    if ang is None or ang.kind != "L":
        return w + [f"** Angulo '{st.angle}' no encontrado en el catalogo (use un perfil L). **"]
    if st.bolt_grade not in FNV:
        w.append(f"** Calidad de perno '{st.bolt_grade}' no reconocida. **")
    if not (2 <= st.n <= 12):
        w.append(f"** {st.n} pernos por fila: el doble angulo del Manual (Tabla 10-1) cubre de 2 a 12. **")
    db = g["db"]
    if g["lev_a"] < -1e-9:
        w.append(f"** El largo de los angulos ({st.L_ang:g} in) no alcanza para los {st.n} pernos con separacion {st.s:g} in. **")
    if g["welded"] is False and st.gs + edge_min(db) > g["ls"] + 1e-9:
        w.append("** La pierna del soporte es demasiado corta para la fila de pernos con su distancia al borde. **")
    if st.gw + edge_min(db) > g["lw"] + 1e-9:
        w.append("** La pierna del alma es demasiado corta para la fila de pernos con su distancia al borde. **")
    if g["h0"] <= 0 or g["lev_t"] < -1e-9 or g["lev_b"] < -1e-9:
        w.append("** Los pernos no caben en el alma que queda: revise y_top, el numero de pernos, la separacion o el cope. **")
    if not g["coped"] and beam.kdes > 0 and (g["lev_t"] < beam.kdes or g["lev_b"] < beam.kdes):
        w.append("** Hay pernos dentro de la zona del filete alma-ala (k): suba/baje el grupo o use cope. **")
    if g["coped"] and g["ct"] > 0 and g["ct"] < beam.tf - 1e-9:
        w.append("** El cope superior es menor que el espesor del ala: el ala no queda eliminada. **")
    if g["coped"] and st.cope_len <= 0:
        w.append("** Hay cope con longitud 0: indique la longitud del cope. **")
    if st.gw <= st.gap:
        w.append("** gw debe ser mayor que el retranqueo del extremo de la viga. **")
    if not g["coped"] and beam.kdes > 0 and st.L_ang > beam.d - 2 * beam.kdes + 1e-9:
        w.append("Los angulos son mas largos que el alma plana (d − 2k): chocarian con las alas de la viga.")
    w += beamend.cope_warnings(st.gap, st.cope_len, st.top_flush, g, beam, sup, st.sup_kind == SUP_KINDS[0])
    w.append("Flexion de las piernas de los angulos y torsion fuera del plano no se verifican (conexion simple).")
    return w


def solve_one(prj, name, vals, rec):
    Vu = vals[0]
    st = prj.dang
    g = geometry(st)
    ck = []
    beam, sup, ang = g["beam"], g["sup"], g["ang"]
    if beam is None or sup is None or ang is None or g["n"] < 2 or st.s <= 0:
        return ck
    u = prj.units()
    db, dh, dhn, n = g["db"], g["dh"], g["dhn"], g["n"]
    s, a = st.s, st.gw
    t, L = g["t"], st.L_ang
    am = M.find(M.SHAPE_STEELS, st.angle_steel)
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    sp = M.find(M.SHAPE_STEELS, st.sup_steel)
    FEXX = M.find(M.ELECTRODES, st.electrode, 1).FEXX
    tw = beam.tw
    ys = [((n - 1) / 2.0 - i) * s for i in range(n)]
    lev_a = g["lev_a"]
    leh_a = g["lw"] - st.gw                                       # del eje de pernos al canto de la pierna del alma

    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Viga apoyada", st.beam, f"{st.beam_steel}: Fy = {rec.f('S', bm.Fy)}, Fu = {rec.f('S', bm.Fu)};  d = {rec.f('L', beam.d)}, "
                f"tw = {rec.f('L', tw)}", None)
        rec.add("Soporte", f"{st.sup_label} — {st.sup_kind}", f"{st.sup_steel}: Fy = {rec.f('S', sp.Fy)}, Fu = {rec.f('S', sp.Fu)}", None)
        rec.add("Angulos", f"2 × {st.angle} × {rec.n('L', L)} {u.L}", f"{st.angle_steel}: Fy = {rec.f('S', am.Fy)}, Fu = {rec.f('S', am.Fu)}; "
                f"pierna del alma {rec.f('L', g['lw'])}, del soporte {rec.f('L', g['ls'])}, t = {rec.f('L', t)}", None)
        rec.add("Pernos", f"{n} × Ø{st.bolt_size} in {st.bolt_grade} por fila", f"s = {rec.f('L', s)}, gw = a = {rec.f('L', a)}, "
                f"gs = {rec.f('L', st.gs)}; {st.attach}", None)
        rec.add("Vu", "reaccion factorizada de la viga", "", Vu, "F")

    # ------------------------------------------------------------- distancias
    add_check(ck, rec, "geo_s", "Separacion entre pernos  s ≥ 2-2/3·db", 8.0 / 3.0 * db, s, "in", "AISC J3.3", "3·db es lo preferible")
    add_check(ck, rec, "geo_lev_a", "Distancia vertical al borde del angulo", edge_min(db), lev_a, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "geo_leh_a", "Distancia del eje de pernos al canto de la pierna del alma", edge_min(db), leh_a, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "geo_leh_b", "Distancia del extremo de la viga a los pernos", edge_min(db), g["leh_b"], "in", "AISC Tabla J3.4")
    if g["ct"] > 0:
        add_check(ck, rec, "geo_lev_b", "Distancia del cope superior al perno superior", edge_min(db), g["lev_t"], "in", "AISC Tabla J3.4")
    if not g["welded"]:
        add_check(ck, rec, "geo_leh_s", "Distancia del eje de pernos al canto de la pierna del soporte", edge_min(db), g["ls"] - st.gs, "in", "AISC Tabla J3.4")

    # -------------------------------------------- grupo A: pernos del alma (doble corte, excentricos)
    ic = ic_vertical_line(ys, a)
    rn1 = bolt_shear_rn(db, st.bolt_grade)
    capA = PHI_BOLT * 2.0 * rn1 * ic.C
    k = Vu / ic.C if ic.C > 0 else 0.0
    Fx, Fy = [fx * k for fx in ic.fx], [fy * k for fy in ic.fy]      # fuerza TOTAL de cada perno (dos angulos)
    if rec:
        rec.section("PERNOS DEL ALMA (grupo A) — doble corte, centro instantaneo")
        rec.add("rn (doble corte)", "2·Fnv·Ab", f"2·{rec.f('S', FNV[st.bolt_grade])}·{rec.f('A', math.pi * db ** 2 / 4)}", 2 * rn1, "F", "AISC J3.6")
        rec.add("C", "coeficiente del grupo (centro instantaneo)", f"e = a = {rec.f('L', a)}; n = {n}; s = {rec.f('L', s)}", ic.C, "-",
                "Manual Parte 7", note=f"el metodo elastico daria C = {ic.C_elastic:.3f}")
    add_check(ck, rec, "bolt_a", f"Pernos del alma — doble corte con excentricidad (IC, C = {ic.C:.2f})", Vu, capA, "kip", "AISC J3.6",
              f"{n} × Ø{st.bolt_size} {st.bolt_grade}; φ·C·2rn")

    # aplastamiento en el alma de la viga (fuerza total del perno)
    lev_web_t = (g["lev_t"] - dh / 2) if g["ct"] > 0 else 1e9
    r, wi, F = bearing_group(Fx, Fy, db, tw, bm.Fu, lambda i: (lev_web_t if i == 0 else s - dh),
                             {i: g["leh_b"] - dh / 2 for i in range(n) if ys[i] < -1e-9})
    add_check(ck, rec, "brg_web", "Pernos — aplastamiento y desgarramiento en el alma de la viga", F, F / r if r > 0 else 0.0, "kip",
              "AISC J3.10", f"perno #{wi + 1} (desde arriba): {F:.1f} kip")
    # aplastamiento en las piernas de los angulos (la mitad de la fuerza en cada angulo)
    Fxa, Fya = [f / 2 for f in Fx], [f / 2 for f in Fy]
    r, wi, F = bearing_group(Fxa, Fya, db, t, am.Fu, lambda i: ((lev_a - dh / 2) if i == n - 1 else s - dh),
                             {i: leh_a - dh / 2 for i in range(n) if ys[i] < -1e-9})
    add_check(ck, rec, "brg_ang", "Pernos — aplastamiento y desgarramiento en la pierna del alma del angulo", F, F / r if r > 0 else 0.0, "kip",
              "AISC J3.10", f"perno #{wi + 1}: {F:.1f} kip por angulo")

    # -------------------------------------------- angulos (cada uno con Vu/2)
    Vh = Vu / 2.0
    Rvy = PHI_YIELD * 0.6 * am.Fy * t * L
    add_check(ck, rec, "ang_vy", "Angulo — fluencia por cortante (cada uno, Vu/2)", Vh, Rvy, "kip", "AISC J4.2(a)")
    Rvr_w = PHI_RUPT * 0.6 * am.Fu * t * (L - n * dhn)
    add_check(ck, rec, "ang_vr_w", "Angulo — rotura por cortante neto, pierna del alma", Vh, Rvr_w, "kip", "AISC J4.2(b)")
    Lgv = lev_a + (n - 1) * s
    Rbs_w = PHI_RUPT * block_shear_rn(am.Fy, am.Fu, t, Lgv, Lgv - (n - 0.5) * dhn, leh_a - 0.5 * dhn)
    add_check(ck, rec, "ang_bs_w", "Angulo — bloque de cortante, pierna del alma", Vh, Rbs_w, "kip", "AISC J4.3",
              f"Lgv = {u.q('L', Lgv)}, Lnt = {u.q('L', leh_a - 0.5 * dhn)}, Ubs = 1.0")

    # ------------------------------------- grupo B: union de la pierna del soporte
    if not g["welded"]:
        Vb = Vu / (2.0 * n)
        capB = PHI_BOLT * rn1
        add_check(ck, rec, "bolt_b", "Pernos del soporte (grupo B) — corte simple, concentrico", Vb, capB, "kip", "AISC J3.6",
                  f"2 × {n} pernos Ø{st.bolt_size}; Vu/(2n) por perno")
        Rvr_s = PHI_RUPT * 0.6 * am.Fu * t * (L - n * dhn)
        add_check(ck, rec, "ang_vr_s", "Angulo — rotura por cortante neto, pierna del soporte", Vh, Rvr_s, "kip", "AISC J4.2(b)")
        leh_s = g["ls"] - st.gs
        Rbs_s = PHI_RUPT * block_shear_rn(am.Fy, am.Fu, t, Lgv, Lgv - (n - 0.5) * dhn, leh_s - 0.5 * dhn)
        add_check(ck, rec, "ang_bs_s", "Angulo — bloque de cortante, pierna del soporte", Vh, Rbs_s, "kip", "AISC J4.3")
        ts = _t_support(st, sup)
        for key, ttl, tt, Fu_, Lc_end in (("brg_ang_s", "Pernos — aplastamiento en la pierna del soporte del angulo", t, am.Fu, lev_a - dh / 2),
                                          ("brg_sup", "Pernos — aplastamiento en el soporte", ts, sp.Fu, 1e9)):
            worst = max((Vb / max(PHI_BOLT * bearing_rn(db, tt, Fu_, (Lc_end if i == 0 else s - dh)), 1e-9) for i in range(n)),
                        default=0.0)
            add_check(ck, rec, key, ttl, Vb, Vb / worst if worst > 0 else 0.0, "kip", "AISC J3.10",
                      "distancia al borde del soporte no verificada (se supone ancha)" if key == "brg_sup" else "")
    else:
        nl = 2 * st.weld_lines
        f, cap_w, th, fv, fh = weld_lines_vertical(Vu, a, L, st.weld_size, FEXX, nl, st.weld_dir)
        if rec:
            rec.section("SOLDADURA DE LOS ANGULOS AL SOPORTE")
            rec.add("fv", "Vu / (nl·L)", "", fv, "LF")
            rec.add("fh", "6·Vu·a / (nl·L²)", "", fh, "LF")
            rec.add("θ", "atan(fh / fv)", f"{th:.1f}°", None, "-")
        add_check(ck, rec, "weld", f"Soldadura de los angulos al soporte — {nl} lineas verticales", f, cap_w, "kip/in", "AISC J2.4",
                  f"w = {float_to_frac(st.weld_size)}\", {st.electrode}, θ = {th:.0f}°; metodo elastico, e = a")
        ts = _t_support(st, sup)
        add_check(ck, rec, "weld_base_s", "Metal base del soporte (cortante bajo el cordon)", f, PHI_RUPT * 0.6 * sp.Fu * ts, "kip/in",
                  "AISC J4.2", f"espesor del soporte {u.q('L', ts)}")
        add_check(ck, rec, "weld_base_a", "Metal base del angulo (cortante bajo el cordon)", f, PHI_RUPT * 0.6 * am.Fu * t, "kip/in",
                  "AISC J4.2", f"espesor del angulo {u.q('L', t)}")
        add_check(ck, rec, "weld_min", "Tamano minimo del filete", M.min_fillet(min(t, ts) if ts > 0 else t), st.weld_size, "in", "AISC Tabla J2.4")
        add_check(ck, rec, "weld_max", "Tamano maximo del filete en el canto del angulo", st.weld_size, M.max_fillet(t), "in", "AISC J2.2b")
        add_check(ck, rec, "ang_vr_s", "Angulo — cortante en la pierna soldada (area bruta)", Vh, Rvy, "kip", "AISC J4.2(a)")

    # ------------------------------------------------------------ viga apoyada
    beamend.web_checks(ck, rec, u, g, beam, bm, Vu, n, s, dhn)
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.dang, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "dang"
TAB = "Doble angulo"
PREFIX = "DA"
TITLE = "CONEXION DE CORTE CON DOBLE ANGULO"
NORMS = "AISC 360-22 (cap. J) · AISC Steel Construction Manual 15a Ed., Partes 7, 9 y 10"
LOADS = [("Vu", "F")]
LOADS_NOTE = "Cada fila es una combinacion con la reaccion vertical Vu de la viga (ya factorizada). Sin carga axial en la viga."

_welded = lambda p: p.dang.attach == DA_ATTACH[1]
FORM = [
    G("Viga apoyada"),
    combo("Perfil", "dang.beam", "@I", editable=True, help="Perfil I de la viga que llega al soporte."),
    combo("Acero", "dang.beam_steel", "@steel_shape"),
    G("Soporte"),
    combo("Tipo de soporte", "dang.sup_kind", SUP_KINDS, help="Viga maestra (alma), alma o ala de columna: define el espesor del metal base y el dibujo."),
    combo("Perfil del soporte", "dang.sup_label", "@I", editable=True),
    combo("Acero del soporte", "dang.sup_steel", "@steel_shape"),
    G("Angulos (dos, uno a cada lado del alma)"),
    combo("Angulo", "dang.angle", "@L", editable=True, help="Perfil L; los dos angulos son iguales."),
    combo("Acero del angulo", "dang.angle_steel", "@steel_shape"),
    check("Pierna larga contra el soporte", "dang.long_on_support", help="Solo importa en angulos de lados distintos."),
    num("Largo de los angulos", "dang.L_ang", 3, 60, uk="L", help="Altura de los angulos. La distancia vertical al borde sale de (L − (n−1)·s)/2."),
    combo("Union al soporte", "dang.attach", DA_ATTACH, help="Atornillado: dos columnas de pernos en las piernas del soporte, cortante concentrico. Soldado: lineas verticales de filete."),
    G("Pernos"),
    combo("Diametro", "dang.bolt_size", SHEAR_BOLT_SIZES),
    combo("Calidad", "dang.bolt_grade", BOLT_GRADES),
    intf("Pernos por fila", "dang.n", 1, 14, help="Entre 2 y 12 (Manual, Tabla 10-1)."),
    num("Separacion vertical  s", "dang.s", 0.5, 12, uk="L"),
    num("Gramil en la pierna del soporte  gs", "dang.gs", 0.5, 12, uk="L", help="Del respaldo de la pierna del alma a la fila de pernos de la pierna del soporte.", show=lambda p: not _welded(p)),
    num("Gramil en la pierna del alma  gw = a", "dang.gw", 0.5, 12, uk="L", help="Del respaldo de la pierna del soporte a la fila de pernos del alma. Es la excentricidad de los pernos del alma."),
    G("Soldadura al soporte", show=_welded),
    num("Cateto del filete", "dang.weld_size", 0.0625, 1, uk="L", show=_welded),
    combo("Electrodo", "dang.electrode", "@electrode", show=_welded),
    check("Incremento direccional (AISC J2-5)", "dang.weld_dir", show=_welded),
    intf("Lineas de soldadura por angulo", "dang.weld_lines", 1, 2, help="1 = solo el borde exterior de la pierna; 2 = ambos bordes verticales.", show=_welded),
    G("Posicion respecto a la viga"),
    num("Retranqueo del extremo de la viga", "dang.gap", 0, 3, uk="L"),
    num("Del tope de la viga al perno superior", "dang.y_top", -1, 60, uk="L", help="Negativo = automatico (centrado en el alma que queda)."),
    G("Cope de la viga apoyada"),
    num("Cope superior: profundidad", "dang.cope_top", 0, 30, uk="L"),
    num("Cope inferior: profundidad", "dang.cope_bot", 0, 30, uk="L"),
    num("Cope: longitud desde el extremo", "dang.cope_len", 0, 40, uk="L"),
    check("Tope de la viga a ras con el de la maestra", "dang.top_flush"),
    N("NO se evalua el pandeo local del alma por cope (Manual Parte 9) ni la flexion de las piernas de los angulos."),
]


def label(prj) -> str:
    st = prj.dang
    return f"{st.beam} → {st.sup_label}  (2{st.angle}, {st.n}×Ø{st.bolt_size})"


def input_rows(prj, us) -> list:
    st = prj.dang
    g = geometry(st)
    rows = [("Viga apoyada", f"{st.beam} ({st.beam_steel})"),
            ("Soporte", f"{st.sup_label} ({st.sup_steel}) — {st.sup_kind}"),
            ("Angulos", f"2 × {st.angle} × {us.q('L', st.L_ang)} ({st.angle_steel}); pierna del alma "
                        f"{us.q('L', g.get('lw', 0))}, del soporte {us.q('L', g.get('ls', 0))}"),
            ("Pernos", f"{st.n} Ø{st.bolt_size} in {st.bolt_grade} por fila; s = {us.q('L', st.s)}, gw = a = {us.q('L', st.gw)}"
                       + ("" if g["welded"] else f", gs = {us.q('L', st.gs)}")),
            ("Union al soporte", st.attach + (f": filete {us.q('L', st.weld_size)} {st.electrode}, {st.weld_lines} linea(s) por angulo"
                                                if g["welded"] else "")),
            ("Retranqueo", us.q("L", st.gap))]
    if g["coped"]:
        rows.append(("Cope", f"superior {us.q('L', g['ct'])}, inferior {us.q('L', g['cb'])}, longitud {us.q('L', st.cope_len)}"))
    rows.append(("Cargas (LRFD)", "; ".join(f"{n}: Vu = {us.q('F', v[0])}" for n, v in st.loads())))
    return rows


def draw(fig, prj):
    from . import drawing as D
    st = prj.dang
    g = geometry(st)
    gs_ = fig.add_gridspec(2, 1, height_ratios=[1.5, 1])
    ax, ax2 = fig.add_subplot(gs_[0]), fig.add_subplot(gs_[1])
    D.blank(ax)
    D.blank(ax2)
    beam, sup, ang = g["beam"], g["sup"], g.get("ang")
    if beam is None or ang is None:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    d, tw, t = beam.d, beam.tw, g["t"]
    n, s, a = g["n"], st.s, st.gw
    Lshow = max(st.gw + 3.0, g["x_cope"] - st.gap + 3.0, g["lw"] + 2.0)
    sx0, xr = D.support_and_beam(ax, beam, sup, st.sup_kind == SUP_KINDS[0], st.top_flush, g, st.gap, Lshow)
    y0 = g["y_top"] - g["lev_a"]
    y1 = y0 + st.L_ang
    from matplotlib.patches import Rectangle, Polygon
    ax.add_patch(Rectangle((0, y0), g["lw"], st.L_ang, fc=D.C_ANGLE, ec=D.C_ANGLE_EDGE, lw=1.2, alpha=0.65, zorder=4))
    for i in range(n):
        D.bolt(ax, a, g["y_top"] + i * s, g["dh"])
        if not g["welded"]:                                       # pernos de la pierna del soporte (en el plano del soporte)
            ax.plot([t / 2], [g["y_top"] + i * s], marker="x", color=D.C_BOLT, ms=4, zorder=7)
    if g["welded"]:
        ax.plot([0, 0], [y0, y1], color=D.C_WELD, lw=3.2, solid_capstyle="butt", zorder=5)
    D._dim(ax, (0, 0), (st.gap, 0), -0.9, q(st.gap) if st.gap > 0 else "")
    D._dim(ax, (0, 0), (a, 0), -2.5, f"a = gw = {q(a)}")
    if g["ct"] > 0 and st.cope_len > 0:
        D._dim(ax, (st.gap, 0), (st.gap + st.cope_len, 0), -4.1, f"c = {q(st.cope_len)}")
    D._dim(ax, (xr, y0), (xr, y1), 1.6, f"L = {q(st.L_ang)}", horizontal=False)
    if n > 1:
        D._dim(ax, (xr, g["y_top"]), (xr, g["y_top"] + g["Lb"]), 3.4, f"{n - 1}×{q(s)} = {q(g['Lb'])}", horizontal=False)
    if g["ct"] > 0:
        D._dim(ax, (sx0, 0), (sx0, g["ct"]), -1.6, f"cope sup. = {q(g['ct'])}", horizontal=False)
    ax.text(0.2, d + 0.9, f"2 {st.angle} × {q(st.L_ang)} {us.L} — {n} Ø{st.bolt_size}\" {st.bolt_grade} (doble corte)", fontsize=7.5, color=D.C_ANGLE_EDGE, va="top")
    ax.text(0.2, d + 1.7, f"{st.attach}" + (f" — filete {float_to_frac(st.weld_size)}\" {st.electrode}" if g["welded"] else ""), fontsize=7.5, color=D.C_BOLT, va="top")
    ax.set_xlim(sx0 - 6.0, xr + 7.5)
    ax.set_ylim(d + 3.4, -6.5)
    ax.set_title(f"Elevacion — {st.beam} sobre {st.sup_label} ({st.sup_kind.lower()})", fontsize=9)
    # ---- planta
    bf = beam.bf
    tws = _t_support(st, sup) or 0.5
    D.hatched(ax2, -tws, -bf / 2 - 1.0, 0, bf / 2 + 1.0)
    ax2.add_patch(Rectangle((st.gap, -tw / 2), Lshow, tw, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.2, zorder=3))
    lw_, ls_ = g["lw"], g["ls"]
    for sg in (1, -1):
        pts = [(0, sg * tw / 2), (lw_, sg * tw / 2), (lw_, sg * (tw / 2 + t)), (t, sg * (tw / 2 + t)), (t, sg * (tw / 2 + ls_)), (0, sg * (tw / 2 + ls_))]
        ax2.add_patch(Polygon(pts, closed=True, fc=D.C_ANGLE, ec=D.C_ANGLE_EDGE, lw=1.2, zorder=4))
        if not g["welded"]:
            zb = sg * (tw / 2 + st.gs)
            ax2.add_patch(Rectangle((-0.3, zb - g["db"] / 2), t + 0.6, g["db"], fc="white", ec=D.C_BOLT, lw=1.1, zorder=6))
        else:
            ax2.add_patch(Polygon([(0, sg * (tw / 2 + ls_)), (st.weld_size, sg * (tw / 2 + ls_)), (0, sg * (tw / 2 + ls_ + st.weld_size))], fc=D.C_WELD, ec=D.C_WELD, zorder=5))
    ax2.add_patch(Rectangle((a - g["db"] / 2, -(tw / 2 + t) - 0.3), g["db"], tw + 2 * t + 0.6, fc="white", ec=D.C_BOLT, lw=1.2, zorder=6))
    D._dim(ax2, (0, -(tw / 2 + ls_)), (a, -(tw / 2 + ls_)), -1.0, f"a = {q(a)}")
    ax2.text(Lshow * 0.6, tw / 2 + ls_ * 0.9, f"angulo {st.angle}  t = {q(t)}\nalma tw = {q(tw)}", fontsize=7.0, color=D.C_DIM, ha="center")
    ax2.set_xlim(-tws - 1.5, xr + 3.0)
    ax2.set_ylim(-(tw / 2 + ls_) - 3.2, tw / 2 + ls_ + 2.0)
    ax2.set_title("Planta (vista desde arriba)", fontsize=9)
