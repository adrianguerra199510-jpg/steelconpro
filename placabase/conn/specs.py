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

# La primera es la placa base (el resto del programa); las demas se calculan en placabase/conn/.
CT_BASEPLATE = "Placa base de columna"
CT_SHEAR_TAB = "Conexion de corte — placa simple (viga a viga / viga a columna)"
CONN_TYPES = [CT_BASEPLATE, CT_SHEAR_TAB]

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
        """[(nombre, Vu)] nunca vacia."""
        out = []
        for c in self.combos or []:
            try:
                out.append((str(c[0]), float(c[1])))
            except (IndexError, TypeError, ValueError):
                continue
        return out or [("Comb 1", 25.0)]
