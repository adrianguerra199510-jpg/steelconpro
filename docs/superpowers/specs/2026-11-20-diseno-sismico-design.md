# Diseno sismico de placas base — ASCE 7-05 / AISC 341-22 / ACI 318-19

## Intencion
SteelConPro (base PlacaBasePro 3.2.11) solo tiene una casilla "Diseno sismico (ACI 17.10, factor 0.75)" que
multiplica por 0.75 TODA la resistencia del concreto de los anclajes. El usuario disena bases de columnas de
porticos de acero bajo **ASCE 7-05 + AISC 341-22 + ACI 318-19** y necesita que el programa:
1. incorpore los requisitos sismicos de esas normas (no solo un factor), y
2. quede configurado para hacer el analisis y diseno sismico: generar las combinaciones, correrlas (cerrado + 3D)
   y reportar el cumplimiento.

## Metas
- Pestana **Sismica** con datos del sitio/sistema, cargas de servicio por caso y generador de combinaciones.
- Combinaciones LRFD de ASCE 7-05 generadas automaticamente, marcadas por tipo (gravedad / E / Ωo) y con la
  parte sismica conocida.
- Requisitos ACI 318-19 §17.10 aplicados por combinacion, como dice la norma.
- Resistencia requerida de la base segun AISC 341-22 §D2.6 (limite por capacidad de la columna).
- Todo visible en la memoria de calculo, la tabla de resultados y los reportes PDF/DOCX/XLSX.

## No-metas
- Analisis sismico global (espectro, periodo, calculo de QE): QE viene del modelo del edificio.
- Fuerzas de conexiones de riostras (D2.6a(a)/D2.6b(a)): el usuario las incluye en QE; se avisa.
- Requisitos de detalle de la columna fuera de la base (zonas protegidas, empalmes).

## Anti-metas
- Aplicar factores donde la norma no los pide (p. ej. 0.75 al cortante) o dejar de aplicarlos donde si.
- Romper archivos .pbase existentes o el flujo manual de combinaciones.

## Enfoque elegido (A) y alternativas
- **A — Generador + verificaciones integradas (elegido).** Las combinaciones generadas son combinaciones normales
  del proyecto, asi el calculo cerrado, el 3D y los reportes existentes las procesan sin cambios.
- B — Solo verificaciones, combinaciones a mano: menos trabajo, propenso a errores de factores/signos.
- C — Analisis sismico global: fuera del alcance de un programa de conexiones.

## Diseno

### Datos (`model.py`)
Nuevo `Seismic` dentro de `Project` (`prj.seis`):
- `enabled`, `sdc` (A–F), `system` (SMF, IMF, OMF, SCBF, OCBF, EBF, columna de gravedad, sistema no detallado
  R=3), `Omega0` (por defecto segun sistema, ASCE 7-05 Tabla 12.2-1, editable), `rho` (1.0/1.3), `SDS`, `f1`
  (factor de L, 1.0 o 0.5 segun 2.3.2 exc. 1), `Ry` (0 = automatico de AISC 341-22 Tabla A3.2 por el acero del
  perfil), `H` (altura de piso), `base_moment` (base empotrada), `cap_limit` (limitar Ωo por capacidad D2.6),
  `ortho` (100 % + 30 %), `gravity` (incluir combinaciones de gravedad), `prune` (conservar solo las que gobiernan),
  `ductile` (verificar anclaje ductil 17.10.5.3(a)), `sleeve` (longitud desadherida en el concreto), `upset`
  (rosca recalcada).
- `cases`: cargas sin factorar D, L, S, QEx, QEy → [P, Mx, My, Vx, Vy] cada una (en ejes de la columna, igual que
  las combinaciones).
- `LoadCombo` gana `kind` ("" gravedad/manual, "E", "Ωo") y la parte sismica `PE, MxE, MyE, VxE, VyE` +
  `e_known`. Una combinacion marcada a mano como E/Ωo sin parte conocida se trata como 100 % sismica
  (conservador).
- Compatibilidad: archivos con `conc.seismic = True` se abren con `seis.enabled = True` y sus combinaciones
  marcadas "E" (parte desconocida). La casilla vieja desaparece de la pestana Concreto.
- `sig3d()` ignora `seis` (las cargas llegan por las combinaciones).

### Generador (`seismic.py`, nuevo)
ASCE 7-05:
- Gravedad (§2.3.2, opcional): 1.4D ; 1.2D + 1.6L + 0.5S ; 1.2D + 1.6S + f1·L.
- Sismica (§12.4.2.3): (1.2 + 0.2SDS)D + ρQE + f1·L + 0.2S ; (0.9 − 0.2SDS)D + ρQE.
- Sobrerresistencia (§12.4.3.2): igual con Ωo·QE.
- Direcciones: ±QEx, ±QEy; con `ortho`, ±QEx ± 0.3QEy y ±0.3QEx ± QEy (§12.5).
- Parte E = ±0.2SDS·D (Ev) + ρ/Ωo·QE.
- Limite por capacidad (AISC 341-22 D2.6b/c) en las combinaciones Ωo, si `cap_limit`:
  |Mux| ≤ 1.1·Ry·Fy·Zx, |Muy| ≤ 1.1·Ry·Fy·Zy (solo si `base_moment`), |Vuy| ≤ 2·Ry·Fy·Zx/H, |Vux| ≤ 2·Ry·Fy·Zy/H
  (rotacion 90° intercambia Zx/Zy; otra rotacion usa el mayor Z, conservador). La parte E se recalcula.
- `prune`: se calcula cada combinacion con el metodo cerrado y se conservan solo las que dan el mayor D/C de al menos
  una verificacion (reduce las corridas 3D). Desactivable.
- Nombres legibles: "E3: 1.40D+1.0L+0.2S−1.0QEx", "Ω2: 0.70D+3.0QEy".
- Boton "Generar combinaciones" en la pestana Sismica reemplaza la lista (con confirmacion).

### Verificaciones (`anchors.py`, `seismic.py`, `solver.py`)
Solo si `seis.enabled` y SDC ∈ {C, D, E, F} (ACI 17.10.1); en SDC A/B se avisa que 17.10 no aplica.
Para cada combinacion tipo E/Ωo:
- Fraccion sismica de la traccion = (Nua − Nua sin E)/Nua (calculo cerrado) y del cortante igual con Vua.
- **Traccion > 20 %** (17.10.5.2/17.10.5.4): 0.75 sobre arrancamiento, extraccion, desprendimiento lateral y
  adherencia. **≤ 20 %**: sin factor (17.10.5.1).
- **Cortante**: sin 0.75 (17.10.6). Si > 20 % y no hay combinaciones Ωo en el proyecto → aviso de que falta
  17.10.6.3.
- Adherencia: τcr×0.8, τuncr×0.4 (Tabla 17.6.5.2.5 nota) — ya existe, pasa a depender de la combinacion sismica.
- Concreto no fisurado → aviso (17.10.5.4 supone fisurado).
- Si `ductile` (17.10.5.3(a)): acero ductil; Nua,b/(1.2·Nsa) ≥ max(Nua/Ncbg, Nua,b/Npn, Nua/Nsbg, Nua/Nag)
  con resistencias nominales; estiramiento = sleeve + mortero + stand-off + tp ≥ 8·da; futa/fya ≥ 1.3 salvo rosca
  recalcada (F1554 Gr.105 no cumple); aviso de pandeo con stand-off (inversion de carga).
- Barras U/Omega: fy de 60 u 80 ksi (17.10.4).
- Adhesivo: aviso de calificacion sismica ACI 355.4 (17.10.3).
- AISC 341: soldaduras columna-placa de SMF/IMF/SCBF/EBF son de demanda critica (A3.4b) → aviso; sistema
  arriostrado → aviso de incluir las fuerzas de las conexiones de riostras en QE.
- Memoria: seccion "S. REQUISITOS SISMICOS" con datos, fraccion sismica, factor aplicado y limites D2.6.

### Interfaz (`ui.py`)
- Pestana **Sismica** entre Cargas y Perfil: grupos "Sitio y sistema", "Cargas de servicio por caso" (tabla 5×5 en
  unidades de trabajo), "Generacion de combinaciones", "Anclaje ductil (ACI 17.10.5.3(a))".
- La tabla de combinaciones gana la columna **Tipo** ("", "E", "Ωo").
- Campos visibles segun lo elegido (como el resto del programa).

### Reportes
- `report.input_rows`: fila "Diseno sismico" con los parametros. Las verificaciones nuevas salen solas (se
  iteran `res.checks`).

### Pruebas (`selftest.py`)
Conteo y factores de las combinaciones generadas, limite por capacidad, regla del 20 %, 0.75 solo en traccion,
anclaje ductil (F1554 Gr.105 falla futa/fya), migracion de la casilla vieja, pestana en la interfaz offscreen.

## Decisiones tomadas por el constructor (revisables)
- f1 por defecto 1.0 (conservador); el usuario pone 0.5 si aplica.
- 100 % + 30 % desactivado por defecto; aviso si SDC ≥ D y esta apagado.
- La fraccion sismica se calcula con el metodo cerrado aunque haya 3D (es una clasificacion, no una resistencia).
- Ry de perfiles no listados = 1.1, con nota.
