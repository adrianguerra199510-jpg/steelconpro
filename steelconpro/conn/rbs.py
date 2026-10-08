# -*- coding: utf-8 -*-
"""Conexion precalificada de viga de seccion reducida (RBS), AISC 358-16 Cap. 5, procedimiento de diseno por demanda.

    Z_RBS = Zx − 2·c·tbf·(d − tbf) ;   M_pr = Cpr·Ry·Fy·Z_RBS ,  Cpr = min(1.2, (Fy + Fu)/(2·Fy))
    s_h = a + b/2 ;  L_h = L − dc − 2·s_h ;  V_RBS = 2·M_pr/L_h + V_g ;  M_f = M_pr + V_RBS·s_h  ≤  φd·Mpe ,  Mpe = Ry·Fy·Zx  (φd = 1.0)
Se verifican ademas: limites de a, b, c; limites de prequalificacion de viga (profundidad ≤ W36, peso ≤ 300 lb/ft, tbf ≤ 1.75 in, luz libre/peralte ≥ 7
en SMF o 5 en IMF) y de columna (peralte ≤ W36); compacidad sismica de ala y alma (AISC 341 Tabla D1.1); zona del panel (J10-11 con φ = 1.0, sin
descontar el cortante de la columna: conservador); columna fuerte-viga debil (AISC 341 E3.4a, M*pb = Σ[M_pr + V_RBS·(s_h + dc/2)]); y placas de
continuidad: no se requieren si tcf ≥ 0.4·√(1.8·bf·tbf·Ryb·Fyb/(Ryc·Fyc)) y tcf ≥ bf/6.
Solo se implementa la RBS: las demas conexiones precalificadas de AISC 358 (WUF-W, BFP, placas extremas, Kaiser, ConXtech, SidePlate...) NO.
NO se evalua: la soldadura CJP de la viga a la columna, el arriostramiento lateral en la RBS ni los limites de la columna con placas de continuidad.
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from .base import run_combos, add_check, not_evaluated
from .common import E_STEEL, ry_of
from .formspec import G, N, num, intf, combo, check
from .specs import CT_RBS, RBS_FRAMES

NAME = CT_RBS


def geometry(st):
    beam, col = CATALOG.get(st.beam), CATALOG.get(st.col)
    g = dict(beam=beam, col=col, smf=st.frame == RBS_FRAMES[0])
    if beam is None or col is None:
        return g
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    cm = M.find(M.SHAPE_STEELS, st.col_steel)
    g.update(bm=bm, cm=cm, Ryb=ry_of(st.beam_steel), Ryc=ry_of(st.col_steel))
    d, tbf = beam.d, beam.tf
    g["Zrbs"] = beam.Zx - 2 * st.c * tbf * (d - tbf)
    g["Cpr"] = min(1.2, (bm.Fy + bm.Fu) / (2 * bm.Fy))
    g["Mpr"] = g["Cpr"] * g["Ryb"] * bm.Fy * g["Zrbs"]
    g["sh"] = st.a + st.b / 2
    g["Lh"] = st.L - col.d - 2 * g["sh"]
    g["R"] = (4 * st.c ** 2 + st.b ** 2) / (8 * st.c) if st.c > 0 else 0.0
    return g


def check_input(st) -> list:
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    w = []
    if beam is None or beam.kind != "W" or col is None or col.kind != "W":
        return ["** La viga y la columna deben ser perfiles I del catalogo. **"]
    if st.a <= 0 or st.b <= 0 or st.c <= 0 or st.L <= 0:
        w.append("** a, b, c y la luz deben ser positivos. **")
    elif g["Lh"] <= 0:
        w.append("** La luz es muy corta: L_h = L − dc − 2·s_h ≤ 0. **")
    if st.n_beams not in (1, 2):
        w.append("** El numero de vigas en el nudo debe ser 1 o 2. **")
    w.append("Solo RBS de AISC 358-16 Cap. 5. Soldadura CJP viga-columna, arriostramiento lateral en la RBS y placas de continuidad (detalle) no se verifican.")
    return w


def solve_one(prj, name, vals, rec):
    Vg, Puc = vals
    st = prj.rbs
    g = geometry(st)
    ck = []
    beam, col = g["beam"], g["col"]
    if beam is None or col is None or beam.kind != "W" or col.kind != "W" or st.a <= 0 or st.b <= 0 or st.c <= 0 or st.L <= 0 or g["Lh"] <= 0 \
            or st.n_beams not in (1, 2):
        return ck
    u = prj.units()
    bm, cm, Ryb, Ryc = g["bm"], g["cm"], g["Ryb"], g["Ryc"]
    d, bf, tbf, tw = beam.d, beam.bf, beam.tf, beam.tw
    Zx, Mpr, sh, Lh = beam.Zx, g["Mpr"], g["sh"], g["Lh"]
    Vrbs = 2 * Mpr / Lh + Vg
    Mf = Mpr + Vrbs * sh
    Mpe = Ryb * bm.Fy * Zx
    Ffu = Mf / (d - tbf)
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Viga", f"{st.beam} ({st.beam_steel})", f"Fy = {rec.f('S', bm.Fy)}, Fu = {rec.f('S', bm.Fu)}, Ry = {Ryb}; d = {rec.f('L', d)}, bf = {rec.f('L', bf)}, tbf = {rec.f('L', tbf)}", None)
        rec.add("Columna", f"{st.col} ({st.col_steel})", f"Fy = {rec.f('S', cm.Fy)}, Ry = {Ryc}; dc = {rec.f('L', col.d)}", None)
        rec.add("RBS", f"a = {rec.n('L', st.a)}, b = {rec.n('L', st.b)}, c = {rec.n('L', st.c)} {u.L}", f"radio R = (4c² + b²)/(8c) = {rec.f('L', g['R'])}", None)
        rec.add("Vg , Puc", "gravedad en el RBS , axial de la columna", f"{rec.n('F', Vg)} , {rec.n('F', Puc)}", None)
        rec.section("DEMANDAS — AISC 358-16 §5.8")
        rec.add("Z,RBS", "Zx − 2·c·tbf·(d − tbf)", f"{Zx / u.fl ** 3:.4g} − 2·{rec.n('L', st.c)}·{rec.n('L', tbf)}·({rec.n('L', d)} − {rec.n('L', tbf)})", g["Zrbs"] / u.fl ** 3, "-", note=f"en {u.L}³")
        rec.add("Cpr", "min(1.2, (Fy + Fu)/(2·Fy))", "", g["Cpr"], "-", "AISC 358 Ec. 2.4.3-2")
        rec.add("M,pr", "Cpr·Ry·Fy·Z,RBS", "", Mpr, "M")
        rec.add("s,h  L,h", "a + b/2 ;  L − dc − 2·s,h", f"{rec.n('L', sh)} ; {rec.n('L', Lh)}", None)
        rec.add("V,RBS", "2·M,pr/L,h + Vg", "", Vrbs, "F")
        rec.add("M,f", "M,pr + V,RBS·s,h", "", Mf, "M", note="momento en la cara de la columna")
        rec.add("M,pe", "Ry·Fy·Zx", "", Mpe, "M")
    add_check(ck, rec, "rbs_mf", "Momento en la cara de la columna  Mf ≤ φd·Mpe  (φd = 1.0)", Mf, 1.0 * Mpe, "kip·in", "AISC 358 §5.8 paso 6")
    # ---- limites de a, b, c
    for key, ttl, val, lo, hi in (("rbs_a", "a entre 0.50·bf y 0.75·bf", st.a, 0.5 * bf, 0.75 * bf),
                                  ("rbs_b", "b entre 0.65·d y 0.85·d", st.b, 0.65 * d, 0.85 * d),
                                  ("rbs_c", "c entre 0.10·bf y 0.25·bf", st.c, 0.10 * bf, 0.25 * bf)):
        add_check(ck, rec, key, f"Limites de la RBS — {ttl}", max(val / hi, lo / val), 1.0, "-", "AISC 358 §5.8 paso 1", f"{u.q('L', val)} en [{u.q('L', lo)}, {u.q('L', hi)}]")
    # ---- limites de prequalificacion
    Lcl = st.L - col.d
    lim = 7.0 if g["smf"] else 5.0
    add_check(ck, rec, "rbs_span", f"Luz libre / peralte ≥ {lim:g}", lim, Lcl / d, "-", "AISC 358 §5.3.1", f"L libre = {u.q('L', Lcl)}, d = {u.q('L', d)}")
    add_check(ck, rec, "rbs_depth", "Peralte de la viga ≤ W36", round(d), 36.0, "in", "AISC 358 §5.3.1", f"d nominal = {round(d)} in")
    add_check(ck, rec, "rbs_wt", "Peso de la viga ≤ 300 lb/ft", beam.A * 3.4, 300.0, "-", "AISC 358 §5.3.1", f"peso = {beam.A * 3.4:.0f} lb/ft")
    add_check(ck, rec, "rbs_tbf", "Espesor del ala de la viga ≤ 1-3/4 in", tbf, 1.75, "in", "AISC 358 §5.3.1")
    add_check(ck, rec, "rbs_cdepth", "Peralte de la columna ≤ W36", round(col.d), 36.0, "in", "AISC 358 §5.3.2", f"d nominal = {round(col.d)} in")
    k = beam.kdes if beam.kdes > 0 else tbf + 0.5
    lam_f = bf / (2 * tbf)
    lam_w = (d - 2 * k) / tw
    sq = math.sqrt(E_STEEL / (Ryb * bm.Fy))
    add_check(ck, rec, "rbs_lf", "Compacidad sismica del ala  bf/2tbf ≤ 0.32·√(E/(Ry·Fy))", lam_f, 0.32 * sq, "-", "AISC 341 Tabla D1.1")
    add_check(ck, rec, "rbs_lw", "Compacidad sismica del alma  h/tw ≤ 2.57·√(E/(Ry·Fy))", lam_w, 2.57 * sq, "-", "AISC 341 Tabla D1.1")
    # ---- zona del panel
    nb = st.n_beams
    Vcol = nb * (Mpr + Vrbs * (sh + col.d / 2)) / st.H_story if st.H_story > 0 else 0.0
    Vpz = nb * Mf / (d - tbf) - Vcol
    Rv = 1.0 * 0.60 * cm.Fy * col.d * col.tw * (1 + 3 * col.bf * col.tf ** 2 / (d * col.d * col.tw))
    add_check(ck, rec, "rbs_pz", "Zona del panel — φv·Rv (J10-11, φv = 1.0)", Vpz, Rv, "kip", "AISC 341 E3.6e / 360 J10.6",
              "Vu = ΣMf/(db − tbf) − Vcol" + (f"; Vcol = {Vcol:.1f} kip" if Vcol > 0 else "; sin restar el cortante de la columna (conservador)"))
    # ---- columna fuerte - viga debil
    nc = 2 if st.two_cols else 1
    Mpc = nc * col.Zx * (cm.Fy - Puc / col.A)
    Mv = Vrbs * (sh + col.d / 2)
    Mpb = nb * (Mpr + Mv)
    add_check(ck, rec, "rbs_scwb", "Columna fuerte - viga debil  ΣM*pb ≤ ΣM*pc", Mpb, Mpc, "kip·in", "AISC 341 E3.4a",
              f"M*pc = {nc}·Zc·(Fyc − Puc/Ag); M*pb = {nb}·(Mpr + V_RBS·(s_h + dc/2)); relacion ΣM*pc/ΣM*pb = {Mpc / Mpb:.2f}")
    # ---- placas de continuidad
    t_req = 0.4 * math.sqrt(1.8 * bf * tbf * (Ryb * bm.Fy) / (Ryc * cm.Fy))
    if not st.cont_plates:
        add_check(ck, rec, "rbs_cp1", "Sin placas de continuidad: tcf ≥ 0.4·√(1.8·bf·tbf·Ryb·Fyb/(Ryc·Fyc))", t_req, col.tf, "in", "AISC 341 E3.6f / 358 §2.4.4")
        add_check(ck, rec, "rbs_cp2", "Sin placas de continuidad: tcf ≥ bf/6", bf / 6.0, col.tf, "in", "AISC 341 E3.6f / 358 §2.4.4")
    else:
        t_cp = tbf / 2 if nb == 1 else tbf
        ck.append(__import__("steelconpro.design", fromlist=["Check"]).Check(
            "rbs_cp_info", f"Placas de continuidad colocadas (t ≥ {u.q('L', t_cp)} segun AISC 358 §2.4.4) — no verificadas", 0.0, 1.0, "-", "AISC 358 §2.4.4",
            "Espesor minimo de referencia: 1/2·tbf con una viga, tbf con dos vigas; revise el detalle.", skip=True))
    not_evaluated(ck, "rbs_other", "Soldadura CJP viga-columna, arriostramiento lateral en la RBS y detalle de placas de continuidad", "AISC 358 §5.6-5.7")
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.rbs, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "rbs"
TAB = "AISC 358 RBS"
PREFIX = "RB"
TITLE = "CONEXION PRECALIFICADA RBS (AISC 358)"
NORMS = "AISC 358-16 Cap. 5 · AISC 341-16 (E3, D1) · AISC 360-22 (J10)"
LOADS = [("Vg (gravedad)", "F"), ("Puc (columna)", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con el cortante de gravedad Vg en el centro de la RBS (1.2D + f1·L + 0.2S) y el axial Puc de la "
              "columna (positivo = compresion).")
FORM = [
    G("Viga"),
    combo("Perfil", "rbs.beam", "@W", editable=True),
    combo("Acero", "rbs.beam_steel", "@steel_shape"),
    G("Columna"),
    combo("Perfil", "rbs.col", "@W", editable=True),
    combo("Acero", "rbs.col_steel", "@steel_shape"),
    check("Placas de continuidad colocadas", "rbs.cont_plates"),
    intf("Vigas en el nudo (1 o 2)", "rbs.n_beams", 1, 2),
    check("Columna arriba y abajo del nudo", "rbs.two_cols"),
    G("Porticos y luz"),
    combo("Sistema", "rbs.frame", RBS_FRAMES, help="Define la relacion luz libre/peralte minima: 7 en SMF, 5 en IMF."),
    num("Luz entre ejes de columnas  L", "rbs.L", 20, 1200, uk="L"),
    num("Altura de entrepiso (0 = no descontar Vcol)", "rbs.H_story", 0, 600, uk="L", help="Si se indica, la fuerza de la zona del panel descuenta el cortante de la columna Vcol = Σ(Mpr + Mv)/H (punto de inflexion a media altura)."),
    G("Recorte de la RBS"),
    num("a (de la cara de la columna al recorte)", "rbs.a", 0.5, 30, uk="L", help="0.50·bf a 0.75·bf."),
    num("b (largo del recorte)", "rbs.b", 1, 60, uk="L", help="0.65·d a 0.85·d."),
    num("c (profundidad del recorte)", "rbs.c", 0.25, 8, uk="L", help="0.10·bf a 0.25·bf, en cada lado del ala."),
    N("Solo se implementa la RBS de AISC 358 (las demas conexiones precalificadas no). No se verifican la soldadura CJP, el arriostramiento lateral ni el detalle de las placas de continuidad."),
]


def label(prj) -> str:
    st = prj.rbs
    return f"RBS {st.beam} → {st.col}  (a = {st.a:g}, b = {st.b:g}, c = {st.c:g} in)"


def input_rows(prj, us) -> list:
    st = prj.rbs
    return [("Viga", f"{st.beam} ({st.beam_steel})"), ("Columna", f"{st.col} ({st.col_steel})" + (", con placas de continuidad" if st.cont_plates else "")),
            ("Sistema", f"{st.frame}; luz L = {us.q('L', st.L)}; {st.n_beams} viga(s) en el nudo; columna {'arriba y abajo' if st.two_cols else 'solo abajo'}"),
            ("Recorte", f"a = {us.q('L', st.a)}, b = {us.q('L', st.b)}, c = {us.q('L', st.c)}"),
            ("Cargas (LRFD)", "; ".join(f"{n}: Vg = {us.q('F', v[0])}, Puc = {us.q('F', v[1])}" for n, v in st.loads()))]


def draw(fig, prj):
    from . import drawing as D
    from matplotlib.patches import Rectangle, Polygon
    import numpy as np
    st = prj.rbs
    g = geometry(st)
    beam, col = g["beam"], g["col"]
    ax = fig.add_subplot(111)
    D.blank(ax)
    if beam is None or col is None or st.c <= 0 or st.b <= 0:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    bf = beam.bf
    Lp = st.a + st.b + 10.0
    ax.add_patch(Rectangle((-col.tf - 1.0, -bf / 2 - 3), col.tf + 1.0, bf + 6, fc=D.C_SUP, ec="#555555", lw=0.8, hatch="////", zorder=1))
    R = g["R"]
    xs = np.linspace(st.a, st.a + st.b, 60)
    xm = st.a + st.b / 2
    cut = R - np.sqrt(np.maximum(R ** 2 - (xs - xm) ** 2, 0.0))          # profundidad del recorte en x (0 en los extremos, c al centro)
    cutd = st.c - cut                                                    # distancia que se corta
    top = [(0, bf / 2), (st.a, bf / 2)] + [(x, bf / 2 - (st.c - (R - math.sqrt(max(R ** 2 - (x - xm) ** 2, 0.0))))) for x in xs] + [(st.a + st.b, bf / 2), (Lp, bf / 2)]
    # el recorte es un arco: en los extremos de b la profundidad es 0 y al centro c
    prof = lambda x: R - math.sqrt(max(R ** 2 - (x - xm) ** 2, 0.0))
    top = [(0, bf / 2), (st.a, bf / 2)] + [(x, bf / 2 - (st.c - prof(x))) for x in xs] + [(st.a + st.b, bf / 2), (Lp, bf / 2)]
    bot = [(x, -y) for x, y in top][::-1]
    ax.add_patch(Polygon(top + bot, closed=True, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.3, zorder=3))
    ax.plot([xm, xm], [-bf / 2 - 2, bf / 2 + 2], color="#c00000", lw=0.9, ls=(0, (6, 3)), zorder=5)
    ax.text(xm + 0.3, bf / 2 + 2.3, "centro de la RBS (rotula plastica)", fontsize=7.5, color="#c00000")
    D._dim(ax, (0, -bf / 2), (st.a, -bf / 2), -2.0, f"a = {q(st.a)}")
    D._dim(ax, (st.a, -bf / 2), (st.a + st.b, -bf / 2), -2.0, f"b = {q(st.b)}")
    D._dim(ax, (Lp + 0.5, bf / 2), (Lp + 0.5, bf / 2 - st.c), 1.5, f"c = {q(st.c)}", horizontal=False)
    D._dim(ax, (0, bf / 2 + 0.5), (xm, bf / 2 + 0.5), 4.2, f"s_h = {q(g['sh'])}")
    Vrbs = 2 * g["Mpr"] / g["Lh"]
    ax.text(0.0, -bf / 2 - 7.5, f"Mpr = {us.fmt('M', g['Mpr'])} {us.label('M')}   (sin gravedad: V_RBS = {us.fmt('F', Vrbs)} {us.F},  Mf ≈ {us.fmt('M', g['Mpr'] + Vrbs * g['sh'])} {us.label('M')})",
            fontsize=7.8, color="#444444")
    ax.set_xlim(-col.tf - 4, Lp + 5)
    ax.set_ylim(-bf / 2 - 10, bf / 2 + 8)
    ax.set_title(f"RBS — {st.beam} (planta del ala)", fontsize=9)
