# -*- coding: utf-8 -*-
"""Rotaciones liberadas en el extremo del nudo: un miembro articulado no transmite momento (ni lo genera el largo del miembro) y sus cargas se dibujan donde llegan al nudo."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from steelconpro.model import load_book                                    # noqa: E402
from steelconpro.conn import nodal as NOD, specs as SP                     # noqa: E402
from steelconpro import api                                                # noqa: E402

fails = []


def fail(t):
    fails.append(t)
    print("FALLA:", t)


p = load_book(os.path.join(ROOT, "ejemplos", "CN-02_viga_con_secundarias.scp"))[0]
nd = p.node
nd.loads = [SP.Load("Caso 1", "S1", Vz=-20.0, My=50.0, Mz=7.0, T=3.0), SP.Load("Caso 1", "S2", Vz=-25.0, My=40.0)]
# S1: placa extrema (momento): empotrada; S2: placa simple: articulada
if nd.releases("S1") != (False, False, False) or nd.releases("S2") != (True, True, True):
    fail(f"liberación automática: S1 {nd.releases('S1')}, S2 {nd.releases('S2')}")
cs = dict((c, {l.member: l for l in ls}) for c, ls in NOD.cases_of(nd))["Caso 1"]
if abs(cs["S2"].My) > 1e-12 or abs(cs["S1"].My - 50.0) > 1e-12:
    fail("las cargas de un miembro articulado conservan su momento")
# manual: liberar solo My en S1
m1 = nd.member_named("S1")
m1.rel_auto = False
m1.rel_My = True
cs = dict((c, {l.member: l for l in ls}) for c, ls in NOD.cases_of(nd))["Caso 1"]
if abs(cs["S1"].My) > 1e-12 or abs(cs["S1"].Mz - 7.0) > 1e-12 or abs(cs["S1"].T - 3.0) > 1e-12:
    fail("liberación manual: solo debe anularse My")
m1.rel_auto = True
# el momento del equilibrio solo viene de las excentricidades, no del largo del miembro: duplicar el largo no cambia nada
b0 = NOD.balance(nd, NOD.cases_of(nd)[0][1])
nd.member_named("S2").L = 200.0
b1 = NOD.balance(nd, NOD.cases_of(nd)[0][1])
if np.max(np.abs(np.array(b0["M"]) - np.array(b1["M"]))) > 1e-9:
    fail("el momento del equilibrio depende del largo del miembro")
# las flechas se dibujan en el extremo que llega al nudo, sin momento si está articulado
a = api.nodal({"connection": api._dump(p)})["cases"][0]["draw"]
d2 = next(d for d in a if d["name"] == "S2")
if np.linalg.norm(d2["M"]) > 1e-9:
    fail(f"S2 articulado dibuja momento {d2['M']}")
import steelconpro.conn.assembly as AS                                     # noqa: E402
Q2 = np.asarray(AS.attach_info(nd, nd.member_named("S2"))["Q"], float)
if np.linalg.norm(np.asarray(d2["pos"]) - Q2) > 1e-6:
    fail(f"S2: la carga no se dibuja en su apoyo: {d2['pos']} vs {Q2}")
print(f"{'articulaciones':34} automáticas por conexión, manuales, sin momento por largo, cargas en el extremo del nudo: OK")
if fails:
    print(f"\nFALLAS ({len(fails)}):")
    sys.exit(1)
print("\nTODAS LAS PRUEBAS DE ARTICULACIONES PASARON")
