# -*- coding: utf-8 -*-
"""Geometrias y conexiones tipo de los tres modulos (asistente Clase / Geometria / Diseño).

    GEOMS[modo]  -> [(clave, nombre, fn(seccion) -> Nodo)]       configuraciones iniciales del nudo
    DESIGNS[modo] -> [(grupo, [(clave, nombre, tipo de conexion)])]   conexiones que se asignan a todos los miembros
    build(modo, geom, seccion, design) -> Nodo

`seccion` es 'I' (perfiles I), 'HSS' (rectangulares) o 'RND' (circulares).  Despues de elegir, todo se puede editar miembro por miembro.
"""
from __future__ import annotations
import copy

from ..shapes import CATALOG
from .specs import (Nodo, Member, MODE_COL, MODE_BEAM, MODE_CHORD, END_LABELS, MEMBER_NAMES,
                    CK_BLANK, CK_TAB, CK_DANG, CK_SEAT, CK_EP_FLUSH, CK_EP_EXT, CK_WELD, CK_GUSSET, CK_GUSSET_W)

SECTION_KEYS = [("I", "Perfil I (W)"), ("HSS", "HSS rectangular"), ("RND", "HSS circular")]
DIAG_MIN = 10.0

MAIN_SHAPES = {MODE_COL: {"I": "W14X90", "HSS": "HSS12X12X1/2", "RND": "HSS12.750X0.500"},
               MODE_BEAM: {"I": "W24X55", "HSS": "HSS12X8X1/2", "RND": "HSS12.750X0.500"},
               MODE_CHORD: {"I": "W14X61", "HSS": "HSS10X10X3/8", "RND": "HSS10.750X0.375"}}
MEMBER_SHAPES = {MODE_COL: {"I": "W16X31", "HSS": "HSS8X4X3/8", "RND": "HSS6.625X0.280"},
                 MODE_BEAM: {"I": "W16X31", "HSS": "HSS8X4X3/8", "RND": "HSS6.625X0.280"},
                 MODE_CHORD: {"I": "HSS4X4X1/4", "HSS": "HSS4X4X1/4", "RND": "HSS4.500X0.237"}}
MEMBER_STEEL = {"I": "ASTM A992", "HSS": "ASTM A500 Gr.C (HSS rect.)", "RND": "ASTM A500 Gr.C (HSS red.)"}


def _depth(label: str) -> float:
    s = CATALOG.get(label)
    return float(s.d) if s is not None else 12.0


def _steel_for(label: str, key: str) -> str:
    """Acero por omision de una seccion (A992 para I; A500 Gr.C para HSS, si el catalogo de materiales lo tiene)."""
    from .. import materials as M
    names = [x.name for x in M.SHAPE_STEELS]
    want = MEMBER_STEEL.get(key, "ASTM A992")
    if want in names:
        return want
    for nm in names:
        if key != "I" and "A500" in nm:
            return nm
    return "ASTM A992" if "ASTM A992" in names else names[0]


def _member(mode, sec, idx, az=0.0, el=0.0, pos=0.0, off=0.0, L=48.0, conn=CK_TAB):
    lab = MEMBER_SHAPES[mode][sec]
    nm = f"{MEMBER_NAMES[mode][0]}{idx}" if mode != MODE_BEAM else f"S{idx}"
    if mode == MODE_CHORD:
        nm = f"D{idx}"
    return Member(name=nm, shape=lab, steel=_steel_for(lab, sec), az=az, el=el, pos=pos, off=off, L=L, conn=conn)


def _main(mode, sec, **kw):
    lab = MAIN_SHAPES[mode][sec]
    return Nodo(mode=mode, main_shape=lab, main_steel=_steel_for(lab, sec), **kw)


# ---------------------------------------------------------------------------------------------- nudo viga-columna
def _col(ends, azs, sec, flush=True):
    nd = _main(MODE_COL, sec)
    nd.main_end = END_LABELS[MODE_COL][ends]
    ds = _depth(MEMBER_SHAPES[MODE_COL][sec])
    nd.members = [_member(MODE_COL, sec, i + 1, az=a, pos=(-ds / 2.0 if (ends == 1 and flush) else 0.0)) for i, a in enumerate(azs)]
    return nd


# ---------------------------------------------------------------------------------------------- viga a viga
def _bb(azs, sec, offs=None):
    nd = _main(MODE_BEAM, sec)
    dm, ds = _depth(MAIN_SHAPES[MODE_BEAM][sec]), _depth(MEMBER_SHAPES[MODE_BEAM][sec])
    flush = max((dm - ds) / 2.0, 0.0)                  # parte alta de la secundaria a ras de la viga principal
    nd.members = [_member(MODE_BEAM, sec, i + 1, az=a, off=flush if offs is None else offs[i]) for i, a in enumerate(azs)]
    return nd


# ---------------------------------------------------------------------------------------------- crucetas (diagonales sobre un cordon)
def _truss(items, sec):
    nd = _main(MODE_CHORD, sec)
    nd.members = [_member(MODE_CHORD, sec, i + 1, az=az, el=el, conn=CK_GUSSET, L=60.0) for i, (az, el) in enumerate(items)]
    return nd


GEOMS = {
    MODE_COL: [
        ("ext1", "Columna de extremo con una viga", lambda s: _col(1, [0.0], s)),
        ("int1", "Columna intermedia con una viga", lambda s: _col(0, [0.0], s)),
        ("int2", "Columna intermedia con dos vigas opuestas", lambda s: _col(0, [0.0, 180.0], s)),
        ("int4", "Columna intermedia con cuatro vigas", lambda s: _col(0, [0.0, 90.0, 180.0, 270.0], s)),
        ("ext2", "Columna de extremo con dos vigas opuestas", lambda s: _col(1, [0.0, 180.0], s)),
    ],
    MODE_BEAM: [
        ("sec1", "Una viga secundaria", lambda s: _bb([90.0], s)),
        ("sec2", "Dos vigas secundarias opuestas", lambda s: _bb([90.0, 270.0], s)),
        ("skew", "Una viga secundaria esviada (60°)", lambda s: _bb([60.0], s)),
        ("skew2", "Dos vigas secundarias en V", lambda s: _bb([60.0, 120.0], s)),
    ],
    MODE_CHORD: [
        ("V", "Dos diagonales en V", lambda s: _truss([(0.0, -45.0), (180.0, -45.0)], s)),
        ("N", "Diagonal y montante", lambda s: _truss([(0.0, -90.0), (0.0, -45.0)], s)),
        ("X", "Cruz: dos diagonales a cada lado", lambda s: _truss([(0.0, -45.0), (180.0, -45.0), (0.0, 45.0), (180.0, 45.0)], s)),
        ("D", "Una diagonal", lambda s: _truss([(0.0, -45.0)], s)),
    ],
}

DESIGNS = {
    MODE_COL: [("Conexión de momento", [("ep_flush", "Placa extrema a ras", CK_EP_FLUSH), ("ep_ext", "Placa extrema extendida", CK_EP_EXT),
                                         ("weld", "Alas soldadas, alma atornillada", CK_WELD)]),
               ("Conexión de corte", [("tab", "Placa simple", CK_TAB), ("dang", "Doble ángulo", CK_DANG), ("seat", "Asiento", CK_SEAT)]),
               ("Conexión en blanco", [("blank", "En blanco", CK_BLANK)])],
    MODE_BEAM: [("Conexión de momento", [("ep_flush", "Placa extrema a ras", CK_EP_FLUSH), ("ep_ext", "Placa extrema extendida", CK_EP_EXT),
                                          ("weld", "Alas soldadas, alma atornillada", CK_WELD)]),
                ("Conexión de corte", [("tab", "Placa simple", CK_TAB), ("dang", "Doble ángulo", CK_DANG), ("seat", "Asiento", CK_SEAT)]),
                ("Conexión en blanco", [("blank", "En blanco", CK_BLANK)])],
    MODE_CHORD: [("Conexión de truss", [("gus_bolt", "Cartela atornillada", CK_GUSSET), ("gus_weld", "Cartela con diagonales soldadas", CK_GUSSET_W)]),
                 ("Conexión en blanco", [("blank", "En blanco", CK_BLANK)])],
}


def design_kind(mode, key):
    for _g, items in DESIGNS[mode]:
        for k, _nm, ck in items:
            if k == key:
                return ck
    return CK_BLANK


def apply_design(nd: Nodo, design_key: str) -> Nodo:
    """Asigna la conexion elegida a todos los miembros; las diagonales llevan cartela (salvo en blanco)."""
    ck = design_kind(nd.mode, design_key)
    for m in nd.members:
        if ck == CK_BLANK:
            m.conn = CK_BLANK
        elif abs(m.el) >= DIAG_MIN or nd.mode == MODE_CHORD:
            m.conn = CK_GUSSET_W if ck == CK_GUSSET_W else CK_GUSSET
        else:
            m.conn = ck
    return nd


def build(mode: str, geom: str, sec: str = "I", design: str = None) -> Nodo:
    fn = next(f for k, _n, f in GEOMS[mode] if k == geom)
    nd = fn(sec)
    if design is None:
        design = {MODE_COL: "tab", MODE_BEAM: "tab", MODE_CHORD: "gus_bolt"}[mode]
    return apply_design(nd, design)


def default_nodo(mode: str) -> Nodo:
    geom = {MODE_COL: "int2", MODE_BEAM: "sec2", MODE_CHORD: "V"}[mode]
    return build(mode, geom, "I")


def new_member(nd: Nodo) -> Member:
    """Miembro nuevo para el boton Agregar: copia el ultimo y lo gira para no quedar encima."""
    n = len(nd.members) + 1
    if nd.members:
        m = copy.deepcopy(nd.members[-1])
        m.az = (m.az + 90.0) % 360.0 if nd.mode == MODE_COL else m.az
        m.name = f"{MEMBER_NAMES[nd.mode][0] if nd.mode != MODE_BEAM else 'S'}{n}"
        if nd.mode == MODE_CHORD:
            m.name = f"D{n}"
            m.az = (m.az + 180.0) % 360.0
        if nd.mode == MODE_BEAM:
            m.az = (m.az + 180.0) % 360.0
        return m
    sec = "I"
    return _member(nd.mode, sec, n, az=0.0 if nd.mode != MODE_BEAM else 90.0, el=-45.0 if nd.mode == MODE_CHORD else 0.0,
                   conn=CK_GUSSET if nd.mode == MODE_CHORD else CK_TAB)
