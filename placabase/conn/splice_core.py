# -*- coding: utf-8 -*-
"""Nucleo de los empalmes atornillados de perfiles I (viga y columna): placas de ala (exterior e interiores) y dos placas de alma.

Fuerzas (el momento lo toman las alas; con "reparto segun la inercia" el alma toma Mw = Mu·Iw/I):
    Ff = Mf/(d − tf)  ;   la carga axial P (compresion +) se reparte por areas:  ala = P·Af/A , alma = P·Aw/A
    ala traccionada  T = Ff − P·Af/A      ala comprimida  C = Ff + P·Af/A
Con extremos en contacto (columnas, AISC J1.4(a)) la compresion pasa por contacto y el empalme se proporciona para
el mayor entre la traccion y el 50 % de la compresion.
Ala: fluencia y rotura de las placas (D2, J4.1(b): An ≤ 0.85·Ag), pandeo de las placas en compresion (E3, K = 1 sobre la
separacion entre las primeras filas de pernos), pernos (simple o doble corte, J3.6; factor de junta larga), aplastamiento
(J3.10), bloque de cortante de la placa exterior y del ala del perfil (J4.3), traccion neta del ala del perfil.
Alma: pernos con el metodo elastico (cortante V con la excentricidad al centro del empalme, mas Mw y N), aplastamiento,
fluencia/rotura/bloque de cortante de las placas, flexion de las placas si hay Mw y cortante del alma del perfil.
NO se evalua: pandeo de las placas de alma, ranuras, deslizamiento critico ni la resistencia del perfil fuera del empalme.
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from .base import add_check
from .common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, FNV, E_STEEL, bolt_db, hole_std, hole_net, edge_min, bolt_shear_rn,
                     bearing_rn, block_shear_rn, column_fcr, elastic_bolt_group, long_joint_factor)
from .specs import SPLICE_SHARE


def geometry(sp):
    sh = CATALOG.get(sp.shape)
    db, dbw = bolt_db(sp.bolt_size), bolt_db(sp.wbolt_size)
    g = dict(sh=sh, db=db, dh=hole_std(db), dhn=hole_net(db), dbw=dbw, dhw=hole_std(dbw), dhwn=hole_net(dbw),
             has_inner=sp.fi_t > 0 and sp.fi_b > 0, nbf=max(sp.f_rows, 0) * max(sp.f_cols, 0))
    if sh is not None:
        g["hf"] = sh.d - sh.tf
        g["Af"] = sh.bf * sh.tf
        g["Aw"] = max(sh.A - 2 * g["Af"], 1e-9)
        g["hweb"] = sh.d - 2 * sh.tf
        g["Iw"] = sh.tw * g["hweb"] ** 3 / 12.0
    g["Lbuck"] = sp.gap + 2 * sp.f_end
    g["Lplate"] = sp.gap + 2 * (sp.f_end + (sp.f_rows - 1) * sp.f_s + sp.f_pend)
    g["e_w"] = sp.gap / 2 + sp.w_end + (sp.w_nh - 1) * sp.w_sh / 2
    g["edge_v"] = (sp.w_h - (sp.w_nv - 1) * sp.w_sv) / 2
    return g


def check_input(sp, is_col: bool) -> list:
    g = geometry(sp)
    sh = g["sh"]
    w = []
    if sh is None or sh.kind != "W":
        return [f"** El perfil '{sp.shape}' debe ser un perfil I del catalogo. **"]
    if sp.bolt_grade not in FNV:
        w.append(f"** Calidad de perno '{sp.bolt_grade}' no reconocida. **")
    if sp.f_rows < 1 or sp.f_cols not in (2, 4) or sp.w_nv < 1 or sp.w_nh < 1:
        w.append("** Pernos del empalme: al menos 1 fila en las alas (2 o 4 columnas) y 1 en el alma. **")
    if sp.fo_b <= 0 or sp.fo_t <= 0:
        w.append("** Falta la placa exterior de ala. **")
    if sp.fo_b > sh.bf + 1e-9:
        w.append(f"** La placa exterior ({sp.fo_b:g} in) es mas ancha que el ala ({sh.bf:g} in). **")
    if g["has_inner"] and sp.fi_b > (sh.bf - sh.tw) / 2 - sh.kdes + sh.tf + 1e-9:
        w.append("Las placas interiores pueden no caber entre el alma y el borde del ala (comprobar contra el filete k).")
    if (sp.f_cols - 1) * sp.f_g + 2 * edge_min(g["db"]) > min(sh.bf, sp.fo_b) + 1e-9:
        w.append("** Las columnas de pernos del ala no caben con su distancia al borde en el ancho del ala/placa. **")
    if sp.w_h > sh.d - 2 * sh.tf + 1e-9:
        w.append("** La placa de alma es mas alta que el alma libre entre alas. **")
    if g["edge_v"] < -1e-9:
        w.append("** Los pernos del alma no caben en la altura de la placa de alma. **")
    if sp.share not in SPLICE_SHARE:
        w.append(f"** Reparto de momento '{sp.share}' no reconocido. **")
    if is_col and sp.contact:
        w.append("Empalme con contacto: la compresion pasa por contacto y las placas se proporcionan para el mayor entre la traccion y "
                 "el 50 % de la compresion (J1.4(a)). Verifique que los extremos esten fresados o aserrados y alineados.")
    w.append("No se evaluan: pandeo de las placas de alma, deslizamiento critico ni la resistencia del perfil fuera del empalme.")
    return w


def _bearing_min(db, dh, t, Fu, Lc_list):
    """Resistencia de aplastamiento por perno con la menor distancia libre."""
    return min(bearing_rn(db, t, Fu, Lc) for Lc in Lc_list)


def checks(prj, sp, name, Mu, Vu, P, contact, rec):
    """Verificaciones del empalme. P = carga axial (compresion +), Mu y Vu en la seccion del empalme."""
    g = geometry(sp)
    sh = g["sh"]
    ck = []
    if (sh is None or sp.f_rows < 1 or sp.f_cols not in (2, 4) or sp.w_nv < 1 or sp.w_nh < 1 or g["nbf"] < 1
            or sp.fo_t <= 0 or sp.fo_b <= 0 or sp.w_t <= 0 or sp.w_h <= 0):
        return ck                                     # datos imposibles: check_input ya avisa con '**'
    u = prj.units()
    mm = M.find(M.SHAPE_STEELS, sp.steel)
    pm = M.find(M.PLATE_STEELS, sp.plate_steel, 1)
    d, tf, tw, bf, A = sh.d, sh.tf, sh.tw, sh.bf, sh.A
    db, dh, dhn, nbf = g["db"], g["dh"], g["dhn"], g["nbf"]
    hf, Af, Aw = g["hf"], g["Af"], g["Aw"]
    # ---------------------------------------------------------------- fuerzas
    if sp.share == SPLICE_SHARE[0]:
        Mw = 0.0
    else:
        Mw = abs(Mu) * g["Iw"] / sh.Ix
    Mf = abs(Mu) - Mw
    Ff = Mf / hf
    T_net = Ff - P * Af / A                        # ala traccionada (si < 0, trabaja a compresion)
    C_net = Ff + P * Af / A                        # ala comprimida
    T = max(T_net, 0.0)
    C = max(C_net, -min(T_net, 0.0))
    Cd = 0.5 * C if contact else C
    Fb = max(T, Cd)                                # fuerza de diseno de pernos, aplastamiento y bloque de cortante
    Nw = -P * Aw / A                               # axial del alma (+ traccion)
    if contact and Nw < 0:
        Nw *= 0.5                                  # compresion del alma por contacto: se proporciona el 50 % (J1.4(a))
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Perfil", f"{sp.shape} ({sp.steel})", f"d = {rec.f('L', d)}, bf = {rec.f('L', bf)}, tf = {rec.f('L', tf)}, tw = {rec.f('L', tw)}; "
                f"A = {rec.f('A', A)}", None)
        rec.add("Mu", "momento en el empalme", "", abs(Mu), "M")
        rec.add("Vu", "cortante", "", Vu, "F")
        rec.add("P", "axial (compresion +)", "", P, "F")
        rec.section("FUERZAS EN LAS PLACAS")
        rec.add("Mw", "0 (alas toman todo) | Mu·Iw/I", f"Iw = {g['Iw'] / u.fl ** 4:.4g} {u.L}⁴", Mw, "M")
        rec.add("Ff", "(Mu − Mw)/(d − tf)", f"({rec.n('M', abs(Mu))} − {rec.n('M', Mw)})/{rec.n('L', hf)}", Ff, "F")
        rec.add("T", "Ff − P·Af/A  (ala traccionada)", f"P·Af/A = {rec.n('F', P * Af / A)}", T, "F")
        rec.add("C", "Ff + P·Af/A  (ala comprimida)", "", C, "F")
        if contact:
            rec.add("Cd", "0.5·C  (J1.4(a), con contacto)", "", Cd, "F")
        rec.add("Fb", "max(T, Cd)", "", Fb, "F", note="fuerza de diseno de los pernos de las alas")
        rec.add("Nw", "−P·Aw/A" + ("  (50 % si es compresion con contacto)" if contact else ""), "", Nw, "F", note="axial del alma, + traccion")

    # ------------------------------------------------------------- distancias
    sp_min = 8.0 / 3.0 * db
    add_check(ck, rec, "geo_fs", "Separacion de pernos en el ala  s ≥ 2-2/3·db", sp_min, sp.f_s if sp.f_rows > 1 else 1e9, "in", "AISC J3.3")
    add_check(ck, rec, "geo_fg", "Separacion entre columnas de pernos del ala", sp_min, sp.f_g, "in", "AISC J3.3")
    add_check(ck, rec, "geo_fend", "Distancia del extremo del perfil a la primera fila (ala)", edge_min(db), sp.f_end, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "geo_fpend", "Distancia de la ultima fila al extremo de la placa (ala)", edge_min(db), sp.f_pend, "in", "AISC Tabla J3.4")
    ecross_m = (bf - (sp.f_cols - 1) * sp.f_g) / 2
    ecross_p = (sp.fo_b - (sp.f_cols - 1) * sp.f_g) / 2
    add_check(ck, rec, "geo_fedge", "Distancia al borde a lo ancho (ala y placa exterior)", edge_min(db), min(ecross_m, ecross_p), "in", "AISC Tabla J3.4")

    # ------------------------------------------------------------------- alas
    Ag_o, Ag_i = sp.fo_b * sp.fo_t, 2 * sp.fi_b * sp.fi_t if g["has_inner"] else 0.0
    An_o = sp.fo_t * (sp.fo_b - sp.f_cols * dhn)
    An_i = 2 * sp.fi_t * (sp.fi_b - (sp.f_cols / 2.0) * dhn) if g["has_inner"] else 0.0
    Ag, An = Ag_o + Ag_i, An_o + An_i
    Ae = min(An, 0.85 * Ag)
    Fp = max(T, C if not contact else Cd)
    m = 2 if g["has_inner"] else 1
    rn = bolt_shear_rn(db, sp.bolt_grade)
    lj = long_joint_factor((sp.f_rows - 1) * sp.f_s)
    if rec:
        rec.section("EMPALME DE LAS ALAS")
        rec.add("Ag", "placa exterior + interiores", f"{rec.n('A', Ag_o)} + {rec.n('A', Ag_i)}", Ag, "A")
        rec.add("Ae", "min(An, 0.85·Ag)", f"An = {rec.n('A', An)}", Ae, "A", "AISC D2 / J4.1(b)")
        rec.add("rn", "Fnv·Ab", f"{rec.f('S', FNV[sp.bolt_grade])}·{rec.f('A', math.pi * db ** 2 / 4)}", rn, "F", "AISC J3.6",
                note=f"{m} plano(s) de corte; {nbf} pernos por ala a cada lado del empalme")
    add_check(ck, rec, "fl_pl_y", "Placas de ala — fluencia por traccion/compresion", Fp, 0.9 * pm.Fy * Ag, "kip", "AISC D2(a)",
              f"Fp = max(T, {'Cd' if contact else 'C'})")
    add_check(ck, rec, "fl_pl_r", "Placas de ala — rotura por traccion neta (Ae ≤ 0.85·Ag)", T, 0.75 * pm.Fu * Ae, "kip", "AISC D2(b), J4.1(b)")
    if not contact:
        r_o = sp.fo_t / math.sqrt(12.0)
        Pn_c = 0.9 * column_fcr(pm.Fy, g["Lbuck"] / r_o) * Ag_o
        if g["has_inner"]:
            Pn_c += 0.9 * column_fcr(pm.Fy, g["Lbuck"] / (sp.fi_t / math.sqrt(12.0))) * Ag_i
        add_check(ck, rec, "fl_pl_b", "Placas de ala — pandeo en compresion (K = 1)", C, Pn_c, "kip", "AISC E3",
                  f"L = gap + 2·f_end = {u.q('L', g['Lbuck'])}; KL/r = {g['Lbuck'] / r_o:.0f}")
    add_check(ck, rec, "fl_bolt", f"Pernos de ala — cortante ({m} plano{'s' if m > 1 else ''})", Fb / nbf, PHI_BOLT * m * rn * lj, "kip", "AISC J3.6",
              f"{nbf} pernos Ø{sp.bolt_size} por ala y por lado" + ("; reduccion por junta larga" if lj < 1 else ""))
    # aplastamiento: placa exterior (la mas delgada manda) y ala del perfil, con la menor distancia libre
    Lc_p = [sp.f_pend - dh / 2, sp.f_s - dh]
    Lc_m = [sp.f_end - dh / 2, sp.f_s - dh]
    t_p = sp.fo_t if not g["has_inner"] else min(sp.fo_t, 2 * sp.fi_t if sp.fi_t > 0 else sp.fo_t)
    cap_p = PHI_BOLT * _bearing_min(db, dh, sp.fo_t, pm.Fu, Lc_p)
    cap_m = PHI_BOLT * _bearing_min(db, dh, tf, mm.Fu, Lc_m)
    add_check(ck, rec, "fl_brg_p", "Pernos de ala — aplastamiento en la placa exterior", Fb / nbf, cap_p, "kip", "AISC J3.10",
              "bloquea toda la fuerza en la placa exterior (conservador si hay interiores)" if g["has_inner"] else "")
    add_check(ck, rec, "fl_brg_m", "Pernos de ala — aplastamiento en el ala del perfil", Fb / nbf, cap_m, "kip", "AISC J3.10")
    # bloque de cortante: dos planos de corte a lo largo de las columnas extremas y traccion a traves del ancho
    gcols = (sp.f_cols - 1) * sp.f_g
    Lnt = gcols - (sp.f_cols - 1) * dhn
    for key, ttl, t_, mat, e0 in (("fl_bs_p", "Placa exterior — bloque de cortante", sp.fo_t, pm, sp.f_pend),
                                  ("fl_bs_m", "Ala del perfil — bloque de cortante", tf, mm, sp.f_end)):
        Lgv = 2 * (e0 + (sp.f_rows - 1) * sp.f_s)
        Lnv = Lgv - 2 * (sp.f_rows - 0.5) * dhn
        add_check(ck, rec, key, ttl, T, PHI_RUPT * block_shear_rn(mat.Fy, mat.Fu, t_, Lgv, Lnv, Lnt), "kip", "AISC J4.3",
                  f"dos planos de corte de {u.q('L', Lgv / 2)} y traccion de {u.q('L', Lnt)}")
    Afn = tf * (bf - sp.f_cols * dhn)
    add_check(ck, rec, "fl_net_m", "Ala del perfil — traccion (fluencia bruta y rotura neta)", T, min(0.9 * mm.Fy * Af, 0.75 * mm.Fu * Afn), "kip", "AISC D2")

    # ------------------------------------------------------------------- alma
    dbw, dhw, dhwn = g["dbw"], g["dhw"], g["dhwn"]
    nv, nh, sv, sh_ = sp.w_nv, sp.w_nh, sp.w_sv, sp.w_sh
    nb = nv * nh
    pts = [(-(sp.gap / 2 + sp.w_end + c * sh_), (nv - 1) / 2 * sv - r * sv) for c in range(nh) for r in range(nv)]
    # carga en el centro del empalme (x = 0): el grupo (lado izquierdo) queda a e_w del eje del empalme
    xc = sum(p[0] for p in pts) / len(pts)
    ecc = abs(xc)
    Mt = Vu * ecc + Mw
    forces = elastic_bolt_group(pts, Nw, Vu, Mt)
    Fmax = max(math.hypot(fx, fy) for fx, fy in forces)
    rnw = bolt_shear_rn(dbw, sp.bolt_grade)
    if rec:
        rec.section("EMPALME DEL ALMA")
        rec.add("e", "del centro del empalme al centroide de los pernos del alma", "", ecc, "L")
        rec.add("M,pernos", "Vu·e + Mw", f"{rec.n('F', Vu)}·{rec.n('L', ecc)} + {rec.n('M', Mw)}", Mt, "M")
        rec.add("F,max", "perno mas cargado (metodo elastico)", f"{nb} pernos Ø{sp.wbolt_size}", Fmax, "F", note="conservador respecto al centro instantaneo")
    add_check(ck, rec, "w_bolt", "Pernos de alma — cortante (doble corte, metodo elastico)", Fmax, PHI_BOLT * 2 * rnw, "kip", "AISC J3.6",
              f"{nb} pernos Ø{sp.wbolt_size} por lado; excentricidad {u.q('L', ecc)}")
    edge_v = g["edge_v"]
    Lc_wp = [sp.w_pend - dhw / 2, sv - dhw, edge_v - dhw / 2 if nv > 0 else 1e9] + ([sh_ - dhw] if nh > 1 else [])
    Lc_wm = [sp.w_end - dhw / 2, sv - dhw] + ([sh_ - dhw] if nh > 1 else [])
    add_check(ck, rec, "w_brg_p", "Pernos de alma — aplastamiento en las placas de alma", Fmax / 2,
              PHI_BOLT * _bearing_min(dbw, dhw, sp.w_t, pm.Fu, Lc_wp), "kip", "AISC J3.10", "la mitad de la fuerza en cada placa")
    add_check(ck, rec, "w_brg_m", "Pernos de alma — aplastamiento en el alma del perfil", Fmax,
              PHI_BOLT * _bearing_min(dbw, dhw, tw, mm.Fu, Lc_wm), "kip", "AISC J3.10")
    add_check(ck, rec, "w_pl_vy", "Placas de alma — fluencia por cortante", Vu, PHI_YIELD * 0.6 * pm.Fy * 2 * sp.w_t * sp.w_h, "kip", "AISC J4.2(a)")
    add_check(ck, rec, "w_pl_vr", "Placas de alma — rotura por cortante neto", Vu, PHI_RUPT * 0.6 * pm.Fu * 2 * sp.w_t * (sp.w_h - nv * dhwn), "kip", "AISC J4.2(b)")
    Lgv = edge_v + (nv - 1) * sv
    Lnv = Lgv - (nv - 0.5) * dhwn
    add_check(ck, rec, "w_pl_bs", "Placas de alma — bloque de cortante", Vu,
              PHI_RUPT * 2 * block_shear_rn(pm.Fy, pm.Fu, sp.w_t, Lgv, Lnv, sp.w_pend - 0.5 * dhwn), "kip", "AISC J4.3")
    if Mw > 0:
        Z = 2 * sp.w_t * sp.w_h ** 2 / 4.0
        add_check(ck, rec, "w_pl_m", "Placas de alma — flexion por el momento del alma", Mw, 0.9 * pm.Fy * Z, "kip·in", "AISC F11")
    if abs(Nw) > 1e-9:
        add_check(ck, rec, "w_pl_n", "Placas de alma — axial", abs(Nw), 0.9 * pm.Fy * 2 * sp.w_t * sp.w_h, "kip", "AISC D2(a)")
    h_net = g["hweb"] - nv * dhwn
    add_check(ck, rec, "w_m_vy", "Alma del perfil — fluencia por cortante", Vu, PHI_YIELD * 0.6 * mm.Fy * tw * g["hweb"], "kip", "AISC J4.2(a)")
    add_check(ck, rec, "w_m_vr", "Alma del perfil — rotura por cortante neto en la fila de pernos", Vu, PHI_RUPT * 0.6 * mm.Fu * tw * max(h_net, 0.0), "kip", "AISC J4.2(b)")
    add_check(ck, rec, "geo_wend", "Distancia del extremo del perfil a la primera columna (alma)", edge_min(dbw), sp.w_end, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "geo_wpend", "Distancia de la ultima columna al extremo de la placa de alma", edge_min(dbw), sp.w_pend, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "geo_wedge", "Distancia vertical al borde de la placa de alma", edge_min(dbw), edge_v, "in", "AISC Tabla J3.4")
    add_check(ck, rec, "geo_ws", "Separacion de pernos del alma  s ≥ 2-2/3·db", 8.0 / 3.0 * dbw, sv if nv > 1 else 1e9, "in", "AISC J3.3")
    return ck


def draw(fig, prj, sp, title):
    """Elevacion lateral (placas de ala y de alma con pernos) y planta del ala."""
    from . import drawing as D
    from matplotlib.patches import Rectangle, Circle
    g = geometry(sp)
    sh = g["sh"]
    gs_ = fig.add_gridspec(2, 1, height_ratios=[1.4, 1])
    ax, ax2 = fig.add_subplot(gs_[0]), fig.add_subplot(gs_[1])
    D.blank(ax); D.blank(ax2)
    if sh is None:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    d, tf, tw, bf = sh.d, sh.tf, sh.tw, sh.bf
    half = sp.gap / 2
    Lp2 = g["Lplate"] / 2
    Lm = Lp2 + 3.0                                      # largo de perfil dibujado a cada lado
    # perfil (elevacion): alas y alma, con la separacion central
    for sx in (-1, 1):
        x0 = half if sx > 0 else -Lm
        ax.add_patch(Rectangle((x0, 0), Lm - half, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
        ax.add_patch(Rectangle((x0, d - tf), Lm - half, tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2))
        ax.add_patch(Rectangle((x0, tf), Lm - half, d - 2 * tf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, zorder=2, alpha=0.8))
    # placas de ala (exterior e interior) arriba y abajo
    for ytop, sg in ((0.0, -1), (d, 1)):
        ax.add_patch(Rectangle((-Lp2, ytop - (sp.fo_t if sg < 0 else 0.0)), 2 * Lp2, sp.fo_t, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.1, zorder=4))
        if g["has_inner"]:
            y_in = tf if sg < 0 else d - tf - sp.fi_t
            ax.add_patch(Rectangle((-Lp2, y_in), 2 * Lp2, sp.fi_t, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=0.9, alpha=0.8, zorder=4))
    # pernos del ala: se ven como trazos verticales que atraviesan las placas y el ala
    for sx in (-1, 1):
        for r in range(sp.f_rows):
            x = sx * (half + sp.f_end + r * sp.f_s)
            for ytop, y1 in ((-sp.fo_t, tf), (d - tf, d + sp.fo_t)):
                ax.plot([x, x], [ytop, y1], color=D.C_BOLT, lw=1.6, zorder=6)
    # placa de alma y pernos
    wx = half + sp.w_end + (sp.w_nh - 1) * sp.w_sh + sp.w_pend
    ax.add_patch(Rectangle((-wx, (d - sp.w_h) / 2), 2 * wx, sp.w_h, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.1, alpha=0.6, zorder=3))
    for sx in (-1, 1):
        for c in range(sp.w_nh):
            for r in range(sp.w_nv):
                D.bolt(ax, sx * (half + sp.w_end + c * sp.w_sh), (d - (sp.w_nv - 1) * sp.w_sv) / 2 + r * sp.w_sv, g["dhw"])
    ax.plot([0, 0], [-sp.fo_t - 1.5, d + sp.fo_t + 1.5], color="#888888", lw=0.7, ls=(0, (8, 4)), zorder=1)
    D._dim(ax, (-half, -sp.fo_t - 0.4), (half, -sp.fo_t - 0.4), -1.0, q(sp.gap) if sp.gap > 0 else "")
    D._dim(ax, (-Lp2, d + sp.fo_t + 0.5), (Lp2, d + sp.fo_t + 0.5), 1.6, f"placa de ala {q(g['Lplate'])}")
    D._dim(ax, (half, -sp.fo_t - 0.4), (half + sp.f_end, -sp.fo_t - 0.4), -2.4, f"{q(sp.f_end)}")
    ax.text(-Lp2, d + sp.fo_t + 3.4, f"Ala: placa exterior {q(sp.fo_b)}×{q(sp.fo_t)}" + (f" + 2 interiores {q(sp.fi_b)}×{q(sp.fi_t)}" if g["has_inner"] else "")
            + f";  {sp.f_rows}×{sp.f_cols} Ø{sp.bolt_size}\" {sp.bolt_grade} por lado", fontsize=7.2, color=D.C_BOLT, va="top")
    ax.text(-Lp2, d + sp.fo_t + 4.4, f"Alma: 2 placas {q(sp.w_h)}×{q(sp.w_t)};  {sp.w_nv}×{sp.w_nh} Ø{sp.wbolt_size}\" por lado", fontsize=7.2, color=D.C_BOLT, va="top")
    ax.set_xlim(-Lm - 1.5, Lm + 1.5)
    ax.set_ylim(d + sp.fo_t + 6.0, -sp.fo_t - 4.5)
    ax.set_title(f"Elevacion lateral — {title} {sp.shape}", fontsize=9)
    # planta del ala
    ax2.add_patch(Rectangle((-Lm, -bf / 2), Lm - half, bf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.5, zorder=2))
    ax2.add_patch(Rectangle((half, -bf / 2), Lm - half, bf, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.0, alpha=0.5, zorder=2))
    ax2.add_patch(Rectangle((-Lp2, -sp.fo_b / 2), 2 * Lp2, sp.fo_b, fc=D.C_PLATE, ec=D.C_PLATE_EDGE, lw=1.2, alpha=0.65, zorder=4))
    for sx in (-1, 1):
        for r in range(sp.f_rows):
            for c in range(sp.f_cols):
                D.bolt(ax2, sx * (half + sp.f_end + r * sp.f_s), (c - (sp.f_cols - 1) / 2) * sp.f_g, g["dh"])
    D._dim(ax2, (-Lp2, -bf / 2), (Lp2, -bf / 2), -1.6, f"{q(g['Lplate'])}")
    D._dim(ax2, (-Lm, -bf / 2), (-Lm, bf / 2), -1.2, f"bf = {q(bf)}", horizontal=False)
    ax2.set_xlim(-Lm - 3.5, Lm + 1.5)
    ax2.set_ylim(-bf / 2 - 3.2, bf / 2 + 1.5)
    ax2.set_title("Planta del ala (placa exterior)", fontsize=9)


# ============================================================ formulario y filas de entrada comunes
def form(attr: str, is_col: bool):
    from .formspec import G, N, num, intf, combo, check
    from .specs import BOLT_GRADES, SHEAR_BOLT_SIZES
    a = attr
    f = [
        G("Perfil (ambos lados del empalme)"),
        combo("Perfil", f"{a}.shape", "@I", editable=True, help="Perfil I de la viga o columna. Se supone el mismo perfil a ambos lados."),
        combo("Acero del perfil", f"{a}.steel", "@steel_shape"),
        combo("Acero de las placas", f"{a}.plate_steel", "@steel_plate"),
        num("Separacion entre extremos", f"{a}.gap", 0, 4, uk="L", help="Luz entre los dos extremos del perfil. En una columna con contacto se pone 0."),
    ]
    if is_col:
        f.append(check("Extremos en contacto (aserrados o fresados)", f"{a}.contact", help="AISC J1.4(a): la compresion pasa por contacto y las placas se proporcionan para el mayor entre la traccion y el 50 % de la compresion."))
    f += [
        G("Placas de ala"),
        num("Placa exterior: ancho", f"{a}.fo_b", 1, 40, uk="L", help="Una placa por ala, sobre la cara exterior."),
        num("Placa exterior: espesor", f"{a}.fo_t", 0.125, 3, uk="L"),
        num("Placas interiores: ancho (cada una)", f"{a}.fi_b", 0, 20, uk="L", help="Dos por ala, entre el ala y el alma. 0 = sin interiores (pernos en corte simple)."),
        num("Placas interiores: espesor", f"{a}.fi_t", 0, 3, uk="L"),
        G("Pernos de las alas"),
        combo("Diametro", f"{a}.bolt_size", SHEAR_BOLT_SIZES),
        combo("Calidad", f"{a}.bolt_grade", BOLT_GRADES),
        intf("Filas a cada lado del empalme", f"{a}.f_rows", 1, 12, help="Filas de pernos a lo largo del perfil, a cada lado."),
        intf("Pernos a lo ancho del ala (2 o 4)", f"{a}.f_cols", 2, 4),
        num("Paso a lo largo  s", f"{a}.f_s", 0.5, 12, uk="L"),
        num("Gramil entre columnas de pernos", f"{a}.f_g", 1, 20, uk="L"),
        num("Del extremo del perfil a la primera fila", f"{a}.f_end", 0.5, 8, uk="L"),
        num("De la ultima fila al extremo de la placa", f"{a}.f_pend", 0.5, 8, uk="L"),
        G("Placas de alma (dos, una a cada lado)"),
        num("Espesor", f"{a}.w_t", 0.125, 2, uk="L"),
        num("Altura", f"{a}.w_h", 2, 60, uk="L"),
        combo("Diametro de los pernos del alma", f"{a}.wbolt_size", SHEAR_BOLT_SIZES),
        intf("Filas verticales de pernos", f"{a}.w_nv", 1, 14),
        intf("Columnas de pernos a cada lado", f"{a}.w_nh", 1, 4),
        num("Separacion vertical", f"{a}.w_sv", 0.5, 12, uk="L"),
        num("Separacion horizontal", f"{a}.w_sh", 0.5, 12, uk="L"),
        num("Del extremo del perfil a la primera columna", f"{a}.w_end", 0.5, 8, uk="L"),
        num("De la ultima columna al extremo de la placa", f"{a}.w_pend", 0.5, 8, uk="L"),
        G("Reparto del momento"),
        combo("Criterio", f"{a}.share", SPLICE_SHARE, help="Las alas toman todo el momento (usual); o el alma toma la parte Iw/I y las alas el resto."),
        N("NO se evalua: pandeo de las placas de alma, deslizamiento critico ni la resistencia del perfil fuera del empalme."),
    ]
    return f


def input_rows(prj, sp, us, is_col: bool) -> list:
    g = geometry(sp)
    rows = [("Perfil", f"{sp.shape} ({sp.steel}); placas {sp.plate_steel}; separacion {us.q('L', sp.gap)}"),
            ("Placas de ala", f"exterior {us.q('L', sp.fo_b)} × {us.q('L', sp.fo_t)}"
                              + (f" + 2 interiores {us.q('L', sp.fi_b)} × {us.q('L', sp.fi_t)}" if g["has_inner"] else "")
                              + f"; largo total {us.q('L', g['Lplate'])}"),
            ("Pernos de ala", f"{sp.f_rows} × {sp.f_cols} por lado, Ø{sp.bolt_size} in {sp.bolt_grade}; s = {us.q('L', sp.f_s)}, g = {us.q('L', sp.f_g)}"),
            ("Placas de alma", f"2 × {us.q('L', sp.w_h)} × {us.q('L', sp.w_t)}; {sp.w_nv} × {sp.w_nh} Ø{sp.wbolt_size} in por lado; sv = {us.q('L', sp.w_sv)}, sh = {us.q('L', sp.w_sh)}"),
            ("Reparto del momento", sp.share)]
    if is_col:
        rows.append(("Contacto", "extremos en contacto (J1.4(a))" if sp.contact else "sin contacto: las placas toman toda la compresion"))
        rows.append(("Cargas (LRFD)", "; ".join(f"{n}: Pu = {us.q('F', v[0])}, Mu = {us.q('M', v[1])}, Vu = {us.q('F', v[2])}" for n, v in sp.loads())))
    else:
        rows.append(("Cargas (LRFD)", "; ".join(f"{n}: Mu = {us.q('M', v[0])}, Vu = {us.q('F', v[1])}, Nu = {us.q('F', v[2])}" for n, v in sp.loads())))
    return rows
