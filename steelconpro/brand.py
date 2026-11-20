# -*- coding: utf-8 -*-
"""Identidad visual de SteelConPro: ruta de los recursos graficos y colores de marca."""
from __future__ import annotations
import os
import sys
from pathlib import Path

DARK = "#12171E"          # negro azulado del logo
ORANGE = "#E85D0C"        # naranja del logo
ORANGE_DK = "#C44A06"
GREY = "#F3F4F1"          # fondo claro del logo
SLATE = "#4A5563"         # gris del lema


def asset(name: str) -> str:
    """Ruta de un recurso de steelconpro/data (tambien dentro del ejecutable de PyInstaller)."""
    for base in (Path(__file__).parent / "data", Path(getattr(sys, "_MEIPASS", ".")) / "steelconpro" / "data"):
        p = base / name
        if p.exists():
            return str(p)
    return str(Path(__file__).parent / "data" / name)


LOGO = lambda: asset("logo.png")          # logo horizontal con lema (fondo transparente)
LOGO_DARK = lambda: asset("logo_dark.png")   # el mismo, con el texto claro para el tema oscuro
ICON = lambda: asset("icon.png")          # icono cuadrado 256 px
ICO = lambda: asset("steelconpro.ico")   # icono de Windows (.ico multi-tamano)


def logo_ratio() -> float:
    """Alto / ancho del logo horizontal (para colocarlo en los reportes)."""
    try:
        from PIL import Image
        w, h = Image.open(LOGO()).size
        return h / float(w)
    except Exception:
        return 0.274
