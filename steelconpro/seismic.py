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
from dataclasses import dataclass

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


def member_caps(prj: Project) -> dict:
    """{miembro: {My, Mz}} = 1.1·Ry·Fy·Z de cada miembro del nudo (y del principal) en sus ejes locales (y = eje fuerte con el perfil sin girar):
    las combinaciones con sobrerresistencia (Ωo) no pueden exigir más momento del que el miembro puede desarrollar (AISC 341-22, «la fuerza
    máxima que el sistema puede entregar»; mismo criterio que D2.6 para la base)."""
    from . import materials as M
    from .shapes import CATALOG
    nd = prj.node
    out = {}
    for name, shape, steel, roll in [(nd.main_name, nd.main_shape, nd.main_steel, nd.main_roll)] + [(m.name, m.shape, m.steel, m.roll) for m in nd.members]:
        s = CATALOG.get(shape)
        if s is None or not getattr(s, "Zx", 0):
            continue
        try:
            Fy = M.find(M.SHAPE_STEELS, steel).Fy
        except Exception:                                    # noqa: BLE001
            continue
        Ry = ry_of(steel)
        zx, zy = (s.Zy, s.Zx) if abs(abs(float(roll)) % 180.0 - 90.0) < 1e-6 else (s.Zx, s.Zy)
        out[name] = {"My": 1.1 * Ry * Fy * zx, "Mz": 1.1 * Ry * Fy * zy}
        m = nd.member_named(name) if name != nd.main_name else None
        if m is not None and float(getattr(m, "sism_Lh", 0.0)) > 0:      # cortante asociado: 2·M/Lh + cortante de gravedad (datos de la ficha de la viga)
            out[name]["Vz"] = 2.0 * out[name]["My"] / float(m.sism_Lh) + abs(float(getattr(m, "sism_Vg", 0.0)))
    return out


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


SERVICE_KINDS = ("D", "L", "S", "QEx", "QEy")
GENERATED_KINDS = ("G", "E", "Ωo")


def combo_specs(S, has_x: bool, has_y: bool) -> list:
    """Combinaciones LRFD de ASCE 7-05 como coeficientes sobre los casos de servicio:
    [{"kind": "G"/"E"/"Ωo", "label", "g": {D, L, S}, "e": {D, QEx, QEy}}]; g = parte no sismica, e = Ev + ρ/Ωo·QE."""
    f1, sds = S.f1, S.SDS
    out = []
    if S.gravity:
        for aD, aL, aS in ((1.4, 0.0, 0.0), (1.2, 1.6, 0.5), (1.2, f1, 1.6)):          # ASCE 7-05 2.3.2 (1), (2), (3)
            out.append({"kind": "G", "label": _term(aD, "D", True) + _term(aL, "L") + _term(aS, "S"),
                        "g": {"D": aD, "L": aL, "S": aS}, "e": {}})
    cs = [[0.0] * 5] * 3 + [[1.0] * 5 if has_x else [0.0] * 5, [1.0] * 5 if has_y else [0.0] * 5]
    dirs = _directions(cs, S.ortho)
    for kind, fq in (("E", S.rho), ("Ωo", S.Omega0)):
        for aD, aL, aS, ev in ((1.2 + 0.2 * sds, f1, 0.2, +1), (0.9 - 0.2 * sds, 0.0, 0.0, -1)):
            for ax, ay in dirs:
                out.append({"kind": kind,
                            "label": (_term(aD, "D", True) + _term(aL, "L") + _term(aS, "S")
                                      + _term(fq * ax, "QEx") + _term(fq * ay, "QEy")),
                            "g": {"D": 1.2 if ev > 0 else 0.9, "L": aL, "S": aS},
                            "e": {"D": ev * 0.2 * sds, "QEx": fq * ax, "QEy": fq * ay}})
    return out


def generate_node_cases(prj: Project) -> int:
    """Genera en el nudo los casos factorizados de ASCE 7-05 a partir de los casos marcados como servicio (D, L, S, QEx, QEy en
    `node.case_kind`): cada caso generado es, miembro a miembro (y lado del principal), la combinacion lineal de las filas de servicio
    (el equilibrio del nudo es lineal).  Reemplaza los casos generados antes; no toca los escritos a mano.  Devuelve cuantos genero."""
    from .conn.specs import Load
    nd = prj.node
    kinds = dict(getattr(nd, "case_kind", None) or {})
    svc = {}                                                  # tipo de servicio -> {(miembro, lado): [N, Vy, Vz, T, My, Mz]}
    for l in nd.loads:
        k = kinds.get(l.case)
        if k in SERVICE_KINDS:
            row = svc.setdefault(k, {}).setdefault((l.member, int(l.side)), [0.0] * 6)
            for i, key in enumerate(("N", "Vy", "Vz", "T", "My", "Mz")):
                row[i] += float(getattr(l, key))
    old = {c for c, k in kinds.items() if k in GENERATED_KINDS}
    nd.loads = [l for l in nd.loads if l.case not in old]
    for c in old:
        kinds.pop(c, None)
        nd.case_meta.pop(c, None)
    nz = lambda k: any(abs(v) > 1e-12 for r in svc.get(k, {}).values() for v in r)          # noqa: E731
    if not svc or not (nz("D") or nz("L") or nz("S") or nz("QEx") or nz("QEy")):
        nd.case_kind = kinds
        return 0
    keys = sorted({mk for d in svc.values() for mk in d}, key=lambda t: (t[0], t[1]))
    caps = member_caps(prj) if (prj.seis.cap_limit and prj.seis.aisc341) else {}
    made, seen = [], set()
    cnt = {"G": 0, "E": 0, "Ωo": 0}
    pre = {"G": "G", "E": "E", "Ωo": "Ω"}
    for sp in combo_specs(prj.seis, nz("QEx"), nz("QEy")):
        coef = {}
        for d in (sp["g"], sp["e"]):
            for k, a in d.items():
                coef[k] = coef.get(k, 0.0) + a
        rows = []
        capped = False
        for mk in keys:
            v = [sum(a * svc.get(k, {}).get(mk, [0.0] * 6)[i] for k, a in coef.items()) for i in range(6)]
            cp = caps.get(mk[0]) if sp["kind"] == "Ωo" else None
            if cp:                                            # AISC 341-22: la acción con Ωo no pasa de la que el miembro puede entregar
                for i, lim in ((4, cp["My"]), (5, cp["Mz"])) + (((2, cp["Vz"]),) if "Vz" in cp else ()):
                    if abs(v[i]) > lim:
                        v[i] = lim if v[i] > 0 else -lim
                        capped = True
            rows.append((mk, v))
        sig = (sp["kind"],) + tuple((mk, tuple(round(x, 9) for x in v)) for mk, v in rows)
        if sig in seen:
            continue
        seen.add(sig)
        cnt[sp["kind"]] += 1
        name = f"{pre[sp['kind']]}{cnt[sp['kind']]}: {sp['label']}" + (" (lím. capacidad)" if capped else "")
        for (m, side), v in rows:
            nd.loads.append(Load(name, m, *v, side=side))
        kinds[name] = sp["kind"]
        nd.case_meta[name] = {"kind": sp["kind"], "g": dict(sp["g"]), "e": dict(sp["e"])}
        made.append(name)
    nd.case_kind = kinds
    return len(made)


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


# ------------------------------------------------------- estado sismico de la combinacion activa
@dataclass
class SeisState:
    active: bool = False         # rige ACI 17.10 en esta combinacion (SDC C-F y combinacion E u Ωo)
    kind: str = ""
    fN: float = 0.0              # fraccion sismica de la traccion de los anclajes (ACI 17.10.5.1)
    fV: float = 0.0              # fraccion sismica del cortante (ACI 17.10.6.1)
    k_t: float = 1.0             # factor sobre los modos de concreto en traccion (0.75 si fN > 20 %, 17.10.5.4)
    bond: bool = False           # reduccion de τ por sismo (nota de la Tabla 17.6.5.2.5)
    known: bool = True           # la parte sismica de la combinacion es conocida


def active_combo(prj: Project):
    cs = prj.combos or []
    return cs[prj.combo_idx] if 0 <= prj.combo_idx < len(cs) else None


def seismic_state(prj: Project) -> SeisState:
    """Clasifica la combinacion activa segun ACI 318-19 17.10.  La fraccion sismica se calcula con el
    equilibrio cerrado (DG1): (Tu − Tu sin E) / Tu, y para el cortante (Vu − Vu sin E) / Vu."""
    from . import design as D
    st = SeisState()
    c = active_combo(prj)
    if not prj.seis.aci_applies or c is None or c.kind not in ("E", "Ωo"):
        return st
    st.active, st.kind, st.bond, st.known = True, c.kind, True, bool(c.e_known)
    q = copy.deepcopy(prj)
    L = q.loads
    if c.e_known:
        L.Pu, L.Mux, L.Muy = L.Pu - c.PE, L.Mux - c.MxE, L.Muy - c.MyE
        L.Vux, L.Vuy = L.Vux - c.VxE, L.Vuy - c.VyE
    else:
        L.Pu = L.Mux = L.Muy = L.Vux = L.Vuy = 0.0
    T = D.bearing(prj).Tu
    T0 = D.bearing(q).Tu if c.e_known else 0.0
    st.fN = 0.0 if T <= 1e-9 else min(1.0, max(0.0, (T - T0) / T))
    V, V0 = prj.eloads.Vu, (q.eloads.Vu if c.e_known else 0.0)
    st.fV = 0.0 if V <= 1e-9 else min(1.0, max(0.0, (V - V0) / V))
    st.k_t = 0.75 if st.fN > 0.20 + 1e-12 else 1.0
    return st


# --------------------------------------------------- verificaciones y avisos sismicos (fuera de anclajes)
_DEMAND_CRITICAL = ("(SMF)", "(IMF)", "(SCBF)", "(EBF)")
_BRACED = ("(SCBF)", "(OCBF)", "(EBF)")


def seismic_checks(prj: Project, br=None, rec=None):
    """Devuelve (checks, avisos) del diseno sismico de la combinacion activa.  La relacion de ductilidad
    17.10.5.3(a) se verifica en anchors.py, donde estan las resistencias nominales."""
    from .design import Check
    S, b, c = prj.seis, prj.bolts, prj.conc
    checks, warns = [], []
    if not S.enabled:
        return checks, warns
    u = prj.units()
    st = seismic_state(prj)
    if not S.aci_applies:
        warns.append(f"SDC {S.sdc}: ACI 318-19 17.10 no aplica a los anclajes (solo SDC C a F, 17.10.1).")
    combos = prj.combos or []
    has_omega = any(x.kind == "Ωo" for x in combos)

    if S.aci_applies:
        mat = b.mat()
        g = b.geom()
        if S.ductile:
            checks.append(Check("seis_duct_mat", "Sismo — anclaje ductil: elemento de acero ductil",
                                0.0 if mat.ductile else 1.0, 1.0 if mat.ductile else 0.0, "-",
                                "ACI 318-19 2.3 / 17.10.5.3(a)",
                                f"{b.steel}: " + ("ductil (alargamiento >= 14 %, reduccion de area >= 30 %)"
                                                   if mat.ductile else "NO es ductil")))
            stretch = S.sleeve + prj.plate.grout + max(0.0, b.standoff) + prj.plate.tp
            checks.append(Check("seis_stretch", "Sismo — anclaje ductil: longitud de estiramiento >= 8·da",
                                8.0 * g.db, stretch, "in", "ACI 318-19 17.10.5.3(a)(iii)",
                                f"camisa {u.q('L', S.sleeve)} + mortero {u.q('L', prj.plate.grout)} + stand-off "
                                f"{u.q('L', max(0.0, b.standoff))} + tp {u.q('L', prj.plate.tp)}"))
            ratio = mat.Fu / mat.Fy if mat.Fy > 0 else 0.0
            checks.append(Check("seis_futa", "Sismo — anclaje ductil: futa/fya >= 1.3 (rosca no recalcada)",
                                1.3, ratio, "-", "ACI 318-19 17.10.5.3(a)(v)",
                                (f"rosca recalcada (upset): no se exige" if S.upset else
                                 f"futa/fya = {mat.Fu:g}/{mat.Fy:g} = {ratio:.2f}"), skip=bool(S.upset)))
            if b.standoff > 1e-9:
                warns.append("Anclaje ductil con stand-off (tuercas de nivelacion): con inversion de carga el perno "
                             "debe protegerse contra el pandeo (ACI 17.10.5.3(a)(iv)).")
        if c.u_on:
            ok = any(abs(c.u_fy - f) < 1e-6 for f in (60.0, 80.0))
            checks.append(Check("seis_rebar", "Sismo — refuerzo del anclaje: Gr.60 u 80 (A615 con 20.2.2.5 o A706)",
                                0.0 if ok else 1.0, 1.0 if ok else 0.0, "-", "ACI 318-19 17.10.4",
                                f"fy = {u.q('S', c.u_fy)}"))
        if not c.cracked:
            warns.append("Sismo: ACI 17.10.5.4 supone concreto FISURADO salvo que se demuestre lo contrario; "
                         "el proyecto usa concreto no fisurado.")
        if b.adhesive:
            warns.append("Sismo: el anclaje adhesivo debe estar calificado para cargas sismicas segun ACI 355.4 "
                         "(17.10.3); τ y Vsa deben salir de esos ensayos.")
        if st.active and (st.fN > 0.20 or st.fV > 0.20) and not has_omega \
                and not (S.ductile and st.fV <= 0.20 and not S.aisc341):   # AISC 341 D2.6 exige Ωo/capacidad igual
            warns.append("Sismo: la parte sismica supera el 20 % de la "
                         + ("traccion" if st.fN > 0.20 else "") + (" y del " if st.fN > 0.2 and st.fV > 0.2 else "")
                         + ("cortante" if st.fV > 0.20 else "")
                         + " pero no hay combinaciones con Ωo: ACI 17.10.5.3 / 17.10.6.3 exigen disenar con Ωo·E, "
                           "con la fluencia del elemento conectado o (en traccion) con anclaje ductil; AISC 341-22 D2.6 exige "
                           "ademas la resistencia requerida de la base con Ωo o por capacidad. "
                           "Genere las combinaciones en la pestana Sismica.")
    if S.aisc341:
        if any(k in S.system for k in _DEMAND_CRITICAL):
            warns.append("AISC 341-22: las soldaduras de ranura de la columna a la placa base de este sistema son de "
                         "DEMANDA CRITICA (A3.4b): metal de aporte con tenacidad CVN especificada.")
        if any(k in S.system for k in _BRACED):
            warns.append("AISC 341-22 D2.6a/b(a): sume a QE las componentes de la resistencia requerida de las "
                         "conexiones de las riostras que llegan a la base.")
    if S.enabled and S.sdc in ("D", "E", "F") and not S.ortho:
        warns.append("ASCE 7-05 12.5.4: si la columna pertenece a dos sistemas que se cruzan, active 100 % + 30 %.")

    if rec:
        lim = capacity_limits(prj)
        z3 = lambda z: f"{z / u.fl ** 3:.4g} {u.L}³"
        rec.section("S.  REQUISITOS SISMICOS  (ASCE 7-05 / AISC 341-22 D2.6 / ACI 318-19 17.10)")
        rec.add("Sistema", S.system, f"SDC {S.sdc}, Ωo = {S.Omega0:g}, ρ = {S.rho:g}, SDS = {S.SDS:g}", None, "-",
                "ASCE 7-05 Tabla 12.2-1")
        cmb = active_combo(prj)
        rec.add("Combinacion", (cmb.name if cmb else "-"),
                {"": "gravedad / sin sismo", "E": "sismica (ρ·QE)", "Ωo": "sobrerresistencia (Ωo·QE)"}
                .get(cmb.kind if cmb else "", ""), None, "-")
        if st.active:
            rec.add("fN", "(Tu − Tu sin E) / Tu", "parte sismica de la traccion de los anclajes"
                    + ("" if st.known else " (desconocida: 100 %)"), st.fN, "-", "ACI 17.10.5.1")
            rec.add("fV", "(Vu − Vu sin E) / Vu", "parte sismica del cortante", st.fV, "-", "ACI 17.10.6.1")
            rec.add("factor traccion", "0.75 si fN > 20 %", "", st.k_t, "-", "ACI 17.10.5.4")
        rec.add("Ry", "AISC 341-22 Tabla A3.2" + (" (manual)" if S.Ry > 0 else ""), prj.section.steel,
                lim["Ry"], "-")
        rec.add("Mpr,x", "1.1·Ry·Fy·Zx", f"1.1·{lim['Ry']:g}·{rec.n('S', lim['Fy'])}·{z3(lim['Zx'])}",
                lim["Mx"], "M", "AISC 341-22 D2.6c(b)(1)", "limite del momento requerido de la base (eje fuerte)")
        rec.add("Mpr,y", "1.1·Ry·Fy·Zy", f"1.1·{lim['Ry']:g}·{rec.n('S', lim['Fy'])}·{z3(lim['Zy'])}",
                lim["My"], "M", "AISC 341-22 D2.6c(b)(1)")
        rec.add("Vpr,y", "2·Ry·Fy·Zx / H", f"H = {rec.f('L', S.H)}", lim["Vy"], "F", "AISC 341-22 D2.6b(b)(1)",
                "limite del cortante requerido de la base")
        rec.add("Vpr,x", "2·Ry·Fy·Zy / H", "", lim["Vx"], "F", "AISC 341-22 D2.6b(b)(1)")
        if S.cap_limit and S.aisc341:
            rec.text("Las combinaciones con Ωo·QE quedan limitadas por estos valores (resistencia requerida de la "
                     "base = el menor entre la capacidad de la columna y la combinacion con sobrerresistencia).")
    return checks, warns
