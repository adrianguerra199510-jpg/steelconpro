# -*- coding: utf-8 -*-
"""Empalme de viga con cubreplacas (AISC 360-22; Manual AISC, Parte 12): una viga I sigue a otra en línea y se unen con una cubreplaca exterior en cada
ala (más dos interiores opcionales, a cada lado del alma) y dos placas en el alma.  Cada grupo (alas, alma) es atornillado o soldado con filetes.

Fuerzas de diseño en la junta (el esfuerzo del miembro en su extremo junto al nudo):
    Mu = máx(|M| del caso, f·φMn),  Vu = máx(|V| del caso, f·φVn)   (f = fracción de la resistencia de la viga; 0 = solo los casos)
    Fuerza en cada ala: Ff = Mu/brazo + |N|/2  (brazo = distancia entre los centroides de las cubreplacas de las dos alas): las alas se diseñan para todo
    el momento.  El alma, para el cortante con su excentricidad hasta el centroide de los pernos (o de los filetes) de cada lado MÁS la parte del momento
    que toman las placas del alma por rigidez en la sección de la junta (donde la viga está cortada y solo trabajan las placas):
    Mw = Mu·Iw/(Iw + If), Iw = 2·tp·Hw³/12 de las placas del alma e If = ΣA·y² de las cubreplacas.  El análisis del modelo de placas muestra ese reparto,
    sobre todo con las placas soldadas (conservador: las alas siguen diseñándose para todo el momento).
Verificaciones:
    alas atornilladas  — cortante de los pernos (J3.6, doble con placas interiores), aplastamiento y desgarramiento en el ala y en las placas (J3.10),
                         fluencia y rotura de las cubreplacas (J4.1), bloque de cortante en el ala y en la placa exterior (J4.3), compresión de las placas
                         (J4.4 / E3, K = 0.65 entre los pernos más cercanos a la junta), flexión de la viga con los agujeros del ala traccionada (F13.1);
    alas soldadas      — filetes de las cubreplacas (J2.4, con los cordones transversales), metal base del ala y de la placa en los filetes (J4.2),
                         fluencia y rotura de las placas (J4.1), compresión, tamaño mínimo y máximo del filete (J2.2b);
    alma atornillada   — pernos en doble cortante con la excentricidad (método elástico), aplastamiento (J3.10), fluencia y rotura por cortante de
                         las placas (J4.2), bloque de cortante (J4.3), flexión de las placas por la excentricidad, rotura por cortante del alma de la viga;
    alma soldada       — grupo de filetes en C de cada placa (método elástico con el aumento direccional, J2.4), fluencia por cortante y flexión de las placas.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

from ... import materials as M
from ...shapes import CATALOG
from ..common import (FNV, bolt_db, edge_min, hole_std, column_fcr, elastic_bolt_group, weld_segments_elastic, block_shear_rn, E_STEEL)
from ..specs import Operation
from .base import add_check

FEXX = 70.0


@dataclass
class Splice:
    beam: str = "W18X50"
    beam_steel: str = "ASTM A992"
    main: str = "W18X50"
    op: Operation = field(default_factory=Operation)


def check_input(st) -> list:
    b = CATALOG.get(st.beam)
    if b is None or b.kind != "W":
        return [f"** El empalme con cubreplacas exige una viga I (W) del catálogo («{st.beam}»). **"]
    mn = CATALOG.get(st.main)
    out = []
    if mn is not None and abs(mn.d - b.d) > 0.13:
        out.append(f"Peraltes distintos ({st.main} y {st.beam}): el empalme necesita rellenos; se verifica con la viga conectada.")
    return out


def _wmin(t):
    """Tamaño mínimo del filete, AISC 360-22 Tabla J2.4 (por la parte más delgada)."""
    return 0.125 if t <= 0.25 else 0.1875 if t <= 0.5 else 0.25 if t <= 0.75 else 0.3125


def design(st, N=0.0, V=0.0, Mc=0.0, rec=None, info=None) -> list:
    from ..assembly import splice_layout
    op = st.op
    b = CATALOG.get(st.beam)
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    pm = M.find(M.PLATE_STEELS, op.plate_steel, 1)
    L = splice_layout(op, b)
    d, bf, tf, tw, Zx, Sx = b.d, b.bf, b.tf, b.tw, b.Zx, b.Sx
    Fy, Fu, Fyp, Fup = bm.Fy, bm.Fu, pm.Fy, pm.Fu
    db, dh = L["db"], L["dh"]
    dn = dh + 1.0 / 16.0                                              # ancho del agujero para las áreas netas (B4.3b)
    Ab = math.pi * db * db / 4.0
    rnv = FNV.get(op.bolt_grade, 54.0) * Ab
    I = info if info is not None else {}
    ck = []
    # ---- fuerzas de diseño
    kd = b.kdes if getattr(b, "kdes", 0) > 0 else tf + 0.5
    phiMn = 0.9 * Fy * Zx
    h_tw = (d - 2 * kd) / tw
    phiv = 1.0 if h_tw <= 2.24 * math.sqrt(E_STEEL / Fy) else 0.9
    phiVn = phiv * 0.6 * Fy * d * tw
    f = max(float(op.sp_cap), 0.0)
    Mu = max(abs(Mc), f * phiMn)
    Vu = max(abs(V), f * phiVn)
    to, ti, bo, bi = L["to"], L["ti"], L["bo"], L["bi"]
    Ao, Ai = bo * to, 2.0 * bi * ti
    yc = (Ao * (d / 2 + to / 2) + Ai * (d / 2 - tf - ti / 2)) / (Ao + Ai)
    arm = 2.0 * yc
    Ff = Mu / arm + abs(N) / 2.0
    tp_, Hw_ = L["tw"], L["Hw"]
    Iw = 2.0 * tp_ * Hw_ ** 3 / 12.0                                   # placas del alma
    If = 2.0 * (Ao * (d / 2 + to / 2) ** 2 + Ai * (d / 2 - tf - ti / 2) ** 2)   # cubreplacas de las dos alas
    Mw = Mu * Iw / (Iw + If)
    I.update(Mu=Mu, Vu=Vu, arm=arm, Ff=Ff, phiMn=phiMn, phiVn=phiVn, L=L, Mw=Mw)
    src = (f"Mu = {Mu:.0f} kip·in" + (f" (≥ {f:g}·φMn = {f * phiMn:.0f})" if f > 0 else "") + f"; brazo = {arm:.2f} in; N = {N:.1f} kip")
    if rec:
        rec.section(f"EMPALME DE VIGA CON CUBREPLACAS — {st.beam}")
        rec.text(f"Alas {'atornilladas' if L['fl_b'] else 'soldadas'}" + (" con cubreplacas interiores" if L["inner"] else "") + f"; alma {'atornillada' if L['we_b'] else 'soldada'}; "
                 f"cubreplaca exterior {bo:g} × {to:g} in" + (f", interiores 2 × {bi:.3g} × {ti:g} in" if L["inner"] else "") + f", placas de alma 2 × {L['Hw']:.3g} × {L['tw']:g} in, {op.plate_steel}; "
                 + (f"pernos Ø{op.bolt_size} {op.bolt_grade}; " if (L["fl_b"] or L["we_b"]) else "") + (f"filetes de {op.weld_size:g} in E70." if not (L["fl_b"] and L["we_b"]) else ""))
        rec.add("φMn", "0.9·Fy·Zx", f"0.9·{Fy:g}·{Zx:g}", phiMn, "M", "AISC 360-22 F2.1")
        rec.add("φVn", f"{phiv:g}·0.6·Fy·d·tw", "", phiVn, "F", "AISC 360-22 G2.1")
        rec.add("Mu", "máx(|M|, f·φMn)", "", Mu, "M")
        rec.add("Vu", "máx(|V|, f·φVn)", "", Vu, "F")
        rec.add("Ff", "Mu/brazo + |N|/2", f"{Mu:.0f}/{arm:.2f} + {abs(N):.1f}/2", Ff, "F", "Manual AISC Parte 12")
        rec.add("Mw", "Mu·Iw/(Iw + If)", f"{Mu:.0f}·{Iw:.0f}/({Iw:.0f} + {If:.0f})", Mw, "M", "parte del momento que toman las placas del alma, por rigidez en la sección de la junta")
    # ================================================================ alas
    Ag_p = Ao + Ai
    if L["fl_b"]:
        nf = L["nf"]
        nb = 2 * nf
        planes = 2 if L["inner"] else 1
        add_check(ck, rec, "sp_fb", f"Alas — cortante de los pernos ({nb} por lado, {'doble' if planes == 2 else 'simple'} cortante)", Ff, 0.75 * rnv * nb * planes, "kip",
                  "AISC 360-22 J3.6", f"{src}; φrn = 0.75·{FNV.get(op.bolt_grade, 54.0):g}·{Ab:.3f} = {0.75 * rnv:.1f} kip por plano"
                  + ("; doble cortante: la exterior y las interiores tienen áreas parecidas" if planes == 2 else ""))
        s, e = L["s"], L["e"]

        def bear(t, Fu_, e_end):
            lc = [e_end - dh / 2.0] + [s - dh] * (nf - 1)
            return 0.75 * 2.0 * sum(min(1.2 * max(l_, 0) * t * Fu_, 2.4 * db * t * Fu_) for l_ in lc)
        add_check(ck, rec, "sp_fbr", "Alas — aplastamiento y desgarramiento en el ala de la viga", Ff, bear(tf, Fu, e), "kip", "AISC 360-22 J3.10",
                  f"lc = {e - dh / 2:.2f} in (extremo de la viga) y {s - dh:.2f} in; t = tf = {tf:g} in")
        add_check(ck, rec, "sp_fbp", "Alas — aplastamiento y desgarramiento en las cubreplacas", Ff, bear(to + ti, Fup, e), "kip", "AISC 360-22 J3.10",
                  f"t = {to + ti:g} in (exterior" + (" + interior)" if L["inner"] else ")"))
        An = Ag_p - 2.0 * dn * (to + ti)
        Ae = min(An, 0.85 * Ag_p)
        add_check(ck, rec, "sp_fy", "Cubreplacas — fluencia por tracción", Ff, 0.9 * Fyp * Ag_p, "kip", "AISC 360-22 J4.1(a)", f"Ag = {Ag_p:.2f} in²")
        add_check(ck, rec, "sp_fr", "Cubreplacas — rotura por tracción en la sección neta", Ff, 0.75 * Fup * Ae, "kip", "AISC 360-22 J4.1(b)",
                  f"An = {An:.2f} in², Ae = mín(An, 0.85·Ag) = {Ae:.2f} in²")
        Lgv = e + (nf - 1) * s
        Lnv = Lgv - (nf - 0.5) * dh
        share_o = Ao / Ag_p
        bs_o = min(block_shear_rn(Fyp, Fup, to, 2 * Lgv, 2 * Lnv, L["gf"] - dh),                            # entre las dos líneas
                   block_shear_rn(Fyp, Fup, to, 2 * Lgv, 2 * Lnv, (bo - L["gf"]) - dh))                      # de cada línea al borde
        add_check(ck, rec, "sp_fbs", "Cubreplaca exterior — bloque de cortante", Ff * share_o, 0.75 * bs_o, "kip", "AISC 360-22 J4.3",
                  f"parte de Ff en la exterior: {share_o:.2f}; Lgv = 2 × {Lgv:.2f} in")
        bs_f = block_shear_rn(Fy, Fu, tf, 2 * Lgv, 2 * Lnv, (bf - L["gf"]) - dh)
        add_check(ck, rec, "sp_fbsb", "Ala de la viga — bloque de cortante", Ff, 0.75 * bs_f, "kip", "AISC 360-22 J4.3", "cortante a lo largo de las dos líneas, tracción hacia los bordes del ala")
        Lc = 2.0 * L["xs_f"][0]
        tmin = min(to, ti) if L["inner"] else to
        KLr = 0.65 * Lc / (tmin / math.sqrt(12.0))
        Fcr = Fyp if KLr <= 25 else column_fcr(Fyp, KLr)
        add_check(ck, rec, "sp_fc", "Cubreplacas — compresión", Ff, 0.9 * Fcr * Ag_p, "kip", "AISC 360-22 J4.4" + ("" if KLr <= 25 else ", E3"),
                  f"KL/r = 0.65·{Lc:.2f}/({tmin:g}/√12) = {KLr:.1f}")
        Afg = bf * tf
        Afn = Afg - 2.0 * dn * tf
        Yt = 1.0 if Fy / Fu <= 0.8 else 1.1
        Mn_h = Zx * Fy if Fu * Afn >= Yt * Fy * Afg else Fu * Afn / Afg * Sx
        add_check(ck, rec, "sp_f13", "Viga — flexión en la sección con los agujeros del ala traccionada", Mu, 0.9 * Mn_h, "kip·in", "AISC 360-22 F13.1",
                  f"Fu·Afn = {Fu * Afn:.0f} {'≥' if Fu * Afn >= Yt * Fy * Afg else '<'} Yt·Fy·Afg = {Yt * Fy * Afg:.0f} kip")
        add_check(ck, rec, "sp_fe", "Alas — distancia del perno al extremo de la viga y al borde de la placa", edge_min(db), e, "in", "AISC 360-22 Tabla J3.4")
    else:
        w = float(op.weld_size)
        lf = L["lf"]
        q = 0.6 * FEXX * 0.707 * w
        Rl, Rt = q * 2 * lf, q * bo
        Rn_o = max(Rl + Rt, 0.85 * Rl + 1.5 * Rt)
        Rn_i = (q * 2 * lf * 2) if L["inner"] else 0.0
        add_check(ck, rec, "sp_fw", "Alas — filetes de las cubreplacas sobre cada viga", Ff, 0.75 * (Rn_o + Rn_i), "kip", "AISC 360-22 J2.4 (J2-10)",
                  f"{src}; exterior: 2 × {lf:g} in longitudinales + {bo:g} in transversal, Rn = máx(Rwl + Rwt, 0.85·Rwl + 1.5·Rwt) = {Rn_o:.0f} kip"
                  + (f"; interiores: 2 × 2 × {lf:g} in = {Rn_i:.0f} kip" if L["inner"] else ""))
        add_check(ck, rec, "sp_fwb", "Ala de la viga — metal base en los filetes (cortante)", Ff, 0.75 * 0.6 * Fu * tf * (2 * lf) * (2 if L["inner"] else 1) + 0.75 * Fu * tf * bo, "kip",
                  "AISC 360-22 J4.2(b), J2.4", "rotura por cortante a lo largo de los filetes longitudinales y por tracción en el transversal")
        add_check(ck, rec, "sp_fwp", "Cubreplaca exterior — metal base en los filetes", Ff * Ao / Ag_p, 0.75 * (0.6 * Fup * to * 2 * lf + Fup * to * bo), "kip", "AISC 360-22 J4.3")
        add_check(ck, rec, "sp_fy", "Cubreplacas — fluencia por tracción", Ff, 0.9 * Fyp * Ag_p, "kip", "AISC 360-22 J4.1(a)", f"Ag = {Ag_p:.2f} in²")
        add_check(ck, rec, "sp_fr", "Cubreplacas — rotura por tracción (sin agujeros, U = 1 con cordón transversal)", Ff, 0.75 * Fup * Ag_p, "kip", "AISC 360-22 J4.1(b), D3")
        tmin = min(to, ti) if L["inner"] else to
        KLr = 0.65 * max(L["gap"], 0.25) / (tmin / math.sqrt(12.0))
        add_check(ck, rec, "sp_fc", "Cubreplacas — compresión (tramo libre en la junta)", Ff, 0.9 * (Fyp if KLr <= 25 else column_fcr(Fyp, KLr)) * Ag_p, "kip", "AISC 360-22 J4.4")
        add_check(ck, rec, "sp_fwmin", "Alas — tamaño mínimo del filete", _wmin(min(to, tf)), w, "in", "AISC 360-22 Tabla J2.4")
        add_check(ck, rec, "sp_fwmax", "Alas — tamaño máximo del filete en el borde de la placa", w, (to - 1 / 16) if to >= 0.25 else to, "in", "AISC 360-22 J2.2b")
    # ================================================================ alma
    tp, Hw = L["tw"], L["Hw"]
    Ag_w = 2.0 * Hw * tp
    if L["we_b"]:
        pts = [(x, y) for x in L["xs_w"] for y in L["ys"]]
        xbar = sum(p_[0] for p_ in pts) / len(pts)
        ecc = xbar                                                    # del centro de la junta al centroide de los pernos de un lado
        forces = elastic_bolt_group([(x - xbar, y) for x, y in pts], 0.0, Vu, Vu * ecc + Mw)
        rmax = max(math.hypot(*f_) for f_ in forces)
        add_check(ck, rec, "sp_wb", f"Alma — pernos en doble cortante con la excentricidad ({len(pts)} por lado)", rmax, 0.75 * rnv * 2, "kip", "AISC 360-22 J3.6; Manual Parte 7 (método elástico)",
                  f"Vu = {Vu:.1f} kip; e = {ecc:.2f} in; Mw = {Mw:.0f} kip·in; perno más cargado {rmax:.1f} kip")
        ev = (Hw - (L["nw"] - 1) * L["s"]) / 2.0
        xw, x_end = L["xw"], L["gap"] / 2.0                            # placa: |x| ≤ xw, |y| ≤ Hw/2; extremo de la viga en x = gap/2

        def ray(x, y, ux, uy, box):                                    # distancia desde (x, y) al borde del rectángulo box en ±u (la menor de las dos)
            x0, x1, y0, y1 = box
            best = 1e9
            for sg in (1.0, -1.0):
                tx, ty = sg * ux, sg * uy
                ts = [t_ for t_ in ((((x1 if tx > 0 else x0) - x) / tx) if abs(tx) > 1e-9 else 1e9, (((y1 if ty > 0 else y0) - y) / ty) if abs(ty) > 1e-9 else 1e9) if t_ >= 0]
                best = min(best, min(ts) if ts else 1e9)
            return best
        worst = (0.0, 0.0, 1.0, 0.0, 0.0)
        for (x, y), (fx_, fy_) in zip(pts, forces):
            r_ = math.hypot(fx_, fy_)
            if r_ <= 0:
                continue
            ux, uy = fx_ / r_, fy_ / r_
            l_pl = ray(x, y, ux, uy, (-xw, xw, -Hw / 2.0, Hw / 2.0)) - dh / 2.0
            l_bm = ((x - x_end) / abs(ux) if abs(ux) > 1e-9 else 1e9) - dh / 2.0      # alma de la viga: solo el extremo de la viga es borde (las alas la rodean)
            rn = min(min(1.2 * l_bm * tw * Fu, 2.4 * db * tw * Fu), min(1.2 * l_pl * 2 * tp * Fup, 2.4 * db * 2 * tp * Fup))
            if r_ / (0.75 * rn) > worst[0]:
                worst = (r_ / (0.75 * rn), r_, 0.75 * rn, l_bm, l_pl)
        add_check(ck, rec, "sp_wbr", "Alma — aplastamiento y desgarramiento (perno más exigido)", worst[1], worst[2], "kip", "AISC 360-22 J3.10",
                  f"lc en la dirección de la fuerza de cada perno (en los dos sentidos): alma de la viga {min(worst[3], 99):.2f} in, placas {min(worst[4], 99):.2f} in; "
                  f"t = tw = {tw:g} y 2·tp = {2 * tp:g} in")
        nw = L["nw"]
        add_check(ck, rec, "sp_wvy", "Placas del alma — fluencia por cortante", Vu, 1.0 * 0.6 * Fyp * Ag_w, "kip", "AISC 360-22 J4.2(a)")
        Anv = 2.0 * (Hw - nw * dn) * tp
        add_check(ck, rec, "sp_wvr", "Placas del alma — rotura por cortante", Vu, 0.75 * 0.6 * Fup * Anv, "kip", "AISC 360-22 J4.2(b)", f"Anv = {Anv:.2f} in²")
        Lgv = ev + (nw - 1) * L["s"]
        Lnv = Lgv - (nw - 0.5) * dh
        Lnt = (L["xw"] - L["xs_w"][0]) - (L["cw"] - 0.5) * dh
        add_check(ck, rec, "sp_wbs", "Placas del alma — bloque de cortante", Vu, 0.75 * 2 * block_shear_rn(Fyp, Fup, tp, Lgv, Lnv, Lnt), "kip", "AISC 360-22 J4.3")
        Zp = 2 * tp * Hw * Hw / 4.0
        add_check(ck, rec, "sp_wf", "Placas del alma — flexión (excentricidad y Mw)", Vu * ecc + Mw, 0.9 * Fyp * Zp, "kip·in", "AISC 360-22 F11")
        add_check(ck, rec, "sp_wbeam", "Alma de la viga — rotura por cortante en la línea de pernos", Vu, 0.75 * 0.6 * Fu * (d - nw * dn) * tw, "kip", "AISC 360-22 J4.2(b)")
    else:
        w = float(op.weld_size)
        lw = L["lw"]
        segs = [(0.0, Hw / 2, lw, Hw / 2), (0.0, -Hw / 2, lw, -Hw / 2), (lw, -Hw / 2, lw, Hw / 2)]
        r = weld_segments_elastic(segs, 0.0, Vu / 2.0, -L["gap"] / 2.0, 0.0, w, FEXX, M0=-Mw / 2.0)   # mismo sentido que el de la excentricidad (se suman)
        add_check(ck, rec, "sp_ww", "Alma — filetes en C de cada placa (método elástico)", r["f"], r["cap"], "kip/in", "AISC 360-22 J2.4 (J2-5)",
                  f"Vu/2 = {Vu / 2:.1f} kip por placa aplicado en la junta y Mw/2 = {Mw / 2:.0f} kip·in; filetes de {w:g} in: 2 × {lw:g} + {Hw:.3g} in; θ = {r['theta']:.0f}°")
        add_check(ck, rec, "sp_wvy", "Placas del alma — fluencia por cortante", Vu, 1.0 * 0.6 * Fyp * Ag_w, "kip", "AISC 360-22 J4.2(a)")
        Zp = 2 * tp * Hw * Hw / 4.0
        add_check(ck, rec, "sp_wf", "Placas del alma — flexión en la junta", Vu * (L["gap"] / 2 + lw) + Mw, 0.9 * Fyp * Zp, "kip·in", "AISC 360-22 F11")
        add_check(ck, rec, "sp_wbm", "Alma de la viga — metal base en los filetes", Vu, 0.75 * 0.6 * Fu * tw * Hw, "kip", "AISC 360-22 J4.2(b)", "rotura por cortante del alma a lo largo de la línea vertical de filetes")
        add_check(ck, rec, "sp_wwmin", "Alma — tamaño mínimo del filete", _wmin(min(tp, tw)), w, "in", "AISC 360-22 Tabla J2.4")
    return ck


def solve_one(p, name, vals, rec):
    """Interfaz de motor (adapters): vals = (N, Vz, My) del extremo del miembro en la junta."""
    N, V, Mc = (tuple(vals) + (0.0, 0.0, 0.0))[:3]
    return design(p.splice, N, V, Mc, rec)


def warnings(st) -> list:
    w = ["Empalme con cubreplacas: las alas se diseñan para todo el momento (y la mitad del axial cada una); el alma, para el cortante con su excentricidad y la parte del momento que toman sus placas por rigidez (Mw = Mu·Iw/(Iw + If))."]
    if st.op.sp_inner and st.op.sp_flange != "Soldada":
        w.append("Empalme: pernos de las alas en doble cortante con las cubreplacas interiores (supone áreas parecidas de la exterior y de las interiores).")
    return w
