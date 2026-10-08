# -*- coding: utf-8 -*-
"""Datos de las tipologias de conexion distintas de la placa base.

Solo dataclasses y listas de catalogo, sin importar nada del resto del programa:
`model.py` importa este modulo para guardar la tipologia dentro de `Project`, asi
que aqui no puede importarse `model` (importacion circular).

Para agregar una tipologia:
  1. su dataclass aqui y su nombre en CONN_TYPES;
  2. un campo en `Project` (model.py) con ese dataclass;
  3. un modulo en `placabase/conn/` con `NAME` y `solve(prj, detail) -> Results`,
     registrado en `conn/__init__.py`.
Unidades internas: in, kip, ksi.
"""
from __future__ import annotations
from dataclasses import dataclass, field

def loads_of(combos, nvals: int, default):
    """[(nombre, (v1, v2, ...))] a partir de [[nombre, v1, v2, ...], ...]; nunca vacia."""
    out = []
    for c in combos or []:
        try:
            out.append((str(c[0]), tuple(float(x) for x in c[1:1 + nvals])))
        except (IndexError, TypeError, ValueError):
            continue
        if len(out[-1][1]) != nvals:
            out.pop()
    return out or [(default[0], tuple(default[1]))]


# La primera es la placa base (el resto del programa); las demas se calculan en placabase/conn/.
CT_BASEPLATE = "Placa base de columna"
CT_SHEAR_TAB = "Conexion de corte — placa simple (viga a viga / viga a columna)"
CT_DOUBLE_ANGLE = "Conexion de corte — doble angulo (viga a viga / viga a columna)"
CT_SEATED = "Conexion de asiento (seated) — angulo o rigidizado"
CT_BEAM_SPLICE = "Empalme de viga — placas de alas y alma atornilladas"
CT_COL_SPLICE = "Empalme de columna — placas atornilladas (con o sin contacto)"
CT_ENDPLATE = "Placa extrema a momento — a ras o extendida (viga a columna)"
CONN_TYPES = [CT_BASEPLATE, CT_SHEAR_TAB, CT_DOUBLE_ANGLE, CT_SEATED, CT_BEAM_SPLICE, CT_COL_SPLICE, CT_ENDPLATE]

# ---- placa simple de corte (shear tab)
SUP_KINDS = ["Alma de viga maestra", "Alma de columna", "Ala de columna"]
BOLT_GRADES = ["A325-N", "A325-X", "A490-N", "A490-X", "A307"]
SHEAR_BOLT_SIZES = ["5/8", "3/4", "7/8", "1", "1-1/8"]


@dataclass
class ShearTab:
    """Viga apoyada (secundaria) unida con una placa simple soldada al soporte y atornillada al alma."""
    # --- viga apoyada (secundaria)
    beam: str = "W16X31"
    beam_steel: str = "ASTM A992"
    # --- soporte
    sup_kind: str = "Alma de viga maestra"
    sup_label: str = "W24X55"
    sup_steel: str = "ASTM A992"
    # --- pernos (una sola fila vertical, agujeros estandar)
    bolt_size: str = "3/4"
    bolt_grade: str = "A325-N"
    n: int = 3                   # pernos en la fila (2 a 12 en la configuracion convencional)
    s: float = 3.0               # separacion vertical, in
    a: float = 3.0               # distancia de la soldadura a la fila de pernos, in
    # --- placa
    tp: float = 0.375
    plate_steel: str = "ASTM A36"
    lev_p: float = 1.5           # distancia vertical al borde (extremos de la placa), in
    leh_p: float = 1.5           # distancia horizontal del perno al borde libre de la placa, in
    # --- posicion respecto a la viga
    gap: float = 0.5             # retranqueo del extremo de la viga respecto a la cara del soporte, in
    y_top: float = -1.0          # del tope de la viga al perno superior, in (-1 = centrado en el alma que queda)
    # --- cope (despatinado) de la viga apoyada
    cope_top: float = 0.0        # profundidad del cope superior, in (0 = sin cope)
    cope_bot: float = 0.0        # profundidad del cope inferior, in
    cope_len: float = 0.0        # longitud del cope desde el extremo de la viga, in
    top_flush: bool = False      # tope de la viga a ras con el de la viga maestra (solo informa el cope minimo)
    # --- soldadura placa-soporte (filete a ambos lados)
    weld_size: float = 0.25
    electrode: str = "E70XX"
    weld_dir: bool = True        # incremento direccional AISC J2-5
    # --- reacciones factorizadas de la viga: [nombre, Vu (kip)]
    combos: list = field(default_factory=lambda: [["Comb 1", 25.0]])
    combo_idx: int = 0

    def loads(self) -> list:
        """[(nombre, (Vu,))] nunca vacia."""
        return loads_of(self.combos, 1, ("Comb 1", (25.0,)))


# ---- doble angulo
DA_ATTACH = ["Atornillado al soporte", "Soldado al soporte"]


@dataclass
class DoubleAngle:
    """Viga apoyada con dos angulos en el alma (pernos en doble corte) y atornillados o soldados al soporte."""
    beam: str = "W16X31"
    beam_steel: str = "ASTM A992"
    sup_kind: str = "Alma de viga maestra"
    sup_label: str = "W24X55"
    sup_steel: str = "ASTM A992"
    # --- angulos
    angle: str = "L4X4X3/8"
    angle_steel: str = "ASTM A36"
    long_on_support: bool = True     # en angulos de lados distintos: la pierna larga va contra el soporte
    L_ang: float = 9.0               # largo (altura) de los angulos, in
    attach: str = "Atornillado al soporte"
    # --- pernos
    bolt_size: str = "3/4"
    bolt_grade: str = "A325-N"
    n: int = 3                       # pernos por fila (alma y pierna del soporte)
    s: float = 3.0
    gw: float = 2.0                  # del respaldo de la pierna del soporte a la fila de pernos del alma (= a), in
    gs: float = 2.0                  # del respaldo de la pierna del alma a la fila de pernos del soporte, in
    # --- soldadura (angulos soldados al soporte)
    weld_size: float = 0.25
    electrode: str = "E70XX"
    weld_dir: bool = True
    weld_lines: int = 1              # lineas de soldadura por angulo: 1 = solo el borde exterior; 2 = ambos bordes verticales
    # --- posicion respecto a la viga y cope
    gap: float = 0.5
    y_top: float = -1.0
    cope_top: float = 0.0
    cope_bot: float = 0.0
    cope_len: float = 0.0
    top_flush: bool = False
    combos: list = field(default_factory=lambda: [["Comb 1", 40.0]])
    combo_idx: int = 0

    def loads(self) -> list:
        return loads_of(self.combos, 1, ("Comb 1", (40.0,)))


# ---- asiento
SEAT_TYPES = ["Sin rigidizar (angulo de asiento)", "Rigidizado (placa de asiento y rigidizador)"]
SEAT_ATTACH = ["Atornillado al soporte", "Soldado al soporte"]


@dataclass
class Seated:
    """Viga apoyada sobre un asiento: angulo sin rigidizar o rigidizador de placa, con angulo superior de estabilidad."""
    beam: str = "W16X31"
    beam_steel: str = "ASTM A992"
    sup_kind: str = "Ala de columna"
    sup_label: str = "W14X90"
    sup_steel: str = "ASTM A992"
    seat_type: str = "Sin rigidizar (angulo de asiento)"
    # --- comunes
    L_seat: float = 8.0              # ancho del asiento (a lo largo del soporte), in
    setback: float = 0.75            # del soporte al extremo de la viga, in
    N: float = 3.5                   # longitud de apoyo de la viga sobre el asiento, in
    # --- asiento sin rigidizar
    angle: str = "L6X6X3/4"
    angle_steel: str = "ASTM A36"
    long_horizontal: bool = True     # la pierna larga es la horizontal (la que recibe la viga)
    attach: str = "Atornillado al soporte"
    bolt_size: str = "3/4"
    bolt_grade: str = "A325-N"
    n: int = 2                       # filas de pernos en la pierna vertical (dos columnas por fila)
    s: float = 3.0
    yb: float = 1.25                 # del fondo del asiento a la fila inferior de pernos, in
    gs: float = 4.0                  # separacion entre las dos columnas de pernos, in
    weld_size: float = 0.3125
    electrode: str = "E70XX"
    weld_dir: bool = True
    # --- asiento rigidizado
    st_W: float = 5.0                # ancho (proyeccion) del rigidizador, in
    st_H: float = 8.0                # alto del rigidizador, in
    st_t: float = 0.625
    st_steel: str = "ASTM A36"
    st_weld: float = 0.3125
    # --- reaccion factorizada
    combos: list = field(default_factory=lambda: [["Comb 1", 25.0]])
    combo_idx: int = 0

    def loads(self) -> list:
        return loads_of(self.combos, 1, ("Comb 1", (25.0,)))


# ---- empalmes atornillados de perfiles I (viga y columna)
SPLICE_SHARE = ["Las alas toman todo el momento", "Momento repartido segun la inercia (alas / alma)"]


@dataclass
class _SpliceBase:
    shape: str = "W16X50"
    steel: str = "ASTM A992"
    plate_steel: str = "ASTM A36"
    gap: float = 0.5                 # separacion entre los extremos de los perfiles, in
    # --- alas: placa exterior (una por ala) e interiores (dos por ala; 0 = sin ellas)
    fo_b: float = 7.0
    fo_t: float = 0.625
    fi_b: float = 0.0
    fi_t: float = 0.0
    bolt_size: str = "7/8"
    bolt_grade: str = "A325-N"
    f_rows: int = 3                  # filas de pernos a lo largo del perfil, a cada lado del empalme
    f_cols: int = 2                  # pernos a lo ancho del ala (2 o 4)
    f_s: float = 3.0
    f_g: float = 3.5                 # separacion entre columnas de pernos a lo ancho
    f_end: float = 1.5               # del extremo del perfil a la primera fila
    f_pend: float = 1.5              # de la ultima fila al extremo de la placa
    # --- alma: dos placas, una a cada lado
    w_t: float = 0.375
    w_h: float = 9.0
    w_nv: int = 3
    w_nh: int = 1
    w_sv: float = 3.0
    w_sh: float = 3.0
    w_end: float = 2.0
    w_pend: float = 1.5
    wbolt_size: str = "3/4"
    # --- reparto del momento
    share: str = "Las alas toman todo el momento"
    combos: list = field(default_factory=list)
    combo_idx: int = 0


@dataclass
class BeamSplice(_SpliceBase):
    combos: list = field(default_factory=lambda: [["Comb 1", 1200.0, 30.0, 0.0]])    # [nombre, Mu, Vu, Nu(+ traccion)]

    def loads(self) -> list:
        return loads_of(self.combos, 3, ("Comb 1", (1200.0, 30.0, 0.0)))


@dataclass
class ColSplice(_SpliceBase):
    shape: str = "W14X90"
    fo_b: float = 8.0
    fo_t: float = 0.75
    f_g: float = 4.0
    w_h: float = 10.0
    contact: bool = True             # extremos aserrados o fresados en contacto (J1.4)
    combos: list = field(default_factory=lambda: [["Comb 1", 400.0, 300.0, 20.0]])   # [nombre, Pu(+ compresion), Mu, Vu]

    def loads(self) -> list:
        return loads_of(self.combos, 3, ("Comb 1", (400.0, 300.0, 20.0)))


# ---- placa extrema a momento
EP_FLANGE_WELD = ["CJP (penetracion completa)", "Filete a ambos lados"]


@dataclass
class EndPlate:
    """Viga con placa extrema soldada, atornillada al ala de la columna. Una fila de pernos (2) dentro de cada ala y,
    si se pide, una fila (2) fuera de cada ala (placa extendida)."""
    beam: str = "W18X50"
    beam_steel: str = "ASTM A992"
    col: str = "W14X90"
    col_steel: str = "ASTM A992"
    cont_plates: bool = False        # placas de continuidad en la columna (se omiten las verificaciones locales del ala y del alma)
    plate_steel: str = "ASTM A572 Gr.50"
    bp: float = 8.0                  # ancho de la placa extrema
    tp: float = 1.0
    bolt_size: str = "7/8"
    bolt_grade: str = "A325-N"
    g: float = 5.5                   # gramil de los pernos (entre las dos columnas)
    pfo: float = 2.0                 # de la cara exterior del ala a la fila exterior de pernos
    pfi: float = 2.0                 # de la cara interior del ala a la fila interior de pernos
    e_ext: float = 1.5               # de la fila exterior al borde de la placa
    ext_t: bool = True               # fila exterior en el lado traccionado (placa extendida)
    ext_c: bool = True               # fila exterior en el lado comprimido
    # --- soldaduras viga-placa
    fw_type: str = "CJP (penetracion completa)"
    fw_size: float = 0.5             # cateto del filete (si es filete) o espesor de garganta de referencia
    ww_size: float = 0.3125          # filete del alma, a ambos lados
    electrode: str = "E70XX"
    weld_dir: bool = True
    combos: list = field(default_factory=lambda: [["Comb 1", 1800.0, 40.0]])    # [nombre, Mu (+ traccion arriba), Vu]

    def loads(self) -> list:
        return loads_of(self.combos, 2, ("Comb 1", (1800.0, 40.0)))

