# -*- coding: utf-8 -*-
"""Biblioteca de ejemplos TP-G: conexiones típicas de edificios que se arman con operaciones generales (placas, ángulos, pernos entre elementos, huecos,
soldaduras y recortes).  Cada ejemplo es un archivo `ejemplos/TP-Gnn_<nombre>.scp`.

    python3 tools/ejemplos_generales.py            (escribe los archivos)
    python3 tools/ejemplos_generales.py --revisa   (además corre el revisor de geometría y las verificaciones sobre cada uno)
"""
from __future__ import annotations
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from steelconpro.model import Project, save_book, load_book
from steelconpro.conn import ops as OPS
from steelconpro.conn.specs import (CT_NODE, END_LABELS, Member, Operation, Load, Nodo, OP_PLATE, OP_BOLTS, OP_FILLET, OP_HOLE, OP_ANGLE, OP_TRIM, OP_WORKPLANE,
                                    OP_BASE, OP_BLOCK, PLATE_SHAPES, PLATE_ORIENTS, ATTACHES, WELD_MODES, WELD_TYPES, WELD_SIDES, TRIM_MODES, OPENINGS, HOLE_SHAPES,
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


def _model(nd):
    from steelconpro.conn import assembly as AS
    return AS.build_nodo(nd)


def face_uv(nd, element, face, pt):
    """(s, u) del punto global `pt` en la cara `face` del elemento `element` (para colocar pernos y placas sobre un punto de otro elemento)."""
    ff = _model(nd).elems[element]["faces"][face]
    return float((pt - ff.O) @ ff.A), float((pt - ff.O) @ ff.U)


def centre_of(nd, plate):
    return _model(nd).elems[plate]["geo"]["centre"]


def g02_empalme_viga_atornillado() -> Project:
    """Empalme atornillado de una viga W24X55: cubrejuntas exteriores e interiores en cada ala (dos interiores, uno a cada lado del alma) y dos cubrejuntas de alma."""
    nd = beam(end=1)
    nd.members = [splice_member("B2", "W24X55", 0.0, 60.0)]
    s0 = nd.main_len_neg
    for k, (face_o, face_i) in enumerate(((F_TOP, F_TOPI), (F_BOT, F_BOTI))):
        gen(nd, OP_PLATE, name=f"PO{k + 1}", parent=nd.main_name, face=face_o, pl_L=40.0, pl_W=6.0, pl_s=s0, plate_t=0.5, attach=FREE_ATT)
        for j, u in enumerate((-1.9, 1.9)):
            gen(nd, OP_PLATE, name=f"PI{k + 1}{j + 1}", parent=nd.main_name, face=face_i, pl_L=40.0, pl_W=2.6, pl_s=s0, pl_u=u, plate_t=0.375, attach=FREE_ATT)
    for nm, face in (("PW1", F_WEBP), ("PW2", F_WEBM)):
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, pl_L=24.0, pl_W=16.0, pl_s=s0, plate_t=0.375, attach=FREE_ATT)
    for k in range(2):
        off = 0.0 if k == 0 else 2.0                                              # las dos alas escalonadas 2 in (paso de 4 in)
        for j in range(2):
            ci = centre_of(nd, f"PI{k + 1}{j + 1}")
            for lado, x in (("inf", -10.0 - off), ("sup", 10.0 + off)):            # x medida desde el empalme sobre el eje de la viga
                tg = [nd.main_name if lado == "inf" else "B2", f"PI{k + 1}{j + 1}"]
                s, u = face_uv(nd, f"PO{k + 1}", "Cara +", ci + np.array([x, 0.0, 0.0]))
                bolt_group(nd, f"PO{k + 1}", "Cara +", tg, s, u, 3, 1, 4.0, 3.0)
    bolt_group(nd, "PW1", "Cara +", [nd.main_name, "PW2"], 6.0, 0.0, 3, 2, 3.0, 3.5)
    bolt_group(nd, "PW1", "Cara +", ["B2", "PW2"], 18.0, 0.0, 3, 2, 3.0, 3.5)
    nd.loads = [Load("Caso 1", "B2", Vz=-30.0, My=800.0)]
    return project("TP-G02", "empalme atornillado de viga W con cubrejuntas exteriores e interiores en las alas y en el alma", nd)


def g03_empalme_columna_hss() -> Project:
    """Empalme de una columna HSS8X8X1/2 con dos placas laterales y pernos que atraviesan las dos paredes del tubo."""
    nd = column("HSS8X8X1/2", end=1)
    nd.members = [splice_member("C2", "HSS8X8X1/2", 90.0, 60.0)]
    s0 = nd.main_len_neg
    for nm, face in (("PL1", "Cara +X"), ("PL2", "Cara −X")):
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, pl_L=30.0, pl_W=6.0, pl_s=s0, plate_t=0.5, attach=FREE_ATT)
    bolt_group(nd, "PL1", "Cara +", [nd.main_name, "PL2"], 7.5, 0.0, 2, 2, 3.5, 3.0)
    bolt_group(nd, "PL1", "Cara +", ["C2", "PL2"], 22.5, 0.0, 2, 2, 3.5, 3.0)
    nd.loads = [Load("Caso 1", "C2", N=-90.0, Vy=4.0, My=150.0)]
    return project("TP-G03", "empalme de columna HSS con placas laterales y pernos pasantes", nd)


def g04_empalme_soldado_cjp() -> Project:
    """Empalme soldado a tope de una columna W: la columna superior apoya en la inferior y se une con soldadura de penetración completa (CJP) en todo el contorno."""
    nd = column(end=1)
    nd.members = [splice_member("C2", "W14X90", 90.0, 60.0, gap=-0.5)]
    gen(nd, OP_FILLET, weld_mode=WELD_MODES[1], targets=["C2"], parent=nd.main_name, face=F_END1, weld_type=CJP, weld_size=0.5)
    nd.loads = [Load("Caso 1", "C2", N=-100.0, Vy=5.0, My=200.0)]
    return project("TP-G04", "empalme soldado a tope (CJP) de columna W", nd)


def _stiffeners(nd, z, tag, t=0.5):
    """Placas de continuidad: dos (una a cada lado del alma) a la altura `z` (distancia al inicio del principal), soldadas al alma y a las dos alas."""
    from steelconpro.conn.specs import Operation
    out = []
    for k, face in enumerate((F_WEBP, F_WEBM)):
        nm = f"{tag}{k + 1}"
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, role="Rigidizador", orient=PERP_T, shape=CLIP, pl_L=12.58, pl_W=6.6, pl_clip=0.75,
            pl_s=z, plate_t=t, plate_steel=A36, weld_size=0.25)
        gen(nd, OP_FILLET, weld_main=nm, weld_to=[[nd.main_name, F_TOPI], [nd.main_name, F_BOTI]], weld_size=0.25)
        out.append(nm)
    return out


def g05_rigidizadores_columna() -> Project:
    """Columna W14X90 con placas de continuidad (dos niveles, a los dos lados del alma) soldadas al alma y a las caras interiores de las alas, y una placa diagonal del alma recortada contra las alas."""
    nd = column(end=0)
    z0 = nd.main_len_neg
    _stiffeners(nd, z0 + 0.0, "CA")
    _stiffeners(nd, z0 + 14.0, "CB")
    d = gen(nd, OP_PLATE, name="DG", parent=nd.main_name, face=F_WEBP, role="Rigidizador", orient=PERP_T, shape=RECT, pl_L=24.0, pl_W=6.6, pl_s=z0 + 7.0, pl_rot=45.0,
            plate_t=0.375, plate_steel=A36, weld_size=0.1875)
    for face in (F_TOPI, F_BOTI):
        gen(nd, OP_TRIM, targets=["DG"], parent=nd.main_name, face=face)
        gen(nd, OP_FILLET, weld_main="DG", weld_to=[[nd.main_name, face]], weld_size=0.1875)
    nd.loads = [Load("Caso 1", nd.main_name, N=-200.0, side=1)]
    return project("TP-G05", "placas de continuidad y diagonal de alma en una columna W", nd)


def g06_cap_plate_columna() -> Project:
    """Placa de cabeza (cap plate) 18×18×1 de una columna W14X90, soldada al contorno del perfil, con cuatro huecos para los pernos de la viga o el apoyo superior."""
    nd = column(end=1)
    gen(nd, OP_PLATE, name="CP", parent=nd.main_name, face=F_END1, shape=RECT, pl_L=18.0, pl_W=18.0, pl_s=7.25, plate_t=1.0, plate_steel=A36, weld_size=0.375)
    gen(nd, OP_HOLE, parent="CP", face="Cara +", rows=2, cols=2, bolt_s=12.0, bolt_g=12.0, pl_s=9.0, pl_u=0.0, hole_D=1.0)
    nd.loads = [Load("Caso 1", nd.main_name, N=-150.0, side=-1)]
    return project("TP-G06", "placa de cabeza de columna con huecos para pernos", nd)


def g07_placa_base_rigidizada() -> Project:
    """Placa base de una columna W14X90 con cuatro rigidizadores triangulares soldados a las alas (dos por ala) y a la placa base."""
    ref = load_book(str(OUT / "PB-01_W14X90.scp"))[0]
    nd = column(end=2)
    nd.main_len_pos = 72.0
    nd.operations = [Operation(kind=OP_BASE, member=nd.main_name, end=-1)]
    k = 0
    for face in (F_TOP, F_BOT):
        for u in (-3.5, 3.5):
            k += 1
            nm = f"RG{k}"
            gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, role="Rigidizador", orient=PERP_L, shape=TRI, pl_L=10.0, pl_W=3.0, pl_s=5.0, pl_u=u,
                plate_t=0.5, plate_steel=A36, weld_size=0.25)
            gen(nd, OP_FILLET, weld_main=nm, weld_to=[["Placa base", "Cara superior"]], weld_all=False, weld_edges=[2], weld_size=0.25)
    nd.loads = [Load("Caso 1", nd.main_name, N=-150.0, Vy=10.0, side=1)]
    p = project("TP-G07", "placa base con rigidizadores triangulares soldados a las alas", nd)
    for kk in ("plate", "bolts", "lug", "stiff", "welds", "conc", "loads", "fea", "combos"):
        setattr(p, kk, getattr(ref, kk))
    p.u_len, p.u_force, p.u_stress, p.u_moment = ref.u_len, ref.u_force, ref.u_stress, ref.u_moment
    p.combo_list()
    p.apply_combo(0)
    return p


def g08_mensula() -> Project:
    """Ménsula soldada al ala de una columna: repisa de 1 in con soldadura CJP a la columna y dos nervios triangulares soldados a la columna y a la repisa."""
    nd = column(end=0)
    z = nd.main_len_neg                                                          # repisa a la altura del nudo
    gen(nd, OP_PLATE, name="SH", parent=nd.main_name, face=F_TOP, orient=PERP_T, role="Rigidizador", shape=RECT, pl_L=10.0, pl_W=10.0, pl_s=z, plate_t=1.0,
        plate_steel=A36, weld_type=CJP)
    for k, u in enumerate((-3.0, 3.0)):
        nm = f"NV{k + 1}"
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=F_TOP, orient=PERP_L, role="Rigidizador", shape=TRI, pl_L=12.0, pl_W=9.0, pl_rot=180.0, pl_u=u,
            pl_s=z - 0.5 - 6.0, plate_t=0.5, plate_steel=A36, weld_size=0.3125)
        gen(nd, OP_FILLET, weld_main=nm, weld_to=[["SH", "Cara −"]], weld_size=0.3125)
    nd.loads = [Load("Caso 1", nd.main_name, N=-60.0, side=1)]
    return project("TP-G08", "ménsula soldada a una columna con repisa y nervios", nd)


def g09_rodilla_portico() -> Project:
    """Rodilla de pórtico: la viga W18X35 se recorta contra el ala de la columna y se suelda en todo su contorno; la columna lleva placas de continuidad a la altura de las alas de la viga, una diagonal de alma y placa de cabeza."""
    nd = column(end=1)
    nd.members = [Member(name="V1", shape="W18X35", steel=A992, az=0.0, el=0.0, pos=-12.0, L=60.0)]
    z0 = nd.main_len_neg
    zc = z0 - 12.0
    dh = 17.7 / 2.0 - 0.425 / 2.0
    _stiffeners(nd, zc + dh, "CT", 0.425)
    _stiffeners(nd, zc - dh, "CB", 0.425)
    gen(nd, OP_PLATE, name="DG", parent=nd.main_name, face=F_WEBP, role="Rigidizador", orient=PERP_T, shape=RECT, pl_L=24.0, pl_W=6.6, pl_s=zc, pl_rot=53.3,
        plate_t=0.375, plate_steel=A36, weld_size=0.1875)
    gen(nd, OP_TRIM, targets=["DG"], parent="CT1", face="Cara −")                 # la diagonal no pasa de las placas de continuidad
    gen(nd, OP_TRIM, targets=["DG"], parent="CB1", face="Cara +")
    gen(nd, OP_FILLET, weld_main="DG", weld_to=[["CT1", "Cara −"], ["CB1", "Cara +"]], weld_size=0.1875)
    gen(nd, OP_TRIM, targets=["V1"], parent=nd.main_name, face=F_TOP, trim_gap=0.0)
    gen(nd, OP_FILLET, weld_mode=WELD_MODES[1], targets=["V1"], parent=nd.main_name, face=F_TOP, weld_size=0.25)
    gen(nd, OP_PLATE, name="CP", parent=nd.main_name, face=F_END1, shape=RECT, pl_L=16.0, pl_W=16.0, pl_s=7.25, plate_t=0.75, plate_steel=A36, weld_size=0.3125)
    nd.loads = [Load("Caso 1", "V1", Vz=-25.0, My=-900.0), Load("Caso 1", nd.main_name, N=-25.0, side=-1)]
    return project("TP-G09", "rodilla de pórtico con viga recortada, continuidad, diagonal de alma y cabeza", nd)


def g10_cartela_cubierta() -> Project:
    """Cartela de arriostramiento de cubierta sobre el ala superior de una viga W16X31: placa con esquinas recortadas soldada, con seis huecos para los pernos de la diagonal."""
    nd = beam("W16X31", end=0)
    s0 = nd.main_len_neg
    gen(nd, OP_PLATE, name="GC", parent=nd.main_name, face=F_TOP, shape=CLIP, pl_L=14.0, pl_W=5.0, pl_clip=1.0, pl_s=s0, plate_t=0.5, plate_steel=A36, weld_size=0.25, weld_all=True)
    gen(nd, OP_HOLE, parent="GC", face="Cara +", rows=3, cols=2, bolt_s=3.0, bolt_g=2.5, pl_s=7.0, pl_u=0.0)
    nd.loads = [Load("Caso 1", nd.main_name, N=0.0, Vz=-10.0, side=1)]
    return project("TP-G10", "cartela de arriostramiento de cubierta sobre el ala superior de una viga", nd)


def g11_apoyo_sobre_muro() -> Project:
    """Apoyo de una viga W16X31 sobre un muro de concreto (elemento «Bloque de concreto»): placa de apoyo soldada al ala inferior, más ancha que el ala, con huecos ranurados; cuatro anclajes que entran al muro; rigidizadores de apoyo en el alma y ángulo atornillado al alma."""
    nd = beam("W16X31", end=1)
    s0 = nd.main_len_neg - 6.0                                                   # la placa llega al extremo de la viga (x de −12 a 0)
    zb = -(15.9 / 2.0) - 0.75                                                    # cara inferior de la placa de apoyo
    gen(nd, OP_BLOCK, name="MURO", wp_x=-6.0, wp_y=0.0, wp_z=zb, wp_az=0.0, blk_L=24.0, blk_W=16.0, blk_H=24.0)
    gen(nd, OP_PLATE, name="PA", parent=nd.main_name, face=F_BOT, shape=RECT, pl_L=12.0, pl_W=12.0, pl_s=s0, plate_t=0.75, plate_steel=A36, weld_size=0.25)
    gen(nd, OP_HOLE, parent="PA", face="Cara −", rows=2, cols=2, bolt_s=7.0, bolt_g=9.0, pl_s=6.0, pl_u=0.0, hole_shape=HOLE_SHAPES[1], hole_L=2.0, hole_D=0.9375, hole_rot=0.0)
    gen(nd, OP_BOLTS, name="ANC", parent="PA", face="Cara −", targets=["MURO"], rows=2, cols=2, bolt_s=7.0, bolt_g=9.0, pl_s=6.0, pl_u=0.0, bolt_size="3/4", bolt_grade="A307")
    for k, face in enumerate((F_WEBP, F_WEBM)):
        nm = f"RA{k + 1}"
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=face, role="Rigidizador", orient=PERP_T, shape=CLIP, pl_L=15.02, pl_W=2.6, pl_clip=0.75, pl_s=s0, plate_t=0.375,
            plate_steel=A36, weld_size=0.1875)
        gen(nd, OP_FILLET, weld_main=nm, weld_to=[[nd.main_name, F_TOPI], [nd.main_name, F_BOTI]], weld_size=0.1875)
    gen(nd, OP_ANGLE, name="AL", parent=nd.main_name, face=F_WEBP, attach=BOLT, leg_a=4.0, leg_b=4.0, plate_t=0.375, pl_L=6.0, pl_s=s0 - 10.0, rows=2, cols=1, bolt_s=3.0)
    nd.loads = [Load("Caso 1", nd.main_name, Vz=-40.0, side=1)]
    return project("TP-G11", "apoyo de viga sobre muro de concreto con placa, ranuras y anclajes", nd)


def g12_placa_con_aberturas() -> Project:
    """Placa de refuerzo sobre el alma de una columna con abertura circular, abertura rectangular, dos ranuras y esquinas recortadas; soldada en todo su contorno."""
    nd = column(end=0)
    z = nd.main_len_neg
    gen(nd, OP_PLATE, name="PX", parent=nd.main_name, face=F_WEBP, shape=CLIP, pl_L=24.0, pl_W=11.0, pl_clip=1.5, pl_s=z, plate_t=0.5, plate_steel=A36, weld_size=0.25,
        opening=OPENINGS[1], op_D=3.0, op_x=-6.0, op_y=0.0)
    gen(nd, OP_HOLE, parent="PX", face="Cara +", rows=2, cols=1, bolt_s=4.0, pl_s=15.0, pl_u=0.0, hole_shape=HOLE_SHAPES[1], hole_L=2.5, hole_D=1.0, hole_rot=90.0)
    gen(nd, OP_HOLE, parent="PX", face="Cara +", rows=1, cols=2, bolt_g=4.0, pl_s=7.0, pl_u=0.0, hole_shape=HOLE_SHAPES[2], hole_L=1.5, hole_W=1.0)
    nd.loads = [Load("Caso 1", nd.main_name, N=-80.0, side=1)]
    return project("TP-G12", "placa de refuerzo de alma con abertura, huecos rectangulares y ranuras", nd)


def g13_placa_atravesada_por_tubo() -> Project:
    """Repisa en una columna W14X90 atravesada por un tubo HSS6X6X3/8: la repisa lleva una abertura que rodea al tubo y se suelda a él por todo el borde de la abertura."""
    nd = column(end=0)
    nd.members = [Member(name="V1", shape="HSS6X6X3/8", steel=HSS_STEEL, az=0.0, el=90.0, pos=0.0, off=14.0, L=48.0)]
    z = nd.main_len_neg + 20.0
    gen(nd, OP_PLATE, name="PR", parent=nd.main_name, face=F_TOP, orient=PERP_T, role="Rigidizador", shape=RECT, pl_L=14.0, pl_W=14.0, pl_s=z, plate_t=0.75, plate_steel=A36,
        weld_size=0.3125, opening=OPENINGS[3], op_member="V1", op_clear=0.0)
    gen(nd, OP_FILLET, weld_main="PR", weld_to=[["V1", f] for f in ("Cara +X", "Cara −X", "Cara +Y", "Cara −Y")], weld_size=0.25, weld_all=True)
    nd.loads = [Load("Caso 1", "V1", N=-60.0)]
    return project("TP-G13", "repisa atravesada por un tubo con abertura que rodea al miembro", nd)


def g14_placas_recortadas() -> Project:
    """Placas recortadas: una repisa sobre el ala de la columna con muesca contra el volumen de la viga que llega (holgura 1/2 in) y una placa de alma cortada por un plano de trabajo inclinado."""
    nd = column(end=0)
    nd.members = [Member(name="V1", shape="W12X26", steel=A992, az=0.0, el=0.0, pos=0.0, L=48.0)]
    z = nd.main_len_neg
    gen(nd, OP_PLATE, name="PN", parent=nd.main_name, face=F_TOP, shape=RECT, pl_L=20.0, pl_W=12.0, pl_s=z + 7.0, plate_t=0.5, plate_steel=A36, weld_size=0.25)
    gen(nd, OP_TRIM, targets=["PN"], parent="V1", trim_mode=M_VOL, trim_gap=0.5)
    gen(nd, OP_WORKPLANE, name="PT1", wp_x=0.0, wp_y=0.0, wp_z=-24.0, wp_az=0.0, wp_el=30.0, wp_size=40.0)
    gen(nd, OP_PLATE, name="PM", parent=nd.main_name, face=F_WEBP, shape=RECT, pl_L=20.0, pl_W=10.0, pl_s=z - 24.0, plate_t=0.375, plate_steel=A36, weld_size=0.25)
    gen(nd, OP_TRIM, targets=["PM"], parent="PT1", face="Plano")
    gen(nd, OP_TRIM, targets=["V1"], parent=nd.main_name, face=F_TOP, trim_gap=0.0)
    gen(nd, OP_FILLET, weld_mode=WELD_MODES[1], targets=["V1"], parent=nd.main_name, face=F_TOP, weld_size=0.1875)
    nd.loads = [Load("Caso 1", "V1", Vz=-10.0)]
    return project("TP-G14", "placas recortadas contra el volumen de una viga y contra un plano de trabajo", nd)


def g15_modos_soldadura() -> Project:
    """Cinco rigidizadores en el alma de una viga W16X31 con distintos modos de soldadura: filete a ambos lados, filete de un solo lado, CJP, PJP y un cordón intermitente."""
    nd = beam("W16X31", end=0)
    s0 = nd.main_len_neg
    modos = [("RF", FILLET, S_BOTH, 0.0, 0.0), ("RU", FILLET, S_1, 0.0, 0.0), ("RC", CJP, S_BOTH, 0.0, 0.0), ("RP", PJP, S_BOTH, 0.0, 0.0), ("RI", FILLET, S_BOTH, 1.0, 2.0)]
    for k, (nm, wt, ws, wa, wl) in enumerate(modos):
        gen(nd, OP_PLATE, name=nm, parent=nd.main_name, face=F_WEBP, role="Rigidizador", orient=PERP_T, shape=CLIP, pl_L=15.02, pl_W=2.6, pl_clip=0.75, pl_s=s0 - 20.0 + 10.0 * k,
            plate_t=0.375, plate_steel=A36, weld_size=0.1875, weld_type=wt, weld_side=ws, weld_a=wa, weld_len=wl)
        gen(nd, OP_FILLET, weld_main=nm, weld_to=[[nd.main_name, F_TOPI], [nd.main_name, F_BOTI]], weld_size=0.1875, weld_type=wt, weld_side=ws)
    nd.loads = [Load("Caso 1", nd.main_name, Vz=-20.0, side=1)]
    return project("TP-G15", "rigidizadores con soldadura de filete, de un lado, CJP, PJP e intermitente", nd)


def g16_angulo_asiento() -> Project:
    """Viga W12X26 apoyada en un ángulo de asiento soldado al ala de la columna y atornillado al ala inferior de la viga, con un ángulo de unión atornillado a su alma."""
    nd = column(end=0)
    nd.members = [Member(name="V1", shape="W12X26", steel=A992, az=0.0, el=0.0, pos=0.0, L=48.0)]
    z = nd.main_len_neg
    gen(nd, OP_ANGLE, name="AS", parent=nd.main_name, face=F_TOP, attach=WELD, leg_a=5.0, leg_b=5.0, plate_t=0.5, pl_L=6.0, pl_rot=90.0, leg_side=1, pl_s=z - 6.1 - 0.5 + 2.5, pl_u=0.0,
        weld_size=0.25)
    ss, uu = face_uv(nd, "AS", FACES_ANGLE[2], np.array([10.0, 0.0, -6.1 - 0.25]))     # centro del grupo de pernos: sobre el ala de asiento, bajo el ala de la viga
    gen(nd, OP_BOLTS, parent="AS", face=FACES_ANGLE[2], targets=["V1"], rows=1, cols=2, bolt_s=3.0, bolt_g=3.0, pl_s=ss, pl_u=uu)
    gen(nd, OP_ANGLE, name="AC", parent="V1", face=F_WEBP, attach=BOLT, leg_a=4.0, leg_b=3.0, plate_t=0.375, pl_L=6.0, pl_s=3.0, rows=2, cols=1, bolt_s=3.0)
    nd.loads = [Load("Caso 1", "V1", Vz=-20.0)]
    return project("TP-G16", "ángulo de asiento soldado a la columna y atornillado a la viga, y ángulo de unión", nd)


EXAMPLES = [("TP-G01_empalme_columna_atornillado.scp", g01_empalme_columna_atornillado),
            ("TP-G02_empalme_viga_atornillado.scp", g02_empalme_viga_atornillado),
            ("TP-G03_empalme_columna_hss.scp", g03_empalme_columna_hss),
            ("TP-G04_empalme_soldado_cjp.scp", g04_empalme_soldado_cjp),
            ("TP-G05_rigidizadores_columna.scp", g05_rigidizadores_columna),
            ("TP-G06_cap_plate_columna.scp", g06_cap_plate_columna),
            ("TP-G07_placa_base_rigidizada.scp", g07_placa_base_rigidizada),
            ("TP-G08_mensula_soldada.scp", g08_mensula),
            ("TP-G09_rodilla_portico.scp", g09_rodilla_portico),
            ("TP-G10_cartela_cubierta.scp", g10_cartela_cubierta),
            ("TP-G11_apoyo_sobre_muro.scp", g11_apoyo_sobre_muro),
            ("TP-G12_placa_con_aberturas.scp", g12_placa_con_aberturas),
            ("TP-G13_placa_atravesada_por_tubo.scp", g13_placa_atravesada_por_tubo),
            ("TP-G14_placas_recortadas.scp", g14_placas_recortadas),
            ("TP-G15_modos_soldadura.scp", g15_modos_soldadura),
            ("TP-G16_angulo_asiento.scp", g16_angulo_asiento)]


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
