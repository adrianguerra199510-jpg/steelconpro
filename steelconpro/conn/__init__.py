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

from .specs import CT_SHEAR_TAB, CT_DOUBLE_ANGLE, CT_SEATED, CT_BEAM_SPLICE, CT_COL_SPLICE, CT_ENDPLATE, CT_GUSSET, CT_HSS, CT_RBS, CT_BRIDGE

_MODULES = {CT_SHEAR_TAB: "shear_tab", CT_DOUBLE_ANGLE: "double_angle", CT_SEATED: "seated",
            CT_BEAM_SPLICE: "splice_beam", CT_COL_SPLICE: "splice_col", CT_ENDPLATE: "endplate", CT_GUSSET: "gusset", CT_HSS: "hss_joint", CT_RBS: "rbs", CT_BRIDGE: "bridge_splice"}


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
    files = [str(out)]
    files += _fem_figures(prj, res, f)
    return files


def _fem_figures(prj, res, folder) -> list:
    """Imagenes del analisis 3D (von Mises, deformada y deformacion plastica) de la combinacion con mayor D/C del FEM."""
    fm = getattr(res, "fem_map", None) or {}
    if not fm:
        return []
    try:
        from .fem import scene as S, post
        k = max(fm, key=lambda i: max((c.ratio for c in post.fem_checks(fm[i].model, fm[i], prj) if not c.skip), default=0.0))
        R = fm[k]
        xs = np_ptp(R)
        sc = 0.0 if R.umax <= 0 else max(1.0, float(f"{min(0.06 * xs / R.umax, 3000.0):.1g}"))
        out = []
        for fld, nm, scale in (("vm", "fem_vonmises.png", 0.0), ("u", "fem_deformada.png", sc)) + ((("peeq", "fem_peeq.png", 0.0),) if R.plastic else ()):
            scn = S.scene_fem(R, prj, fld, scale, "all", loads=False, bolts=(scale == 0.0))
            p = str(folder / nm)
            S.render_scene_png(scn, p, 24.0, 50.0, size=(1000, 760), title=scn.title)
            out.append(p)
        return out
    except Exception:
        import traceback
        traceback.print_exc()
        return []


def np_ptp(R) -> float:
    import numpy as np
    P = np.array(list(R.nodes.values()))
    return float(np.ptp(P, axis=0).max()) if len(P) else 1.0
