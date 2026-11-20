# SteelConPro — Parte 2: riostras SCBF / OCBF / EBF (AISC 341-22 F1, F2, F3) con casos de capacidad en el nudo

Enfoque elegido por el usuario: **B** — verificaciones de la conexion de la riostra + casos de capacidad en el nudo, para que
la placa base, la columna y las demas conexiones reciban las resistencias requeridas de las riostras (AISC 341-22 D2.6a/b(a)).
Descartado A (solo la conexion de la riostra): dejaba la placa base sin las fuerzas de las riostras.

## Como funciona hoy
- Las diagonales son `Member` del nudo; su cartela es la operacion `OP_GUSSET` (atornillada) u `OP_GUSSET_W` (soldada) y se
  verifica en `conn/checks/generic.py::_gusset` con la N del miembro en cada caso del nudo (Whitmore, bloque, pernos,
  soldadura, miembro en traccion; compresion simplificada).
- Parte 1 dejo: `Project.seis`, tipos de caso (`Nodo.case_kind/case_meta`), generador `seismic.generate_node_cases`,
  Ry de la Tabla A3.2 (`seismic.ry_of`), parte E y limite D2.6 en la placa base.

## Datos nuevos
- `Member.seis_role`: "" | "Riostra SCBF" | "Riostra OCBF" | "Riostra EBF" | "Eslabon EBF".
- `Member.brace_L` (longitud de la riostra entre puntos de trabajo, in; 0 = no dada) y `Member.brace_K` (1.0).
- `Member.link_e` (longitud del eslabon, in; solo "Eslabon EBF").
- `Operation.seis_clear` (cartela: holgura del extremo de la riostra a la linea de restriccion, in; 0 = no dada) y
  `Operation.seis_clear_mode` ("Lineal 2t" | "Eliptica 8t").
- `Seismic.capacity_cases: bool = True` (generar los casos de capacidad de las riostras).

## Resistencias requeridas de la conexion de cada riostra (LRFD; Ry y Fy del acero de la riostra)
- SCBF (F2.6c): traccion Treq = Ry·Fy·Ag; compresion Creq = 1.1·Ry·Pn (Pn de AISC 360 E3 con K·L/r; sin L, Pn = Fy·Ag y aviso).
- OCBF (F1.6a): Treq = min(Ry·Fy·Ag ; maxima traccion de la riostra en los casos Ωo del nudo); Creq = maxima compresion en los casos Ωo.
- EBF (F3.3/F3.6): P = 1.25·Ry·Vn del eslabon (1.4 si es cajon) × |N_riostra / V_eslabon| del caso QE de servicio;
  Vn = min(Vp, 2·Mp/e), Vp = 0.6·Fy·(d − 2tf)·tw.  Sin eslabon definido: los casos Ωo y un aviso.

## Casos de capacidad en el nudo (generador)
Por direccion sismica (±QEx, ±QEy, y 100/30 si esta activo), dos casos "C#" (kind "Cap", tratados como Ωo en la placa base
con la parte E conocida): (1.2 + 0.2·SDS)·D + f1·L + 0.2·S + Ecl  y  (0.9 − 0.2·SDS)·D + Ecl, donde Ecl = cada riostra con su
resistencia requerida con el signo que le da QE en esa direccion (traccion → Treq, compresion → −Creq) y los demas miembros
con Ωo·QE.  SCBF agrega el caso de post-pandeo (F2.3b): las comprimidas a 0.3·Pn.  La placa base aplica a estos casos el
limite D2.6 de la Parte 1.  Las cartelas se verifican con estos casos sin cambiar su motor.

## Verificaciones propias de AISC 341 (grupo de la cartela de la riostra)
- Esbeltez: SCBF K·L/r ≤ 200 (F2.5b(1)).
- Ancho/espesor (Tabla D1.1): SCBF alta ductilidad, OCBF ductilidad moderada (HSS rectangular b/t, HSS redondo D/t,
  alas de W y angulos b/t, alma de W h/tw), con Ry·Fy.
- SCBF: seccion neta efectiva Ae ≥ Ag en la conexion (F2.5b(3)); si no cumple, avisa que hace falta refuerzo.
- SCBF: acomodo del pandeo (F2.6c(3)(b)): holgura ≥ 2t (lineal) u 8t (eliptica) de la cartela; sin holgura dada → NO EVALUADO.
- EBF eslabon: tipo (corto si e ≤ 1.6·Mp/Vp) y Vn informados; el giro del eslabon no se verifica (depende de la deriva).
- Avisos: zona protegida, soldaduras de demanda critica (A3.4b), V invertida (F1.4a/F2.4a), conexion viga-columna de EBF.

## Interfaz
- Ventana del miembro: tarjeta "Sismo (AISC 341)" con papel, L, K y e (segun el papel).
- Ventana de la cartela: holgura y modo.
- Ventana Diseno sismico: casilla "Casos de capacidad de las riostras" y tabla con Treq/Creq de cada riostra.

## Pruebas
Motor: Treq/Creq de una HSS A500 Gr.B (Ry 1.4), casos C# en el nudo con la riostra a su capacidad y signo, la placa base
recibe la componente de la riostra, ancho/espesor (una HSS que falla y una que cumple), esbeltez, Ae ≥ Ag, holgura 2t,
eslabon EBF (corto/largo y la fuerza de la riostra).  Electron: la ventana del miembro y la de sismo con la tabla.

## Fuera de esta parte
Diseno del miembro riostra/eslabon (pandeo global, giro del eslabon, rigidizadores del eslabon), UFM con momentos,
la conexion viga-columna de EBF; placas extremas precalificadas (Parte 3).
