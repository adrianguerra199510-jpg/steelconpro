# -*- coding: utf-8 -*-
"""Empalme de columna con placas atornilladas, con o sin contacto (ver splice_core.py)."""
from __future__ import annotations

from . import splice_core as C
from .base import run_combos
from .specs import CT_COL_SPLICE

NAME = CT_COL_SPLICE
ATTR = "csp"
TAB = "Empalme de columna"
PREFIX = "EC"
TITLE = "EMPALME DE COLUMNA CON PLACAS ATORNILLADAS"
NORMS = "AISC 360-22 (cap. D, E, J, J1.4) · AISC Steel Construction Manual 15a Ed., Partes 7, 9 y 14"
LOADS = [("Pu", "F"), ("Mu", "M"), ("Vu", "F")]
LOADS_NOTE = ("Cada fila es una combinacion con la axial Pu (positiva = compresion; negativa = traccion), el momento Mu y el "
              "cortante Vu en la seccion del empalme.")
FORM = C.form(ATTR, True)


def check_input(sp):
    return C.check_input(sp, True)


def solve_one(prj, name, vals, rec):
    Pu, Mu, Vu = vals
    return C.checks(prj, prj.csp, name, Mu, Vu, Pu, prj.csp.contact, rec)


def solve(prj, detail: bool = True):
    return run_combos(prj, prj.csp, check_input, solve_one, detail)


def label(prj) -> str:
    sp = prj.csp
    return f"{sp.shape}  ({'con' if sp.contact else 'sin'} contacto; alas {sp.f_rows}×{sp.f_cols} Ø{sp.bolt_size})"


def input_rows(prj, us):
    return C.input_rows(prj, prj.csp, us, True)


def draw(fig, prj):
    C.draw(fig, prj, prj.csp, "empalme de columna")
