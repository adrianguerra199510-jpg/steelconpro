# -*- coding: utf-8 -*-
"""Biblioteca de ejemplos TP-G: conexiones típicas de edificios que se arman con operaciones generales (placas, ángulos, pernos entre elementos, huecos,
soldaduras y recortes).  Cada ejemplo es un archivo `ejemplos/TP-Gnn_<nombre>.scp`.

    python3 tools/ejemplos_generales.py            (escribe los archivos)
    python3 tools/ejemplos_generales.py --revisa   (además corre el revisor de geometría y las verificaciones sobre cada uno)
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from steelconpro.model import Project, save_book, load_book
from steelconpro.conn import ops as OPS
from steelconpro.conn.specs import (CT_NODE, END_LABELS, Member, Operation, Load, Nodo, OP_PLATE, OP_BOLTS, OP_FILLET, OP_HOLE, OP_ANGLE, OP_TRIM, OP_WORKPLANE,
                                    OP_BASE, PLATE_SHAPES, PLATE_ORIENTS, ATTACHES, WELD_MODES, WELD_TYPES, WELD_SIDES, TRIM_MODES, OPENINGS, HOLE_SHAPES,
                                    FACES_I, FACES_END, FACES_PLATE, FACES_ANGLE)

OUT = Path(__file__).resolve().parent.parent / "ejemplos"
RECT, TRI, CLIP, CIRC, TRAP, SLOT, FREE = PLATE_SHAPES
PAR, PERP_T, PERP_L = PLATE_ORIENTS
WELD, BOLT, FREE_ATT = ATTACHES
S_BOTH, S_1, S_2 = WELD_SIDES
FILLET, CJP, PJP = WELD_TYPES
M_FACE, M_MITER, M_VOL = TRIM_MODES
F_TOP, F_BOT, F_WEBP, F_WEBM, F_END0, F_END1, F_TOPI, F_BOTI = FACES_I
A36, A992 = "ASTM A36", "ASTM A992"
HSS_STEEL = "ASTM A500 Gr.C (HSS rect.)"


def gen(nd, kind, **kw):
    return OPS.add_operation(nd, kind, **kw)


def project(code, title, nd):
    p = Project()
    p.ctype = CT_NODE
    p.element = code
    p.name = f"Ejemplo: {title}"
    p.node = nd
    return p


def column(shape="W14X90", length=60.0, end=0, **kw):
    """Principal vertical (columna) sin miembros ni operaciones."""
    nd = Nodo(main_name="Columna", main_shape=shape, main_steel=A992 if shape.startswith("W") else HSS_STEEL, main_el=90.0, main_len_neg=length, main_len_pos=length, **kw)
    nd.main_end = END_LABELS[end]
    nd.operations, nd.members, nd.loads = [], [], []
    return nd


def beam(shape="W24X55", length=60.0, end=0, **kw):
    nd = Nodo(main_name="Viga", main_shape=shape, main_steel=A992 if shape.startswith("W") else HSS_STEEL, main_el=0.0, main_len_neg=length, main_len_pos=length, **kw)
    nd.main_end = END_LABELS[end]
    nd.operations, nd.members, nd.loads = [], [], []
    return nd


def splice_member(name, shape, el, L, gap=0.0, az=0.0):
    return Member(name=name, shape=shape, steel=A992 if shape.startswith("W") else HSS_STEEL, az=az, el=el, pos=0.0, L=L, gap=gap)


def bolt_group(nd, plate, face, targets, s, u, rows, cols, sp, g, size="3/4", **kw):
    return gen(nd, OP_BOLTS, parent=plate, face=face, targets=list(targets), pl_s=s, pl_u=u, rows=rows, cols=cols, bolt_s=sp, bolt_g=g, bolt_size=size, **kw)


# ================================================================================================== empalmes
def g01_empalme_columna_atornillado() -> Project:
    """Empalme atornillado de una columna W14X90: cubrejuntas en las dos alas (por fuera) y en el alma (a los dos lados), pernos a ambos lados del empalme."""
    nd = column(end=1)                                                           # el principal termina en el nudo (empalme) y la columna de arriba sigue
    nd.members = [splice_member("C2", "W14X90", 90.0, 60.0, gap=0.0)]
    s0 = nd.main_len_neg                                                         # posición del empalme medida desde el inicio de la columna inferior
    for nm, face in (("PA1", F_TOP), ("PA2", F_BOT)):                            # cubrejuntas de ala, por la cara exterior
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, shape=RECT, pl_L=36.0, pl_W=8.0, pl_s=s0, plate_t=0.5, attach=FREE_ATT, plate_steel=A36)
    for nm, face in (("PW1", F_WEBP), ("PW2", F_WEBM)):                          # cubrejuntas de alma, una a cada lado
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, shape=RECT, pl_L=24.0, pl_W=8.0, pl_s=s0, plate_t=0.375, attach=FREE_ATT, plate_steel=A36)
    for nm, off in (("PA1", 0.0), ("PA2", 2.0)):                                  # los pernos de las dos alas van escalonados 2 in (cada ala tiene su paso de 4 in)
        bolt_group(nd, nm, "Cara +", [nd.main_name], 9.0 + off, 0.0, 3, 2, 4.0, 5.5)       # pernos del lado de la columna inferior
        bolt_group(nd, nm, "Cara +", ["C2"], 27.0 - off, 0.0, 3, 2, 4.0, 5.5)              # pernos del lado de la columna superior
    bolt_group(nd, "PW1", "Cara +", [nd.main_name, "PW2"], 6.0, 0.0, 3, 2, 3.0, 3.5)
    bolt_group(nd, "PW1", "Cara +", ["C2", "PW2"], 18.0, 0.0, 3, 2, 3.0, 3.5)
    nd.loads = [Load("Caso 1", "C2", N=-120.0, Vy=6.0, Vz=0.0, My=300.0)]
    return project("TP-G01", "empalme atornillado de columna W con cubrejuntas de alas y alma", nd)


EXAMPLES = [("TP-G01_empalme_columna_atornillado.scp", g01_empalme_columna_atornillado)]


def main(revisa=False):
    OUT.mkdir(exist_ok=True)
    for fn, mk in EXAMPLES:
        p = mk()
        save_book(str(OUT / fn), [p])
        print("->", OUT / fn)
        if revisa:
            report(p, fn)


def report(p, fn):
    from steelconpro import api
    from steelconpro.conn import assembly as AS, geocheck as GC
    m = AS.build_model(p)
    iss = GC.check(m)
    s = GC.summary(iss)
    print(f"   {fn}: piezas {len(m.parts)} pernos {len(m.bolts)} cordones {len(m.welds)}  errores {s['errors']} avisos {s['warnings']}")
    for n in m.notes:
        print("      nota:", n[:200])
    for e in iss:
        print("      ", e["sev"], e["code"], e["text"][:200])
    try:
        v = api.verify({"connection": api._dump(p)})
        print(f"   verify ok: {len(v['checks'])} verificaciones, D/C máx {v['max_ratio']:.2f}")
    except Exception as e:                                                       # noqa: BLE001
        print("   verify EXCEPCIÓN:", repr(e))


if __name__ == "__main__":
    main("--revisa" in sys.argv)
