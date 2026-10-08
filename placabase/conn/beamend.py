# -*- coding: utf-8 -*-
"""Extremo de una viga apoyada con una fila vertical de pernos en el alma (con o sin cope).

Geometria y verificaciones del alma (cortante, bloque de cortante, flexion en el cope) compartidas por las
conexiones de corte: placa simple, doble angulo, etc.  Coordenadas verticales desde el tope de la viga, hacia abajo;
horizontales desde la cara del soporte hacia la viga.  in, kip, ksi.
"""
from __future__ import annotations

from .base import add_check, not_evaluated
from .common import PHI_RUPT, PHI_YIELD, PHI_FLEX, block_shear_rn, coped_section


def geometry(beam, n, s, a, gap, y_top, cope_top, cope_bot, cope_len):
    """Derivados del extremo de la viga: alma que queda, posicion del grupo de pernos y brazo del cope.
    `a` = distancia de la cara del soporte a la fila de pernos; `gap` = retranqueo del extremo de la viga."""
    ct, cb = max(cope_top, 0.0), max(cope_bot, 0.0)
    Lb = (max(int(n), 1) - 1) * s
    g = dict(ct=ct, cb=cb, coped=(ct > 0 or cb > 0), Lb=Lb)
    if beam is None:
        return g
    web_lo, web_hi = ct, beam.d - cb
    g["h0"] = beam.d - ct - cb
    g["y_top"] = y_top if y_top >= 0 else 0.5 * (web_lo + web_hi) - 0.5 * Lb
    g["lev_t"] = g["y_top"] - web_lo                        # del borde superior del alma al perno superior
    g["lev_b"] = web_hi - (g["y_top"] + Lb)                 # del perno inferior al borde inferior del alma
    g["leh_b"] = a - gap                                    # del extremo de la viga a la fila de pernos
    g["x_cope"] = gap + max(cope_len, 0.0)                  # de la cara del soporte al fin del cope
    g["e_cope"] = max(0.0, g["x_cope"] - a)                 # brazo del momento en la seccion con cope
    return g


def web_checks(ck, rec, u, g, beam, bm, Vu, n, s, dhn, memo_title="VIGA APOYADA"):
    """Alma de la viga: fluencia y rotura por cortante, bloque de cortante (cope superior) y flexion en el cope."""
    tw, h0 = beam.tw, g["h0"]
    Rwy = PHI_YIELD * 0.6 * bm.Fy * tw * h0
    Rwr = PHI_RUPT * 0.6 * bm.Fu * tw * (h0 - n * dhn)
    if rec:
        rec.section(memo_title + (" — CON COPE" if g["coped"] else ""))
        rec.add("φRn,fl", "1.00·0.6·Fy·tw·h0", f"0.6·{rec.n('S', bm.Fy)}·{rec.n('L', tw)}·{rec.n('L', h0)}", Rwy, "F",
                "AISC J4.2(a) / G2.1")
        rec.add("φRn,rot", "0.75·0.6·Fu·tw·(h0 − n·dh')",
                f"0.6·{rec.n('S', bm.Fu)}·{rec.n('L', tw)}·({rec.n('L', h0)} − {n}·{rec.n('L', dhn)})", Rwr, "F",
                "AISC J4.2(b)")
    add_check(ck, rec, "web_vy", "Alma de la viga — fluencia por cortante" + (" (en el cope)" if g["coped"] else ""),
              Vu, Rwy, "kip", "AISC J4.2(a) / G2.1")
    add_check(ck, rec, "web_vr", "Alma de la viga — rotura por cortante neto", Vu, Rwr, "kip", "AISC J4.2(b)")
    if g["ct"] > 0:
        Lgv = g["lev_t"] + (n - 1) * s
        Lnv = Lgv - (n - 0.5) * dhn
        Lnt = g["leh_b"] - 0.5 * dhn
        Rbs = PHI_RUPT * block_shear_rn(bm.Fy, bm.Fu, tw, Lgv, Lnv, Lnt)
        add_check(ck, rec, "web_bs", "Alma de la viga — bloque de cortante (cope superior)", Vu, Rbs, "kip", "AISC J4.3",
                  f"Lgv = {u.q('L', Lgv)}, Lnv = {u.q('L', Lnv)}, Lnt = {u.q('L', Lnt)}, Ubs = 1.0 (una fila)")
    if g["coped"]:
        cs = coped_section(beam, g["ct"], g["cb"])
        Mc = Vu * g["e_cope"]
        phiMc = PHI_FLEX * bm.Fy * cs["S"]
        add_check(ck, rec, "cope_flex", "Seccion con cope — fluencia por flexion", Mc, phiMc, "kip·in",
                  "AISC F / Manual Parte 9", f"Mu = Vu·e = {u.q('M', Mc)};  Snet = {cs['S'] / u.fl ** 3:.4g} {u.L}³")
        not_evaluated(ck, "cope_lwb", "Pandeo local del alma por cope", "Manual 15a Ed., Parte 9")


def cope_warnings(st_gap, st_cope_len, st_top_flush, g, beam, sup, sup_is_girder_web) -> list:
    """Avisos de cope: pandeo local no evaluado y holgura frente al ala de la viga maestra."""
    w = []
    if g["coped"]:
        w.append("NO EVALUADO: pandeo local del alma de la viga por cope (Manual Parte 9). Verifiquelo aparte; "
                 "la 15a Ed. cambio el procedimiento (Dowswell, EJ 2018).")
        if st_top_flush and sup is not None and sup_is_girder_web:
            c_req = max(0.0, (sup.bf - sup.tw) / 2 + 0.5 - st_gap)
            d_req = max(beam.tf, sup.tf) + 0.5
            if st_cope_len < c_req - 1e-9 or g["ct"] < d_req - 1e-9:
                w.append(f"Cope menor que el recomendado para librar el ala de la viga maestra a ras: "
                         f"longitud >= {c_req:.2f} in y profundidad >= {d_req:.2f} in (holgura de 1/2 in supuesta).")
    elif st_top_flush and sup_is_girder_web:
        w.append("Tope a ras con la viga maestra pero sin cope: el ala de la viga apoyada choca con el ala del soporte.")
    return w
