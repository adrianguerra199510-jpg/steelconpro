# -*- coding: utf-8 -*-
"""Prueba del revisor de geometría: un modelo limpio no da hallazgos y cada defecto sembrado se detecta.  Uso: python3 selftest_geocheck.py"""
import copy
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from steelconpro.model import load_book                                    # noqa: E402
from steelconpro.conn import assembly as AS, geocheck as GC                # noqa: E402
from steelconpro.conn.fem.model3d import Part, box_prism                   # noqa: E402
from steelconpro import api                                                # noqa: E402

fails = []


def fail(t):
    fails.append(t)
    print("FALLA:", t)


def codes(iss, sev="error"):
    return sorted({e["code"] for e in iss if e["sev"] == sev})


prj = load_book(os.path.join(ROOT, "ejemplos", "CN-06_diagonal_con_recorte_y_angulo.scp"))[0]
base = AS.build_model(prj)
iss = GC.check(base)
if iss:
    fail(f"el ejemplo limpio CN-06 da hallazgos: {[e['text'] for e in iss]}")
print(f"{'modelo limpio':34} CN-06 sin hallazgos ({len(base.parts)} piezas, {len(base.bolts)} pernos, {len(base.welds)} cordones): OK")

# 1) cordón separado de la pieza
m = copy.deepcopy(base)
w = m.welds[0]
sh = np.asarray(w.nB, float) * 1.0
w.p0, w.p1 = tuple(np.asarray(w.p0) + sh), tuple(np.asarray(w.p1) + sh)
if "soldadura" not in codes(GC.check(m)):
    fail("no se detecta un cordón separado 1 in de su pieza")
# 2) perno fuera de la pieza
m = copy.deepcopy(base)
b = m.bolts[0]
ax = np.asarray(b.axis, float)
lat = np.cross(ax, [1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.cross(ax, [0.0, 1.0, 0.0])
b.p = tuple(np.asarray(b.p, float) + lat / np.linalg.norm(lat) * 40.0)
if "perno" not in codes(GC.check(m)):
    fail("no se detecta un perno cuyo eje cae fuera de su pieza")
# 3) pieza que atraviesa a otra
m = copy.deepcopy(base)
col = next(p for p in m.parts if p.kind == "column")
lo, hi = col.bbox()
m.parts.append(Part("Intrusa", "plate", "placa atravesada", 36.0, 58.0, [box_prism((lo + hi) / 2.0, (30.0, 30.0, 0.5))], t=0.5))
r = GC.check(m)
if "choque" not in codes(r) or "suelta" not in codes(r):
    fail(f"no se detecta una placa que atraviesa la columna y está suelta: {codes(r)}")
# 4) sin uniones: el miembro queda sin camino al principal
m = copy.deepcopy(base)
m.welds, m.bolts = [], []
r = GC.check(m)
if not any(e["code"] == "suelta" for e in r):
    fail("no se detectan piezas sin unión al quitar todos los cordones y pernos")
# 5) pernos demasiado juntos y agujero que corta el borde
m = copy.deepcopy(base)
if len(m.bolts) >= 2:
    m.bolts[1].p = tuple(np.asarray(m.bolts[0].p, float) + lat / np.linalg.norm(lat) * 0.4)
    if not any(e["code"] == "perno" for e in GC.check(m)):
        fail("no se detectan dos pernos superpuestos")
# 6) recorte que se lleva toda la pieza
m = copy.deepcopy(base)
d1 = next(p for p in m.parts if p.kind == "brace")
c = np.vstack([pr.corners() for pr in d1.prisms]).mean(axis=0)
for pr in d1.prisms:
    pr.cut_planes = list(pr.cut_planes) + [(tuple(c + np.array([0.0, 0.0, 1e4])), (0.0, 0.0, -1.0))]
if "degenerada" not in codes(GC.check(m)):
    fail("no se detecta un recorte que elimina toda la pieza")
print(f"{'defectos sembrados':34} cordón separado, perno fuera, choque, pieza suelta, pernos superpuestos y recorte total se detectan: OK")

# 6b) cartelas: se recortan contra el principal, se sueldan a él y la diagonal no choca con la columna ni con la cartela
for ej in ("CN-07_placa_base_con_diagonal.scp", "CN-03_cordon_con_diagonales.scp", "CN-01_columna_con_vigas.scp"):
    pj = load_book(os.path.join(ROOT, "ejemplos", ej))[0]
    mj = AS.build_model(pj)
    gi = GC.check(mj)
    malos = [e["text"] for e in gi if e["sev"] == "error" and any(("Cartela" in n or n.startswith("D") or n.startswith("M")) and n in e["parts"] for n in e["parts"])
             and e["code"] in ("choque", "suelta", "soldadura", "perno")]
    if malos:
        fail(f"{ej}: cartela / diagonal con errores: {malos[:3]}")
    if not any(w.name.startswith("Cartela") for w in mj.welds) and ej.startswith("CN-07"):
        fail("la cartela de CN-07 no tiene cordones contra el principal")
print(f"{'cartelas':34} recortadas contra el principal, soldadas a él, sin choques con la diagonal: OK")

# 6c) barrido ortogonal: ningún caso lanza excepciones y los errores de geometría no crecen respecto de la línea base conocida
sys.path.insert(0, os.path.join(ROOT, "tools"))
import io, contextlib                                                      # noqa: E402
import barrido_geometria as BG                                             # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    cr, bad = BG.run()
n_bad = sum(sum(c.values()) for c in bad.values())
if cr:
    fail(f"el barrido lanzó excepciones: {cr[:2]}")
if n_bad > 6:
    fail(f"el barrido ortogonal da {n_bad} errores de geometría (línea base: 6, doble ángulo con tubo en columna estrecha): {dict((k, dict(v)) for k, v in bad.items())}")
print(f"{'barrido ortogonal':34} 288 combinaciones (8 conexiones × 3 principales × 3 vigas × 4 acimuts): sin excepciones, {n_bad} errores (base 6): OK")

# 6d) corte de una placa contra el plano de otra cara: el contorno se recorta y los cordones siguen el contorno nuevo
from steelconpro.conn import specs as SP, ops as OPS                       # noqa: E402
p5 = load_book(os.path.join(ROOT, "ejemplos", "CN-05_viga_con_placas_trapezoidales.scp"))[0]
n0 = len(AS.build_model(p5).part("P1").prisms[0].poly)
OPS.add_operation(p5.node, SP.OP_TRIM, targets=["P1"], parent=p5.node.main_name, face="Alma +", trim_gap=1.0)
m5 = AS.build_model(p5)
poly5 = m5.part("P1").prisms[0].poly
ys5 = [q[1] for q in poly5]
if max(ys5) > -0.7 or min(ys5) > -2.9 or not any(w.name.startswith("P1-W") and abs(w.p0[1] + 0.8) < 0.1 and abs(w.p1[1] + 0.8) < 0.1 for w in m5.welds):   # la holgura se mide hacia el lado que se conserva
    fail(f"corte de placa: contorno {poly5}")
p5.node.operations[-1].trim_flip = True
poly5b = AS.build_model(p5).part("P1").prisms[0].poly
if min(q[1] for q in poly5b) < 0.7:
    fail("corte de placa: «conservar el otro lado» no invierte el lado")
print(f"{'corte de placas':34} la placa se recorta contra el plano de otra cara (contorno, cordones y lado a conservar): OK")

# 6e) tapa de un cilindro / tubo redondo recortado: superficie cerrada
from steelconpro.conn.fem.model3d import cyl_prism                         # noqa: E402
from collections import Counter                                            # noqa: E402
for ri in (0.0, 1.5):
    cp = cyl_prism((0, 0, 0), (0, 0, 1), 2.0, 10.0, ri)
    cp.cut_planes = [((0, 0, 2.0), (0.5, 0, 0.8660254))]
    cnt = Counter()
    for fc in cp.faces():
        for i in range(len(fc)):
            a_, b_ = tuple(np.round(fc[i], 4)), tuple(np.round(fc[(i + 1) % len(fc)], 4))
            cnt[tuple(sorted((a_, b_)))] += 1
    if set(cnt.values()) != {2}:
        fail(f"cilindro recortado (ri={ri}) no queda cerrado: {Counter(cnt.values())}")
print(f"{'tapa de cilindros recortados':34} cilindro y tubo redondo con recorte oblicuo quedan cerrados: OK")

# 7) API
g = api.geometry_check({"connection": api._dump(prj)})
v = api.verify({"connection": api._dump(prj)})
if not g["ok"] or g["errors"] != 0 or "geometry" not in v or v["geometry"]["errors"] != 0:
    fail(f"API geometry_check / verify.geometry: {g.get('errors')}, {v.get('geometry')}")
print(f"{'API':34} geometry_check y el resumen dentro de verify: OK")

if fails:
    print(f"\nFALLAS ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("\nTODAS LAS PRUEBAS DEL REVISOR DE GEOMETRÍA PASARON")
