<p align="center"><img src="steelconpro/data/logo.png" width="420" alt="SteelConPro"></p>

# SteelConPro 1.1

Diseño y verificación de **conexiones de acero**: placas base de columna (perfiles **W, HSS cuadrado/rectangular, HSS circular y Pipe**, anclajes ACI 318-19,
llave de corte, rigidizadores, soldadura), conexiones de corte (placa simple, doble ángulo, asiento), empalmes de viga y de columna, placa extrema a
momento, cartelas de arriostramiento, nudos HSS a HSS, RBS (AISC 358) y empalmes de puente con pernos pretensados. Todas con dibujo paramétrico, **vista 3D**
y **análisis de elementos finitos** sólido (Gmsh + CalculiX) además del cálculo cerrado.

Normas: **AISC 360-22**, **AISC Design Guide 1 (2ª Ed.)**, **ACI 318-19 Cap. 17**; para las conexiones: AISC Manual 15ª Ed., AISC 358-16, AISC 341-22, AASHTO LRFD y RCSC.

> **Cambio de nombre (1.1).** El programa antes tenía otro nombre y otra numeración de versiones; la de SteelConPro empieza en 1.1. Los proyectos se guardan ahora como `.scp`; los archivos `.pbase` y el formato de libro de las
> versiones anteriores se siguen abriendo (al guardar quedan como `.scp`), y los materiales y perfiles importados de la carpeta de datos anterior se copian solos a la
> carpeta `SteelConPro` la primera vez que se abre el programa.

**Unidades configurables**: longitud en in / ft / mm / cm / m, fuerza en kip / lbf /
kN / N / tonf / kgf, momento y esfuerzo por separado. Se aplican a las entradas, a la
tabla de resultados y a los reportes. El cálculo interno siempre corre en in-kip-ksi,
que son las unidades nativas de AISC v14 y de los pernos en pulgadas.

Los proyectos nuevos arrancan en **mm, kN, MPa, kN·m** (se cambia en la pestaña Proyecto; los archivos guardados conservan sus unidades).

## Modelo 3D y análisis FEM de todas las conexiones

- **Nuevo nombre y nuevo logo** (`tools/make_logo.py` los regenera). Los proyectos se guardan como `.scp`; los `.pbase` anteriores se siguen abriendo.
- **Pestaña «Modelo 3D»** en las diez tipologías de conexión (placa de corte, doble ángulo, asiento, empalmes de viga y de columna, placa extrema, cartela,
  HSS a HSS, RBS y puente): vigas, columnas, placas, ángulos, rigidizadores, pernos con cabeza y tuerca, cordones y las flechas de la combinación que gobierna.
  Se gira con el ratón (OpenGL; sin OpenGL se usa matplotlib).
- **Análisis de elementos finitos sólido (Gmsh + CalculiX) igual que el de la placa base**: `CALCULAR (F8)` corre cada combinación de carga y agrega sus
  verificaciones a las del cálculo cerrado; la pestaña **«Análisis FEM»** muestra von Mises, desplazamiento, deformada amplificable y deformación plástica por
  pieza o del conjunto, con las tablas de **pernos** (cortante y tracción, D/C) y de **cordones** (esfuerzo en la garganta, pico y media). Los PDF/Word llevan un
  *Anexo C* con las imágenes y las tablas. `SteelConPro.exe archivo.scp --3d carpeta` hace lo mismo por lotes; *Exportar > Modelo sólido 3D* escribe un `.step`.

**Cómo se modela** (`steelconpro/conn/fem/`; unidades in, kip, ksi):

| Elemento | Modelo |
|---|---|
| Piezas | tetraedros cuadráticos (C3D10), un cuerpo por pieza; acero elasto-plástico perfecto con límite **φ·Fy** (0.9·Fy); RBS: viga con endurecimiento (Ry·Fy → Cpr·Ry·Fy) y columna con Fy |
| Pernos | el borde de cada agujero (y la corona de cabeza y tuerca) es un cuerpo rígido (ecuaciones lineales de pequeños giros, no el *RIGID BODY* de CalculiX, que hacía divergir el paso plástico); entre los de piezas consecutivas actúan resortes de cortante (en las dos direcciones del plano) y, entre cabeza y tuerca, un resorte axial **solo a tracción**. La fuerza del perno sale de los resortes: se compara con φ·Fnv·Ab por plano de corte y con φ·F'nt·Ab (J3.7) |
| Cordones de filete | prismas triangulares unidos a las dos piezas; se lee el esfuerzo resultante en el plano de la garganta (nodos libres del cordón) y se compara con φ·0.60·FEXX: **D/C = máx(pico / 1.5, media)** (el cordón es elástico: el pico de los extremos es singular) |
| Contacto | resortes solo-compresión entre nodos gemelos de las superficies que se tocan (penalización); se resuelve con un **conjunto activo** de problemas lineales (cada iteración es una corrida de CalculiX) |
| Apoyos y cargas | extremos de columnas, vigas o perfiles empotrados; las fuerzas y momentos de la combinación actúan sobre una cara rígida en el punto de aplicación del cálculo cerrado (p. ej. la reacción en la cara del soporte). En el asiento la viga solo apoya (sin fricción): se fijan el deslizamiento y el giro en planta del extremo cargado para que no quede un modo de cuerpo rígido |
| Plasticidad | se verifica la **deformación plástica equivalente** promediada (límite del proyecto, 5 %); si el análisis plástico no converge antes de la carga de diseño se informa «capacidad = x % de la carga» con D/C = 1/x |

Si ninguna pieza se acerca a la fluencia (von Mises promediado < 0.8·φ·Fy) la pasada plástica se omite: el elástico ya es la solución (queda indicado en la pestaña FEM). La malla automática es algo más gruesa que la «Fina»; los cordones se mallan más fino.

Tiempo típico por combinación (4 núcleos, malla *Automática*): HSS ≈ 15 s; placa de corte, doble ángulo, asiento y placa extrema, de 1.5 a 4 min; cartela, empalmes y puente, de 3 a 6 min; RBS (plástica con endurecimiento) ≈ 6 min. Con la malla *Fina* o muchos contactos puede pasar de 10 min.

**Lo que este análisis NO hace** (y por qué conviene leer sus resultados con criterio):
- **Pernos**: sin plastificación, fractura ni pretensión. Los empalmes de puente con pernos pretensados se analizan como pernos de aplastamiento (el deslizamiento crítico sólo
  está en el cálculo cerrado). La rigidez al cortante del perno (3500·d² kip/in) es un valor de modelo, no medido.
- **Soldaduras**: los cordones de filete de la placa de corte, doble ángulo, asiento y cartela se modelan; en la placa extrema, los nudos HSS y la unión viga-columna de la cartela y de la RBS
  la unión es continua (equivale a penetración completa) y no se verifica el cordón.
- **Contacto sin fricción** y sin preapretado; las partes rígidas de los agujeros ocultan la concentración de esfuerzos en el borde (el aplastamiento se verifica en el cálculo cerrado).
- **Pandeo** (local o global) y grandes desplazamientos: análisis de pequeños desplazamientos.
- RBS: la plastificación de la viga en la zona reducida es lo buscado y no se verifica; se verifican la columna, las placas de continuidad y la zona del panel.
- Los resultados del 3D no sustituyen las verificaciones de la norma: se agregan a ellas. Fueron contrastados con cálculos manuales (reparto elástico de la placa de corte,
  tracción de la placa extrema, equilibrio), **no con ejemplos publicados ni con otro programa**; revíselos antes de usarlos en un proyecto.

## Tipologías de conexión

Cada conexión del proyecto tiene una **tipología** (Proyecto > Tipología, o el diálogo del botón *Nueva*). Un mismo archivo `.scp`
puede mezclarlas; los archivos de placa base de versiones anteriores se abren como placa base. Todas las tipologías se calculan en **forma cerrada** (el modelo 3D y el análisis FEM, descritos arriba, se suman a ese cálculo),
con varias combinaciones de carga (gobierna la peor), tabla de verificaciones D/C, dibujo con cotas, memoria detallada y PDF/Word, y se pueden
correr por lotes (`run.py libro.scp --pdf memoria.pdf`).

| Tipología | Pestaña | Norma | Qué verifica |
|---|---|---|---|
| Placa base de columna | (las de siempre) | AISC DG1, ACI 318-19 cap. 17 | como siempre; con análisis 3D (Gmsh + CalculiX) |
| **Placa de corte (shear tab)** | Conexión de corte | AISC 360-22, Manual 15ª Parte 7, 9, 10 | viga secundaria a viga maestra (con cope), viga a alma o ala de columna |
| **Doble ángulo** | Doble angulo | AISC 360-22, Manual Parte 10 | atornillado o atornillado-soldado al soporte; viga a viga o a columna |
| **Asiento (seated)** | Asiento | AISC 360-22, Manual Parte 10 | sin rigidizar (ángulo) o rigidizado (ménsula) |
| **Empalme de viga** | Empalme de viga | AISC 360-22 cap. D, J | placas de ala y de alma atornilladas; momento, cortante y axial |
| **Empalme de columna** | Empalme de columna | AISC 360-22 cap. D, J | igual, con contacto de extremos opcional (J1.4(a)) |
| **Placa extrema a momento** | Placa extrema | AISC 360-22, Manual Parte 9 | a ras o extendida; filas de pernos con efecto palanca, lado de la columna |
| **Cartela de arriostramiento** | Cartela | AISC Manual Parte 13 | Whitmore, bloque de cortante, Thornton, UFM sin momentos |
| **HSS a HSS (celosía)** | HSS a HSS | AISC 360-22 cap. K | nudos T, Y, X y K con separación (redondos); T, Y, X (rectangulares) |
| **RBS precalificada** | AISC 358 RBS | AISC 358-16 cap. 5, AISC 341 | Mpr, Mf en la cara, zona del panel, columna fuerte-viga débil |
| **Puente pretensado** | Puente pretensado | AASHTO LRFD 6.13, RCSC | empalme de ala con pernos A325/A490 de deslizamiento crítico |

Cargas: cada tipología tiene su tabla de combinaciones, con las columnas que le corresponden: Vu (placa de corte, doble ángulo), R (asiento), Mu, Vu, Nu
(empalme de viga), Pu, Mu, Vu (empalme de columna), Mu, Vu (placa extrema), P del arriostramiento (cartela), P de cada diagonal (HSS), Vg y Puc (RBS)
y la fuerza del ala en Resistencia y en Servicio II (puente). Una nota sobre la tabla explica la convención de signos y de qué combinación se trata.

### Placa de corte (shear tab)

Cubre la **viga secundaria apoyada en el alma de una viga maestra** (con cope superior y/o inferior), la viga apoyada
en el alma de una columna y en el ala de una columna. Una fila vertical de 2 a 12 pernos en agujeros estándar, placa soldada al soporte con filete
a ambos lados. Se verifica, por cada reacción factorizada Vu (varias combinaciones; gobierna la peor):

- **Pernos**: cortante con excentricidad por el método del centro instantáneo (AISC Manual Parte 7; curva de Crawford y Kulak, Δmax = 0.34 in;
  e = a, la distancia de la soldadura a la fila de pernos); se informa también el coeficiente del método elástico. Aplastamiento y desgarramiento
  (J3.10) por perno en la placa y en el alma, con la componente vertical y la horizontal de la fuerza de cada perno según el centro instantáneo.
- **Placa**: fluencia y rotura por cortante (J4.2), bloque de cortante (J4.3), flexión en la soldadura (F11), interacción flexión-cortante
  (criterio plástico del programa, conservador) y rotura por flexión en la sección neta.
- **Soldadura** placa-soporte (J2.4, método elástico con incremento direccional opcional), cortante del **metal base del soporte** (equivale a
  la Ec. 9-2 del Manual), tamaño mínimo y máximo del filete.
- **Viga apoyada**: fluencia por cortante y rotura por cortante neto del alma, **bloque de cortante** con cope superior, **flexión de la sección
  con cope** (Snet de la sección en T, brazo = retranqueo + longitud del cope − a).
- Distancias mínimas (J3.3, J3.4, J2.4) y avisos de la configuración convencional (Tabla 10-9: 2 ≤ n ≤ 12, a ≤ 3.5 in, leh ≥ 2·db, tp ≤ db/2 + 1/16, filete ≈ 5/8·tp).

No hace: pandeo local del alma por cope (*NO EVALUADO*; la 15ª edición cambió el procedimiento), carga axial en la viga, agujeros ranurados, deslizamiento
crítico, configuraciones extendidas (a > 3.5 in), flexión local del ala de la columna ni rigidez del soporte. La excentricidad es la completa (e = a),
sin la reducción que permite la Tabla 10-9: es conservador.

### Doble ángulo, asiento, empalmes

- **Doble ángulo**: los pernos del alma trabajan en doble corte con excentricidad (centro instantáneo); la pierna al soporte se atornilla (dos columnas,
  cortante concentrado) o se suelda (líneas verticales con excentricidad). Aplastamiento y desgarramiento en alma, ángulos y soporte; cortante, rotura y
  bloque de cortante de los ángulos; alma de la viga con cope. *No*: flexión de las piernas, axial, ranuras, deslizamiento crítico, pandeo por cope.
- **Asiento**: la reacción actúa a e = retranqueo + N/2. Viga: fluencia local y aplastamiento del alma (J10.2, J10.3 en el extremo). Ángulo sin rigidizar:
  flexión plástica de la pierna horizontal, cortante, tracción de la pierna vertical, pernos o soldadura al soporte con el momento R·e. Rigidizado: ménsula
  (M, V, interacción plástica) y soldadura de dos líneas. *No*: placa horizontal del asiento rigidizado, ángulo superior, unión del ala inferior,
  pandeo del rigidizador (solo aviso de esbeltez).
- **Empalme de viga / columna**: el momento lo toman las alas (o se reparte según la inercia con el alma); el axial se reparte por áreas. Placas de ala
  exterior e interiores (fluencia, rotura con An ≤ 0.85·Ag, pandeo en compresión), pernos (simple o doble corte, junta larga), aplastamiento, bloque de
  cortante, tracción neta del ala del perfil; alma con método elástico (V con excentricidad, Mw, N). Columna con contacto: la compresión pasa por
  contacto y el empalme se dimensiona para el mayor entre la tracción y el 50 % de la compresión (ala y alma). *No*: pandeo de las placas de alma,
  ranuras, deslizamiento crítico ni la resistencia del perfil fuera del empalme.

### Placa extrema a momento

Cada fila de pernos se trata como una **T equivalente con efecto palanca** (Manual Parte 9): el momento resistente es Mcap = 2·Σ T_i·h_i; el cortante lo
toman los pernos de compresión. Lado de la columna: flexión local del ala (J10.1), fluencia y aplastamiento del alma (J10.2, J10.3) y zona del panel
(J10.6); con placas de continuidad se omiten las tres primeras. **Atención: no es el procedimiento de líneas de fluencia de AISC DG4**
(Murray y Sumner), que no se pudo consultar: es una aproximación conservadora que puede diferir de DG4. *No*: rigidizadores de placa (4ES, 8ES),
flexión del ala de la columna por líneas de fluencia (*NO EVALUADO*).

### Cartela de arriostramiento

Método de fuerza uniforme (UFM, Manual Parte 13) en la esquina viga-columna, caso sin momentos: tanθ = (α + ec)/(β + eb); fuerzas de interfaz
H_b, V_b, H_c, V_c. Se verifican la unión del arriostramiento (pernos con método elástico o soldadura), la sección de **Whitmore** (fluencia y rotura en
tracción; pandeo con K = 0.65 y L_avg, Thornton, en compresión), el bloque de cortante, las soldaduras e interfaces y los efectos locales en viga y
columna (J10.1, J10.2, J10.3). Si la geometría no cumple la condición del UFM se avisa (fatal si la diferencia pasa de 10 %). *No*: el
arriostramiento como miembro, el borde libre de la cartela (Dowswell), la conexión viga-columna bajo las fuerzas de la cartela.

### HSS a HSS

AISC 360-22 cap. K: tabla K3.1 (redondos T, Y, X y K con separación: plastificación del cordón y punzonamiento) y tabla K3.2A (rectangulares T, Y, X con
β ≤ 0.85). Los límites de validez (β, D/t, θ ≥ 30°, Fy ≤ 52 ksi, Fy/Fu ≤ 0.8, g ≥ tb1 + tb2) son avisos críticos: fuera de ellos las ecuaciones no
aplican y el veredicto no es válido. *No*: nudos rectangulares K/N con separación (aviso fatal «no implementado»), β > 0.85, cortante del cordón en la
separación, el miembro diagonal, la soldadura diagonal-cordón ni la excentricidad del nudo.

### RBS (AISC 358-16)

Procedimiento de diseño por demanda del cap. 5: Z_RBS, Mpr = Cpr·Ry·Fy·Z_RBS, s_h = a + b/2, V_RBS = 2·Mpr/L_h + Vg, Mf = Mpr + V_RBS·s_h ≤ φd·Mpe; límites de
a, b, c; límites de precalificación de viga y columna; compacidad sísmica (AISC 341 Tabla D1.1); zona del panel; columna fuerte-viga débil
(AISC 341 E3.4a) y criterio de placas de continuidad. **Solo la RBS**: las demás conexiones precalificadas de AISC 358 (WUF-W, BFP, placas extremas
precalificadas, Kaiser, ConXtech, SidePlate...) **no** están. *No*: la soldadura CJP viga-columna ni el arriostramiento lateral en la RBS.

### Puente: empalme con pernos pretensados (AASHTO)

«Conexiones de puente con pretensado» se interpretó como el **empalme atornillado de ala de viga de puente con pernos de alta resistencia pretensados de
deslizamiento crítico** (AASHTO LRFD 6.13, RCSC): una placa exterior y dos interiores. Servicio II: Rn = Kh·Ks·Ns·Pt (Ks: clase A 0.30, B 0.50, C 0.30; Kh:
1.0 / 0.85 / 0.70; Pt según RCSC Tabla 8.1). Resistencia: cortante (0.56 o 0.48·Ab·Fub·Ns, φs = 0.80, ×0.80 si la junta pasa de 38 in), aplastamiento, fluencia y
fractura del ala y de las placas, bloque de cortante, distancias. La fuerza de diseño del ala se ingresa ya calculada (AASHTO 6.13.6.1.4). *No*: fatiga,
empalme del alma, pandeo de las placas en compresión, fuerza mínima de diseño del ala. Si lo que se buscaba era **postensado** (cables o barras en
hormigón pretensado), esa tipología **no** está.

### Lo que hay que saber antes de confiar en los resultados

- Las ecuaciones, tablas (J3.2–J3.4, K3.1/K3.2A, Ks/Kh y pretensiones de pernos) y procedimientos se transcribieron **de memoria, sin acceso a las
  publicaciones primarias** (AISC, AASHTO, RCSC, Manual 15ª, DG4). Las pruebas (`selftest.py`) las comparan contra cálculos manuales independientes
  y contra otros métodos numéricos (centro instantáneo y efecto palanca resueltos con *brentq*), **no contra tablas o ejemplos publicados**. Revíselos
  contra la edición vigente antes de usarlos en un proyecto.
- Lo que cada tipología no evalúa aparece en la tabla como *NO EVALUADO* (sin D/C) y en los avisos de la memoria.
- Un aviso que empieza con `**` (geometría imposible, tipo de nudo no implementado, fuera del rango de validez) invalida el veredicto: el resultado
  no dirá CUMPLE.
- Las conexiones cerradas no pasan por el FEM 3D: el veredicto es el del cálculo cerrado.
- Es una herramienta de verificación; la responsabilidad del diseño es del ingeniero.

**Modo por lotes.** `SteelConPro.exe proyecto.scp --pdf ...` lee el libro tal como lo guarda la interfaz y calcula **todas** sus conexiones (con varias, el nombre de
la conexión se agrega a los archivos de salida).

**Para agregar otra tipología:** su dataclass en `steelconpro/conn/specs.py` (con su constante `CT_*` en `CONN_TYPES`); un campo en `Project`
(`model.py`, y en `_used_extras` si usa perfiles o aceros propios); un módulo en `steelconpro/conn/` con `NAME`, `ATTR`, `TAB`, `PREFIX`, `TITLE`, `NORMS`,
`LOADS`, `LOADS_NOTE`, `FORM` (formulario declarativo con `formspec.py`), `solve(prj, detail) -> Results` (usa `base.run_combos` y `common.py`: centro
instantáneo, bloque de cortante, soldadura, efecto palanca...), `draw(fig, prj)`, `input_rows` y `label`, registrado en `conn/__init__.py`. La interfaz, el
dibujo, las memorias PDF/Word y el modo por lotes lo toman solos; `selftest.py` recorre todas las tipologías registradas con una prueba de fuzz.

## 1. Usar y compartir

**Si recibio `SteelConPro_portable.zip`:** descomprimalo donde quiera y abra
`SteelConPro\SteelConPro.exe`. No hay que instalar nada: Gmsh va dentro del
programa y CalculiX en `solvers\calculix`. No separe el `.exe` de su carpeta.

**Para compilarlo desde este codigo fuente (Windows):**

1. Tenga **Python 3.10 o superior** instalado.
2. Doble clic en **`build_portable.bat`**.

El script crea un entorno virtual, instala las dependencias (incluida la libreria
de Gmsh), corre las autopruebas, compila, copia `solvers\` y deja:

- `dist\SteelConPro\SteelConPro.exe` — el programa listo para usar.
- `SteelConPro_portable.zip` — la misma carpeta comprimida, para compartir.

`ejecutar_sin_compilar.bat` corre la aplicacion directamente con Python, util
mientras se prueba.

### Uso por línea de comandos

```
SteelConPro.exe                                      interfaz gráfica
SteelConPro.exe --selftest                           autopruebas del motor
SteelConPro.exe PB-01.scp --pdf m.pdf --docx m.docx --inp m.inp
```

En modo lote devuelve código de salida 0 si cumple y 2 si no cumple, así que se
puede encadenar en un script para verificar muchas placas de golpe.

---

## 2. Lo que se pidió, y dónde está

### 2.1 Catálogo AISC 14

Pestaña **Perfil**. Selector de tipo (W / HSS rect. / HSS circular / Pipe) y luego
el perfil, ordenados por dimensiones. Debajo se muestran d, bf, tf, tw, A y el
origen del dato.

La tabla **integrada** es un subconjunto del Manual AISC 14ª Ed. con los perfiles
de uso más frecuente (249: W4 a W24, HSS cuadrados y rectangulares, HSS circulares
y Pipe STD/XS). **Para el catálogo completo y verificado**, use
`Archivo > Importar base de datos AISC v14.1...` y seleccione el archivo oficial
`aisc-shapes-database-v14.1.xlsx`. El importador reconoce las columnas nativas de
ese archivo (`Type`, `AISC_Manual_Label`, `d`, `bf`, `tf`, `tw`, `Ht`, `B`, `tdes`,
`OD`, `A`, `Ix`, `Sx`, `Zx`, …), guarda el resultado en
`%APPDATA%\SteelConPro\shapes.json` y los perfiles importados sustituyen a los
integrados. Hágalo una vez; queda permanente.

### 2.2 Pernos en pulgadas y base de materiales

Pestaña **Pernos**. Diámetros de 1/2" a 3" con `Ase` de rosca UNC (ASME B1.1),
diámetro de agujero según AISC Manual Tabla 14-2, ancho de tuerca hexagonal pesada
(ASME B18.2.2) y `Abrg` calculado como hexágono menos agujero — editable si usa
placa de anclaje en vez de tuerca.

Materiales de anclaje: F1554 Gr.36 / 55 / 105, A307 Gr.C, A36, F3125 Gr.A325
(dos rangos de diámetro) y Gr.A490, A449 (dos rangos), A193 B7, A354 BD. Cada uno
lleva su marca de ductilidad, que es la que decide el φ de ACI Tabla 17.5.3(a).

También hay catálogos de acero de placa (A36, A572 Gr.50/55/60/65, A588, A709,
A514), de perfil (A992, A500 B/C rect. y red., A53, A1085) y de electrodos
(E60XX a E110XX).

### 2.3 Rotación del perfil y pernos por eje

Pestaña **Perfil → Rotación**: cualquier ángulo. 0° = eje fuerte paralelo a N (Y);
90° = eje débil. Con ángulos distintos de 0/90 las fórmulas cerradas de DG1 usan
el rectángulo envolvente del perfil girado (conservador) y lo avisa; el modelo de
elementos finitos sí usa la geometría real girada.

Pestaña **Pernos → Disposición**: `Pernos en eje MAYOR` y `Pernos en eje MENOR`
son independientes. Patrones:

| Patrón | Total de pernos |
|---|---|
| Perimetral (4 lados) | 2·mayor + 2·menor − 4 |
| 2 lados (eje mayor) | 2·mayor |
| 2 lados (eje menor) | 2·menor |
| Circular | el número que indique, equiespaciados |

Distancias al borde `ex` y `ey` independientes. El programa avisa si algún perno
queda dentro del perfil o sin holgura para la tuerca y la llave.

### 2.4 Llave de corte

Pestaña **Llave de corte**. Orientación en X, en Y o en ambos ejes, con W, H, t,
acero, filete y electrodo. Al activarla, **el cortante se reasigna a la llave** y
deja de exigirse a los pernos (se anulan las verificaciones de cortante del
anclaje, como corresponde). Se verifica:

- aplastamiento del concreto contra la llave (ACI 318-19 17.11.2.1, descontando
  el espesor del mortero de la altura embebida);
- flexión y cortante de la pletina;
- soldadura de la llave a la placa (doble filete, V y M combinados);
- desprendimiento del concreto delante de la llave (17.11.2.2 → 17.7.2).

### 2.5 Tipo de anclaje

Pestaña **Pernos → Tipo de anclaje**: con cabeza hexagonal pesada, gancho en L,
gancho en J, o recto. Cambia el dibujo en elevación y la resistencia a extracción:

- **Con cabeza** → `Np = 8·Abrg·f'c` (ACI 17.6.3.2.2a), más verificación de
  desprendimiento lateral si `ca_min < 0.4·hef`.
- **Gancho L/J** → `Np = 0.9·f'c·eh·da` (17.6.3.2.2b), con `eh` limitado a
  3·db ≤ eh ≤ 4.5·db.
- **Recto** → ACI no le reconoce resistencia a extracción. Si hay tracción, el
  programa lo marca como aviso crítico y la verificación sale reprobada, que es
  el comportamiento correcto.

### 2.6 Soldadura

Pestaña **Soldadura**, con definiciones separadas para **alas**, **alma** y
**perímetro** (HSS/Pipe). Cada una: tipo (filete / CJP / PJP / sin soldadura),
tamaño, electrodo y si va a uno o ambos lados.

- CJP con metal de aporte compatible → resistencia = metal base (AISC J2.4); no se
  calcula el depósito, se reporta así.
- Filete y PJP → `φRn = 0.75·0.60·FEXX·garganta·L`, con el incremento direccional
  `(1 + 0.5·sin^1.5 θ)` de la Ec. J2-5 activable. Se verifica también el metal
  base adyacente y el tamaño mínimo de filete de la Tabla J2.4.
- Demanda: las alas toman la fuerza normal del ala (de Mux, Muy y Pu) más su parte
  del cortante; el alma toma el cortante en su plano. En HSS, la soldadura
  perimetral toma todo.

### 2.7 Elementos finitos

Pestaña **Elementos finitos** (opciones) y pestaña **Modelo 3D** (analisis y resultados). El programa tiene
un solo analisis de elementos finitos: el **modelo SOLIDO 3D**, dentro del programa (boton *Ejecutar
analisis 3D* o `Cálculo > Análisis SÓLIDO 3D`, F8). Escribe un `.geo` con kernel OpenCASCADE que construye

- la placa base con los **agujeros taladrados** como cilindros restados,
- el perfil extruido como sólido con el espesor real de sus paredes y alas,
- las pletinas rigidizadoras con su forma (triangular, recortada, etc.),
- la llave de corte por debajo de la placa,

todo fusionado con `BooleanFragments` para obtener una malla conforme. Despues de mallar, la union
perfil-placa se modela con **conectores** entre cuerpos separados (`steelconpro/weldfe.py`: contacto solo-compresion en la huella y, en cada linea soldada, un resorte normal solo-traccion y dos de cortante); el modelo
"Fusionado" (union monolitica equivalente a CJP) queda como opcion.

El programa encadena todo el proceso en segundo plano, sin congelar la ventana: malla con Gmsh en
tetraedros de segundo orden, localiza por coordenadas los nodos del apoyo, del tope y de cada anillo de
perno, escribe el `.inp` de CalculiX con el concreto como resortes de Winkler **solo a compresion**
(rigidez `ks` por area tributaria de cada nodo), los pernos como resortes **solo a traccion** en el anillo
de la tuerca (mas los horizontales que equilibran el cortante), el contacto y los conectores del cordon,
y las cargas P-M-V en un nodo de referencia; lo resuelve, y lee el `.frd` para dibujar el resultado.
Puede alternar entre von Mises, |U| y Uz, y amplificar la deformada.

Salidas: la **tabla de traccion por perno** (posicion, D/C frente a AISC J3), la tabla
de **soldadura por zona** (pico y media, con la capacidad AISC J2.4), la presion de contacto, el von Mises
promediado y el residuo de equilibrio (reaccion del concreto − pernos − Pu). Todas entran al veredicto
como filas `fem_*` y a la memoria (secciones 6 y 7, con la placa aislada en planta).

Junto al `.geo` se deja tambien **`correr_3d.py`** por si prefiere lanzarlo fuera de la aplicacion, y todos
los archivos quedan en la carpeta del proyecto, listos para abrir en PrePoMax o CGX. Gmsh y CalculiX vienen
incluidos; indique otras rutas en la pestaña Elementos finitos si quiere.

Una advertencia de lectura: los picos de von Mises PUNTUALES en aristas vivas — borde del agujero,
encuentro perfil-placa — son **singularidades de malla**: crecen al refinar y no deben interpretarse como
esfuerzo real. Por eso se verifica el von Mises promediado, y lo confiable del 3D es la distribucion
global, la deformada y el equilibrio.

### 2.8 Rigidizadores de pletina

Pestaña **Rigidizadores**. Posición en las alas, en el alma, en ambos, o en las
cuatro caras de un HSS. Cantidad, proyección L, altura h, espesor t, acero, filete
y electrodo. Las pletinas **giran con el perfil** y se recortan automáticamente al
contorno de la placa.

Efecto en el cálculo cerrado: el voladizo efectivo pasa a
`m_ef = máx(m − L, mín(m, s/2))`, donde `s` es la separación entre pletinas en esa
cara — pletinas muy separadas casi no reducen el voladizo, igual que muestra el FEA.

Verificaciones: que la proyección quepa en la placa, esbeltez `h/t ≤ 0.56√(E/Fy)`,
flexión y cortante de la pletina, soldadura **a la placa** (flujo de cortante) y
soldadura **a la columna** (V y M) — que son trayectorias de carga distintas y se
verifican por separado.

---

## 3. Lista completa de verificaciones

| Grupo | Verificación | Referencia |
|---|---|---|
| Placa | Aplastamiento del concreto, casos 1 y 2 | AISC J8, DG1 §3.3 |
| Placa | Espesor requerido (m, n, λn' y voladizo traccionado) | DG1 §3.1 y §3.3 |
| Perno | Tracción, cortante e interacción | AISC J3, Ec. J3-3a |
| Anclaje | Acero en tracción | ACI 17.6.1 |
| Anclaje | Arrancamiento del concreto en tracción (grupo) | ACI 17.6.2 |
| Anclaje | Extracción — pullout (cabeza o gancho) | ACI 17.6.3 |
| Anclaje | Desprendimiento lateral, si `ca_min < 0.4·hef` | ACI 17.6.4 |
| Anclaje | Acero en cortante (con factor 0.80 por mortero) | ACI 17.7.1 |
| Anclaje | Arrancamiento del concreto en cortante | ACI 17.7.2 |
| Anclaje | Pryout | ACI 17.7.3 |
| Anclaje | Interacción tracción-cortante | ACI 17.8 |
| Detallado | Distancia del perno al borde | AISC Tabla 14-2 / J3.4 |
| Soldadura | Ala, alma o perímetro; depósito y metal base; tamaño mínimo | AISC J2.4, Tabla J2.4 |
| Llave | Aplastamiento, flexión, cortante, soldadura, breakout | ACI 17.11, AISC F11/J2 |
| Rigidizador | Geometría, esbeltez, flexión, cortante, dos soldaduras | AISC B4.1a, F11, J2 |
| Perfil | Esfuerzo normal combinado y cortante en la base | AISC H1, G2 |
| FEM 3D | tracción máxima por perno, presión de contacto, von Mises promediado en la placa, soldadura por zona | AISC J3.6, J8, J2.4 / criterio del programa |

Opciones globales: concreto fisurado/no fisurado, condición A/B de refuerzo
suplementario, diseño sísmico (factor 0.75 de ACI 17.10.5.2), concreto liviano λa,
y descuento de la fricción placa-mortero del cortante en pernos.

---

## 3.bis  Memoria detallada (el "modo CalcPad")

La pestaña **Memoria detallada** muestra el cálculo completo paso a paso. Cada línea
tiene cuatro partes:

```
fp,max = φc·Pp / A1 = 8,651 / 312,257 = 27.70 MPa          [AISC Ec. J8-2]
  símbolo   fórmula     sustitución      resultado           referencia
```

No es un texto redactado aparte que pueda quedar desfasado: son los mismos cálculos
los que van registrando sus pasos mientras corren, así que la memoria y los números
de la tabla de verificaciones no pueden divergir. Todo sale en las unidades de
trabajo del proyecto, y las verificaciones aparecen marcadas con su D/C en verde o
rojo dentro de la sección que les corresponde.

Se incluye como anexo en los tres reportes (se puede desactivar con la casilla de la
pestaña) y hay un botón para copiarla al portapapeles.

## 4. Salidas

- **Memoria de cálculo PDF** — generada directamente, sin necesidad de tener Word
  instalado. Mismo contenido que la versión en Word, con la tabla de tensiones por
  perno incluida.
- **Memoria de cálculo Word** — datos de entrada, desarrollo del equilibrio de DG1,
  tabla de verificaciones con los D/C en rojo cuando no cumplen, avisos, resumen
  del modelo 3D (soldadura y pernos), la placa aislada en planta con von Mises de ambas caras, presión de
  contacto y deflexión, y anexo con planta y elevación.
- **Imágenes PNG** sueltas.
- **Modelo 3D para Gmsh/CalculiX** (`.geo` y `correr_3d.py`).
- **Proyecto `.scp`** (JSON legible) para reabrir o correr por lotes.

Todos los reportes salen en el sistema de unidades que haya elegido en la pestaña
Proyecto, incluida la tabla de verificaciones.

---

## 5. Alcance y limitaciones

Léalas antes de firmar nada con esto.

1. **La tabla de perfiles integrada debe verificarse** contra el Manual AISC, o
   mejor, reemplazarse importando la base oficial v14.1. Es un subconjunto
   transcrito, no la base certificada.
2. **Placa circular**: las fórmulas cerradas usan el cuadrado equivalente de igual
   área (`Leq = 0.8862·Dp`). Es una aproximación de diseño; el modelo 3D sí
   modela el contorno circular real.
3. **Rotaciones distintas de 0° y 90°**: las fórmulas de DG1 usan el rectángulo
   envolvente del perfil girado. Conservador, pero conservador.
4. **Momento biaxial**: `Muy` entra en el esfuerzo del perfil, en la soldadura y en
   el modelo 3D, pero el equilibrio cerrado de aplastamiento de DG1 es uniaxial (usa
   `Mux`). Con biaxial importante, gobierne por el 3D.
5. `ψec,N` y `ψec,V` de ACI se dejan en 1.0; si la resultante de tracción o el
   cortante son excéntricos respecto al grupo, ajústelos a mano.
6. No se verifica: fatiga, efecto de palanca (*prying*) por flexibilidad de la
   placa, anclajes post-instalados adheridos, ni el refuerzo del pedestal.
7. El modelo 3D es **lineal elástico** con contacto y pernos unilaterales (resortes). No hay
   plasticidad ni pandeo; la rigidez del cordon es una idealizacion.
8. Para diseño sísmico, ACI 17.10 además exige que el anclaje sea gobernado por la
   fluencia dúctil del acero; el programa aplica el 0.75 pero **no** verifica ese
   requisito de jerarquía por usted.

---

## 6. Estructura del código

```
run.py                  punto de entrada (GUI / lote / autopruebas)
selftest.py             45 casos de prueba del motor
steelconpro/
  units.py              sistema de unidades configurable (UnitSet)
  materials.py          aceros, varillas, electrodos, geometría de pernos
  shapes.py             catálogo AISC integrado + importador de la base oficial
  model.py              dataclasses del proyecto, serialización .scp
  geometry.py           contornos, rotación, disposición de pernos, llave,
                        rigidizadores, detección de interferencias
  design.py             aplastamiento, espesor, soldadura, llave, rigidizadores
  anchors.py            ACI 318-19 Cap. 17 y AISC J3
  params3d.py           brazo del cortante, modulo de balasto y rigidez del perno del modelo 3D
  fem_checks.py         verificaciones FEM a partir del 3D (Fem3D, fem_bolt/press/vm/weld)
  mesh3d.py             modelo sólido 3D: .geo de Gmsh, .inp de CalculiX y pipeline
  view3d.py             lectura del .frd, dibujo 3D y von Mises promediado
  plan3d.py             placa aislada en planta (mapas de la memoria)
  rep3d.py              empaqueta el resultado 3D (Fem3D, imagenes) para el veredicto
  weldfe.py             soldadura como conectores entre cuerpos separados
  explain.py            registro de ecuaciones para la memoria detallada
  draw.py               planta, elevación y detalle del rigidizador
  report.py             PDF y DOCX
  weld3d.py             postproceso 3D: pernos, contacto y soldadura (fusionado)
  dialogs.py            seccion personalizada y biblioteca de materiales
  data/aisc_shapes.json catalogo AISC integrado (1,660 perfiles)
  ui.py, ui_widgets.py  interfaz PySide6
ejemplos/               tres proyectos resueltos
```

Para tocar el motor sin abrir la GUI: `python run.py --selftest` corre los casos y
verifica, entre otras cosas, que sin 3D el veredicto sea PENDIENTE y que con 3D (simulado) las fuerzas de
los pernos salgan de el; con `--3d` (o `python selftest.py --3d`) corre ademas el analisis solido de PB-01, la traccion pura
y el respaldo fusionado. `python run.py proyecto.scp --3d carpeta --pdf memoria.pdf` hace el calculo
completo por lotes.

---

## 7. Ejemplos incluidos

| Archivo | Caso | D/C | Gobierna |
|---|---|---|---|
| `PB-01_W14X90.scp` | W14X90, 22×22×2", 8 pernos Ø1¼", llave de corte | 0.750 | distancia al borde |
| `PB-02_HSS12_rigidizada.scp` | HSS12X12X½, 24×24×2", rigidizadores perimetrales, soldadura CJP | 0.949 | esbeltez del rigidizador |
| `PB-03_poste_circular.scp` | Pipe/HSS16 sobre placa circular Ø30", 12 pernos Ø1½" con gancho en J | 1.000 | aplastamiento del concreto |

---

*Los resultados deben ser revisados por un ingeniero responsable. El programa es
una herramienta de cálculo, no un sustituto del criterio profesional.*


## Modelo solido 3D: como se lee la soldadura

Con el modelo de **conectores** (predeterminado) la fuerza del cordon se lee directamente de los resortes
entre el perfil y la placa. Como en la DG1, la compresion se transmite
por contacto y el cordon se verifica a traccion y cortante: f = raiz(max(f_n,0)² + f_l² + f_t²) por unidad
de longitud de cada linea, contra la resistencia del metodo vectorial de AISC J2.4 (con el incremento
direccional si esta activado en la pestaña Soldadura) y, con la suma de las lineas de la pared, contra la
rotura del metal base.

Se reportan dos valores por zona:

- **D/C pico** — el punto mas cargado de la curva suavizada (ventana de 4 veces el cateto). Suele estar donde
  el alma llega al ala o en los extremos: la placa es flexible y la fuerza se concentra ahi.
- **D/C media** — la fuerza de la linea repartida en su longitud, que es lo que supone el calculo de forma
  cerrada.

Con el modelo **fusionado** (respaldo) la union es monolitica y la fuerza se deduce de los esfuerzos del
perfil justo por encima del pie del cordon (franja delgada, integrada en el espesor de la pared):
f_n = t·σzz, f_l = t·τ(z,t), f_t = t·τ(z,n). Ahi los picos incluyen la concentracion de esquina y una
zona sin soldar transmite igual; por eso se prefiere el modelo de conectores.

Verificacion: la reaccion del concreto menos la traccion de los pernos cierra con Pu; con conectores,
ademas, el contacto menos la traccion de los cordones cierra con Pu y la suma del cortante de los cordones
cierra con V.
