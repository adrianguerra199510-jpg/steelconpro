<p align="center"><img src="steelconpro/data/logo.png" width="420" alt="SteelConPro"></p>

# SteelConPro 1.1

Diseño y verificación de **conexiones de acero** con **un solo tipo de conexión**, que se arma por operaciones:

| Elemento | Qué es |
|---|---|
| **Miembros** | cualquier número (columnas, vigas, diagonales; cualquier sección y ángulo); **uno es el principal, que usted designa** (el que recibe a los demás, como el miembro de apoyo de IDEA StatiCa) |
| **Operaciones** | placa simple, doble ángulo, asiento, placa extrema, alas soldadas, cartelas, corte del extremo, placas de continuidad y **placa base** (anclajes ACI 318-19, llave de corte, rigidizadores, soldadura; cálculo cerrado y análisis 3D por elementos finitos sólido con Gmsh + CalculiX), sobre cualquier miembro |
| **Cargas y análisis** | esfuerzos por miembro y caso de carga (y las combinaciones de la placa base), verificación por código (AISC 360-22, AISC DG1, ACI 318), vista 3D, memoria de cálculo; análisis FEM 3D de la placa base |

**No hay un módulo de placa base aparte.** Una placa base es una operación más: se crea una conexión, se agregan los miembros (o solo el principal), y a la columna se le asigna la operación *Placa base*.
Los archivos y plantillas de placa base de las versiones anteriores abren como una conexión de nudo con esa operación (mismos resultados).

No hay «tipologías» de nudo (viga-columna, viga a viga, crucetas): el tipo de nudo lo define lo que usted arma. El nudo se arma **por operaciones**, como en IDEA StatiCa Connection (*Miembros → Operaciones → Cargas → Análisis → Informe*), y se verifican
**por código** con tablas de D/C por operación y memoria de cálculo, como en RAM Connection. La pestaña *Análisis FEM* es el análisis de elementos finitos sólido de la **placa base** (solo se activa si la conexión la lleva; el resto de las operaciones se verifica por código,
sin FEM por ahora). Las tipologías anteriores (placa de corte, doble ángulo, asiento, empalmes, placa extrema, cartela, HSS, RBS y puente) se retiraron como
módulos independientes: ahora son operaciones de la conexión de nudo.

Normas: **AISC 360-22**, **AISC 358/341** donde aplique; placa base: **AISC Design Guide 1 (2ª Ed.)** y **ACI 318-19 Cap. 17**.

> **Cambio de nombre (1.1).** El programa antes tenía otro nombre y otra numeración de versiones; la de SteelConPro empieza en 1.1. Los proyectos se guardan ahora como `.scp`; los archivos `.pbase` y el formato de libro de las
> versiones anteriores se siguen abriendo (al guardar quedan como `.scp`), y los materiales y perfiles importados de la carpeta de datos anterior se copian solos a la
> carpeta `SteelConPro` la primera vez que se abre el programa.

**Unidades configurables**: longitud en in / ft / mm / cm / m, fuerza en kip / lbf /
kN / N / tonf / kgf, momento y esfuerzo por separado. Se aplican a las entradas, a la
tabla de resultados y a los reportes. El cálculo interno siempre corre en in-kip-ksi,
que son las unidades nativas de AISC v14 y de los pernos en pulgadas.

Los proyectos nuevos arrancan en **mm, kN, MPa, kN·m** (se cambia en la pestaña Proyecto; los archivos guardados conservan sus unidades).


## Conexión de nudo y miembro principal

**Nueva conexión** (botón *Nueva*, `Ctrl+Mayús+N`) elige el módulo y el punto de partida. **No hay plantillas predefinidas**: la conexión nueva empieza **en blanco**
(solo el miembro principal; usted agrega los miembros, las operaciones y las cargas) o desde una **plantilla propia**.

**Plantillas propias.** Con la conexión terminada, el botón **Plantilla** (o *Archivo > Guardar la conexión como plantilla*) la guarda con un nombre, una descripción y, en los
nudos, con o sin las cargas. Después aparece en *Nueva conexión*, con vista previa en 3D, y se puede **renombrar o eliminar** desde ahí. Sirve para cualquier módulo
(con placa base o sin ella). Cada plantilla es un archivo `.json` en `%APPDATA%\SteelConPro\plantillas` con la conexión completa y las secciones y materiales propios que usa; se puede
copiar a otra PC. Guardar con el mismo nombre la reemplaza.

Después la conexión se edita en cuatro pasos (pestañas dentro de *Conexión de nudo*):

1. **Miembros**: la tabla lista **todos los miembros del nudo**; el **principal lleva ★** en la primera fila. Al seleccionar una fila se edita ese miembro (*Agregar*,
   *Duplicar*, *Quitar*), con **cualquier sección** del catálogo AISC, de la biblioteca de secciones o dibujada en el Section Designer.
   - **Miembro principal**: nombre, sección, acero, **azimut y elevación de su eje** (90° = vertical, como una columna; 0° = horizontal, como una viga o un cordón; cualquier
     valor intermedio = inclinado), giro, extremo (*continuo* o *termina en el nudo* por el lado + o −) y largos de cada lado.
   - **Miembros conectados**: sección y acero, **azimut**, **elevación**, **posición** sobre el eje del principal (medida desde el nudo), desplazamiento lateral en los dos
     sentidos de la sección del principal, largo, giro y retranqueo. El miembro arranca donde su eje sale de la sección del principal.
   - **★ Designar como principal**: con un miembro conectado seleccionado, ese miembro pasa a ser el principal (sección, acero, eje y giro) y el principal anterior queda como
     miembro conectado (como dos miembros si pasaba por el nudo). **La geometría del nudo no se mueve**: el origen se traslada al punto donde el miembro llegaba y los demás
     miembros conservan su posición (si ya no tocan al nuevo principal, quedan con un retranqueo). Las operaciones y las cargas del miembro designado se descartan, porque eran su
     conexión al principal anterior; el programa lo avisa antes de hacerlo y hay que definirlas de nuevo en los miembros que ahora llegan al principal.
2. **Operaciones**: una lista ordenada que se aplica a los miembros (*Agregar operación*): **placa simple, doble ángulo, asiento, placa extrema a ras o extendida, alas
   soldadas con alma atornillada, cartela atornillada o con miembro soldado, corte del extremo (cope), placas de continuidad y placa base**. Cada operación tiene sus parámetros
   (pernos: diámetro, calidad, número y separación; placas: espesor y acero; filetes; profundidades del corte). A lo sumo una operación de conexión por miembro; el 3D se
   actualiza con cada cambio. Las diagonales que comparten plano comparten una sola cartela.
   **Placa base**: va en el extremo libre de un miembro, el principal (lado − o +) o uno conectado, y solo hay una por conexión. Al agregarla aparece la pestaña **Placa base** con
   sus datos de siempre (*Cargas* con las combinaciones, *Perfil* —giro y descentrado de la columna sobre la placa, inclinación—, *Placa*, *Pernos*, *Llave de corte*,
   *Rigidizadores*, *Soldadura*, *Concreto* y *Elementos finitos*). El perfil es el del miembro que la lleva. La placa queda perpendicular al eje del miembro (la inclinación de la
   columna respecto de la placa se indica en *Perfil*). Si se designa otro miembro como principal, la placa sigue en el mismo extremo libre.
3. **Cargas**: esfuerzos internos de cada miembro junto al nudo (N, Vy, Vz, T, My, Mz) por caso de carga, en los ejes locales del miembro; se verifican todos los casos y
   gobierna el peor.
4. **Análisis**: *Verificar por código* (también el botón **VERIFICAR (F8)**), *Análisis 3D por elementos finitos* (todavía no disponible) e *Informe del nudo* (PDF).

La pestaña **Resultados** muestra los casos de carga, la tabla de verificaciones de cada operación (demanda, capacidad, D/C y referencia AISC; para cada una se informa el
caso que gobierna), los avisos, el veredicto y la memoria de cálculo con el desarrollo de las ecuaciones; si cambia cualquier dato aparece **DESACTUALIZADO** hasta volver a
verificar. **Exportar** escribe la memoria en PDF o Word, y *Modelo sólido 3D* escribe la geometría en **STEP**. En modo por lotes: `python run.py archivo.scp --pdf memoria.pdf`.

**Qué verifica** (AISC 360-22, motores de formulas cerradas): placa simple (pernos con excentricidad por centro instantáneo de rotación, aplastamiento, fluencia, rotura y bloque
de cortante, flexión, soldadura, tamaño de filetes, alma de la viga), doble ángulo, asiento, placa extrema a ras o extendida (columna I por el ala), fuerza del ala en alas
soldadas CJP, y cartelas (pernos, aplastamiento, ancho de Whitmore, bloque de cortante, fluencia y rotura del miembro, soldaduras).

**Qué no verifica** (aparece como *NO EVALUADO*, hay que revisarlo aparte): reparto de fuerzas de la cartela (UFM), pandeo del miembro en compresión, flexión local del ala y
alma de la columna (líneas de fluencia, J10), placas de continuidad, pandeo local del alma por el corte; las operaciones de placa simple, doble ángulo, asiento y placa extrema
con miembros que no son perfiles I; el análisis de una cartela en compresión es simplificado. Los motores suponen miembros perpendiculares al soporte: en miembros esviados
solo se usa el cortante vertical y se avisa del resto.

## Interfaz

Hoja de estilo común refinada (pestañas con acento, grupos con filete, tablas con filas alternas, barras de desplazamiento finas, botones y menús redondeados) en los dos temas.
En los nudos: las **operaciones** llevan un icono de color por grupo (corte, momento, diagonal, modificar el miembro, rigidizar); el paso **Análisis** muestra una lista de
preparación (miembros, operaciones, cargas: lo que está listo, lo que falta y los avisos) y desactiva *Verificar* si falta algo; la pestaña **Resultados** abre con tarjetas de
resumen (veredicto, D/C máximo, qué gobierna, verificaciones y NO EVALUADAS) y una tabla **agrupada por operación** con barras de D/C (verde < 0.80, ámbar hasta 1.00, rojo arriba)
y un filtro (todas / críticas / no cumplen / no evaluadas); clic en una fila lleva a su cálculo en la memoria.

## Biblioteca de secciones y Section Designer

El menú **Secciones** abre la **biblioteca de secciones**: todas las secciones (catálogo AISC, personalizadas por dimensiones y libres), con búsqueda, familias, vista previa y
propiedades (A, centroide, Ix, Iy, Ixy, ejes principales, Sx, Sy, Zx, Zy, rx, ry, J aproximada y peso). Desde cualquier selector de sección de los módulos de nudo, el botón **…**
abre la misma biblioteca para elegir. Con doble clic (o *Abrir en el Section Designer*) se abre el **Section Designer**:

- **Plantillas**: perfil I armado con alas distintas, I con cubreplacas, cajón soldado, canal, doble canal, te, ángulo, doble ángulo, tubo, barra maciza, cruz, polígono regular…
- **Componentes** de cualquier forma: rectángulo (con giro), círculo, tubo y polígono; **se arrastran con el ratón** (con paso de rejilla opcional), y también se editan por campos.
  Duplicar, quitar, espejo y centrar.
- **Propiedades en vivo**, con aviso si hay componentes superpuestos (se contarían dos veces).
- Un perfil estándar se abre como copia editable; la sección se guarda con otro nombre en la familia *Libre* (`shapes.json` de la carpeta de datos) y los proyectos que la usan
  la llevan dentro.

Las propiedades salen de las fórmulas exactas de polígonos y círculos y del eje neutro plástico. Las secciones libres funcionan en los módulos de nudo (3D, contacto del
miembro y verificaciones); las verificaciones de placa simple, doble ángulo, asiento y placa extrema las marcan como *NO EVALUADO*. La placa base no las usa.

## Biblioteca de materiales

El menú **Materiales** abre la biblioteca, con cinco categorías: **aceros** (Fy, Fu, E, ν, ρ y G), **pernos de conexión** (Fnt y Fnv de AISC Tabla J3.2), **electrodos**,
**varillas de anclaje** y **concretos**. Las filas grises son de la biblioteca (AISC / ASTM / ACI) y no se editan; los materiales propios se agregan, duplican, editan, eliminan,
exportan e importan (JSON), quedan en todas las listas del programa (los pernos propios entran a las verificaciones de los nudos) y cada proyecto lleva dentro los que usa.

## Visor 3D

Toda conexión usa el **visor OpenGL de la última versión de PlacaBase Pro** (un solo visor con Iso, Planta, Frontal y Lateral y el interruptor **Cotas**: en los nudos
acota los largos del miembro principal y de cada miembro conectado y su posición; con OpenGL no hay pestaña «Planta y elevación») (`gl3d.py`: sombreado plano con aristas vivas, órbita con el ratón,
etiquetas) cuando el equipo ofrece OpenGL; si no, usan el visor clásico de matplotlib. Se puede forzar el clásico con **Ver > Visor 3D OpenGL** (desmarcar; se aplica al reiniciar)
o con la variable de entorno `SCP_GL=0`. El programa **arranca maximizado**.

Los herrajes del 3D son representaciones con proporciones razonables (placas, ángulos, pernos con cabeza y tuerca); las verificaciones se hacen con los datos de las operaciones.
Los archivos de ejemplo `ejemplos/CN-01_columna_con_vigas.scp`, `CN-02_viga_con_secundarias.scp` y `CN-03_cordon_con_diagonales.scp` son proyectos normales (no plantillas); se regeneran con `tools/make_examples.py`, que usa los nudos de prueba de `tools/node_presets.py`.

**Archivos anteriores.** Los `.scp` con nudos de la versión con tipologías (*Nudo viga-columna*, *Viga a viga*, *Crucetas*) y las plantillas que se guardaron con ellas se abren como
conexión de nudo: el principal queda orientado como estaba (vertical en el nudo viga-columna, horizontal en los otros dos), con la misma geometría y los mismos resultados. Los
`.scp` con conexiones de las tipologías retiradas antes (placa de corte, doble ángulo, asiento...) se abren, pero esas conexiones se omiten (el programa avisa cuáles); las placas
base se abren igual que siempre.

**Para modificar o ampliar un módulo**: los datos están en `conn/specs.py` (`Member`, `Nodo`), el nudo en blanco y el miembro nuevo en `conn/presets.py`, la geometría
3D (secciones, recorte de cada miembro contra el principal, herrajes, cartelas) en `conn/assembly.py` y la pestaña de entrada en `ui_nodes.py`; el asistente es
`ui_wizard.py`. `selftest_nodes.py` prueba la geometría con valores calculados a mano, 225 nudos de ejemplo de `tools/node_presets.py` y 300 nudos al azar.

---

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
selftest.py             casos de prueba del motor (placa base); al final corre selftest_nodes.py
selftest_nodes.py       pruebas de los módulos de nudo (operaciones, verificaciones, secciones libres, materiales, interfaz): `python selftest_nodes.py`
tools/                  make_logo.py (logo e iconos), make_examples.py (ejemplos de los nudos)
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
  dialogs.py            sección personalizada (dimensiones)
  sections.py           secciones libres: propiedades exactas (polígonos, círculos, plástico), plantillas
  ui_sections.py        biblioteca de secciones y Section Designer
  ui_materials.py       biblioteca de materiales
  data/aisc_shapes.json catalogo AISC integrado (1,660 perfiles)
  ui.py, ui_widgets.py  interfaz PySide6
  ui_nodes.py           pestaña de los módulos de nudo: Miembros / Operaciones / Cargas / Análisis
  ui_wizard.py          asistente Nueva conexión (en blanco o desde plantilla) y guardado de plantillas
  templates.py          plantillas del usuario (guardar, listar, cargar, renombrar, eliminar)
  conn/specs.py         datos de los módulos de nudo (Member, Operation, Load, Nodo) y sus listas
  conn/checks/          verificaciones por código AISC 360-22 de cada operación (motores de fórmulas cerradas y adaptadores)
  conn/presets.py       nudo en blanco de cada módulo y miembro nuevo
  conn/assembly.py      geometría 3D de los nudos: secciones, recorte contra el principal, herrajes, cartelas
  conn/nodes.py         los tres módulos vistos por la interfaz y su esquema de planta y elevación
  conn/fem/             modelo 3D y escena (visor y miniaturas); malla, CalculiX y resultados quedan sin uso hasta reactivar el análisis
ejemplos/               tres placas base resueltas y un ejemplo de cada módulo de nudo
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
| `PB-01_W14X90.scp` | placa base: W14X90, 22×22×2", 8 pernos Ø1¼", llave de corte (archivo de la versión anterior: abre como conexión con la operación de placa base) | 0.750 | distancia al borde |
| `PB-02_HSS12_rigidizada.scp` | HSS12X12X½, 24×24×2", rigidizadores perimetrales, soldadura CJP | 0.949 | esbeltez del rigidizador |
| `PB-03_poste_circular.scp` | Pipe/HSS16 sobre placa circular Ø30", 12 pernos Ø1½" con gancho en J | 1.000 | aplastamiento del concreto |
| `CN-01_columna_con_vigas.scp` | columna W14X90 intermedia con cuatro vigas (placa extrema extendida, doble ángulo, placa simple, alas soldadas) y una diagonal con cartela | — | verificación por código |
| `CN-02_viga_con_secundarias.scp` | viga principal W24X55 con tres secundarias (placa extrema a ras, placa simple, doble ángulo esviada 60°) | — | verificación por código |
| `CN-03_cordon_con_diagonales.scp` | cordón HSS10X10 con dos diagonales en V y un montante, cartela atornillada | — | verificación por código |
| `CN-04_columna_con_placa_base.scp` | columna W14X90 sobre placa base (datos de PB-01) con una viga a cada lado y una diagonal con cartela | 0.800 | verificación por código |

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
