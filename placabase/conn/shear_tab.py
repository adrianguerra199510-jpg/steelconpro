# -*- coding: utf-8 -*-
"""Conexion de corte con placa simple (shear tab): viga apoyada -> viga maestra o columna.

Cubre la viga secundaria apoyada en el alma de la viga maestra (con cope superior y/o inferior) y la viga
apoyada en el alma o el ala de una columna.  Configuracion: una fila vertical de 2 a 12 pernos en agujeros
estandar, placa soldada al soporte con filete a ambos lados, carga = reaccion vertical de la viga.

Verificaciones (AISC 360-22 y Manual 15a Ed., Parte 10), todo LRFD:
  pernos (centro instantaneo, J3.6) · aplastamiento/desgarramiento en placa y alma (J3.10) ·
  placa: fluencia y rotura por cortante (J4.2), bloque de cortante (J4.3), flexion y V-M (F, Parte 10) ·
  soldadura placa-soporte (J2.4) y metal base del soporte · alma de la viga: cortante, bloque de cortante
  y flexion en el cope · distancias minimas (J3.3, J3.4, J2.4).

NO se evalua el pandeo local del alma por cope (Manual Parte 9): la 15a Ed. cambio el procedimiento y no
se pudo consultar; se informa como "NO EVALUADO".  Tampoco: carga axial, ranuras, pernos de deslizamiento
critico, configuraciones extendidas (a > 3.5 in), flexion local del ala de la columna ni rigidez del soporte.
"""
from __future__ import annotations
import math

from .. import materials as M
from ..design import Check
from ..explain import Recorder
from ..shapes import CATALOG, W_SHAPE
from .base import run_combos, add_check
from . import beamend
from .formspec import G, N, num, intf, combo, check
from .common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, PHI_FLEX, FNV, bolt_db, hole_std, hole_net, edge_min,
                     bolt_shear_rn, bearing_rn, block_shear_rn, ic_vertical_line, weld_pair_vertical,
                     coped_section, net_flexure_plate)
from .specs import CT_SHEAR_TAB, SUP_KINDS, BOLT_GRADES, SHEAR_BOLT_SIZES

NAME = CT_SHEAR_TAB
E_STEEL = 29000.0


def geometry(st):
    """Geometria derivada (in).  Coordenadas verticales desde el tope de la viga, hacia abajo."""
    beam = CATALOG.get(st.beam)
    sup = CATALOG.get(st.sup_label)
    db = bolt_db(st.bolt_size)
    n = max(int(st.n), 1)
    Lb = (n - 1) * st.s
    g = dict(beam=beam, sup=sup, db=db, dh=hole_std(db), dhn=hole_net(db), n=n, Lb=Lb, Lp=Lb + 2 * st.lev_p)
    g.update(beamend.geometry(beam, n, st.s, st.a, st.gap, st.y_top, st.cope_top, st.cope_bot, st.cope_len))
    return g


def _t_support(st, sup):
    if sup is None:
        return 0.0
    return sup.tf if st.sup_kind == SUP_KINDS[2] else sup.tw


def check_input(st) -> list:
    """Avisos de datos. Los que empiezan con '**' invalidan el veredicto."""
    g = geometry(st)
    w = []
    if g["beam"] is None:
        w.append(f"** Perfil de la viga apoyada '{st.beam}' no encontrado en el catalogo. **")
        return w
    beam, sup = g["beam"], g["sup"]
    if sup is None:
        w.append(f"** Perfil del soporte '{st.sup_label}' no encontrado en el catalogo. **")
    if beam.kind != W_SHAPE:
        w.append("** La viga apoyada debe ser un perfil I (W, M, S, HP): el alma y las alas se toman de ahi. **")
    if st.bolt_grade not in FNV:
        w.append(f"** Calidad de perno '{st.bolt_grade}' no reconocida. **")
    if not (2 <= st.n <= 12):
        w.append(f"** {st.n} pernos: la configuracion convencional admite de 2 a 12 en una fila (Manual, "
                 "Tabla 10-9); con 1 perno no hay resistencia al momento de excentricidad. **")
    if st.a > 3.5 + 1e-9:
        w.append(f"** a = {st.a:g} in > 3.5 in: configuracion EXTENDIDA. Este modulo solo cubre la convencional "
                 "(no verifica pandeo de la placa ni torsion del soporte). **")
    if g["coped"] and st.cope_len <= 0:
        w.append("** Hay cope con longitud 0: indique la longitud del cope. **")
    if g["h0"] <= 0 or g["lev_t"] < -1e-9 or g["lev_b"] < -1e-9:
        w.append("** Los pernos no caben en el alma que queda: revise y_top, el numero de pernos, la separacion o el cope. **")
    if not g["coped"] and beam.kdes > 0 and (g["lev_t"] < beam.kdes or g["lev_b"] < beam.kdes):
        w.append("** Hay pernos dentro de la zona del filete alma-ala (k): suba/baje el grupo o use cope. **")
    if g["coped"] and g["ct"] > 0 and g["ct"] < beam.tf - 1e-9:
        w.append("** El cope superior es menor que el espesor del ala: el ala no queda eliminada. **")
    if st.tp > 0.5 * g["db"] + 0.0625 + 1e-9:
        w.append(f"tp = {st.tp:g} in > db/2 + 1/16: la ductilidad de rotacion de la configuracion convencional "
                 "(Tabla 10-9) pide placa mas delgada.")
    if st.leh_p < 2 * g["db"] - 1e-9:
        w.append("Distancia horizontal al borde de la placa menor que 2·db (Tabla 10-9, configuracion convencional).")
    if st.weld_size < 0.625 * st.tp - 1e-9:
        w.append(f"Filete de {st.weld_size:g} in < 5/8·tp ({0.625 * st.tp:.3f} in): la practica del Manual para que "
                 "la soldadura no gobierne antes que la placa (ductilidad). Se verifica por resistencia igualmente.")
    w += beamend.cope_warnings(st.gap, st.cope_len, st.top_flush, g, beam, sup, st.sup_kind == SUP_KINDS[0])
    if beam.tw > 0 and beam.d > 0:
        hw = (beam.d - 2 * beam.kdes) / beam.tw if beam.kdes else beam.d / beam.tw
        Fy = M.find(M.SHAPE_STEELS, st.beam_steel).Fy
        if hw > 2.24 * math.sqrt(E_STEEL / Fy):
            w.append("h/tw del alma mayor que 2.24·√(E/Fy): la fluencia por cortante con φ = 1.00 y Cv = 1 (G2.1a) "
                     "no aplica; use el calculo de G2.1(b).")
    if st.leh_p <= 0 or st.lev_p <= 0 or st.a <= st.gap:
        w.append("** a debe ser mayor que el retranqueo y las distancias al borde de la placa positivas. **")
    return w


_chk = add_check


def solve_one(prj, name: str, vals, rec: Recorder | None):
    """Verificaciones de una combinacion (vals = (Vu,)). Devuelve la lista de Check."""
    Vu = vals[0]
    st = prj.stab
    g = geometry(st)
    ck: list[Check] = []
    if g["beam"] is None or g["sup"] is None:
        return ck
    beam, sup = g["beam"], g["sup"]
    u = prj.units()
    db, dh, dhn, n, Lp, Lb = g["db"], g["dh"], g["dhn"], g["n"], g["Lp"], g["Lb"]
    if n < 2 or st.s <= 0:
        return ck
    pl = M.find(M.PLATE_STEELS, st.plate_steel, 1)
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    sp = M.find(M.SHAPE_STEELS, st.sup_steel)
    FEXX = M.find(M.ELECTRODES, st.electrode, 1).FEXX
    tp, tw, a = st.tp, beam.tw, st.a
    ys = [((n - 1) / 2.0 - i) * st.s for i in range(n)]            # y hacia arriba, i = 0 es el perno superior

    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Viga apoyada", st.beam, f"{st.beam_steel}: Fy = {rec.f('S', bm.Fy)}, Fu = {rec.f('S', bm.Fu)};  d = {rec.f('L', beam.d)}, "
                f"tw = {rec.f('L', tw)}, tf = {rec.f('L', beam.tf)}", None)
        rec.add("Soporte", f"{st.sup_label} — {st.sup_kind}", f"{st.sup_steel}: Fy = {rec.f('S', sp.Fy)}, Fu = {rec.f('S', sp.Fu)}", None)
        rec.add("Placa", f"{rec.n('L', Lp)} × {rec.n('L', a + st.leh_p)} × {rec.n('L', tp)} {u.L}",
                f"{st.plate_steel}: Fy = {rec.f('S', pl.Fy)}, Fu = {rec.f('S', pl.Fu)}", None)
        rec.add("Pernos", f"{n} × Ø{st.bolt_size} in {st.bolt_grade}",
                f"s = {rec.f('L', st.s)}, a = {rec.f('L', a)}, agujero estandar {rec.f('L', dh)}", None)
        rec.add("Vu", "reaccion factorizada de la viga", "", Vu, "F")
        rec.section("GEOMETRIA")
        rec.add("Lp", "(n−1)·s + 2·lev,p", f"{rec.n('L', Lb)} + 2·{rec.n('L', st.lev_p)}", Lp, "L")
        rec.add("leh,b", "a − retranqueo", f"{rec.n('L', a)} − {rec.n('L', st.gap)}", g["leh_b"], "L",
                note="distancia del extremo de la viga a la fila de pernos")
        if g["coped"]:
            rec.add("h0", "d − cope sup. − cope inf.", f"{rec.n('L', beam.d)} − {rec.n('L', g['ct'])} − {rec.n('L', g['cb'])}",
                    g["h0"], "L", note="alma que queda en el extremo")
            rec.add("lev,t", "borde superior del alma al perno superior", "", g["lev_t"], "L")
            rec.add("e,cope", "max(0, retranqueo + c − a)", f"{rec.n('L', st.gap)} + {rec.n('L', st.cope_len)} − {rec.n('L', a)}",
                    g["e_cope"], "L", note="brazo del momento en el fin del cope")

    # ------------------------------------------------------------- distancias
    sp_min = 8.0 / 3.0 * db
    _chk(ck, rec, "geo_s", "Separacion entre pernos  s ≥ 2-2/3·db", sp_min, st.s, "in", "AISC J3.3",
         "3·db es lo preferible")
    _chk(ck, rec, "geo_lev_p", "Distancia vertical al borde de la placa", edge_min(db), st.lev_p, "in", "AISC Tabla J3.4")
    _chk(ck, rec, "geo_leh_p", "Distancia horizontal al borde de la placa", edge_min(db), st.leh_p, "in", "AISC Tabla J3.4")
    _chk(ck, rec, "geo_leh_b", "Distancia del extremo de la viga a los pernos", edge_min(db), g["leh_b"], "in", "AISC Tabla J3.4")
    if g["ct"] > 0:
        _chk(ck, rec, "geo_lev_b", "Distancia del cope superior al perno superior", edge_min(db), g["lev_t"], "in",
             "AISC Tabla J3.4")

    # ---------------------------------------------------------------- pernos
    ic = ic_vertical_line(ys, a)
    rn = bolt_shear_rn(db, st.bolt_grade)
    phi_rn = PHI_BOLT * rn
    cap_b = phi_rn * ic.C
    k = Vu / ic.C if ic.C > 0 else 0.0                              # fuerza real = f_i · Vu / C
    Fx = [fx * k for fx in ic.fx]
    Fy = [fy * k for fy in ic.fy]
    if rec:
        rec.section("PERNOS — metodo del centro instantaneo")
        rec.add("rn", "Fnv·Ab", f"{rec.f('S', FNV[st.bolt_grade])} · {rec.f('A', math.pi * db ** 2 / 4)}", rn, "F", "AISC J3.6")
        rec.add("φrn", "0.75·rn", "", phi_rn, "F")
        rec.add("C", "coeficiente del grupo (centro instantaneo)",
                f"e = a = {rec.f('L', a)};  n = {n};  s = {rec.f('L', st.s)};  CI a {rec.f('L', ic.x_ic)} del centroide",
                ic.C, "-", "Manual Parte 7 (Crawford-Kulak, Δmax = 0.34 in)",
                note=f"el metodo elastico daria C = {ic.C_elastic:.3f} (conservador)")
    _chk(ck, rec, "bolt_shear", f"Pernos — cortante con excentricidad (IC, C = {ic.C:.2f})", Vu, cap_b, "kip", "AISC J3.6",
         f"{n} × Ø{st.bolt_size} {st.bolt_grade}; φ·C·rn")

    def bearing_row(label, key, t, Fu, Lc_v, Lc_h_edge_bolts, ref):
        """Aplastamiento por perno: la componente vertical y la horizontal se combinan en elipse.
        `Lc_v(i)`: distancia libre en la direccion en que el perno empuja; `Lc_h_edge_bolts`: indices de los pernos
        cuya componente horizontal empuja hacia un borde libre (el resto empuja hacia material continuo)."""
        worst, wi = 0.0, 0
        for i in range(n):
            rv = PHI_BOLT * bearing_rn(db, t, Fu, Lc_v(i))
            Lh = (Lc_h_edge_bolts[i] if i in Lc_h_edge_bolts else 1e9)
            rh = PHI_BOLT * bearing_rn(db, t, Fu, Lh)
            r = math.hypot(abs(Fy[i]) / rv, abs(Fx[i]) / rh) if rv > 0 and rh > 0 else 99.0
            if r > worst:
                worst, wi = r, i
        F = math.hypot(Fx[wi], Fy[wi])
        _chk(ck, rec, key, label, F, F / worst if worst > 0 else 0.0, "kip", ref,
             f"perno #{wi + 1} (desde arriba): {math.hypot(Fx[wi], Fy[wi]):.1f} kip")
        return worst

    # placa: empujada hacia abajo; la componente horizontal empuja hacia el borde libre en los pernos de abajo
    lev_pl = st.lev_p - dh / 2
    bearing_row("Pernos — aplastamiento y desgarramiento en la placa", "brg_plate", tp, pl.Fu,
                lambda i: (lev_pl if i == n - 1 else st.s - dh),
                {i: st.leh_p - dh / 2 for i in range(n) if ys[i] < -1e-9}, "AISC J3.10")
    # alma: empujada hacia arriba; hacia el extremo de la viga empujan los pernos de abajo
    lev_web_t = (g["lev_t"] - dh / 2) if g["ct"] > 0 else 1e9
    bearing_row("Pernos — aplastamiento y desgarramiento en el alma de la viga", "brg_web", tw, bm.Fu,
                lambda i: (lev_web_t if i == 0 else st.s - dh),
                {i: g["leh_b"] - dh / 2 for i in range(n) if ys[i] < -1e-9}, "AISC J3.10")

    # ----------------------------------------------------------------- placa
    Agv = tp * Lp
    Anv = tp * (Lp - n * dhn)
    Rvy = PHI_YIELD * 0.6 * pl.Fy * Agv
    Rvr = PHI_RUPT * 0.6 * pl.Fu * Anv
    if rec:
        rec.section("PLACA")
        rec.add("φRn,fl", "1.00·0.6·Fy·Agv", f"0.6·{rec.n('S', pl.Fy)}·{rec.n('L', tp)}·{rec.n('L', Lp)}", Rvy, "F", "AISC J4.2(a)")
        rec.add("φRn,rot", "0.75·0.6·Fu·Anv", f"0.6·{rec.n('S', pl.Fu)}·{rec.n('L', tp)}·({rec.n('L', Lp)} − {n}·{rec.n('L', dhn)})",
                Rvr, "F", "AISC J4.2(b)")
    _chk(ck, rec, "plate_vy", "Placa — fluencia por cortante", Vu, Rvy, "kip", "AISC J4.2(a)")
    _chk(ck, rec, "plate_vr", "Placa — rotura por cortante neto", Vu, Rvr, "kip", "AISC J4.2(b)")
    Lgv = st.lev_p + (n - 1) * st.s
    Lnv = Lgv - (n - 0.5) * dhn
    Lnt = st.leh_p - 0.5 * dhn
    Rbs = PHI_RUPT * block_shear_rn(pl.Fy, pl.Fu, tp, Lgv, Lnv, Lnt)
    _chk(ck, rec, "plate_bs", "Placa — bloque de cortante", Vu, Rbs, "kip", "AISC J4.3",
         f"Lgv = {u.q('L', Lgv)}, Lnv = {u.q('L', Lnv)}, Lnt = {u.q('L', Lnt)}, Ubs = 1.0 (una fila)")
    Mu = Vu * a
    Z = tp * Lp ** 2 / 4.0
    phiMp = PHI_FLEX * pl.Fy * Z
    phiVp = PHI_YIELD * 0.6 * pl.Fy * Agv
    ratio_vm = Mu / max(phiMp, 1e-9) + (Vu / max(phiVp, 1e-9)) ** 2
    if rec:
        rec.add("Mu", "Vu·a  (en la soldadura)", f"{rec.n('F', Vu)}·{rec.n('L', a)}", Mu, "M", "Manual Parte 10")
        rec.add("φMp", "0.90·Fy·Z", f"0.9·{rec.n('S', pl.Fy)}·{Z / u.fl ** 3:.4g} {u.L}³", phiMp, "M", "AISC F11")
    _chk(ck, rec, "plate_m", "Placa — flexion (fluencia) en la soldadura", Mu, phiMp, "kip·in", "AISC F11 / Manual Parte 10")
    _chk(ck, rec, "plate_vm", "Placa — interaccion flexion-cortante (plastica)", ratio_vm, 1.0, "-",
         "Criterio del programa", "Mu/φMp + (Vu/φVp)² ≤ 1: forma conservadora para seccion rectangular")
    Sn, _I = net_flexure_plate(tp, Lp, ys, dhn)
    phiMr = PHI_RUPT * pl.Fu * Sn
    _chk(ck, rec, "plate_mr", "Placa — rotura por flexion en la seccion neta (fila de pernos)", Mu, phiMr, "kip·in",
         "Manual Parte 10", f"Snet = {Sn / u.fl ** 3:.4g} {u.L}³; M = Vu·a (conservador)")

    # ------------------------------------------------------------- soldadura
    f, cap_w, th, fv, fh = weld_pair_vertical(Vu, a, Lp, st.weld_size, FEXX, st.weld_dir)
    if rec:
        rec.section("SOLDADURA PLACA-SOPORTE (filete a ambos lados, metodo elastico)")
        rec.add("fv", "Vu / (2·L)", "", fv, "LF")
        rec.add("fh", "3·Vu·a / L²", "", fh, "LF")
        rec.add("θ", "atan(fh / fv)", f"{th:.1f}°", None, "-", note="angulo de la resultante respecto al eje de la soldadura")
    _chk(ck, rec, "weld", "Soldadura placa-soporte — filete a ambos lados", f, cap_w, "kip/in", "AISC J2.4",
         f"w = {M.float_to_frac(st.weld_size)}\", {st.electrode}, θ = {th:.0f}°"
         + (" (incremento direccional J2-5)" if st.weld_dir else ""))
    ts = _t_support(st, sup)
    cap_base = PHI_RUPT * 0.6 * sp.Fu * ts
    _chk(ck, rec, "weld_base", "Metal base del soporte (cortante en la cara soldada)", 2 * f, cap_base, "kip/in", "AISC J4.2",
         f"espesor del soporte {u.q('L', ts)} ({st.sup_kind.lower()}); equivale al espesor minimo del Manual Ec. 9-2")
    wmin = M.min_fillet(min(tp, ts)) if ts > 0 else M.min_fillet(tp)
    _chk(ck, rec, "weld_min", "Tamano minimo del filete", wmin, st.weld_size, "in", "AISC Tabla J2.4")
    _chk(ck, rec, "weld_max", "Tamano maximo del filete en el borde de la placa", st.weld_size, M.max_fillet(tp), "in", "AISC J2.2b")

    # ----------------------------------------------------------- viga apoyada
    beamend.web_checks(ck, rec, u, g, beam, bm, Vu, n, st.s, dhn)
    return ck


def solve(prj, detail: bool = True):
    """Calcula todas las combinaciones; el resultado devuelto es el de la que gobierna."""
    return run_combos(prj, prj.stab, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "stab"                     # campo de Project con los datos
TAB = "Conexion de corte"         # pestaña de entrada
PREFIX = "CC"
TITLE = "CONEXION DE CORTE CON PLACA SIMPLE"
NORMS = "AISC 360-22 (cap. J, F, G) · AISC Steel Construction Manual 15a Ed., Partes 7, 9 y 10"
LOADS = [("Vu", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con la reaccion vertical Vu de la viga (ya factorizada). El veredicto es el de "
              "la mas desfavorable. Sin carga axial en la viga.")

FORM = [
    G("Viga apoyada (secundaria)"),
    combo("Perfil", "stab.beam", "@I", editable=True, help="Perfil I de la viga que llega al soporte (W, M, S, HP). Puede escribirse: la lista se completa sola."),
    combo("Acero", "stab.beam_steel", "@steel_shape", help="Grado del acero de la viga: Fy y Fu para el alma (cortante, bloque de cortante, aplastamiento y cope)."),
    G("Soporte"),
    combo("Tipo de soporte", "stab.sup_kind", SUP_KINDS, help="Viga maestra (la placa se suelda a su alma), alma de columna o ala de columna. Define el espesor del metal base bajo el cordon y el dibujo."),
    combo("Perfil del soporte", "stab.sup_label", "@I", editable=True, help="Perfil de la viga maestra o de la columna."),
    combo("Acero del soporte", "stab.sup_steel", "@steel_shape", help="Fu del soporte para el cortante del metal base bajo la soldadura."),
    G("Pernos (una sola fila vertical, agujero estandar)"),
    combo("Diametro", "stab.bolt_size", SHEAR_BOLT_SIZES, help="Diametro nominal del perno, en pulgadas."),
    combo("Calidad", "stab.bolt_grade", BOLT_GRADES, help="A325/A490 con la rosca incluida (N) o excluida (X) del plano de corte (AISC Tabla J3.2). Solo cortante simple, tipo aplastamiento."),
    intf("Numero de pernos", "stab.n", 1, 14, help="La configuracion convencional admite de 2 a 12 pernos en una fila (Manual Tabla 10-9). Fuera de ese rango el resultado se marca como no valido."),
    num("Separacion vertical  s", "stab.s", 0.5, 12, uk="L", help="Entre centros de pernos. Minimo 2-2/3·db (AISC J3.3); 3·db es lo preferible."),
    num("Soldadura a fila de pernos  a", "stab.a", 0.5, 12, uk="L", help="Distancia de la linea de soldadura a la fila de pernos: es la excentricidad con la que se verifican los pernos y la soldadura. La configuracion convencional exige a ≤ 3.5 in; mas alla es una conexion extendida, que este modulo no cubre."),
    G("Placa"),
    num("Espesor  tp", "stab.tp", 0.1, 3, uk="L", help="Espesor de la placa. Para la ductilidad de rotacion de la configuracion convencional conviene tp ≤ db/2 + 1/16 in (aviso)."),
    combo("Acero de la placa", "stab.plate_steel", "@steel_plate", help="Grado del acero de la placa."),
    num("Distancia vertical al borde", "stab.lev_p", 0.25, 6, uk="L", help="Del centro del perno extremo al borde superior o inferior de la placa. La altura de la placa sale de (n−1)·s + 2·lev."),
    num("Distancia horizontal al borde libre", "stab.leh_p", 0.25, 6, uk="L", help="Del centro de la fila de pernos al borde libre de la placa. La Tabla 10-9 pide al menos 2·db (aviso)."),
    G("Posicion respecto a la viga"),
    num("Retranqueo del extremo de la viga", "stab.gap", 0, 3, uk="L", help="Separacion entre el extremo de la viga y la cara del soporte (usual 1/2 in). La distancia del extremo a los pernos resulta a − retranqueo."),
    num("Del tope de la viga al perno superior", "stab.y_top", -1, 60, uk="L", help="Negativo = automatico: el grupo de pernos se centra en el alma que queda (descontando los copes)."),
    G("Cope (despatinado) de la viga apoyada"),
    num("Cope superior: profundidad", "stab.cope_top", 0, 30, uk="L", help="Profundidad que se corta desde el tope de la viga (0 = sin cope). Debe pasar del espesor del ala. Con cope se verifican el bloque de cortante del alma y la flexion de la seccion con cope."),
    num("Cope inferior: profundidad", "stab.cope_bot", 0, 30, uk="L", help="Profundidad que se corta desde el fondo de la viga (0 = sin cope), por ejemplo cuando las vigas quedan a ras por abajo."),
    num("Cope: longitud desde el extremo", "stab.cope_len", 0, 40, uk="L", help="Longitud del cope medida desde el extremo de la viga. Es el brazo del momento en la seccion con cope: retranqueo + longitud − a."),
    check("Tope de la viga a ras con el de la maestra", "stab.top_flush", help="Solo informativo: el programa avisa si el cope no alcanza para librar el ala de la viga maestra (supone 1/2 in de holgura)."),
    N("NO se evalua el pandeo local del alma por cope (Manual AISC Parte 9; la 15a Ed. cambio el procedimiento): el programa lo avisa. Verifiquelo aparte."),
    G("Soldadura placa-soporte"),
    num("Cateto del filete (ambos lados)", "stab.weld_size", 0.0625, 1, uk="L", help="Filete a ambos lados de la placa, en toda su altura. Metodo elastico para la excentricidad (conservador). La practica del Manual es 5/8·tp."),
    combo("Electrodo", "stab.electrode", "@electrode", help="FEXX del metal de aporte."),
    check("Incremento direccional de resistencia (AISC J2-5)", "stab.weld_dir", help="Aplica 1 + 0.5·sen^1.5(θ) con θ el angulo de la resultante respecto al eje de la soldadura."),
]


def label(prj) -> str:
    st = prj.stab
    return f"{st.beam} → {st.sup_label}  ({st.n}×Ø{st.bolt_size})"


def input_rows(prj, us) -> list:
    """Filas (concepto, descripcion) de los datos de entrada para los reportes."""
    st = prj.stab
    g = geometry(st)
    b = g["beam"]
    rows = [
        ("Viga apoyada", f"{st.beam} ({st.beam_steel})" + (f" — d = {us.q('L', b.d)}, tw = {us.q('L', b.tw)}" if b else "")),
        ("Soporte", f"{st.sup_label} ({st.sup_steel}) — {st.sup_kind}"),
        ("Pernos", f"{st.n} Ø{st.bolt_size} in {st.bolt_grade}, agujero estandar; s = {us.q('L', st.s)}, a = {us.q('L', st.a)}"),
        ("Placa", f"{us.q('L', g['Lp'])} × {us.q('L', st.a + st.leh_p)} × {us.q('L', st.tp)} — {st.plate_steel}; "
                  f"lev = {us.q('L', st.lev_p)}, leh = {us.q('L', st.leh_p)}"),
        ("Soldadura", f"filete {us.q('L', st.weld_size)} {st.electrode} a ambos lados"
                      + (", con incremento direccional" if st.weld_dir else "")),
        ("Retranqueo", f"{us.q('L', st.gap)} del extremo de la viga a la cara del soporte"),
    ]
    if g["coped"]:
        rows.append(("Cope", f"superior {us.q('L', g['ct'])}, inferior {us.q('L', g['cb'])}, longitud {us.q('L', st.cope_len)}"))
    rows.append(("Cargas (LRFD)", "; ".join(f"{n}: Vu = {us.q('F', v[0])}" for n, v in st.loads())))
    return rows


def draw(fig, prj):
    """Elevacion y planta con cotas."""
    from . import draw_conn
    gs = fig.add_gridspec(2, 1, height_ratios=[1.5, 1])
    draw_conn.elevation(fig.add_subplot(gs[0]), prj)
    draw_conn.plan(fig.add_subplot(gs[1]), prj)
