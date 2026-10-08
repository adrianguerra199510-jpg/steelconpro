# -*- coding: utf-8 -*-
"""Datos de los modulos de conexion distintos de la placa base: nudo viga-columna, viga a viga y crucetas.

Solo dataclasses y listas de catalogo, sin importar nada del resto del programa:
`model.py` importa este modulo para guardar el modulo dentro de `Project`, asi
que aqui no puede importarse `model` (importacion circular).

Los tres modulos comparten el mismo modelo: un MIEMBRO PRINCIPAL (columna, viga o cordon) que pasa por el nudo y cualquier numero de
MIEMBROS conectados (vigas, diagonales) que llegan a el con un azimut (angulo en planta), una elevacion (inclinacion) y una posicion
sobre el miembro principal.  Cada miembro tiene su propia conexion (corte, momento, cartela o en blanco).

Unidades internas: in, grados.  Por ahora los modulos son solo geometria y vista 3D: no tienen calculo ni analisis.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# La primera es la placa base (el resto del programa); las demas se arman en steelconpro/conn/.
CT_BASEPLATE = "Placa base de columna"
CT_NODE = "Nudo viga-columna"
CT_B2B = "Viga a viga"
CT_TRUSS = "Crucetas (celosia y diagonales)"
CONN_TYPES = [CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS]

# modo del miembro principal de cada modulo
MODE_COL, MODE_BEAM, MODE_CHORD = "col", "viga", "cordon"
MODE_OF = {CT_NODE: MODE_COL, CT_B2B: MODE_BEAM, CT_TRUSS: MODE_CHORD}
ATTR_OF = {CT_NODE: "ncol", CT_B2B: "nbb", CT_TRUSS: "ntr"}

BOLT_GRADES = ["A325-N", "A325-X", "A490-N", "A490-X", "A307"]
SHEAR_BOLT_SIZES = ["5/8", "3/4", "7/8", "1", "1-1/8"]

# ---- conexion de cada miembro
CK_BLANK = "En blanco (sin conexión)"
CK_TAB = "Corte — placa simple"
CK_DANG = "Corte — doble ángulo"
CK_SEAT = "Corte — asiento (ángulo)"
CK_EP_FLUSH = "Momento — placa extrema a ras"
CK_EP_EXT = "Momento — placa extrema extendida"
CK_WELD = "Momento — alas soldadas y alma atornillada"
CK_GUSSET = "Diagonal — cartela atornillada"
CK_GUSSET_W = "Diagonal — cartela con miembro soldado"
CONNECT_KINDS = [CK_BLANK, CK_TAB, CK_DANG, CK_SEAT, CK_EP_FLUSH, CK_EP_EXT, CK_WELD, CK_GUSSET, CK_GUSSET_W]
MOMENT_KINDS = (CK_EP_FLUSH, CK_EP_EXT, CK_WELD)
SHEAR_KINDS = (CK_TAB, CK_DANG, CK_SEAT)
GUSSET_KINDS = (CK_GUSSET, CK_GUSSET_W)

# ---- como termina el miembro principal en el nudo (indice 0 = continuo en los dos sentidos)
END_LABELS = {
    MODE_COL: ["Intermedia (continúa arriba y abajo)", "Extremo superior (la columna termina en el nudo)",
               "Extremo inferior (la columna nace en el nudo)"],
    MODE_BEAM: ["Continua (a ambos lados del nudo)", "Extremo (termina en el nudo, lado +X)", "Extremo (termina en el nudo, lado −X)"],
    MODE_CHORD: ["Cordón continuo", "Extremo (termina en el nudo, lado +X)", "Extremo (termina en el nudo, lado −X)"],
}
MAIN_NAMES = {MODE_COL: "Columna", MODE_BEAM: "Viga principal", MODE_CHORD: "Cordón"}
MEMBER_NAMES = {MODE_COL: "Viga", MODE_BEAM: "Viga secundaria", MODE_CHORD: "Diagonal"}
POS_LABELS = {MODE_COL: "Altura del eje respecto del nudo", MODE_BEAM: "Distancia al nudo a lo largo de la viga principal",
              MODE_CHORD: "Distancia al nudo a lo largo del cordón"}
OFF_LABELS = {MODE_COL: "", MODE_BEAM: "Desnivel del eje respecto del eje de la viga principal",
              MODE_CHORD: "Desnivel del eje respecto del eje del cordón"}


@dataclass
class Member:
    """Miembro conectado al principal (viga o diagonal)."""
    name: str = "V1"
    shape: str = "W16X31"
    steel: str = "ASTM A992"
    az: float = 0.0              # azimut en planta, grados, desde +X hacia +Y (visto desde arriba)
    el: float = 0.0              # inclinacion sobre la horizontal, grados (+ hacia arriba)
    pos: float = 0.0             # posicion sobre el miembro principal medida desde el nudo (in): altura (columna) o distancia (viga/cordon)
    off: float = 0.0             # desnivel del eje respecto del eje del principal (viga/cordon), in
    L: float = 48.0              # largo libre dibujado del miembro, in
    roll: float = 0.0            # giro del miembro sobre su eje, grados
    conn: str = CK_TAB
    gap: float = 0.5             # retranqueo del extremo respecto de la cara del miembro principal, in
    # ---- herraje
    bolt_size: str = "3/4"
    bolt_grade: str = "A325-N"
    n_bolts: int = 3             # pernos por fila (placa simple, doble angulo) o filas (cartela)
    bolt_s: float = 3.0          # separacion de los pernos, in
    plate_t: float = 0.375       # espesor de placas / angulos / cartela, in
    plate_steel: str = "ASTM A36"
    ep_ext: float = 3.0          # extension de la placa extrema extendida sobre el ala, in
    cont: bool = True            # placas de continuidad en la columna (momento contra el ala de una columna I)


@dataclass
class Nodo:
    """Nudo: miembro principal + miembros conectados.  `mode` fija el eje del principal (columna vertical; viga o cordon a lo largo de X)."""
    mode: str = MODE_COL
    main_shape: str = "W14X90"
    main_steel: str = "ASTM A992"
    main_roll: float = 0.0       # giro de la seccion sobre su eje, grados
    main_slope: float = 0.0      # inclinacion del eje respecto de la horizontal (viga / cordon), grados
    main_end: str = ""           # uno de END_LABELS[mode]; vacio = continuo
    main_len_neg: float = 60.0   # largo del miembro principal antes del nudo (abajo / lado -X), in
    main_len_pos: float = 60.0   # largo despues del nudo (arriba / lado +X), in
    members: list = field(default_factory=list)      # [Member]
    show_hw: bool = True         # dibujar los herrajes (placas, angulos, pernos)

    def __post_init__(self):
        self.members = [m if isinstance(m, Member) else _mk_member(m) for m in (self.members or [])]
        if not self.main_end:
            self.main_end = END_LABELS[self.mode][0]

    @property
    def end_index(self) -> int:
        labs = END_LABELS.get(self.mode, [])
        return labs.index(self.main_end) if self.main_end in labs else 0

    def lengths(self):
        """(largo en el lado negativo, largo en el lado positivo) segun como termina el principal."""
        k = self.end_index
        return (self.main_len_neg if k != 2 else 0.0, self.main_len_pos if k != 1 else 0.0)


def _mk_member(d) -> Member:
    ok = Member.__dataclass_fields__
    return Member(**{k: v for k, v in dict(d).items() if k in ok})
