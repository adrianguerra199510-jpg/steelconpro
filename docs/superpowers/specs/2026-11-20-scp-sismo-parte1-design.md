# SteelConPro — Parte 1: marco sismico de la conexion + placa base (ASCE 7-05 / AISC 341-22 / ACI 318-19)

Partes siguientes (diseño propio cada una): 2) conexiones de riostras SCBF/OCBF/EBF (AISC 341 F1-F3);
3) placas extremas precalificadas AISC 358 Cap. 6 (4E, 4ES, 8ES).  Ambas usan los datos sismicos de esta parte.

## Intencion
El usuario disena nudos de porticos de acero con ASCE 7-05 + AISC 341-22 + ACI 318-19.  SteelConPro 1.1 solo tiene la
casilla heredada `conc.seismic` (0.75 a todo el concreto de los anclajes, incluido el cortante, que ACI 318-19 no pide).
Se necesita: datos sismicos de la conexion, combinaciones ASCE 7-05 generadas desde casos de servicio del nudo, y los
requisitos de ACI 17.10 y AISC 341 D2.6 en la placa base.

## Como funciona hoy (SteelConPro 1.1)
- La conexion es un `Project` con `node: Nodo`.  `Nodo.loads` = filas `Load(case, member, N, Vy, Vz, T, My, Mz)`; cada caso
  es una combinacion YA factorizada.  `conn/nodal.py` hace el equilibrio por caso y `base_combos()` convierte cada caso en
  una `LoadCombo` de la placa base.  Sin casos del nudo, la placa base usa las combinaciones escritas en su operacion.
- El motor de la placa base (`steelconpro/anchors.py`, `solver.py`, `model.py`) es el de PlacaBasePro: el trabajo de la
  rama anterior (commits 57b7b9a..ba7c76a, en el historial) se traslada casi directo.

## Diseno
### Datos
- `Project.seis: Seismic` (igual que en el diseno aprobado: enabled, sdc, system, Omega0, rho, SDS, f1, Ry, H,
  base_moment, cap_limit, ortho, gravity, ductile, sleeve, upset) — por conexion.
- `Nodo.case_kind: dict[str, str]` — tipo de cada caso: "" (combinacion factorizada, como hoy), servicio "D", "L", "S",
  "QEx", "QEy", o generada "E" / "Ωo".  Los casos de SERVICIO no se disenan: `nodal.cases_of()` los omite.
- `Nodo.case_meta: dict[str, dict]` — para los casos generados: coeficientes por caso de servicio, separados en parte
  no sismica y parte sismica (Ev + ρ·QE u Ωo·QE).
- `LoadCombo` gana `kind`, `PE, MxE, MyE, VxE, VyE`, `e_known` (como en el diseno aprobado).
- Migracion: `conc.seismic = True` → `seis.enabled`, casos/combinaciones marcados "E" con parte desconocida.

### Generador (nudo)
`seismic.generate_cases(prj)`: a partir de los casos marcados D/L/S/QEx/QEy crea casos factorizados nuevos (filas `Load`
por miembro = combinacion lineal de las filas de servicio; el equilibrio es lineal) con las combinaciones de ASCE 7-05:
gravedad 2.3.2 (opcional), 12.4.2.3 con ρ·QE, 12.4.3.2 con Ωo·QE, ±QE y 100 % + 30 % opcional.  Reemplaza los casos
generados anteriores; no toca los escritos a mano.

### Placa base
- `nodal.base_combos()`: para un caso generado calcula tambien la carga de la placa de la parte sismica sola (equilibrio
  del caso virtual de solo E) → `PE…VyE`, `e_known = True`, `kind`.
- Casos Ωo: limite por capacidad AISC 341-22 D2.6 sobre Mux/Muy (1.1·Ry·Fy·Z, si la base es empotrada) y Vux/Vuy
  (2·Ry·Fy·Z/H) del miembro que lleva la placa.
- ACI 17.10 por combinacion (se traslada tal cual): SDC C-F; fraccion sismica de traccion y cortante; 0.75 solo en los
  modos de concreto en traccion si fN > 20 % (tambien desprendimiento lateral); sin 0.75 en cortante; τ×0.8/0.4;
  anclaje ductil opcional (1.2·Nsa, estiramiento ≥ 8·da, futa/fya ≥ 1.3); barras U/Omega Gr.60/80; avisos (adhesivo
  355.4, no fisurado, sin Ωo, demanda critica, riostras, 12.5.4); seccion "REQUISITOS SISMICOS" en la memoria.
- Combinaciones escritas en la operacion (sin casos del nudo): columna "Tipo" (""/E/Ωo).

### Interfaz (Electron)
- Arbol del editor, seccion Cargas: boton **Sismo** → ventana con datos de sitio/sistema, asignacion del tipo de cada caso
  (lista desplegable por caso: combinacion / D / L / S / QEx / QEy) y **Generar combinaciones**; muestra los limites
  1.1·Ry·Fy·Z y 2·Ry·Fy·Z/H.  Ventana de cargas: el tipo del caso junto a su nombre.
- API: `seismic_generate(connection) -> connection`, `seismic_info(connection) -> {limites, Ωo por sistema}`.

### Pruebas
`selftest.py` (motor): las mismas del diseno aprobado + generacion en el nudo (casos de servicio omitidos del diseno,
caso generado = combinacion lineal, parte E de la placa, limite D2.6, archivo viejo).  Prueba de Electron solo si el
entorno lo permite (`electron/tests/smoke.js`).

## Fuera de esta parte
Partes 2 y 3; poda de combinaciones (se deja para despues: aqui las combinaciones las usa todo el nudo, no solo la placa).
