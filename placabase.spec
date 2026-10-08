# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec de PlacaBasePro (formato carpeta).
# Uso:  pyinstaller --noconfirm --clean placabase.spec
# build_portable.bat agrega despues la carpeta solvers\ y arma el .zip final.
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import gmsh as _gmsh

datas = []
datas += collect_data_files("docx")          # plantilla base de python-docx
datas += collect_data_files("reportlab")     # fuentes Type1 de reportlab
datas += collect_data_files("matplotlib", subdir="mpl-data")

# libreria de Gmsh: va junto al modulo gmsh para que este la encuentre
if not _gmsh.libpath or not os.path.exists(_gmsh.libpath):
    raise SystemExit("No se encontro la libreria de Gmsh (pip install gmsh).")
binaries = [(_gmsh.libpath, ".")]

hidden = []
hidden += collect_submodules("scipy.sparse")
hidden += ["mpl_toolkits.mplot3d", "scipy.sparse.linalg", "scipy.sparse.csgraph",
           "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg",
           "openpyxl", "docx", "pandas", "reportlab", "reportlab.platypus", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
           "reportlab.lib.styles", "PIL", "gmsh"]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas + [("selftest.py", "."), ("ejemplos", "ejemplos"),
                   ("placabase/data", "placabase/data")],
    hiddenimports=hidden,
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "notebook",
              "pytest", "sphinx"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PlacaBasePro",
    console=False,            # sin ventana de consola
    icon="placabase/data/placabasepro.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PlacaBasePro")
