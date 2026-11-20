# -*- coding: utf-8 -*-
"""Carpetas de datos del usuario (materiales, perfiles importados, registro de errores).

El programa se llamaba antes de otra forma: la primera vez que se abre la carpeta nueva se copian a ella, sin borrar nada,
los archivos de la carpeta de las versiones anteriores, para que no se pierdan los materiales ni los perfiles importados."""
from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path

NAME = "SteelConPro"
_LEGACY = "PlacaBasePro"              # nombre de las versiones anteriores (solo se usa para migrar y para abrir archivos viejos)
LEGACY_BOOK_TAGS = (_LEGACY + "-libro",)


def data_dir(env: str = "APPDATA", fallback: str = "") -> Path:
    """Carpeta de datos del programa dentro de `env` (APPDATA / LOCALAPPDATA); se crea si no existe.
    Con `fallback` vacio se usa la carpeta personal del usuario (~/.config)."""
    root = os.environ.get(env) or fallback or os.path.expanduser("~/.config")
    new = Path(root) / NAME
    if not new.exists():
        old = Path(root) / _LEGACY
        new.mkdir(parents=True, exist_ok=True)
        try:
            if old.is_dir():
                for f in old.iterdir():
                    if f.is_file() and not (new / f.name).exists():
                        shutil.copy2(f, new / f.name)
        except OSError:
            pass
    new.mkdir(parents=True, exist_ok=True)
    return new


def temp_dir() -> Path:
    """Carpeta de trabajo del analisis 3D y del registro de errores."""
    return data_dir("LOCALAPPDATA", tempfile.gettempdir())
