# -*- coding: utf-8 -*-
"""Geometria y malla del modelo 3D con la API de Gmsh (OpenCASCADE), tetraedros de segundo orden.

Corre en un proceso hijo (`run.py --meshm modelo.json malla.npz`, igual que el mallador de la placa base) para que un fallo de Gmsh no cierre la
ventana.  Cada pieza es un volumen independiente (los contactos y los cordones se resuelven en CalculiX); los agujeros de los pernos se restan
de las piezas que atraviesa cada perno; los cordones son prismas triangulares aparte."""
from __future__ import annotations
import json
import math
import os

import numpy as np

from .model3d import model_from_dict, weld_prism, unit, Prism


def _prism_vol(occ, pr: Prism):
    """Crea el volumen del prisma en coordenadas globales y devuelve su (3, tag)."""
    W = np.asarray(pr.W, float)
    L = pr.w1 - pr.w0
    if pr.circle is not None:
        ro, ri = pr.circle
        c0 = pr.to_global(0.0, 0.0, pr.w0)
        t = occ.addCylinder(*c0, *(W * L), ro)
        if ri > 0:
            ti = occ.addCylinder(*(c0 - W * 0.01), *(W * (L + 0.02)), ri)
            out, _ = occ.cut([(3, t)], [(3, ti)])
            return out[0]
        return (3, t)

    def loop(poly):
        pts = [occ.addPoint(*pr.to_global(u, v, pr.w0)) for (u, v) in poly]
        lns = [occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        return occ.addCurveLoop(lns)
    loops = [loop(pr.poly)] + [loop(h) for h in pr.holes]
    surf = occ.addPlaneSurface(loops)
    out = occ.extrude([(2, surf)], *(W * L))
    return next(dt for dt in out if dt[0] == 3)


def mesh_job(job: dict, out_npz: str) -> dict:
    import gmsh
    mdl = model_from_dict(job["model"])
    P = job["params"]
    gmsh.initialize(["gmsh", "-nopopup"], interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", max(1, (os.cpu_count() or 2) - 1))
        gmsh.model.add("conexion")
        occ = gmsh.model.occ
        vols = {}                                   # nombre -> [(3, tag)]
        for p in mdl.parts:
            dts = [_prism_vol(occ, pr) for pr in p.prisms]
            if len(dts) > 1:
                dts, _ = occ.fuse([dts[0]], dts[1:])
            for ct in p.cuts:
                tool = [_prism_vol(occ, ct)]
                dts, _ = occ.cut(dts, tool)
            holes = mdl.bolt_hole_prisms(p.name)
            if holes:
                tools = []
                for (c, ax, dh, ln) in holes:
                    ax = np.asarray(ax, float)
                    c0 = np.asarray(c, float) - ax * (ln / 2 + 0.05)
                    tools.append((3, occ.addCylinder(*c0, *(ax * (ln + 0.1)), dh / 2.0)))
                dts, _ = occ.cut(dts, tools)
            vols[p.name] = [d for d in dts if d[0] == 3]
        wvols = []
        for w in mdl.welds:
            wvols.append(_prism_vol(occ, weld_prism(w)))
        # union general (fragmentos): las caras que se tocan quedan con la misma malla (nodos compartidos); ccxgen separa despues
        # los nodos de las piezas que solo se apoyan (contacto) y deja unidos los cordones
        flat, owner = [], []
        for p in mdl.parts:
            for d in vols[p.name]:
                flat.append(d)
                owner.append(p.name)
        for w, wv in zip(mdl.welds, wvols):
            flat.append(wv)
            owner.append("W:" + w.name)
        _out, omap = occ.fragment(flat, [])
        vols = {}
        for d, own, ch in zip(flat, owner, omap):
            vols.setdefault(own, []).extend([c for c in ch if c[0] == 3])
        occ.synchronize()
        wvols = [vols.get("W:" + w.name, []) for w in mdl.welds]

        # ------------------------------------------------------------------ tamanos
        fld = gmsh.model.mesh.field
        ids = []

        def box(vin, vout, lo, hi, thick=0.0):
            i = fld.add("Box")
            fld.setNumber(i, "VIn", vin)
            fld.setNumber(i, "VOut", vout)
            for k, (a, b) in enumerate(zip(lo, hi)):
                fld.setNumber(i, "XYZ"[k] + "Min", float(a))
                fld.setNumber(i, "XYZ"[k] + "Max", float(b))
            fld.setNumber(i, "Thickness", thick)
            ids.append(i)
        z = mdl.zone
        for p in mdl.parts:
            lo, hi = p.bbox()
            lo, hi = lo - 0.02, hi + 0.02
            lc = P["part_lc"].get(p.name, P["lc_near"])
            far = P["part_far"].get(p.name, 0.0)
            if far > 0:
                zlo = np.array([z[0], z[2], z[4]]) if z else lo
                zhi = np.array([z[1], z[3], z[5]]) if z else hi
                box(lc, far, zlo, zhi, thick=P["transition"])
                box(far, 1e22, lo, hi)
            else:
                box(lc, 1e22, lo, hi)
        for w, wv in zip(mdl.welds, wvols):
            for dt in wv:
                bb = gmsh.model.getBoundingBox(*dt)
                box(P["lc_weld"], 1e22, np.array(bb[:3]) - 0.02, np.array(bb[3:]) + 0.02)
        # refinamiento alrededor de cada agujero
        hole_curves = []
        for b in mdl.bolts:
            ax = unit(b.axis)
            for (pn, s0, s1) in b.grip:
                c = np.asarray(b.p, float) + ax * 0.5 * (s0 + s1)
                half = np.abs(ax) * (0.5 * (s1 - s0) + 0.08) + (1 - np.abs(ax)) * (b.dh / 2 + 0.02)
                lo, hi = c - half, c + half
                for (d_, t_) in gmsh.model.getEntitiesInBoundingBox(*lo, *hi, 1):
                    hole_curves.append(t_)
        if hole_curves:
            dist = fld.add("Distance")
            fld.setNumbers(dist, "CurvesList", sorted(set(hole_curves)))
            fld.setNumber(dist, "Sampling", 40)
            th = fld.add("Threshold")
            fld.setNumber(th, "InField", dist)
            fld.setNumber(th, "SizeMin", P["lc_hole"])
            fld.setNumber(th, "SizeMax", 1e22)
            fld.setNumber(th, "DistMin", 0.12)
            fld.setNumber(th, "DistMax", 0.12 + 2.5 * P["lc_hole"])
            ids.append(th)
        fm = fld.add("Min")
        fld.setNumbers(fm, "FieldsList", ids)
        fld.setAsBackgroundMesh(fm)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", P["lc_far"] * 3)
        gmsh.option.setNumber("Mesh.MeshSizeMin", P["lc_min"])
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.mesh.generate(3)

        # ------------------------------------------------------------------ salida
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(tags)
        out = {"node_id": np.asarray(tags, np.int64)[order], "xyz": np.asarray(xyz, float).reshape(-1, 3)[order]}
        names = []
        def grab(key, dts):
            blocks = []
            for (_d, vt) in dts:
                et, _etag, enode = gmsh.model.mesh.getElements(3, vt)
                for t_, en in zip(et, enode):
                    if t_ != 11:
                        continue
                    A = np.asarray(en, np.int64).reshape(-1, 10)
                    A = A[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]          # gmsh -> CalculiX (C3D10)
                    blocks.append(A)
            out["e_" + key] = np.concatenate(blocks) if blocks else np.zeros((0, 10), np.int64)
            names.append(key)
        for p in mdl.parts:
            grab(p.name, vols.get(p.name, []))
        for w, wv in zip(mdl.welds, wvols):
            grab("W:" + w.name, wv)
        out["names"] = np.array(json.dumps(names))
        np.savez_compressed(out_npz, **out)
        return {"nodes": int(len(tags)), "elems": int(sum(len(out["e_" + k]) for k in names))}
    finally:
        gmsh.finalize()


def child(job_json: str, out_npz: str) -> int:
    with open(job_json, encoding="utf-8") as f:
        job = json.load(f)
    info = mesh_job(job, out_npz)
    print(json.dumps(info))
    return 0 if os.path.exists(out_npz) else 3
