# -*- coding: utf-8 -*-
"""Une el analisis 3D (FemResult) con el resultado del calculo cerrado de una conexion: firma de vigencia, verificaciones y memoria."""
from __future__ import annotations
import json
from dataclasses import asdict

from . import post


def conn_sig(prj) -> str:
    """Firma de lo que define el modelo 3D de la conexion: la tipologia, sus datos (con las combinaciones) y las opciones del FEM."""
    from .. import module_for
    mod = module_for(prj.ctype)
    d = {"ctype": prj.ctype, "spec": asdict(getattr(prj, mod.ATTR))}
    fea = asdict(prj.fea)
    d["fea"] = {k: fea[k] for k in ("plastic", "plastic_limit", "mesh3d", "mesh3d_mode", "weld_peak_factor") if k in fea}
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def combo_names(prj) -> list:
    from .. import module_for
    return [nm for nm, _ in getattr(prj, module_for(prj.ctype).ATTR).loads()]


def augment(res, prj, fem_map: dict):
    """Agrega a `res` (Results del calculo cerrado) las verificaciones y avisos del analisis 3D de cada combinacion calculada.
    `fem_map` = {indice de combinacion: FemResult}.  Devuelve el mismo `res`."""
    res.fem_map = dict(fem_map or {})
    if not fem_map:
        return res
    names = combo_names(prj)
    multi = len(names) > 1
    for i in sorted(fem_map):
        R = fem_map[i]
        checks = post.fem_checks(R.model, R, prj)
        tag = f" [{names[i]}]" if multi and i < len(names) else ""
        for c in checks:
            if tag:
                c.title += tag
            c.key = f"{c.key}__{i}" if multi else c.key
        res.checks += checks
        for n in R.notes:
            res.warnings.append(f"FEM 3D{tag}: {n}")
        for n in (R.model.notes if R.model is not None else []):
            if n not in res.warnings:
                res.warnings.append(n)
        if R.equil[1] > 0 and R.equil[0] > 0.02 * R.equil[1] + 0.05:
            res.warnings.append(f"FEM 3D{tag}: el equilibrio no cierra (residuo {R.equil[0]:.3g} kip de {R.equil[1]:.3g} kip aplicados).")
    if res.rec is not None:
        try:
            _memo(res.rec, prj, fem_map, names)
        except Exception as e:                                 # pragma: no cover
            res.warnings.append(f"No se pudo agregar el analisis 3D a la memoria: {e}")
    return res


def _memo(rec, prj, fem_map, names):
    rec.section("ANALISIS 3D POR ELEMENTOS FINITOS (Gmsh + CalculiX)")
    rec.text("Modelo solido de tetraedros cuadraticos (C3D10): cada pieza es un cuerpo independiente; los cordones de filete son prismas "
             "unidos a las dos piezas; los pernos son resortes (cortante y traccion) entre cuerpos rigidos que sustituyen el borde de cada agujero; "
             "las piezas que solo se apoyan interactuan por resortes solo-compresion (contacto, conjunto activo). Acero elasto-plastico perfecto con limite "
             "φ·Fy (RBS: acero con endurecimiento y columna con Fy). Se verifican la fuerza de los pernos (AISC J3.6, J3.7), el esfuerzo en la "
             "garganta de los cordones (AISC J2.4: φ·0.60·FEXX) y la deformacion plastica equivalente (limite del proyecto).")
    u = prj.units()
    for i in sorted(fem_map):
        R = fem_map[i]
        nm = names[i] if i < len(names) else f"Comb {i + 1}"
        rec.add(f"Malla — {nm}", f"{R.n_nodes:,} nodos, {R.n_elems:,} elementos", f"tamano de elemento {u.q('L', R.lc)}", None)
        rec.add(f"|U| max — {nm}", "desplazamiento maximo", "", R.umax, "L")
        if R.bolts:
            b = max(R.bolts, key=lambda x: max(x.V, x.T))
            rec.add(f"Perno mas cargado — {nm}", b.tag, f"V = {u.q('F', b.V)}, T = {u.q('F', b.T)}", None)
        rec.add(f"Equilibrio — {nm}", "residuo / carga aplicada", f"{R.equil[0]:.3g} / {R.equil[1]:.3g} kip", None)
