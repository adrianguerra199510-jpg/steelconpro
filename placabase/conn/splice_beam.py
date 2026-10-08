# -*- coding: utf-8 -*-
"""Empalme de viga con placas de alas y alma atornilladas (ver splice_core.py)."""
from __future__ import annotations

from . import splice_core as C
from .base import run_combos
from .specs import CT_BEAM_SPLICE

NAME = CT_BEAM_SPLICE
ATTR = "bsp"
TAB = "Empalme de viga"
PREFIX = "EV"
TITLE = "EMPALME DE VIGA CON PLACAS ATORNILLADAS"
NORMS = "AISC 360-22 (cap. D, E, J) · AISC Steel Construction Manual 15a Ed., Partes 7, 9 y 14"
LOADS = [("Mu", "M"), ("Vu", "F"), ("Nu", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con el momento Mu y el cortante Vu en la seccion del empalme y la axial Nu "
              "(positiva = traccion; normalmente 0).")
FORM = C.form(ATTR, False)


def check_input(sp):
    return C.check_input(sp, False)


def solve_one(prj, name, vals, rec):
    Mu, Vu, Nu = vals
    return C.checks(prj, prj.bsp, name, Mu, Vu, -Nu, False, rec)


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.bsp, check_input, solve_one, detail)


def label(prj) -> str:
    sp = prj.bsp
    return f"{sp.shape}  (alas {sp.f_rows}×{sp.f_cols} Ø{sp.bolt_size}, alma {sp.w_nv}×{sp.w_nh} Ø{sp.wbolt_size})"


def input_rows(prj, us):
    return C.input_rows(prj, prj.bsp, us, False)


def draw(fig, prj):
    C.draw(fig, prj, prj.bsp, "empalme de viga")
