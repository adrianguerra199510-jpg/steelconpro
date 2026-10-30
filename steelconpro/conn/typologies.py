# -*- coding: utf-8 -*-
"""Tipologías de nudo: plantillas que arman el nudo completo (miembros, operaciones y cargas) a partir de unos pocos datos.

    base   Plato base: columna que nace en la placa base, con las diagonales que llegan cerca de la base (cada una con su cartela).
    col    Nodo de columna intermedia o superior: la columna continúa (o termina) en el nudo y llegan las diagonales.
    vigas  Nodo de vigas: dos miembros que se cruzan en el nudo (una X), uno de ellos es el principal.

Todo queda editable después (miembros, operaciones, cargas); las tipologías solo ahorran armar el nudo a mano.
"""
from __future__ import annotations
import math

from .specs import Nodo, Member, Operation, Load, END_LABELS, OP_GUSSET, OP_BASE, OP_CONT
from .presets import MAIN_NAME

TYPES = [("base", "Plato base"), ("col", "Nodo de columna intermedia o superior"), ("vigas", "Nodo de vigas")]
HSS_STEEL = "ASTM A500 Gr.C (HSS rect.)"
I_STEEL = "ASTM A992"


def schema(kind: str) -> list:
    """Campos del formulario de cada tipología: [{key, label, type, default, items?, length?}]."""
    brace = {"key": "brace_shape", "label": "Perfil de las diagonales", "type": "shape", "default": "HSS5X5X3/8"}
    ang = {"key": "angle", "label": "Ángulo de las diagonales sobre la horizontal (°)", "type": "num", "default": 45.0, "lo": 10, "hi": 80}
    if kind == "base":
        return [{"key": "col_shape", "label": "Perfil de la columna", "type": "shape", "default": "W14X90"}, brace, ang,
                {"key": "n_braces", "label": "Número de diagonales", "type": "int", "default": 2, "lo": 0, "hi": 4},
                {"key": "h", "label": "Altura donde llegan las diagonales sobre la placa base", "type": "num", "default": 20.0, "length": True, "lo": 8, "hi": 120}]
    if kind == "col":
        return [{"key": "col_shape", "label": "Perfil de la columna", "type": "shape", "default": "W14X90"}, brace, ang,
                {"key": "top", "label": "Nudo superior (la columna termina en el nudo)", "type": "bool", "default": False},
                {"key": "n_braces", "label": "Número de diagonales", "type": "int", "default": 4, "lo": 1, "hi": 4}]
    return [{"key": "main_shape", "label": "Perfil del miembro principal (pasa por el nudo)", "type": "shape", "default": "W16X31"},
            {"key": "brace_shape", "label": "Perfil de los otros miembros", "type": "shape", "default": "W16X31"}, ang,
            {"key": "n_members", "label": "Miembros que llegan al principal", "type": "int", "default": 2, "lo": 1, "hi": 2}]


def _vals(kind, params):
    out = {f["key"]: f["default"] for f in schema(kind)}
    for k, v in (params or {}).items():
        if k in out and v not in (None, ""):
            out[k] = type(out[k])(v) if not isinstance(out[k], bool) else bool(v)
    return out


def _steel(label):
    from ..shapes import CATALOG
    s = CATALOG.get(label)
    return HSS_STEEL if (s is not None and s.is_hollow) else I_STEEL


def _member(name, shape, az, el, pos, L=60.0, gap=0.0) -> Member:
    return Member(name=name, shape=shape, steel=_steel(shape), az=az, el=el, pos=pos, L=L, gap=gap)


def build_nodo(kind: str, params: dict | None = None) -> Nodo:
    v = _vals(kind, params)
    if kind == "base":
        nd = Nodo(main_name="Columna", main_shape=v["col_shape"], main_steel=_steel(v["col_shape"]), main_end=END_LABELS[2], main_len_neg=0.0, main_len_pos=max(v["h"] * 3.5, 72.0))
        azs = [0.0, 180.0, 90.0, 270.0]
        for k in range(int(v["n_braces"])):
            nd.members.append(_member(f"D{k + 1}", v["brace_shape"], azs[k], v["angle"], v["h"], L=72.0))
            nd.operations.append(Operation(kind=OP_GUSSET, member=f"D{k + 1}", plate_t=0.5))
        nd.operations.append(Operation(kind=OP_BASE, member=nd.main_name, end=-1))
        nd.loads = [Load("Caso 1", nd.main_name, N=-40.0, side=1)]
        for k, m in enumerate(nd.members):
            nd.loads.append(Load("Caso 1", m.name, N=-10.0 if k % 2 == 0 else 10.0))
        return nd
    if kind == "col":
        top = bool(v["top"])
        nd = Nodo(main_name="Columna", main_shape=v["col_shape"], main_steel=_steel(v["col_shape"]), main_end=END_LABELS[1] if top else END_LABELS[0], main_len_neg=72.0, main_len_pos=0.0 if top else 72.0)
        # dos diagonales hacia abajo (una a cada lado) y, si la columna continúa, dos hacia arriba
        plan = [(0.0, -v["angle"]), (180.0, -v["angle"]), (0.0, v["angle"]), (180.0, v["angle"])]
        plan = [p for p in plan if not (top and p[1] > 0)]
        for k, (az, el) in enumerate(plan[:int(v["n_braces"])]):
            nd.members.append(_member(f"D{k + 1}", v["brace_shape"], az, el, 0.0, L=72.0))
            nd.operations.append(Operation(kind=OP_GUSSET, member=f"D{k + 1}", plate_t=0.5))
        nd.balance_end = 1 if top else -1                          # la acción de la columna sobre el nudo sale del equilibrio: no se le asignan cargas
        nd.loads = []
        for k, m in enumerate(nd.members):
            nd.loads.append(Load("Caso 1", m.name, N=-10.0 if k % 2 == 0 else 10.0))
        return nd
    nd = Nodo(main_name="Viga principal", main_shape=v["main_shape"], main_steel=_steel(v["main_shape"]), main_az=0.0, main_el=float(v["angle"]), main_end=END_LABELS[0], main_len_neg=60.0, main_len_pos=60.0)
    plan = [(0.0, -v["angle"]), (180.0, v["angle"])]
    for k, (az, el) in enumerate(plan[:int(v["n_members"])]):
        nd.members.append(_member(f"M{k + 1}", v["brace_shape"], az, el, 0.0, L=60.0))
        nd.operations.append(Operation(kind=OP_GUSSET, member=f"M{k + 1}", plate_t=0.5))
    nd.loads = []                                                    # el principal pasa por el nudo: su acción sale del equilibrio
    for k, m in enumerate(nd.members):
        nd.loads.append(Load("Caso 1", m.name, N=-10.0 if k % 2 == 0 else 10.0))
    return nd
