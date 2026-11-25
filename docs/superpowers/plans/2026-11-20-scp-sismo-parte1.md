# SteelConPro — Sismo parte 1 (nudo + placa base) — Plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Datos sismicos por conexion, casos de servicio y generador ASCE 7-05 en el nudo, y ACI 17.10 / AISC 341 D2.6 en la placa base de SteelConPro.

**Architecture:** Se trasladan del historial de la rama (commits 57b7b9a..ba7c76a, `placabase/`) `Seismic`, `LoadCombo.kind/E`, `seismic.py` y los cambios de `anchors.py`/`solver.py` al paquete `steelconpro/`. El generador trabaja sobre `Nodo.loads` (combinacion lineal de filas de servicio) y `nodal.base_combos` calcula la parte E de la placa con el caso virtual de solo E. Interfaz Electron: ventana "Sismo" desde la seccion Cargas.

**Tech Stack:** Python 3 (motor), JavaScript (Electron renderer), sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-20-scp-sismo-parte1-design.md` (y para las formulas, `docs/superpowers/specs/2026-11-20-diseno-sismico-design.md` del historial).

## Global Constraints
- Unidades internas in-kip-ksi.  Textos en espanol, identificadores sin tildes.
- Archivos .scp/.pbase anteriores abren igual (claves nuevas con valores por defecto).
- Los casos de SERVICIO (D, L, S, QEx, QEy) no se disenan.
- Pruebas en `selftest.py` (motor); todas las `selftest*.py` deben seguir como en la linea base.

## Review Focus
1. Nudo sin casos de servicio marcados: generar no debe borrar los casos escritos a mano ni fallar.
2. Renombrar o borrar un caso de servicio despues de generar: los casos generados conservan sus cargas; `case_kind`/`case_meta` sin claves huerfanas que rompan.
3. Placa base en un miembro conectado (no el principal): parte E y limite por capacidad con el perfil de ESE miembro.
4. Caso generado editado a mano en la ventana de cargas: su parte E deja de conocerse (100 % sismica).
5. Proyecto con casos del nudo y `seis.enabled = False`: resultados identicos a la linea base.

---
### Task 1: Motor de placa base sismico (traslado)
Files: `steelconpro/model.py`, `steelconpro/seismic.py` (nuevo), `steelconpro/anchors.py`, `steelconpro/solver.py`, `steelconpro/report.py`, `selftest.py`.
Produces: lo mismo que las tareas 1-4 del plan anterior (`Seismic`, `Project.seis`, `LoadCombo.kind/PE…/e_known`, `seismic.generate/capacity_limits/ry_of/seismic_state/seismic_checks`, `OMEGA0_DEFAULT`), sin `prune`.
- [ ] Trasladar las pruebas de sismo del historial (modelo, generador, ACI 17.10, ductil) a `selftest.py`; ver fallar.
- [ ] Trasladar el codigo; `Project.from_json` de SteelConPro debe leer `seis`; `sig3d` y la firma del nudo ignoran `seis` solo si no cambia cargas.
- [ ] Pruebas pasan; commit.

### Task 2: Casos de servicio y generador en el nudo
Files: `steelconpro/conn/specs.py` (`Nodo.case_kind: dict`, `Nodo.case_meta: dict`), `steelconpro/conn/nodal.py`, `steelconpro/seismic.py`, `selftest.py`.
Produces: `SERVICE_KINDS = ("D","L","S","QEx","QEy")`; `nodal.cases_of(nd)` omite los casos de servicio; `seismic.generate_node_cases(prj) -> int` reemplaza en `nd.loads` los casos con kind E/Ωo/"G" generados antes y agrega los nuevos (filas por miembro, `case_kind[c]`, `case_meta[c] = {"g": {D:..,L:..,S:..}, "e": {D:±0.2SDS, QEx:.., QEy:..}}`).
- [ ] Pruebas: nudo con columna principal y una viga, casos D/L/QEx → `generate_node_cases` crea 3 G + 4 E + 4 Ω; fila de la viga del caso "E1" = 1.4·D + 1.0·L(f1) + 0.2·S + 1.0·QEx por componente; `cases_of` no devuelve D/L/QEx; casos a mano intactos; regenerar no duplica.
- [ ] Implementar; pasan; commit.

### Task 3: Parte E y limite D2.6 en las combinaciones de la placa base
Files: `steelconpro/conn/nodal.py` (`_base_cases`), `steelconpro/conn/baseplate.py` (`derive`), `selftest.py`.
- `_base_cases`: para un caso generado, la carga de la placa de la parte E = la del caso virtual `e` (coeficientes de `case_meta`); `kind`, `PE…`, `e_known=True`. Casos con kind "" → como hoy. Ωo: limite `seismic.capacity_limits(bp)` aplicado en `derive` (perfil del miembro de la placa).
- [ ] Pruebas: placa base en el principal con QEx que tracciona → combinacion E con `e_known`, `seismic_state` fN ≈ 1; combinacion Ω con Mux capado a 1.1·Ry·Fy·Zx; `seis.enabled=False` → mismas combinaciones que la linea base.
- [ ] Implementar; pasan; commit.

### Task 4: API e interfaz Electron
Files: `steelconpro/api.py` (`seismic_generate`, `seismic_info`, `constants` con SDC/sistemas/Ωo), `electron/renderer/js/editdialogs.js` (`openSeismic(E)`), `electron/renderer/js/editor.js` (boton en Cargas, tipo junto al caso), `selftest.py` (API).
- [ ] Prueba API: `seismic_generate({connection})` devuelve conexion con casos generados; `seismic_info` da los limites.
- [ ] Implementar; prueba de humo de Electron si el entorno la corre; commit.

### Task 5: Documentacion, ejemplo y empuje
Files: `LEEME.md` (novedades 1.2: modulo sismico), `ejemplos/SIS-01_porticoSMF_placa_base.scp` (con `tools`/script), `selftest.py` (abre y resuelve el ejemplo).
- [ ] Commit y push.
