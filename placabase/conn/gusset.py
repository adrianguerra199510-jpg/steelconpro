# -*- coding: utf-8 -*-
"""Cartela de arriostramiento en la esquina viga-columna: seccion de Whitmore, bloque de cortante, pandeo (Thornton) y
fuerzas de interfaz por el metodo de fuerza uniforme (UFM), caso sin momentos (AISC Manual 15a Ed., Parte 13).

UFM (θ desde la vertical, eb = d_viga/2, ec = d_col/2, α = L_b/2, β = L_c/2):
    condicion sin momentos:   tanθ = (α + ec)/(β + eb)           (si L_c = 0 el programa toma el que la cumple)
    r = √((α + ec)² + (β + eb)²) ;  H_b = α·P/r ,  V_b = eb·P/r   (cartela-viga)
                                   H_c = ec·P/r ,  V_c = β·P/r   (cartela-columna)
Se verifican: union del arriostramiento (pernos con metodo elastico y momento P·e, aplastamiento en cartela y arriostramiento, o soldadura),
seccion de Whitmore (fluencia y rotura en traccion, pandeo K = 0.65 con L_avg en compresion), bloque de cortante de la cartela, soldaduras y esfuerzos
en las interfaces, y efectos locales en el ala/alma de la viga y de la columna (J10.1, J10.2, J10.3).
NO se evalua: el arriostramiento como miembro, el borde libre de la cartela (Dowswell), la conexion viga-columna bajo las fuerzas de la cartela,
momentos de interfaz si la geometria no cumple la condicion del UFM (se avisa; fatal si la diferencia pasa de 10 %).
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from ..units import float_to_frac
from .base import run_combos, add_check, not_evaluated
from .common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, PHI_WELD, FNV, bolt_db, hole_std, hole_net, edge_min, bolt_shear_rn, bearing_rn,
                     block_shear_rn, column_fcr, elastic_bolt_group, flange_local_bending, web_local_yielding, web_crippling)
from .formspec import G, N, num, intf, combo, check
from .specs import CT_GUSSET, BOLT_GRADES, SHEAR_BOLT_SIZES, GUS_CONN

NAME = CT_GUSSET
T30 = math.tan(math.radians(30.0))


def geometry(st):
    beam, col = CATALOG.get(st.beam), CATALOG.get(st.col)
    th = math.radians(st.theta)
    db = bolt_db(st.bolt_size)
    g = dict(beam=beam, col=col, th=th, db=db, dh=hole_std(db), dhn=hole_net(db), bolted=st.conn == GUS_CONN[0])
    if beam is None or col is None or not (0.0 < st.theta < 90.0):
        return g
    ec, eb = col.d / 2.0, beam.d / 2.0
    al = st.L_b / 2.0
    beta_req = (al + ec) / math.tan(th) - eb
    Lc_req = 2.0 * beta_req
    Lc = st.L_c if st.L_c > 0 else Lc_req
    be = Lc / 2.0
    r = math.hypot(al + ec, be + eb)
    g.update(ec=ec, eb=eb, al=al, be=be, Lc=Lc, Lc_req=Lc_req, r=r,
             mis=abs((al + ec) / max(be + eb, 1e-9) - math.tan(th)) / math.tan(th))
    g["Hb"], g["Vb"], g["Hc"], g["Vc"] = al / r, eb / r, ec / r, be / r          # por unidad de P
    # conexion del arriostramiento
    if g["bolted"]:
        g["Lconn"] = (st.n_rows - 1) * st.s
        g["bg"] = (st.n_lines - 1) * st.g_t
    else:
        g["Lconn"] = st.Lw
        g["bg"] = st.g_t
    g["Ww"] = 2.0 * g["Lconn"] * T30 + g["bg"]
    # longitud de pandeo: de la primera fila al primer borde de la cartela sobre el eje del arriostramiento
    s_beam = eb / math.cos(th)                                  # distancia del punto de trabajo a la cara superior de la viga, sobre el eje
    s_col = ec / math.sin(th)                                   # ... a la cara de la columna
    g["s_edge"] = max(s_beam, s_col)                          # el eje entra en la cartela al pasar ambas caras
    g["L2"] = max(st.D1 - g["s_edge"], 0.0)
    return g


def check_input(st) -> list:
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    w = []
    if beam is None or beam.kind != "W" or col is None or col.kind != "W":
        return ["** Viga o columna no encontrada o no es un perfil I del catalogo. **"]
    if not (0.0 < st.theta < 90.0):
        return ["** El angulo del arriostramiento debe estar entre 0° y 90° (medido desde la vertical). **"]
    if g["bolted"] and st.bolt_grade not in FNV:
        w.append(f"** Calidad de perno '{st.bolt_grade}' no reconocida. **")
    if st.t <= 0 or st.L_b <= 0:
        w.append("** El espesor y el largo de la cartela deben ser positivos. **")
    if g["Lc"] <= 0:
        w.append(f"** La geometria no permite un UFM sin momentos: α + ec ≤ eb·tanθ (aumente L_b). **")
    if st.L_c > 0 and g["mis"] > 0.10:
        w.append(f"** L_c = {st.L_c:g} in no cumple la condicion del UFM (tanθ = (α+ec)/(β+eb)): diferencia {100 * g['mis']:.0f} %; el valor que la cumple es {g['Lc_req']:.2f} in. **")
    elif st.L_c > 0 and g["mis"] > 0.02:
        w.append(f"L_c = {st.L_c:g} in se aparta {100 * g['mis']:.0f} % de la condicion del UFM (L_c = {g['Lc_req']:.2f} in): se desprecian los momentos de interfaz.")
    if g["bolted"]:
        if st.n_rows < 1 or st.n_lines < 1:
            w.append("** Faltan filas o lineas de pernos. **")
        if st.m_planes not in (1, 2):
            w.append("** Los planos de corte deben ser 1 o 2. **")
    elif st.nlw not in (2, 4) or st.Lw <= 0:
        w.append("** Soldadura del arriostramiento: 2 o 4 lineas con largo positivo. **")
    if st.D1 <= g.get("s_edge", 0.0):
        w.append("La primera fila de pernos queda antes del borde de la cartela sobre el eje (D1 menor que la distancia del punto de trabajo al borde): "
                 "la longitud de pandeo sale 0; revise D1.")
    w.append("Aproximaciones: UFM caso sin momentos; L1 = L3 = L2 en Thornton; no se verifican el arriostramiento, el borde libre de la cartela ni la conexion viga-columna.")
    return w


def solve_one(prj, name, vals, rec):
    P0 = vals[0]
    st = prj.gus
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    ck = []
    if beam is None or col is None or beam.kind != "W" or col.kind != "W" or not (0.0 < st.theta < 90.0) or st.t <= 0 or st.L_b <= 0 or g["Lc"] <= 0:
        return ck
    if (g["bolted"] and (st.n_rows < 1 or st.n_lines < 1 or st.m_planes not in (1, 2))) or (not g["bolted"] and (st.nlw not in (2, 4) or st.Lw <= 0)):
        return ck                                      # datos imposibles: check_input ya avisa con '**'
    u = prj.units()
    gm = M.find(M.PLATE_STEELS, st.steel, 1)
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    cm = M.find(M.SHAPE_STEELS, st.col_steel)
    FEXX = M.find(M.ELECTRODES, st.electrode, 1).FEXX
    P = abs(P0)
    tens = P0 >= 0
    t, Lb, Lc = st.t, st.L_b, g["Lc"]
    Hb, Vb, Hc, Vc = (g[k] * P for k in ("Hb", "Vb", "Hc", "Vc"))
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("P", "fuerza del arriostramiento (" + ("traccion" if tens else "compresion") + ")", "", P, "F")
        rec.add("Viga / columna", f"{st.beam} / {st.col}", f"eb = {rec.f('L', g['eb'])}, ec = {rec.f('L', g['ec'])}; θ = {st.theta:g}° desde la vertical", None)
        rec.add("Cartela", f"t = {rec.n('L', t)} {u.L}", f"{st.steel}: Fy = {rec.f('S', gm.Fy)}, Fu = {rec.f('S', gm.Fu)}; L_b = {rec.f('L', Lb)}, L_c = {rec.f('L', Lc)}", None)
        rec.section("FUERZAS DE INTERFAZ — metodo de fuerza uniforme")
        rec.add("α, β", "L_b/2 , L_c/2", f"{rec.n('L', g['al'])} , {rec.n('L', g['be'])} {u.L}", None, note=f"condicion: tanθ = (α+ec)/(β+eb) → L_c requerido = {rec.f('L', g['Lc_req'])}")
        rec.add("r", "√((α+ec)² + (β+eb)²)", "", g["r"], "L")
        rec.add("H_b , V_b", "α·P/r , eb·P/r", f"{rec.n('F', Hb)} , {rec.n('F', Vb)}", None, note="cartela-viga: paralela y normal al ala")
        rec.add("H_c , V_c", "ec·P/r , β·P/r", f"{rec.n('F', Hc)} , {rec.n('F', Vc)}", None, note="cartela-columna: normal y paralela al ala")
    # --------------------------------------------------- union del arriostramiento
    db, dh, dhn = g["db"], g["dh"], g["dhn"]
    if g["bolted"]:
        nb = st.n_rows * st.n_lines
        pts = [(i * st.s, (j - (st.n_lines - 1) / 2.0) * st.g_t) for i in range(st.n_rows) for j in range(st.n_lines)]
        F = elastic_bolt_group(pts, P, 0.0, P * st.e_b)
        Fmax = max(math.hypot(fx, fy) for fx, fy in F)
        rn = bolt_shear_rn(db, st.bolt_grade)
        add_check(ck, rec, "br_bolt", f"Pernos del arriostramiento — cortante ({st.m_planes} plano{'s' if st.m_planes > 1 else ''})", Fmax,
                  PHI_BOLT * st.m_planes * rn, "kip", "AISC J3.6", f"{nb} pernos Ø{st.bolt_size}; metodo elastico, e = {u.q('L', st.e_b)}")
        Lc_g = [st.lg_end - dh / 2, st.s - dh] + ([st.g_t - dh] if st.n_lines > 1 else [])
        Lc_b = [st.Le - dh / 2, st.s - dh] + ([st.g_t - dh] if st.n_lines > 1 else [])
        add_check(ck, rec, "br_brg_g", "Pernos — aplastamiento en la cartela", Fmax, PHI_BOLT * min(bearing_rn(db, t, gm.Fu, x) for x in Lc_g), "kip", "AISC J3.10",
                  "fuerza total del perno sobre la cartela")
        add_check(ck, rec, "br_brg_b", "Pernos — aplastamiento en el arriostramiento", Fmax, PHI_BOLT * min(bearing_rn(db, st.t_br, st.Fu_br, x) for x in Lc_b), "kip", "AISC J3.10",
                  f"espesor total {u.q('L', st.t_br)}")
        add_check(ck, rec, "br_le", "Distancia del extremo del arriostramiento a la primera fila", edge_min(db), st.Le, "in", "AISC Tabla J3.4")
        add_check(ck, rec, "br_lg", "Distancia de la ultima fila al borde libre de la cartela", edge_min(db), st.lg_end, "in", "AISC Tabla J3.4")
        add_check(ck, rec, "br_sp", "Separacion de los pernos  s ≥ 2-2/3·db", 8.0 / 3.0 * db, st.s if st.n_rows > 1 else 1e9, "in", "AISC J3.3")
    else:
        f = P / (st.nlw * st.Lw)
        add_check(ck, rec, "br_weld", f"Soldadura del arriostramiento — {st.nlw} lineas", f, PHI_WELD * 0.60 * FEXX * 0.707 * st.w_br, "kip/in", "AISC J2.4",
                  f"w = {float_to_frac(st.w_br)}\", L = {u.q('L', st.Lw)}; fuerza axial (θ = 0°)")
        add_check(ck, rec, "br_weld_base", "Metal base de la cartela bajo la soldadura del arriostramiento", f, PHI_RUPT * 0.6 * gm.Fu * t / 1.0, "kip/in", "AISC J4.2",
                  "una linea por cara de la cartela")
    # ---------------------------------------------------------- cartela: Whitmore
    Ww = g["Ww"]
    if rec:
        rec.section("CARTELA — SECCION DE WHITMORE")
        rec.add("Ww", "2·L·tan30° + b", f"2·{rec.n('L', g['Lconn'])}·0.577 + {rec.n('L', g['bg'])}", Ww, "L", "Manual Parte 9", note="ancho de Whitmore (30° a cada lado de la primera a la ultima fila)")
    add_check(ck, rec, "gu_wy", "Cartela — fluencia en la seccion de Whitmore", P if tens else 0.0, PHI_YIELD * 0.9 * gm.Fy * Ww * t, "kip", "AISC J4.1(a)",
              "solo traccion" if not tens else f"Ww = {u.q('L', Ww)}")
    nh = st.n_lines if g["bolted"] else 0
    add_check(ck, rec, "gu_wr", "Cartela — rotura en la seccion de Whitmore (ultima fila)", P if tens else 0.0, 0.75 * gm.Fu * max(Ww - nh * dhn, 0.0) * t, "kip", "AISC J4.1(b)")
    L_avg = st.L_avg if st.L_avg > 0 else g["L2"]
    r_ = t / math.sqrt(12.0)
    KLr = 0.65 * L_avg / r_
    Pn_c = 0.9 * column_fcr(gm.Fy, KLr) * Ww * t
    add_check(ck, rec, "gu_buck", "Cartela — pandeo en compresion (Thornton, K = 0.65)", 0.0 if tens else P, Pn_c, "kip", "AISC E3 / Manual Parte 9",
              f"L_avg = {u.q('L', L_avg)}" + (" (automatica: L2)" if st.L_avg <= 0 else "") + f"; KL/r = {KLr:.0f}")
    if g["bolted"]:
        Lgv = 2.0 * ((st.n_rows - 1) * st.s + st.lg_end)
        Lnv = Lgv - 2.0 * (st.n_rows - 0.5) * dhn
        Lnt = g["bg"] - (st.n_lines - 1) * dhn
        add_check(ck, rec, "gu_bs", "Cartela — bloque de cortante en el grupo de pernos", P if tens else 0.0,
                  PHI_RUPT * block_shear_rn(gm.Fy, gm.Fu, t, Lgv, Lnv, Lnt), "kip", "AISC J4.3",
                  f"dos planos de corte de {u.q('L', Lgv / 2)} y traccion de {u.q('L', Lnt)} en la primera fila")
    # ------------------------------------------------------ interfaces: soldaduras y esfuerzos
    for key, ttl, Ha, Vn, Ll, w_ in (("gb", "cartela-viga", Hb, Vb, Lb, st.w_gb), ("gc", "cartela-columna", Vc, Hc, Lc, st.w_gc)):
        fa, fn = Ha / (2.0 * Ll), Vn / (2.0 * Ll)
        fr = math.hypot(fa, fn)
        th = math.degrees(math.atan2(fn, fa)) if fr > 0 else 0.0
        kd = (1.0 + 0.5 * math.sin(math.radians(th)) ** 1.5) if st.weld_dir else 1.0
        capw = PHI_WELD * 0.60 * FEXX * kd * 0.707 * w_
        add_check(ck, rec, f"{key}_weld", f"Soldadura {ttl} — dos lineas, fuerza resultante", fr, capw, "kip/in", "AISC J2.4",
                  f"w = {float_to_frac(w_)}\", L = {u.q('L', Ll)}; paralela {Ha:.1f} kip, normal {Vn:.1f} kip; θ = {th:.0f}°")
        add_check(ck, rec, f"{key}_pl_v", f"Cartela en la interfaz {ttl} — cortante", Ha, min(PHI_YIELD * 0.6 * gm.Fy, PHI_RUPT * 0.6 * gm.Fu) * t * Ll, "kip", "AISC J4.2")
        add_check(ck, rec, f"{key}_pl_n", f"Cartela en la interfaz {ttl} — fuerza normal", Vn, 0.9 * gm.Fy * t * Ll, "kip", "AISC J4.1(a)")
    add_check(ck, rec, "gb_weld_min", "Filete cartela-viga — tamano minimo", M.min_fillet(min(t, beam.tf)), st.w_gb, "in", "AISC Tabla J2.4")
    add_check(ck, rec, "gc_weld_min", "Filete cartela-columna — tamano minimo", M.min_fillet(min(t, col.tf)), st.w_gc, "in", "AISC Tabla J2.4")
    # ---------------------------------------------------------------- efectos locales
    kb = beam.kdes if beam.kdes > 0 else beam.tf + 0.5
    kc = col.kdes if col.kdes > 0 else col.tf + 0.5
    add_check(ck, rec, "lb_wy", "Viga — fluencia local del alma bajo V_b (J10.2)", Vb, PHI_YIELD * web_local_yielding(bm.Fy, beam.tw, kb, Lb), "kip", "AISC J10.2")
    add_check(ck, rec, "lb_wc", "Viga — aplastamiento del alma bajo V_b (J10.3)", 0.0 if tens else Vb, 0.75 * web_crippling(bm.Fy, beam.tw, beam.tf, beam.d, Lb), "kip", "AISC J10.3",
              "solo compresion del arriostramiento")
    if Lb > 0.15 * beam.bf:
        add_check(ck, rec, "lb_fb", "Viga — flexion local del ala bajo V_b traccionante (J10.1)", Vb if tens else 0.0, 0.9 * flange_local_bending(bm.Fy, beam.tf), "kip", "AISC J10.1",
                  "solo traccion del arriostramiento")
    add_check(ck, rec, "lc_wy", "Columna — fluencia local del alma bajo H_c (J10.2)", Hc, PHI_YIELD * web_local_yielding(cm.Fy, col.tw, kc, Lc), "kip", "AISC J10.2")
    add_check(ck, rec, "lc_wc", "Columna — aplastamiento del alma bajo H_c (J10.3)", 0.0 if tens else Hc, 0.75 * web_crippling(cm.Fy, col.tw, col.tf, col.d, Lc), "kip", "AISC J10.3",
              "solo compresion del arriostramiento")
    if Lc > 0.15 * col.bf:
        add_check(ck, rec, "lc_fb", "Columna — flexion local del ala bajo H_c traccionante (J10.1)", Hc if tens else 0.0, 0.9 * flange_local_bending(cm.Fy, col.tf), "kip", "AISC J10.1",
                  "solo traccion del arriostramiento")
    not_evaluated(ck, "gu_member", "Arriostramiento como miembro, borde libre de la cartela y conexion viga-columna", "Manual Parte 13",
                  "Verifiquelos aparte: la conexion viga-columna debe resistir las fuerzas de interfaz de la cartela.")
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.gus, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "gus"
TAB = "Cartela"
PREFIX = "CA"
TITLE = "CARTELA DE ARRIOSTRAMIENTO (WHITMORE Y UFM)"
NORMS = "AISC 360-22 (cap. D, E, J) · AISC Steel Construction Manual 15a Ed., Partes 9 y 13"
LOADS = [("P", "F")]
LOADS_NOTE = "Cada fila es una combinacion con la fuerza axial P del arriostramiento (positiva = traccion; negativa = compresion)."
_bolted = lambda p: p.gus.conn == GUS_CONN[0]
FORM = [
    G("Viga y columna"),
    combo("Viga", "gus.beam", "@I", editable=True),
    combo("Acero de la viga", "gus.beam_steel", "@steel_shape"),
    combo("Columna", "gus.col", "@I", editable=True),
    combo("Acero de la columna", "gus.col_steel", "@steel_shape"),
    G("Arriostramiento"),
    num("Angulo con la vertical", "gus.theta", 5, 85, step=1.0, dec=1, suffix="°", help="Medido desde la VERTICAL (45° = diagonal a 45°)."),
    num("Distancia del punto de trabajo a la primera fila (D1)", "gus.D1", 1, 100, uk="L", help="Sobre el eje del arriostramiento, desde la interseccion de las lineas de centro de viga y columna."),
    combo("Union", "gus.conn", GUS_CONN),
    G("Cartela"),
    num("Espesor", "gus.t", 0.125, 3, uk="L"),
    combo("Acero", "gus.steel", "@steel_plate"),
    num("Separacion transversal g (entre lineas de pernos o de soldadura)", "gus.g_t", 0.5, 20, uk="L", help="Ancho del grupo de union del arriostramiento: entre las lineas extremas de pernos o de soldadura."),
    num("Largo soldado a la viga  L_b", "gus.L_b", 4, 120, uk="L"),
    num("Largo soldado a la columna  L_c (0 = el del UFM)", "gus.L_c", 0, 120, uk="L", help="0: el programa toma el largo que cumple la condicion del UFM sin momentos. Si lo fija, no debe apartarse mas de 10 %."),
    num("Filete cartela-viga", "gus.w_gb", 0.0625, 1, uk="L"),
    num("Filete cartela-columna", "gus.w_gc", 0.0625, 1, uk="L"),
    combo("Electrodo", "gus.electrode", "@electrode"),
    check("Incremento direccional (AISC J2-5)", "gus.weld_dir"),
    num("Longitud de pandeo L_avg (0 = automatica)", "gus.L_avg", 0, 100, uk="L", help="Longitud de Thornton (promedio de L1, L2, L3). Automatica: L2 (de la primera fila al borde de la cartela sobre el eje), con L1 = L3 = L2."),
    G("Pernos del arriostramiento", show=_bolted),
    combo("Diametro", "gus.bolt_size", SHEAR_BOLT_SIZES, show=_bolted),
    combo("Calidad", "gus.bolt_grade", BOLT_GRADES, show=_bolted),
    intf("Filas a lo largo del eje", "gus.n_rows", 1, 12, show=_bolted),
    intf("Lineas transversales", "gus.n_lines", 1, 6, show=_bolted),
    num("Separacion a lo largo  s", "gus.s", 0.5, 12, uk="L", show=_bolted),
    intf("Planos de corte", "gus.m_planes", 1, 2, help="2 si la cartela queda entre dos angulos o placas.", show=_bolted),
    num("Excentricidad del arriostramiento  e", "gus.e_b", 0, 20, uk="L", show=_bolted),
    num("Espesor total del arriostramiento en apoyo", "gus.t_br", 0.1, 6, uk="L", show=_bolted),
    num("Fu del arriostramiento", "gus.Fu_br", 30, 150, uk="S", show=_bolted),
    num("Extremo del arriostramiento a la primera fila", "gus.Le", 0.5, 8, uk="L", show=_bolted),
    num("De la ultima fila al borde libre de la cartela", "gus.lg_end", 0.5, 8, uk="L", show=_bolted),
    G("Soldadura del arriostramiento", show=lambda p: not _bolted(p)),
    intf("Lineas de soldadura (2 o 4)", "gus.nlw", 2, 4, show=lambda p: not _bolted(p)),
    num("Largo de cada linea", "gus.Lw", 1, 60, uk="L", show=lambda p: not _bolted(p)),
    num("Cateto del filete", "gus.w_br", 0.0625, 1, uk="L", show=lambda p: not _bolted(p)),
    N("UFM caso sin momentos. NO se verifican el arriostramiento como miembro, el borde libre de la cartela ni la conexion viga-columna."),
]


def label(prj) -> str:
    st = prj.gus
    return f"cartela {st.beam} / {st.col}  (θ = {st.theta:g}°, t = {st.t:g} in)"


def input_rows(prj, us) -> list:
    st = prj.gus
    g = geometry(st)
    rows = [("Viga / columna", f"{st.beam} ({st.beam_steel}) / {st.col} ({st.col_steel}); θ = {st.theta:g}° desde la vertical"),
            ("Cartela", f"t = {us.q('L', st.t)} ({st.steel}); L_b = {us.q('L', st.L_b)}, L_c = {us.q('L', g.get('Lc', st.L_c))}"
                        + (" (UFM)" if st.L_c <= 0 else "")),
            ("Soldaduras de la cartela", f"viga: filete {us.q('L', st.w_gb)}; columna: filete {us.q('L', st.w_gc)} ({st.electrode}), a ambos lados"),
            ("Arriostramiento", (f"{st.n_rows}×{st.n_lines} pernos Ø{st.bolt_size} in {st.bolt_grade}, {st.m_planes} plano(s); s = {us.q('L', st.s)}, g = {us.q('L', st.g_t)}, e = {us.q('L', st.e_b)}"
                                 if g["bolted"] else f"{st.nlw} lineas de filete {us.q('L', st.w_br)} × {us.q('L', st.Lw)}")),
            ("Cargas (LRFD)", "; ".join(f"{n}: P = {us.q('F', v[0])}" for n, v in st.loads()))]
    return rows


def draw(fig, prj):
    from . import drawing as D
    from matplotlib.patches import Rectangle, Polygon, Circle
    st = prj.gus
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    ax = fig.add_subplot(111)
    D.blank(ax)
    if beam is None or col is None or "Lc" not in g or g["Lc"] <= 0:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    ec, eb, th = g["ec"], g["eb"], g["th"]
    Lb, Lc = st.L_b, g["Lc"]
    ux, uy = math.sin(th), math.cos(th)                       # eje del arriostramiento
    nx, ny = math.cos(th), -math.sin(th)                      # normal
    Lc_ = g["Lconn"]
    s_end = st.D1 + Lc_ + (st.lg_end if g["bolted"] else 1.5)
    wend = max(g["Ww"], g["bg"] + 3.0) / 2 + 0.5
    ex, ey = s_end * ux, s_end * uy
    # columna y viga
    ytop = eb + max(Lc, 8.0) + 8.0
    ax.add_patch(Rectangle((-ec, -eb - 6), 2 * ec, ytop + eb + 6, fc=D.C_SUP, ec="#555555", lw=0.8, hatch="////", zorder=1))
    ax.add_patch(Rectangle((ec, -eb), Lb + 14, 2 * eb, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    # cartela
    poly = [(ec, eb), (ec + Lb, eb), (ex + wend * nx, ey + wend * ny), (ex - wend * nx, ey - wend * ny), (ec, eb + Lc)]
    ax.add_patch(Polygon(poly, closed=True, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.3, alpha=0.7, zorder=4))
    ax.plot([ec, ec + Lb], [eb, eb], color=D.C_WELD, lw=3.0, zorder=5)
    ax.plot([ec, ec], [eb, eb + Lc], color=D.C_WELD, lw=3.0, zorder=5)
    # punto de trabajo y eje
    ax.plot([0], [0], marker="o", color="#000000", ms=4, zorder=7)
    ax.plot([0, ex * 1.25], [0, ey * 1.25], color="#555555", lw=0.8, ls=(0, (8, 4)), zorder=3)
    # fijaciones y Whitmore
    if g["bolted"]:
        for i in range(st.n_rows):
            for j in range(st.n_lines):
                s_ = st.D1 + i * st.s
                tt = (j - (st.n_lines - 1) / 2) * st.g_t
                D.bolt(ax, s_ * ux + tt * nx, s_ * uy + tt * ny, g["dh"])
    else:
        for j in range(st.nlw // 2):
            tt = (j - (st.nlw // 2 - 1) / 2) * st.g_t if st.nlw > 2 else st.g_t / 2
            for sg in (1, -1):
                ax.plot([st.D1 * ux + sg * tt * nx, (st.D1 + st.Lw) * ux + sg * tt * nx], [st.D1 * uy + sg * tt * ny, (st.D1 + st.Lw) * uy + sg * tt * ny], color=D.C_WELD, lw=2.4, zorder=6)
    wa = g["bg"] / 2
    for sg in (1, -1):
        xs = [st.D1 * ux + sg * wa * nx, (st.D1 + Lc_) * ux + sg * (wa + Lc_ * T30) * nx]
        ys = [st.D1 * uy + sg * wa * ny, (st.D1 + Lc_) * uy + sg * (wa + Lc_ * T30) * ny]
        ax.plot(xs, ys, color="#2e7d32", lw=1.0, ls=(0, (4, 3)), zorder=6)
    ax.text(ex * 1.25 + 0.8, ey * 1.25, f"θ = {st.theta:g}° (desde la vertical)", fontsize=8, color="#444444")
    D._dim(ax, (ec, -eb), (ec + Lb, -eb), -2.4, f"L_b = {q(Lb)}")
    D._dim(ax, (-ec, eb), (-ec, eb + Lc), -3.0, f"L_c = {q(Lc)}", horizontal=False)
    ax.text(ec + Lb + 1.5, -eb - 4.5, f"UFM:  H_b = {g['Hb']:.3f}P  V_b = {g['Vb']:.3f}P\n          H_c = {g['Hc']:.3f}P  V_c = {g['Vc']:.3f}P   (r = {q(g['r'])})", fontsize=7.2, color="#444444", va="top")
    ax.text(ec + Lb + 1.5, -eb - 9.5, "Verde: seccion de Whitmore (30°)", fontsize=7.2, color="#2e7d32", va="top")
    ax.set_xlim(-ec - 7, max(ec + Lb + 16, ex + 8))
    ax.set_ylim(-eb - 11, max(ytop, ey + 6))
    ax.set_title(f"Cartela de arriostramiento — {st.beam} / {st.col}", fontsize=9)
