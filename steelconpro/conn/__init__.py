# -*- coding: utf-8 -*-
"""Modulos de conexion distintos de la placa base: nudo viga-columna, viga a viga y crucetas.

Cada modulo es una instancia de `nodes.NodeModule` (identidad, esquema y texto de la lista) sobre un `specs.Nodo`; el modelo 3D lo arma
`assembly.build_model`.  Por ahora son solo geometria y vista 3D (sin calculo): ver LEEME.
Se importan al usarse, para que `model.py` pueda importar `conn.specs` sin arrastrar el resto (importacion circular).
"""
from __future__ import annotations

from .specs import CT_NODE, CT_B2B, CT_TRUSS

_ORDER = (CT_NODE, CT_B2B, CT_TRUSS)


def module_for(ctype: str):
    from . import nodes
    mod = nodes.MODULES.get(ctype)
    if mod is None:
        raise KeyError(f"Modulo de conexion no implementado: {ctype}")
    return mod


def modules() -> list:
    """[(ctype, modulo)] de los modulos distintos de la placa base."""
    return [(ct, module_for(ct)) for ct in _ORDER]


def solve_conn(prj, detail: bool = True):
    return module_for(prj.ctype).solve(prj, detail)


def save_figures(prj, res, folder: str) -> list:
    """Imagenes del modelo 3D (isometrica y dos vistas) y del esquema de planta y elevacion de un modulo de nudo."""
    from pathlib import Path
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    from .assembly import build_model
    from .fem import scene as S
    mdl = build_model(prj)
    sc = S.scene_model(mdl, loads=False, tags=True)
    out = []
    for nm, (el, az) in (("modelo3d_iso.png", (24.0, 50.0)), ("modelo3d_planta.png", (89.0, 0.0)), ("modelo3d_frente.png", (0.0, -90.0))):
        p = str(f / nm)
        S.render_scene_png(sc, p, el, az, size=(1100, 800), title=f"{prj.element} — {mdl.name}")
        out.append(p)
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    fig = Figure(figsize=(8.0, 9.5), dpi=150)
    module_for(prj.ctype).draw(fig, prj)
    p = str(f / "esquema.png")
    fig.savefig(p)
    out.append(p)
    return out
