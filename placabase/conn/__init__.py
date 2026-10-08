# -*- coding: utf-8 -*-
"""Tipologias de conexion distintas de la placa base.

Cada tipologia es un modulo con `NAME` (el mismo texto que en `specs.CONN_TYPES`) y
`solve(prj, detail) -> solver.Results`.  Se importan al usarse, para que `model.py` pueda importar
`conn.specs` sin arrastrar el resto (importacion circular).
"""
from __future__ import annotations
import importlib

from .specs import CT_SHEAR_TAB

_MODULES = {CT_SHEAR_TAB: "shear_tab"}


def module_for(ctype: str):
    name = _MODULES.get(ctype)
    if name is None:
        raise KeyError(f"Tipologia de conexion no implementada: {ctype}")
    return importlib.import_module(f"{__name__}.{name}")


def solve_conn(prj, detail: bool = True):
    return module_for(prj.ctype).solve(prj, detail)
