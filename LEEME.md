<p align="center"><img src="steelconpro/data/logo.png" width="420" alt="SteelConPro"></p>

# SteelConPro 1.1

Diseño y verificación de **conexiones de acero** con **un solo tipo de conexión**, que se arma por operaciones. Es una **aplicación de escritorio Electron** (interfaz web local) que usa
el motor de cálculo en Python como servicio local; el visor 3D es three.js.

| Elemento | Qué es |
|---|---|
| **Miembros** | cualquier número (columnas, vigas, diagonales; cualquier sección y ángulo); **uno es el principal, que usted designa** (el que recibe a los demás, como el miembro de apoyo de IDEA StatiCa) |
| **Operaciones** | las de conexión (placa simple, doble ángulo, asiento, placa extrema, alas soldadas, cartelas), **placa** (refuerzo soldado o atornillado, cartela o rigidizador, de forma rectangular, triangular, trapecio, circular, ranurada, con esquina recortada o polígono libre, con abertura circular, rectangular o que rodea a un miembro; también sobre el **extremo** de un miembro, sobre la cara de un miembro, de la placa base o de **otra placa**), **pernos**, **soldadura de filete** (por bordes de la placa, con inicio y largo, filete/CJP/PJP, o **contorno de un miembro** contra una cara), **ángulo** como pieza (soldado o atornillado), **huecos y ranuras**, **recorte de un miembro** contra la cara de otro elemento o en **inglete**, **corte de elementos**, corte del extremo, placas de continuidad y **placa base** (anclajes ACI 318-19, llave de corte, rigidizadores, soldadura; cálculo cerrado y análisis 3D por elementos finitos sólido con Gmsh + CalculiX) |
| **Cargas y análisis** | **análisis nodal** (equilibrio del nudo por caso de carga; de él salen las cargas de la placa base), verificación por código (AISC 360-22, AISC DG1, ACI 318), vista 3D, memoria de cálculo; análisis FEM 3D de la placa base |

**No hay un módulo de placa base aparte** ni «tipologías» de nudo: se crea una conexión, se le agregan miembros y las operaciones que se necesiten, y el tipo de nudo lo define lo que usted arma.
Los archivos y plantillas de placa base de las versiones anteriores abren como una conexión con la operación *Placa base* (mismos resultados).

Normas: **AISC 360-22**, **AISC 358/341** donde aplique; placa base: **AISC Design Guide 1 (2ª Ed.)** y **ACI 318-19 Cap. 17**.

> **Cambio de nombre (1.1).** El programa antes tenía otro nombre y otra numeración de versiones; la de SteelConPro empieza en 1.1. Los proyectos se guardan como `.scp`; los archivos `.pbase` y el
> formato de libro de las versiones anteriores se siguen abriendo (al guardar quedan como `.scp`).

**Unidades configurables**: longitud en in / ft / mm / cm / m, fuerza en kip / lbf / kN / N / tonf / kgf, momento y esfuerzo por separado, para cada proyecto (clic en el título del proyecto).
Se aplican a las entradas, a los resultados y a los reportes. El cálculo interno siempre corre en in-kip-ksi. Los proyectos nuevos arrancan en **mm, kN, MPa, kN·m** (o en el conjunto que se elija al crearlos).

## Pantalla de inicio (proyectos)

Como el panel de proyectos de Terrastruct: los proyectos son archivos `.scp` en una **carpeta de trabajo** (por omisión `Documentos\SteelConPro`; se cambia abajo a la izquierda) y se organizan en **carpetas**
(anidadas), con **favoritos**, **recientes**, búsqueda, orden (más recientes, nombre) y vista en tarjetas con **miniatura 3D** o en lista. Desde cada tarjeta se abre, renombra, duplica, mueve a una carpeta,
marca como favorito, muestra en el explorador o elimina. *Nuevo proyecto* pide nombre, carpeta y unidades y abre una conexión en blanco; *Abrir archivo* importa un `.scp` o `.pbase` a la carpeta de trabajo.
La primera vez, la carpeta `Ejemplos` trae los proyectos de ejemplo. También están aquí las bibliotecas de **secciones** (con Section Designer), **materiales** y **plantillas**.

## Editor

Barra superior: volver al inicio, nombre del proyecto y **pestañas de conexiones** (un proyecto puede tener varias; clic derecho para renombrar, duplicar o eliminar), deshacer / rehacer (`Ctrl+Z` / `Ctrl+Y`),
bibliotecas, informe (PDF, Word, STEP) y **Calcular**. El proyecto se guarda solo (y con `Ctrl+S`). A la izquierda el **árbol**: *Miembros* (★ = principal), *Operaciones* (con la barra de D/C de cada una; las que dependen de una placa
cuelgan de ella) y *Cargas*. Al centro el **visor 3D** (Iso / Planta / Frontal / Lateral, ajustar, cotas, etiquetas, mostrar herrajes, guardar imagen); clic en una pieza la selecciona en el árbol. A la derecha, **Resultados**, **Memoria** y,
si hay placa base, **FEM**.

**Cada operación se edita en su propia ventana.** Al elegir *Agregar operación* se crea la operación con valores típicos y se **abre su ventana**; los cambios se ven en vivo en el 3D y en los resultados, *Cancelar* los revierte y
*Agregar* / *Aceptar* los conserva. Doble clic en una operación del árbol la vuelve a abrir.

- **Placa**: función (*Refuerzo*, *Cartela* o *Rigidizador*), **elemento al que se une** (un miembro, la placa base u otra placa creada antes) y **cara**; orientación (paralela a la cara o perpendicular, transversal o
  longitudinal), forma (rectangular, triangular o con esquina recortada), largo, ancho, posición y giro, espesor y acero; **unión soldada** (cateto y contorno) o **atornillada** (diámetro, calidad, filas, columnas y separaciones).
  Una placa nueva es un elemento al que otras operaciones pueden unirse: *una placa que rigidiza otra placa* es una placa cuyo elemento padre es la primera. Al borrar una placa se borran en cascada las que dependen de ella (se avisa antes).
- **Pernos**: elemento y cara de partida, **elementos que atraviesan** (se marcan en la lista), diámetro, calidad, filas, columnas, separaciones y posición.
- **Soldadura de filete**: se marcan **qué placas se sueldan** (cordón de filete adicional entre cada placa y la cara a la que está unida).
- **Corte de elementos / corte del extremo**: se marcan **los miembros que se cortan**, el extremo, las profundidades superior e inferior y el largo del corte.
- **Placa base**: miembro y extremo, y todos sus datos en pestañas (*Cargas*, *Orientación*, *Placa*, *Pernos*, *Llave de corte*, *Rigidizadores*, *Soldadura*, *Concreto*, *Elementos finitos*). El perfil es el del miembro que la lleva.

Las operaciones generales (placa, pernos, soldadura) se verifican con las **fuerzas de diseño que usted escriba en la operación** (cortante y tracción): placa (fluencia y rotura en tracción, fluencia por cortante, esbeltez del rigidizador),
pernos (separación, distancia al borde, cortante, tracción, aplastamiento y desgarramiento por capa) y soldadura (cateto mínimo y máximo, resistencia). Con las fuerzas en cero solo se comprueban las condiciones geométricas.

### Cargas y análisis nodal

Una conexión es **un nodo** con el miembro principal y cualquier número de miembros que llegan a él. En *Cargas* se escribe, por caso de carga, la **acción de cada miembro sobre el nudo** en su extremo junto al nudo, en sus ejes
locales (x a lo largo del miembro hacia afuera del nudo, N > 0 = tracción; z el peralte; y = z × x), y opcionalmente una **carga externa en el nudo** (miembro «Carga externa», ejes globales: N = Fx, Vy = Fy, Vz = Fz, T = Mx, My, Mz).
El miembro principal puede dar sus cargas en un lado; **la acción del principal en el otro lado (el *lado que equilibra*) no se escribe: se calcula** por equilibrio de fuerzas y de momentos del nudo
(`R = −(Σ F + F externa)`, `M = −(Σ (M + r × F) + M externo)`, con los momentos respecto del cruce de ejes y `r` el punto donde cada miembro llega al eje del principal). La pestaña **Nudo** del editor muestra, por caso, las acciones
en ejes globales, la reacción del principal en sus ejes locales y comprueba que ΣF = ΣM = 0.

**Placa base**: si el nudo tiene casos de carga, las combinaciones de la placa base **salen del análisis nodal** (un caso = una combinación): la carga sobre la placa es la opuesta a la reacción del apoyo sobre el miembro, trasladada
del nudo al centro de la placa (Pu, Mux, Muy, Vux, Vuy en los ejes del miembro, girados con la *Rotación* de la placa; Mux > 0 tracciona el lado +Y, Muy > 0 el lado +X). Sin casos de carga se usan las combinaciones escritas en la operación.
Esto vale para la placa base en el lado que equilibra del principal, en el lado dado del principal y en un miembro conectado (en éste, el brazo se mide hasta el extremo libre dibujado, sin el retranqueo de los herrajes).
Los miembros conectados se verifican con las cargas que usted escribió; las operaciones generales (placa, pernos, soldadura) siguen usando las fuerzas de diseño de su propia ventana.

### Resultados por operación

La pestaña **Resultados** agrupa las verificaciones **por operación** (`n. operación — elemento`), cada grupo con su barra de D/C (verde < 0.80, ámbar hasta 1.00, rojo arriba); los grupos que no cumplen se abren solos,
y al elegir una operación en el árbol se lleva al grupo correspondiente. Arriba, el veredicto y las tarjetas de D/C máximo, qué gobierna y número de verificaciones; si cambia cualquier dato aparece *Desactualizado* hasta que termina el recálculo.
La pestaña **Memoria** trae el desarrollo de las ecuaciones. En modo por lotes: `python run.py archivo.scp --pdf memoria.pdf`.

**Qué verifica** (AISC 360-22, motores de fórmulas cerradas): placa simple (pernos con excentricidad por centro instantáneo de rotación, aplastamiento, fluencia, rotura y bloque
de cortante, flexión, soldadura, tamaño de filetes, alma de la viga), doble ángulo, asiento, placa extrema a ras o extendida (columna I por el ala), fuerza del ala en alas
soldadas CJP, cartelas (pernos, aplastamiento, ancho de Whitmore, bloque de cortante, fluencia y rotura del miembro, soldaduras) y placa base completa (DG1 + ACI 318-19 + FEM opcional).

**Qué no verifica** (aparece como *NO EVALUADO*, hay que revisarlo aparte): reparto de fuerzas de la cartela (UFM), pandeo del miembro en compresión, flexión local del ala y alma de la columna (J10), placas de continuidad,
pandeo local del alma por el corte; las operaciones de conexión con miembros que no son perfiles I; el análisis de una cartela en compresión es simplificado. **Las operaciones generales usan las fuerzas que usted escribe: el programa
no las obtiene de un análisis de la conexión (no hay CBFEM).** El análisis FEM sólido existe solo para la placa base. No hay operación de *huecos* (agujeros libres): los de los pernos se consideran en sus verificaciones, pero no se dibujan en las placas.
La soldadura entre elementos une placas con la cara a la que están unidas; no une dos miembros cualesquiera.

## Biblioteca de secciones y Section Designer

*Bibliotecas > Secciones* (o desde la pantalla de inicio) lista todas las secciones: catálogo AISC (1 660 perfiles), personalizadas y libres, con búsqueda por familia y propiedades. *Nueva sección* abre el **Section Designer**:

- **Plantillas**: perfil I armado con alas distintas, I con cubreplacas, cajón soldado, canal, doble canal, te, ángulo, doble ángulo, tubo, barra maciza, cruz, polígono regular…
- **Componentes** de cualquier forma: rectángulo (con giro), círculo, tubo y polígono (vértices pegables desde Excel); se editan por campos y se ven en el dibujo (clic para seleccionar). Duplicar y quitar.
- **Propiedades en vivo** (A, anchos, Ix, Iy, J, Sx, Sy, Zx, Zy, rx, ry y peso), con aviso si hay componentes superpuestos (se contarían dos veces).
- Un perfil estándar se abre como copia editable; la sección se guarda en la familia *Libre* y los proyectos que la usan la llevan dentro.

## Biblioteca de materiales

*Bibliotecas > Materiales*: **aceros**, **pernos de conexión** (Fnt y Fnv de AISC Tabla J3.2), **electrodos**, **varillas de anclaje** y **concretos**. Los de la biblioteca (AISC / ASTM / ACI) no se editan; los propios se agregan,
quedan en todas las listas y cada proyecto lleva dentro los que usa.

## Plantillas

*Bibliotecas > Plantillas de conexión*: guarda la conexión actual (miembros, operaciones y, si se quiere, cargas) con un nombre y la aplica a otra conexión (se puede deshacer). Cada plantilla es un `.json` en la carpeta de datos con las secciones y materiales propios que usa.

## Visor 3D

El visor usa three.js (WebGL) con sombreado plano de dos caras y aristas vivas, órbita con el ratón, etiquetas HTML y cotas en las unidades del proyecto. El programa arranca maximizado; hay tema claro y oscuro (abajo a la izquierda en la pantalla de inicio).
Los herrajes del 3D son representaciones con proporciones razonables (placas, ángulos, pernos con cabeza y tuerca); las verificaciones se hacen con los datos de las operaciones.
Los archivos `ejemplos/CN-01…CN-04.scp` son proyectos normales; se regeneran con `tools/make_examples.py`, que usa los nudos de prueba de `tools/node_presets.py`.

**Archivos anteriores.** Los `.scp` con nudos de la versión con tipologías y las plantillas que se guardaron con ellas se abren como conexión de nudo con la misma geometría y los mismos resultados. Los `.scp` con conexiones de las
tipologías retiradas antes (placa de corte, doble ángulo, asiento...) se abren, pero esas conexiones se omiten (se avisa cuáles); las placas base se abren como conexión con la operación de placa base.

---

## 1. Usar y compartir

**Si recibió `SteelConPro-1.1.0-portable.exe`:** ábralo (un solo archivo, no hay que instalar nada): lleva dentro Electron, el motor con Gmsh y CalculiX. La primera vez tarda unos segundos en desempaquetarse.

**Para compilarlo desde este código fuente (Windows):** instale **Python 3.11+** y **Node.js 20+** y haga doble clic en **`build_portable.bat`**: crea un entorno virtual, instala las dependencias, corre las autopruebas,
compila el motor con PyInstaller (`dist\engine`), copia `solvers\` y arma con electron-builder `electron\dist\SteelConPro-1.1.0-portable.exe`. El flujo de GitHub Actions (`.github/workflows/build-windows.yml`) hace lo mismo
y deja el `.exe` como artefacto.

**Para probarlo sin compilar:** `ejecutar_sin_compilar.bat` (o, en cualquier sistema, `cd electron && npm install && npm start`; el motor se lanza con `python run.py --serve`; `SCP_PYTHON` elige otro intérprete).

**Pruebas:** `python selftest.py` (motor, operaciones, API y servidor) y, con el motor y Playwright, `cd electron && node tests/smoke.js` (abre la aplicación real, el proyecto de ejemplo, el visor y la ventana de una operación).

### Uso por línea de comandos

```
SteelConPro-engine.exe --serve [--port N] [--token T]   servidor local del motor (lo lanza la aplicación)
SteelConPro-engine.exe --selftest                       autopruebas del motor
SteelConPro-engine.exe PB-01.scp --pdf m.pdf --docx m.docx --inp m.inp
```

En modo lote devuelve código de salida 0 si cumple y 2 si no cumple, así que se puede encadenar en un script para verificar muchas conexiones de golpe.

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

Las opciones están en la pestaña *Elementos finitos* de la operación *Placa base*; el análisis se corre y se ve en la pestaña **FEM** del panel derecho del editor. El programa tiene
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
incluidos; indique otras rutas en la pestaña *Elementos finitos* de la operación si quiere.

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

La pestaña **Memoria** muestra el cálculo completo paso a paso. Cada línea
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

Se incluye como anexo en los reportes (PDF y Word).

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
run.py                  punto de entrada del motor (--serve / lote / autopruebas)
selftest.py             casos de prueba del motor (placa base); al final corre selftest_nodes.py y selftest_ops.py
selftest_nodes.py       pruebas de los nudos (operaciones, verificaciones, secciones libres, materiales, plantillas)
selftest_ops.py         pruebas de las operaciones generales, la API JSON, el espacio de trabajo y el servidor local
tools/                  make_logo.py (logo e iconos), make_examples.py (ejemplos), node_presets.py (nudos de prueba)
electron/
  main.js, preload.js   proceso principal (arranca el motor, ventana, diálogos de archivo) y puente seguro
  renderer/             interfaz: index.html, css/app.css, js/ (home, editor, opdialog, bpform, libraries, viewer…), vendor/ (three.js)
  tests/smoke.js        prueba de humo con la aplicación real (Playwright)
steelconpro/
  api.py                funciones que expone el motor a la interfaz (libros, operaciones, malla 3D, verificación, FEM, informes, espacio de trabajo)
  server.py             servidor HTTP local (127.0.0.1, con token) que despacha api.py
  scene3d.py            escenas 3D (mallas por pieza) que el visor three.js dibuja
  units.py, materials.py, shapes.py, model.py, geometry.py, design.py, anchors.py   núcleo de la placa base (DG1, ACI 318)
  mesh3d.py, weldfe.py, weld3d.py, fem_checks.py, view3d.py, rep3d.py, params3d.py  modelo sólido 3D (Gmsh + CalculiX) y su postproceso
  explain.py, draw.py, report.py   memoria detallada, dibujos, PDF y DOCX
  sections.py           secciones libres: propiedades exactas (polígonos, círculos, plástico), plantillas del Section Designer
  templates.py          plantillas del usuario
  conn/specs.py         datos del nudo (Member, Operation, Load, Nodo) y listas de operaciones
  conn/ops.py           operaciones generales: placa, pernos, soldadura, corte (geometría, dependencias, verificaciones)
  conn/assembly.py      geometría 3D del nudo: secciones, recorte contra el principal, herrajes, cartelas
  conn/baseplate.py     la placa base como operación (proyecto derivado para el motor DG1/ACI/FEM)
  conn/checks/          verificaciones por código AISC 360-22 de cada operación (motores de fórmulas cerradas y adaptadores)
  conn/fem/             modelo 3D y escena (miniaturas); malla, CalculiX y resultados
  data/                 catálogo AISC (1,660 perfiles), esquema de los datos de la placa base, logotipos e iconos
ejemplos/               tres placas base resueltas y cuatro conexiones de nudo
```

Para tocar el motor sin abrir la interfaz: `python run.py --selftest` corre los casos y
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


## Edición libre de las conexiones y malla del FEM

- Las conexiones tipo tienen sus medidas editables: placa simple (alto, ancho, filas × columnas, desplazamiento), doble ángulo (piernas y largo), asiento (piernas y ancho) y placa extrema (ancho, alto, gramil y posición de cada fila de pernos).
- **Convertir en piezas editables** (placa extrema a ras y extendida): la conexión se reemplaza por una placa sobre el extremo del miembro, la soldadura de contorno y un grupo de pernos por fila, con los mismos pernos que la original. Desde ahí se edita cada pieza (forma, aberturas, pernos, soldaduras).
- Pestaña **FEM**: *Configuración del análisis FEM* (largo modelado de cada miembro, calidad y tamaño de malla, contacto, plasticidad, modelo y criterio de soldaduras) y **Ver malla en el visor** (genera solo la malla con Gmsh y la muestra pieza por pieza, sin resolver).
