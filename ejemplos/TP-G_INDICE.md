# Ejemplos TP-G (operaciones generales / modelado libre)

Se generan con `python3 tools/ejemplos_generales.py` (con `--revisa` imprime el revisor y las verificaciones). Todos: build sin excepciones, revisor de geometría con 0 errores y 0 avisos, `api.verify` sin excepciones. Se probaron en el visor (capturas de TP-G01, 05, 08, 09, 13, 14 y 16).

| Archivo | Qué es | Operaciones | Revisor | Notas |
|---|---|---|---|---|
| TP-G01_empalme_columna_atornillado | Empalme de columna W14X90: cubrejuntas en alas (fuera) y alma (dos), pernos a ambos lados | PLACA (sin unión propia) ×4, PERNOS ×6 (varias capas) | 0 / 0 | Los pernos de las dos alas van escalonados 2 in (el revisor da falso error de agujeros superpuestos si comparten línea: ver informe) |
| TP-G02_empalme_viga_atornillado | Empalme de viga W24X55: cubrejuntas exteriores e interiores en cada ala y dos de alma | PLACA ×8 (usa las caras interiores de las alas), PERNOS ×10 | 0 / 0 | |
| TP-G03_empalme_columna_hss | Empalme de columna HSS8X8X1/2 con dos placas laterales y pernos pasantes (dos paredes) | PLACA ×2, PERNOS ×2 | 0 / 0 | |
| TP-G04_empalme_soldado_cjp | Empalme a tope de columna W con soldadura CJP en todo el contorno | SOLDADURA (contorno del miembro, CJP) | 0 / 0 | |
| TP-G05_rigidizadores_columna | Placas de continuidad (2 niveles × 2 lados) y diagonal de alma recortada contra las alas | PLACA ×5, SOLDADURA ×7, RECORTE ×2 (contra caras interiores de las alas) | 0 / 0 | |
| TP-G06_cap_plate_columna | Placa de cabeza 18×18×1 con 4 huecos | PLACA sobre «Extremo fin», HUECOS | 0 / 0 | El cordón sigue el contorno del perfil, no los bordes de la placa |
| TP-G07_placa_base_rigidizada | Placa base con 4 rigidizadores triangulares soldados a las alas y a la placa base | BASE, PLACA ×4, SOLDADURA ×4 | 0 / 0 | La placa base no es pieza: su soldadura no se mide en el revisor |
| TP-G08_mensula_soldada | Ménsula: repisa 1 in con CJP y dos nervios triangulares | PLACA ×3 (perpendiculares), SOLDADURA ×2 | 0 / 0 | |
| TP-G09_rodilla_portico | Rodilla: viga recortada y soldada en contorno, continuidad, diagonal recortada contra las placas, placa de cabeza | RECORTE ×3, SOLDADURA ×8, PLACA ×6 | 0 / 0 | 2 notas de «sobresale de la cara» (chaflán de las placas de continuidad) |
| TP-G10_cartela_cubierta | Cartela de cubierta con esquinas recortadas y 6 huecos | PLACA, HUECOS | 0 / 0 | |
| TP-G11_apoyo_sobre_muro | Viga W16X31 sobre un muro de concreto (elemento Bloque de concreto): placa de apoyo más ancha que el ala, ranuras, 4 anclajes que entran al muro, rigidizadores y ángulo | BLOQUE, PLACA ×3, HUECOS (ranura), PERNOS (anclajes), ÁNGULO, SOLDADURA ×2 | 0 / 0 | Nota informativa: la placa sobresale del ala (los cordones se recortan al apoyo) |
| TP-G12_placa_con_aberturas | Placa de alma con abertura circular, huecos rectangulares y ranuras | PLACA con abertura, HUECOS ×2 | 0 / 0 | |
| TP-G13_placa_atravesada_por_tubo | Repisa con abertura que rodea a un tubo, soldada a él por el borde de la abertura | PLACA (abertura «Rodea al miembro»), SOLDADURA (4 caras) | 0 / 0 | Nota «V1 no toca al principal»: el tubo está desplazado y solo se une por la repisa |
| TP-G14_placas_recortadas | Placa con muesca contra el volumen de una viga; placa cortada por un plano de trabajo | RECORTE (volumen y plano), PLANO DE TRABAJO | 0 / 0 | |
| TP-G15_modos_soldadura | Rigidizadores con filete, un lado, CJP, PJP e intermitente | PLACA ×5, SOLDADURA ×5 | 0 / 0 | |
| TP-G16_angulo_asiento | Ángulo de asiento soldado a la columna y atornillado a la viga + ángulo de unión | ÁNGULO ×2 (con giro), PERNOS | 0 / 0 | |
| TP-G17_tubo_redondo_con_nervios | Tubo redondo con dos nervios perpendiculares soldados sobre la generatriz y placa de cabeza circular | PLACA ×3 | 0 / 0 | Una placa paralela sobre un redondo solo toca la generatriz (nota) || TP-G18_posicion_referenciada | Continuidad a la altura de las alas de la viga (`pos_ref`), rigidizador de la viga a 9 in de la columna, viga con soldadura de recorte | RECORTE con `trim_weld`, PLACA ×5 con posición referenciada | 0 / 0 | |
| TP-G19_recortes_con_soldadura | Repisa con muesca contra el volumen de una viga (holgura 0) soldada solo en el contacto y viga recortada con soldadura | RECORTE ×2 con `trim_weld` | 0 / 0 | |

## No soportado
- Placas PARALELAS sobre perfiles redondos (silla cilíndrica): solo se admite el nervio perpendicular sobre la generatriz (franja de contacto de ±0.5 in); la paralela deja nota.
