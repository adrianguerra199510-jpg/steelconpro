# -*- coding: utf-8 -*-
"""Resultados del analisis del modelo de placas: campos por elemento (von Mises en las caras, deformacion plastica), desplazamientos,
fuerzas de pernos y anclajes, fuerza por unidad de largo de los cordones, y la escena de resultados para el visor."""
from __future__ import annotations
import math
from dataclasses import dataclass, field

import numpy as np

from .model3d import unit
from .shellccx import read_dat, read_frd_u, surface_stresses, _vm

PLASTIC_LIMIT = 0.05            # deformacion plastica admisible (5 %)


@dataclass
class ShellResult:
    ok: bool = False
    msg: str = ""
    notes: list = field(default_factory=list)
    plastic: bool = False
    plastic_failed: bool = False
    iters: int = 0
    folder: str = ""
    sig: str = ""
    case: str = ""
    # malla
    node_ids: np.ndarray = None
    xyz: np.ndarray = None
    U: np.ndarray = None                   # (n, 3) desplazamientos de los nodos de la malla
    elems: list = field(default_factory=list)       # [(id, [indices locales de nodos], placa)]
    e_vm: np.ndarray = None                # von Mises maximo de las dos caras, ksi
    e_vm_avg: np.ndarray = None            # ... promediado en un radio del orden del espesor (sin picos puntuales)
    e_peeq: np.ndarray = None              # deformacion plastica equivalente maxima
    plate_part: list = field(default_factory=list)
    plate_kind: list = field(default_factory=list)
    plate_t: list = field(default_factory=list)
    # resumen
    parts: dict = field(default_factory=dict)       # pieza -> {kind, Fy, vm, peeq, vm_zone, peeq_zone, where}
    bolts: list = field(default_factory=list)
    welds: list = field(default_factory=list)
    umax: float = 0.0
    vmmax: float = 0.0
    peeqmax: float = 0.0
    n_nodes: int = 0
    n_elems: int = 0
    member_names: set = field(default_factory=set)
    n_bad: int = 0                         # elementos astilla (no se usan para evaluar esfuerzos)


def _part_info(mdl):
    return {p.name: p for p in mdl.parts}


def postprocess(case, info, members=(), case_name="") -> ShellResult:
    R = ShellResult(ok=True, notes=list(case.notes), plastic=bool(info.get("plastic")), plastic_failed=bool(info.get("plastic_failed")),
                    iters=int(info.get("iters", 0)), case=case_name)
    R.member_names = set(members)
    Uall = read_frd_u(info["frd"])
    S, PE, UR = read_dat(info["dat"])
    Uall.update(UR)
    R.node_ids = case.node_ids
    R.xyz = case.xyz
    R.U = np.array([Uall.get(int(n), np.zeros(3)) for n in case.node_ids], float).reshape(-1, 3)
    R.plate_part = list(case.sm.parts)
    R.plate_kind = list(case.sm.kinds)
    R.plate_t = [float(t) for t in case.sm.thick]
    idx = case.index
    R.elems = [(e, [idx[n] for n in ns], p) for e, ns, p in case.elems]
    vm = np.zeros(len(R.elems))
    pe = np.zeros(len(R.elems))
    for k, (e, _ns, _p) in enumerate(R.elems):
        s = S.get(e)
        if s is not None and len(s):
            a, b, _m = surface_stresses(s)
            vm[k] = float(max(_vm(a), _vm(b)))
        pe[k] = float(PE.get(e, 0.0))
    R.e_vm, R.e_peeq = vm, pe
    from .shellccx import averaged_vm
    avg = averaged_vm(case, {e: float(vm[k]) for k, (e, _ns, _p) in enumerate(R.elems)})
    R.e_vm_avg = np.array([avg.get(e, float(vm[k])) for k, (e, _ns, _p) in enumerate(R.elems)])
    from .shellccx import elem_quality, QMIN
    bad = np.array([elem_quality(R.xyz[ns]) < QMIN for _e, ns, _p in R.elems], bool)
    vm[bad] = R.e_vm_avg[bad]                                   # astillas de la malla: su esfuerzo no es fiable; se muestra el de sus vecinos
    R.n_bad = int(bad.sum())
    R.n_nodes, R.n_elems = len(case.node_ids), len(R.elems)
    R.umax = float(np.linalg.norm(R.U, axis=1).max()) if len(R.U) else 0.0
    R.vmmax = float(vm.max()) if len(vm) else 0.0
    R.peeqmax = float(pe.max()) if len(pe) else 0.0
    # ---- por pieza (en la zona de la conexion: sin los elementos de los extremos rigidizados de apoyos y cargas)
    rigid = set()
    for ld in case.meta["loads"]:
        rigid.update(ld["nodes"])
    for sp in case.meta["supports"]:
        rigid.update(sp["nodes"])
    rigid_idx = {idx[n] for n in rigid if n in idx}
    parts = _part_info(case.mdl)
    near = 1.5 * case.h
    rigid_pts = R.xyz[sorted(rigid_idx)] if rigid_idx else np.zeros((0, 3))
    tree = None
    if len(rigid_pts):
        from scipy.spatial import cKDTree
        tree = cKDTree(rigid_pts)
    for k, (e, ns, p) in enumerate(R.elems):
        part = R.plate_part[p]
        d = R.parts.setdefault(part, {"kind": R.plate_kind[p], "Fy": float(getattr(parts.get(part), "Fy", 50.0) or 50.0), "vm": 0.0, "peeq": 0.0,
                                      "vm_peak": 0.0, "where_vm": None, "where_peeq": None, "t": 0.0, "n_el": 0})
        d["n_el"] += 1
        c = R.xyz[ns].mean(axis=0)
        if tree is not None and tree.query(c)[0] < near:
            continue
        if R.e_vm_avg[k] > d["vm"]:
            d["vm"], d["where_vm"], d["t"] = float(R.e_vm_avg[k]), c.tolist(), R.plate_t[p]
        d["vm_peak"] = max(d["vm_peak"], float(vm[k]))
        if pe[k] > d["peeq"]:
            d["peeq"], d["where_peeq"] = float(pe[k]), c.tolist()
    # ---- pernos y anclajes
    for mb in case.meta["bolts"]:
        if mb.get("skip"):
            continue
        b = case.mdl.bolts[mb["index"]]
        refs = mb["refs"]
        ax = np.asarray(mb["axis"], float)
        planes = []
        for i in range(len(refs) - 1):
            du = Uall.get(refs[i + 1], np.zeros(3)) - Uall.get(refs[i], np.zeros(3))
            dut = du - ax * float(du @ ax)
            planes.append({"V": float(mb["ks"] * np.linalg.norm(dut)), "dir": unit(dut).tolist() if np.linalg.norm(dut) > 1e-12 else [0, 0, 0],
                           "between": (mb["parts"][i], mb["parts"][i + 1])})
        du = Uall.get(refs[-1], np.zeros(3)) - Uall.get(refs[0], np.zeros(3))
        sgn = 1.0 if float((case.coord(refs[-1]) - case.coord(refs[0])) @ ax) >= 0 else -1.0
        el = float(du @ ax) * sgn
        on = mb["index"] in info.get("bolt_on", set()) or mb["index"] in case.bolt_bidir
        T = float(mb["kax"] * el) if on else 0.0
        if T < 0 and mb["index"] not in case.bolt_bidir:
            T = 0.0
        R.bolts.append({"tag": mb["tag"], "pos": mb["p"], "db": mb["db"], "dh": mb["dh"], "grade": mb["grade"], "anchor": mb["anchor"],
                        "parts": mb["parts"], "planes": planes, "V": max([q["V"] for q in planes] + [0.0]), "T": T, "axis": mb["axis"],
                        "group": getattr(b, "group", "") or mb["tag"].rsplit("-", 1)[0]})
    # ---- cordones: fuerza por unidad de largo transmitida por la placa que llega al cordon
    R.welds = _weld_forces(case, R, S)
    return R


def _weld_forces(case, R, S):
    """Para cada cordon, fuerza por unidad de largo (kip/in) que transmiten los elementos de la pieza A (si no, B) junto a la linea del cordon:
    membrana (σ·t, en el plano) mas la flexion (m / t, par de fuerzas en los dos lados).  Se reparte entre los cordones paralelos de la misma union
    (un cordon a cada lado) y se toma el maximo del promedio movil a lo largo del cordon (los picos de un elemento son singularidades)."""
    out = []
    elem_c = {}
    for k, (e, ns, p) in enumerate(R.elems):
        elem_c[e] = (R.xyz[ns].mean(axis=0), p)
    by_part = {}
    for e, (c, p) in elem_c.items():
        by_part.setdefault(R.plate_part[p], []).append(e)
    from scipy.spatial import cKDTree
    trees = {}
    for part, es in by_part.items():
        trees[part] = (np.array(es), cKDTree(np.array([elem_c[e][0] for e in es])))
    welds = case.meta["welds"]
    lines = [(np.asarray(w["p0"], float), np.asarray(w["p1"], float)) for w in welds]
    for iw, w in enumerate(welds):
        a, b = lines[iw]
        L = float(np.linalg.norm(b - a))
        if L < 1e-6:
            continue
        ed = (b - a) / L
        q_best, used = 0.0, None
        for side in (w["A"], w["B"]):
            if side not in trees:
                continue
            es, tr = trees[side]
            mid = 0.5 * (a + b)
            cand = tr.query_ball_point(mid, 0.5 * L + 1.2 * case.h)
            rows = []
            for j in cand:
                e = int(es[j])
                c, p = elem_c[e]
                v = c - a
                s_ = float(v @ ed)
                if s_ < -0.25 * case.h or s_ > L + 0.25 * case.h:
                    continue
                d = float(np.linalg.norm(v - ed * s_))
                if d > 1.0 * case.h:
                    continue
                nrm = unit(case.plates[p]["n"])
                if abs(float(nrm @ ed)) > 0.3:                    # la placa debe contener la direccion del cordon
                    continue
                m = unit(np.cross(nrm, ed))                       # normal al cordon en el plano de la placa
                st = S.get(e)
                if st is None or not len(st):
                    continue
                top, bot, mm = surface_stresses(st)
                t = R.plate_t[p]

                def tens(x):
                    return np.array([[x[0], x[3], x[4]], [x[3], x[1], x[5]], [x[4], x[5], x[2]]])
                tm = tens(mm) @ m * t                              # fuerza de membrana por unidad de largo (vector)
                sb = float(m @ (tens(top) - tens(mm)) @ m)         # esfuerzo de flexion normal al cordon
                mb_ = abs(sb) * t * t / 6.0
                q = float(np.linalg.norm(tm)) + mb_ / max(t, 1e-6)
                rows.append((s_, q))
            if rows and (used is None or side == w["A"]):
                rows.sort()
                qs = np.array([r[1] for r in rows])
                k = max(1, min(3, len(qs)))
                mov = np.convolve(qs, np.ones(k) / k, mode="valid") if len(qs) >= k else qs
                q_best, used = float(mov.max()), side
                break
        # cordones paralelos de la misma union (un cordon a cada lado de la placa): se reparte
        ns = 1
        for jw, w2 in enumerate(welds):
            if jw == iw or {w2["A"], w2["B"]} != {w["A"], w["B"]}:
                continue
            a2, b2 = lines[jw]
            e2 = unit(b2 - a2)
            if abs(float(e2 @ ed)) < 0.98:
                continue
            dist = float(np.linalg.norm((a2 - a) - ed * float((a2 - a) @ ed)))
            s0, s1 = sorted((float((a2 - a) @ ed), float((b2 - a) @ ed)))
            if dist < 1.5 + 2 * w["w"] and s1 > 0.1 * L and s0 < 0.9 * L:
                ns = 2
                break
        q = q_best / ns
        cap = 0.75 * 0.60 * w["fexx"] * 0.7071 * w["w"]           # φ·0.60·FEXX·0.707·w, kip/in (AISC J2.4, sin el aumento por direccion)
        out.append({"name": w["name"], "A": w["A"], "B": w["B"], "group": w.get("group", ""), "q": q, "cap": cap, "w": w["w"], "L": L,
                    "sides": ns, "from": used, "p0": w["p0"], "p1": w["p1"]})
    return out


# ================================================================================================== escena para el visor
FIELDS = [("vm", "Esfuerzo de von Mises"), ("peeq", "Deformación plástica"), ("u", "Desplazamiento")]


def scene(R: ShellResult, units, field="vm", scale=0.0, part="all", edges=True):
    from ...scene3d import Scene
    from ...view3d import _soft_cmap
    sc = Scene()
    kl, ks = units.fl, units.fs
    sel = [k for k, (_e, _ns, p) in enumerate(R.elems) if part == "all" or R.plate_part[p] == part]
    if not sel:
        sc.message = ("Sin elementos de esa pieza en el modelo.", "#777777")
        return sc
    P = R.xyz + (scale * R.U if scale > 0 else 0.0)
    Pm = P / kl
    if field == "u":
        nodal = np.linalg.norm(R.U, axis=1) / kl
        title, unit_ = "Desplazamiento |U|", units.L
    elif field == "peeq":
        val = R.e_peeq * 100.0
        title, unit_ = "Deformación plástica equivalente", "%"
    else:
        val = R.e_vm / ks
        title, unit_ = "Esfuerzo de von Mises (caras)", units.S
    cmap = _soft_cmap()
    if field == "u":
        vals = np.array([nodal[R.elems[k][1]].mean() for k in sel])
    else:
        vals = val[sel]
    vmin, vmax = (0.0, float(vals.max()) if len(vals) else 1.0)
    if field == "peeq":
        vmax = max(vmax, PLASTIC_LIMIT * 100.0)
    if vmax - vmin < 1e-12:
        vmax = vmin + 1.0
    V, T, C = [], [], []
    seg = []
    for j, k in enumerate(sel):
        _e, ns, _p = R.elems[k]
        base = len(V)
        if field == "u":
            cols = cmap(np.clip((nodal[ns] - vmin) / (vmax - vmin), 0, 1))
        else:
            cols = np.repeat(cmap(np.clip(np.array([(vals[j] - vmin) / (vmax - vmin)]), 0, 1)), len(ns), axis=0)
        for q, n in enumerate(ns):
            V.append(Pm[n])
            C.append(cols[q])
        T.append((base, base + 1, base + 2))
        if len(ns) == 4:
            T.append((base, base + 2, base + 3))
        if edges:
            for q in range(len(ns)):
                seg.append((Pm[ns[q]], Pm[ns[(q + 1) % len(ns)]]))
    sc.add_mesh(np.array(V), np.array(T), np.array(C))
    if seg:
        arr = np.zeros((2 * len(seg), 10), np.float32)
        A = np.array(seg)
        arr[0::2, 0:3], arr[1::2, 0:3] = A[:, 0], A[:, 1]
        arr[:, 6:10] = (0.08, 0.1, 0.14, 0.35)
        sc.lines.append(arr)
        sc.tagged.append(("other", "l", arr))
    sc.pts = np.array(V)
    jm = int(np.argmax(vals))
    _e, ns, _p = R.elems[sel[jm]]
    sc.markers.append((tuple(Pm[ns].mean(axis=0)), "#d62728"))
    txt = f"{title}: máximo = {vals[jm]:.4g} {unit_}"
    if field == "peeq":
        txt += f"   (límite {PLASTIC_LIMIT * 100:g} %)"
    if scale > 0:
        txt += f"   —   deformada ×{scale:g}"
    sc.hud.append(("bl", txt, "#7a1010", "#fff3e0", "#d62728"))
    sc.title = f"{title} ({unit_})"
    sc.cbar = dict(colors=cmap(np.linspace(0, 1, 64))[:, :3], vmin=vmin, vmax=vmax, note=None)
    return sc


def auto_scale(R: ShellResult) -> float:
    """Factor de la deformada para que el desplazamiento maximo se vea como ~4 % del tamano del modelo."""
    if R.umax <= 1e-12:
        return 1.0
    size = float(np.linalg.norm(np.ptp(R.xyz, axis=0)))
    f = 0.04 * size / R.umax
    mag = 10 ** math.floor(math.log10(max(f, 1e-9)))
    return float(min((c * mag for c in (1, 2, 5, 10) if c * mag >= f * 0.7), default=f))
