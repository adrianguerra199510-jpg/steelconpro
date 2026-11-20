# -*- coding: utf-8 -*-
"""Resultados del analisis 3D de una conexion: campos (von Mises, desplazamiento, deformacion plastica), fuerzas de los pernos,
esfuerzo de las soldaduras, presion de contacto y equilibrio; y las verificaciones que de ellos salen."""
from __future__ import annotations
import math
from dataclasses import dataclass, field

import numpy as np

from ...view3d import read_frd, read_peeq, von_mises
from ...design import Check
from ..common import FNV, FNT, PHI_BOLT, bolt_tension_shear

PHI_WELD = 0.75


@dataclass
class BoltRes:
    tag: str
    pos: tuple
    V: float                      # cortante mayor entre los planos de corte, kip
    T: float                      # traccion, kip
    planes: list                  # resultante en cada plano, kip
    db: float
    grade: str
    nplanes: int = 1


@dataclass
class WeldRes:
    name: str
    group: str
    stress_max: float             # traccion resultante en la garganta, ksi (pico: percentil 95 de los nodos libres)
    stress_avg: float
    cap: float                    # φ·0.60·FEXX, ksi
    w: float
    length: float
    where: tuple = (0.0, 0.0, 0.0)


@dataclass
class FemResult:
    ok: bool = False
    msg: str = ""
    nodes: dict = field(default_factory=dict)
    parts: dict = field(default_factory=dict)          # clave de pieza -> triangulos exteriores
    kinds: dict = field(default_factory=dict)          # clave -> tipo ('beam', 'plate', ..., 'weld')
    labels: dict = field(default_factory=dict)
    disp: dict = field(default_factory=dict)
    vm: dict = field(default_factory=dict)
    peeq: dict = field(default_factory=dict)
    umax: float = 0.0
    vmmax: float = 0.0
    n_nodes: int = 0
    n_elems: int = 0
    lc: float = 0.0
    plastic: bool = False
    bolts: list = field(default_factory=list)
    welds: list = field(default_factory=list)
    peeq_parts: dict = field(default_factory=dict)     # clave -> {"raw": (v, x, y, z), "avg": (v, x, y, z)}
    vm_parts: dict = field(default_factory=dict)       # clave -> (vm max, x, y, z)
    pmax: float = 0.0                                  # presion de contacto maxima, ksi
    n_contacts: int = 0
    equil: tuple = (0.0, 0.0)                          # (reaccion, carga) fuerza total
    iters: int = 0
    converged: bool = True
    folder: str = ""
    sig: str = ""
    model: object = None
    notes: list = field(default_factory=list)
    zone: tuple = None
    loads: list = field(default_factory=list)
    rim_nodes: set = field(default_factory=set)
    screened: bool = False                             # no se corrio el paso plastico: el esfuerzo promedio queda por debajo de 0.8·φFy
    screen_ratio: float = 0.0
    collapsed: bool = False                            # el analisis plastico no convergio antes de la carga de diseno
    load_frac: float = 1.0


def phi_y(case) -> float:
    return float(getattr(case, "phi", 0.9))


def postprocess(mdl, case, info, frd, lc=0.0, plastic=False, folder="") -> FemResult:
    mesh = case.mesh
    R = FemResult()
    disp, stress, forc = read_frd(frd)
    if not disp:
        R.msg = "El .frd no contiene desplazamientos: revise la salida de CalculiX."
        return R
    pe = read_peeq(frd) if plastic else {}
    R.plastic = bool(pe)
    ids = [int(n) for n in mesh.node_ids]
    R.nodes = {n: tuple(mesh.xyz[i]) for i, n in enumerate(ids)}
    R.disp = {n: disp[n] for n in ids if n in disp}
    R.vm = {n: von_mises(*stress[n]) for n in ids if n in stress}
    R.peeq = {n: pe[n] for n in ids if n in pe}
    if R.plastic:                                    # el esfuerzo en los puntos de integracion no pasa del limite, pero la extrapolacion a los nodos si
        cap = {}
        for p in mdl.parts:
            f = (p.hard[1] if p.hard else phi_y(case) * p.Fy)
            for n in mesh.part_nodes(p.name):
                if f > cap.get(int(n), 0.0):
                    cap[int(n)] = f
        for n, v in R.vm.items():
            c = cap.get(n)
            if c is not None and v > c:
                R.vm[n] = c
    R.umax = max((math.sqrt(sum(c * c for c in u)) for u in R.disp.values()), default=0.0)
    R.vmmax = max(R.vm.values(), default=0.0)
    R.n_nodes, R.n_elems = len(ids), mesh.n_elem
    R.lc, R.folder, R.model, R.zone = lc, folder, mdl, mdl.zone
    for p in mdl.parts:
        R.kinds[p.name], R.labels[p.name] = p.kind, p.label
    for w in mdl.welds:
        R.kinds["W:" + w.name], R.labels["W:" + w.name] = "weld", "Cordon " + w.name
    for k in mesh.names:
        R.parts[k] = [tuple(int(q) for q in nodes[:3]) for (_e, _f, nodes, _c, _n) in mesh.skin(k)]
    R.iters = info.get("iters", 0)
    R.converged = bool(info.get("converged", True))
    R.rim_nodes = set(case.rigid_nodes)
    if info.get("plastic_skipped"):
        R.screened, R.screen_ratio = True, float(info.get("screen", 0.0))
    if info.get("plastic_failed"):
        R.collapsed, R.load_frac = True, float(info.get("load_frac", 0.0))

    # ---------------------------------------------------------------- pernos: fuerzas de los resortes
    for mb, b in zip(case.meta["bolts"], mdl.bolts):
        refs = mb["refs"]
        ax = np.asarray(mb["axis"], float)
        planes = []
        for i in range(len(refs) - 1):
            comp = []
            for sh in mb["shear"]:
                if sh["plane"] != i:
                    continue
                d = sh["dof"] - 1
                comp.append(mb["ks"] * (disp[refs[i + 1]][d] - disp[refs[i]][d]))
            planes.append(math.sqrt(sum(c * c for c in comp)))
        T = 0.0
        if len(refs) >= 2:
            el = float(np.dot(np.asarray(disp[refs[-1]]) - np.asarray(disp[refs[0]]), ax))
            T = max(mb["kax"] * el, 0.0)
        R.bolts.append(BoltRes(b.tag, tuple(b.p), max(planes, default=0.0), T, planes, b.db, b.grade, b.planes))

    # ---------------------------------------------------------------- soldaduras: traccion en el plano de la garganta
    parts_of = {}
    for k in mesh.names:
        for n in np.unique(mesh.E[k]):
            parts_of.setdefault(int(n), set()).add(k)
    for mw in case.meta["welds"]:
        key = mw["key"]
        if key not in mesh.E or not len(mesh.E[key]):
            continue
        nA, nB = np.asarray(mw["nA"], float), np.asarray(mw["nB"], float)
        m = (nA - nB) / np.linalg.norm(nA - nB)                  # normal del plano de la garganta
        free = [int(n) for n in np.unique(mesh.E[key]) if parts_of[int(n)] == {key} and int(n) in stress]
        if not free:
            continue
        vals, pts = [], []
        for n in free:
            sx, sy, sz, sxy, syz, szx = stress[n]
            S = np.array([[sx, sxy, szx], [sxy, sy, syz], [szx, syz, sz]])
            vals.append(float(np.linalg.norm(S @ m)))
            pts.append(R.nodes[n])
        vals = np.array(vals)
        L = float(np.linalg.norm(np.asarray(mw["p1"]) - np.asarray(mw["p0"])))
        i_max = int(np.argmax(vals))
        R.welds.append(WeldRes(mw["name"], mw.get("group", ""), float(np.percentile(vals, 95)), float(vals.mean()), PHI_WELD * 0.60 * mw["fexx"],
                               mw["w"], L, tuple(pts[i_max])))

    # ---------------------------------------------------------------- contacto y equilibrio
    kc = case.kc
    pm = 0.0
    for i, (_e, n1, n2, dof, k) in enumerate(case.gaps):
        if info.get("gap_on") is not None and i not in info["gap_on"]:
            continue
        d = disp[n2][dof - 1] - disp[n1][dof - 1]
        if d < 0:
            pm = max(pm, kc * (-d))
    R.pmax = pm
    R.n_contacts = len(info.get("gap_on", case.gaps)) if info.get("gap_on") is not None else len(case.gaps)
    sf = np.zeros(3)
    for s in case.meta["supports"]:
        for n in s["nodes"]:
            if n in forc:
                sf += np.asarray(forc[n])
    lf = np.zeros(3)
    for ld, ml in zip(mdl.loads, case.meta["loads"]):
        lf += np.asarray(ld.F, float)
    free = [d for d in range(3) if not any((d + 1) in ld.fix_ref for ld in mdl.loads)]       # componentes cuya reaccion esta en los apoyos
    res_v = (sf + lf)[free] if free else np.zeros(1)
    R.equil = (float(np.linalg.norm(res_v)), float(np.linalg.norm(lf[free])) if free else 0.0)        # (residuo, carga aplicada)

    # ---------------------------------------------------------------- deformacion plastica y von Mises por pieza (dentro de la zona)
    z = mdl.zone
    def in_zone(x, y, zz):
        return z is None or (z[0] <= x <= z[1] and z[2] <= y <= z[3] and z[4] <= zz <= z[5])
    from scipy.spatial import cKDTree
    for p in mdl.parts:
        nodes = [int(n) for n in mesh.part_nodes(p.name) if int(n) not in case.rigid_nodes and in_zone(*R.nodes[int(n)])]
        if not nodes:
            continue
        P = np.array([R.nodes[n] for n in nodes])
        vmv = np.array([R.vm.get(n, 0.0) for n in nodes])
        i = int(vmv.argmax())
        R.vm_parts[p.name] = (float(vmv[i]), *map(float, P[i]))
        if R.plastic:
            V = np.array([R.peeq.get(n, 0.0) for n in nodes])
            i = int(V.argmax())
            t_part = float(np.min(p.bbox()[1] - p.bbox()[0]))
            r = max(min(t_part, 1.0), lc / 1.2 if lc else 0.3)
            tree = cKDTree(P)
            sm = np.array([V[ix].mean() for ix in tree.query_ball_point(P, r)])
            j = int(sm.argmax())
            R.peeq_parts[p.name] = {"raw": (float(V[i]), *map(float, P[i])), "avg": (float(sm[j]), *map(float, P[j])), "r": r}
    R.ok = True
    R.msg = (f"{R.n_nodes:,} nodos y {R.n_elems:,} tetraedros.  |U| max = {R.umax:.4f} in ;  von Mises max = {R.vmmax:.1f} ksi")
    return R


# ================================================================================ verificaciones
def bolt_caps(R: FemResult):
    """Resistencias de diseno de cada perno: φRnv por plano de corte y φRnt reducida por el cortante concomitante (AISC J3.6, J3.7)."""
    for b in R.bolts:
        Ab = math.pi * b.db ** 2 / 4.0
        b.phiV = PHI_BOLT * FNV[b.grade] * Ab
        b.phiT = bolt_tension_shear(b.db, b.grade, (b.V / Ab) if Ab > 0 else 0.0)


def fem_checks(mdl, R: FemResult, prj, rec=None) -> list:
    """Filas del veredicto que salen del analisis 3D: pernos, cordones y deformacion plastica."""
    u = prj.units()
    out = []
    mesh_txt = (f"malla de {u.q('L', R.lc)}" if R.lc else "malla") + f", {R.n_nodes:,} nodos"
    bolt_caps(R)
    if R.bolts:
        bv = max(R.bolts, key=lambda b: b.V / b.phiV)
        out.append(Check("fem_bolt_v", "FEM 3D — cortante maximo en un perno (por plano)", bv.V, bv.phiV, "kip", "AISC J3.6",
                         f"{bv.tag}; {len(bv.planes)} plano(s); {mesh_txt}"))
        bt = max(R.bolts, key=lambda b: b.T / b.phiT if b.phiT > 0 else 0.0)
        out.append(Check("fem_bolt_t", "FEM 3D — traccion maxima en un perno (con cortante, J3.7)", bt.T, bt.phiT, "kip", "AISC J3.6, J3.7",
                         f"{bt.tag}; cortante concomitante {u.q('F', bt.V)}", skip=bt.T <= 1e-6))
    for i, w in enumerate(R.welds):
        F = max(1.0, float(getattr(prj.fea, "weld_peak_factor", 1.5)))
        dem = max(w.stress_max / F, w.stress_avg)
        out.append(Check(f"fem_weld{i}", f"FEM 3D — soldadura {w.name}", dem, w.cap, "ksi", "AISC J2.4",
                         f"traccion resultante en la garganta: pico {u.q('S', w.stress_max)} (limite {F:g}x), media {u.q('S', w.stress_avg)}; "
                         f"cateto {u.q('L', w.w)}; cordon elastico (singularidades en los extremos)"))
    lim = float(getattr(prj.fea, "plastic_limit", 5.0))
    if R.collapsed:
        out.append(Check("fem_cap", "FEM 3D — capacidad (el analisis elasto-plastico no alcanza la carga de diseno)", 100.0, max(100.0 * R.load_frac, 1e-6), "%",
                         "analisis elasto-plastico (φ·Fy)", f"el calculo deja de converger al {100 * R.load_frac:.0f} % de la carga: colapso plastico o inestabilidad"))
    if R.plastic:
        for key, d in R.peeq_parts.items():
            if R.model is not None and R.model.part(key) is not None and R.model.part(key).no_peeq:
                continue
            a = d["avg"]
            lbl = R.labels.get(key, key)
            out.append(Check(f"fem_peeq_{_san(key)}", f"FEM 3D — deformacion plastica equivalente: {lbl}", a[0] * 100.0, lim, "%",
                             "deformacion plastica admisible",
                             f"promedio en r = {u.q('L', d['r'])}; pico nodal {d['raw'][0] * 100:.3f} %; maximo en "
                             f"({u.fmt('L', a[1])}, {u.fmt('L', a[2])}, {u.fmt('L', a[3])}) {u.L}"))
    elif R.screened:
        for p in mdl.parts:
            if p.no_peeq or p.hard:
                continue
            out.append(Check(f"fem_peeq_{_san(p.name)}", f"FEM 3D — deformacion plastica equivalente: {R.labels.get(p.name, p.name)}", 0.0, lim, "%",
                             "deformacion plastica admisible",
                             f"sin plastificacion: el von Mises promediado maximo del conjunto es {100 * R.screen_ratio:.0f} % de φ·Fy (< 80 %), por lo que no se corrio el paso elasto-plastico"))
    else:
        for key, (v, x, y, z) in R.vm_parts.items():
            p = mdl.part(key)
            if p is None:
                continue
            out.append(Check(f"fem_vm_{_san(key)}", f"FEM 3D — von Mises maximo: {R.labels.get(key, key)}", v, 0.9 * p.Fy, "ksi",
                             "criterio del programa: <= 0.90·Fy (pico puntual: depende de la malla)", "", skip=True))
    return out


def _san(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s)
