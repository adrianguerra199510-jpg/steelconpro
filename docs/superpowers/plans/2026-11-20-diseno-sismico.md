# Diseno sismico de placas base — Plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modulo sismico completo (ASCE 7-05 / AISC 341-22 / ACI 318-19 §17.10) con generador de combinaciones y verificaciones por combinacion.

**Architecture:** Nuevo `placabase/seismic.py` (datos de sistema, Ry, generador, fraccion sismica, verificaciones ACI 17.10 / AISC 341). `model.py` gana `Seismic` y campos de tipo/parte E en `LoadCombo`. `anchors.py` toma el factor 0.75 de la combinacion en lugar de `conc.seismic`. `solver.py` agrega las verificaciones, avisos y la seccion de memoria. `ui.py` agrega la pestana Sismica y la columna Tipo.

**Tech Stack:** Python 3, dataclasses, PySide6 (UI), sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-20-diseno-sismico-design.md`

## Global Constraints
- Unidades internas in-kip-ksi; la UI convierte con `UnitSet` (`u.inn`/`u.out`).
- Textos en espanol sin tildes en identificadores, igual que el resto del codigo; φ, Ω, ρ permitidos en textos.
- Archivos .pbase de versiones anteriores deben abrir sin error (`Project.from_json` ignora claves desconocidas; `seis` ausente = desactivado).
- `sig3d()` no debe cambiar por `seis` (no invalidar el 3D).
- Pruebas: secciones nuevas en `selftest.py` (unico arnes del proyecto, empaquetado en el .exe); `QT_QPA_PLATFORM=offscreen python3 selftest.py` debe terminar en "TODAS LAS PRUEBAS DEL MOTOR PASARON".
- Normas citadas: ASCE 7-05 §2.3.2, §12.4.2.3, §12.4.3.2, §12.5, Tabla 12.2-1; AISC 341-22 §D2.6, Tabla A3.2, A3.4b; ACI 318-19 §17.10.1–17.10.7, Tabla 17.6.5.2.5.

## Review Focus
1. Combinacion con Nua = 0 (sin traccion): fraccion sismica no debe dividir por cero → 0 y sin factor 0.75.
2. Casos de carga todos en cero / QE en cero: el generador produce combinaciones validas y no duplica identicas (las identicas se fusionan).
3. Perfil girado 90° o rotacion arbitraria con limite por capacidad: Zx/Zy correctos (90 intercambia; otra usa el mayor).
4. Archivo viejo con `conc.seismic = True`: abre, activa el modulo, marca combinaciones "E", y el resultado aplica 0.75 solo a traccion.
5. `prune` con una sola combinacion o con todas iguales: nunca deja la lista vacia.

---

### Task 1: Modelo de datos y compatibilidad

**Files:** Modify `placabase/model.py`; Test `selftest.py`

**Interfaces — Produces:**
- `SEIS_SYSTEMS: list[str]`, `SDC_LIST = ["A","B","C","D","E","F"]`, `SEIS_CASES = ["D","L","S","QEx","QEy"]` en `model.py`.
- `@dataclass Seismic` con los campos del spec (`enabled=False, sdc="D", system=SEIS_SYSTEMS[0], Omega0=3.0, rho=1.0, SDS=1.0, f1=1.0, Ry=0.0, H=157.5, base_moment=True, cap_limit=True, ortho=False, gravity=True, prune=True, ductile=False, sleeve=0.0, upset=False, cases: list` = 5 filas `[P,Mx,My,Vx,Vy]` en cero).
- `Project.seis: Seismic`.
- `LoadCombo.kind: str = ""`, `PE, MxE, MyE, VxE, VyE: float = 0.0`, `e_known: bool = False`.
- `Project.combo_loads_noE(i) -> Project`: copia con la combinacion i sin su parte E (si `e_known`; si no, P/M/V = 0).
- `normalize()`: migra `conc.seismic=True` → `seis.enabled=True`, combos sin kind → "E", `conc.seismic=False`.
- `sig3d()` excluye `seis`.

- [ ] Step 1: prueba en `selftest.py` seccion "SISMO — MODELO": proyecto con `conc.seismic=True` → tras `normalize()`, `seis.enabled` True, todas las `kind == "E"`, `conc.seismic` False; `Project.from_json(p.to_json())` conserva `seis.cases` y `kind`; `sig3d` igual con/sin cambiar `seis.SDS`.
- [ ] Step 2: correr selftest, ver la falla.
- [ ] Step 3: implementar.
- [ ] Step 4: selftest pasa.
- [ ] Step 5: commit.

### Task 2: Generador de combinaciones (`seismic.py`)

**Files:** Create `placabase/seismic.py`; Test `selftest.py`

**Interfaces — Produces:**
- `OMEGA0_DEFAULT: dict[str, float]` (SMF/IMF/OMF 3.0; SCBF/OCBF/EBF 2.0; gravedad 3.0; no detallado 3.0).
- `ry_of(steel_name: str) -> float` (A36 1.5, A992/A572/A588/A913 1.1, A500 Gr.B 1.4, A500 Gr.C 1.3, A53 1.6, A1085 1.25, otro 1.1).
- `capacity_limits(prj) -> dict` con `Mx, My, Vx, Vy` (kip·in / kip) = 1.1·Ry·Fy·Z y 2·Ry·Fy·Z/H con la regla de rotacion.
- `generate(prj) -> list[LoadCombo]` (sin prune) y `prune(prj, combos) -> list[LoadCombo]`.
- Nombres: prefijo "G#", "E#", "Ω#".

- [ ] Step 1: pruebas: con D=(100,0,0,0,0), L=(50,…), S=0, QEx=(0,1000,0,0,20), SDS=1.0, ρ=1.0, Ωo=3, f1=1, gravity, sin ortho → 3 G + 4 E + 4 Ω = 11 (QEy nulo se omite: ±QEy identicos a sin QE → fusionados); E1 Pu = 1.4·100+50 = 190, Mux = ±1000; parte E de E1: PE = 0.2·100 = 20, MxE = ±1000; combinacion 0.9 → Pu = 0.7·100 = 70; Ω: Mux = ±3000 y, con `cap_limit` y W14X90 A992 (Zx=157, Ry 1.1) → |Mux| = min(3000, 1.1·1.1·50·157 = 9498.5) = 3000; con QEx Mx=10000 → capado a 9498.5. Con ortho: 3 + 8·2 + 8·2 = 35 antes de fusionar. `ry_of("ASTM A992") == 1.1`, `ry_of("ASTM A36") == 1.5`. Rotacion 90° intercambia limites Mx/My.
- [ ] Step 2: falla.
- [ ] Step 3: implementar `generate`, `capacity_limits`, `ry_of`; fusion de duplicados por (kind, valores redondeados).
- [ ] Step 4: pasa.
- [ ] Step 5: commit.

### Task 3: Fraccion sismica y factores ACI 17.10 en anclajes

**Files:** Modify `placabase/seismic.py`, `placabase/anchors.py`; Test `selftest.py`

**Interfaces:**
- Produces `seismic_state(prj) -> SeisState` (dataclass: `active: bool`, `kind: str`, `fN: float`, `fV: float`, `k_t: float` (0.75 o 1.0), `bond: bool` (reduccion τ)).
  `active` = `seis.enabled` y SDC en C–F y combinacion activa con kind E/Ω. `fN` = (Tu − Tu_sinE)/Tu con `D.bearing` cerrado (0 si Tu ≤ 1e-9); sin parte conocida → 1.0. `k_t` = 0.75 si `fN > 0.20`.
- `anchors.anchor_checks`: `k_seis` → `st.k_t` solo en traccion (Ncb, Np, Nsb, Na); cortante (Vcb, Vcp) sin factor; reduccion τ si `st.active`. Desprendimiento lateral gana el factor.
- [ ] Step 1: pruebas: combinacion E con toda la traccion de QE → `k_t == 0.75`; capacidad `aci_ncb` = 0.75 × la de gravedad; `aci_vcb` igual con y sin sismo; combinacion E con QE pequeno (fN ≤ 0.2) → `k_t == 1.0`; Pu grande sin traccion → fN = 0; SDC "B" → inactivo.
- [ ] Step 2: falla. Step 3: implementar. Step 4: pasa. Step 5: commit.

### Task 4: Verificaciones y avisos sismicos + memoria

**Files:** Modify `placabase/seismic.py`, `placabase/solver.py`; Test `selftest.py`

**Interfaces — Produces:** `seismic_checks(prj, br, rec) -> (list[Check], list[str])` llamada desde `solve` tras `anchor_checks`.
- Checks (claves): `seis_duct_mat` (acero ductil), `seis_duct_ratio` (r_c ≤ r_s, 17.10.5.3(a)), `seis_stretch` (8·da ≤ sleeve + grout + standoff + tp), `seis_futa` (1.3 ≤ futa/fya, skip si `upset`) — solo con `ductile`; `seis_rebar` (fy ∈ {60, 80}) si `conc.u_on`.
- Avisos: SDC A/B; no fisurado; adhesivo 355.4; stand-off y pandeo (con `ductile`); cortante > 20 % sin combinaciones Ω en el proyecto; soldadura de demanda critica (SMF/IMF/SCBF/EBF); arriostrados → fuerzas de riostras; SDC ≥ D sin 100/30.
- Memoria: `rec.section("S.  REQUISITOS SISMICOS  (ASCE 7-05 / AISC 341-22 / ACI 318-19 17.10)")` con tipo de combinacion, fN, fV, factor aplicado, Ry, limites D2.6.
- Se quita el aviso viejo de `conc.seismic` en `solver.py`.
- [ ] Step 1: pruebas: F1554 Gr.105 con `ductile` → `seis_futa` no cumple; Gr.36 cumple; con `upset` skip; estiramiento 8·1.25 = 10 in con sleeve 0, grout 1.5, tp 2 → no cumple; sleeve 8 → cumple; barras U fy 75 → `seis_rebar` no cumple; memoria contiene "REQUISITOS SISMICOS".
- [ ] Step 2–5: falla, implementar, pasa, commit.

### Task 5: Interfaz y reportes

**Files:** Modify `placabase/ui.py`, `placabase/report.py`; Test `selftest.py` (seccion interfaz offscreen existente)

- Pestana "Sismica" (despues de "Cargas"): grupos "Sitio y sistema" (`seis.enabled`, `seis.sdc`, `seis.system`, `seis.Omega0`, `seis.rho`, `seis.SDS`, `seis.f1`, `seis.Ry`, `seis.H`, `seis.base_moment`), "Cargas de servicio por caso" (QTableWidget 5×5 `tbl_seis`, unidades de trabajo), "Generacion de combinaciones" (`seis.gravity`, `seis.ortho`, `seis.cap_limit`, `seis.prune`, boton "Generar combinaciones" → `self.seis_generate()` con confirmacion), "Anclaje ductil (ACI 17.10.5.3(a))" (`seis.ductile`, `seis.sleeve`, `seis.upset`). Al cambiar `seis.system` se copia `OMEGA0_DEFAULT`.
- Tabla de combinaciones: 7a columna "Tipo" ("", "E", "Ωo"); al editar a mano P/M/V de una generada, `e_known` pasa a False.
- Se quita la casilla de `conc.seismic` de la pestana Concreto.
- `report.input_rows`: fila "Diseno sismico".
- [ ] Step 1: prueba offscreen: la ventana tiene la pestana "Sismica"; `seis_generate()` sin dialogo (parametro `ask=False`) deja `len(prj.combos) > 1` y `tbl_cb.columnCount() == 7`.
- [ ] Step 2–5: falla, implementar, pasa, commit.

### Task 6: Documentacion y ejemplo
**Files:** Modify `LEEME.md`; Create `ejemplos/SIS-01_W14X90_SMF.pbase`
- Novedades: modulo sismico, cambio de criterio del 0.75 (ya no en cortante; si en desprendimiento lateral), flujo de uso. Ejemplo generado con el generador.
- [ ] Verificar que el ejemplo abre y resuelve en `selftest.py`; commit; push.
