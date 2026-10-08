# -*- coding: utf-8 -*-
"""Genera los ejemplos de los modulos de nudo en ejemplos/ (solo geometria).

    python tools/make_examples.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from steelconpro.model import Project, save_book
from steelconpro.conn import presets as PRE
from steelconpro.conn.specs import (CT_NODE, CT_B2B, CT_TRUSS, MODE_COL, MODE_BEAM, MODE_CHORD, END_LABELS, Member,
                                    CK_TAB, CK_DANG, CK_SEAT, CK_EP_FLUSH, CK_EP_EXT, CK_WELD, CK_GUSSET)

OUT = Path(__file__).resolve().parent.parent / "ejemplos"


def nodo_columna() -> Project:
    """Columna W14X90 intermedia: viga con placa extrema a un lado, viga con placa simple al otro, viga por el alma con doble angulo y una diagonal con cartela."""
    p = Project(); p.ctype = CT_NODE; p.element = "NC-01"; p.name = "Ejemplo de nudo viga-columna"
    nd = PRE.build(MODE_COL, "int4", "I", "tab")
    nd.members[0].conn, nd.members[0].shape = CK_EP_EXT, "W18X50"
    nd.members[1].conn, nd.members[1].shape = CK_DANG, "W16X31"
    nd.members[2].conn, nd.members[2].shape = CK_TAB, "W18X50"
    nd.members[3].conn, nd.members[3].shape = CK_WELD, "W16X31"
    diag = Member(name="D1", shape="HSS6X6X3/8", steel="ASTM A500 Gr.C (HSS rect.)", az=0.0, el=-40.0, pos=-12.0, L=72.0, conn=CK_GUSSET, plate_t=0.5)
    nd.members.append(diag)
    p.ncol = nd
    return p


def viga_a_viga() -> Project:
    p = Project(); p.ctype = CT_B2B; p.element = "VV-01"; p.name = "Ejemplo de viga a viga"
    nd = PRE.build(MODE_BEAM, "sec2", "I", "tab")
    nd.members[0].conn, nd.members[0].shape = CK_EP_FLUSH, "W18X35"
    nd.members[1].conn, nd.members[1].shape = CK_TAB, "W16X31"
    nd.members.append(Member(name="S3", shape="W14X22", az=60.0, pos=36.0, off=nd.members[0].off + 1.0, conn=CK_DANG, L=48.0))
    p.nbb = nd
    return p


def cruceta() -> Project:
    p = Project(); p.ctype = CT_TRUSS; p.element = "CR-01"; p.name = "Ejemplo de crucetas"
    nd = PRE.build(MODE_CHORD, "V", "HSS", "gus_bolt")
    nd.members.append(Member(name="M1", shape="HSS4X4X1/4", steel="ASTM A500 Gr.C (HSS rect.)", az=0.0, el=-90.0, pos=0.0, L=48.0, conn=CK_GUSSET))
    p.ntr = nd
    return p


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fn, mk in (("NC-01_nudo_viga_columna.scp", nodo_columna), ("VV-01_viga_a_viga.scp", viga_a_viga), ("CR-01_crucetas.scp", cruceta)):
        save_book(str(OUT / fn), [mk()])
        print("->", OUT / fn)
