# SteelConPro 1.1 — guía para Claude

**SteelConPro NO es PlacaBase Pro.** Es una herramienta de diseño de **conexiones de acero genéricas** (estilo IDEA StatiCa / RAM Connection): un nudo con un miembro principal,
cualquier número de miembros conectados y una lista de **operaciones** (placas, pernos, soldaduras, recortes, ángulos, placa base…). La placa base es solo UNA operación más.
Idioma del código, mensajes, documentación y conversación con el usuario: **español**.

**Nombre:** nunca lo llame «PlacaBasePro» ni «la rama de PlacaBasePro»: PlacaBasePro 3.2.11 es solo el código base del que se partió (commit inicial); si ve ese nombre en un historial o comentario, es herencia. Los archivos `.pbase` y los datos de `PlacaBasePro` solo se leen/migran por compatibilidad.
Referencia de alcance: SteelConnDesign (CivilEngrTools; software cerrado, no hay código que reutilizar; sirve para alcance y para validar contra ejemplos del AISC Design Examples v15: II.A-17B, II.A-1B, II.B-1). `machinery-lab` no es relevante y es GPL-3.0: no copiar código.

## Por qué parece PlacaBase Pro
El repositorio nació de PlacaBase Pro 3.2.11 (primer commit). Los módulos de la **raíz** del paquete son ese núcleo heredado y se siguen usando solo para la operación *Placa base*
y para abrir archivos viejos (`.pbase`): `model.py` (`Project` con plate/bolts/stiff/lug/conc), `design.py`, `anchors.py`, `geometry.py`, `view3d.py`, `mesh3d.py`, `weldfe.py`, `weld3d.py`,
`params3d.py`, `solver.py`, `rep3d.py`, `fem_checks.py`. **Todo lo nuevo vive en `steelconpro/conn/`**; empiece por ahí y no asuma que el programa es de placa base.

## Mapa del motor (`steelconpro/`)
- `api.py` — funciones JSON que expone el motor a la interfaz (`server.py` las sirve; `run.py --serve`).
- `mcp_server.py` + `chat.py` — servidor MCP para Claude Desktop (`run.py --mcp`; `--mcp-install`, `--mcp-check`): crear, analizar y consultar conexiones por chat sobre la misma API; botón «Conectar con Claude Desktop» en el inicio (copia el motor a `%LOCALAPPDATA%\SteelConPro\claude-engine`).
- `conn/specs.py` — datos: `Nodo` (principal + `members` + `operations` + `loads`), `Member` (incluye `attach_to`: llega a otro miembro), `Operation` (todas las operaciones comparten esta clase), constantes.
- `conn/assembly.py` — `build_nodo`/`build_model`: arma el modelo 3D (`Model3D`: piezas de prismas, pernos, soldaduras) a partir del `Nodo`. `conn/ops.py` y `conn/plates.py`: operaciones generales (placas, pernos, soldaduras, recortes, huecos).
- `conn/nodal.py` — análisis nodal (equilibrio, articulaciones/rotaciones liberadas); `conn/checks/` — verificaciones AISC 360-22/DG1/ACI 318; `conn/baseplate.py` — puente a la placa base heredada.
- `conn/geocheck.py` (revisor de geometría), `conn/meshcheck.py` (mallas cerradas), `conn/fem/` — prismas y mallas (`prismmesh.py`), modelo de placas/cascarones (`shellmesh.py`), CalculiX (`ccxgen.py`, `solve.py`).
- `seismic.py` — diseño sísmico (ASCE 7-05 / AISC 341-22 / ACI 318-19 17.10: generador de casos E y Ωo por miembro, placa base sísmica; ventana «Diseño sísmico»; ejemplo `SIS-01`); sus planes y diseños están en `docs/superpowers/`.
- Interfaz: `electron/renderer/js/` (ES modules + three.js, sin framework); pruebas de interfaz en `electron/tests/` (Playwright + Electron con `xvfb-run`).
- Ejemplos: `ejemplos/CN-*`, `TP-V*`, `TP-A*`, `TP-G*` (`.scp`), generados por `tools/ejemplos_*.py`; cada uno debe pasar el revisor de geometría con 0 errores.

## Decisiones de diseño vigentes (no las deshaga sin preguntar)
- El **largo de los miembros es automático** (`Nodo.auto_len()`, mín. 60 in): no se edita ni en la ficha ni en el FEM; lo dibujado es lo que se malla.
- El **FEM es un modelo de placas** (cascarones sobre la superficie media, `shellmesh.py`, Gmsh en proceso hijo `run.py --meshs`, 1 hilo). Con placa base (o placa sobre un bloque de concreto), el concreto NO se malla (resortes solo-compresión y anclajes a punto fijo). **«Calcular» verifica y analiza** el modelo de placas con CalculiX (`conn/fem/shellccx.py`, `shellpost.py`, `shellchecks.py`) y el visor muestra esfuerzos y deformada; el FEM sólido antiguo (`ccxgen.py`, `driver.py`) ya no se usa.
- **Resultados**: el resumen por componentes (Miembros, Placas, Pernos, Soldaduras, Anclajes y concreto) es la vista estándar; los miembros se revisan por los esfuerzos locales que produce la conexión (no pandeo global); las fuerzas a mano de las operaciones generales se mantienen.
- Las conexiones de catálogo (placa simple, doble ángulo, asiento, placa extrema, alas soldadas, cartelas) solo se arman contra el **principal**; un miembro que llega a otro miembro (`attach_to`) se une con operaciones generales. El recorte tubo redondo contra tubo redondo es en **boca de pez** (`Prism.cut_cyls`).
- Cálculo interno siempre en in-kip-ksi; las unidades se convierten solo en la entrada y la salida.

## Ramas
- `main` es la rama de referencia y se actualiza por **PR**. La rama de trabajo de la última sesión de desarrollo es `claude/great-cori-lw9wqj` (contiene todo: motor, interfaz, módulo sísmico). Las demás `claude/*` son sesiones anteriores o paralelas; antes de dar algo por «lo último», compare ramas con `git fetch --all` y `git log --oneline main..<rama>`.
- Antes de empezar, revise si otra rama tiene trabajo que esta no tiene (en una ocasión el módulo sísmico quedó en `claude/kind-meitner-ou1rzg` y no entraba en el exe).

## Cómo trabajar
- Desarrolle en la rama que indique la sesión; `git push -u origin <rama>`; **no abra PR** salvo que el usuario lo pida. El flujo de entrega: commit + push, y el exe de Windows lo compila GitHub Actions (`.github/workflows/build-windows.yml`, ~10 min; artifact `SteelConPro_portable`). Cuando el usuario pida «el exe», dé el enlace de la ejecución terminada.
- Pruebas (todas deben seguir pasando): `selftest.py` (motor y sísmico), `selftest_nodes.py`, `selftest_ops.py`, `selftest_geocheck.py`, `selftest_geo_vigas.py`, `selftest_geo_cartelas.py`, `selftest_geo_ops.py`, `selftest_geo_malla.py` (`--rapido` omite los barridos), `selftest_articulaciones.py`, `selftest_miembro_a_miembro.py`, `selftest_fem_placas.py` (`--rapido` sin CalculiX), `selftest_mcp.py`, `selftest_sismo_conexion.py`, `selftest_dg4.py` (placa extrema precalificada validada contra AISC Design Guide 4, nudo SMF de AISC 341 y la plantilla fija `smf`), `selftest_empalme.py` (empalme de viga con cubreplacas), `selftest_caras_secciones.py` (caras por componente de las secciones del Section Designer), `selftest_reporte.py` (reporte PDF y Word con figuras y tablas; `--rapido` sin CalculiX), y en Electron `cd electron && xvfb-run -a node tests/smoke.js` `node tests/sismo.js <carpeta>`, `node tests/alambrico.js <carpeta>` `node tests/analisis.js <carpeta>`, `node tests/dg4.js`, `node tests/plantilla_smf.js`, `node tests/empalme.js`, `node tests/formularios.js <carpeta>` (textos de los formularios de operaciones) y `node tests/claude.js`. Cada cambio nuevo lleva su prueba de regresión.
- Antes de dar algo por hecho, mírelo en el visor real con Electron (`tools/capturas_ejemplos.py`, `electron/tests/*.js`) y revise la imagen.
- La memoria del contenedor es limitada: no lance a la vez un solver CalculiX y varias baterías (el sistema mata procesos). Instalación del entorno si falta algo: `pip install -r requirements.txt`, `apt install libglu1-mesa calculix-ccx`, `cd electron && npm install`.
- Documente cada función nueva en `LEEME.md` (secciones por tema) y mantenga los índices `ejemplos/TP-*_INDICE.md`.
- Pregunte antes de decidir cosas de producto que cambien la interfaz de forma visible; el usuario da instrucciones precisas (p. ej. «solo mallado por ahora», «un solo modelo») y espera que se cumplan al pie de la letra.
