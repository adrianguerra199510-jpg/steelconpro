# -*- coding: utf-8 -*-
"""Biblioteca de ejemplos de conexiones típicas viga–columna y viga–viga (corte y momento): ejemplos/TP-V*.scp.

    python3 tools/ejemplos_vigas.py            # escribe los archivos
    python3 tools/ejemplos_vigas.py --revisar  # además arma cada modelo, corre el revisor de geometría y las verificaciones

Cada ejemplo es una función que devuelve un `Project`; `EJEMPLOS` los lista con su código.  El eje del miembro se coloca (off / off2) para que llegue al CENTRO
de la cara del principal, también cuando llega esviado o inclinado.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steelconpro.model import Project, save_book                                  # noqa: E402
from steelconpro.conn import assembly as AS                                       # noqa: E402
from steelconpro.conn.specs import (CT_NODE, Nodo, Member, Operation, Load, TAB_MODES, BEAM_CONNS,   # noqa: E402
                                    OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_CONT, OP_COPE, END_LABELS, OP_PLATE, OP_FILLET, WELD_TYPES, PLATE_ROLES, PLATE_ORIENTS, PLATE_SHAPES, ATTACHES)

OUT = ROOT / "ejemplos"
HSS = "ASTM A500 Gr.C (HSS rect.)"


def centrar(nd, m, cara="y"):
    """off / off2 del miembro para que su eje llegue al centro de la cara del principal: 'y' = cara del ala (o cara «de peralte» de un HSS), 'x' = cara del alma o lateral."""
    A, msx, msy = AS.main_frame(nd)
    ms = AS.shape_of(nd.main_shape)
    d = AS.member_dir(m)
    dx, dy = float(d @ msx), float(d @ msy)
    if cara == "y":
        sg = 1.0 if dy > 0 else -1.0
        m.off, m.off2 = 0.0, -(sg * ms.d / 2.0) / dy * dx
    else:
        sg = 1.0 if dx > 0 else -1.0
        w = ms.bf / 2.0 if ms.is_hollow else ms.tw / 2.0
        m.off2, m.off = 0.0, -(sg * w) / dx * dy


def nudo(code, titulo, main, el, miembros, ops, cargas, steel_main=None, largo=96.0, nombre="Columna"):
    """miembros: [(nombre, perfil, az, el, cara, kwargs de Member)]; ops: [(nombre del miembro, tipo, kwargs)]."""
    p = Project()
    p.ctype = CT_NODE
    p.element = code
    p.name = "Ejemplo: " + titulo
    nd = Nodo(main_name=nombre, main_shape=main, main_steel=steel_main or ("ASTM A992" if main.startswith("W") else HSS), main_el=el,
              main_len_neg=largo / 2, main_len_pos=largo / 2)
    for (nm, sh, az, mel, cara, kw) in miembros:
        m = Member(name=nm, shape=sh, steel="ASTM A992" if sh.startswith("W") else HSS, az=az, el=mel, L=kw.pop("L", 60.0), **kw)
        nd.members.append(m)
        if cara:
            off, off2 = m.off, m.off2
            centrar(nd, m, cara)
            m.off += off
            m.off2 += off2
    for (nm, kind, kw) in ops:
        nd.operations.append(Operation(kind=kind, member=nm, **kw))
    nd.loads = [Load("Caso 1", nm, **kw) for nm, kw in cargas]
    p.node = nd
    return p


V = -20.0
# ----------------------------------------------------------------------------------------------------------------- placa simple
def v01():
    return nudo("TP-V01", "placa simple de una viga W al ala de una columna W", "W14X90", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_TAB, dict(n_bolts=3))], [("V1", dict(Vz=V))])


def v02():
    return nudo("TP-V02", "placa simple de una viga W al alma de una columna W (con corte automático de las alas)", "W14X90", 90, [("V1", "W16X31", 90, 0, "x", {})],
                [("V1", OP_TAB, dict(n_bolts=3))], [("V1", dict(Vz=V))])


def v03():
    return nudo("TP-V03", "placa simple de una viga W a la cara de una columna HSS", "HSS10X10X1/2", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_TAB, dict(n_bolts=3, plate_t=0.375))], [("V1", dict(Vz=V))])


def v04():
    return nudo("TP-V04", "placa simple de una viga secundaria a una viga maestra, con corte (cope) de las alas", "W24X55", 0,
                [("S1", "W16X31", 90, 0, "x", dict(off=4.0))], [("S1", OP_TAB, dict(n_bolts=3, n_cols=1))], [("S1", dict(Vz=V))], nombre="Viga maestra")


def v05():
    return nudo("TP-V05", "placa simple con la viga soldada a la placa (filetes en el alma) sobre el ala de una columna", "W14X90", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_TAB, dict(beam_conn=BEAM_CONNS[1], weld_size=0.25))], [("V1", dict(Vz=V))])


def v06():
    return nudo("TP-V06", "placa simple hasta el interior de las alas de la columna", "W14X90", 90, [("V1", "W16X31", 90, 0, "x", {})],
                [("V1", OP_TAB, dict(tab_mode=TAB_MODES[1]))], [("V1", dict(Vz=V))])


def v07():
    return nudo("TP-V07", "placa simple con dos placas, arriba y abajo, entre las alas de la columna", "W14X90", 90, [("V1", "W16X31", 90, 0, "x", {})],
                [("V1", OP_TAB, dict(tab_mode=TAB_MODES[1], tab_split=True, tp_t=0.5))], [("V1", dict(Vz=V))])


def v08():
    return nudo("TP-V08", "placa simple hasta el interior de las alas de una viga maestra (placa escalonada)", "W24X55", 0,
                [("S1", "W16X31", 90, 0, "x", dict(off=4.0))], [("S1", OP_TAB, dict(tab_mode=TAB_MODES[1]))], [("S1", dict(Vz=V))], nombre="Viga maestra")


# ----------------------------------------------------------------------------------------------------------------- doble ángulo y asiento
def v09():
    return nudo("TP-V09", "doble ángulo de una viga W al ala de una columna W", "W14X90", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_DANG, dict(n_bolts=3))], [("V1", dict(Vz=V))])


def v10():
    return nudo("TP-V10", "doble ángulo de una viga secundaria a una viga maestra (con corte automático)", "W24X55", 0,
                [("S1", "W16X31", 90, 0, "x", dict(off=4.0))], [("S1", OP_DANG, dict(n_bolts=3))], [("S1", dict(Vz=V))], nombre="Viga maestra")


def v11():
    return nudo("TP-V11", "doble ángulo de una viga W a la cara de una columna HSS", "HSS10X10X1/2", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_DANG, dict(n_bolts=3, dang_lo=3.0))], [("V1", dict(Vz=V))])


def v12():
    return nudo("TP-V12", "asiento (ángulo de apoyo) bajo una viga W contra el ala de una columna W", "W14X90", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_SEAT, dict(plate_t=0.5))], [("V1", dict(Vz=V))])


# ----------------------------------------------------------------------------------------------------------------- momento
def v13():
    return nudo("TP-V13", "placa extrema a ras (momento) en el ala de una columna, con placas de continuidad", "W14X90", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_EP_FLUSH, dict(plate_t=0.625)), ("V1", OP_CONT, dict(cont_t=0.5))], [("V1", dict(Vz=V, My=300.0))])


def v14():
    return nudo("TP-V14", "placa extrema extendida (momento) en el ala de una columna, con placas de continuidad", "W14X90", 90, [("V1", "W18X50", 0, 0, "y", {})],
                [("V1", OP_EP_EXT, dict(plate_t=0.75, ep_ext=3.0)), ("V1", OP_CONT, dict(cont_t=0.5))], [("V1", dict(Vz=V, My=600.0))])


def v15():
    return nudo("TP-V15", "alas soldadas y alma atornillada (WUF) en el ala de una columna, con placas de continuidad", "W14X90", 90, [("V1", "W18X50", 0, 0, "y", {})],
                [("V1", OP_WELD, dict(n_bolts=4)), ("V1", OP_CONT, dict(cont_t=0.5))], [("V1", dict(Vz=V, My=600.0))])


def v16():
    return nudo("TP-V16", "placa extrema a ras en una columna HSS", "HSS10X10X1/2", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_EP_FLUSH, dict(plate_t=0.625, ep_w=7.0))], [("V1", dict(Vz=V, My=200.0))])


# ----------------------------------------------------------------------------------------------------------------- varias vigas
def v17():
    return nudo("TP-V17", "columna de esquina: una viga al ala (placa simple) y otra al alma (doble ángulo)", "W14X90", 90,
                [("V1", "W16X31", 0, 0, "y", {}), ("V2", "W16X31", 90, 0, "x", {})],
                [("V1", OP_TAB, {}), ("V2", OP_DANG, {})], [("V1", dict(Vz=V)), ("V2", dict(Vz=V))])


def v18():
    return nudo("TP-V18", "columna de borde con tres vigas (dos al ala opuestas, una al alma)", "W14X90", 90,
                [("V1", "W16X31", 0, 0, "y", {}), ("V2", "W16X31", 180, 0, "y", {}), ("V3", "W16X31", 90, 0, "x", {})],
                [("V1", OP_TAB, {}), ("V2", OP_TAB, {}), ("V3", OP_DANG, {})], [("V1", dict(Vz=V)), ("V2", dict(Vz=V)), ("V3", dict(Vz=V))])


def v19():
    return nudo("TP-V19", "columna interior con cuatro vigas: placa extrema, doble ángulo, placa simple y asiento", "W14X90", 90,
                [("V1", "W18X50", 0, 0, "y", {}), ("V2", "W16X31", 90, 0, "x", {}), ("V3", "W18X50", 180, 0, "y", {}), ("V4", "W16X31", 270, 0, "x", {})],
                [("V1", OP_EP_EXT, {}), ("V2", OP_DANG, {}), ("V3", OP_TAB, {}), ("V4", OP_TAB, {})],
                [("V1", dict(Vz=V)), ("V2", dict(Vz=V)), ("V3", dict(Vz=V)), ("V4", dict(Vz=V))])


def v20():
    return nudo("TP-V20", "columna HSS interior con tres vigas (placa simple en cada cara)", "HSS12X12X1/2", 90,
                [("V1", "W16X31", 0, 0, "y", {}), ("V2", "W16X31", 180, 0, "y", {}), ("V3", "W16X31", 90, 0, "x", {})],
                [("V1", OP_TAB, {}), ("V2", OP_TAB, {}), ("V3", OP_TAB, {})], [("V1", dict(Vz=V)), ("V2", dict(Vz=V)), ("V3", dict(Vz=V))])


def v21():
    return nudo("TP-V21", "viga maestra con dos secundarias opuestas (doble ángulo y placa simple)", "W24X55", 0,
                [("S1", "W16X31", 90, 0, "x", dict(off=4.0)), ("S2", "W16X31", 270, 0, "x", dict(off=4.0))],
                [("S1", OP_DANG, {}), ("S2", OP_TAB, {})], [("S1", dict(Vz=V)), ("S2", dict(Vz=V))], nombre="Viga maestra")


# ----------------------------------------------------------------------------------------------------------------- esviajes y pendientes
def _esv(code, titulo, kind, az, main="W14X90", beam="W16X31", **kw):
    return nudo(code, titulo, main, 90, [("V1", beam, az, 0, "y", {})], [("V1", kind, kw)], [("V1", dict(Vz=V))])


def v22():
    return _esv("TP-V22", "viga esviada 30° en planta con placa simple al ala de la columna", OP_TAB, 30.0)


def v23():
    return _esv("TP-V23", "viga esviada 45° en planta con doble ángulo al ala de la columna", OP_DANG, 45.0)


def v24():
    return _esv("TP-V24", "viga esviada 30° con placa extrema (la placa se apoya en la cara, la viga se corta en ángulo)", OP_EP_FLUSH, 330.0, plate_t=0.625)


def v25():
    return _esv("TP-V25", "viga esviada 30° con asiento", OP_SEAT, 30.0, plate_t=0.5)


def v26():
    return _esv("TP-V26", "viga esviada 30° con alas soldadas y alma atornillada", OP_WELD, 30.0)


def v27():
    return nudo("TP-V27", "viga de cubierta con pendiente de 15° y placa simple en el ala de la columna", "W14X90", 90, [("V1", "W16X31", 0, 15.0, "y", {})],
                [("V1", OP_TAB, {})], [("V1", dict(Vz=V))])


def v28():
    return nudo("TP-V28", "viga de cubierta con pendiente de 18° y placa extrema a ras en la columna", "W14X90", 90, [("V1", "W16X31", 0, 18.0, "y", {})],
                [("V1", OP_EP_FLUSH, dict(plate_t=0.625))], [("V1", dict(Vz=V, My=100.0))])


def v29():
    return nudo("TP-V29", "viga de cubierta con pendiente de 10° y doble ángulo en la columna", "W14X90", 90, [("V1", "W16X31", 0, 10.0, "y", {})],
                [("V1", OP_DANG, {})], [("V1", dict(Vz=V))])


def v30():
    return nudo("TP-V30", "viga secundaria esviada 30° a una viga maestra con placa simple", "W24X55", 0,
                [("S1", "W16X31", 120, 0, "x", dict(off=4.0))], [("S1", OP_TAB, {})], [("S1", dict(Vz=V))], nombre="Viga maestra")


def v31():
    return nudo("TP-V31", "viga esviada 30° al alma de una columna W con placa simple (se cortan las alas de la viga)", "W14X90", 90, [("V1", "W16X31", 60, 0, "x", {})],
                [("V1", OP_TAB, {})], [("V1", dict(Vz=V))])


def v32():
    return nudo("TP-V32", "viga esviada 30° al alma de una columna W con doble ángulo", "W14X90", 90, [("V1", "W16X31", 120, 0, "x", {})],
                [("V1", OP_DANG, {})], [("V1", dict(Vz=V))])


def v33():
    return nudo("TP-V33", "viga inclinada 12° al alma de una columna W con placa simple", "W14X90", 90, [("V1", "W16X31", 90, 12.0, "x", {})],
                [("V1", OP_TAB, {})], [("V1", dict(Vz=V))])


def v34():
    return nudo("TP-V34", "asiento rigidizado bajo una viga W contra el ala de una columna W", "W14X90", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_SEAT, dict(plate_t=0.5, seat_Lv=8.0, seat_Lh=5.0, seat_stiff=True, seat_stiff_t=0.5))], [("V1", dict(Vz=-30.0))])


def v35():
    return nudo("TP-V35", "asiento rigidizado con la viga esviada 30°", "W14X90", 90, [("V1", "W16X31", 30, 0, "y", {})],
                [("V1", OP_SEAT, dict(plate_t=0.5, seat_Lv=8.0, seat_Lh=5.0, seat_stiff=True))], [("V1", dict(Vz=-30.0))])


def v36():
    return nudo("TP-V36", "asiento rigidizado contra la cara de una columna HSS", "HSS10X10X1/2", 90, [("V1", "W16X31", 0, 0, "y", {})],
                [("V1", OP_SEAT, dict(plate_t=0.5, seat_Lv=8.0, seat_Lh=5.0, seat_stiff=True))], [("V1", dict(Vz=-30.0))])


def v37():
    return nudo("TP-V37", "placa simple de una viga W a una columna de tubo redondo (borde de la placa con silla)", "HSS12.750X0.500", 90, [("V1", "W16X31", 0, 0, None, {})],
                [("V1", OP_TAB, {})], [("V1", dict(Vz=V))], steel_main="ASTM A500 Gr.C (HSS red.)")


def v38():
    return nudo("TP-V38", "placa simple de una viga HSS a un tubo redondo horizontal con esviaje de 30°", "HSS12.750X0.500", 0, [("S1", "HSS6X6X3/8", 120, 0, None, {})],
                [("S1", OP_TAB, {})], [("S1", dict(Vz=V))], steel_main="ASTM A500 Gr.C (HSS red.)", nombre="Cordon")


def v39():
    """Ejemplo 4.4 de AISC Design Guide 4 (8ES): W21X55 a W14X109, pernos A325 de 1 in, placa de 7/8 in A572 Gr. 50, diseño sísmico con Vu = 40 kip."""
    p = nudo("TP-V39", "placa extrema 8ES precalificada (AISC Design Guide 4, ejemplo 4.4) con diseño sísmico", "W14X109", 90, [("V1", "W21X55", 0, 0, "y", {})],
             [("V1", OP_EP_EXT, dict(ep_dg4="8ES", bolt_size="1", bolt_grade="A325-N", plate_t=0.875, plate_steel="ASTM A572 Gr.50", ep_w=9.0, ep_g=5.5,
                                     ep_st_t=0.5, wf_top="CJP (penetración completa)", wf_bot="CJP (penetración completa)", weld_size=0.3125)),
              ("V1", OP_CONT, dict(cont_t=0.5))], [("V1", dict(Vz=-40.0, My=4000.0))])
    p.node.member_named("V1").sism_Vg = 40.0
    return p


def v40():
    """Plantilla fija «Pórtico especial: placa extrema precalificada (AISC DG4)» con vigas a los dos lados: verificación del nudo (AISC 341-22)."""
    from steelconpro.conn import typologies as TY
    p = Project()
    p.ctype = CT_NODE
    p.element = "TP-V40"
    p.name = "Ejemplo: plantilla pórtico especial 8ES con vigas a los dos lados (nudo AISC 341)"
    p.node = TY.build_nodo("smf", {"two_sided": True})
    return p


def _empalme(code, titulo, **kw):
    from steelconpro.conn.specs import OP_SPLICE
    p = Project()
    p.ctype = CT_NODE
    p.element = code
    p.name = "Ejemplo: " + titulo
    nd = Nodo(main_name="V1", main_shape="W18X50", main_steel="ASTM A992", main_el=0.0, main_az=0.0, main_end=END_LABELS[1])
    nd.members = [Member(name="V2", shape="W18X50", steel="ASTM A992", az=0.0, el=0.0)]
    nd.operations = [Operation(kind=OP_SPLICE, member="V2", bolt_size="7/8", bolt_grade="A325-N", plate_t=0.5, plate_steel="ASTM A572 Gr.50", weld_size=0.25, **kw)]
    nd.loads = [Load("Caso 1", "V2", Vz=-30.0, My=1500.0)]
    p.node = nd
    return p


def v41():
    """Empalme de viga W18X50 con cubreplacas atornilladas en las alas (3 pernos por línea a cada lado) y dos placas atornilladas en el alma
    (dos columnas de pernos a cada lado: con una sola, el perno de la esquina no alcanza por desgarramiento hacia el extremo de la viga)."""
    return _empalme("TP-V41", "empalme de viga con cubreplacas atornilladas en alas y alma", sp_cw=2)


def v42():
    """Empalme con las cubreplacas de las alas soldadas (filetes) y el alma atornillada."""
    return _empalme("TP-V42", "empalme de viga con alas soldadas y alma atornillada", sp_flange="Soldada", sp_cw=2)


def v43():
    """Empalme todo soldado, con cubreplacas interiores en las alas."""
    return _empalme("TP-V43", "empalme de viga soldado con cubreplacas exteriores e interiores", sp_flange="Soldada", sp_web="Soldada", sp_inner=True)


def v44():
    """Empalme soldado de una viga doble 2 × HN600×200×11×17 (dos vigas lado a lado, puntas de las alas unidas) armado con operaciones generales,
    diseñado para desarrollar la capacidad de la viga (AISC 360-22): cubreplacas PL 20 × 340 × 720 con filete de 14 mm arriba y abajo, y una placa de alma
    PL 20 × 500 × 1410 por viga en la cara exterior con filete de 12 mm en C.  Acero A572 Gr. 50 (supuesto), E70, separación de 10 mm.
    Dos casos: A = momento completo φMn (889 kN·m por viga) con 30 % de φVn concurrente; B = cortante completo φVn (1366 kN por viga)."""
    from steelconpro.shapes import CATALOG, make_custom, W_SHAPE
    MM = 1 / 25.4
    KN, KNM = 1 / 4.448222, 8.850746
    lab = "HN600X200X11X17"
    if CATALOG.get(lab) is None:
        sh = make_custom(lab, W_SHAPE, 600 * MM, 200 * MM, 11 * MM, 17 * MM)
        sh.kdes = 30 * MM
        CATALOG.shapes[lab] = sh
        CATALOG._reindex()
    st = "ASTM A572 Gr.50"
    p = Project()
    p.ctype = CT_NODE
    p.element = "TP-V44"
    p.name = "Ejemplo: empalme soldado de viga doble 2xHN600x200x11x17 que desarrolla su capacidad (operaciones generales)"
    p.u_len, p.u_force, p.u_stress, p.u_moment = "mm", "kN", "MPa", "kN·m"
    gap, off = 10 * MM, 200 * MM
    nd = Nodo(main_name="V1a", main_shape=lab, main_steel=st, main_el=0.0, main_az=0.0, main_end=END_LABELS[1])
    nd.members = [Member(name="V1b", shape=lab, steel=st, az=180.0, el=0.0, off2=off, gap=-0.5),         # viga del lado izquierdo, junto a V1a
                  Member(name="V2a", shape=lab, steel=st, az=0.0, el=0.0, gap=gap - 0.5),                # vigas del lado derecho, a 10 mm
                  Member(name="V2b", shape=lab, steel=st, az=0.0, el=0.0, off2=off, gap=gap - 0.5)]
    P = lambda **k: Operation(kind=OP_PLATE, member="", role=PLATE_ROLES[0], orient=PLATE_ORIENTS[0], shape=PLATE_SHAPES[0], attach=ATTACHES[2], plate_steel=st,   # noqa: E731
                              plate_t=20 * MM, **k)
    nd.operations = [P(name="CP-S", parent="V2a", face="Ala superior", pl_L=720 * MM, pl_W=340 * MM, pl_s=-5 * MM, pl_u=100 * MM),
                     P(name="CP-I", parent="V2a", face="Ala inferior", pl_L=720 * MM, pl_W=340 * MM, pl_s=-5 * MM, pl_u=-100 * MM),
                     P(name="PA-a", parent="V2a", face="Alma −", pl_L=1410 * MM, pl_W=500 * MM, pl_s=-5 * MM, pl_u=0.0),
                     P(name="PA-b", parent="V2b", face="Alma +", pl_L=1410 * MM, pl_W=500 * MM, pl_s=-5 * MM, pl_u=0.0)]
    for nm, fc in (("CP-S", "Ala superior"), ("CP-I", "Ala inferior")):           # fuerza a mano: la mitad de Ff = 1985 kN en el ala de cada viga
        nd.operations.append(Operation(kind=OP_FILLET, member="", weld_main=nm, weld_to=[["V1a", fc], ["V1b", fc], ["V2a", fc], ["V2b", fc]], weld_size=14 * MM,
                                       weld_all=True, force_T=993.0 * KN))
    nd.operations.append(Operation(kind=OP_FILLET, member="", weld_main="PA-a", weld_to=[["V1a", "Alma −"], ["V2a", "Alma −"]], weld_size=12 * MM, weld_all=True,
                                   force_V=1366.0 * KN))
    nd.operations.append(Operation(kind=OP_FILLET, member="", weld_main="PA-b", weld_to=[["V1b", "Alma −"], ["V2b", "Alma +"]], weld_size=12 * MM, weld_all=True,
                                   force_V=1366.0 * KN))
    VA, MA, VB = 0.3 * 1366.0, 889.0, 1366.0
    nd.loads = []
    for nm in ("V2a", "V2b"):
        nd.loads.append(Load("A: momento completo", nm, Vz=-VA * KN, My=MA * KNM))
        nd.loads.append(Load("B: cortante completo", nm, Vz=-VB * KN))
    nd.loads += [Load("A: momento completo", "V1b", Vz=VA * KN, My=MA * KNM), Load("B: cortante completo", "V1b", Vz=VB * KN)]   # V1b equilibra a V2b
    p.node = nd
    return p


def v45():
    """Empalme soldado de la viga doble 2 × HN600×200×11×17 armado como UNA sección personalizada del Section Designer (2XHN600X200X11X17: 4 rectángulos de ala
    y 2 de alma): solo 2 miembros.  Diseñado a capacidad de la viga (φMn y φVn de AISC 360-22) con placas de 20 mm A572 Gr. 50 y E70:
    2 placas de ala PL 20 × 360 × 500 (una arriba y otra abajo, cada una sobre las dos alas, filete de 16 mm) y 2 placas de alma PL 20 × 400 × 500 (una por alma, solo
    por la cara exterior, filete de 12 mm en C), más la **soldadura a tope de penetración completa (CJP) de cada alma contra la de la otra viga** (separación de 2 mm entre
    las vigas): con solo la placa, el alma no alcanza la capacidad (D/C 1.5 en los filetes, los gobierna el metal base del alma); con la CJP, el alma desarrolla su resistencia
    y la placa es adicional.  Las placas y los filetes se refieren a las caras de cada componente («Comp. 6 (Rect.) — Cara +X» = cara exterior del alma derecha), no a la
    envolvente de la sección.  Casos: A = momento completo (889 kN·m por viga) con 30 % de φVn; B = cortante completo (1366 kN por viga)."""
    from steelconpro.shapes import CATALOG, make_general
    MM = 1 / 25.4
    KN, KNM = 1 / 4.448222, 8.850746
    lab = "2XHN600X200X11X17"
    comps = [{"t": "rect", "x": x * MM, "y": y * MM, "w": 200 * MM, "h": 17 * MM, "rot": 0.0} for x in (-100, 100) for y in (292, -292)]
    comps += [{"t": "rect", "x": x * MM, "y": 0.0, "w": 11 * MM, "h": 566 * MM, "rot": 0.0} for x in (-100, 100)]
    if CATALOG.get(lab) is None:
        CATALOG.shapes[lab] = make_general(lab, comps)
        CATALOG._reindex()
    st = "ASTM A572 Gr.50"
    p = Project()
    p.ctype = CT_NODE
    p.element = "TP-V45"
    p.name = "Ejemplo: empalme soldado de viga doble 2xHN600x200x11x17 a capacidad, como una sola sección personalizada (caras de cada componente)"
    p.u_len, p.u_force, p.u_stress, p.u_moment = "mm", "kN", "MPa", "kN·m"
    nd = Nodo(main_name="V1", main_shape=lab, main_steel=st, main_el=0.0, main_az=0.0, main_end=END_LABELS[1])
    nd.members = [Member(name="V2", shape=lab, steel=st, az=0.0, el=0.0, gap=2 * MM - 0.5)]
    P = lambda **k: Operation(kind=OP_PLATE, member="", role=PLATE_ROLES[0], orient=PLATE_ORIENTS[0], shape=PLATE_SHAPES[0], attach=ATTACHES[2], plate_steel=st,   # noqa: E731
                              plate_t=20 * MM, parent="V2", pl_s=-1 * MM, **{"pl_u": 0.0, **k})
    cara = lambda k, c: f"Comp. {k} (Rect.) — Cara {c}"                                                                        # noqa: E731
    # placas de ala: UNA por nivel (superior e inferior), por fuera, que cubre las dos alas (comp. 1 y 3 = alas superiores, 2 y 4 = inferiores); centrada en la junta de las alas
    # (pl_u = ±100 mm desde el centro de la cara del comp. 1 o 2).  Ancho 360 mm: con 200 mm la placa solo alcanza el 62 % de la fuerza de las alas.
    nd.operations = [P(name="CA-S", face=cara(1, "+Y"), pl_L=500 * MM, pl_W=360 * MM, pl_u=100 * MM), P(name="CA-I", face=cara(2, "−Y"), pl_L=500 * MM, pl_W=360 * MM, pl_u=-100 * MM)]
    # placas de alma: solo exteriores, una por alma (comp. 5 = alma izquierda, 6 = alma derecha)
    almas = [("PA-1", cara(5, "−X")), ("PA-2", cara(6, "+X"))]
    nd.operations += [P(name=n, face=f, pl_L=500 * MM, pl_W=400 * MM) for n, f in almas]
    for n, f1, f2 in (("CA-S", cara(1, "+Y"), cara(3, "+Y")), ("CA-I", cara(2, "−Y"), cara(4, "−Y"))):   # fuerza del ala por viga: Mf/(d + tp) = 993 kN a cada lado de la junta
        nd.operations.append(Operation(kind=OP_FILLET, member="", weld_main=n, weld_to=[["V1", f1], ["V1", f2], ["V2", f1], ["V2", f2]], weld_size=16 * MM, weld_all=True, force_T=993.0 * KN))
    # soldadura a tope CJP de cada alma contra la otra (extremo del componente: 11 × 566 mm); la CJP desarrolla el alma y la placa lleva el resto del cortante (78 kN)
    nd.operations.append(Operation(kind=OP_FILLET, member="", weld_main="V2", weld_to=[["V1", "Comp. 5 (Rect.) — Extremo fin"], ["V1", "Comp. 6 (Rect.) — Extremo fin"]],
                                   weld_type=WELD_TYPES[1], weld_size=11 * MM, weld_all=True))
    for n, f in almas:                                                                                      # la placa es adicional: lleva el cortante que excede a la CJP (1366 − 1288 = 78 kN)
        nd.operations.append(Operation(kind=OP_FILLET, member="", weld_main=n, weld_to=[["V1", f], ["V2", f]], weld_size=12 * MM, weld_all=True, force_V=78.0 * KN))
    nd.loads = [Load("A: momento completo", "V2", Vz=-0.6 * 1366.0 * KN, My=1778.0 * KNM), Load("B: cortante completo", "V2", Vz=-2732.0 * KN)]
    p.node = nd
    return p


EJEMPLOS = [(f"TP-V{k:02d}", fn) for k, fn in enumerate([v01, v02, v03, v04, v05, v06, v07, v08, v09, v10, v11, v12, v13, v14, v15, v16, v17, v18, v19, v20, v21,
                                                         v22, v23, v24, v25, v26, v27, v28, v29, v30, v31, v32, v33, v34, v35, v36, v37, v38, v39, v40, v41, v42, v43, v44, v45], 1)]


def nombre_archivo(p) -> str:
    base = p.name.replace("Ejemplo: ", "")
    s = "".join(c if c.isalnum() else "_" for c in base.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    while "__" in s:
        s = s.replace("__", "_")
    return f"{p.element}_{s.strip('_')[:60]}.scp"


def revisar(p):
    from steelconpro.conn import geocheck as GC
    from steelconpro import api
    mdl = AS.build_model(p)
    iss = GC.check(mdl)
    err = [e for e in iss if e["sev"] == "error"]
    avisos = [e for e in iss if e["sev"] != "error"]
    ok_v = True
    try:
        api.verify({"connection": api._dump(p)})
    except Exception as e:                                           # noqa: BLE001
        ok_v = repr(e)[:100]
    return err, avisos, ok_v, mdl.notes


def main():
    rev = "--revisar" in sys.argv
    for code, fn in EJEMPLOS:
        p = fn()
        f = OUT / nombre_archivo(p)
        for old in OUT.glob(f"{code}_*.scp"):
            old.unlink()
        save_book(str(f), [p])
        if rev:
            err, avisos, ok_v, notes = revisar(p)
            print(f"{code} {f.name}: errores {len(err)}, avisos {len(avisos)}, verify {ok_v}")
            for e in err:
                print("     ERROR", e["text"][:150])
            for e in avisos[:3]:
                print("     aviso", e["text"][:150])
            for n in notes[:3]:
                print("     nota", n[:150])


if __name__ == "__main__":
    main()
