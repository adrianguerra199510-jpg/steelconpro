<p align="center"><img src="placabase/data/logo.png" width="420" alt="PlacaBasePro"></p>

# PlacaBasePro 3.2.11

Diseño y verificación de placas base para perfiles **W, HSS cuadrado/rectangular,
HSS circular y Pipe**, con dibujo paramétrico, anclajes ACI 318-19, llave de corte,
rigidizadores, soldadura y análisis de elementos finitos.

Normas: **AISC 360-22**, **AISC Design Guide 1 (2ª Ed.)**, **ACI 318-19 Cap. 17**.

**Unidades configurables**: longitud en in / ft / mm / cm / m, fuerza en kip / lbf /
kN / N / tonf / kgf, momento y esfuerzo por separado. Se aplican a las entradas, a la
tabla de resultados y a los reportes. El cálculo interno siempre corre en in-kip-ksi,
que son las unidades nativas de AISC v14 y de los pernos en pulgadas.

Los proyectos nuevos arrancan en **mm, kN, MPa, kN·m** (se cambia en la pestaña Proyecto; los archivos guardados conservan sus unidades).

## Novedades de la 3.2.11

- **Columna descentrada**: en la pestaña Perfil, "Desplazamiento de la columna en X / Y" (cx, cy, respecto al centro de la placa). Pernos, placa y concreto no se mueven; se desplazan el perfil, la soldadura, los rigidizadores, el dibujo (con cotas cx / cy), el visor 3D y el modelo de elementos finitos.
- Las cargas se ingresan en el eje de la columna. El calculo cerrado las traslada al centro de la placa (Mux' = Mux − Pu·cy, Muy' = Muy + Pu·cx; la torsion Tz' = cx·Vuy − cy·Vux es solo informativa); el FEM 3D las aplica en el eje real de la columna, y la soldadura y el perfil se verifican con las cargas de la columna.
- Los voladizos m y n de la placa se toman del lado mas largo ((N + 2|cy| − 0.95d)/2) y el brazo de traccion se mide desde la cara real de la columna.

## Novedades de la 3.2.10

- Estudio de malla de la soldadura (PB-01, malla global 61 / 152 / 300 mm, elemento sobre el cordon 14 / 28 mm): el D/C del ala -Y varia 0.74-0.78 con el tamano del elemento del cordon (el pico es local y baja ~5 % al afinar) y casi no depende de la malla global mientras el cordon conserve ~28 mm (que es lo que hace el modo automatico). Con malla de 300 mm el calculo tarda ~19 s.
- Nuevo campo "Malla sobre la soldadura" (Elementos finitos): fija el tamano del elemento junto al cordon (0 = automatico).

## Novedades de la 3.2.9

- **Malla automatica 1.33 veces mas gruesa con acero plastico** (la opcion por defecto). Estudio con PB-01 (elementos de 61, 81, 102 y 127 mm; la
  malla del cordon se mantiene en ~28 mm): traccion en pernos, presion de contacto, desplazamiento y D/C de la soldadura cambian menos de 2 %;
  el tiempo total baja de 99 s a 56 s (43 % menos). El von Mises promediado de la placa baja 8 % (con plasticidad es informativo; sin ella se
  conserva la malla de antes). "Fina" y el tamaño manual no cambian.

## Novedades de la 3.2.8

- **Analisis mas rapido.** El primer incremento de CalculiX era de 0.5 de la carga; con acero plastico y cordones no lineales ese intento diverge,
  CalculiX lo descarta y reinicia con 0.125 (8 incrementos y ~55 iteraciones). Ahora el incremento inicial es 0.25: 4 incrementos y ~31
  iteraciones. En PB-01 la resolucion pasa de 157 s a 83 s (47 % menos) con los mismos resultados (desplazamiento y von Mises iguales hasta el
  0.004 %).

## Novedades de la 3.2.7

- Se retiraron del programa, la documentacion y los ejemplos las referencias a otros programas comerciales. El ejemplo de comparacion se
  llama ahora `COMP-1_W14X90_traccion.pbase`. Los proyectos guardados con el nombre anterior del criterio del cordon se abren sin problema.

## Novedades de la 3.2.6

- Barras U/Omega: **ld / ldh bajo la punta del anclaje.** La seccion critica es el extremo inferior del anclaje (z = hef) y la longitud
  desarrollada se mide de ahi hacia abajo hasta el final de la pata (como en el esquema); sobre ese nivel se exige ldh. La pata automatica es la
  que cumple ambas longitudes. Las cotas y las revisiones usan esa misma referencia.

## Novedades de la 3.2.5

- Las **barras U/Omega** se colocan **fuera del grupo de anclajes**, a 5 cm de la fila extrema (mitad a cada lado): ya no atraviesan los pernos.
  Se dibujan como barras redondas rojas.
- Nueva cota **"U a punta del anclaje"**: de la parte superior de la barra (tramo horizontal) al extremo inferior del anclaje (vistas Frontal e Iso).
- Columna inclinada: las cargas se rotulan en ejes de la columna (Pu', Vux', Vuy', Mux', Muy'); Pu indica que va a lo largo de la columna.

## Novedades de la 3.2.4

- Columna inclinada: las flechas del visor 3D muestran las cargas **como se ingresan** (en ejes de la columna: Pu a lo largo de ella, Vux/Vuy
  perpendiculares). Antes dibujaban los valores ya proyectados a la placa sobre los ejes de la columna (p. ej. Pu 1258 y un Vuy 1258 que no existian).
  El diseño sigue usando las cargas proyectadas a los ejes de la placa (se ven en Perfil > "En ejes de la placa").

## Novedades de la 3.2.3

- En la vista de **Planta** la columna y los rigidizadores se ven con un relleno tenue de su color y un contorno nitido (antes eran un gris casi
  invisible): se lee la huella del perfil sobre la placa.

## Novedades de la 3.2.2: soldadura calibrada contra un calculo de referencia

Con el ejemplo PB-01_W14X90 (P = 400 kip, Mux = 1800 kip·in, Vux = 30 kip) el ala −Y exterior da **Ut = 0.778** (programa de referencia 0.777;
calculo independiente con un elemento de cordon como el del paper, 0.779). Cambios respecto de la 3.2.1:
- Rigidez del cordon de filete **0.272·E** por unidad de longitud en las tres direcciones (rigidez a cortante del throat, 0.707·G); antes la
  normal era 0.707·E. El paper no publica la rigidez del elemento; este valor reproduce el calculo de referencia y debe tratarse como parametro declarado (la
  utilizacion del ala comprimida depende mucho de el).
- El conector normal del cordon **transmite tambien compresion** (en paralelo con el contacto, que es unas 13 veces mas rigido) y su modulo
  cuenta en la resultante y en el factor direccional kds, como en la Ec. 23 del paper.
- El pico se lee por elemento (sin ventana de promedio) y la media de cada linea sigue informandose.

## Novedades de la 3.2.1

- **Refuerzo del arrancamiento con dos opciones** (pestaña Concreto, "Tipo de barra"): **A, barra U** (patas rectas; bajo el cono se desarrolla ld y
  sobre el cono el tramo horizontal actua como gancho, ldh) y **B, barra Omega** (patas con gancho estandar de 90° hacia afuera, cola de 12·db;
  se desarrolla ldh bajo y sobre el cono). Se dibujan como barras redondas con doblez de radio interior 3·db (3D, con cotas, y elevacion) y se
  revisan: resistencia a traccion (φ·n·Ab·fy), desarrollo bajo el cono, desarrollo sobre el cono, altura del pedestal y, en la Omega, el
  recubrimiento lateral de la cola.
- **Cordon plastico sin suavizar** (como en el paper): la fuerza se lee por elemento (la fluencia redistribuye los picos) y el
  elemento del cordon no pasa de ~28 mm. En el ejemplo PB-01_W14X90 (referencia externa: 77.7 % en el ala −Y exterior) el programa da 0.72. El criterio
  elastico conserva el suavizado de 4 veces el cateto.
- El metal base solo se verifica con electrodo sobrecompatible (AISC J2.4).

## Novedades de la 3.2.0: un solo visor con cotas, y criterios del paper de soldaduras

- **Un solo visor en "Modelo y vistas"** (con OpenGL): reemplaza a los dibujos de planta y de elevacion. Botones: Iso, **Planta** (solo la
  placa con sus agujeros, P1..Pn y cotas; la columna y los rigidizadores en gris tenue), **Frontal** y **Lateral** (ortograficas, con la
  longitud de anclaje: hef, longitud total L, tp, mortero, stand-off, ancho de la placa, separacion de pernos y el gancho eh) y un
  interruptor **Cotas**. Al girar a mano la vista deja de ser de plano. El concreto es translucido y ahora se dibuja el **mortero**
  (grout) bajo la placa y la tuerca de nivelacion cuando hay stand-off; hef se mide desde la superficie del concreto. Sin OpenGL se usan
  los dibujos de siempre.

## Criterios del paper de soldaduras

Basado en Ghimire, Wald, Vild y Kabelac, *Numerical design calculation of the fillet weld resistance*, Welding in the World (2023):

- **Cordon plastico (5 %), segun el paper.** Con el modelo de conectores, la soldadura es ahora elasto-plastica: cada conector
  (normal solo-traccion y cortante x, y) fluye en la resistencia de diseno AISC J2.4, φ·0.60·FEXX·garganta (x1.5 si trabaja
  transversal, J2-5), con una rama plastica corta de pendiente k/1000. Eso redistribuye los picos locales de las esquinas en lugar de
  limitarlos con un factor. El D/C del cordon vale 1 cuando la deformacion plastica de la garganta llega al limite (5 %, editable) y la
  MEDIA de cada cara se exige hasta 1.0. El criterio anterior (elastico con pico limitado) sigue disponible en Elementos finitos. Si
  CalculiX no converge con el cordon plastico, se repite con el cordon elastico y se avisa.
- **Reduccion por cordon largo (AISC J2.2b(d)).** El paper confirma que el FEM no captura esta reduccion. Se aplica β a los filetes con
  L > 100·w: β = 1.2 − 0.002·L/w (0.6 a 300·w; longitud efectiva 180·w despues). Es conservador para cordones no cargados en sus
  extremos; se puede desactivar en Elementos finitos.
- La resistencia por linea sigue siendo la de AISC con el incremento direccional (coincide con la Ec. 23 del paper).

## Novedades de la 3.2.0: criterios del paper de soldaduras

Basado en Ghimire, Wald, Vild y Kabelac, *Numerical design calculation of the fillet weld resistance*, Welding in the World (2023):

- **Cordon plastico (5 %), segun el paper.** Con el modelo de conectores, la soldadura es ahora elasto-plastica: cada conector
  (normal solo-traccion y cortante x, y) fluye en la resistencia de diseno AISC J2.4, φ·0.60·FEXX·garganta (x1.5 si trabaja
  transversal, J2-5), con una rama plastica corta de pendiente k/1000. Eso redistribuye los picos locales de las esquinas en lugar de
  limitarlos con un factor. El D/C del cordon vale 1 cuando la deformacion plastica de la garganta llega al limite (5 %, editable) y la
  MEDIA de cada cara se exige hasta 1.0. El criterio anterior (elastico con pico limitado) sigue disponible en Elementos finitos. Si
  CalculiX no converge con el cordon plastico, se repite con el cordon elastico y se avisa.
- **Reduccion por cordon largo (AISC J2.2b(d)).** El paper confirma que el FEM no captura esta reduccion. Se aplica β a los filetes con
  L > 100·w: β = 1.2 − 0.002·L/w (0.6 a 300·w; longitud efectiva 180·w despues). Es conservador para cordones no cargados en sus
  extremos; se puede desactivar en Elementos finitos.
- La resistencia por linea sigue siendo la de AISC con el incremento direccional (coincide con la Ec. 23 del paper).

## Novedades de la 3.1.3

- Con la columna inclinada, las flechas de carga siguen sus ejes: Pu va a lo largo de la columna, Vux/Vuy perpendiculares a ella y los arcos de Mux/Muy en sus planos.

## Novedades de la 3.1.2

- Los formularios ya no se mueven al pasar el cursor sobre los campos (sobre todo en Pernos): el panel de ayuda del pie tiene
  altura fija con su propio scroll y la barra vertical del formulario siempre esta presente, asi el ancho no cambia.

## Novedades de la 3.1.1

- La **arandela** se dibuja sobre la placa (bajo la tuerca) en el 3D y en la elevacion, con el diametro y espesor del proyecto.
- **Ganchos L y J** con doblez circular real (radio interior 1.5·db): L a 90° con pata de largo eh; J a 180° con cola de 4·db (o eh/2).
- El visor 3D **no salta** al editar: conserva la camara (giro, zoom y desplazamiento) y solo la reescala si el modelo cambia de tamaño.
  "Encuadrar" (o doble clic) vuelve a ajustar.

## Novedades de la 3.1

- **Visor 3D en tiempo real (OpenGL).** "Modelo y vistas" y "Analisis FEM" usan ahora un visor OpenGL con z-buffer por pixel: el orden de
  las piezas es siempre correcto (columna, placa, tuercas, pernos y pedestal translucido) y la rotacion es fluida (>= 30 fps; con tarjeta
  grafica, cientos). Izquierdo: girar. Derecho o central: desplazar. Rueda: zoom. Doble clic: encuadrar. Barra: Iso / Frontal / Lateral /
  Planta, perspectiva u ortografica y guardar imagen. Si el equipo no ofrece OpenGL 2.1 (o se define `PB_NO_GL=1`) se usa el visor matplotlib
  de siempre. La memoria de calculo sigue usando matplotlib.
- **Tema claro por defecto** (no depende del perfil de Windows) y un interruptor sol/luna arriba a la derecha; la eleccion se recuerda y
  los graficos siempre van sobre fondo blanco. El logo se adapta al tema oscuro.
- **CALCULAR** sobre las pestañas del panel izquierdo.
- La rueda del raton solo cambia un campo numerico o una lista si ya tiene el foco; si no, desplaza el panel.

## Renderizado 3D (3.0, solo memoria y respaldo)

Todas las caras de acero (placa, pernos, tuercas, columna, rigidizadores, llave) van en **una sola coleccion** ordenada por profundidad (cara mas cercana,
algoritmo del pintor por cara) en vez de una coleccion por pieza; el pedestal translucido se parte en caras traseras (se pintan antes del acero) y
delanteras (despues) segun la camara, y se reordena al girar. Una rotacion completa tarda < 0.1 s.

## Soldadura en el FEM: pico y media

Cada cara del cordon se evalua con un **D/C pico** (punto mas cargado, elastico) y un **D/C media** (fuerza de la cara / su longitud). El pico se admite
hasta `Limite del D/C pico` (Elementos finitos; 1.5 por defecto, por la redistribucion plastica de un filete ductil) y la media hasta 1.0; el D/C de la fila es max(pico / limite, media). El calculo cerrado equivale a la media.

## Version 3.0: acero elasto-plastico en todas las piezas y sin motor de placas

Se **retira el motor de placas (shell)** de la 2.0: el unico analisis es el **solido 3D** (tetraedros, con arandelas y conectores de soldadura). Con plasticidad el motor de placas no convergia en varios casos (compresion con contacto unilateral, el tubo de comparacion) y modelaba peor la soldadura y el von Mises. Los archivos antiguos con ese motor elegido se abren sin problema y usan el solido.

### Plasticidad

Por defecto el 3D usa acero elasto-plastico perfecto (limite φ·Fy del acero de CADA pieza: placa, perfil, rigidizadores, llave y
arandelas): el esfuerzo queda acotado, desaparecen los picos puntuales y se verifica la deformacion plastica equivalente (PEEQ) ≤ 5 %. La
placa se verifica con el maximo nodal; el perfil, los rigidizadores y la llave, con el promedio en un circulo de radio ≈ espesor, porque el
borde del cordon es una singularidad de malla (en el tubo de comparacion: placa 0.016 %, perfil 0.2 % promedio y 1.3 % puntual). El von Mises
promediado pasa a ser informativo. El von Mises que se dibuja se **recorta en φ·Fy** del acero de cada pieza (CalculiX extrapola a los nodos y puede pasarse del tope; en el tubo de comparacion 359 → 285 MPa, 154 nodos); la verificacion no cambia. Se desactiva en Elementos finitos (vuelve al criterio elastico ≤ 0.9·Fy); si CalculiX no converge con
plasticidad, el programa usa el criterio elastico y lo avisa.
Con barras U la condicion A de ACI (φ = 0.75) se aplica sola; la casilla manual se elimino. En el visor, el analisis elasto-plastico reporta
solo el punto maximo, bajo la escala de colores.

## Barras U, cargas en el visor y elevacion (2.1)

- **Barras U de refuerzo del arrancamiento** (pestaña Concreto): diametro de barra (#3 a #10), cantidad de U (cada una aporta 2 patas),
  fy, profundidad del tramo horizontal y largo de pata (0 = automatico). Capacidad del refuerzo = φ·n_patas·Ab·fy con φ = 0.75
  (ACI 17.5.2.1 / 17.7.2.5); sustituye al concreto en traccion y cortante si resiste mas. Se verifica ademas el desarrollo de la pata
  bajo el cono de falla (ld, ACI 25.4.2.3; el cono se cruza a hef − d/1.5) y el gancho sobre el cono (ldh, ACI 25.4.3). Se dibujan en la
  elevacion (con la cota Ld) y en el 3D. El analisis 3D de elementos finitos no modela las barras.
- **Cargas en el visor 3D:** casilla "Mostrar cargas" en Modelo y vistas y en Analisis FEM: Pu (rojo), Vux/Vuy (azul) y Mux/Muy (violeta)
  de la combinacion activa, con su valor.
- **Elevacion:** el mortero se dibuja sobre el concreto y el stand-off como tuerca de nivelacion.

## Identidad visual (2.1)

Icono propio del programa y del .exe (`placabase/data/placabasepro.ico`), logo en la ventana, pantalla de inicio, "Acerca de" y el encabezado de las memorias PDF y Word; barra con acento naranja y boton CALCULAR de marca. Los recursos estan en `placabase/data/` y los colores en `placabase/brand.py`.

## Novedades de la 2.1: combinaciones de carga, flexion del perno y nueva organizacion

- **Flexion en los anclajes (stand-off):** Pernos > "Separacion libre placa-concreto". Con valor > 0 el cortante
  flexiona el perno en el tramo libre l = stand-off + mortero + tp/2 (se verifica si stand-off + mortero > db/2; un mortero mas delgado lo cubre el factor 0.80 de ACI): M = V·l/2 (doble empotramiento) o V·l (voladizo);
  se verifica φMn = 0.90·Fy·Z (AISC F11) y la interaccion traccion-flexion T/φTn + M/φMn ≤ 1 (AISC H1-1a). La
  traccion sale del 3D. El stand-off tambien suma al brazo del cortante del 3D y a la longitud del resorte del perno.
- **Combinaciones de carga:** la pestaña Cargas (ahora justo despues de Proyecto) es una tabla; cada fila es una
  combinacion (Pu, Mux, Muy, Vux, Vuy). CALCULAR corre el 3D de todas (solo las que no tienen 3D vigente) y el
  veredicto es el de la mas desfavorable. El combo "Combinacion" de la barra superior elige la que se dibuja y
  se detalla. La memoria detalla la que gobierna e incluye la tabla de todas.
- **Boton CALCULAR (F8)** junto al D/C de la barra superior. Hasta calcular no se muestra ninguna verificacion,
  D/C, memoria ni tabla de resultados ("SIN CALCULAR"); si se edita algo, el resultado vuelve a quedar sin calcular.
- **Pestañas:** "Modelo y vistas" (solo geometria: 3D + planta + elevacion, que tambien alterna con el detalle del rigidizador; sin cuadricula), "Analisis FEM" (selector de combinacion, campos, soldadura y pernos; con "Placa base" se rotulan los anclajes y el mas exigido va en rojo) y "Resultados" (combinaciones, verificaciones, botones de memoria PDF/Word y, con "Mostrar calculos detallados", la memoria; al hacer clic en una fila se salta a su calculo). CALCULAR esta junto a Guardar; el D/C, en la esquina superior derecha.

## Novedades de la 2.0 (motor de placas, retirado en la 3.0)

La 2.0 incluyo un motor de elementos tipo placa (shell S6). Se retiro en la 3.0; ver arriba.

## Novedades: malla 3D automatica, reintentos y boton para cancelar

- **Tamano de malla automatico** (`Calidad de la malla 3D → Automatica`, con tamano manual = 0): el mayor entre
  1.2 veces el radio de promedio del von Mises (r = factor × espesor) y raiz(area de la placa / 400), sin
  pasar de 1/4 del lado menor. Sale del estudio de convergencia (placa 500×500×20 mm, 1000 kN de traccion,
  mallas de 30 a 12 mm): con r de 15-20 mm el promedio varia ±2 % para elementos de hasta 1.2·r; la traccion
  en pernos varia < 0.5 %. En placas grandes manda el costo (modelo de ~70-90 mil nodos) y el radio de
  promedio sube a lc/1.2. "Fina" usa 0.65 veces ese tamano. Un tamano manual > 0 tiene prioridad.
- **Reintentos:** si Gmsh o CalculiX fallan (tetraedros invalidos, sin convergencia) el analisis se repite solo
  con malla 1.35 y 1.8 veces mas gruesa. El paso de carga de CalculiX ya no baja de 1e-3 (antes 1e-5 y se
  quedaba iterando con incrementos minimos).
- **Cancelar:** la ventana "Analisis 3D" tiene el boton *Cancelar analisis*, que mata Gmsh/CalculiX en curso
  (tambien al cerrar el programa).

## Novedades: un solo analisis de elementos finitos (el solido 3D) y soldadura con conectores

**Se elimino el FEM 2D interno** (placa de Mindlin, `fea.py`), su pestaña, sus mapas y la exportacion de
cascarones. El unico analisis de elementos finitos es el **modelo solido 3D** (Gmsh + CalculiX), y las
verificaciones FEM salen de el:

| Fila del veredicto | Que verifica | Criterio |
|---|---|---|
| `fem_bolt` | traccion del perno mas cargado (reaccion de los resortes del anillo de la tuerca) | AISC J3.6, φ·0.75·Fu·Ab |
| `fem_press` | presion de contacto maxima sobre el concreto | AISC J8 |
| `fem_vm` | von Mises **promediado** en la placa (r = 1 espesor; el pico puntual no converge) | ≤ 0.90·Fy (criterio del programa) |
| `fem_weld…` | una fila por zona de soldadura perfil-placa | AISC J2.4 |

**El veredicto lo da el 3D.** Mientras no exista un 3D vigente (hecho con el proyecto tal como esta ahora; la
firma ignora nombre, autor y unidades) la barra superior dice **"REALIZAR ANALISIS 3D (F8)"** en ambar (y
los reportes "PENDIENTE — realizar analisis 3D"): se muestran las verificaciones de calculo cerrado pero no
se declara CUMPLE / NO CUMPLE. Al terminar el 3D (malla rapida, ~30 s) todo se recalcula solo y aparece el
veredicto. La fuerza de cada perno para las verificaciones de acero y de concreto (AISC J3, ACI 17) sale
directamente del 3D (el perno de diseno es el mas cargado y el grupo traccionado son los pernos con T > 0).
El reparto lineal que se uso para validar el 3D se elimino del programa y de la memoria: coincidian con
placa gruesa (0.97-1.00) y el 3D es la referencia.

**Memoria de calculo.** La seccion 6 trae la soldadura por zona y la traccion por perno; la
seccion 7 aisla la PLACA y muestra en planta: von Mises promediado de la cara superior y de la inferior
(con la etiqueta del maximo y la curva 0.90·Fy), presion de contacto con la traccion de cada perno, y el
desplazamiento vertical; despues las dos vistas 3D en perspectiva.

### Soldadura perfil-placa: conectores entre cuerpos separados (`placabase/weldfe.py`)

En el modelo fusionado anterior la union era monolitica (una CJP ideal): una zona sin soldar transmitia
igual, la compresion pasaba por el cordon y la fuerza del cordon habia que deducirla de los esfuerzos del
perfil (concentraciones de esquina que dependen de la malla). Ahora, por defecto (`Elementos finitos →
Modelo de la soldadura`), despues de mallar (malla conforme) se **separan** el cuerpo superior (perfil y
rigidizadores) y el inferior (placa y llave) duplicando los nodos de la interfaz, y solo se comunican por:

- **Contacto solo-compresion** en toda la huella (un resorte por nodo, rigidez por area tributaria). El
  cordon no trabaja a compresion (DG1).
- **Conectores de cordon** en cada linea soldada: borde de la huella del perfil (cara exterior o interior
  de cada pared, segun "a uno o dos lados") y base de cada rigidizador. Por nodo: un resorte normal
  **solo-traccion** y dos de cortante. Rigidez por unidad de longitud = garganta de acero sobre una
  longitud igual al cateto: filete 0.707·E y 0.707·G; PJP E y G; CJP 5·E y 5·G. Un lado sin cordon o una
  zona "sin soldadura" **no** tiene conector.
- Los resortes normales usan un nodo auxiliar ligado con `*EQUATION` (z del nodo superior, x-y del inferior)
  para que midan solo el movimiento vertical aunque el perfil se deslice: sin el, CalculiX inclina el
  resorte con el deslizamiento y el alargamiento se contamina con Δ²/2δ (llegaba a falsear 40 % la
  compresion de los nodos de punta de ala).

La fuerza del cordon se lee **directa del conector** (F = k·Δ), sin integrar esfuerzos. Se suaviza por linea
en una ventana movil de 4 veces el cateto (nunca menos de 3 elementos; equivale a la redistribucion por
ductilidad de un cordon real) y se compara, por linea, con `φ·0.60·FEXX·garganta·kd` (AISC J2.4, kd de
J2-5) y, con la suma de las lineas de la pared, con la rotura del metal base. D/C pico = maximo de la curva
suavizada; D/C media = fuerza de la linea repartida en su longitud. El modelo fusionado sigue disponible
como respaldo.

Comprobaciones (`python selftest.py --3d`, y corridas de prueba con W14X90, HSS con rigidizadores y tubo
redondo): equilibrio vertical del cuerpo superior contacto − cordones = Pu (−0.1 kip en 400); en **traccion
pura** de 100 kip los cordones toman 100.08 kip, el contacto 0.000 y los pernos 100.00; el cortante de los
cordones suma 29.9 kip contra Vux = 30; el equilibrio de momentos cierra en 1 % (la diferencia es el P-Δ
del giro del nodo de carga). Con la web sin soldar, el alma no transmite y su carga pasa a las alas. En
PB-01 (malla rapida) el pico suavizado de la ala mas cargada es 5.8 kip/in contra 8.9 del metodo fusionado
por esfuerzos (que incluye la concentracion de esquina). Tarda lo mismo que antes (~25-30 s).

**Convergencia de malla de la soldadura** (PB-01): malla rapida (16 mil nodos, 24 s) contra automatica (58 mil
nodos, 3 min): pico suavizado del ala mas cargada 5.82 contra 5.94 kip/in (−2 %), del ala opuesta 1.97
contra 1.90, del alma 1.18 contra 1.20; medias dentro de 1-2 %; traccion en pernos 0.33 contra 0.31 kip.
El metodo fusionado por esfuerzos no convergia en los picos; la flexibilidad finita del conector es la que
regulariza la esquina.

**Limitaciones.** La rigidez del cordon es una idealizacion (garganta sobre una longitud = cateto), no una
curva carga-deformacion de soldadura; el contacto es sin friccion; el CalculiX incluido para Windows
(2.14) no se probo con estas tarjetas (`*EQUATION`, `SPRING2`, `SPRINGA` no lineal): se probo con 2.21. Si
falla, use "Fusionado" en `Modelo de la soldadura`.

## Novedades de la 1.2

| Cambio | Dónde |
|---|---|
| **Memoria detallada**: cada ecuación con su símbolo, fórmula, sustitución numérica y resultado, al estilo CalcPad | Pestaña Memoria detallada, y anexo en PDF y Word |
| El **análisis 3D se ejecuta y se ve dentro del programa**: Gmsh y CalculiX corren en segundo plano y el resultado se dibuja en 3D | Pestaña Modelo 3D |
| Los **pernos van etiquetados P1, P2…** en planta, en los mapas del FEA y en la tabla de reacciones | Planta, Elementos finitos |
| **Todo** sale en las unidades elegidas: también la columna de observaciones, los ejes de los dibujos y los títulos | Toda la aplicación |
| **Descripción de cada dato de entrada** en un panel al pie de cada pestaña, más la convención de signos de las cargas | Los 65 campos de entrada |

## Cortante en el modelo 3D

- El cortante entra a la altura e (brazo automatico: sin llave tp/2 + mortero; con llave tp + H/2; o manual en
  Elementos finitos), lo que genera el par V·e sobre la placa: con Vux ≠ 0 los pernos de un lado quedan mas
  cargados.
- Convencion de signo: Muy > 0 tracciona el lado −X (mano derecha).

## Novedades: malla 3D rapida (predeterminada) y von Mises promediado

Pestaña Elementos finitos → "Calidad de la malla 3D": **Rapida** (predeterminada; tetraedros del
doble de tamaño, ~30 s) o **Automatica** (fina, ~3 min).

El von Mises PUNTUAL del sólido no converge (crece al refinar en las aristas vivas), asi que el
programa reporta ademas el **von Mises promediado**: promedio del tensor de esfuerzos, ponderado
por el area de cada nodo, en un circulo de radio r (predeterminado = 1 espesor de placa; nunca
menor que el tamaño del elemento) sobre la misma cara de la placa; la cara superior excluye lo
cubierto por el perfil. Ese es el "esfuerzo maximo" de la etiqueta del visor y de la memoria.

Rapida vs automatica (3 conexiones, r = 1 espesor): traccion en pernos, presion y desplazamiento
difieren ≤ 0.5 %; el von Mises promediado difiere −2.4 % (PB-01 caso A: 14.96 vs 15.33 ksi),
−0.6 % (caso B: 25.36 vs 25.5) y +0.4 % (PB-02: 20.99 vs 20.91). Con un radio menor que el
tamaño del elemento (0.5 espesores en la malla rapida) la diferencia sube a +21 % (caso A):
por eso el radio tiene ese minimo.

## Convergencia de malla del 3D (PB-01, W14X90, placa 22×22×2 in)

Se corrio el modelo solido (Gmsh + CalculiX 2.21). Los estudios de esta seccion se hicieron antes de
mover los resortes horizontales de los pernos a la cara inferior (cambio de ≤ 1 % en placas de
2 in; ver la calibracion del 3D arriba).

Convergencia del 3D (caso B, tamano de malla objetivo en in):

| Malla | Nodos | Tiempo | Tracc. total | Perno max | p max | w placa | vM placa lejos | vM global |
|---|---|---|---|---|---|---|---|---|
| 2.0 | 15,912 | 0.5 min | 85.5 kip | 31.2 | 3.554 | 0.0475 | 26.5 | 138 |
| 1.5 | 27,293 | 0.8 min | 85.5 kip | 30.8 | 3.543 | 0.0474 | 29.4 | 147 |
| 1.0 (auto) | 56,911 | 3 min | 85.4 kip | 30.9 | 3.551 | 0.0475 | 44.2 | 172 |
| 0.75 | 93,481 | 7 min | 85.5 kip | 30.8 | 3.549 | 0.0475 | 46.7 | 192 |

Las cantidades globales (traccion en pernos, presion, deflexion, |U|, reacciones) estan
convergidas desde la malla de 2.0 in (variacion < 1.5 %); una malla de 2.0 in basta para
ellas y corre en ~30 s. El von Mises puntual NO converge (crece al refinar; el maximo nodal en la placa lejos de las
aristas sube 26.5 → 46.7 ksi). El promediado en r = 1 espesor si: 25.4, 25.2, 25.5 y 25.5 ksi
para las mallas de 2.0, 1.5, 1.0 y 0.75 in.

## Novedades: resultados 3D en la memoria y soldadura parcial

- Tras un analisis 3D, la memoria (PDF y Word) agrega una seccion con las imagenes de von Mises
  y de desplazamiento sobre la geometria deformada, con una etiqueta (★) en el esfuerzo maximo.
  El grafico 3D se ajusta al ancho y alto disponibles y se reajusta al cambiar el tamaño.
- Si alguna zona del perfil esta "Sin soldadura" (p. ej. un W solo soldado en el alma), sale un
  aviso y se verifica el contorno PARCIAL por el metodo elastico sobre las lineas soldadas; la
  compresion se transmite por contacto.

## Novedades: pegar coordenadas desde Excel

Pernos → Coordenadas manuales: boton **Pegar desde Excel** (reemplaza la lista con las
dos columnas x, y del portapapeles) o **Ctrl+V** sobre una celda (sobrescribe desde ella y
agrega filas). **Ctrl+C** copia las filas seleccionadas hacia Excel. Se aceptan coma o
punto decimal; encabezados y rotulos se ignoran; valores en las unidades actuales.

## Novedades: rigidizadores radiales

Con columna circular (HSS redondo o tubo) los rigidizadores se disponen en forma
RADIAL, repartidos por igual en 360° (cantidad = numero total de pletinas; angulo de la
primera en "Angulo de arranque"). El ancho tributario y la reduccion de voladizo usan la
separacion en arco a media proyeccion. La vista 3D ya no usa transparencias (el pedestal
de concreto no se dibuja).

## Novedades: vista 3D de geometria

La pestaña **Modelo 3D** muestra siempre la geometria de la conexion (placa, perfil,
pernos con tuerca, rigidizadores, llave de corte y pedestal transparente), dibujada
directamente por el programa: no necesita Gmsh ni CalculiX y se actualiza al editar.
El combo "Campo" tiene ahora "Solo geometria" (por defecto); tras un analisis 3D pasa a
von Mises. La columna inclinada se dibuja inclinada.

## Novedades: columna inclinada

Pestaña **Perfil → Inclinacion de la columna**: giro alrededor de X y/o de Y (grados,
respecto a la normal de la placa; 0° = perpendicular). Con inclinacion, Pu, Vux, Vuy,
Mux y Muy se ingresan en los ejes de la **columna** (Pu axial, V transversal) y el
programa los proyecta a los ejes de la placa con R = Ry·Rx antes de TODAS las
verificaciones (aplastamiento, pernos, soldadura, llave, FEA, CalculiX, informes).
Ejemplo: giro X = 30° → Pu,placa = Pu·cos30°, Vuy,placa = Vuy·cos30° + Pu·sin30°.
Con la columna inclinada **no se permiten rigidizadores**: la casilla se bloquea y, si el
proyecto ya los tenia, se desactivan al inclinar (o al abrir el archivo).
El torsor Tz que aparece por la inclinacion no se verifica (se emite un aviso).

## Novedades de la 1.5

| Cambio | Donde |
|---|---|
| **Catalogo AISC completo integrado**: 1,660 perfiles W, M, S, HP, C, MC, L, WT, MT, ST, HSS rectangulares y circulares, Pipe | pestana Perfil, lista Familia |
| **Secciones personalizadas**: tipo (I, canal, angulo, te, HSS, tubo, pletina) y dimensiones libres; propiedades calculadas | Perfil > Nueva seccion |
| **Secciones dobles espalda con espalda** con separacion (2L, 2C, 2WT...) | Perfil > Seccion doble |
| **Llave de corte con cualquier perfil**, ademas de la placa | pestana Llave de corte |
| **Biblioteca de materiales** propia: acero, anclajes y concreto | menu Materiales |
| **Varias conexiones por archivo** y reportes de todas de una vez (uno por conexion) | panel Conexiones; Exportar |
| Vista 3D centrada, con proporciones reales y **zoom con la rueda del mouse** (tambien en las vistas 2D) | Modelo 3D |

### Como se calculan las secciones nuevas

Toda seccion (salvo las redondas) se describe como un conjunto de rectangulos:
almas, alas, alas de angulo o pletinas. De ahi salen el dibujo, el solido 3D, las
paredes donde se lee la soldadura y las propiedades de las secciones dobles y
personalizadas. Para un perfil AISC simple se usan los valores de la tabla; los
rectangulos reproducen esas propiedades con 1-2 % de diferencia (los redondeos de
laminacion). Una seccion doble 2L4X4X1/2 con separacion de 3/8 in da Iy = 25.2 in⁴
contra 25.1 del Manual.

**Soldadura de angulos, canales, tes, pletinas y secciones dobles.** Se verifica
como grupo de soldadura por el metodo elastico en todo el contorno exterior,
con la especificacion "perimetral" de la pestana Soldadura:

    fz = −Pu/Lw + Mux·y/Ixw + Muy·x/Iyw   (+ traccion; la compresion va por contacto)
    f  = raiz( max(fz,0)² + (Vux/Lw)² + (Vuy/Lw)² )   <=   φ·0.60·FEXX·garganta

La autoprueba lo contrasta con dos casos a mano (traccion pura y momento puro).
Para estas secciones no se ofrecen rigidizadores.

**Llave de corte con perfil.** En cada direccion de cortante se verifican:
aplastamiento contra el concreto (ancho perpendicular × altura embebida), flexion
con Z del perfil en ese eje, cortante con los elementos paralelos a la fuerza,
soldadura como grupo en todo el contorno y desprendimiento del concreto. El giro
admite 0° o 90°.

### Varias conexiones

Un archivo `.pbase` guarda ahora todas las conexiones del proyecto, junto con los
perfiles personalizados y materiales propios que usen, para que abra igual en
otra computadora. Los archivos de versiones anteriores (una sola conexion) se
siguen abriendo. `Exportar > Reportes ... de TODAS las conexiones` genera un
archivo por conexion en la carpeta que se elija; el analisis 3D se incluye en el
reporte de una conexion solo si se corrio con esa conexion tal como esta.

## Novedades de la 1.4

| Cambio | Donde |
|---|---|
| **Gmsh y CalculiX incluidos**: el analisis 3D corre con un boton (o F8), sin instalar ni configurar nada | pestana Modelo 3D |
| **Revision de soldadura en el modelo 3D**: fuerza por unidad de longitud en cada ala, alma o cara, con D/C pico y D/C media | pestana Modelo 3D y reportes |
| Traccion por perno leida del modelo 3D | pestana Modelo 3D y reportes |
| Concreto **solo a compresion** y pernos **solo a traccion** en el 3D (paso no lineal) | — |
| Corregido: en el 3D el momento Mux/Muy no se aplicaba (iba a los grados de giro del nodo de referencia, que CalculiX ignora) | — |
| **Anclajes postinstalados con adhesivo** (ACI 318-19 17.6.5) para varilla recta | pestana Pernos |
| **Coordenadas manuales** de los anclajes | pestana Pernos |
| Corregido: con traccion neta la traccion se reparte entre todos los pernos (antes solo los de +Y) | — |
| Se quito la exportacion a Excel | — |

## Novedades de la 1.3

| Cambio | Donde |
|---|---|
| Todas las vistas graficas (planta, elevacion, rigidizador, FEA, 3D) dibujan y acotan en el sistema de unidades elegido | pestanas de salida |
| Los reportes — PDF y Word — salen enteros en ese sistema: datos de entrada, verificaciones, FEA y memoria detallada | Exportar |
| Tabla de tensiones perno por perno incluida en los tres reportes | Exportar |
| El calculo y el FEA corren solos con cada cambio; ya no hay boton "Calcular todo" ni casilla de FEA automatico | — |
| El analisis solido 3D se lanza y se ve dentro del programa (pestana Modelo 3D); ya no hay boton de exportacion en la barra | pestana Modelo 3D |
| Criterio del agujero de anclaje seleccionable: Tabla 14-2, arandela F844 o ajustado | pestana Pernos |
| Ejecutable portable para copiar y compartir | `build_portable.bat` |

## Novedades de la 1.1

| Cambio | Dónde |
|---|---|
| Sistema de unidades configurable, con presets | Pestaña Proyecto |
| Ubicación de los rigidizadores: separación fija, corrimiento o alineados con los pernos | Pestaña Rigidizadores |
| Forma de los rigidizadores: rectangular, triangular o con la esquina recortada, más destaje en el vértice | Pestaña Rigidizadores, vista Rigidizador |
| Memoria de cálculo en **PDF** (sin necesidad de Word) | Exportar |
| Tabla resumen de **tensiones perno por perno** | Pestaña Elementos finitos y los tres reportes |
| Los **agujeros de perno se mallan** en el FEA; el perno apoya en el anillo de la tuerca, no en un punto | Pestaña Elementos finitos |
| **Modelo sólido 3D** vía Gmsh + CalculiX, con la placa taladrada de verdad | Exportar |

---

## 1. Usar y compartir

**Si recibio `PlacaBasePro_portable.zip`:** descomprimalo donde quiera y abra
`PlacaBasePro\PlacaBasePro.exe`. No hay que instalar nada: Gmsh va dentro del
programa y CalculiX en `solvers\calculix`. No separe el `.exe` de su carpeta.

**Para compilarlo desde este codigo fuente (Windows):**

1. Tenga **Python 3.10 o superior** instalado.
2. Doble clic en **`build_portable.bat`**.

El script crea un entorno virtual, instala las dependencias (incluida la libreria
de Gmsh), corre las autopruebas, compila, copia `solvers\` y deja:

- `dist\PlacaBasePro\PlacaBasePro.exe` — el programa listo para usar.
- `PlacaBasePro_portable.zip` — la misma carpeta comprimida, para compartir.

`ejecutar_sin_compilar.bat` corre la aplicacion directamente con Python, util
mientras se prueba.

### Uso por línea de comandos

```
PlacaBasePro.exe                                      interfaz gráfica
PlacaBasePro.exe --selftest                           autopruebas del motor
PlacaBasePro.exe PB-01.pbase --pdf m.pdf --docx m.docx --inp m.inp
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
`%APPDATA%\PlacaBasePro\shapes.json` y los perfiles importados sustituyen a los
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
perfil-placa se modela con **conectores** entre cuerpos separados (ver arriba, `weldfe.py`); el modelo
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
- **Proyecto `.pbase`** (JSON legible) para reabrir o correr por lotes.

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
placabase/
  units.py              sistema de unidades configurable (UnitSet)
  materials.py          aceros, varillas, electrodos, geometría de pernos
  shapes.py             catálogo AISC integrado + importador de la base oficial
  model.py              dataclasses del proyecto, serialización .pbase
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
y el respaldo fusionado. `python run.py proyecto.pbase --3d carpeta --pdf memoria.pdf` hace el calculo
completo por lotes.

---

## 7. Ejemplos incluidos

| Archivo | Caso | D/C | Gobierna |
|---|---|---|---|
| `PB-01_W14X90.pbase` | W14X90, 22×22×2", 8 pernos Ø1¼", llave de corte | 0.750 | distancia al borde |
| `PB-02_HSS12_rigidizada.pbase` | HSS12X12X½, 24×24×2", rigidizadores perimetrales, soldadura CJP | 0.949 | esbeltez del rigidizador |
| `PB-03_poste_circular.pbase` | Pipe/HSS16 sobre placa circular Ø30", 12 pernos Ø1½" con gancho en J | 1.000 | aplastamiento del concreto |

---

*Los resultados deben ser revisados por un ingeniero responsable. El programa es
una herramienta de cálculo, no un sustituto del criterio profesional.*


## Modelo solido 3D: como se lee la soldadura

Con el modelo de **conectores** (predeterminado) la fuerza del cordon se lee directamente de los resortes
entre el perfil y la placa (ver "Soldadura perfil-placa" arriba). Como en la DG1, la compresion se transmite
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
