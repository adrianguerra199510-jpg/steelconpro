# Ejemplos TP-A: arriostramientos y nudos de armadura

Generados con `python3 tools/ejemplos_arriostramientos.py` (una función `ex_aNN` por ejemplo). Revisados con `selftest_geo_cartelas.py` (0 errores del revisor de geometría y `api.verify` sin excepciones).

| Archivo | Qué es | Operaciones | Revisor (errores / avisos) | verify D/C | Notas |
|---|---|---|---|---|---|
| `TP-A01_diagonal_HSS_cartela_atornillada_ala_columna.scp` | diagonal HSS con cartela atornillada al ala de una columna W | Cartela atornillada | 0 / 0 | 0.45 |  |
| `TP-A02_diagonal_HSS_cartela_soldada_ala_columna.scp` | diagonal HSS soldada a la cartela (ranura en el tubo) soldada al ala de una columna W | Cartela con miembro soldado | 0 / 0 | 0.45 |  |
| `TP-A03_diagonal_W_cartela_atornillada_ala_columna.scp` | diagonal W (alma contra la cartela) con cartela atornillada al ala de una columna W | Cartela atornillada | 0 / 0 | 0.48 |  |
| `TP-A04_diagonal_W_cartela_soldada_ala_columna.scp` | diagonal W soldada a la cartela soldada al ala de una columna W | Cartela con miembro soldado | 0 / 0 | 0.48 |  |
| `TP-A05_diagonal_HSS_cartela_alma_columna.scp` | diagonal HSS con cartela atornillada al alma de una columna W (entre las alas) | Cartela atornillada | 0 / 0 | 0.45 |  |
| `TP-A06_diagonal_HSS_columna_HSS.scp` | diagonal HSS con cartela atornillada a una columna tubular HSS | Cartela atornillada | 0 / 0 | 0.45 |  |
| `TP-A07_diagonal_W_soldada_columna_HSS.scp` | diagonal W soldada con cartela soldada a una columna tubular HSS | Cartela con miembro soldado | 0 / 0 | 0.48 |  |
| `TP-A08_placa_base_diagonal_HSS_cartela_apoyada.scp` | placa base: diagonal HSS con cartela atornillada soldada a la columna y apoyada y soldada sobre la placa base | Cartela atornillada; Placa base | 0 / 0 | 0.75 |  |
| `TP-A09_placa_base_diagonal_W_soldada_alma.scp` | placa base: diagonal W soldada con cartela contra el alma de la columna y apoyada en la placa base | Cartela con miembro soldado; Placa base | 0 / 0 | 0.75 |  |
| `TP-A10_placa_base_dos_diagonales_V.scp` | placa base con dos diagonales en V (una a cada ala, cartelas apoyadas en la placa) | Cartela atornillada; Placa base | 0 / 0 | 0.75 |  |
| `TP-A11_cartela_esquina_bajo_viga.scp` | cartela de esquina bajo la viga: soldada al ala inferior de la viga y al ala de la columna a la vez (diagonal hacia abajo) | Cartela atornillada; Placa simple | 0 / 0 | 0.80 |  |
| `TP-A12_cartela_esquina_sobre_viga_soldada.scp` | cartela de esquina sobre la viga: soldada al ala superior de la viga y al ala de la columna (diagonal hacia arriba, soldada) | Cartela con miembro soldado; Placa simple | 0 / 0 | 0.80 |  |
| `TP-A13_chevron_sobre_viga_HSS.scp` | chevron (V invertida) sobre una viga: dos diagonales HSS con una cartela común soldada al ala superior | Cartela atornillada | 0 / 0 | 0.51 |  |
| `TP-A14_chevron_bajo_viga_W.scp` | chevron (V) bajo una viga: dos diagonales W con cartela común soldada al ala inferior | Cartela atornillada | 0 / 0 | 0.43 |  |
| `TP-A15_arriostramiento_K_columna_W.scp` | arriostramiento en K: dos diagonales HSS (una sube y otra baja) con cartela común contra el ala de la columna | Cartela atornillada | 0 / 0 | 0.51 |  |
| `TP-A16_arriostramiento_X_columna_intermedia.scp` | arriostramiento en X en una columna intermedia: cuatro diagonales (dos cartelas, una a cada lado de la columna) | Cartela atornillada | 0 / 0 | 0.13 |  |
| `TP-A17_arriostramiento_K_soldado_columna_HSS.scp` | arriostramiento en K soldado sobre una columna tubular HSS | Cartela con miembro soldado | 0 / 0 | 0.51 |  |
| `TP-A18_armadura_Warren_cordon_HSS.scp` | nudo de armadura Warren en el cordón superior HSS: dos diagonales HSS con cartela común bajo el cordón | Cartela atornillada | 0 / 0 | 0.38 |  |
| `TP-A19_armadura_Pratt_soldada.scp` | nudo de armadura Pratt: diagonal y montante HSS soldados a una cartela soldada bajo el cordón superior | Cartela con miembro soldado | 0 / 0 | 0.38 |  |
| `TP-A20_armadura_cordon_inferior.scp` | nudo del cordón inferior: dos diagonales y un montante HSS hacia arriba con cartela común sobre el cordón | Cartela atornillada | 0 / 0 | 0.38 |  |
| `TP-A21_armadura_cordon_W.scp` | nudo de armadura con cordón de perfil W: dos diagonales HSS con cartela soldada al ala inferior del cordón | Cartela atornillada | 0 / 0 | 0.38 |  |
| `TP-A22_armadura_X_cordon_HSS.scp` | nudo en X sobre un cordón: cuatro diagonales (dos cartelas, una por cada cara del cordón) | Cartela atornillada | 0 / 0 | 0.32 |  |
| `TP-A23_cartela_medidas_editadas.scp` | cartela con medidas editadas (largo 24, base 16, punta 9) y esquinas cortadas, diagonal HSS atornillada | Cartela atornillada | 0 / 0 | 0.45 |  |
| `TP-A24_diagonal_esviada_30.scp` | diagonal en un plano esviado (30°) respecto de las caras de la columna: la cartela se corta en bisel contra el ala | Cartela atornillada | 0 / 0 | 0.45 |  |
| `TP-A25_diagonal_desplazada_sobre_columna.scp` | diagonal con su eje desplazado 3 in a un lado del eje de la columna (llega excéntrica sobre el ala) | Cartela atornillada | 0 / 0 | 0.45 |  |
| `TP-A26_tipologia_plato_base.scp` | tipología «Plato base»: columna sobre placa base con dos diagonales | Cartela atornillada; Placa base | 0 / 0 | 0.87 |  |
| `TP-A27_tipologia_plato_base_4_diagonales.scp` | tipología «Plato base» con cuatro diagonales (una en cada cara de la columna) | Cartela atornillada; Placa base | 0 / 0 | 0.75 |  |
| `TP-A28_tipologia_columna_intermedia.scp` | tipología «Columna intermedia»: cuatro diagonales (dos por lado) | Cartela atornillada | 0 / 0 | 0.13 |  |
| `TP-A29_tipologia_columna_superior.scp` | tipología «Columna superior»: la columna termina en el nudo con dos diagonales hacia abajo | Cartela atornillada | 0 / 0 | 0.13 |  |
| `TP-A30_tipologia_nudo_vigas.scp` | tipología «Nudo de vigas»: viga principal inclinada con dos miembros que la cruzan | Cartela atornillada | 0 / 0 | 0.09 |  |

## Tipologías no soportadas / limitaciones
- Diagonales que se cruzan entre sí en el centro de un vano (X con cartela central): no hay cartela de cruce; se modela con un nudo en cada extremo.
- Cartela de esquina contra viga y columna: la viga apoya en la cartela por su ala (la cartela queda bajo/sobre el ala); si la diagonal cruza la viga hay que usar `gap` del miembro.
- La placa base no es una pieza: el revisor omite sus cordones; `selftest_geo_cartelas.py` los comprueba contra la cara superior expuesta en `mdl.elems['Placa base']`.
- Ángulos como diagonales: el tipo de sección ángulo no tiene cartela propia.
