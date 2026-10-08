<p align="center"><img src="steelconpro/data/logo.png" width="420" alt="SteelConPro"></p>

# SteelConPro 1.1

Diseño y verificación de **conexiones de acero** en cuatro módulos:

| Módulo | Qué es | Estado |
|---|---|---|
| **Placa base** | placas base de columna (perfiles **W, HSS cuadrado/rectangular, HSS circular y Pipe**), anclajes ACI 318-19, llave de corte, rigidizadores, soldadura; cálculo cerrado y análisis de elementos finitos sólido (Gmsh + CalculiX) | terminado |
| **Nudo viga-columna** | cualquier columna, de extremo o intermedia, con vigas en cualquier ubicación y ángulo (y diagonales con cartela) | solo geometría y vista 3D |
| **Viga a viga** | cualquier viga principal con vigas secundarias ubicadas respecto del nudo, a corte o a momento | solo geometría y vista 3D |
| **Crucetas** | cordón (o viga) con diagonales y montantes en cualquier ángulo, con cartela | solo geometría y vista 3D |

Los tres módulos de nudo no tienen todavía cálculo ni análisis: sus pestañas *Análisis FEM* y *Resultados* y el botón CALCULAR están desactivados, y no
se corre nada. Con estos módulos se podrán generar todas las tipologías de conexión; las tipologías anteriores (placa de corte, doble ángulo, asiento,
empalmes, placa extrema, cartela, HSS, RBS y puente) se retiraron.

Normas de la placa base: **AISC 360-22**, **AISC Design Guide 1 (2ª Ed.)**, **ACI 318-19 Cap. 17**.

> **Cambio de nombre (1.1).** El programa antes tenía otro nombre y otra numeración de versiones; la de SteelConPro empieza en 1.1. Los proyectos se guardan ahora como `.scp`; los archivos `.pbase` y el formato de libro de las
> versiones anteriores se siguen abriendo (al guardar quedan como `.scp`), y los materiales y perfiles importados de la carpeta de datos anterior se copian solos a la
> carpeta `SteelConPro` la primera vez que se abre el programa.

**Unidades configurables**: longitud en in / ft / mm / cm / m, fuerza en kip / lbf /
kN / N / tonf / kgf, momento y esfuerzo por separado. Se aplican a las entradas, a la
tabla de resultados y a los reportes. El cálculo interno siempre corre en in-kip-ksi,
que son las unidades nativas de AISC v14 y de los pernos en pulgadas.

Los proyectos nuevos arrancan en **mm, kN, MPa, kN·m** (se cambia en la pestaña Proyecto; los archivos guardados conservan sus unidades).


## Módulos de nudo: viga-columna, viga a viga y crucetas

**Nueva conexión** abre un asistente de tres pasos con miniaturas 3D, en el estilo de los programas de conexiones:

1. **Clase**: nudo viga-columna, viga a viga, crucetas o placa base.
2. **Geometría**: la configuración inicial del nudo (columna de extremo con una viga, intermedia con dos o cuatro vigas, una o dos secundarias, V, N, cruz…) en
   perfil I, HSS rectangular o HSS circular.
3. **Diseño**: la conexión que se asigna a todos los miembros — *momento* (placa extrema a ras o extendida; alas soldadas con alma atornillada y placas de
   continuidad), *corte* (placa simple, doble ángulo, asiento), *truss* (cartela atornillada o con miembros soldados) o *en blanco*.

Después todo se edita en la pestaña del módulo:

- **Miembro principal** (la columna, la viga principal o el cordón): **cualquier sección del catálogo AISC** (I, canal, ángulo, te, HSS rectangular y circular, tubo,
  y las que importe o defina), acero, giro de la sección sobre su eje, inclinación del eje (viga y cordón), y cómo termina en el nudo: *intermedio* (continúa a los
  dos lados) o *extremo* (la columna termina en el nudo por arriba o nace en él), con el largo a cada lado.
- **Miembros conectados**: una tabla con **Agregar, Duplicar y Quitar**; cada miembro tiene su propia sección y acero, su **azimut** (ángulo en planta, desde +X
  hacia +Y), su **elevación** (inclinación sobre la horizontal: 0° viga, ±45° diagonal, ±90° montante), su **posición** respecto del nudo (altura sobre la columna, o
  distancia al nudo a lo largo de la viga principal o del cordón: el nudo es el punto de aplicación de la carga), un desnivel de eje (viga y cordón), su largo, su giro
  sobre el eje y su retranqueo. El miembro arranca donde su eje sale de la sección del principal, sea cual sea el ángulo.
- **Conexión de cada miembro** (o la misma para todos con *Aplicar*): en blanco, placa simple, doble ángulo, asiento, placa extrema a ras o extendida, alas
  soldadas con alma atornillada (con placas de continuidad si llega al ala de una columna I) y, para las diagonales, cartela atornillada o con el miembro soldado.
  Parámetros: diámetro y calidad de los pernos, número y separación, espesor y acero de las placas, extensión de la placa extrema.
  Las diagonales que comparten plano **comparten una sola cartela**.
- **Vista**: *Modelo 3D* (gira con el ratón; con *Mostrar nombres* cada miembro lleva su nombre en el extremo) y *Planta y elevación* (esquema). *Exportar >
  Modelo sólido 3D* escribe la geometría en **STEP**.

Los herrajes son representaciones visuales (placas, ángulos, pernos con cabeza y tuerca) con proporciones razonables: **no están dimensionados ni verificados**.
Los archivos de ejemplo `ejemplos/NC-01_nudo_viga_columna.scp`, `VV-01_viga_a_viga.scp` y `CR-01_crucetas.scp` se regeneran con `tools/make_examples.py`.

**Archivos anteriores.** Los `.scp` que contengan conexiones de las tipologías retiradas se abren, pero esas conexiones se omiten (el programa avisa cuáles); las
placas base se abren igual que siempre.

**Para modificar o ampliar un módulo**: los datos están en `conn/specs.py` (`Member`, `Nodo`), las configuraciones del asistente en `conn/presets.py`, la geometría
3D (secciones, recorte de cada miembro contra el principal, herrajes, cartelas) en `conn/assembly.py` y la pestaña de entrada en `ui_nodes.py`; el asistente es
`ui_wizard.py`. `selftest_nodes.py` prueba la geometría con valores calculados a mano, todas las combinaciones del asistente y 300 nudos al azar.

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
selftest_nodes.py       pruebas de los módulos de nudo (solo geometría): `python selftest_nodes.py`
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
  dialogs.py            seccion personalizada y biblioteca de materiales
  data/aisc_shapes.json catalogo AISC integrado (1,660 perfiles)
  ui.py, ui_widgets.py  interfaz PySide6
  ui_nodes.py           pestaña de entrada de los módulos de nudo (principal + tabla de miembros)
  ui_wizard.py          asistente Nueva conexión: Clase / Geometría / Diseño con miniaturas
  conn/specs.py         datos de los módulos de nudo (Member, Nodo) y sus listas
  conn/presets.py       geometrías y diseños del asistente
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
| `PB-01_W14X90.scp` | W14X90, 22×22×2", 8 pernos Ø1¼", llave de corte | 0.750 | distancia al borde |
| `PB-02_HSS12_rigidizada.scp` | HSS12X12X½, 24×24×2", rigidizadores perimetrales, soldadura CJP | 0.949 | esbeltez del rigidizador |
| `PB-03_poste_circular.scp` | Pipe/HSS16 sobre placa circular Ø30", 12 pernos Ø1½" con gancho en J | 1.000 | aplastamiento del concreto |
| `NC-01_nudo_viga_columna.scp` | columna W14X90 intermedia con cuatro vigas (placa extrema extendida, doble ángulo, placa simple, alas soldadas) y una diagonal con cartela | — | solo geometría |
| `VV-01_viga_a_viga.scp` | viga principal W24X55 con tres secundarias (placa extrema a ras, placa simple, doble ángulo esviada 60°) | — | solo geometría |
| `CR-01_crucetas.scp` | cordón HSS10X10 con dos diagonales en V y un montante, cartela atornillada | — | solo geometría |

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
