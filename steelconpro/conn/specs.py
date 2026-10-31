# -*- coding: utf-8 -*-
"""Datos del modulo de conexion de nudo (todo lo que no es placa base): un nudo generico con un miembro principal designado por el usuario.

Solo dataclasses y listas de catalogo, sin importar nada del resto del programa:
`model.py` importa este modulo para guardar el modulo dentro de `Project`, asi
que aqui no puede importarse `model` (importacion circular).

No hay tipologias (viga-columna, viga a viga, crucetas): el nudo se arma por OPERACIONES como en IDEA StatiCa Connection:
  1. MIEMBROS: un miembro principal (el que el usuario designa; puede ser una columna, una viga o un cordon, con la orientacion que tenga) que pasa
     por el nudo y cualquier numero de miembros conectados con un azimut (angulo en planta), una elevacion (inclinacion) y una posicion sobre el principal;
  2. OPERACIONES: una lista ordenada de operaciones sobre los miembros (placa simple, doble angulo, asiento, placa extrema, cartela, corte,
     placas de continuidad...), cada una con sus parametros;
  3. CARGAS: esfuerzos internos en el extremo de cada miembro, por caso de carga;
  4. ANALISIS: verificaciones por codigo (AISC 360-22) de cada operacion y, despues, analisis 3D por elementos finitos.

Unidades internas: in, kip, grados.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# La primera es la placa base (el resto del programa); la otra es el nudo generico (steelconpro/conn/).
CT_BASEPLATE = "Placa base de columna"
CT_NODE = "Conexión de nudo"
CONN_TYPES = [CT_BASEPLATE, CT_NODE]
ATTR_OF = {CT_NODE: "node"}

# Tipologias retiradas (archivos y plantillas de la version anterior): se leen como nudo generico con el principal orientado como lo estaba.
MODE_COL, MODE_BEAM, MODE_CHORD = "col", "viga", "cordon"
LEGACY_NODES = {"Nudo viga-columna": ("ncol", MODE_COL), "Viga a viga": ("nbb", MODE_BEAM), "Crucetas (celosia y diagonales)": ("ntr", MODE_CHORD)}
LEGACY_MAIN_NAMES = {MODE_COL: "Columna", MODE_BEAM: "Viga principal", MODE_CHORD: "Cordón"}
LEGACY_END_LABELS = {
    MODE_COL: ["Intermedia (continúa arriba y abajo)", "Extremo superior (la columna termina en el nudo)",
               "Extremo inferior (la columna nace en el nudo)"],
    MODE_BEAM: ["Continua (a ambos lados del nudo)", "Extremo (termina en el nudo, lado +X)", "Extremo (termina en el nudo, lado −X)"],
    MODE_CHORD: ["Cordón continuo", "Extremo (termina en el nudo, lado +X)", "Extremo (termina en el nudo, lado −X)"],
}

BOLT_GRADES = ["A325-N", "A325-X", "A490-N", "A490-X", "A307"]
SHEAR_BOLT_SIZES = ["5/8", "3/4", "7/8", "1", "1-1/8"]

# ---- operaciones (como en IDEA StatiCa Connection): la conexion se arma aplicando operaciones, en orden, a los miembros
OP_TAB = "Placa simple (corte)"
OP_DANG = "Doble ángulo (corte)"
OP_SEAT = "Asiento (ángulo)"
OP_EP_FLUSH = "Placa extrema a ras (momento)"
OP_EP_EXT = "Placa extrema extendida (momento)"
OP_WELD = "Alas soldadas y alma atornillada (momento)"
OP_GUSSET = "Cartela atornillada (diagonal)"
OP_GUSSET_W = "Cartela con miembro soldado (diagonal)"
OP_COPE = "Corte del extremo (cope)"
OP_CONT = "Placas de continuidad"
OP_BASE = "Placa base (apoyo sobre concreto)"
# operaciones generales: eligen los elementos sobre los que actuan (miembros y placas creadas por otras operaciones) y pueden depender unas de otras
OP_PLATE = "Placa (refuerzo, cartela o rigidizador)"
OP_BOLTS = "Pernos entre elementos"
OP_FILLET = "Soldadura de filete entre elementos"
OP_CUT = "Corte de elementos"
OP_HOLE = "Huecos y ranuras"
OP_ANGLE = "Ángulo (herraje)"
OP_TRIM = "Recorte contra otro elemento"
OP_WORKPLANE = "Plano de trabajo"
OP_ALIGN = "Alinear cara"
OPERATIONS = [OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET, OP_GUSSET_W, OP_COPE, OP_CONT, OP_BASE, OP_PLATE, OP_ANGLE, OP_BOLTS, OP_FILLET, OP_HOLE, OP_CUT, OP_TRIM, OP_WORKPLANE, OP_ALIGN]
GENERIC_OPS = (OP_PLATE, OP_BOLTS, OP_FILLET, OP_CUT, OP_HOLE, OP_ANGLE, OP_TRIM, OP_WORKPLANE, OP_ALIGN)
# grupos del menu "Agregar operacion" (como la cinta de IDEA)
OP_GROUPS = [("Conexión de corte", [OP_TAB, OP_DANG, OP_SEAT]),
             ("Conexión de momento", [OP_EP_FLUSH, OP_EP_EXT, OP_WELD]),
             ("Conexión de diagonal", [OP_GUSSET, OP_GUSSET_W]),
             ("Placas, pernos y soldaduras", [OP_PLATE, OP_ANGLE, OP_BOLTS, OP_FILLET]),
             ("Modificar elementos", [OP_COPE, OP_CUT, OP_TRIM, OP_HOLE]),
             ("Referencias", [OP_WORKPLANE]),
             ("Rigidizar el miembro principal", [OP_CONT]),
             ("Apoyo del miembro", [OP_BASE])]
PLATE_ROLES = ["Refuerzo", "Cartela", "Rigidizador"]
PLATE_ORIENTS = ["Paralela a la cara", "Perpendicular, transversal", "Perpendicular, longitudinal"]
PLATE_SHAPES = ["Rectangular", "Triangular", "Con esquina recortada", "Circular", "Trapecio", "Ranurada (extremos redondeados)", "Polígono libre"]
OPENINGS = ["Ninguna", "Circular", "Rectangular", "Rodea al miembro"]
HOLE_SHAPES = ["Circular", "Ranura", "Rectangular"]
WELD_TYPES = ["Filete", "CJP (penetración completa)", "PJP (penetración parcial)"]
TAB_MODES = ["Sobre la cara del soporte", "Hasta el interior de las alas del principal", "Dos placas (arriba y abajo) hasta las alas del principal"]
BEAM_CONNS = ["Atornillada", "Soldada"]
TRIM_MODES = ["Contra una cara de otro elemento", "Inglete con otro miembro"]
WELD_MODES = ["Bordes de la placa", "Contorno del miembro"]
ATTACHES = ["Soldada", "Atornillada"]
FACES_END = ["Extremo inicio", "Extremo fin"]
FACES_I = ["Ala superior", "Ala inferior", "Alma +", "Alma −"] + FACES_END
FACES_BOX = ["Cara +X", "Cara −X", "Cara +Y", "Cara −Y"] + FACES_END
FACES_PLATE = ["Cara +", "Cara −"]
FACES_ANGLE = ["Pierna sobre la cara", "Pierna saliente +", "Pierna saliente −"]
FACE_LABELS = {"I": FACES_I, "box": FACES_BOX, "plate": FACES_PLATE}
CONNECTION_OPS = (OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET, OP_GUSSET_W)   # a lo sumo una por miembro
MOMENT_OPS = (OP_EP_FLUSH, OP_EP_EXT, OP_WELD)
SHEAR_OPS = (OP_TAB, OP_DANG, OP_SEAT)
GUSSET_OPS = (OP_GUSSET, OP_GUSSET_W)
# nombres antiguos (version anterior de los archivos: la conexion era un campo del miembro)
CK_BLANK = "En blanco (sin conexión)"
_LEGACY_CONN = {"Corte — placa simple": OP_TAB, "Corte — doble ángulo": OP_DANG, "Corte — asiento (ángulo)": OP_SEAT,
                "Momento — placa extrema a ras": OP_EP_FLUSH, "Momento — placa extrema extendida": OP_EP_EXT,
                "Momento — alas soldadas y alma atornillada": OP_WELD, "Diagonal — cartela atornillada": OP_GUSSET,
                "Diagonal — cartela con miembro soldado": OP_GUSSET_W}

# ---- como termina el miembro principal en el nudo (indice 0 = continuo en los dos sentidos); "+" es el sentido de su eje (azimut y elevacion)
END_LABELS = ["Continuo (pasa por el nudo)", "Termina en el nudo (el cuerpo queda del lado −)", "Termina en el nudo (el cuerpo queda del lado +)"]
POS_LABEL = "Posición sobre el principal"
OFF_LABEL = "Desplazamiento (peralte)"
OFF2_LABEL = "Desplazamiento (ancho)"
MAIN_NAME = "M1"


@dataclass
class Member:
    """Miembro conectado al principal (viga o diagonal): solo geometria; la conexion se define con operaciones."""
    name: str = "V1"
    shape: str = "W16X31"
    steel: str = "ASTM A992"
    az: float = 0.0              # azimut en planta, grados, desde +X hacia +Y (visto desde arriba)
    el: float = 0.0              # inclinacion sobre la horizontal, grados (+ hacia arriba)
    pos: float = 0.0             # posicion sobre el miembro principal medida desde el nudo (in), a lo largo del eje del principal
    off: float = 0.0             # desplazamiento del eje respecto del eje del principal, en el sentido del peralte del principal (in)
    off2: float = 0.0            # idem, en el sentido del ancho del principal (in)
    L: float = 48.0              # largo libre dibujado del miembro, in
    roll: float = 0.0            # giro del miembro sobre su eje, grados
    gap: float = 0.0             # desplazamiento del miembro sobre su propio eje, in (+ lo aleja del principal, − lo acerca)


@dataclass
class Operation:
    """Una operacion sobre un miembro (los parametros que se usan dependen del tipo)."""
    kind: str = OP_TAB
    member: str = "V1"           # nombre del miembro al que se aplica
    # ---- pernos y placas (placa simple, doble angulo, asiento, placa extrema, cartela)
    bolt_size: str = "3/4"
    bolt_grade: str = "A325-N"
    n_bolts: int = 3             # pernos por fila (placa simple, doble angulo) o filas (cartela)
    bolt_s: float = 3.0          # separacion de los pernos, in
    plate_t: float = 0.375       # espesor de placas / angulos / cartela, in
    plate_steel: str = "ASTM A36"
    weld_size: float = 0.25      # cateto de los filetes de la placa al soporte, in
    ep_ext: float = 3.0          # extension de la placa extrema extendida sobre el ala, in
    # ---- corte del extremo (cope)
    cope_top: float = 2.0        # profundidad del corte superior, in (0 = sin corte)
    cope_bot: float = 0.0        # profundidad del corte inferior, in
    cope_len: float = 4.5        # longitud del corte desde el extremo, in
    # ---- placas de continuidad
    cont_t: float = 0.5          # espesor, in
    # ---- placa base: extremo del miembro principal donde va (−1 = lado −, +1 = lado +); en un miembro conectado va en su extremo libre.
    #      Sus datos (placa, anclajes, llave, rigidizadores, soldadura, concreto, cargas) estan en los bloques de la conexion (ver conn/baseplate.py)
    end: int = -1
    # ---- operaciones generales (placa, pernos, soldadura, corte): elementos sobre los que actuan y parametros
    name: str = ""               # nombre del elemento que crea (placa) o rotulo de la operacion
    parent: str = ""             # elemento al que se une / de cuya cara depende (miembro o placa de otra operacion)
    face: str = ""               # cara del elemento padre (ver FACE_LABELS)
    targets: list = field(default_factory=list)      # otros elementos que toca: pernos (capas que atraviesan), soldadura (placas que une), corte (miembros que corta)
    role: str = PLATE_ROLES[0]
    orient: str = PLATE_ORIENTS[0]
    shape: str = PLATE_SHAPES[0]
    attach: str = ATTACHES[0]
    pl_L: float = 8.0            # largo de la placa (a lo largo del miembro, o ancho transversal si es perpendicular), in
    pl_W: float = 6.0            # ancho de la placa (a lo ancho de la cara) o altura sobre la cara (perpendicular), in
    pl_s: float = 12.0           # posicion del centro de la placa a lo largo del elemento padre desde su inicio, in
    pl_u: float = 0.0            # desplazamiento transversal del centro respecto del centro de la cara, in
    pl_rot: float = 0.0          # giro de la placa en el plano de la cara, grados
    pl_clip: float = 1.0         # lado del recorte de la esquina (forma recortada), in
    weld_all: bool = True        # soldadura en todo el contorno (si no, solo los lados largos)
    rows: int = 2                # pernos en la direccion del elemento padre
    cols: int = 2                # pernos en la direccion transversal
    bolt_g: float = 3.0          # separacion transversal de los pernos, in
    cut_at: str = "Inicio"       # extremo donde se corta: Inicio | Fin
    # ---- placa simple / doble angulo: tamaño de la placa, columnas de pernos y corte automatico de la viga secundaria
    tab_H: float = 0.0           # alto de la placa simple (a lo largo del peralte de la viga), in (0 = automatico)
    tab_W: float = 0.0           # ancho de la placa simple (a lo largo de la viga), in (0 = automatico)
    n_cols: int = 1              # columnas de pernos de la placa simple (separacion: bolt_g)
    beam_conn: str = BEAM_CONNS[0]  # placa simple: unión de la placa al alma de la viga conectada (pernos o filetes en el contorno de la placa)
    tab_mode: str = TAB_MODES[0]  # placa simple: «Hasta el interior de las alas» saca la viga del principal y extiende la placa para soldarla al alma y a la cara interna de las alas
    wp_x: float = 0.0            # plano de trabajo: punto del plano (coordenadas globales), in
    wp_y: float = 0.0
    wp_z: float = 0.0
    wp_az: float = 0.0           # plano de trabajo: azimut de la normal en planta, grados (desde +X hacia +Y)
    wp_el: float = 0.0           # plano de trabajo: inclinación de la normal sobre la horizontal, grados (90 = normal vertical, plano horizontal)
    wp_size: float = 60.0        # plano de trabajo: lado del cuadrado que se dibuja, in
    ref_face: str = ""           # alinear cara: cara del elemento de referencia (el plano de trabajo no tiene caras que elegir)
    al_offset: float = 0.0       # alinear cara: distancia a la que queda la cara del plano de referencia, in (+ en el sentido de la normal de la referencia)
    tab_clip: float = -1.0        # placa simple: lado del recorte de las esquinas junto al soporte, in (<0 o 0 = sin recorte; con «hasta las alas» la placa ya es escalonada)
    tp_sep: float = 0.0          # dos placas arriba y abajo: distancia libre entre ellas, in (0 = el alto de la placa de pernos)
    tp_t: float = 0.0            # dos placas arriba y abajo: espesor, in (0 = el de la placa)
    tab_y: float = 0.0           # placa simple: desplazamiento del centro de la placa a lo largo del peralte de la viga, in
    ep_w: float = 0.0            # placa extrema: ancho, in (0 = automático)
    ep_h: float = 0.0            # placa extrema: alto total, in (0 = automático según la extensión)
    ep_g: float = 0.0            # placa extrema: gramil (separación transversal de los pernos), in (0 = automático)
    ep_rows: list = field(default_factory=list)      # placa extrema: posición vertical de cada fila de pernos respecto del centro, in (vacío = automático)
    dang_lo: float = 3.5         # doble ángulo: pierna que va al soporte, in
    dang_la: float = 0.0         # doble ángulo: pierna sobre el alma, in (0 = automático)
    dang_H: float = 0.0          # doble ángulo: largo del ángulo, in (0 = automático)
    seat_Lh: float = 5.0         # ángulo de asiento: pierna horizontal (bajo el ala), in
    seat_Lv: float = 6.0         # ángulo de asiento: pierna vertical (contra el soporte), in
    seat_W: float = 0.0          # ángulo de asiento: ancho, in (0 = automático)
    wf_top: str = WELD_TYPES[1]  # conexiones de momento: tipo de soldadura del ala superior de la viga a la placa / al soporte
    wf_bot: str = WELD_TYPES[1]  # idem, ala inferior
    wf_web: str = WELD_TYPES[0]  # idem, alma
    align_to: str = ""           # conexiones de corte y de momento: elemento al que se alinea la placa («» = el miembro conectado; el nombre del principal = paralela a su cara)
    gus_L: float = 0.0           # cartela de arriostramiento: largo a lo largo del eje del miembro desde el principal, in (0 = automático)
    gus_hb: float = 0.0          # cartela: ancho de la base sobre el principal, in (0 = automático)
    gus_hm: float = 0.0          # cartela: ancho de la punta, in (0 = automático)
    gus_cut: float = 0.0         # cartela: lado del corte de las esquinas de la punta, in
    cope_auto: bool = True       # corta la viga secundaria (cope) lo necesario para librar las alas de la viga principal
    # ---- formas de placa, aberturas, agujeros y soldadura (operaciones generales)
    pl_L2: float = 0.0           # trapecio: ancho de la base superior, in (0 = igual al de la base)
    pts: list = field(default_factory=list)          # polígono libre: vértices [u, v] respecto del centro de la placa, in
    opening: str = OPENINGS[0]
    op_D: float = 2.0            # abertura circular: diametro, in
    op_W: float = 4.0            # abertura rectangular: ancho, in
    op_H: float = 4.0            # abertura rectangular: alto, in
    op_x: float = 0.0            # desplazamiento de la abertura respecto del centro de la placa, in
    op_y: float = 0.0
    op_member: str = ""          # «Rodea al miembro»: miembro cuya sección atraviesa la placa
    op_clear: float = 0.25       # holgura de la abertura alrededor del miembro, in
    weld_edges: list = field(default_factory=list)   # bordes de la placa que se sueldan (indices); con weld_all = True se sueldan todos
    weld_type: str = WELD_TYPES[0]
    weld_mode: str = WELD_MODES[0]
    weld_main: str = ""          # soldadura: elemento que se suelda (miembro, placa o ángulo); con él se usa `weld_to` en vez de parent/face/targets
    weld_to: list = field(default_factory=list)      # soldadura: [[elemento, cara]] a los que se suelda (cara "" = la que toca); puede haber varios
    weld_a: float = 0.0          # inicio del cordon en cada borde (in desde su primer vertice)
    weld_len: float = 0.0        # largo del cordon en cada borde, in (0 = todo el borde)
    hole_shape: str = HOLE_SHAPES[0]
    hole_D: float = 0.8125       # hueco circular: diametro; ranura: ancho; in
    hole_L: float = 1.5          # ranura o hueco rectangular: largo, in
    hole_W: float = 0.8125       # hueco rectangular: ancho, in
    hole_rot: float = 0.0
    leg_a: float = 4.0           # angulo: pierna sobre la cara, in
    leg_b: float = 4.0           # angulo: pierna saliente, in
    leg_side: int = 1            # angulo: pierna saliente hacia +1 o −1 (a lo ancho de la cara)
    trim_gap: float = 0.0        # recorte contra elemento: holgura, in
    trim_mode: str = TRIM_MODES[0]
    trim_weld: bool = False      # recorte contra otro elemento: soldar el contorno del miembro recortado contra la cara (usa weld_size y weld_type)
    trim_end: str = "Inicio"     # extremo del miembro que se recorta
    force_V: float = 0.0         # fuerza cortante de diseño de la operacion (kip), opcional
    force_T: float = 0.0         # fuerza de traccion de diseño de la operacion (kip), opcional

    @property
    def is_connection(self) -> bool:
        return self.kind in CONNECTION_OPS

    @property
    def makes_element(self) -> bool:
        return self.kind in (OP_PLATE, OP_ANGLE, OP_WORKPLANE)


@dataclass
class Load:
    """Accion de un miembro sobre el nudo en un caso de carga (su extremo junto al nudo), en sus ejes locales: x a lo largo del miembro
    (desde el nudo hacia fuera; N > 0 = traccion), z el peralte (vertical en una viga) e y = z × x.  kip y kip·in.  `member` = «@nudo» es una carga
    externa aplicada al nudo en ejes globales (N = Fx, Vy = Fy, Vz = Fz, T = Mx, My, Mz).  Las del miembro principal dan un lado; el otro sale del equilibrio."""
    case: str = "Caso 1"
    member: str = "V1"
    N: float = 0.0
    Vy: float = 0.0
    Vz: float = 0.0
    T: float = 0.0
    My: float = 0.0
    Mz: float = 0.0
    side: int = 0                # solo para el miembro principal: lado del nudo (−1 / +1) en el que se da la carga (0 = el opuesto al que equilibra)


@dataclass
class Nodo:
    """Nudo: miembro principal + miembros conectados + operaciones + cargas.  El principal lo designa el usuario (`main_name`) y su eje lo fijan el
    azimut y la elevacion (90° = vertical, 0° = horizontal); los demas miembros llegan a el."""
    main_name: str = MAIN_NAME
    main_shape: str = "W14X90"
    main_steel: str = "ASTM A992"
    main_az: float = 0.0         # azimut del eje del principal en planta (grados, desde +X hacia +Y); sin efecto si es vertical
    main_el: float = 90.0        # inclinacion del eje del principal sobre la horizontal (grados; 90 = vertical)
    main_roll: float = 0.0       # giro de la seccion sobre su eje, grados
    main_end: str = ""           # uno de END_LABELS; vacio = continuo
    main_len_neg: float = 60.0   # largo del miembro principal del lado − del nudo (abajo si es vertical), in
    main_len_pos: float = 60.0   # largo del lado + (arriba si es vertical), in
    members: list = field(default_factory=list)      # [Member]
    operations: list = field(default_factory=list)   # [Operation], en el orden en que se aplican
    loads: list = field(default_factory=list)        # [Load]
    show_hw: bool = True         # dibujar los herrajes (placas, angulos, pernos)
    balance_end: int = -1        # lado del principal (−1 / +1) cuya accion sobre el nudo sale del equilibrio (analisis nodal, conn/nodal.py)

    def __post_init__(self):
        raw = list(self.members or [])
        legacy_ops = []
        mem = []
        for m in raw:
            if isinstance(m, Member):
                mem.append(m)
                continue
            d = dict(m)
            conn = _LEGACY_CONN.get(d.get("conn", ""))
            if conn and not self.operations:               # archivo de la version anterior: la conexion estaba en el miembro
                legacy_ops.append(_mk(Operation, {**d, "kind": conn, "member": d.get("name", "")}))
            mem.append(_mk(Member, d))
        self.members = mem
        self.operations = [o if isinstance(o, Operation) else _mk(Operation, o) for o in (self.operations or legacy_ops)]
        self.loads = [x if isinstance(x, Load) else _mk(Load, x) for x in (self.loads or [])]
        if not self.main_end:
            self.main_end = END_LABELS[0]

    @property
    def end_index(self) -> int:
        return END_LABELS.index(self.main_end) if self.main_end in END_LABELS else 0

    @property
    def vertical(self) -> bool:
        """El eje del principal es (casi) vertical: se comporta como una columna (soporte, ejes locales)."""
        return abs(self.main_el) >= 45.0

    def names(self) -> list:
        return [self.main_name] + [m.name for m in self.members]

    def lengths(self):
        """(largo en el lado negativo, largo en el lado positivo) segun como termina el principal."""
        k = self.end_index
        return (self.main_len_neg if k != 2 else 0.0, self.main_len_pos if k != 1 else 0.0)

    def member_named(self, name):
        return next((m for m in self.members if m.name == name), None)

    def ops_of(self, name):
        """Operaciones aplicadas al miembro `name`, en orden."""
        return [o for o in self.operations if o.member == name]

    def connection_of(self, name):
        """La operacion de conexion (a lo sumo una) del miembro, o None."""
        return next((o for o in self.operations if o.member == name and o.is_connection), None)

    def element_names(self) -> list:
        """Nombres de todos los elementos: miembros (el principal primero) y placas creadas por operaciones, en el orden de las operaciones."""
        return self.names() + [o.name for o in self.operations if o.makes_element and o.name]

    def dependents(self, name: str) -> list:
        """Indices de las operaciones que dependen del elemento `name` (lo usan como padre, objetivo o miembro)."""
        out = []
        for i, o in enumerate(self.operations):
            if o.makes_element and o.name == name:
                continue
            if o.parent == name or name in (o.targets or []) or o.weld_main == name or any(t[0] == name for t in (o.weld_to or [])) or (o.member == name and o.kind != OP_BASE and o.kind in GENERIC_OPS):
                out.append(i)
        return out

    def base_op(self):
        """La operacion de placa base (a lo sumo una por conexion) o None."""
        return next((o for o in self.operations if o.kind == OP_BASE), None)

    def rename_main(self, new):
        old = self.main_name
        for o in self.operations:
            if o.member == old:
                o.member = new
            if o.parent == old:
                o.parent = new
            o.targets = [new if x == old else x for x in (o.targets or [])]
            o.weld_main = new if o.weld_main == old else o.weld_main
            o.weld_to = [[new if t[0] == old else t[0], t[1]] for t in (o.weld_to or [])]
        for x in self.loads:
            if x.member == old:
                x.member = new
        self.main_name = new

    def rename_member(self, old, new):
        for o in self.operations:
            if o.member == old:
                o.member = new
            if o.parent == old:
                o.parent = new
            o.targets = [new if x == old else x for x in (o.targets or [])]
            o.weld_main = new if o.weld_main == old else o.weld_main
            o.weld_to = [[new if t[0] == old else t[0], t[1]] for t in (o.weld_to or [])]
        for x in self.loads:
            if x.member == old:
                x.member = new


def _mk(cls, d):
    ok = cls.__dataclass_fields__
    return cls(**{k: v for k, v in dict(d).items() if k in ok})


def migrate_nodo(d: dict, mode: str) -> dict:
    """Datos de un nudo de la version con tipologias (`mode` = col | viga | cordon) en el formato del nudo generico: el principal queda orientado
    como estaba (columna vertical; viga o cordon a lo largo de X con su inclinacion) y conserva su nombre de antes."""
    d = dict(d)
    d.pop("mode", None)
    slope = float(d.pop("main_slope", 0.0) or 0.0)
    d.setdefault("main_name", LEGACY_MAIN_NAMES[mode])
    d["main_el"] = 90.0 if mode == MODE_COL else slope
    d["main_az"] = 0.0
    labs = LEGACY_END_LABELS[mode]
    if d.get("main_end") in labs:
        d["main_end"] = END_LABELS[labs.index(d["main_end"])]
    elif d.get("main_end"):
        d["main_end"] = END_LABELS[0]
    if mode == MODE_COL:                                    # en la columna el desnivel no se usaba
        d["members"] = [{**m, "off": 0.0} if isinstance(m, dict) else m for m in d.get("members", [])]
    return d
