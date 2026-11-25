# SteelConPro

Software de **diseño y verificación de conexiones de acero** (AISC 360-22, AISC Design Guide 1,
ACI 318-19 cap. 17). Escritorio Windows, Python + PySide6, FEM sólido con Gmsh + CalculiX.

**Nombre del proyecto: SteelConPro.** Nunca lo llames "PlacaBasePro" ni "la rama de PlacaBasePro":
PlacaBasePro 3.2.11 es solo el código base del que se partió (commit inicial) y hoy es el primer
módulo de SteelConPro (placas base). Si ves ese nombre en un historial o comentario, es herencia.

## Estado
- Módulo existente: placas base (anclajes ACI 318, llave de corte, rigidizadores, soldadura, FEM 3D).
- Pendiente: conexiones viga-columna (placa simple, ángulos, placa de extremo, momento, empalmes, riostras).
  Referencia de alcance: CivilEngrTools/SteelConnDesign (software cerrado: no hay código que reutilizar;
  sirve solo como alcance y para validar contra ejemplos del AISC Design Examples v15: II.A-17B, II.A-1B, II.B-1).
- machinery-lab (LinkLab/CamLab) no es relevante para el cálculo; es GPL-3.0, no copiar código.

## Estructura
- `run.py` punto de entrada (GUI, `--selftest`, modo por lotes). `selftest.py` autopruebas del motor.
- `placabase/` paquete interno (el nombre del directorio se conserva por compatibilidad; no renombrar
  sin actualizar `placabase.spec`, workflow y `selftest.py`).
  - Motor: `design.py` (verificaciones), `anchors.py`, `solver.py`, `model.py` (proyecto y libro `.pbase`),
    `materials.py`, `shapes.py` (+ `data/aisc_shapes.json`), `units.py`.
  - FEM: `mesh3d.py`, `weldfe.py`, `fem_checks.py`. Memoria: `explain.py`, `report.py`.
  - UI: `ui.py`, `gl3d.py`, `view3d.py`, `draw.py`, `brand.py`.
- Unidades internas siempre in-kip-ksi; la conversión ocurre solo en entrada/salida.
- Formato de archivo: `.pbase`, `"formato": "SteelConPro-libro"` (se sigue leyendo `PlacaBasePro-libro`).
- Datos de usuario: `%APPDATA%\SteelConPro` (se migra una vez desde `PlacaBasePro` si existe).

## Convenciones
- Idioma de la interfaz, comentarios y docs: español.
- Cada verificación es un `Check` (demanda/capacidad/referencia a la norma) registrado con `Recorder` para la memoria de cálculo.
- `ccx.exe` es solo Windows: el FEM no corre en Linux. `python selftest.py` (necesita numpy, scipy, matplotlib, PySide6, gmsh).

## Ramas
- `main` es la rama de referencia. El trabajo de sesiones de Claude va en ramas `claude/*`.
