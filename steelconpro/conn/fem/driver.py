# -*- coding: utf-8 -*-
"""Orquesta el analisis 3D de una conexion: modelo -> malla (Gmsh, proceso hijo) -> CalculiX -> resultados -> verificaciones."""
from __future__ import annotations
import json
import time
from pathlib import Path

import numpy as np

from ... import mesh3d
from .builders import build_model
from .model3d import model_to_dict
from . import ccxgen, solve, post


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def mesh_params(mdl, fea, f: float = 1.0) -> dict:
    """Tamanos de elemento (in): finos en las placas y alrededor de los agujeros, mas gruesos en la viga/columna fuera de la zona.
    `f` = factor de reintento (malla mas gruesa)."""
    fine = str(getattr(fea, "mesh3d_mode", "")).startswith("Fina")
    k = (1.1 if fine else 1.7) * f
    manual = float(getattr(fea, "mesh3d", 0.0) or 0.0)
    part_lc, part_far = {}, {}
    for p in mdl.parts:
        t = p.thickness
        if p.stub:
            lc = _clip(2.4 * t, 0.55, 1.1) * k
            lc = (manual * 1.6 if manual > 0 else lc)
            lc = min(lc, 3.0 * t)                       # elementos de mas de ~3 espesores dan errores de malla en paredes delgadas
            part_far[p.name] = min(_clip(3.4 * lc, 1.8, 3.4) * (f if f > 1 else 1.0), max(1.8, 8.0 * t))
        else:
            lc = _clip(0.9 * t, 0.25, 0.75) * k
            lc = manual if manual > 0 else lc
            lc = min(lc, 2.2 * t + 0.15)
        part_lc[p.name] = lc
    lc_near = min(part_lc.values()) if part_lc else 0.6
    wmin = min((w.w for w in mdl.welds), default=0.25)
    return {"lc_near": lc_near, "lc_far": 3.0, "lc_weld": _clip(0.55 * wmin, 0.1, 0.25) * max(1.0, f), "lc_hole": _clip(0.3 * (min((b.dh for b in mdl.bolts), default=1.0)), 0.18, 0.4) * k,
            "lc_min": 0.08, "transition": 3.0 * max(1.0, f), "part_lc": part_lc, "part_far": part_far}


def _mesh(mdl, params, folder: Path, stem: str, cancel):
    job = folder / f"{stem}_job.json"
    npz = folder / f"{stem}_malla.npz"
    if npz.exists():
        npz.unlink()
    job.write_text(json.dumps({"model": model_to_dict(mdl), "params": params}), encoding="utf-8")
    rc, out, state = mesh3d._run_proc(mesh3d._self_cmd() + ["--meshm", str(job), str(npz)], cancel, 1800)
    if state == "cancelado":
        return None, mesh3d.CANCELADO
    if state == "tiempo":
        return None, "Gmsh excedio el tiempo limite."
    if not npz.exists():
        return None, "Gmsh no genero la malla.\n\n" + out[-2500:]
    return npz, out


def run_fem(prj, vals, folder: str, stem: str = "modelo3d", progress=None, cancel=None):
    """Corre el analisis 3D de la combinacion `vals`.  Devuelve (FemResult | None, mensaje)."""
    say = progress or (lambda m: None)
    fea = prj.fea
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    last = "No se pudo completar el analisis."
    for f in (1.0, 1.35, 1.8):
        if cancel is not None and cancel.cancelled:
            return None, mesh3d.CANCELADO
        tag = "" if f == 1.0 else f"  (reintento con malla mas gruesa x{f:g})"
        try:
            say(f"1/4  Armando el modelo 3D ...{tag}")
            mdl = build_model(prj, vals)
            params = mesh_params(mdl, fea, f)
            say(f"2/4  Mallando con Gmsh ...{tag}")
            npz, out = _mesh(mdl, params, folder, stem, cancel)
            if npz is None:
                if out == mesh3d.CANCELADO:
                    return None, out
                last = out
                continue
            say(f"3/4  Armando el modelo de CalculiX ...{tag}")
            mesh = ccxgen.Mesh(str(npz))
            case = ccxgen.CcxCase(mdl, mesh, {"plastic": bool(getattr(fea, "plastic", True)), "contacts": True})
            say(f"4/4  Resolviendo con CalculiX ...{tag}")
            ok, msg, info = solve.solve_case(case, str(folder), stem, getattr(fea, "ccx_path", ""), cancel, say)
            if not ok:
                if msg == mesh3d.CANCELADO:
                    return None, msg
                last = msg
                continue
            say("Leyendo resultados ...")
            R = post.postprocess(mdl, case, info, info["frd"], lc=min(params["part_lc"].values()), plastic=bool(getattr(fea, "plastic", True)) and "plastic_failed" not in info
                                 and info.get("frd") != info.get("frd_elastic"), folder=str(folder))
            if not R.ok:
                last = R.msg
                continue
            R.notes = ([msg] if msg else []) + ([] if info.get("converged", True) else ["Los contactos no llegaron a un conjunto estable (se muestra la ultima iteracion)."])
            return R, R.msg + ("   " + msg if msg else "")
        except Exception as e:                                  # malla o modelo imposibles: se prueba con una malla mas gruesa
            last = f"{type(e).__name__}: {e}"
    return None, last + "\n\n(Se probaron tres tamanos de malla; revise la geometria o aumente el tamano manual.)"


def export_step(prj, vals, path: str):
    """Escribe la geometria solida de la conexion (piezas y cordones; sin los agujeros de los pernos) en un archivo STEP (proceso hijo de Gmsh)."""
    import tempfile
    mdl = build_model(prj, vals)
    job = Path(tempfile.mkdtemp(prefix="scp_")) / "job.json"
    job.write_text(json.dumps({"model": model_to_dict(mdl), "params": {}, "step": str(path)}), encoding="utf-8")
    rc, out, state = mesh3d._run_proc(mesh3d._self_cmd() + ["--meshm", str(job), str(Path(path).with_suffix(".npz"))], None, 600)
    if not Path(path).exists():
        raise RuntimeError("No se pudo escribir el STEP.\n" + out[-1500:])
    try:
        Path(path).with_suffix(".npz").unlink()
    except OSError:
        pass
    return path
