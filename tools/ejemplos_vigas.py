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
                                    OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_CONT, OP_COPE)

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


EJEMPLOS = [(f"TP-V{k:02d}", fn) for k, fn in enumerate([v01, v02, v03, v04, v05, v06, v07, v08, v09, v10, v11, v12, v13, v14, v15, v16, v17, v18, v19, v20, v21,
                                                         v22, v23, v24, v25, v26, v27, v28, v29, v30], 1)]


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
