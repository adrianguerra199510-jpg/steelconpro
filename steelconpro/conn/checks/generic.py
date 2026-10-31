# -*- coding: utf-8 -*-
"""Verificaciones de la cartela de una diagonal y de las alas soldadas de una conexion a momento (AISC 360-22).

Cartela atornillada (dos pernos por fila, `n_bolts` filas): cortante y aplastamiento de los pernos, aplastamiento del miembro y de la cartela,
fluencia y rotura en el ancho de Whitmore, bloque de cortante de la cartela, fluencia y rotura del miembro, y soldadura de la cartela al principal
(resultante de la fuerza, sin descomponer: conservador).  Con el miembro soldado a la cartela: soldadura del miembro.
No se evalua: pandeo del miembro en compresion, pandeo de la cartela por compresion fuera de lo simplificado, ni el reparto de fuerzas del UFM.

Alas soldadas (CJP): fuerza del ala por momento y axial contra la fluencia del ala de la viga.
"""
from __future__ import annotations
import math

from ... import materials as M
from ...design import Check
from ...shapes import CATALOG, W_SHAPE
from ..common import (PHI_BOLT, PHI_RUPT, PHI_YIELD, bolt_db, hole_std, hole_net, bolt_shear_rn, bearing_rn, block_shear_rn, edge_min)
from ..specs import OP_GUSSET, OP_GUSSET_W, OP_WELD
from .base import add_check, not_evaluated

PHI_COMP = 0.90
PHI_WELD = 0.75
E_STEEL = 29000.0


def _member_axial_props(shape):
    """(area bruta, espesor que recibe los pernos, planos de corte, perimetro soldable) del miembro."""
    if shape.is_hollow:
        per = math.pi * shape.d if shape.is_round else 2.0 * (shape.d + shape.bf)
        return shape.A, shape.tw, 2, per
    t = shape.tw if shape.tw > 0 else 0.3
    per = 2.0 * (shape.d + 2.0 * shape.bf) if shape.kind == W_SHAPE else 2.0 * (shape.d + shape.bf)
    return shape.A, t, 1, per


def solve_one(prj, nd, op, m, vals, rec):
    from ..specs import OP_TAB
    if op.kind == OP_TAB:
        return _tab_weld(nd, op, m, vals, rec)
    if op.kind == OP_WELD:
        return _flange_welds(nd, op, m, vals, rec)
    return _gusset(nd, op, m, vals, rec)


def _flange_welds(nd, op, m, vals, rec):
    N, Vy, Vz, T, My, Mz = vals
    ck = []
    beam = CATALOG.get(m.shape)
    if beam is None or beam.kind != W_SHAPE:
        not_evaluated(ck, "wf", "Soldadura de las alas", "AISC 360-22 J2", "Solo para vigas I.")
        return ck
    bm = M.find(M.SHAPE_STEELS, m.steel)
    Pf = abs(My) / max(beam.d - beam.tf, 1e-6) + max(N, 0.0) / 2.0
    cap = 0.9 * bm.Fy * beam.bf * beam.tf                                    # φ = 0.90
    if rec:
        rec.add("Pf", "|My| / (d − tf) + N / 2", f"{rec.n('M', abs(My))} / ({rec.n('L', beam.d)} − {rec.n('L', beam.tf)}) + {rec.n('F', max(N, 0.0))} / 2", Pf, "F",
                "fuerza del ala traccionada")
    add_check(ck, rec, "wf_flange", "Alas soldadas (CJP): fuerza del ala ≤ φ·Fy·bf·tf", Pf, cap, "kip", "AISC 360-22 J2.5 / F13",
              "Soldadura de penetración completa con metal de aporte compatible: la resistencia la da el ala. Las verificaciones locales de la columna (J10) no se evalúan.")
    return ck


def _gusset(nd, op, m, vals, rec):
    N, Vy, Vz, T, My, Mz = vals
    ck = []
    shp = CATALOG.get(m.shape)
    if shp is None:
        return ck
    P = abs(N)
    tens = N >= 0
    pl = M.find(M.PLATE_STEELS, op.plate_steel, 1)
    mm = M.find(M.SHAPE_STEELS, m.steel)
    Ag, t_m, planes, per = _member_axial_props(shp)
    t = max(op.plate_t, 1e-3)
    fexx = 70.0
    bolted = op.kind == OP_GUSSET
    if rec:
        rec.add("P", "fuerza axial del miembro", "", P, "F", note="tracción" if tens else "compresión")
    if P < 1e-9:
        not_evaluated(ck, "g0", "Cartela sin fuerza axial en el miembro", "AISC 360-22 J", "Defina la carga axial N del miembro en «Cargas».")
        return ck
    if bolted:
        db = bolt_db(op.bolt_size)
        dh, dhn = hole_std(db), hole_net(db)
        rows = max(int(op.n_bolts), 1)
        s = max(op.bolt_s, 2.5 * db)
        nb = 2 * rows
        Vb = P / nb
        phiRn_v = PHI_BOLT * bolt_shear_rn(db, op.bolt_grade) * planes
        add_check(ck, rec, "g_bolt", f"Pernos de la cartela ({nb} × Ø{op.bolt_size}, {planes} plano{'s' if planes > 1 else ''}): cortante por perno", Vb, phiRn_v, "kip",
                  "AISC 360-22 J3.6", "Reparto uniforme entre los pernos.")
        Lc = min(1.5 - dh / 2.0, s - dh)
        add_check(ck, rec, "g_brg_m", "Aplastamiento del miembro en un perno", Vb / (2 if planes == 2 else 1),
                  PHI_BOLT * bearing_rn(db, t_m, mm.Fu, Lc), "kip", "AISC 360-22 J3.10", f"t = {t_m:g} in; Lc = {Lc:.2f} in")
        add_check(ck, rec, "g_brg_p", "Aplastamiento de la cartela en un perno", Vb, PHI_BOLT * bearing_rn(db, t, pl.Fu, Lc), "kip", "AISC 360-22 J3.10", f"t = {t:g} in")
        gauge = max(min(shp.d * 0.5, 6.0), 2.5)
        Lb = (rows - 1) * s
        Lw = 2.0 * Lb * math.tan(math.radians(30.0)) + gauge                 # ancho de Whitmore
        phiPy = PHI_COMP * pl.Fy * t * Lw
        if tens:
            add_check(ck, rec, "g_whit_y", "Cartela: fluencia en el ancho de Whitmore", P, phiPy, "kip", "AISC 360-22 J4.1(a)", f"Lw = {Lw:.2f} in")
            phiPu = PHI_RUPT * pl.Fu * t * max(Lw - 2.0 * dhn, 0.0)
            add_check(ck, rec, "g_whit_u", "Cartela: rotura en el ancho de Whitmore (sección neta)", P, phiPu, "kip", "AISC 360-22 J4.1(b)", "Dos agujeros en la última fila.")
            Lgv = Lb + 1.5
            Lnv = Lgv - (rows - 0.5) * dhn
            Ant = pl.Fu * t * max(gauge - dhn, 0.0)
            Rbs = min(0.6 * pl.Fu * t * Lnv * 2.0 + Ant, 0.6 * pl.Fy * t * Lgv * 2.0 + Ant)
            add_check(ck, rec, "g_bs", "Cartela: bloque de cortante", P, PHI_RUPT * Rbs, "kip", "AISC 360-22 J4.3", "Dos planos de cortante y un plano de tracción entre columnas.")
        else:
            Lfree = 2.0 + 1.5                                                  # distancia de la cara del principal a la primera fila, aprox.
            r = t / math.sqrt(12.0)
            KLr = 0.65 * Lfree / r
            Fe = math.pi ** 2 * E_STEEL / max(KLr, 1e-6) ** 2
            Fcr = (0.658 ** (pl.Fy / Fe)) * pl.Fy if KLr <= 4.71 * math.sqrt(E_STEEL / pl.Fy) else 0.877 * Fe
            add_check(ck, rec, "g_whit_c", "Cartela en compresión: fluencia / pandeo en el ancho de Whitmore", P, PHI_COMP * Fcr * t * Lw, "kip",
                      "AISC 360-22 E3 (K = 0.65)", f"Lw = {Lw:.2f} in; L = {Lfree:.1f} in: verificación simplificada")
        if tens:
            An = Ag - 2.0 * dhn * t_m * (2 if shp.is_hollow else 1) * 0.5
            Ae = 0.8 * An                                                         # U = 0.8 (simplificado)
            add_check(ck, rec, "g_mem_y", "Miembro: fluencia en la sección bruta", P, PHI_COMP * mm.Fy * Ag, "kip", "AISC 360-22 D2(a)")
            add_check(ck, rec, "g_mem_u", "Miembro: rotura en la sección neta efectiva", P, PHI_RUPT * mm.Fu * Ae, "kip", "AISC 360-22 D2(b)", "U = 0.8 (simplificado).")
        else:
            not_evaluated(ck, "g_mem_c", "Pandeo del miembro en compresión", "AISC 360-22 E3", "Depende de su longitud y arriostramiento.")
    else:
        Lw_w = per
        w = max(op.weld_size, 0.0625)
        add_check(ck, rec, "g_wm", "Soldadura del miembro a la cartela (perímetro)", P, PHI_WELD * 0.6 * fexx * 0.707 * w * Lw_w, "kip", "AISC 360-22 J2.4",
                  f"Filete de {w:g} in en {Lw_w:.1f} in de perímetro; sin incremento direccional.")
        add_check(ck, rec, "g_mem_y", "Miembro: fluencia en la sección bruta", P, PHI_COMP * mm.Fy * Ag, "kip", "AISC 360-22 D2(a)") if tens else \
            not_evaluated(ck, "g_mem_c", "Pandeo del miembro en compresión", "AISC 360-22 E3", "Depende de su longitud y arriostramiento.")
    # soldadura de la cartela al miembro principal
    dm = max(min(shp.d, 16.0), 4.0)
    Lbase = max(dm * 1.05, 7.0)
    wg = max(op.weld_size, 0.0625)
    add_check(ck, rec, "g_wp", "Soldadura de la cartela al miembro principal (dos lados)", P, PHI_WELD * 0.6 * fexx * 0.707 * wg * 2.0 * Lbase, "kip", "AISC 360-22 J2.4",
              f"Filete de {wg:g} in, {Lbase:.1f} in de base a cada lado; la fuerza se toma completa (resultante, sin descomponer).")
    not_evaluated(ck, "g_ufm", "Reparto de fuerzas de interfaz de la cartela (UFM)", "AISC Manual Parte 13", "Los esfuerzos locales del principal no se evalúan.")
    return ck


def _tab_weld(nd, op, m, vals, rec):
    """Placa simple soldada al alma de la viga conectada: filetes en el borde superior, el inferior y el del extremo de la placa (traslape sobre el alma)."""
    from ..assembly import tab_dims, tab_extra, gap_eff
    from ..common import bolt_db
    N, Vy, Vz, T, My, Mz = vals
    ck = []
    beam = CATALOG.get(m.shape)
    if beam is None or beam.is_hollow:
        not_evaluated(ck, "tw", "Soldadura de la placa a la viga", "AISC 360-22 J2.4", "Solo para vigas I.")
        return ck
    n, s_, cols, g_, H, Wd, a = tab_dims(op, m, beam, bolt_db(op.bolt_size), tab_extra(nd, m, op))
    ov = max(Wd - gap_eff(m) - tab_extra(nd, m, op), 0.1)
    L = 2.0 * ov + H
    w = float(op.weld_size)
    V = abs(Vz)
    pl = M.find(M.PLATE_STEELS, op.plate_steel, 1)
    bm = M.find(M.SHAPE_STEELS, m.steel)
    fexx = 70.0
    if rec:
        rec.section(f"{op.kind.upper()} — {m.name}: soldadura de la placa al alma")
        rec.text(f"Placa {H:g} × {Wd:g} × {op.plate_t:g} in traslapada {ov:g} in sobre el alma; filete {w:g} in en el borde superior, el inferior y el del extremo (L = {L:g} in).")
    add_check(ck, rec, "tw_weld", f"Soldadura de la placa al alma: V ≤ φ·0.6·FEXX·0.707·w·L  (L = {L:g} in)", V, 0.75 * 0.60 * fexx * 0.707 * w * L, "kip", "AISC 360-22 J2.4",
              "Cortante repartido por igual en la longitud del cordón; no incluye la excentricidad del cortante respecto del grupo de soldadura (verifíquela aparte).")
    add_check(ck, rec, "tw_sup", f"Soldadura de la placa al soporte: V ≤ φ·0.6·FEXX·0.707·w·2H  (2H = {2 * H:g} in)", V, 0.75 * 0.60 * fexx * 0.707 * w * 2.0 * H, "kip", "AISC 360-22 J2.4",
              "Dos filetes del mismo cateto en la cara del soporte; sin excentricidad.")
    add_check(ck, rec, "tw_plate_y", "Placa: fluencia por cortante", V, 1.00 * 0.60 * pl.Fy * H * op.plate_t, "kip", "AISC 360-22 J4.2(a)", "φ = 1.00")
    add_check(ck, rec, "tw_web", "Alma de la viga: rotura por cortante en el cordón", V, 0.75 * 0.60 * bm.Fu * beam.tw * H, "kip",
              "AISC 360-22 J4.2(b)", "Se toma la altura de la placa sobre el alma (φ = 0.75).")
    add_check(ck, rec, "tw_min", "Cateto mínimo del filete", M.min_fillet(min(op.plate_t, beam.tw)), w, "in", "AISC 360-22 Tabla J2.4", "Se compara con la parte más delgada.", skip=False)
    return ck
