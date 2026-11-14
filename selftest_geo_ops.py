# -*- coding: utf-8 -*-
"""Pruebas de regresión de la geometría de las operaciones generales (placas, ángulos, pernos, huecos, soldaduras, recortes y planos de trabajo).

    python3 selftest_geo_ops.py        (termina con código ≠ 0 si algo falla)
"""
import sys, os, glob, math, traceback
sys.path.insert(0, ".")
import numpy as np

from steelconpro.model import new_connection, load_book
from steelconpro.conn import assembly as AS, geocheck as GC, ops as OPS, plates as PL
from steelconpro.conn.specs import *

FAIL = []


def fail(msg):
    FAIL.append(msg)
    print("  FALLA:", msg)


def prj(main="W14X90", el=90.0, members=()):
    p = new_connection()
    p.node.main_shape, p.node.main_el = main, el
    p.node.members = list(members)
    return p


def gen(p, kind, **kw):
    return OPS.add_operation(p.node, kind, **kw)


def build(p, label, clashes=True):
    try:
        m = AS.build_model(p)
    except Exception:
        fail(f"{label}: build_model lanzó una excepción\n{traceback.format_exc(limit=4)}")
        return None, []
    try:
        iss = GC.check(m, clashes=clashes)
    except Exception:
        fail(f"{label}: geocheck lanzó una excepción\n{traceback.format_exc(limit=4)}")
        return m, []
    return m, [e for e in iss if e["sev"] == "error"]


def area(poly):
    return abs(0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))))


def run():
    # ------------------------------------------------------------------ ejemplos TP-G*: sin errores del revisor y verify sin excepciones
    from steelconpro import api
    files = sorted(glob.glob(os.path.join("ejemplos", "TP-G*.scp")))
    if not files:
        fail("no hay ejemplos TP-G* en ejemplos/ (python3 tools/ejemplos_generales.py)")
    for f in files:
        for p in load_book(f):
            m, errs = build(p, os.path.basename(f))
            if errs:
                fail(f"{os.path.basename(f)}: {len(errs)} errores del revisor, p. ej. {errs[0]['text'][:140]}")
            try:
                api.verify({"connection": api._dump(p)})
            except Exception as e:                                                   # noqa: BLE001
                fail(f"{os.path.basename(f)}: verify lanzó {e!r}")
    print(f"{'ejemplos TP-G':34} {len(files)} archivos: build, revisor (0 errores) y verify: {'OK' if not FAIL else 'con fallas'}")

    # ------------------------------------------------------------------ barrido A: placas bien colocadas sobre alas y almas (soldadas y atornilladas): 0 errores
    n = 0
    for main, el in (("W14X90", 90.0), ("W18X50", 0.0), ("HSS8X8X1/2", 90.0)):
        shp = AS.shape_of(main)
        for face in OPS.face_names_of(shp):
            if face in FACES_END:
                continue
            for shape in (PLATE_SHAPES[0], PLATE_SHAPES[2], PLATE_SHAPES[4], PLATE_SHAPES[5]):
                for orient in PLATE_ORIENTS[:1]:
                    for rot in (0.0, 90.0):
                        for att in (ATTACHES[0], ATTACHES[1]):
                            p = prj(main, el)
                            gen(p, OP_PLATE, parent=p.node.main_name, face=face, shape=shape, orient=orient, pl_rot=rot, pl_L=4.0, pl_W=2.5, pl_s=24.0, plate_t=0.375, attach=att,
                                rows=1, cols=1, pl_L2=2.0)
                            m, errs = build(p, f"placa {main} {face} {shape} {orient} {rot} {att}")
                            n += 1
                            if errs:
                                fail(f"placa {main} {face} {shape} rot {rot} {att}: {errs[0]['text'][:120]}")
    print(f"{'barrido de placas paralelas':34} {n} casos")

    # ------------------------------------------------------------------ barrido B: solo que no lance excepciones (formas × orientaciones × caras, incluidos redondos, extremos y giros)
    n = 0
    for main, el in (("W14X90", 90.0), ("HSS8X4X3/8", 20.0), ("HSS6.625X0.280", 90.0)):
        shp = AS.shape_of(main)
        for face in OPS.face_names_of(shp):
            for shape in PLATE_SHAPES:
                for orient in PLATE_ORIENTS:
                    for rot in (0.0, 30.0):
                        for att in ATTACHES:
                            p = prj(main, el)
                            kw = dict(parent=p.node.main_name, face=face, shape=shape, orient=orient, pl_rot=rot, pl_L=5.0, pl_W=3.0, pl_s=20.0, attach=att, rows=2, cols=1,
                                      opening=OPENINGS[2], op_W=1.0, op_H=1.0)
                            if shape == PLATE_SHAPES[6]:
                                kw["pts"] = [[-2.5, -1.5], [2.5, -1.5], [0.0, 1.5]]
                            gen(p, OP_PLATE, **kw)
                            m, _ = build(p, f"excepciones {main} {face} {shape} {orient}", clashes=False)
                            n += 1
    print(f"{'barrido sin excepciones':34} {n} casos")

    # ------------------------------------------------------------------ pernos a través de varias capas: agarre real (placa, ala, placa del otro lado)
    p = prj("W14X90", 90.0)
    nd = p.node
    nd.main_end = END_LABELS[0]
    gen(p, OP_PLATE, name="A1", parent=nd.main_name, face=FACES_I[2], pl_L=10.0, pl_W=6.0, pl_s=60.0, plate_t=0.5, attach=ATTACHES[2])
    gen(p, OP_PLATE, name="A2", parent=nd.main_name, face=FACES_I[3], pl_L=10.0, pl_W=6.0, pl_s=60.0, plate_t=0.375, attach=ATTACHES[2])
    gen(p, OP_BOLTS, parent="A1", face="Cara +", targets=[nd.main_name, "A2"], rows=2, cols=1, bolt_s=3.0, pl_s=5.0, pl_u=0.0)
    m, errs = build(p, "pernos de tres capas")
    if errs:
        fail(f"pernos de tres capas: {errs[0]['text'][:120]}")
    b = m.bolts[0]
    nm = [g[0] for g in b.grip]
    if nm != ["A1", "M1", "A2"] if False else nm != ["A1", nd.main_name, "A2"]:
        fail(f"el agarre debe ser placa, alma, placa (salió {nm})")
    else:
        t = [round(g[2] - g[1], 3) for g in b.grip]
        if t != [0.5, round(AS.shape_of("W14X90").tw, 3), 0.375] or abs(b.grip[1][1] - 0.5) > 0.01:
            fail(f"espesores del agarre {t} (esperado [0.5, tw, 0.375])")
    print(f"{'pernos a través de varias capas':34} agarre {nm}: {'OK' if not FAIL else ''}")

    # ------------------------------------------------------------------ recorte de placas: plano, volumen, invertir, dependencias circulares
    def plate_model(shape_kw=None):
        p = prj("W14X90", 90.0)
        p.node.members = [Member(name="V1", shape="W12X26", az=0.0, el=0.0, pos=0.0, L=48.0)]
        kw = dict(parent=p.node.main_name, face=FACES_I[0], pl_L=20.0, pl_W=12.0, pl_s=67.0, plate_t=0.5)
        kw.update(shape_kw or {})
        pl = gen(p, OP_PLATE, **kw)
        return p, pl

    p, pl = plate_model()
    a0 = area(AS.build_model(p).elems[pl.name]["geo"]["poly"])
    tr = gen(p, OP_TRIM, targets=[pl.name], parent="V1", face=FACES_I[0], trim_gap=0.0)
    m, errs = build(p, "recorte de placa contra un plano")
    g = m.elems[pl.name]["geo"]
    if not (area(g["poly"]) < a0 - 1.0):
        fail("el plano de la cara de V1 debe recortar la placa")
    tr.trim_flip = True
    m2, _ = build(p, "recorte invertido")
    a_flip = area(m2.elems[pl.name]["geo"]["poly"]) if m2 and pl.name in m2.elems else 0.0
    if abs(a_flip + area(g["poly"]) - a0) > 0.5 and a_flip > 0:
        fail(f"el recorte invertido debe conservar el otro lado (áreas {a_flip:.1f} + {area(g['poly']):.1f} ≠ {a0:.1f})")
    p, pl = plate_model(dict(pl_L=20.0, pl_s=67.0))
    tr = gen(p, OP_TRIM, targets=[pl.name], parent="V1", trim_mode=TRIM_MODES[2], trim_gap=0.5)
    m, errs = build(p, "recorte de placa contra el volumen")
    ge = m.elems[pl.name]["geo"]
    if len(ge["poly"]) <= 4 and not ge.get("holes"):
        fail("el volumen de V1 debe abrir una muesca o una abertura en la placa")
    # el contorno recortado manda: plate_edges y los pernos usan el contorno nuevo
    edges = api_edges(p, pl.name)
    if len(edges) < 5:
        fail(f"plate_edges debe listar los bordes del contorno recortado ({len(edges)})")
    # dependencia circular: se informa y no se cuelga
    p, pl = plate_model()
    q = gen(p, OP_PLATE, name="Q9", parent=pl.name, face="Cara +", orient=PLATE_ORIENTS[1], pl_L=4.0, pl_W=2.0, pl_s=10.0)
    gen(p, OP_TRIM, targets=[pl.name], parent="Q9", trim_mode=TRIM_MODES[2])
    m, _ = build(p, "dependencia circular")
    if m is not None and not any("circular" in n_ for n_ in m.notes):
        fail("la dependencia circular de un recorte debe informarse en las notas")
    # el plano se lleva toda la placa / no la toca: nota clara
    p, pl = plate_model()
    gen(p, OP_TRIM, targets=[pl.name], parent="V1", face=FACES_I[0], trim_gap=-60.0)
    m, _ = build(p, "recorte que no toca")
    if m is not None and not any("recorte" in n_.lower() or "recorta" in n_.lower() or "plano" in n_.lower() for n_ in m.notes):
        fail("un plano que no toca (o se lleva) la placa debe dejar una nota")
    print(f"{'recorte de placas':34} plano, volumen, invertir, bordes, circular: OK" if not FAIL else "recorte de placas: con fallas")

    # ------------------------------------------------------------------ recorte de ángulos (plano y volumen)
    p = prj("W14X90", 90.0)
    p.node.members = [Member(name="V1", shape="W12X26", az=0.0, el=0.0, pos=0.0, L=48.0)]
    an = gen(p, OP_ANGLE, name="AN", parent=p.node.main_name, face=FACES_I[0], leg_a=4.0, leg_b=4.0, pl_L=24.0, pl_s=60.0, plate_t=0.375, attach=ATTACHES[0])
    gen(p, OP_TRIM, targets=["AN"], parent="V1", trim_mode=TRIM_MODES[2], trim_gap=0.25)
    m, errs = build(p, "recorte de ángulo contra volumen")
    L = m.elems["AN"]["faces"][FACES_ANGLE[0]].L
    if not (L < 23.0):
        fail(f"el volumen de V1 debe acortar el ángulo (largo {L:.1f})")
    gen(p, OP_TRIM, targets=["AN"], parent="V1", face=FACES_I[1])
    build(p, "recorte de ángulo contra un plano")
    print(f"{'recorte de ángulos':34} largo {L:.1f} in: OK")

    # ------------------------------------------------------------------ recorte de miembros I / HSS / redondo: extremos, holguras y dos recortes
    n = 0
    for shp in ("W12X26", "HSS6X6X3/8", "HSS6.625X0.280"):
        for az, el in ((0, 0), (0, 45), (30, 20), (90, -40)):
            for end in ("Inicio", "Fin"):
                for gap in (0.0, 0.5, -0.5):
                    for two in (False, True):
                        p = prj("W14X90", 90.0, [Member(name="D1", shape=shp, az=az, el=el, pos=5.0, L=40.0)])
                        gen(p, OP_TRIM, targets=["D1"], parent="Columna", face=FACES_I[0], trim_gap=gap, trim_end=end)
                        if two:
                            gen(p, OP_TRIM, targets=["D1"], parent="Columna", face=FACES_I[1], trim_gap=gap, trim_end=end)
                        m, errs = build(p, f"recorte de miembro {shp} {az}/{el} {end} {gap} {two}", clashes=False)
                        n += 1
                        if m is None:
                            continue
                        bad = [e for e in errs if e["code"] == "degenerada"]
                        if bad:
                            fail(f"recorte de miembro {shp} {az}/{el} {end}: {bad[0]['text'][:100]}")
                        for pr in m.part("D1").prisms:
                            if not pr.faces():
                                fail(f"recorte de miembro {shp} {az}/{el} {end}: prisma sin caras")
                                break
    print(f"{'recorte de miembros':34} {n} casos")

    # ------------------------------------------------------------------ soldadura: una placa que sobresale de la cara solo suelda donde hay apoyo
    p = prj("W14X90", 90.0)
    gen(p, OP_PLATE, name="SB", parent=p.node.main_name, face=FACES_I[2], pl_L=10.0, pl_W=20.0, pl_s=60.0, plate_t=0.5)       # el alma libre mide ~12.6 in
    m, errs = build(p, "placa que sobresale")
    if errs:
        fail(f"la placa que sobresale no debe dejar cordones en el aire: {errs[0]['text'][:120]}")
    print(f"{'placa que sobresale de la cara':34} cordones recortados al apoyo: {'OK' if not errs else 'con fallas'}")

    # ------------------------------------------------------------------ renombrar / eliminar elementos con dependientes y convertir a piezas
    p = prj("W14X90", 90.0)
    a = gen(p, OP_PLATE, parent=p.node.main_name, face=FACES_I[0], pl_L=6.0, pl_W=4.0, pl_s=60.0)
    b = gen(p, OP_PLATE, parent=a.name, face="Cara +", orient=PLATE_ORIENTS[1], role="Rigidizador", pl_L=4.0, pl_W=2.0, pl_s=3.0)
    gen(p, OP_FILLET, weld_main=b.name, weld_to=[[a.name, "Cara +"]])
    if not p.node.rename_element(a.name, "PX") or b.parent != "PX" or p.node.operations[2].weld_to[0][0] != "PX":
        fail("renombrar una placa debe actualizar a sus dependientes")
    removed = OPS.delete_operation(p.node, 0)
    if len(removed) < 3 or any(o.name == "PX" for o in p.node.operations):
        fail(f"eliminar una placa debe quitar sus dependientes ({len(removed)})")
    print(f"{'renombrar y eliminar':34} OK")

    # ------------------------------------------------------------------ triangulación con agujeros que tocan el borde o entre sí
    from steelconpro.conn import geom2d as G
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    for holes in ([G.circle_poly(5, 5, 2, 16)], [G.circle_poly(3, 5, 1.5, 12), G.circle_poly(7, 5, 1.5, 12)], [G.circle_poly(5, 1.5, 1.5, 12)], [G.circle_poly(2, 2, 1.0, 8), G.circle_poly(4.2, 2, 1.0, 8)]):
        try:
            hc = [G.cw(h) for h in holes]
            pts = outer + [q for h in hc for q in h]
            tri = G.triangulate(outer, hc)
            ar = sum(abs(G.area([pts[i] for i in t])) for t in tri)
            if not tri or abs(ar - (100.0 - sum(abs(G.area(h)) for h in holes))) > 0.6:
                fail(f"triangulación con agujeros: área {ar:.2f} no coincide")
        except Exception as e:                                                        # noqa: BLE001
            fail(f"triangulación con agujeros lanzó {e!r}")
    print(f"{'triangulación con agujeros':34} OK")


def api_edges(p, name):
    from steelconpro import api
    idx = next(i for i, o in enumerate(p.node.operations) if o.name == name)
    return api.plate_edges({"connection": api._dump(p), "index": idx})["edges"]


if __name__ == "__main__":
    print("=" * 100)
    print("GEOMETRÍA DE LAS OPERACIONES GENERALES")
    print("=" * 100)
    run()
    if FAIL:
        print(f"\nFALLAS ({len(FAIL)}):")
        for f in FAIL:
            print("  -", f)
        sys.exit(1)
    print("\nTodo bien: selftest_geo_ops OK")
