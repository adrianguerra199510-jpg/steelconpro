# -*- coding: utf-8 -*-
"""Genera los ejemplos de conexion de nudo en ejemplos/ (el principal es una columna, una viga o un cordon segun el ejemplo).

    python tools/make_examples.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from steelconpro.model import Project, save_book
from tools import node_presets as PRE
from steelconpro.conn.specs import (CT_NODE, MODE_COL, MODE_BEAM, MODE_CHORD, END_LABELS, Member, Operation, Load,
                                    OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET, OP_COPE, OP_CONT)

OUT = Path(__file__).resolve().parent.parent / "ejemplos"


def _set(nd, name, kind, **kw):
    """Cambia la operacion de conexion del miembro `name` por otra de tipo `kind`."""
    nd.operations = [o for o in nd.operations if not (o.member == name and o.is_connection)]
    nd.operations.append(Operation(kind=kind, member=name, **kw))


def nodo_columna() -> Project:
    """Columna W14X90 intermedia con cuatro vigas (placa extrema extendida, doble angulo, placa simple, alas soldadas) y una diagonal con cartela."""
    p = Project(); p.ctype = CT_NODE; p.element = "CN-01"; p.name = "Ejemplo: columna principal con vigas y una diagonal"
    nd = PRE.build(MODE_COL, "int4", "I", "tab")
    nd.members[0].shape, nd.members[2].shape = "W18X50", "W18X50"
    _set(nd, "V1", OP_EP_EXT)
    _set(nd, "V2", OP_DANG)
    _set(nd, "V3", OP_WELD)
    nd.operations.append(Operation(kind=OP_CONT, member="V3", cont_t=0.5))
    nd.members.append(Member(name="D1", shape="HSS6X6X3/8", steel="ASTM A500 Gr.C (HSS rect.)", az=0.0, el=-40.0, pos=-12.0, L=72.0))
    nd.operations.append(Operation(kind=OP_GUSSET, member="D1", plate_t=0.5))
    nd.loads = [Load("Caso 1", "V1", Vz=-25.0, My=0.0), Load("Caso 1", "V2", Vz=-20.0), Load("Caso 1", "V3", Vz=-25.0), Load("Caso 1", "V4", Vz=-20.0),
                Load("Caso 1", "D1", N=30.0)]
    p.node = nd
    return p


def viga_a_viga() -> Project:
    p = Project(); p.ctype = CT_NODE; p.element = "CN-02"; p.name = "Ejemplo: viga principal con vigas secundarias"
    nd = PRE.build(MODE_BEAM, "sec2", "I", "tab")
    nd.members[0].shape = "W18X35"
    _set(nd, "S1", OP_EP_FLUSH)
    nd.operations.append(Operation(kind=OP_COPE, member="S2", cope_top=2.0, cope_len=4.5))
    nd.members.append(Member(name="S3", shape="W14X22", az=60.0, pos=36.0, off=nd.members[0].off + 1.0, L=48.0))
    nd.operations.append(Operation(kind=OP_DANG, member="S3"))
    nd.loads = [Load("Caso 1", "S1", Vz=-20.0), Load("Caso 1", "S2", Vz=-25.0), Load("Caso 1", "S3", Vz=-10.0)]
    p.node = nd
    return p


def cruceta() -> Project:
    p = Project(); p.ctype = CT_NODE; p.element = "CN-03"; p.name = "Ejemplo: cordón principal con diagonales"
    nd = PRE.build(MODE_CHORD, "V", "HSS", "gus_bolt")
    nd.members.append(Member(name="M1", shape="HSS4X4X1/4", steel="ASTM A500 Gr.C (HSS rect.)", az=0.0, el=-90.0, pos=0.0, L=48.0))
    nd.operations.append(Operation(kind=OP_GUSSET, member="M1"))
    nd.loads = [Load("Caso 1", "D1", N=-35.0), Load("Caso 1", "D2", N=35.0), Load("Caso 1", "M1", N=0.0)]
    p.node = nd
    return p


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fn, mk in (("CN-01_columna_con_vigas.scp", nodo_columna), ("CN-02_viga_con_secundarias.scp", viga_a_viga), ("CN-03_cordon_con_diagonales.scp", cruceta)):
        save_book(str(OUT / fn), [mk()])
        print("->", OUT / fn)
