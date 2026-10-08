# -*- coding: utf-8 -*-
"""Empalme atornillado de una ala de viga de puente con pernos de alta resistencia PRETENSADOS (deslizamiento critico),
AASHTO LRFD 6.13 (placa exterior y dos interiores).  La fuerza de diseno del ala se ingresa ya calculada (6.13.6.1.4).

    Servicio II (deslizamiento):   Rn = Kh·Ks·Ns·Pt            (6.13.2.8-1, φ = 1.0)   Pt = pretension minima (RCSC Tabla 8.1)
    Resistencia, cortante:         Rn = 0.48·Ab·Fub·Ns (rosca en el plano) | 0.56·Ab·Fub·Ns (rosca fuera)   φs = 0.80   (×0.80 si la junta pasa de 38 in)
    Aplastamiento:                 Rn = 2.4·d·t·Fu (Lc ≥ 2d) | 1.2·Lc·t·Fu                                  φbb = 0.80
    Placas: fluencia 0.95·Fy·Ag ; fractura 0.80·Fu·An con An ≤ 0.85·Ag ; bloque de cortante φbs = 0.80
    Separaciones: s ≥ 3·d ; paso maximo 4 + 4t ≤ 7 in ; borde maximo 8t ≤ 5 in.
Ks: clase A 0.30, clase B 0.50, clase C 0.30; Kh: 1.0 estandar, 0.85 sobredimensionado/ranura corta, 0.70 ranura larga.
Los valores de las tablas de AASHTO y RCSC estan transcritos del texto sin poder contrastarlos; revisense contra la edicion vigente.
NO se evalua: el reparto de fuerzas del empalme del alma, la resistencia de fatiga (categoria B), el limite de pandeo de las placas en compresion ni
la fuerza de diseno minima del ala (6.13.6.1.4).
"""
from __future__ import annotations
import math

from .. import materials as M
from ..units import frac_to_float
from .base import run_combos, add_check, not_evaluated
from .common import edge_min
from .formspec import G, N, num, intf, combo, check
from .specs import CT_BRIDGE, BR_SURFACE, BR_HOLES, BR_GRADES

NAME = CT_BRIDGE
# pretension minima, kip (RCSC Tabla 8.1)
PT = {"A325": {"1/2": 12, "5/8": 19, "3/4": 28, "7/8": 39, "1": 51, "1-1/8": 56, "1-1/4": 71, "1-3/8": 85, "1-1/2": 103},
      "A490": {"1/2": 15, "5/8": 24, "3/4": 35, "7/8": 49, "1": 64, "1-1/8": 80, "1-1/4": 102, "1-3/8": 121, "1-1/2": 148}}
KS = {BR_SURFACE[0]: 0.30, BR_SURFACE[1]: 0.50, BR_SURFACE[2]: 0.30}
KH = {BR_HOLES[0]: 1.0, BR_HOLES[1]: 0.85, BR_HOLES[2]: 0.70}
PHI_S, PHI_BB, PHI_Y, PHI_U, PHI_BS = 0.80, 0.80, 0.95, 0.80, 0.80
SIZES = ["5/8", "3/4", "7/8", "1", "1-1/8", "1-1/4"]


def fub(db: float, grade: str) -> float:
    return 150.0 if grade == "A490" else (120.0 if db <= 1.0 + 1e-9 else 105.0)


def geometry(st):
    db = frac_to_float(st.bolt_size)
    std = st.holes == BR_HOLES[0]
    dh = db + (0.0625 if std else (0.1875 if db < 1.0 else 0.25))
    return dict(db=db, dh=dh, dhn=dh + 0.0625 + (0.0 if std else 0.0), has_inner=st.pi_t > 0 and st.pi_b > 0,
                nb=max(st.n_rows, 0) * max(st.n_cols, 0))


def check_input(st) -> list:
    g = geometry(st)
    w = []
    if st.bolt_size not in PT.get(st.bolt_grade, {}):
        w.append(f"** Perno Ø{st.bolt_size} {st.bolt_grade}: sin pretension tabulada. **")
    if st.n_rows < 1 or st.n_cols < 1:
        w.append("** Faltan filas o columnas de pernos. **")
    if st.fl_b <= 0 or st.fl_t <= 0 or st.po_b <= 0 or st.po_t <= 0:
        w.append("** Dimensiones de ala o de placa exterior no validas. **")
    if (st.n_cols - 1) * st.g + 2 * edge_min(g["db"]) > min(st.fl_b, st.po_b) + 1e-9:
        w.append("** Las columnas de pernos no caben con su distancia al borde en el ancho del ala/placa. **")
    if st.surface not in KS or st.holes not in KH or st.bolt_grade not in PT:
        w.append("** Superficie, agujero o calidad de perno no reconocidos. **")
    if st.holes == BR_HOLES[2]:
        w.append("Ranura larga: se supone orientada perpendicular a la fuerza; el area neta usa el ancho aumentado (conservador).")
    w.append("Las tablas de pretension, Ks y Kh estan transcritas sin contraste: verifiquelas contra AASHTO LRFD y RCSC vigentes.")
    w.append("NO se evalua: fatiga, pandeo de las placas en compresion, el empalme del alma ni la fuerza minima de diseno del ala (6.13.6.1.4).")
    return w


def solve_one(prj, name, vals, rec):
    Fs, Fv = vals                                               # resistencia, servicio II (kip)
    st = prj.brs
    g = geometry(st)
    ck = []
    if (st.bolt_size not in PT.get(st.bolt_grade, {}) or st.n_rows < 1 or st.n_cols < 1 or st.fl_b <= 0 or st.fl_t <= 0 or st.po_b <= 0
            or st.po_t <= 0 or st.surface not in KS or st.holes not in KH):
        return ck
    u = prj.units()
    fm = M.find(M.PLATE_STEELS, st.fl_steel, 1)
    pm = M.find(M.PLATE_STEELS, st.sp_steel, 1)
    db, dh, dhn, nb = g["db"], g["dh"], g["dhn"], g["nb"]
    Ns = 2 if g["has_inner"] else 1
    Ab = math.pi * db ** 2 / 4
    Pt = PT[st.bolt_grade][st.bolt_size]
    Kh, Ks = KH[st.holes], KS[st.surface]
    Rslip = Kh * Ks * Ns * Pt
    Rsh = (0.56 if st.threads_excl else 0.48) * Ab * fub(db, st.bolt_grade) * Ns
    Ljoint = (st.n_rows - 1) * st.s
    red = 0.80 if Ljoint > 38.0 else 1.0
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Ala", f"{rec.n('L', st.fl_b)} × {rec.n('L', st.fl_t)} {u.L}", f"{st.fl_steel}: Fy = {rec.f('S', fm.Fy)}, Fu = {rec.f('S', fm.Fu)}", None)
        rec.add("Placas", f"exterior {rec.n('L', st.po_b)} × {rec.n('L', st.po_t)}" + (f" + 2 interiores {rec.n('L', st.pi_b)} × {rec.n('L', st.pi_t)}" if g["has_inner"] else ""),
                f"{st.sp_steel}: Fy = {rec.f('S', pm.Fy)}, Fu = {rec.f('S', pm.Fu)}", None)
        rec.add("Pernos", f"{st.n_rows} × {st.n_cols} = {nb} por lado, Ø{st.bolt_size} in {st.bolt_grade}", f"{st.holes}; superficie {st.surface}; {Ns} plano(s) de deslizamiento", None)
        rec.add("F,res  F,serv", "fuerzas de diseno del ala", f"{rec.n('F', Fs)} , {rec.n('F', Fv)}", None)
        rec.section("PERNOS — PRETENSION Y DESLIZAMIENTO CRITICO")
        rec.add("Pt", "pretension minima (RCSC Tabla 8.1)", f"{st.bolt_grade} Ø{st.bolt_size}", Pt, "F")
        rec.add("Rn,slip", "Kh·Ks·Ns·Pt", f"{Kh}·{Ks}·{Ns}·{rec.n('F', Pt)}", Rslip, "F", "AASHTO 6.13.2.8-1")
        rec.add("Rn,shear", ("0.56" if st.threads_excl else "0.48") + "·Ab·Fub·Ns", f"Fub = {rec.f('S', fub(db, st.bolt_grade))}", Rsh, "F", "AASHTO 6.13.2.7")
    # ----------------------------------------------------------- distancias
    t_min = min(st.fl_t, st.po_t, st.pi_t if g["has_inner"] else 1e9)
    add_check(ck, rec, "bs_s", "Separacion de pernos  s ≥ 3·d", 3 * db, st.s if st.n_rows > 1 else 1e9, "in", "AASHTO 6.13.2.6.1")
    add_check(ck, rec, "bs_g", "Separacion transversal  g ≥ 3·d", 3 * db, st.g if st.n_cols > 1 else 1e9, "in", "AASHTO 6.13.2.6.1")
    add_check(ck, rec, "bs_smax", "Paso maximo  s ≤ 4 + 4·t (≤ 7 in)", st.s if st.n_rows > 1 else 0.0, min(4 + 4 * t_min, 7.0), "in", "AASHTO 6.13.2.6.2")
    add_check(ck, rec, "bs_edge", "Distancia al borde minima", edge_min(db), min(st.e_end, st.e_pend, (min(st.fl_b, st.po_b) - (st.n_cols - 1) * st.g) / 2), "in", "AASHTO Tabla 6.13.2.6.6-1")
    add_check(ck, rec, "bs_emax", "Distancia al borde maxima  ≤ 8·t (≤ 5 in)", max(st.e_end, st.e_pend), min(8 * t_min, 5.0), "in", "AASHTO 6.13.2.6.6")
    # --------------------------------------------------------------- pernos
    add_check(ck, rec, "bs_slip", "Pernos — deslizamiento en Servicio II", Fv / nb, Rslip, "kip", "AASHTO 6.13.2.8", f"{nb} pernos por lado; φ = 1.0")
    add_check(ck, rec, "bs_shear", "Pernos — cortante en Resistencia", Fs / nb, PHI_S * red * Rsh, "kip", "AASHTO 6.13.2.7",
              f"{Ns} plano(s)" + ("; reduccion 0.80 por junta de mas de 38 in" if red < 1 else ""))
    Lc_end_p, Lc_end_f = st.e_pend - dh / 2, st.e_end - dh / 2
    Lc_in = st.s - dh

    def brg(t, Fu, Lcs):
        return min((2.4 * db * t * Fu if Lc >= 2 * db else 1.2 * Lc * t * Fu) for Lc in Lcs)

    t_p_eff = st.po_t + (2 * st.pi_t if g["has_inner"] else 0.0)
    add_check(ck, rec, "bs_brg_f", "Pernos — aplastamiento en el ala", Fs / nb, PHI_BB * brg(st.fl_t, fm.Fu, [Lc_end_f, Lc_in]), "kip", "AASHTO 6.13.2.9")
    add_check(ck, rec, "bs_brg_p", "Pernos — aplastamiento en las placas de empalme (espesor total)", Fs / nb, PHI_BB * brg(t_p_eff, pm.Fu, [Lc_end_p, Lc_in]), "kip", "AASHTO 6.13.2.9",
              f"espesor total {u.q('L', t_p_eff)}")
    # --------------------------------------------------------- placas y ala
    Ag_fl = st.fl_b * st.fl_t
    An_fl = st.fl_t * (st.fl_b - st.n_cols * dhn)
    Ag_p = st.po_b * st.po_t + (2 * st.pi_b * st.pi_t if g["has_inner"] else 0.0)
    An_p = st.po_t * (st.po_b - st.n_cols * dhn) + (2 * st.pi_t * (st.pi_b - (st.n_cols / 2.0) * dhn) if g["has_inner"] else 0.0)
    add_check(ck, rec, "bs_fl_y", "Ala — fluencia de la seccion bruta", Fs, PHI_Y * fm.Fy * Ag_fl, "kip", "AASHTO 6.8.2.1")
    add_check(ck, rec, "bs_fl_u", "Ala — fractura de la seccion neta", Fs, PHI_U * fm.Fu * An_fl, "kip", "AASHTO 6.8.2.1")
    add_check(ck, rec, "bs_p_y", "Placas de empalme — fluencia de la seccion bruta", Fs, PHI_Y * pm.Fy * Ag_p, "kip", "AASHTO 6.13.5.2")
    add_check(ck, rec, "bs_p_u", "Placas de empalme — fractura neta (An ≤ 0.85·Ag)", Fs, PHI_U * pm.Fu * min(An_p, 0.85 * Ag_p), "kip", "AASHTO 6.13.5.2")
    gc = (st.n_cols - 1) * st.g
    Lnt = gc - (st.n_cols - 1) * dhn
    for key, ttl, t_, mat, e0 in (("bs_bs_p", "Placa exterior — bloque de cortante", st.po_t, pm, st.e_pend), ("bs_bs_f", "Ala — bloque de cortante", st.fl_t, fm, st.e_end)):
        Lgv = 2 * (e0 + (st.n_rows - 1) * st.s)
        Lnv = Lgv - 2 * (st.n_rows - 0.5) * dhn
        add_check(ck, rec, key, ttl, Fs, PHI_BS * min(0.58 * mat.Fu * t_ * Lnv, 0.58 * mat.Fy * t_ * Lgv) + PHI_BS * mat.Fu * t_ * max(Lnt, 0.0), "kip", "AASHTO 6.13.4",
                  f"dos planos de corte de {u.q('L', Lgv / 2)} y traccion de {u.q('L', Lnt)}")
    not_evaluated(ck, "bs_other", "Fatiga, pandeo de placas en compresion, empalme del alma y fuerza minima del ala", "AASHTO 6.6, 6.13.6")
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.brs, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "brs"
TAB = "Puente pretensado"
PREFIX = "BP"
TITLE = "EMPALME DE PUENTE CON PERNOS PRETENSADOS (AASHTO)"
NORMS = "AASHTO LRFD Bridge Design Specifications, 6.13 · RCSC Specification for Structural Joints"
LOADS = [("F resistencia", "F"), ("F servicio II", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con la fuerza de diseno del ala en Resistencia (cortante, aplastamiento, placas) y en Servicio II "
              "(deslizamiento critico), ya calculadas segun AASHTO 6.13.6.1.4.")
FORM = [
    G("Ala de la viga"),
    num("Ancho", "brs.fl_b", 3, 80, uk="L"),
    num("Espesor", "brs.fl_t", 0.25, 6, uk="L"),
    combo("Acero del ala", "brs.fl_steel", "@steel_plate"),
    G("Placas de empalme"),
    combo("Acero de las placas", "brs.sp_steel", "@steel_plate"),
    num("Placa exterior: ancho", "brs.po_b", 3, 80, uk="L"),
    num("Placa exterior: espesor", "brs.po_t", 0.25, 4, uk="L"),
    num("Placas interiores: ancho (cada una)", "brs.pi_b", 0, 40, uk="L", help="Dos por ala, entre el ala y el alma; 0 = sin interiores (un plano de deslizamiento)."),
    num("Placas interiores: espesor", "brs.pi_t", 0, 4, uk="L"),
    G("Pernos pretensados"),
    combo("Diametro", "brs.bolt_size", SIZES),
    combo("Calidad", "brs.bolt_grade", BR_GRADES, help="A325 o A490 (ASTM F3125). Los valores de pretension son los minimos de RCSC Tabla 8.1."),
    check("Rosca fuera de los planos de corte", "brs.threads_excl", help="0.56 si la rosca no esta en el plano de corte; 0.48 si lo esta."),
    combo("Superficie de contacto", "brs.surface", BR_SURFACE, help="Clase A: sin pintar, limpia; clase B: granallada; clase C: galvanizada y rugosa. Define Ks."),
    combo("Tipo de agujero", "brs.holes", BR_HOLES, help="Define Kh: 1.0 estandar, 0.85 sobredimensionado o ranura corta, 0.70 ranura larga."),
    intf("Filas a cada lado del empalme", "brs.n_rows", 1, 20),
    intf("Pernos a lo ancho", "brs.n_cols", 1, 12),
    num("Paso a lo largo  s", "brs.s", 1, 12, uk="L"),
    num("Gramil transversal  g", "brs.g", 1, 12, uk="L"),
    num("Del extremo del ala a la primera fila", "brs.e_end", 0.5, 8, uk="L"),
    num("De la ultima fila al extremo de la placa", "brs.e_pend", 0.5, 8, uk="L"),
    N("Tablas de pretension, Ks y Kh transcritas sin contraste con las ediciones vigentes: verifiquelas. No se evalua fatiga ni el empalme del alma."),
]


def label(prj) -> str:
    st = prj.brs
    return f"empalme de ala {st.fl_b:g}×{st.fl_t:g} in  ({st.n_rows}×{st.n_cols} Ø{st.bolt_size} {st.bolt_grade})"


def input_rows(prj, us) -> list:
    st = prj.brs
    g = geometry(st)
    return [("Ala", f"{us.q('L', st.fl_b)} × {us.q('L', st.fl_t)} ({st.fl_steel})"),
            ("Placas de empalme", f"exterior {us.q('L', st.po_b)} × {us.q('L', st.po_t)}" + (f" + 2 interiores {us.q('L', st.pi_b)} × {us.q('L', st.pi_t)}" if g["has_inner"] else "") + f" ({st.sp_steel})"),
            ("Pernos", f"{st.n_rows} × {st.n_cols} por lado, Ø{st.bolt_size} in {st.bolt_grade}, rosca {'fuera' if st.threads_excl else 'dentro'}; s = {us.q('L', st.s)}, g = {us.q('L', st.g)}"),
            ("Superficie y agujeros", f"{st.surface}; agujeros: {st.holes}"),
            ("Cargas (LRFD)", "; ".join(f"{n}: F,res = {us.q('F', v[0])}, F,serv = {us.q('F', v[1])}" for n, v in st.loads()))]


def draw(fig, prj):
    from . import drawing as D
    from matplotlib.patches import Rectangle
    st = prj.brs
    g = geometry(st)
    gs_ = fig.add_gridspec(2, 1, height_ratios=[1.3, 1])
    ax, ax2 = fig.add_subplot(gs_[0]), fig.add_subplot(gs_[1])
    D.blank(ax); D.blank(ax2)
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    half = 0.25
    Lp2 = half + st.e_end + (st.n_rows - 1) * st.s + st.e_pend
    Lm = Lp2 + 3.0
    # planta
    ax.add_patch(Rectangle((-Lm, -st.fl_b / 2), Lm - half, st.fl_b, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.5, zorder=2))
    ax.add_patch(Rectangle((half, -st.fl_b / 2), Lm - half, st.fl_b, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.5, zorder=2))
    ax.add_patch(Rectangle((-Lp2, -st.po_b / 2), 2 * Lp2, st.po_b, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.2, alpha=0.65, zorder=4))
    for sx in (-1, 1):
        for r in range(max(st.n_rows, 0)):
            for c in range(max(st.n_cols, 0)):
                D.bolt(ax, sx * (half + st.e_end + r * st.s), (c - (st.n_cols - 1) / 2) * st.g, g["dh"])
    D._dim(ax, (-Lp2, -st.fl_b / 2), (Lp2, -st.fl_b / 2), -1.8, f"{q(2 * Lp2)}")
    D._dim(ax, (-Lm, -st.fl_b / 2), (-Lm, st.fl_b / 2), -1.4, f"{q(st.fl_b)}", horizontal=False)
    ax.set_xlim(-Lm - 4, Lm + 2)
    ax.set_ylim(-st.fl_b / 2 - 4, st.fl_b / 2 + 2)
    ax.set_title("Planta del empalme de ala", fontsize=9)
    # seccion longitudinal: pila de placas
    tfl, tpo = st.fl_t, st.po_t
    ytop = -tpo
    ax2.add_patch(Rectangle((-Lp2, ytop), 2 * Lp2, tpo, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.2, zorder=4))
    for sx in (-1, 1):
        x0 = half if sx > 0 else -Lm
        ax2.add_patch(Rectangle((x0, 0), Lm - half, tfl, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=3))
    if g["has_inner"]:
        ax2.add_patch(Rectangle((-Lp2, tfl), 2 * Lp2, st.pi_t, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.0, alpha=0.8, zorder=4))
    for sx in (-1, 1):
        for r in range(max(st.n_rows, 0)):
            x = sx * (half + st.e_end + r * st.s)
            ax2.plot([x, x], [ytop - 0.3, tfl + (st.pi_t if g["has_inner"] else 0) + 0.3], color=D.C_BOLT, lw=1.6, zorder=6)
    ax2.text(-Lp2, tfl + (st.pi_t if g["has_inner"] else 0) + 2.5,
             f"{st.bolt_grade} Ø{st.bolt_size}\" pretensado (Pt = {PT.get(st.bolt_grade, {}).get(st.bolt_size, 0)} kip) — {st.surface}", fontsize=7.5, color=D.C_BOLT, va="top")
    ax2.set_xlim(-Lm - 4, Lm + 2)
    ax2.set_ylim(tfl + (st.pi_t if g["has_inner"] else 0) + 5, -tpo - 4)
    ax2.set_title("Seccion longitudinal (pila de placas y pernos)", fontsize=9)
