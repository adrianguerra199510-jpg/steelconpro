# -*- coding: utf-8 -*-
"""Placa extrema a momento (a ras o extendida): viga soldada a una placa que se atornilla al ala de la columna.

Cada fila de pernos (2 pernos) se trata como una T equivalente con efecto palanca (AISC Manual Parte 9, LRFD; ver
common.prying_available): la placa es el ala de la T y el ala de la viga, el alma.  El momento resistente es
    Mcap = 2·Σ T_i·h_i       (h_i = brazo de la fila i respecto al centroide del ala comprimida)
suponiendo que las filas traccionadas alcanzan su capacidad (como el metodo de DG4).  El cortante lo toman los pernos del lado comprimido.
IMPORTANTE: NO es el procedimiento de lineas de fluencia de AISC DG4 (Murray y Sumner), que no se pudo consultar: el modelo de T equivalente
independiente por fila es una aproximacion conservadora que puede diferir de DG4.  No se incluyen rigidizadores de placa (4ES, 8ES).
Lado de la columna: flexion local del ala (J10.1), fluencia del alma (J10.2), aplastamiento del alma (J10.3) y zona del panel (J10.6a);
con placas de continuidad se omiten las tres primeras.  NO se evalua la flexion del ala de la columna por lineas de fluencia (DG4).
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from ..units import float_to_frac
from .base import run_combos, add_check, not_evaluated
from .common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, FNV, FNT, bolt_db, hole_std, hole_net, edge_min, bolt_shear_rn,
                     bolt_tension_rn, bearing_rn, prying_available, flange_local_bending, web_local_yielding,
                     web_crippling, panel_zone_shear)
from .formspec import G, N, num, intf, combo, check
from .specs import CT_ENDPLATE, BOLT_GRADES, SHEAR_BOLT_SIZES, EP_FLANGE_WELD

NAME = CT_ENDPLATE


def geometry(st):
    beam, col = CATALOG.get(st.beam), CATALOG.get(st.col)
    db = bolt_db(st.bolt_size)
    g = dict(beam=beam, col=col, db=db, dh=hole_std(db), dhn=hole_net(db),
             fillet=st.fw_type == EP_FLANGE_WELD[1])
    if beam is not None:
        g["hf"] = beam.d - beam.tf
    return g


def _rows(st, g, ext):
    """Filas de pernos de un lado, medidas desde el centro de la viga hacia ese lado: [(nombre, y, b, a)]."""
    beam, wf = g["beam"], (st.fw_size if g["fillet"] else 0.0)
    out = [("interior", beam.d / 2 - beam.tf - st.pfi, st.pfi - wf, 1.25 * (st.pfi - wf))]
    if ext:
        out.insert(0, ("exterior", beam.d / 2 + st.pfo, st.pfo - wf, st.e_ext))
    return out


def check_input(st) -> list:
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    w = []
    if beam is None or beam.kind != "W":
        return [f"** La viga '{st.beam}' debe ser un perfil I del catalogo. **"]
    if col is None or col.kind != "W":
        return [f"** La columna '{st.col}' debe ser un perfil I del catalogo. **"]
    if st.bolt_grade not in FNV:
        w.append(f"** Calidad de perno '{st.bolt_grade}' no reconocida. **")
    db = g["db"]
    if st.bp <= 0 or st.tp <= 0 or st.g <= 0:
        w.append("** El ancho, el espesor de la placa y el gramil deben ser positivos. **")
    if (st.bp - st.g) / 2 < edge_min(db) - 1e-9:
        w.append("** La distancia de los pernos al borde lateral de la placa es menor que la minima de J3.4. **")
    if (col.bf - st.g) / 2 < edge_min(db) - 1e-9:
        w.append("** Los pernos no caben en el ancho del ala de la columna. **")
    if st.pfi - (st.fw_size if g["fillet"] else 0.0) <= db / 2 or st.pfo - (st.fw_size if g["fillet"] else 0.0) <= db / 2:
        w.append("** pfi / pfo demasiado pequenos: el perno choca con el ala o con la soldadura. **")
    if st.bp < beam.bf - 1e-9:
        w.append(f"La placa ({st.bp:g} in) es mas angosta que el ala de la viga ({beam.bf:g} in).")
    if st.g < beam.tw + 2 * db:
        w.append("El gramil es muy chico para pasar los pernos junto al alma de la viga.")
    w.append("Aproximacion: T equivalente con efecto palanca por fila (Manual Parte 9), no las lineas de fluencia de DG4; sin rigidizadores de placa.")
    w.append("NO EVALUADO: flexion del ala de la columna por lineas de fluencia (DG4) ni su rigidizacion; verifiquelo aparte.")
    return w


def solve_one(prj, name, vals, rec):
    Mu0, Vu = vals
    st = prj.epl
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    ck = []
    if beam is None or col is None or beam.kind != "W" or col.kind != "W" or st.bp <= 0 or st.tp <= 0:
        return ck
    u = prj.units()
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    cm = M.find(M.SHAPE_STEELS, st.col_steel)
    pm = M.find(M.PLATE_STEELS, st.plate_steel, 1)
    FEXX = M.find(M.ELECTRODES, st.electrode, 1).FEXX
    Mu = abs(Mu0)
    top = Mu0 >= 0
    d, tf, bf, tw = beam.d, beam.tf, beam.bf, beam.tw
    db, dh, dhn = g["db"], g["dh"], g["dhn"]
    hf = g["hf"]
    Bc = PHI_BOLT * bolt_tension_rn(db, st.bolt_grade)
    ext_T, ext_C = (st.ext_t, st.ext_c) if top else (st.ext_c, st.ext_t)
    yc_cf = -(d / 2 - tf / 2)                                       # centroide del ala comprimida (la traccionada va hacia +y)
    rows = _rows(st, g, ext_T)
    p = st.bp / 2.0                                                 # ancho tributario por perno
    Ff = Mu / hf
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Viga", f"{st.beam} ({st.beam_steel})", f"d = {rec.f('L', d)}, bf = {rec.f('L', bf)}, tf = {rec.f('L', tf)}, tw = {rec.f('L', tw)}", None)
        rec.add("Columna", f"{st.col} ({st.col_steel})", "con placas de continuidad" if st.cont_plates else "sin placas de continuidad", None)
        rec.add("Placa", f"{rec.n('L', st.bp)} × {rec.n('L', st.tp)} {u.L}", f"{st.plate_steel}: Fy = {rec.f('S', pm.Fy)}, Fu = {rec.f('S', pm.Fu)}", None)
        rec.add("Pernos", f"Ø{st.bolt_size} in {st.bolt_grade}", f"g = {rec.f('L', st.g)}, pfi = {rec.f('L', st.pfi)}, pfo = {rec.f('L', st.pfo)}, e = {rec.f('L', st.e_ext)}", None)
        rec.add("Mu", "momento factorizado" + (" (traccion arriba)" if top else " (traccion abajo)"), "", Mu, "M")
        rec.add("Vu", "cortante", "", Vu, "F")
        rec.add("Ff", "Mu/(d − tf)", f"{rec.n('M', Mu)}/{rec.n('L', hf)}", Ff, "F", note="fuerza en el ala traccionada")
        rec.section("PERNOS A TRACCION POR FILA — T equivalente con efecto palanca (Manual Parte 9)")
        rec.add("Bc", "φ·Fnt·Ab", f"0.75·{rec.f('S', FNT[st.bolt_grade])}·{rec.f('A', math.pi * db ** 2 / 4)}", Bc, "F", "AISC J3.6")
    Mcap = Mnp = 0.0
    detail = []
    for rn_, y, b, a in rows:
        h = y - yc_cf
        T, alpha, tc = prying_available(Bc, max(b, 1e-6), a, p, st.tp, pm.Fu, db, dh)
        Mcap += 2.0 * T * h
        Mnp += 2.0 * Bc * h
        detail.append((rn_, h, T, alpha, tc, b, a))
        if rec:
            rec.add(f"T fila {rn_}", "T maxima por perno con palanca", f"b = {rec.n('L', b)}, a = {rec.n('L', a)}, p = {rec.n('L', p)}, tc = {rec.n('L', tc)} {u.L}; "
                    f"α' = {alpha:.2f}; brazo h = {rec.n('L', h)}", T, "F", "AISC Manual Parte 9")
    add_check(ck, rec, "ep_M", "Placa extrema — momento resistente (pernos y placa con palanca)", Mu, Mcap, "kip·in", "AISC Manual Parte 9",
              "; ".join(f"fila {r[0]}: T = {r[2]:.1f} kip (tc = {u.q('L', r[4])}, α' = {r[3]:.2f})" for r in detail))
    add_check(ck, rec, "ep_Mb", "Pernos a traccion sin palanca (referencia)", Mu, Mnp, "kip·in", "AISC J3.6",
              "capacidad si la placa fuera infinitamente gruesa")
    # ----------------------------------------------------- cortante en los pernos comprimidos
    nbc = 2 * (1 + (1 if ext_C else 0))
    rnv = bolt_shear_rn(db, st.bolt_grade)
    add_check(ck, rec, "ep_V", "Pernos del lado comprimido — cortante", Vu / nbc, PHI_BOLT * rnv, "kip", "AISC J3.6", f"{nbc} pernos Ø{st.bolt_size} (Vu/n por perno)")
    Lc = min([st.e_ext - dh / 2] if ext_C else [st.pfi + tf - dh / 2])
    Lc_in = (st.pfi + tf + st.pfo - dh) if ext_C else 1e9
    capb = PHI_BOLT * min(bearing_rn(db, st.tp, pm.Fu, Lc), bearing_rn(db, st.tp, pm.Fu, Lc_in))
    add_check(ck, rec, "ep_brg", "Pernos del lado comprimido — aplastamiento en la placa", Vu / nbc, capb, "kip", "AISC J3.10")
    # ------------------------------------------------------- placa: cortante en la extension traccionada
    if ext_T:
        An = (st.bp - 2 * (dh + 0.125)) * st.tp
        add_check(ck, rec, "ep_pv_y", "Placa — fluencia por cortante de la extension (Ff/2)", Ff / 2, PHI_YIELD * 0.6 * pm.Fy * st.bp * st.tp, "kip", "AISC J4.2(a)")
        add_check(ck, rec, "ep_pv_r", "Placa — rotura por cortante de la extension (Ff/2)", Ff / 2, PHI_RUPT * 0.6 * pm.Fu * An, "kip", "AISC J4.2(b)")
    # ------------------------------------------------------------- soldaduras viga-placa
    kd = 1.5 if st.weld_dir else 1.0
    if g["fillet"]:
        Lfw = 2 * bf - tw
        capw = 0.75 * 0.60 * FEXX * kd * 0.707 * st.fw_size * Lfw
        add_check(ck, rec, "ep_fw", "Soldadura del ala traccionada a la placa — filetes a ambos lados", Ff, capw, "kip", "AISC J2.4",
                  f"w = {float_to_frac(st.fw_size)}\", L = 2·bf − tw = {u.q('L', Lfw)}; ala transversal (θ = 90°)")
        add_check(ck, rec, "ep_fw_min", "Filete del ala — tamano minimo", M.min_fillet(min(tf, st.tp)), st.fw_size, "in", "AISC Tabla J2.4")
    else:
        add_check(ck, rec, "ep_fw", "Soldadura CJP del ala — fuerza vs resistencia del ala de la viga", Ff, 0.9 * bm.Fy * bf * tf, "kip", "AISC J2.4 / D2",
                  "CJP con aporte compatible: la resistencia es la del metal base")
    Lww = 2 * (d - 2 * tf)
    add_check(ck, rec, "ep_ww", "Soldadura del alma a la placa (filetes a ambos lados)", Vu, 0.75 * 0.60 * FEXX * 0.707 * st.ww_size * Lww, "kip", "AISC J2.4",
              f"w = {float_to_frac(st.ww_size)}\", L = 2·(d − 2·tf) = {u.q('L', Lww)}")
    add_check(ck, rec, "ep_ww_min", "Filete del alma — tamano minimo", M.min_fillet(min(tw, st.tp)), st.ww_size, "in", "AISC Tabla J2.4")
    # ------------------------------------------------------------------- distancias
    add_check(ck, rec, "ep_geo_e", "Distancia de la fila exterior al borde de la placa", edge_min(db), st.e_ext if ext_T or ext_C else 1e9, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "ep_geo_s", "Distancia de los pernos al borde lateral de la placa", edge_min(db), (st.bp - st.g) / 2, "in", "AISC Tabla J3.4")
    # ------------------------------------------------------------------- columna
    kc = col.kdes if col.kdes > 0 else col.tf + 0.5
    Npt = tf + 2 * st.tp
    if not st.cont_plates:
        add_check(ck, rec, "ep_c_fb", "Columna — flexion local del ala (J10.1, estimacion)", Ff, 0.90 * flange_local_bending(cm.Fy, col.tf), "kip", "AISC J10.1",
                  "con pernos pasantes conviene verificar las lineas de fluencia del ala (DG4)")
        add_check(ck, rec, "ep_c_wy", "Columna — fluencia local del alma (J10.2)", Ff, PHI_YIELD * web_local_yielding(cm.Fy, col.tw, kc, Npt), "kip", "AISC J10.2",
                  f"N = tf,viga + 2·tp = {u.q('L', Npt)}")
        add_check(ck, rec, "ep_c_wc", "Columna — aplastamiento del alma, lado comprimido (J10.3)", Ff, 0.75 * web_crippling(cm.Fy, col.tw, col.tf, col.d, Npt), "kip", "AISC J10.3")
    add_check(ck, rec, "ep_c_pz", "Columna — zona del panel (J10.6a, sin descontar el cortante de la columna)", Ff, 0.9 * panel_zone_shear(cm.Fy, col.d, col.tw), "kip", "AISC J10.6(a)",
              "V,panel = Ff (conservador: no resta el cortante de la columna)")
    not_evaluated(ck, "ep_c_yl", "Ala de la columna — mecanismo de lineas de fluencia", "AISC DG4")
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.epl, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "epl"
TAB = "Placa extrema"
PREFIX = "PE"
TITLE = "PLACA EXTREMA A MOMENTO (VIGA A COLUMNA)"
NORMS = "AISC 360-22 (cap. J) · AISC Steel Construction Manual 15a Ed., Parte 9 (T equivalente con palanca) · referencia AISC DG4"
LOADS = [("Mu", "M"), ("Vu", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con el momento Mu en la cara de la columna (positivo = traccion en el ala superior; "
              "negativo = traccion en el inferior) y el cortante Vu.")
FORM = [
    G("Viga"),
    combo("Perfil", "epl.beam", "@I", editable=True),
    combo("Acero", "epl.beam_steel", "@steel_shape"),
    G("Columna (conexion al ala)"),
    combo("Perfil", "epl.col", "@I", editable=True),
    combo("Acero", "epl.col_steel", "@steel_shape"),
    check("Placas de continuidad en la columna", "epl.cont_plates", help="Si hay placas de continuidad se omiten las verificaciones locales del ala y del alma de la columna (J10.1 a J10.3); se mantiene la zona del panel."),
    G("Placa extrema"),
    combo("Acero de la placa", "epl.plate_steel", "@steel_plate"),
    num("Ancho  bp", "epl.bp", 3, 30, uk="L"),
    num("Espesor  tp", "epl.tp", 0.25, 4, uk="L"),
    num("Pasante a la fila exterior  e", "epl.e_ext", 0.5, 6, uk="L", help="Distancia de la fila exterior de pernos al borde de la placa."),
    check("Fila exterior en el lado traccionado (placa extendida)", "epl.ext_t", help="Sin ella la placa es a ras: solo hay fila interior en el ala traccionada."),
    check("Fila exterior en el lado comprimido", "epl.ext_c", help="Los pernos del lado comprimido toman el cortante y sirven si el momento se invierte."),
    G("Pernos"),
    combo("Diametro", "epl.bolt_size", SHEAR_BOLT_SIZES),
    combo("Calidad", "epl.bolt_grade", BOLT_GRADES),
    num("Gramil  g (entre columnas)", "epl.g", 1, 20, uk="L"),
    num("Fila exterior: cara exterior del ala al perno  pfo", "epl.pfo", 0.5, 8, uk="L"),
    num("Fila interior: cara interior del ala al perno  pfi", "epl.pfi", 0.5, 8, uk="L"),
    G("Soldaduras viga-placa"),
    combo("Soldadura del ala", "epl.fw_type", EP_FLANGE_WELD),
    num("Cateto del filete del ala", "epl.fw_size", 0.0625, 1.5, uk="L", show=lambda p: p.epl.fw_type == EP_FLANGE_WELD[1]),
    num("Cateto del filete del alma", "epl.ww_size", 0.0625, 1, uk="L"),
    combo("Electrodo", "epl.electrode", "@electrode"),
    check("Incremento direccional (AISC J2-5)", "epl.weld_dir"),
    N("Aproximacion de T equivalente con palanca por fila (Manual Parte 9), NO el procedimiento de lineas de fluencia de DG4. Sin rigidizadores de placa. "
      "No se evalua la flexion del ala de la columna por lineas de fluencia."),
]


def label(prj) -> str:
    st = prj.epl
    return f"{st.beam} → {st.col}  (placa {'extendida' if st.ext_t else 'a ras'}, Ø{st.bolt_size})"


def input_rows(prj, us) -> list:
    st = prj.epl
    g = geometry(st)
    return [("Viga", f"{st.beam} ({st.beam_steel})"), ("Columna", f"{st.col} ({st.col_steel})" + (", con placas de continuidad" if st.cont_plates else "")),
            ("Placa extrema", f"{us.q('L', st.bp)} × {us.q('L', st.tp)} ({st.plate_steel}); " + ("extendida" if st.ext_t else "a ras") + (" / extendida en el lado comprimido" if st.ext_c else "")),
            ("Pernos", f"Ø{st.bolt_size} in {st.bolt_grade}; g = {us.q('L', st.g)}, pfo = {us.q('L', st.pfo)}, pfi = {us.q('L', st.pfi)}, e = {us.q('L', st.e_ext)}"),
            ("Soldaduras", f"ala: {st.fw_type}" + (f" {us.q('L', st.fw_size)}" if g["fillet"] else "") + f"; alma: filete {us.q('L', st.ww_size)} {st.electrode}"),
            ("Cargas (LRFD)", "; ".join(f"{n}: Mu = {us.q('M', v[0])}, Vu = {us.q('F', v[1])}" for n, v in st.loads()))]


def draw(fig, prj):
    from . import drawing as D
    from matplotlib.patches import Rectangle, Polygon
    st = prj.epl
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    gs_ = fig.add_gridspec(2, 1, height_ratios=[1.3, 1])
    ax, ax2 = fig.add_subplot(gs_[0]), fig.add_subplot(gs_[1])
    D.blank(ax); D.blank(ax2)
    if beam is None or col is None:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    d, tf, bf, tw, tp = beam.d, beam.tf, beam.bf, beam.tw, st.tp
    Lb = 12.0
    yt = d / 2 + (st.pfo + st.e_ext if st.ext_t else 0.0)              # arriba (lado de la traccion para Mu > 0)
    yb = -(d / 2 + (st.pfo + st.e_ext if st.ext_c else 0.0))
    # columna (ala vista de canto) y placa
    ax.add_patch(Rectangle((-col.tf, yb - 1.5), col.tf, yt - yb + 3.0, fc=D.C_SUP, ec="#555555", lw=0.8, hatch="////", zorder=1))
    ax.add_patch(Rectangle((0, yb), tp, yt - yb, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.2, zorder=3))
    # viga
    ax.add_patch(Rectangle((tp, -d / 2 + tf), Lb, d - 2 * tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((tp, d / 2 - tf), Lb, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    ax.add_patch(Rectangle((tp, -d / 2), Lb, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
    for sgn, ext in ((1, st.ext_t), (-1, st.ext_c)):
        ys = [sgn * (d / 2 - tf - st.pfi)] + ([sgn * (d / 2 + st.pfo)] if ext else [])
        for y in ys:
            ax.plot([-col.tf - 0.4, tp + 0.5], [y, y], color=D.C_BOLT, lw=2.4, zorder=6)
        w_ = st.fw_size if g["fillet"] else 0.3
        for yf in (sgn * d / 2, sgn * (d / 2 - tf)):
            ax.add_patch(Polygon([(tp, yf), (tp + w_, yf), (tp, yf + (w_ if yf == sgn * d / 2 else -w_) * sgn)], fc=D.C_WELD, ec=D.C_WELD, zorder=5))
    xd = tp + Lb + 0.8
    if st.ext_t:
        D._dim(ax, (xd, d / 2), (xd, d / 2 + st.pfo), 1.2, f"pfo = {q(st.pfo)}", horizontal=False)
        D._dim(ax, (xd, d / 2 + st.pfo), (xd, yt), 3.4, f"e = {q(st.e_ext)}", horizontal=False)
    D._dim(ax, (xd, d / 2 - tf), (xd, d / 2 - tf - st.pfi), 3.4, f"pfi = {q(st.pfi)}", horizontal=False)
    D._dim(ax, (-col.tf - 0.6, yb), (-col.tf - 0.6, yt), -1.6, f"placa {q(yt - yb)} × {q(st.bp)} × {q(tp)}", horizontal=False)
    ax.set_xlim(-col.tf - 5.0, tp + Lb + 6.0)
    ax.set_ylim(yb - 2.5, yt + 2.5)
    ax.set_title(f"Elevacion lateral — {st.beam} sobre {st.col}", fontsize=9)
    # vista frontal de la placa
    ax2.add_patch(Rectangle((-st.bp / 2, yb), st.bp, yt - yb, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.2, alpha=0.6, zorder=2))
    ax2.add_patch(Rectangle((-bf / 2, d / 2 - tf), bf, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.7, zorder=3))
    ax2.add_patch(Rectangle((-bf / 2, -d / 2), bf, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.7, zorder=3))
    ax2.add_patch(Rectangle((-tw / 2, -d / 2 + tf), tw, d - 2 * tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.7, zorder=3))
    for sgn, ext in ((1, st.ext_t), (-1, st.ext_c)):
        ys = [sgn * (d / 2 - tf - st.pfi)] + ([sgn * (d / 2 + st.pfo)] if ext else [])
        for y in ys:
            for xs in (-st.g / 2, st.g / 2):
                D.bolt(ax2, xs, y, g["dh"])
    D._dim(ax2, (-st.g / 2, yb), (st.g / 2, yb), -1.4, f"g = {q(st.g)}")
    D._dim(ax2, (-st.bp / 2, yb), (st.bp / 2, yb), -3.4, f"bp = {q(st.bp)}")
    ax2.set_xlim(-st.bp / 2 - 4, st.bp / 2 + 4)
    ax2.set_ylim(yb - 5.0, yt + 2.0)
    ax2.set_title("Vista de la placa extrema (desde la viga)", fontsize=9)
