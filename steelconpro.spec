# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec del MOTOR de SteelConPro (formato carpeta, sin ventana): lo lanza la aplicacion Electron como proceso local.
# Uso:  pyinstaller --noconfirm --clean steelconpro.spec      ->  dist/engine/SteelConPro-engine(.exe)
# build_portable.bat arma despues la aplicacion Electron (electron-builder) con esta carpeta.
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
hidden += collect_submodules("steelconpro")          # modulos cargados con importlib (conn/__init__.py) y funciones de api.py
hidden += ["tools", "tools.node_presets", "mpl_toolkits.mplot3d", "scipy.sparse.linalg", "scipy.sparse.csgraph",
           "matplotlib.backends.backend_agg", "openpyxl", "docx", "pandas", "reportlab", "reportlab.platypus",
           "reportlab.lib.styles", "PIL", "gmsh"]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas + [("selftest.py", "."), ("selftest_nodes.py", "."), ("selftest_ops.py", "."), ("ejemplos", "ejemplos"),
                   ("steelconpro/data", "steelconpro/data")],
    hiddenimports=hidden,
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "shiboken6", "IPython", "notebook", "pytest", "sphinx"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SteelConPro-engine",
    console=True,             # el motor no tiene ventana: Electron lo lanza oculto y lee su salida
    icon="steelconpro/data/steelconpro.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="engine")
