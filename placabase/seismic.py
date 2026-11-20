# -*- coding: utf-8 -*-
"""
Diseno sismico de la base de columna.

  - ASCE 7-05  : combinaciones LRFD con sismo (12.4.2.3) y con sobrerresistencia (12.4.3.2), gravedad (2.3.2),
                 direcciones ortogonales 100 % + 30 % (12.5), Ωo de la Tabla 12.2-1.
  - AISC 341-22: resistencia requerida de la base (D2.6): las combinaciones con Ωo se limitan por la capacidad
                 de la columna, 1.1·Ry·Fy·Z (flexion) y 2·Ry·Fy·Z/H (cortante); Ry de la Tabla A3.2.
  - ACI 318-19 : 17.10 (anclajes en SDC C a F).

Unidades internas: in, kip, ksi.
"""
from __future__ import annotations
import copy

from .model import Project, LoadCombo, SEIS_SYSTEMS

# Ωo por sistema (ASCE 7-05 Tabla 12.2-1, porticos y arriostrados de acero)
OMEGA0_DEFAULT = {
    SEIS_SYSTEMS[0]: 3.0,   # SMF
    SEIS_SYSTEMS[1]: 3.0,   # IMF
    SEIS_SYSTEMS[2]: 3.0,   # OMF
    SEIS_SYSTEMS[3]: 2.0,   # SCBF
    SEIS_SYSTEMS[4]: 2.0,   # OCBF
    SEIS_SYSTEMS[5]: 2.0,   # EBF
    SEIS_SYSTEMS[6]: 3.0,   # columna de gravedad: Ωo del sistema del edificio (editable)
    SEIS_SYSTEMS[7]: 3.0,   # sistema no detallado R = 3
}

# Ry, AISC 341-22 Tabla A3.2 (busqueda por fragmento del nombre del acero, en orden)
_RY = [("A500 Gr.B", 1.4), ("A500 Gr.C", 1.3), ("A1085", 1.25), ("A53", 1.6),
       ("A1043", 1.3), ("A36", 1.5), ("A992", 1.1), ("A572", 1.1), ("A588", 1.1), ("A913", 1.1)]


def ry_of(steel_name: str) -> float:
    """Ry del acero del perfil (AISC 341-22 Tabla A3.2); 1.1 si el acero no esta en la tabla."""
    n = str(steel_name)
    for key, ry in _RY:
        if key in n:
            return ry
    return 1.1


def ry_used(prj: Project) -> float:
    return prj.seis.Ry if prj.seis.Ry > 0 else ry_of(prj.section.steel)


def capacity_limits(prj: Project) -> dict:
    """Limites por capacidad de la columna (AISC 341-22 D2.6b(b)(1) y D2.6c(b)(1)), en ejes de la columna:
    Mx = 1.1·Ry·Fy·Z (momento Mux) ; My idem con el otro eje ; Vy = 2·Ry·Fy·Z/H (cortante asociado a Mux) ;
    Vx idem con Muy.  Perfil girado 90°: se intercambian Zx y Zy; otro giro: el mayor Z (conservador)."""
    s = prj.section.eff()
    Fy = prj.section.mat().Fy
    Ry = ry_used(prj)
    H = max(prj.seis.H, 1e-6)
    rot = abs(float(prj.section.rotation)) % 180.0
    if rot < 1e-6:
        zx, zy = s.Zx, s.Zy
    elif abs(rot - 90.0) < 1e-6:
        zx, zy = s.Zy, s.Zx
    else:
        zx = zy = max(s.Zx, s.Zy)
    return {"Mx": 1.1 * Ry * Fy * zx, "My": 1.1 * Ry * Fy * zy,
            "Vy": 2.0 * Ry * Fy * zx / H, "Vx": 2.0 * Ry * Fy * zy / H,
            "Ry": Ry, "Fy": Fy, "Zx": zx, "Zy": zy}


# ------------------------------------------------------------------ generador
def _fmt(a: float) -> str:
    t = f"{a:.2f}".rstrip("0").rstrip(".")
    return t if "." in t else t + ".0"


def _term(a: float, name: str, first=False) -> str:
    if abs(a) < 1e-12:
        return ""
    sgn = "−" if a < 0 else ("" if first else "+")
    return f"{sgn}{_fmt(abs(a))}{name}"


def _directions(cases, ortho):
    """[(ax, ay)] factores sobre QEx y QEy (ASCE 7-05 12.5: 100 % + 30 % si ortho)."""
    nzx = any(abs(v) > 1e-12 for v in cases[3])
    nzy = any(abs(v) > 1e-12 for v in cases[4])
    out = []
    if ortho and nzx and nzy:
        for sx in (1, -1):
            for sy in (1, -1):
                out.append((sx * 1.0, sy * 0.3))
        for sx in (1, -1):
            for sy in (1, -1):
                out.append((sx * 0.3, sy * 1.0))
        return out
    if nzx:
        out += [(1.0, 0.0), (-1.0, 0.0)]
    if nzy:
        out += [(0.0, 1.0), (0.0, -1.0)]
    return out


def _lin(coefs, cases):
    """Suma de casos: sum(a_i · cases[i]) -> [P, Mx, My, Vx, Vy]."""
    return [sum(a * cases[i][k] for i, a in enumerate(coefs)) for k in range(5)]


def generate(prj: Project) -> list:
    """Combinaciones LRFD de ASCE 7-05 a partir de las cargas de servicio de prj.seis.cases.
    Gravedad (G), sismicas (E: ρ·QE) y de sobrerresistencia (Ω: Ωo·QE), con la parte sismica guardada."""
    S = prj.seis
    cs = [list(map(float, r)) + [0.0] * (5 - len(r)) for r in S.cases][:5]
    while len(cs) < 5:
        cs.append([0.0] * 5)
    f1, sds = S.f1, S.SDS
    out = []

    if S.gravity:
        for coefs in ([1.4, 0, 0], [1.2, 1.6, 0.5], [1.2, f1, 1.6]):        # ASCE 7-05 2.3.2 (1), (2), (3)
            v = _lin(coefs + [0, 0], cs)
            name = _term(coefs[0], "D", True) + _term(coefs[1], "L") + _term(coefs[2], "S")
            out.append(LoadCombo(name, *v))

    dirs = _directions(cs, S.ortho)
    lim = capacity_limits(prj) if (S.cap_limit and S.aisc341) else None
    for kind, fq in (("E", S.rho), ("Ωo", S.Omega0)):
        for basic in ((1.2 + 0.2 * sds, f1, 0.2, +1), (0.9 - 0.2 * sds, 0.0, 0.0, -1)):
            aD, aL, aS, ev = basic                     # ev: +Ev en (1.2 + 0.2SDS)D, −Ev en (0.9 − 0.2SDS)D
            for ax, ay in dirs:
                g = _lin([1.2 if ev > 0 else 0.9, aL, aS, 0, 0], cs)                 # parte no sismica
                e = _lin([ev * 0.2 * sds, 0, 0, fq * ax, fq * ay], cs)               # Ev + ρ/Ωo·QE
                tot = [g[k] + e[k] for k in range(5)]
                capped = False
                if kind == "Ωo" and lim is not None:
                    for k, key, use in ((1, "Mx", S.base_moment), (2, "My", S.base_moment),
                                        (3, "Vx", True), (4, "Vy", True)):
                        if use and abs(tot[k]) > lim[key]:
                            tot[k] = lim[key] if tot[k] > 0 else -lim[key]
                            capped = True
                    e = [tot[k] - g[k] for k in range(5)]
                name = (_term(aD, "D", True) + _term(aL, "L") + _term(aS, "S")
                        + _term(fq * ax, "QEx") + _term(fq * ay, "QEy")
                        + (" (lim. D2.6)" if capped else ""))
                c = LoadCombo(name, *tot)
                c.kind = kind
                c.PE, c.MxE, c.MyE, c.VxE, c.VyE = e
                c.e_known = True
                out.append(c)

    # fusion de combinaciones identicas (mismo tipo y mismas cargas)
    seen, uniq = set(), []
    for c in out:
        key = (c.kind,) + tuple(round(v, 6) for v in (c.Pu, c.Mux, c.Muy, c.Vux, c.Vuy))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    if not uniq:
        uniq = [LoadCombo("1.4D", *_lin([1.4, 0, 0, 0, 0], cs))]
    cnt = {"": 0, "E": 0, "Ωo": 0}
    pre = {"": "G", "E": "E", "Ωo": "Ω"}
    for c in uniq:
        cnt[c.kind] += 1
        c.name = f"{pre[c.kind]}{cnt[c.kind]}: {c.name}"
    return uniq


def prune(prj: Project, combos: list) -> list:
    """Conserva las combinaciones que dan el mayor D/C de al menos una verificacion del calculo cerrado,
    mas la mas desfavorable de cada tipo (G, E, Ω).  Nunca devuelve una lista vacia."""
    from .solver import solve
    if len(combos) <= 1:
        return list(combos)
    q = copy.deepcopy(prj)
    q.combos = list(combos)
    best, best_kind = {}, {}
    for i in range(len(combos)):
        R = solve(q.with_combo(i))                 # detail=False falla en design.welds (error previo); se usa la memoria completa
        for ch in R.checks:
            if ch.skip:
                continue
            if ch.key not in best or ch.ratio > best[ch.key][0] + 1e-12:
                best[ch.key] = (ch.ratio, i)
        k = combos[i].kind
        if k not in best_kind or R.max_ratio > best_kind[k][0] + 1e-12:
            best_kind[k] = (R.max_ratio, i)
    keep = sorted({i for _, i in best.values()} | {i for _, i in best_kind.values()})
    return [combos[i] for i in keep] or [combos[0]]
