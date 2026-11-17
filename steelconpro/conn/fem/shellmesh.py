# -*- coding: utf-8 -*-
"""Modelo de PLACAS (cascarones) del FEM: cada pieza del modelo 3D se reduce a su SUPERFICIE MEDIA con su espesor, como en IDEA StatiCa / RAM Connection.

· `build_plates(mdl)` convierte los prismas de cada pieza en placas (polígono plano en 3D + espesor + normal):
    - placa plana (espesor en la dirección de extrusión W): el polígono a mitad del espesor;
    - rectángulo delgado en su propio plano (alas y alma de un perfil I, paredes de un HSS, piernas de un ángulo): la superficie media de ese rectángulo extruido;
    - tubo redondo: facetas sobre el radio medio;
    - recortes planos (`cut_planes`) y agujeros (`holes_extra`, pernos y anclajes) se respetan.
· `snap_plates` lleva el borde de una placa hasta la superficie media de la placa perpendicular contra la que apoya (alma contra ala, placa soldada contra ala, pared de HSS contra pared):
  así las placas comparten arista (malla conforme y unión continua, como una soldadura de penetración completa en el modelo de placas).
· El mallado lo hace Gmsh en un proceso hijo (`run.py --meshs`): superficies planas fragmentadas (nodos compartidos), cuadriláteros cuando se puede.
"""
from __future__ import annotations
import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

TOL = 1e-6


def unit(v):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


@dataclass
class Plate:
    key: str                     # identificador unico
    part: str                    # pieza del modelo 3D a la que pertenece
    kind: str                    # tipo de la pieza (beam, plate, ...)
    P: np.ndarray                # vertices (n, 3) del contorno
    t: float                     # espesor
    n: np.ndarray                # normal de la superficie media
    holes: list = field(default_factory=list)       # [(m, 3)] agujeros (pernos, anclajes, aberturas)

    @property
    def c(self):
        return self.P.mean(axis=0)

    def basis(self):
        n = unit(self.n)
        a = unit(self.P[1] - self.P[0]) if len(self.P) > 1 else np.array([1.0, 0, 0])
        a = unit(a - n * float(a @ n))
        return a, np.cross(n, a), n


# ---------------------------------------------------------------------------------------------- geometria 2D
def _in_poly(pt, poly):
    x, y = pt
    ins = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-300) + x0:
            ins = not ins
    return ins


def _dist_poly(pt, poly):
    best = 1e18
    n = len(poly)
    p = np.asarray(pt, float)
    for i in range(n):
        a, b = np.asarray(poly[i], float), np.asarray(poly[(i + 1) % n], float)
        ab = b - a
        L2 = float(ab @ ab)
        s = 0.0 if L2 < 1e-18 else min(1.0, max(0.0, float((p - a) @ ab) / L2))
        best = min(best, float(np.linalg.norm(p - (a + s * ab))))
    return best


def _near_plate(pl: Plate, x, margin):
    """¿El punto 3D x (ya sobre el plano de `pl`) cae dentro del contorno de la placa o a menos de `margin` de él?"""
    a, b, _n = pl.basis()
    c = pl.c
    poly = [((q - c) @ a, (q - c) @ b) for q in pl.P]
    pt = ((x - c) @ a, (x - c) @ b)
    return _in_poly(pt, poly) or _dist_poly(pt, poly) <= margin


def _clip_plane(P, p0, nrm):
    """Recorta el poligono 3D P conservando nrm·(x − p0) <= 0 (Sutherland–Hodgman)."""
    out = []
    n = len(P)
    f = [float(nrm @ (q - p0)) for q in P]
    for i in range(n):
        q, r = P[i], P[(i + 1) % n]
        fq, fr = f[i], f[(i + 1) % n]
        if fq <= 0:
            out.append(q)
        if (fq < 0 < fr) or (fr < 0 < fq):
            s = fq / (fq - fr)
            out.append(q + s * (r - q))
    return np.array(out) if len(out) >= 3 else None


def _is_rect(poly):
    if len(poly) != 4:
        return None
    xs = sorted({round(float(q[0]), 7) for q in poly})
    ys = sorted({round(float(q[1]), 7) for q in poly})
    if len(xs) == 2 and len(ys) == 2:
        return xs[0], xs[1], ys[0], ys[1]
    return None


# ---------------------------------------------------------------------------------------------- prismas -> placas
def _prism_plates(part, ip, pr, notes):
    U, V, W = (np.asarray(x, float) for x in (pr.U, pr.V, pr.W))
    o = np.asarray(pr.o, float)
    w0, w1 = float(pr.w0), float(pr.w1)
    tw = w1 - w0
    g = lambda u, v, w: o + u * U + v * V + w * W                                  # noqa: E731
    out = []

    def add(k, P, t, n, holes=()):
        P = np.asarray(P, float)
        for pl_cut in pr.cut_planes:                                                 # recortes planos del prisma (bisel de cartela, inglete)
            p0, nrm = np.asarray(pl_cut[0], float), unit(pl_cut[1])
            P = _clip_plane(P, p0, nrm)
            if P is None:
                return
        P = _clean(P)                                                                # sin vertices colineales (si no, el ajuste de bordes deja astillas)
        if P is None:
            return
        out.append(Plate(f"{part.name}#{ip}.{k}", part.name, part.kind, P, float(t), unit(n), [np.asarray(h, float) for h in holes]))

    if pr.circle is not None:                                                         # cilindro / tubo redondo: facetas sobre el radio medio
        ro, ri = pr.circle
        t = (ro - ri) if ri > 0 else max(min(ro, 0.5), 1e-3)
        rm = ro - t / 2.0
        ns = 24
        for k in range(ns):
            a0, a1 = 2 * math.pi * k / ns, 2 * math.pi * (k + 1) / ns
            p00, p10 = g(rm * math.cos(a0), rm * math.sin(a0), w0), g(rm * math.cos(a1), rm * math.sin(a1), w0)
            p11, p01 = g(rm * math.cos(a1), rm * math.sin(a1), w1), g(rm * math.cos(a0), rm * math.sin(a0), w1)
            am = 0.5 * (a0 + a1)
            add(k, [p00, p10, p11, p01], t, math.cos(am) * U + math.sin(am) * V)
        return out
    poly = [(float(q[0]), float(q[1])) for q in pr.poly]
    if pr.holes:                                                                       # tubo poligonal: paredes entre exterior e interior
        inner = [(float(q[0]), float(q[1])) for q in pr.holes[0]]
        mid = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(poly, inner)]
        for k in range(len(mid)):
            (u0, v0), (u1, v1) = mid[k], mid[(k + 1) % len(mid)]
            t = 0.5 * (math.hypot(poly[k][0] - inner[k][0], poly[k][1] - inner[k][1]) + math.hypot(poly[(k + 1) % len(mid)][0] - inner[(k + 1) % len(mid)][0], poly[(k + 1) % len(mid)][1] - inner[(k + 1) % len(mid)][1])) / 1.0
            e = np.array([u1 - u0, v1 - v0])
            if float(np.linalg.norm(e)) < 1e-9:
                continue
            nn = unit(np.array([e[1], -e[0]])[0] * U + np.array([e[1], -e[0]])[1] * V)
            add(k, [g(u0, v0, w0), g(u1, v1, w0), g(u1, v1, w1), g(u0, v0, w1)], t / 1.4142, nn)
        return out
    rc = _is_rect(poly)
    L = float(len(poly))
    if rc is not None:
        u0, u1, v0, v1 = rc
        du, dv = u1 - u0, v1 - v0
        if min(du, dv) < tw * 0.999:                                                    # delgado en su propio plano (ala, alma, pared)
            if du <= dv:
                um = 0.5 * (u0 + u1)
                add(0, [g(um, v0, w0), g(um, v1, w0), g(um, v1, w1), g(um, v0, w1)], du, U)
            else:
                vm = 0.5 * (v0 + v1)
                add(0, [g(u0, vm, w0), g(u1, vm, w0), g(u1, vm, w1), g(u0, vm, w1)], dv, V)
            return out
    elif len(poly) == 6:                                                                # perfil L (angulo): dos piernas
        us = sorted({round(q[0], 7) for q in poly})
        vs = sorted({round(q[1], 7) for q in poly})
        if len(us) == 3 and len(vs) == 3 and min(us[1] - us[0], vs[1] - vs[0]) < tw:
            t = us[1] - us[0]
            leg_b, leg_a = us[2], vs[2]
            tv = vs[1] - vs[0]
            add(0, [g(t / 2, 0, w0), g(t / 2, leg_a, w0), g(t / 2, leg_a, w1), g(t / 2, 0, w1)], t, U)
            add(1, [g(t / 2, tv / 2, w0), g(leg_b, tv / 2, w0), g(leg_b, tv / 2, w1), g(t / 2, tv / 2, w1)], tv, V)
            return out
    # placa plana: el poligono a mitad del espesor
    holes = []
    for h in pr.holes_extra:
        holes.append([g(float(q[0]), float(q[1]), 0.5 * (w0 + w1)) for q in h])
    area = 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))))
    per = sum(math.hypot(poly[i][0] - poly[(i + 1) % len(poly)][0], poly[i][1] - poly[(i + 1) % len(poly)][1]) for i in range(len(poly)))
    t_in = 2.0 * area / max(per, 1e-9)
    if t_in < 0.45 * tw and rc is None:
        notes.append(f"{part.name}: su sección no se pudo reducir a placas (perfil libre); se modela como placa plana.")
    add(0, [g(u, v, 0.5 * (w0 + w1)) for (u, v) in poly], tw, W, holes)
    return out


def _clean(P, tol=1e-4):
    """Contorno sin vertices repetidos ni colineales; None si queda degenerado."""
    P = [np.asarray(q, float) for q in P]
    out = []
    for q in P:
        if not out or float(np.linalg.norm(q - out[-1])) > tol:
            out.append(q)
    if len(out) > 1 and float(np.linalg.norm(out[0] - out[-1])) <= tol:
        out.pop()
    changed = True
    while changed and len(out) >= 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            ab, bc = b - a, c - b
            if float(np.linalg.norm(np.cross(ab, bc))) <= 1e-6 * max(float(np.linalg.norm(ab)) * float(np.linalg.norm(bc)), 1e-12) + 1e-9:
                out.pop(i)
                changed = True
                break
    if len(out) < 3:
        return None
    A = np.zeros(3)
    for i in range(len(out)):
        A += np.cross(out[i], out[(i + 1) % len(out)])
    return np.array(out) if float(np.linalg.norm(A)) / 2.0 > 1e-4 else None


def build_plates(mdl):
    """(placas, notas) del modelo 3D."""
    plates, notes = [], []
    for part in mdl.parts:
        for ip, pr in enumerate(part.prisms):
            plates += _prism_plates(part, ip, pr, notes)
    snap_plates(plates)
    add_bolt_holes(mdl, plates)
    out = []
    for pl in plates:                                                                # tras el ajuste pueden quedar vertices repetidos o placas colapsadas
        P = _clean(pl.P)
        if P is None:
            notes.append(f"{pl.part}: una placa quedó degenerada y se omite del modelo de placas.")
            continue
        pl.P = P
        out.append(pl)
    return out, notes


# ---------------------------------------------------------------------------------------------- uniones
def snap_plates(plates, gap_tol=0.06):
    """Lleva cada borde que apoya contra la superficie de otra placa (a menos de la mitad del espesor de esa placa) hasta su superficie media."""
    for P in plates:
        n = len(P.P)
        for i in range(n):
            a, b = P.P[i].copy(), P.P[(i + 1) % n].copy()
            e = b - a
            Le = float(np.linalg.norm(e))
            if Le < 1e-6:
                continue
            ed = e / Le
            m = np.cross(P.n, ed)
            best = None
            for Q in plates:
                if Q is P:
                    continue
                nq = Q.n
                if abs(float(P.n @ nq)) > 0.9:                                     # paralelas: contacto, no union
                    continue
                if abs(float(ed @ nq)) > 0.12:                                     # el borde debe ser paralelo al plano de Q
                    continue
                cq = Q.c
                da, db = float((a - cq) @ nq), float((b - cq) @ nq)
                if abs(da - db) > 0.05:
                    continue
                if abs(da) < 1e-5 or abs(da) > Q.t / 2.0 + gap_tol:
                    continue
                mn = float(m @ nq)
                if abs(mn) < 0.35:
                    continue
                s = -da / mn
                mid = 0.5 * (a + b) + s * m
                if not _near_plate(Q, mid - float((mid - cq) @ nq) * nq, Q.t + 0.1):
                    continue
                if best is None or abs(s) < abs(best):
                    best = s
            if best is not None:
                P.P[i] = a + best * m
                P.P[(i + 1) % n] = b + best * m
    return plates


def add_bolt_holes(mdl, plates, nseg=12):
    """Agujero circular en cada placa que atraviesa un perno o anclaje (eje perpendicular a la placa y dentro de ella)."""
    by_part = {}
    for pl in plates:
        by_part.setdefault(pl.part, []).append(pl)
    for b in mdl.bolts:
        ax = unit(b.axis)
        p0 = np.asarray(b.p, float)
        for (pn, _s0, _s1) in b.grip:
            for pl in by_part.get(pn, []):
                dn = float(ax @ pl.n)
                if abs(dn) < 0.9:
                    continue
                s = float((pl.c - p0) @ pl.n) / dn
                x = p0 + s * ax
                if not _near_plate(pl, x, 0.0):
                    continue
                if _dist_poly_3d(pl, x) < 0.55 * b.dh:
                    continue
                if any(float(np.linalg.norm(np.mean(h, axis=0) - x)) < 0.6 * b.dh for h in pl.holes):          # ya hay un agujero ahi (otro perno coincidente o el agujero de la placa)
                    break
                a, bb, n_ = pl.basis()
                ring = [x + 0.5 * b.dh * (math.cos(2 * math.pi * k / nseg) * a + math.sin(2 * math.pi * k / nseg) * bb) for k in range(nseg)]
                pl.holes.append(np.array(ring))
                break


def _dist_poly_3d(pl, x):
    a, b, _n = pl.basis()
    c = pl.c
    poly = [((q - c) @ a, (q - c) @ b) for q in pl.P]
    return _dist_poly(((x - c) @ a, (x - c) @ b), poly)


# ---------------------------------------------------------------------------------------------- mallado (proceso hijo)
def shell_params(fea, mdl, f: float = 1.0) -> dict:
    fine = str(getattr(fea, "mesh3d_mode", "")).startswith("Fina")
    manual = float(getattr(fea, "mesh3d", 0.0) or 0.0)
    near = manual if manual > 0 else (0.55 if fine else 0.9)
    near *= f
    return {"h_near": near, "h_far": max(2.5 * near, 2.0), "h_hole": max(0.45 * near, 0.25), "zone": list(mdl.zone) if mdl.zone else None, "transition": 4.0 * near}


def write_job(plates, params, path):
    data = {"plates": [{"key": p.key, "part": p.part, "kind": p.kind, "t": p.t, "n": p.n.tolist(), "P": p.P.tolist(), "holes": [h.tolist() for h in p.holes]} for p in plates],
            "params": params}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def mesh_job(job: dict, out_npz: str) -> dict:
    import gmsh
    plates, P = job["plates"], job["params"]
    gmsh.initialize(["gmsh", "-nopopup"], interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)                                # el mallado 2D es rapido y en paralelo falla de forma intermitente
        gmsh.model.add("placas")
        occ = gmsh.model.occ
        surfs = []
        for pl in plates:
            def loop(pts):
                ids = [occ.addPoint(*q) for q in pts]
                lns = [occ.addLine(ids[i], ids[(i + 1) % len(ids)]) for i in range(len(ids))]
                return occ.addCurveLoop(lns)
            loops = [loop(pl["P"])] + [loop(h) for h in pl["holes"]]
            try:
                sid = occ.addPlaneSurface(loops)
            except Exception:                                                        # contorno degenerado: se omite
                sid = None
            surfs.append((2, sid) if sid is not None else None)
        flat = [s for s in surfs if s is not None]
        _out, omap = occ.fragment(flat, [])
        occ.synchronize()
        res, k = {}, 0
        for i, s in enumerate(surfs):
            if s is None:
                continue
            res[i] = [d for d in omap[k] if d[0] == 2]
            k += 1
        fld = gmsh.model.mesh.field
        ids = []
        z = P.get("zone")
        if z:
            i = fld.add("Box")
            fld.setNumber(i, "VIn", P["h_near"]); fld.setNumber(i, "VOut", P["h_far"])
            for kk, (a, b) in enumerate(zip(z[0::2], z[1::2])):
                fld.setNumber(i, "XYZ"[kk] + "Min", float(a)); fld.setNumber(i, "XYZ"[kk] + "Max", float(b))
            fld.setNumber(i, "Thickness", P["transition"])
            ids.append(i)
        else:
            i = fld.add("MathEval"); fld.setString(i, "F", str(P["h_near"])); ids.append(i)
        # refinamiento alrededor de los agujeros
        hole_curves = []
        for pl, s in zip(plates, surfs):
            if s is None or not pl["holes"]:
                continue
            for h in pl["holes"]:
                c = np.mean(h, axis=0)
                r = float(np.max(np.linalg.norm(np.asarray(h) - c, axis=1)))
                for (d_, t_) in gmsh.model.getEntitiesInBoundingBox(*(c - r - 0.05), *(c + r + 0.05), 1):
                    hole_curves.append(t_)
        if hole_curves:
            dist = fld.add("Distance")
            fld.setNumbers(dist, "CurvesList", sorted(set(hole_curves)))
            fld.setNumber(dist, "Sampling", 20)
            th = fld.add("Threshold")
            fld.setNumber(th, "InField", dist)
            fld.setNumber(th, "SizeMin", P["h_hole"]); fld.setNumber(th, "SizeMax", 1e22)
            fld.setNumber(th, "DistMin", 0.1); fld.setNumber(th, "DistMax", 0.1 + 2.0 * P["h_hole"])
            ids.append(th)
        fm = fld.add("Min")
        fld.setNumbers(fm, "FieldsList", ids)
        fld.setAsBackgroundMesh(fm)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.05)
        gmsh.option.setNumber("Mesh.MeshSizeMax", max(P["h_far"], 1.0) * 2)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 0)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(2)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(tags)
        out = {"node_id": np.asarray(tags, np.int64)[order], "xyz": np.asarray(xyz, float).reshape(-1, 3)[order]}
        keys = []
        for i, pl in enumerate(plates):
            tri, quad = [], []
            for (_d, st) in res.get(i, []):
                et, _etag, enode = gmsh.model.mesh.getElements(2, st)
                for t_, en in zip(et, enode):
                    if t_ == 2:
                        tri.append(np.asarray(en, np.int64).reshape(-1, 3))
                    elif t_ == 3:
                        quad.append(np.asarray(en, np.int64).reshape(-1, 4))
            out[f"t_{i}"] = np.concatenate(tri) if tri else np.zeros((0, 3), np.int64)
            out[f"q_{i}"] = np.concatenate(quad) if quad else np.zeros((0, 4), np.int64)
            keys.append(pl["key"])
        out["keys"] = np.array(json.dumps(keys))
        out["parts"] = np.array(json.dumps([p["part"] for p in plates]))
        out["kinds"] = np.array(json.dumps([p["kind"] for p in plates]))
        out["thick"] = np.array([p["t"] for p in plates], float)
        np.savez_compressed(out_npz, **out)
        n_el = int(sum(len(out[f"t_{i}"]) + len(out[f"q_{i}"]) for i in range(len(plates))))
        return {"nodes": int(len(tags)), "elems": n_el}
    finally:
        gmsh.finalize()


def child(job_json: str, out_npz: str) -> int:
    with open(job_json, encoding="utf-8") as f:
        job = json.load(f)
    info = mesh_job(job, out_npz)
    print(json.dumps(info))
    return 0 if os.path.exists(out_npz) else 3


class ShellMesh:
    """Malla de placas leida del .npz: nodos, y por placa sus triangulos y cuadrilateros (indices a `xyz`)."""

    def __init__(self, path):
        z = np.load(path, allow_pickle=False)
        self.node_ids = z["node_id"]
        self.xyz = z["xyz"]
        self.keys = json.loads(str(z["keys"]))
        self.parts = json.loads(str(z["parts"]))
        self.kinds = json.loads(str(z["kinds"]))
        self.thick = z["thick"]
        self.tri = [z[f"t_{i}"] for i in range(len(self.keys))]
        self.quad = [z[f"q_{i}"] for i in range(len(self.keys))]
        self.index = {int(n): i for i, n in enumerate(self.node_ids)}

    @property
    def n_elems(self):
        return int(sum(len(t) for t in self.tri) + sum(len(q) for q in self.quad))

    def polygons(self, i):
        """Poligonos (3 o 4 vertices) de la placa i."""
        out = []
        for row in self.tri[i]:
            out.append([tuple(self.xyz[self.index[int(n)]]) for n in row])
        for row in self.quad[i]:
            out.append([tuple(self.xyz[self.index[int(n)]]) for n in row])
        return out
