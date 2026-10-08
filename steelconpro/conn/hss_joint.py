# -*- coding: utf-8 -*-
"""Nudos de celosia HSS a HSS (diagonales soldadas directamente al cordon), AISC 360-22 Cap. K.

Redondos (Tabla K3.1): γ = D/(2t), β = Db/D, Qf = 1 (cordon traccionado) o 1 − 0.3·U·(1 + U), U = |Pro/(Fy·Ag)|:
    T, Y   plastificacion del cordon   φPn·senθ = 0.90·Fy·t²·(3.1 + 15.6·β²)·γ^0.2·Qf
    X      plastificacion del cordon   φPn·senθ = 0.90·Fy·t²·[5.7/(1 − 0.81·β)]·Qf
    K, N   con separacion g            φPn·senθ = 0.90·Fy·t²·(2.0 + 11.33·Db,c/D)·Qg·Qf     (diagonal comprimida; la traccionada tiene el mismo Pn·senθ)
           Qg = γ^0.2·[1 + 0.024·γ^1.2/(exp(0.5·g/t − 1.33) + 1)]
    corte por punzonamiento (Db ≤ D − 2t):  φPn = 0.95·0.6·Fy·t·π·Db·(1 + senθ)/(2·sen²θ)
Rectangulares (Tabla K3.2A, T, Y, X con β ≤ 0.85): γ = B/(2t), β = Bb/B, η = Hb/B, Qf = 1 (traccion) o 1.3 − 0.4·U/β ≤ 1:
    plastificacion de la pared del cordon   φPn·senθ = 0.90·Fy·t²·[2η/(1 − β) + 4/√(1 − β)]·Qf
Los limites de validez (β, D/t, θ ≥ 30°, Fy ≤ 52 ksi, Fy/Fu ≤ 0.8, g ≥ tb1 + tb2) se tratan como avisos criticos: fuera de ellos las
ecuaciones no aplican.  NO se evaluan: nudos rectangulares K/N con separacion, β > 0.85, cortante del cordon en la separacion, el miembro
diagonal, la soldadura diagonal-cordon ni la excentricidad del nudo.
"""
from __future__ import annotations
import math

from .. import materials as M
from ..shapes import CATALOG
from .base import run_combos, add_check, not_evaluated
from .formspec import G, N, num, combo
from .specs import CT_HSS, HSS_SHAPES, HSS_TYPES

NAME = CT_HSS
PHI_CW = 0.90        # plastificacion del cordon
PHI_PS = 0.95        # punzonamiento


def _round(st):
    return st.shape == HSS_SHAPES[0]


def _kj(st):
    return st.jt == HSS_TYPES[2]


def _two(st):
    return st.jt != HSS_TYPES[0]


def geometry(st):
    ch, b1, b2 = CATALOG.get(st.chord), CATALOG.get(st.br1), CATALOG.get(st.br2)
    g = dict(ch=ch, b1=b1, b2=b2, rnd=_round(st))
    if ch is None:
        return g
    if g["rnd"]:
        g["D"], g["t"] = ch.d, ch.tw
        g["B"] = g["H"] = ch.d
        g["Ag"] = ch.A
    else:
        g["B"], g["H"], g["t"] = ch.bf, ch.d, ch.tw
        g["D"] = g["B"]
        g["Ag"] = ch.A
    g["gam"] = (g["D"] if g["rnd"] else g["B"]) / (2.0 * g["t"])
    return g


def _bdim(sh, rnd):
    """(ancho Db o Bb, alto Hb, espesor tb) de una diagonal."""
    if sh is None:
        return 0.0, 0.0, 0.0
    return (sh.d, sh.d, sh.tw) if rnd else (sh.bf, sh.d, sh.tw)


def check_input(st) -> list:
    g = geometry(st)
    w = []
    ch = g["ch"]
    exp_kind = "HSS-C" if g["rnd"] else "HSS-R"
    if ch is None or ch.kind != exp_kind:
        return [f"** El cordon '{st.chord}' debe ser un HSS {'circular' if g['rnd'] else 'rectangular/cuadrado'} del catalogo. **"]
    brs = [(st.br1, g["b1"], st.theta1, st.br1_steel)] + ([(st.br2, g["b2"], st.theta2, st.br2_steel)] if _two(st) else [])
    Fyc = M.find(M.SHAPE_STEELS, st.chord_steel).Fy
    for lab, sh, th, steel in brs:
        if sh is None or sh.kind != exp_kind:
            w.append(f"** La diagonal '{lab}' debe ser del mismo tipo que el cordon (catalogo). **")
            continue
        Db, Hb, tb = _bdim(sh, g["rnd"])
        beta = Db / g["D"]
        if th < 30.0 - 1e-9 or th > 90.0 + 1e-9:
            w.append(f"** Angulo de la diagonal {lab}: {th:g}° fuera de 30° a 90° (limite de validez del Cap. K). **")
        if g["rnd"]:
            if not (0.2 < beta <= 1.0):
                w.append(f"** β = Db/D = {beta:.2f} de {lab} fuera de 0.2 < β ≤ 1.0 (Tabla K3.1A). **")
            if g["D"] / g["t"] > (40.0 if st.jt == HSS_TYPES[1] else 50.0):
                w.append(f"** D/t = {g['D'] / g['t']:.1f} del cordon supera el limite ({'40' if st.jt == HSS_TYPES[1] else '50'}) de la Tabla K3.1A. **")
        else:
            if beta > 0.85 + 1e-9:
                w.append(f"** β = Bb/B = {beta:.2f} de {lab} > 0.85: la plastificacion de pared no aplica y el procedimiento de β mayor no esta implementado. **")
            if beta < 0.25 - 1e-9:
                w.append(f"** β = Bb/B = {beta:.2f} de {lab} < 0.25 (limite de la Tabla K3.2A). **")
            if g["B"] / g["t"] > 35.0 + 1e-9 or g["H"] / g["t"] > 35.0 + 1e-9:
                w.append("** B/t o H/t del cordon supera 35 (Tabla K3.2A). **")
    if Fyc > 52.0 + 1e-9:
        w.append(f"** Fy del cordon = {Fyc:g} ksi supera 52 ksi (limite del Cap. K). **")
    mc = M.find(M.SHAPE_STEELS, st.chord_steel)
    if mc.Fy / mc.Fu > 0.8 + 1e-9:
        w.append(f"Fy/Fu del cordon = {mc.Fy / mc.Fu:.3f} supera 0.8 (limite de validez del Cap. K): las ecuaciones se usan igualmente; revise la aplicabilidad.")
    if _kj(st):
        if not g["rnd"]:
            w.append("** Los nudos K/N rectangulares con separacion no estan implementados: use otro tipo o verifique con el Manual (Tabla K3.2A). **")
        else:
            tb1, tb2 = _bdim(g["b1"], True)[2], _bdim(g["b2"], True)[2]
            if st.gap < tb1 + tb2 - 1e-9:
                w.append(f"** Separacion g = {st.gap:g} in menor que tb1 + tb2 = {tb1 + tb2:.3f} in (limite de la Tabla K3.1A). **")
    if st.jt == HSS_TYPES[1]:
        w.append("Cruzada (X): se verifica cada diagonal por separado con la expresion de cruzada; deben estar en lados opuestos del cordon y alineadas.")
    w.append("NO se evalua: soldadura diagonal-cordon, cortante del cordon en la separacion, el miembro diagonal ni la excentricidad del nudo.")
    return w


def solve_one(prj, name, vals, rec):
    P1, P2 = vals
    st = prj.hss
    g = geometry(st)
    ck = []
    ch = g["ch"]
    exp_kind = "HSS-C" if g["rnd"] else "HSS-R"
    if ch is None or ch.kind != exp_kind:
        return ck
    u = prj.units()
    Fy = M.find(M.SHAPE_STEELS, st.chord_steel).Fy
    t, D, B, gam = g["t"], g["D"], g["B"], g["gam"]
    U = abs(st.chord_P) / (Fy * g["Ag"]) if st.chord_P > 0 else 0.0
    if rec:
        rec.section(f"DATOS DE PARTIDA — {name}")
        rec.add("Cordon", f"{st.chord} ({st.chord_steel})", f"{'D' if g['rnd'] else 'B × H'} = " + (f"{rec.f('L', D)}" if g["rnd"] else f"{rec.f('L', B)} × {rec.f('L', g['H'])}")
                + f", t = {rec.f('L', t)}, Fy = {rec.f('S', Fy)}; γ = {gam:.2f}", None)
        rec.add("Axial del cordon", "compresion +", "", st.chord_P, "F")
        rec.add("U", "|Pro|/(Fy·Ag)", "", U, "-", "AISC K3")
    branches = [(1, st.br1, g["b1"], st.theta1, P1)] + ([(2, st.br2, g["b2"], st.theta2, P2)] if _two(st) else [])
    cap_sin = {}                                           # φPn·senθ de la plastificacion del cordon (para K)
    for idx, lab, sh, th, P in branches:
        if sh is None or sh.kind != exp_kind:
            continue
        Db, Hb, tb = _bdim(sh, g["rnd"])
        sinth = math.sin(math.radians(th))
        if sinth < 1e-6:                                   # θ imposible: check_input ya avisa con '**'
            continue
        beta = Db / (D if g["rnd"] else B)
        tag = f"Diagonal {idx} ({lab})"
        if g["rnd"]:
            Qf = 1.0 if st.chord_P <= 0 else 1.0 - 0.3 * U * (1.0 + U)
            if st.jt == HSS_TYPES[0]:
                cw = PHI_CW * Fy * t ** 2 * (3.1 + 15.6 * beta ** 2) * gam ** 0.2 * Qf
                form = f"0.90·Fy·t²·(3.1 + 15.6·β²)·γ^0.2·Qf   (β = {beta:.3f}, Qf = {Qf:.3f})"
            elif st.jt == HSS_TYPES[1]:
                cw = PHI_CW * Fy * t ** 2 * (5.7 / (1.0 - 0.81 * beta)) * Qf
                form = f"0.90·Fy·t²·5.7/(1 − 0.81·β)·Qf   (β = {beta:.3f}, Qf = {Qf:.3f})"
            else:
                # K/N: se calcula con la diagonal comprimida y la traccionada hereda el mismo Pn·senθ
                comp = 1 if P1 >= P2 else 2
                shc = g["b1"] if comp == 1 else g["b2"]
                Dbc = _bdim(shc, True)[0]
                Qg = gam ** 0.2 * (1.0 + 0.024 * gam ** 1.2 / (math.exp(0.5 * st.gap / t - 1.33) + 1.0))
                cw_s = PHI_CW * Fy * t ** 2 * (2.0 + 11.33 * Dbc / D) * Qg * Qf
                cap_sin[idx] = cw_s
                form = f"0.90·Fy·t²·(2.0 + 11.33·Db,c/D)·Qg·Qf   (Qg = {Qg:.3f}, Qf = {Qf:.3f}; diagonal comprimida #{comp})"
            Pcap = (cw_s if _kj(st) else cw) / sinth
            add_check(ck, rec, f"jt_cw{idx}", f"{tag} — plastificacion del cordon", abs(P), Pcap, "kip", "AISC Tabla K3.1",
                      form + f"; θ = {th:g}°")
            if Db <= D - 2 * t + 1e-9:
                Ppun = PHI_PS * 0.6 * Fy * t * math.pi * Db * (1.0 + sinth) / (2.0 * sinth ** 2)
                add_check(ck, rec, f"jt_ps{idx}", f"{tag} — corte por punzonamiento del cordon", abs(P), Ppun, "kip", "AISC Tabla K3.1",
                          "φ = 0.95; solo si Db ≤ D − 2t")
        else:
            eta = Hb / B
            Qf = 1.0 if st.chord_P <= 0 else min(1.0, 1.3 - 0.4 * U / beta)
            cw = PHI_CW * Fy * t ** 2 * (2.0 * eta / (1.0 - beta) + 4.0 / math.sqrt(1.0 - beta)) * Qf
            add_check(ck, rec, f"jt_cw{idx}", f"{tag} — plastificacion de la pared del cordon", abs(P), cw / sinth, "kip", "AISC Tabla K3.2A",
                      f"0.90·Fy·t²·[2η/(1−β) + 4/√(1−β)]·Qf   (β = {beta:.3f}, η = {eta:.3f}, Qf = {Qf:.3f}); θ = {th:g}°")
    if _kj(st):
        # la diagonal traccionada tiene el mismo Pn·senθ que la comprimida: su capacidad es cap_sin[comp]/sen(θ_tracc)
        comp = 1 if P1 >= P2 else 2
        other = 2 if comp == 1 else 1
        th_o = max(st.theta2 if other == 2 else st.theta1, 0.01)
        P_o = P2 if other == 2 else P1
        cs = cap_sin.get(comp) or cap_sin.get(1)
        if cs:
            ck_o = [c for c in ck if c.key == f"jt_cw{other}"]
            if ck_o:
                ck_o[0].capacity = cs / math.sin(math.radians(th_o))
                ck_o[0].note += "; Pn·senθ igual al de la diagonal comprimida"
        if P1 * P2 > 0:
            not_evaluated(ck, "jt_kdir", "Diagonales con fuerzas del mismo sentido (no es un nudo K/N tipico)", "AISC K3", "Revise el signo de las fuerzas.")
    not_evaluated(ck, "jt_other", "Soldadura de las diagonales, cortante del cordon y miembro diagonal", "AISC K / Cap. D-E")
    return ck


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.hss, check_input, solve_one, detail)


# ============================================================ contrato con la UI y los reportes
ATTR = "hss"
TAB = "HSS a HSS"
PREFIX = "HS"
TITLE = "NUDO DE CELOSIA HSS A HSS"
NORMS = "AISC 360-22 Cap. K (Tablas K3.1 y K3.2A)"
LOADS = [("P diagonal 1", "F"), ("P diagonal 2", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con los axiales P de las diagonales (compresion +, traccion −). En T/Y/X solo cuenta la diagonal 1; "
              "en K/N, una diagonal debe ir comprimida y la otra traccionada.")
_rnd = lambda p: p.hss.shape == HSS_SHAPES[0]
_rect = lambda p: p.hss.shape == HSS_SHAPES[1]
_two_ = lambda p: p.hss.jt != HSS_TYPES[0]
FORM = [
    G("Tipo de nudo"),
    combo("Perfiles", "hss.shape", HSS_SHAPES, help="Todos los miembros del nudo del mismo tipo (redondos o rectangulares). Cambie el perfil despues de cambiar el tipo."),
    combo("Nudo", "hss.jt", HSS_TYPES),
    G("Cordon"),
    combo("Perfil del cordon", "hss.chord", "@HSS_ANY", editable=True, help="HSS circular o rectangular segun el tipo elegido."),
    combo("Acero del cordon", "hss.chord_steel", "@steel_shape"),
    num("Axial del cordon junto al nudo", "hss.chord_P", -5000, 5000, uk="F", help="Compresion positiva. Solo la compresion reduce la resistencia (Qf)."),
    G("Diagonal 1"),
    combo("Perfil de la diagonal 1", "hss.br1", "@HSS_ANY", editable=True),
    combo("Acero de la diagonal 1", "hss.br1_steel", "@steel_shape"),
    num("Angulo con el cordon  θ1", "hss.theta1", 30, 90, step=1.0, dec=1, suffix="°"),
    G("Diagonal 2", show=_two_),
    combo("Perfil de la diagonal 2", "hss.br2", "@HSS_ANY", editable=True, show=_two_),
    combo("Acero de la diagonal 2", "hss.br2_steel", "@steel_shape", show=_two_),
    num("Angulo con el cordon  θ2", "hss.theta2", 30, 90, step=1.0, dec=1, suffix="°", show=_two_),
    num("Separacion g entre las puntas", "hss.gap", 0, 20, uk="L", help="Medida sobre la cara del cordon entre los pies de las dos diagonales (solo K/N).",
        show=lambda p: p.hss.jt == HSS_TYPES[2]),
    N("Redondos: T/Y, X y K con separacion. Rectangulares: T/Y/X con β ≤ 0.85. NO se evalua la soldadura ni el miembro diagonal."),
]


def label(prj) -> str:
    st = prj.hss
    return f"{st.chord}  {st.jt.split(' (')[0]}  ({st.br1}" + (f", {st.br2})" if _two(st) else ")")


def input_rows(prj, us) -> list:
    st = prj.hss
    rows = [("Nudo", f"{st.jt} — {st.shape}"), ("Cordon", f"{st.chord} ({st.chord_steel}); axial {us.q('F', st.chord_P)} (compresion +)"),
            ("Diagonal 1", f"{st.br1} ({st.br1_steel}), θ1 = {st.theta1:g}°")]
    if _two(st):
        rows.append(("Diagonal 2", f"{st.br2} ({st.br2_steel}), θ2 = {st.theta2:g}°" + (f"; separacion {us.q('L', st.gap)}" if _kj(st) else "")))
    rows.append(("Cargas (LRFD)", "; ".join(f"{n}: P1 = {us.q('F', v[0])}, P2 = {us.q('F', v[1])}" for n, v in st.loads())))
    return rows


def draw(fig, prj):
    from . import drawing as D
    from matplotlib.patches import Rectangle, Polygon
    st = prj.hss
    g = geometry(st)
    ax = fig.add_subplot(111)
    D.blank(ax)
    ch = g["ch"]
    exp_kind = "HSS-C" if g["rnd"] else "HSS-R"
    if ch is None or ch.kind != exp_kind:
        return
    us = prj.units()
    q = lambda v: us.fmt("L", v)
    Hc = g["D"] if g["rnd"] else g["H"]
    L = 40.0
    ax.add_patch(Rectangle((-L, -Hc / 2), 2 * L, Hc, fc=D.C_BEAM, ec=D.C_BEAM_EDGE, lw=1.3, zorder=2))

    def branch(cx, th_deg, sh, direction, up=True, color=D.C_ANGLE, edge=D.C_ANGLE_EDGE):
        """Diagonal con la huella real sobre la cara del cordon (ancho w/senθ) centrada en cx."""
        Db, Hb, tb = _bdim(sh, g["rnd"])
        w = Db if g["rnd"] else Hb                                      # ancho de la diagonal en el plano del nudo
        th = math.radians(th_deg)
        f = w / max(math.sin(th), 1e-6)
        dx, dy = direction * math.cos(th), (1 if up else -1) * math.sin(th)
        y0 = (Hc / 2) if up else (-Hc / 2)
        Lb = 30.0
        pts = [(cx - f / 2, y0), (cx + f / 2, y0), (cx + f / 2 + Lb * dx, y0 + Lb * dy), (cx - f / 2 + Lb * dx, y0 + Lb * dy)]
        ax.add_patch(Polygon(pts, closed=True, fc=color, ec=edge, lw=1.2, alpha=0.8, zorder=3))
        return w

    b1, b2 = g["b1"], g["b2"]
    if b1 is None:
        return
    if st.jt == HSS_TYPES[0]:
        w1 = branch(0.0, st.theta1, b1, 1)
    elif st.jt == HSS_TYPES[1]:
        w1 = branch(0.0, st.theta1, b1, 1, up=True)
        branch(0.0, st.theta1, b1, -1, up=False)
    else:
        if b2 is None:
            return
        w1 = _bdim(b1, g["rnd"])[0] if g["rnd"] else _bdim(b1, False)[1]
        w2 = _bdim(b2, g["rnd"])[0] if g["rnd"] else _bdim(b2, False)[1]
        f1 = w1 / math.sin(math.radians(st.theta1))
        f2 = w2 / math.sin(math.radians(st.theta2))
        branch(-(st.gap / 2 + f1 / 2), st.theta1, b1, -1)
        branch(st.gap / 2 + f2 / 2, st.theta2, b2, 1)
        D._dim(ax, (-st.gap / 2, Hc / 2), (st.gap / 2, Hc / 2), 3.0, f"g = {q(st.gap)}")
    ax.text(-L + 1, -Hc / 2 - 2.5, f"Cordon {st.chord}  ·  diagonal 1 {st.br1}" + (f"  ·  diagonal 2 {st.br2}" if _two(st) else ""), fontsize=8, color="#444444", va="top")
    ax.text(-L + 1, -Hc / 2 - 5.0, f"θ1 = {st.theta1:g}°" + (f", θ2 = {st.theta2:g}°" if _two(st) else ""), fontsize=8, color="#444444", va="top")
    ax.set_xlim(-L, L)
    ax.set_ylim(-Hc / 2 - 9, Hc / 2 + 32)
    ax.set_title(f"Nudo HSS a HSS — {st.jt.split(' (')[0]}", fontsize=9)
