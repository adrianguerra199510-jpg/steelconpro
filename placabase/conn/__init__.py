# -*- coding: utf-8 -*-
"""Tipologias de conexion distintas de la placa base.

Cada tipologia es un modulo con este contrato (ver `shear_tab.py`, que sirve de plantilla):
    NAME, ATTR, TAB, PREFIX, TITLE, NORMS     identidad (NAME = entrada de specs.CONN_TYPES, ATTR = campo de Project)
    LOADS, LOADS_NOTE                         columnas de la tabla de cargas: [(encabezado, magnitud 'F'|'M')]
    FORM                                      formulario declarativo (formspec.py)
    solve(prj, detail) -> solver.Results      calculo (todas las combinaciones; devuelve la que gobierna)
    draw(fig, prj)                            dibujo con cotas en una figura de matplotlib
    input_rows(prj, us), label(prj)           datos de entrada para los reportes y texto de la lista
Se importan al usarse, para que `model.py` pueda importar `conn.specs` sin arrastrar el resto (importacion circular).
"""
from __future__ import annotations
import importlib

from .specs import CT_SHEAR_TAB, CT_DOUBLE_ANGLE, CT_SEATED, CT_BEAM_SPLICE, CT_COL_SPLICE

_MODULES = {CT_SHEAR_TAB: "shear_tab", CT_DOUBLE_ANGLE: "double_angle", CT_SEATED: "seated",
            CT_BEAM_SPLICE: "splice_beam", CT_COL_SPLICE: "splice_col"}


def module_for(ctype: str):
    name = _MODULES.get(ctype)
    if name is None:
        raise KeyError(f"Tipologia de conexion no implementada: {ctype}")
    return importlib.import_module(f"{__name__}.{name}")


def modules() -> list:
    """[(ctype, modulo)] de todas las tipologias distintas de la placa base."""
    return [(ct, module_for(ct)) for ct in _MODULES]


def solve_conn(prj, detail: bool = True):
    return module_for(prj.ctype).solve(prj, detail)


def save_figures(prj, res, folder: str) -> list:
    """Dibujo de la conexion en PNG (para los reportes)."""
    from pathlib import Path
    from .base import new_figure
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    fig = new_figure(8.0, 9.5)
    module_for(prj.ctype).draw(fig, prj)
    out = f / "conexion.png"
    fig.savefig(out)
    return [str(out)]
