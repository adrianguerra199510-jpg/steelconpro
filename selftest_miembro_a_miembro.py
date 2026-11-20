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
    ph = mt.part("H1")
    Fh = np.array([q for pr in ph.prisms for f_ in pr.faces(48) for q in f_])
    check(any(pr.cut_cyls for pr in ph.prisms) and -11.2 < float(Fh[:, 1].min()) < -10.7, f"H1 (az −90°) se corta en boca de pez contra el cilindro de T2: y mín = {float(Fh[:, 1].min()):.2f} (cresta a −10.81)")

    # ---------------------------------------------------------------- análisis nodal: el brazo de una carga en un miembro que llega a otro
    nd = tower_node()
    nd.loads = [Load("C", "H1", Vz=-10.0)]
    bal = NOD.balance(nd, NOD.cases_of(nd)[0][1])
    Pn = NOD._node_point(nd, "H1")
    check(np.allclose(Pn, [12.0, 0.0, 14.0]), "el nodal usa el punto global de llegada como brazo")
    check(abs(sum(bal["sum_F"]) + 0.0) >= 0.0 and abs(bal["R"][2] - 10.0) < 1e-6, f"equilibrio global: la reacción del principal equilibra la carga ({np.round(bal['R'], 3)})")

    # ---------------------------------------------------------------- boca de pez: tubo redondo contra el cilindro de otro tubo redondo
    from steelconpro.conn import meshcheck as MC
    from steelconpro.conn.fem.model3d import Prism, cyl_roots
    from steelconpro.conn.specs import OP_TRIM as _TR
    for az, el, label in ((-90.0, 0.0, "horizontal"), (-90.0, 52.0, "inclinada 52°"), (-90.0, -25.0, "descendente 25°")):
        nd = tower_node()
        nd.members.append(Member(name="T2", shape="HSS2.375X0.218", steel=nd.main_steel, az=0.0, el=90.0, pos=0.0, off=12.0, off2=12.0, L=60.0, gap=-0.5))
        h1 = nd.members[1]
        h1.az, h1.el, h1.gap = az, el, 0.0
        EG.gen(nd, _TR, targets=["H1"], parent="T1", trim_mode=TRIM_MODES[2], trim_gap=0.0, trim_end="Inicio", trim_weld=True, weld_size=0.125)
        EG.gen(nd, _TR, targets=["H1"], parent="T2", trim_mode=TRIM_MODES[2], trim_gap=0.0, trim_end="Fin", trim_weld=True, weld_size=0.125)
        mb = AS.build_nodo(nd)
        ph = mb.part("H1")
        pr = ph.prisms[0]
        check(len(pr.cut_cyls) == 2, f"boca de pez ({label}): el tubo lleva dos cortes por cilindro (inicio y fin)")
        rep = MC.check_faces(pr.faces(36))
        check(rep["ok"], f"boca de pez ({label}): superficie cerrada y orientada {rep['errors'][:1]}")
        # los puntos de la curva de soldadura están sobre las dos superficies: a ro del eje del tubo y a R del eje del cordón
        ws = [w for w in mb.welds if w.A == "H1"]
        ro = float(pr.circle[0])
        axis_m = np.asarray(pr.W, float)
        bad = 0
        for w in ws:
            for q in (w.p0, w.p1):
                q = np.asarray(q, float)
                rel = q - np.asarray(pr.o, float)
                dm = float(np.linalg.norm(rel - (rel @ axis_m) * axis_m))
                cuts = [c for c in pr.cut_cyls if abs(np.linalg.norm(((q - np.asarray(c[0], float)) - ((q - np.asarray(c[0], float)) @ (np.asarray(c[1], float) / np.linalg.norm(c[1]))) * (np.asarray(c[1], float) / np.linalg.norm(c[1])))) - c[2]) < 1e-6]
                if abs(dm - ro) > 1e-6 or not cuts:
                    bad += 1
        check(len(ws) >= 60 and bad == 0, f"boca de pez ({label}): {len(ws)} tramos de soldadura sobre la curva de intersección (puntos en las dos superficies; fuera de ellas: {bad})")
        g = GC.summary(GC.check(mb))
        check(g["errors"] == 0, f"boca de pez ({label}): el revisor no ve choques ni cordones flotando {g}")
    # el material quitado: un punto dentro del cordón, sobre la boca, no está en el tubo; uno fuera de él, sí
    pr = Prism(poly=[], o=(12.0, 0.0, 14.0), U=(0, 0, 1), V=(0, 1, 0), w0=-0.5, w1=60.0, circle=(0.525, 0.4))
    pr.cut_cyls = [((12.0, 0.0, 0.0), (0, 0, 1), 1.1875, -1)]
    inside = np.array([[11.2, 0.45, 14.0]])                     # a 0.8 in del eje del cordón: dentro del cilindro
    outside = np.array([[9.0, 0.45, 14.0]])
    check(not bool(GC.prism_mask(pr, inside)[0]) and bool(GC.prism_mask(pr, outside)[0]), "el material del tubo dentro del cilindro del cordón se quita; fuera queda")

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
    check(sum(1 for m in ex.node.members if m.attach_to) == 12, "TP-G22: 8 travesaños y 4 diagonales llegan a un cordón")


if __name__ == "__main__":
    run()
    print("\nTODO BIEN" if not FAILS else f"\nFALLARON {len(FAILS)}:\n  " + "\n  ".join(FAILS))
    sys.exit(1 if FAILS else 0)
