# Ejemplos TP-V: conexiones típicas viga–columna y viga–viga

Se generan con `python3 tools/ejemplos_vigas.py` (con `--revisar` también arma cada modelo, corre el revisor de geometría y `api.verify`).
Estado del revisor de geometría: **0 errores y 0 avisos en los 38 ejemplos**; `api.verify` corre sin excepciones. Prueba: `python3 selftest_geo_vigas.py`.

| Código | Qué es | Operaciones | Notas |
|---|---|---|---|
| TP-V01 | Placa simple, viga W al ala de columna W | `Placa simple` | |
| TP-V02 | Placa simple al alma de columna W | `Placa simple` | corte automático de las alas de la viga |
| TP-V03 | Placa simple a la cara de columna HSS | `Placa simple` | |
| TP-V04 | Placa simple, secundaria a viga maestra | `Placa simple` | corte (cope) automático |
| TP-V05 | Placa simple con la viga soldada a la placa | `Placa simple` (`beam_conn` = Soldada) | filetes en el alma de la viga |
| TP-V06 | Placa simple «hasta el interior de las alas» en columna | `Placa simple` (`tab_mode`) | placa plana soldada al alma, sin filetes a las alas |
| TP-V07 | Dos placas arriba y abajo entre las alas de la columna | `Placa simple` (`tab_split`) | placas horizontales soldadas al alma y a las alas |
| TP-V08 | Placa simple «hasta las alas» en viga maestra | `Placa simple` (`tab_mode`) | placa escalonada entre las alas, 4 filetes a ellas |
| TP-V09 | Doble ángulo, ala de columna W | `Doble ángulo` | |
| TP-V10 | Doble ángulo, secundaria a viga maestra | `Doble ángulo` | cope automático |
| TP-V11 | Doble ángulo a columna HSS | `Doble ángulo` | |
| TP-V12 | Asiento bajo viga W en ala de columna | `Asiento` | |
| TP-V13 | Placa extrema a ras + continuidad | `Placa extrema a ras`, `Placas de continuidad` | |
| TP-V14 | Placa extrema extendida + continuidad | `Placa extrema extendida`, `Placas de continuidad` | |
| TP-V15 | Alas soldadas y alma atornillada (WUF) + continuidad | `Alas soldadas…`, `Placas de continuidad` | |
| TP-V16 | Placa extrema a ras en columna HSS | `Placa extrema a ras` | |
| TP-V17 | Columna de esquina, 2 vigas (ala y alma) | placa simple + doble ángulo | |
| TP-V18 | Columna de borde, 3 vigas | 2 placas simples + doble ángulo | |
| TP-V19 | Columna interior, 4 vigas | placa extrema extendida, doble ángulo, 2 placas simples | |
| TP-V20 | Columna HSS interior, 3 vigas | 3 placas simples | |
| TP-V21 | Viga maestra con 2 secundarias opuestas | doble ángulo + placa simple | |
| TP-V22 | Viga esviada 30° | placa simple | la placa se apoya en la cara; la viga se retrasa |
| TP-V23 | Viga esviada 45° | doble ángulo | pierna al soporte plana sobre la cara |
| TP-V24 | Viga esviada 30° | placa extrema a ras | placa alineada con la cara; la viga se corta en ángulo |
| TP-V25 | Viga esviada 30° | asiento | pierna vertical sobre la cara |
| TP-V26 | Viga esviada 30° | alas soldadas + alma atornillada | viga cortada en ángulo contra la cara |
| TP-V27 | Viga de cubierta, pendiente 15° | placa simple | |
| TP-V28 | Viga de cubierta, pendiente 18° | placa extrema a ras | |
| TP-V29 | Viga de cubierta, pendiente 10° | doble ángulo | |
| TP-V30 | Secundaria esviada 30° a viga maestra | placa simple | cope automático |
| TP-V31 | Viga esviada 30° al alma de columna W | `Placa simple` | se cortan las alas de la viga (cope automático) |
| TP-V32 | Viga esviada 30° (otro lado) al alma de columna W | `Doble ángulo` | cope automático |
| TP-V33 | Viga inclinada 12° al alma de columna W | `Placa simple` | |
| TP-V34 | Asiento rigidizado en ala de columna W | `Asiento` (`seat_stiff`, `seat_stiff_t`) | rigidizador por una ranura de la pierna vertical, soldado a la columna y al ángulo |
| TP-V35 | Asiento rigidizado con viga esviada 30° | `Asiento` (`seat_stiff`) | |
| TP-V36 | Asiento rigidizado en columna HSS | `Asiento` (`seat_stiff`) | |
| TP-V37 | Placa simple a columna de tubo redondo | `Placa simple` | borde de la placa con silla; cordón en varios tramos |
| TP-V38 | Placa simple de viga HSS a tubo redondo horizontal, esviaje 30° | `Placa simple` | la viga se retrasa para no entrar al tubo |
| TP-V39 | Placa extrema 8ES precalificada (AISC DG4, ejemplo 4.4), diseño sísmico | `Placa extrema extendida` (`ep_dg4 = 8ES`), `Placas de continuidad` | valida contra la guía: φMnp = 8600, Yp = 277.6, tp,req = 0.87 in, Yc = 377.7 con placas de continuidad |
| TP-V40 | Plantilla fija «Pórtico especial: placa extrema precalificada (AISC DG4)», 8ES con vigas a los dos lados | tipología `smf` (plantilla favorita del inicio), `Placa extrema extendida` ×2, `Placas de continuidad` | verificación del nudo AISC 341-22: columna fuerte–viga débil, zona del panel (falla: pide placa adosada), placas de continuidad (espesor ≥ tbf con dos vigas) |
| TP-V41 | Empalme de viga W18X50 con cubreplacas atornilladas en alas y alma | `Empalme de viga con cubreplacas` (alas y alma atornilladas, 2 columnas en el alma) | pernos de las alas en simple cortante, F13.1 con los agujeros del ala, alma con excentricidad y Mw |
| TP-V42 | Empalme de viga con alas soldadas y alma atornillada | `Empalme de viga con cubreplacas` (`sp_flange = Soldada`) | filetes longitudinales y transversal de las cubreplacas (J2-10) |
| TP-V43 | Empalme de viga todo soldado, con cubreplacas exteriores e interiores | `Empalme de viga con cubreplacas` (`sp_flange = sp_web = Soldada`, `sp_inner`) | filetes en C de las placas del alma (método elástico) |
| TP-V44 | Empalme soldado de viga doble 2×HN600×200×11×17 que desarrolla su capacidad (placas de 20 mm Gr. 50) | operaciones generales: 4 vigas (`V1b`, `V2b` paralelas al principal), `Placa` ×4 (cubreplacas 340×720, placas de alma 500×1410 por la cara exterior), `Soldadura de filete entre elementos` ×4 (14 y 12 mm) | casos A (φMn con 30 % de φVn) y B (φVn); fuerzas a mano en las soldaduras; aviso «su eje no toca» esperado (vigas paralelas) |
| TP-V45 | El empalme de TP-V44 con la viga doble como UNA sección personalizada (`2XHN600X200X11X17`, Section Designer): solo 2 miembros | `Placa` ×4 y `Soldadura de filete entre elementos` ×4 sobre las caras de los componentes («Comp. 6 (Rect.) — Cara +X» = cara exterior del alma derecha) | mismas soldaduras y D/C que TP-V44 (0.88 y 0.39) |

## Limitaciones conocidas (no soportado o avisado)
- Placa extrema, asiento y alas soldadas con la viga esviada o inclinada contra el ALMA de una columna I (dentro de las alas): la viga choca con las alas; se avisa
  y se recomienda placa simple o doble ángulo (se cortan las alas de la viga). Un esviaje de 45° desde el centro del alma ya sale por el borde de las alas.
- Apoyo redondo (HSS circular): solo la placa simple (con silla). Doble ángulo, asiento, placa extrema y alas soldadas se avisan (cara curva).
- Sección libre (Section Designer) como principal: sin plano de apoyo conocido; se dibuja perpendicular al miembro.
- Viga más profunda que la cara del soporte: el asiento se acorta y se avisa; las alas soldadas / pernos fuera de la cara se omiten con nota.
- «Dos placas arriba y abajo» solo se arma con el principal vertical (alas a los lados de la viga); con viga maestra horizontal se avisa y se dibuja una placa.
