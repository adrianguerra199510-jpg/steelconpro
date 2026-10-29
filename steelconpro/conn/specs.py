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
OPERATIONS = [OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET, OP_GUSSET_W, OP_COPE, OP_CONT, OP_BASE, OP_PLATE, OP_BOLTS, OP_FILLET, OP_CUT]
GENERIC_OPS = (OP_PLATE, OP_BOLTS, OP_FILLET, OP_CUT)
# grupos del menu "Agregar operacion" (como la cinta de IDEA)
OP_GROUPS = [("Conexión de corte", [OP_TAB, OP_DANG, OP_SEAT]),
             ("Conexión de momento", [OP_EP_FLUSH, OP_EP_EXT, OP_WELD]),
             ("Conexión de diagonal", [OP_GUSSET, OP_GUSSET_W]),
             ("Placas, pernos y soldaduras", [OP_PLATE, OP_BOLTS, OP_FILLET]),
             ("Modificar elementos", [OP_COPE, OP_CUT]),
             ("Rigidizar el miembro principal", [OP_CONT]),
             ("Apoyo del miembro", [OP_BASE])]
PLATE_ROLES = ["Refuerzo", "Cartela", "Rigidizador"]
PLATE_ORIENTS = ["Paralela a la cara", "Perpendicular, transversal", "Perpendicular, longitudinal"]
PLATE_SHAPES = ["Rectangular", "Triangular", "Con esquina recortada"]
ATTACHES = ["Soldada", "Atornillada"]
FACES_I = ["Ala superior", "Ala inferior", "Alma +", "Alma −"]
FACES_BOX = ["Cara +X", "Cara −X", "Cara +Y", "Cara −Y"]
FACES_PLATE = ["Cara +", "Cara −"]
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
    gap: float = 0.5             # retranqueo del extremo respecto de la cara del miembro principal, in


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
    force_V: float = 0.0         # fuerza cortante de diseño de la operacion (kip), opcional
    force_T: float = 0.0         # fuerza de traccion de diseño de la operacion (kip), opcional

    @property
    def is_connection(self) -> bool:
        return self.kind in CONNECTION_OPS

    @property
    def makes_element(self) -> bool:
        return self.kind == OP_PLATE


@dataclass
class Load:
    """Esfuerzos internos de un caso de carga en el extremo de un miembro (junto al nudo), en sus ejes locales: x a lo largo del miembro
    (desde el nudo hacia fuera; N > 0 = traccion), z el peralte (vertical en una viga) e y = z × x.  kip y kip·in."""
    case: str = "Caso 1"
    member: str = "V1"
    N: float = 0.0
    Vy: float = 0.0
    Vz: float = 0.0
    T: float = 0.0
    My: float = 0.0
    Mz: float = 0.0


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
            if o.parent == name or name in (o.targets or []) or (o.member == name and o.kind != OP_BASE and o.kind in GENERIC_OPS):
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
