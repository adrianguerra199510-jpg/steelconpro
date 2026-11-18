# -*- coding: utf-8 -*-
"""Pruebas de la unión de MIEMBRO con MIEMBRO (`Member.attach_to`): orden, ciclos, colocación desde el inicio del miembro de apoyo, renombrado, análisis nodal, guardado y el ejemplo TP-G22.

    python3 selftest_miembro_a_miembro.py
"""
import os
import sys
import tempfile
from dataclasses import asdict

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from steelconpro.conn import assembly as AS, geocheck as GC, nodal as NOD                        # noqa: E402
from steelconpro.conn.specs import Member, Load, Nodo, OP_TAB, OP_TRIM, TRIM_MODES               # noqa: E402
from steelconpro.model import load_book, save_book                                               # noqa: E402
import ejemplos_generales as EG                                                                  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def tower_node():
    shape = "HSS2.375X0.218"
    nd = EG.column(shape=shape, length=60.0, end=2)
    nd.members = [Member(name="T1", shape=shape, steel=nd.main_steel, az=0.0, el=90.0, pos=0.0, off=12.0, off2=0.0, L=60.0, gap=-0.5),
                  Member(name="H1", shape="Pipe3.4XS", steel=nd.main_steel, az=180.0, el=0.0, pos=14.0, L=60.0, gap=-0.05, attach_to="T1")]
    return nd


def run():
    # ---------------------------------------------------------------- orden, ciclos y referencias inexistentes
    nd = Nodo()
    nd.members = [Member(name="A", attach_to="B"), Member(name="B", attach_to="C"), Member(name="C"), Member(name="D", attach_to="D"), Member(name="E", attach_to="X"),
                  Member(name="F", attach_to=nd.main_name)]
    order = [m.name for m in nd.member_order()]
    check(order.index("C") < order.index("B") < order.index("A"), f"los padres van antes que sus hijos: {order}")
    check([nd.parent_name(m) for m in nd.members] == ["B", "C", "", "", "", ""], "sin ciclos: D (a sí mismo), E (inexistente) y F (el principal) llegan al principal")
    nd.members[2].attach_to = "A"
    check(all(nd.parent_name(m) == "" for m in nd.members[:3]), "un ciclo A→B→C→A se trata como llegada al principal (sin colgarse)")
    check(set(order) == {m.name for m in nd.member_order()} and len(nd.member_order()) == 6, "member_order devuelve todos los miembros una vez")

    # ---------------------------------------------------------------- colocación: la posición se mide desde el inicio del miembro de apoyo
    nd = tower_node()
    mdl = AS.build_nodo(nd)
    h = mdl.part("H1").bbox()
    t1 = mdl.part("T1").bbox()
    R = AS.shape_of("HSS2.375X0.218").d / 2.0
    check(abs(float(t1[0][2])) < 1e-6 and abs((t1[0][0] + t1[1][0]) / 2 - 12.0) < 1e-6, "el cordón T1 es un miembro paralelo en x = 12 que empieza en z = 0")
    check(abs((h[0][2] + h[1][2]) / 2 - 14.0) < 0.05, f"H1 llega a 14 in del inicio de T1: z = {(h[0][2] + h[1][2]) / 2:.2f}")
    check(abs(float(h[1][0]) - (12.0 - R + 0.05 + 0.0) - 0.0) < 0.5 and float(h[1][0]) < 12.0, f"H1 parte de la superficie de T1 hacia −X (x máx = {float(h[1][0]):.2f})")
    P = AS.attach_global(nd, nd.members[1])
    check(np.allclose(P, [12.0, 0.0, 14.0], atol=1e-6), f"punto global de llegada de H1 = {np.round(P, 3)}")
    # el mismo punto sobre el principal con un miembro propio da la misma geometría
    check(not any("no toca" in n and "H1" in n for n in mdl.notes), "H1 toca a su apoyo (sin aviso de «no toca»)")

    # ---------------------------------------------------------------- longitud del principal: los hijos no la alargan; el largo es automático
    check(nd.lengths() == (0.0, nd.auto_len()), f"los miembros que llegan a otro miembro no alargan al principal: {nd.lengths()}")

    # ---------------------------------------------------------------- conexión de catálogo sobre un hijo: se ignora con nota
    nd = tower_node()
    nd.operations = []
    EG.gen(nd, OP_TAB, member="H1")
    m2 = AS.build_nodo(nd)
    check(any("solo se arman contra el principal" in n for n in m2.notes), "una conexión de catálogo en un miembro que llega a otro se ignora con una nota")
    check(m2.part("H1") is not None and not any(w.A.startswith("Placa") for w in m2.welds), "el miembro se coloca igual y no se arma la placa")

    # ---------------------------------------------------------------- renombrar y recorte contra el volumen del vecino
    nd = tower_node()
    nd.rename_element("T1", "CORDON")
    check(nd.members[1].attach_to == "CORDON" and nd.parent_name(nd.members[1]) == "CORDON", "al renombrar el cordón, el miembro que llega a él lo sigue")
    nd = tower_node()
    nd.members.append(Member(name="T2", shape="HSS2.375X0.218", steel=nd.main_steel, az=0.0, el=90.0, pos=0.0, off=12.0, off2=12.0, L=60.0, gap=-0.5))   # off2 > 0 va hacia −Y (eje x de la sección de la columna)
    EG.gen(nd, OP_TRIM, targets=["H1"], parent="T2", trim_mode=TRIM_MODES[2], trim_gap=-0.05, trim_end="Fin")
    nd.members[1].az = -90.0 + 0.0
    mt = AS.build_nodo(nd)
    ht = mt.part("H1").bbox()
    check(float(ht[0][1]) > -11.0 and float(ht[0][1]) < -9.0, f"H1 (az −90°) se recorta contra el volumen de T2: y mín = {float(ht[0][1]):.2f}")

    # ---------------------------------------------------------------- análisis nodal: el brazo de una carga en un miembro que llega a otro
    nd = tower_node()
    nd.loads = [Load("C", "H1", Vz=-10.0)]
    bal = NOD.balance(nd, NOD.cases_of(nd)[0][1])
    Pn = NOD._node_point(nd, "H1")
    check(np.allclose(Pn, [12.0, 0.0, 14.0]), "el nodal usa el punto global de llegada como brazo")
    check(abs(sum(bal["sum_F"]) + 0.0) >= 0.0 and abs(bal["R"][2] - 10.0) < 1e-6, f"equilibrio global: la reacción del principal equilibra la carga ({np.round(bal['R'], 3)})")

    # ---------------------------------------------------------------- guardado y lectura
    p = EG.g22_torre_cuatro_tubos_sobre_placa()
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "t.scp")
        save_book(f, [p])
        q = load_book(f)[0]
    check([m.attach_to for m in q.node.members] == [m.attach_to for m in p.node.members] and any(m.attach_to for m in q.node.members), "attach_to se guarda y se lee")

    # ---------------------------------------------------------------- el ejemplo
    ex = load_book(os.path.join(ROOT, "ejemplos", "TP-G22_torre_cuatro_tubos_sobre_placa.scp"))[0]
    g = GC.summary(GC.check(AS.build_model(ex)))
    check(g["errors"] == 0 and g["warnings"] == 0, f"TP-G22: revisor sin errores ni avisos ({g})")
    check(sum(1 for m in ex.node.members if m.attach_to) == 8, "TP-G22: ocho travesaños llegan a un cordón")


if __name__ == "__main__":
    run()
    print("\nTODO BIEN" if not FAILS else f"\nFALLARON {len(FAILS)}:\n  " + "\n  ".join(FAILS))
    sys.exit(1 if FAILS else 0)
