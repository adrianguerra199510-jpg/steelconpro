# -*- coding: utf-8 -*-
"""Nudo en blanco y miembro nuevo.

El programa no trae plantillas predefinidas: una conexion nueva parte de cero (solo el miembro principal, que luego se puede designar entre los miembros) o de una plantilla del usuario
(ver `templates.py`).  Despues se agregan los miembros, las operaciones y las cargas.
"""
from __future__ import annotations
import copy

from ..shapes import CATALOG
from .specs import Nodo, Member, END_LABELS, MAIN_NAME

MAIN_SHAPE = "W14X90"
MEMBER_SHAPE = "W16X31"
STEEL = "ASTM A992"
HSS_STEEL = "ASTM A500 Gr.C (HSS rect.)"


def _steel(label: str) -> str:
    """Acero por omision de una seccion (A992 para I; A500 Gr.C para HSS, si el catalogo de materiales lo tiene)."""
    from .. import materials as M
    names = [x.name for x in M.SHAPE_STEELS]
    s = CATALOG.get(label)
    want = HSS_STEEL if (s is not None and s.is_hollow) else STEEL
    return want if want in names else (STEEL if STEEL in names else names[0])


def blank_nodo() -> Nodo:
    """Nudo sin miembros conectados, sin operaciones y sin cargas: solo el miembro principal (vertical, continuo a los dos lados)."""
    return Nodo(main_name=MAIN_NAME, main_shape=MAIN_SHAPE, main_steel=_steel(MAIN_SHAPE), main_end=END_LABELS[0])


def default_nodo() -> Nodo:
    return blank_nodo()


def unique_name(nd: Nodo, base: str) -> str:
    """Nombre que no usa ningun miembro del nudo (principal incluido): `base`, o `base` con un numero."""
    used = set(nd.names())
    if base not in used:
        return base
    k = 2
    while f"{base}{k}" in used:
        k += 1
    return f"{base}{k}"


def new_member(nd: Nodo) -> Member:
    """Miembro nuevo para el boton Agregar: copia el ultimo y lo gira para no quedar encima; el primero es una viga que llega por el lado +X."""
    n = len(nd.members) + 2
    name = unique_name(nd, f"M{n}")
    if nd.members:
        m = copy.deepcopy(nd.members[-1])
        m.name = name
        m.az = (m.az + (90.0 if nd.vertical else 180.0)) % 360.0
        return m
    return Member(name=name, shape=MEMBER_SHAPE, steel=_steel(MEMBER_SHAPE), az=0.0 if nd.vertical else 90.0, el=0.0, L=48.0)
