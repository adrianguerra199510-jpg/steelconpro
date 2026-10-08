# -*- coding: utf-8 -*-
"""Descripcion declarativa de los formularios de las tipologias de conexion.

Cada tipologia define `FORM = [ G("Grupo"), num(...), combo(...), ... ]`; `ui.py` construye la pestaña con
`ui_widgets.Form` a partir de esa lista (sin importar PySide6 aqui, asi el motor sigue siendo independiente de Qt).

`show=lambda prj: bool` oculta el campo o el grupo cuando no aplica (se evalua al editar).
En `items`, una cadena que empieza con '@' se resuelve en la UI contra un catalogo:
    @I  perfiles I (W, M, S, HP)      @W  solo W         @L  angulos (L)
    @HSSR  HSS rectangular/cuadrado   @HSSC  HSS circular   @T  tes (WT, MT, ST)
    @steel_shape  aceros de perfil    @steel_plate  aceros de placa     @electrode  electrodos
"""
from __future__ import annotations


def G(title, show=None):
    """Grupo (caja) del formulario."""
    return {"t": "group", "title": title, "show": show}


def N(text):
    """Nota al pie de un grupo."""
    return {"t": "note", "text": text}


def num(label, path, lo=0.0, hi=1e6, uk=None, help="", show=None, step=0.125, dec=3, suffix=""):
    """Campo numerico. uk = magnitud ('L','F','M','S','A','K'): se muestra en las unidades del usuario."""
    return {"t": "num", "label": label, "path": path, "lo": lo, "hi": hi, "uk": uk, "help": help, "show": show,
            "step": step, "dec": dec, "suffix": suffix}


def intf(label, path, lo=0, hi=999, help="", show=None):
    return {"t": "int", "label": label, "path": path, "lo": lo, "hi": hi, "help": help, "show": show}


def combo(label, path, items, editable=False, help="", show=None):
    return {"t": "combo", "label": label, "path": path, "items": items, "editable": editable, "help": help,
            "show": show}


def check(label, path, help="", show=None):
    return {"t": "check", "label": label, "path": path, "help": help, "show": show}
