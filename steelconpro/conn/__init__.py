# -*- coding: utf-8 -*-
"""Modulo de conexion de nudo (todo lo que no es placa base): un nudo generico con el miembro principal que designa el usuario.

El modulo es una instancia de `nodes.NodeModule` (identidad, esquema y texto de la lista) sobre un `specs.Nodo`; el modelo 3D lo arma
`assembly.build_model`.  Se arman por operaciones (miembros, operaciones, cargas) y se verifican por codigo (conn/checks); el analisis 3D por elementos finitos es la etapa siguiente.
Se importan al usarse, para que `model.py` pueda importar `conn.specs` sin arrastrar el resto (importacion circular).
"""
from __future__ import annotations

from .specs import CT_NODE

_ORDER = (CT_NODE,)


def module_for(ctype: str):
    from . import nodes
    mod = nodes.MODULES.get(ctype)
    if mod is None:
        raise KeyError(f"Modulo de conexion no implementado: {ctype}")
    return mod


def modules() -> list:
    """[(ctype, modulo)] de los modulos distintos de la placa base."""
    return [(ct, module_for(ct)) for ct in _ORDER]


def solve_conn(prj, detail: bool = True, fem_map=None):
    return module_for(prj.ctype).solve(prj, detail, fem_map)


def save_figures(prj, res, folder: str) -> list:
    """Imagenes del modelo 3D (isometrica y dos vistas) y del esquema de planta y elevacion de un modulo de nudo.  El 3D se dibuja con el visor clasico
    de matplotlib, el mismo con que la placa base arma las imagenes de su memoria."""
    from pathlib import Path
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    from matplotlib.figure import Figure
    from .assembly import build_model
    from .. import view3d
    mdl = build_model(prj)
    kl = prj.units().fl
    out = []
    for nm, (el, az) in (("modelo3d_iso.png", (24.0, -58.0)), ("modelo3d_planta.png", (90.0, -90.0)), ("modelo3d_frente.png", (0.0, -90.0))):
        fig = Figure(figsize=(7.0, 5.6), dpi=150)
        ax = fig.add_axes([0.0, 0.0, 1.0, 0.95], projection="3d")
        view3d.plot_model(ax, mdl, scale=1.0 / kl, tags=True)
        ax.view_init(elev=el, azim=az)
        view3d.fit_to_axes(ax)
        fig.suptitle(mdl.name, fontsize=9, x=0.02, ha="left", y=0.99)
        p = str(f / nm)
        fig.savefig(p)
        out.append(p)
    fig = Figure(figsize=(8.0, 9.5), dpi=150)
    module_for(prj.ctype).draw(fig, prj)
    p = str(f / "esquema.png")
    fig.savefig(p)
    out.append(p)
    return out
