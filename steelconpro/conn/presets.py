# -*- coding: utf-8 -*-
"""Nudo en blanco de cada modulo y miembro nuevo.

El programa no trae plantillas predefinidas: una conexion nueva parte de cero (solo el miembro principal) o de una plantilla del usuario
(ver `templates.py`).  Despues se agregan los miembros, las operaciones y las cargas.
"""
from __future__ import annotations
import copy

from ..shapes import CATALOG
from .specs import Nodo, Member, MODE_COL, MODE_BEAM, MODE_CHORD, END_LABELS, MEMBER_NAMES

MAIN_SHAPES = {MODE_COL: "W14X90", MODE_BEAM: "W24X55", MODE_CHORD: "W14X61"}
MEMBER_SHAPES = {MODE_COL: "W16X31", MODE_BEAM: "W16X31", MODE_CHORD: "HSS4X4X1/4"}
STEEL = "ASTM A992"
HSS_STEEL = "ASTM A500 Gr.C (HSS rect.)"


def _steel(label: str) -> str:
    """Acero por omision de una seccion (A992 para I; A500 Gr.C para HSS, si el catalogo de materiales lo tiene)."""
    from .. import materials as M
    names = [x.name for x in M.SHAPE_STEELS]
    s = CATALOG.get(label)
    want = HSS_STEEL if (s is not None and s.is_hollow) else STEEL
    return want if want in names else (STEEL if STEEL in names else names[0])


def blank_nodo(mode: str) -> Nodo:
    """Nudo sin miembros conectados, sin operaciones y sin cargas: solo el miembro principal (intermedio, continuo a los dos lados)."""
    lab = MAIN_SHAPES[mode]
    return Nodo(mode=mode, main_shape=lab, main_steel=_steel(lab), main_end=END_LABELS[mode][0])


def default_nodo(mode: str) -> Nodo:
    return blank_nodo(mode)


def new_member(nd: Nodo) -> Member:
    """Miembro nuevo para el boton Agregar: copia el ultimo y lo gira para no quedar encima; el primero lleva valores tipicos del modulo."""
    n = len(nd.members) + 1
    pre = "S" if nd.mode == MODE_BEAM else ("D" if nd.mode == MODE_CHORD else "V")
    if nd.members:
        m = copy.deepcopy(nd.members[-1])
        m.name = f"{pre}{n}"
        if nd.mode == MODE_COL:
            m.az = (m.az + 90.0) % 360.0
        else:
            m.az = (m.az + 180.0) % 360.0
        return m
    lab = MEMBER_SHAPES[nd.mode]
    return Member(name=f"{pre}{n}", shape=lab, steel=_steel(lab), az=0.0 if nd.mode != MODE_BEAM else 90.0, el=-45.0 if nd.mode == MODE_CHORD else 0.0, L=60.0 if nd.mode == MODE_CHORD else 48.0)
