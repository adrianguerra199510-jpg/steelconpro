# -*- coding: utf-8 -*-
"""Pruebas de geometría de cartelas, nudos de armadura, placa base y tipologías.  Uso: python3 selftest_geo_cartelas.py
Barre diagonales (perfil, ángulo, acimut, conexión) sobre columnas W y HSS, varias diagonales por nudo, cartela de esquina, tipologías, y recorre los
ejemplos ejemplos/TP-A*.scp (0 errores del revisor, `api.verify` sin excepciones)."""
import copy
import glob
import itertools
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from steelconpro.model import Project, load_book                                  # noqa: E402
from steelconpro.conn import assembly as AS, geocheck as GC, typologies as TY     # noqa: E402
from steelconpro.conn.specs import (CT_NODE, OP_GUSSET, OP_GUSSET_W, OP_TAB, OP_BASE, END_LABELS, Member, Operation, Nodo)   # noqa: E402
from steelconpro import api                                                       # noqa: E402

fails = []
HSS = "ASTM A500 Gr.C (HSS rect.)"


def fail(t):
    fails.append(t)
    print("FALLA:", t)


def steel(s):
    return HSS if s.startswith("HSS") else "ASTM A992"


def prj(nd):
    p = Project()
    p.ctype = CT_NODE
    p.node = nd
    return p


def errs(p):
    return [e for e in GC.check(AS.build_model(p)) if e["sev"] == "error"]


def col(shape="W14X90", end=0, neg=96.0, pos=96.0):
    return Nodo(main_name="Columna", main_shape=shape, main_steel=steel(shape), main_el=90.0, main_end=END_LABELS[end], main_len_neg=neg, main_len_pos=pos)


# 1) barrido de una diagonal
n = 0
for kind, dsh, csh, az, el in itertools.product((OP_GUSSET, OP_GUSSET_W), ("HSS6X6X3/8", "W8X31"), ("W14X90", "HSS12X12X1/2"),
                                                (0, 90, 180, 270, 20, 30, 60, 150, 210), (-60.0, -30.0, 30.0, 45.0, 70.0)):
    nd = col(csh)
    nd.members = [Member(name="D1", shape=dsh, steel=steel(dsh), az=float(az), el=el, L=72.0)]
    nd.operations = [Operation(kind=kind, member="D1", plate_t=0.5)]
    n += 1
    try:
        e = errs(prj(nd))
    except Exception as ex:                                                       # noqa: BLE001
        fail(f"excepción {kind[:12]} {dsh} {csh} az {az} el {el}: {ex!r}")
        continue
    if e:
        fail(f"{kind[:12]} {dsh} {csh} az {az} el {el}: {e[0]['text'][:120]}")
print(f"{'barrido de una diagonal':34} {n} casos: {'OK' if not fails else 'con fallas'}")

# 2) varias diagonales en el mismo nudo (K, V, X) y montante
f0 = len(fails)
for csh, shapes in itertools.product(("W14X90", "HSS12X12X1/2"), ("HSS5X5X3/8", "W8X31")):
    for plan in ([(0, 45), (0, -45)], [(0, 45), (180, 45)], [(0, 45), (180, 45), (0, -45), (180, -45)], [(0, 45), (90, 45), (180, 45), (270, 45)]):
        for kind in (OP_GUSSET, OP_GUSSET_W):
            nd = col(csh)
            nd.members = [Member(name=f"D{i + 1}", shape=shapes, steel=steel(shapes), az=float(a), el=float(e), L=60.0) for i, (a, e) in enumerate(plan)]
            nd.operations = [Operation(kind=kind, member=m.name, plate_t=0.5) for m in nd.members]
            try:
                e = errs(prj(nd))
            except Exception as ex:                                               # noqa: BLE001
                fail(f"excepción varias diagonales {csh} {shapes} {plan}: {ex!r}")
                continue
            if e:
                fail(f"varias diagonales {csh} {shapes} {plan} {kind[:12]}: {e[0]['text'][:120]}")
print(f"{'varias diagonales por nudo':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 3) nudos de armadura: cordón HSS / W con diagonales y montante
f0 = len(fails)
for chord, kind in itertools.product(("HSS10X10X3/8", "W14X61"), (OP_GUSSET, OP_GUSSET_W)):
    for plan in ([(0, -45), (180, -45)], [(0, -45), (0, -90)], [(0, 45), (180, 45), (0, 90)], [(0, -45), (180, -45), (0, 45), (180, 45)]):
        nd = Nodo(main_name="Cordón", main_shape=chord, main_steel=steel(chord), main_el=0.0, main_end=END_LABELS[0], main_len_neg=96.0, main_len_pos=96.0)
        nd.members = [Member(name=f"D{i + 1}", shape="HSS4X4X1/4", steel=HSS, az=float(a), el=float(e), L=60.0) for i, (a, e) in enumerate(plan)]
        nd.operations = [Operation(kind=kind, member=m.name, plate_t=0.5) for m in nd.members]
        e = errs(prj(nd))
        if e:
            fail(f"armadura {chord} {plan} {kind[:12]}: {e[0]['text'][:120]}")
print(f"{'nudos de armadura':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 4) cartela de esquina contra viga y columna
f0 = len(fails)
for el, gap in ((-45.0, 6.0), (45.0, 6.0), (-35.0, 12.0), (55.0, 5.0)):
    for kind in (OP_GUSSET, OP_GUSSET_W):
        nd = col("W14X90", neg=120.0)
        nd.members = [Member(name="V1", shape="W18X50", steel="ASTM A992", az=0.0, el=0.0, L=96.0),
                      Member(name="D1", shape="HSS6X6X3/8", steel=HSS, az=0.0, el=el, L=96.0, gap=gap)]
        nd.operations = [Operation(kind=OP_TAB, member="V1"), Operation(kind=kind, member="D1", plate_t=0.5)]
        m = AS.build_model(prj(nd))
        e = [x for x in GC.check(m) if x["sev"] == "error"]
        if e:
            fail(f"cartela de esquina el {el} gap {gap} {kind[:12]}: {e[0]['text'][:120]}")
        if not any(w.B == "V1" and w.A.startswith("Cartela") for w in m.welds):
            fail(f"cartela de esquina el {el} gap {gap}: la cartela no se suelda a la viga")
print(f"{'cartela de esquina':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 5) medidas editadas y cartela cortada
f0 = len(fails)
for L, hb, hm, cut in ((0, 0, 0, 0), (24, 16, 9, 2.5), (18, 0, 7, 1.5), (30, 20, 0, 0), (0, 12, 12, 3)):
    for dsh in ("HSS6X6X3/8", "W8X31"):
        nd = col()
        nd.members = [Member(name="D1", shape=dsh, steel=steel(dsh), az=0.0, el=-45.0, L=72.0)]
        nd.operations = [Operation(kind=OP_GUSSET, member="D1", plate_t=0.5, gus_L=float(L), gus_hb=float(hb), gus_hm=float(hm), gus_cut=float(cut))]
        e = errs(prj(nd))
        if e:
            fail(f"medidas L {L} hb {hb} hm {hm} cut {cut} {dsh}: {e[0]['text'][:120]}")
print(f"{'medidas editadas':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 6) placa base: la cartela apoya en la cara superior (cordón sobre ella, sin hundirse)
f0 = len(fails)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ejemplos_arriostramientos as EA                                            # noqa: E402
for fn in (EA.ex_a08, EA.ex_a09, EA.ex_a10):
    p = fn()
    m = AS.build_model(p)
    top = m.elems["Placa base"]["faces"]["Cara superior"]
    zt = float(top.O[2])
    wb = [w for w in m.welds if w.B == "Placa base"]
    if not wb:
        fail(f"{p.element}: ningún cordón a la placa base")
    for w in wb:
        if abs(w.p0[2] - zt) > 0.02 or abs(w.p1[2] - zt) > 0.02:
            fail(f"{p.element}: cordón a la placa base fuera de su cara superior (z {w.p0[2]:.2f} / {w.p1[2]:.2f}, cara {zt:.2f})")
    for g in (q for q in m.parts if q.kind == "gusset"):
        zmin = min(float(c[2]) for pr in g.prisms for c in pr.corners())
        if zmin < zt - 0.02:
            fail(f"{p.element}: {g.name} hundida en la placa base ({zmin:.2f} < {zt:.2f})")
print(f"{'cartelas sobre la placa base':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 7) tipologías con sus parámetros en los límites
f0 = len(fails)
for kind in ("base", "col", "vigas"):
    sch = TY.schema(kind)
    lims = []
    for f in sch:
        if f["type"] in ("num", "int"):
            lims.append((f["key"], [f["lo"], f["default"], f["hi"]]))
        elif f["type"] == "bool":
            lims.append((f["key"], [False, True]))
    for key, vals in lims:
        for v in vals:
            nd = TY.build_nodo(kind, {key: v})
            p = prj(nd)
            if kind == "base":
                from steelconpro.conn import baseplate as BP                     # noqa: F401
                p = EA._with_base_data(p)
            try:
                e = errs(p)
            except Exception as ex:                                               # noqa: BLE001
                fail(f"excepción tipología {kind} {key}={v}: {ex!r}")
                continue
            if e:
                fail(f"tipología {kind} {key}={v}: {e[0]['text'][:120]}")
print(f"{'tipologías en sus límites':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 9) diagonales de ángulo y de canal contra la cartela
f0 = len(fails)
for dsh, kind, csh, az, el in itertools.product(("L4X4X1/4", "C8X11.5", "L6X6X3/8"), (OP_GUSSET, OP_GUSSET_W), ("W14X90", "HSS12X12X1/2"), (0, 90, 30), (-45.0, 45.0)):
    nd = col(csh)
    nd.members = [Member(name="D1", shape=dsh, steel="ASTM A992", az=float(az), el=el, L=60.0)]
    nd.operations = [Operation(kind=kind, member="D1", plate_t=0.5)]
    e = errs(prj(nd))
    if e:
        fail(f"ángulo/canal {dsh} {kind[:12]} {csh} az {az} el {el}: {e[0]['text'][:110]}")
print(f"{'diagonales de ángulo y canal':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 10) cruce de una X: diagonal continua (principal) y la otra en dos tramos con cartela común
f0 = len(fails)
for msh, dsh, kind in itertools.product(("HSS6X6X3/8", "W10X33"), ("HSS4X4X1/4", "W6X15"), (OP_GUSSET, OP_GUSSET_W)):
    nd = Nodo(main_name="Diagonal 1", main_shape=msh, main_steel=steel(msh), main_az=0.0, main_el=45.0, main_end=END_LABELS[0], main_len_neg=60.0, main_len_pos=60.0)
    nd.members = [Member(name="D2", shape=dsh, steel=steel(dsh), az=0.0, el=-45.0, L=48.0), Member(name="D3", shape=dsh, steel=steel(dsh), az=180.0, el=45.0, L=48.0)]
    nd.operations = [Operation(kind=kind, member=m.name, plate_t=0.5) for m in nd.members]
    e = errs(prj(nd))
    if e:
        fail(f"cruce de X {msh} {dsh} {kind[:12]}: {e[0]['text'][:110]}")
print(f"{'cruce de X':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 11) aviso cuando la cartela sobresale de la placa base
f0 = len(fails)
p = EA.ex_a08()
if any("sobresale" in x for x in AS.build_model(p).notes):
    fail("TP-A08 no debe avisar de borde de placa base")
p.plate.N, p.conc.N2 = 16.0, 40.0
if not any("sobresale" in x and "placa base" in x for x in AS.build_model(p).notes):
    fail("falta el aviso de cartela que sobresale de la placa base")
print(f"{'aviso de borde de placa base':34} {'OK' if len(fails) == f0 else 'con fallas'}")

# 8) ejemplos TP-A*
f0 = len(fails)
files = sorted(glob.glob(os.path.join(ROOT, "ejemplos", "TP-A*.scp")))
if not files:
    fail("no hay ejemplos TP-A*.scp")
for f in files:
    p = load_book(f)[0]
    try:
        e = errs(p)
        v = api.verify({"connection": api._dump(p)})
    except Exception as ex:                                                       # noqa: BLE001
        fail(f"{os.path.basename(f)}: excepción {ex!r}")
        continue
    if e:
        fail(f"{os.path.basename(f)}: {e[0]['text'][:120]}")
print(f"{'ejemplos TP-A':34} {len(files)} archivos: {'OK' if len(fails) == f0 else 'con fallas'}")

print("\nTODO OK" if not fails else f"\n{len(fails)} FALLAS")
sys.exit(1 if fails else 0)
