# -*- coding: utf-8 -*-
"""Caras por componente de las secciones del Section Designer: cada rectángulo, polígono, círculo o tubo de una sección libre aporta sus caras a las
operaciones generales (placa, ángulo, pernos, huecos, soldadura y posición referenciada), de modo que una placa se apoya en la cara de un componente
(p. ej. el alma de una viga de una sección doble) y no en la envolvente de la sección.

    python3 selftest_caras_secciones.py
"""
import glob
import os
import sys
from dataclasses import asdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from steelconpro import api, sections as SEC                                      # noqa: E402
from steelconpro.model import Project, load_book                                  # noqa: E402
from steelconpro.shapes import CATALOG, make_general                              # noqa: E402
from steelconpro.conn import assembly as AS, geocheck as GC, ops as OPS           # noqa: E402
from steelconpro.conn.specs import (CT_NODE, Nodo, Operation, OP_PLATE, OP_FILLET, PLATE_ROLES, PLATE_ORIENTS, PLATE_SHAPES, ATTACHES)   # noqa: E402

MM = 1 / 25.4
FAILS = []


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def doble():
    comps = [{"t": "rect", "x": x * MM, "y": y * MM, "w": 200 * MM, "h": 17 * MM, "rot": 0.0} for x in (-100, 100) for y in (292, -292)]
    comps += [{"t": "rect", "x": x * MM, "y": 0.0, "w": 11 * MM, "h": 566 * MM, "rot": 0.0} for x in (-100, 100)]
    return make_general("2XHN600X200X11X17", comps)


def caras():
    print("== Caras de los componentes ==")
    s = doble()
    fc = {f["name"]: f for f in s.comp_faces()}
    check(len(fc) == 24, f"6 rectángulos × 4 caras = 24 caras ({len(fc)})")
    f = fc["Comp. 6 (Rect.) — Cara +X"]
    check(abs(f["c"][0] - 105.5 * MM) < 1e-9 and abs(f["c"][1]) < 1e-9 and f["n"] == (1.0, -0.0) or f["n"][0] == 1.0, "alma derecha: su cara +X está a 105.5 mm del eje, mirando hacia afuera")
    check(abs(f["half"] - 283 * MM) < 1e-6 and abs(f["wall"] - 11 * MM) < 1e-9, f"alma derecha: cara de 566 mm de alto y espesor 11 mm ({f['half'] / MM * 2:.0f}, {f['wall'] / MM:.0f})")
    f1 = fc["Comp. 1 (Rect.) — Cara +Y"]
    check(abs(f1["c"][0] + 100 * MM) < 1e-9 and abs(f1["c"][1] - 300.5 * MM) < 1e-9, "ala superior izquierda: su cara +Y está a 300.5 mm sobre el centroide")
    names = OPS.face_names_of(s)
    check(names[0].startswith("Comp. 1") and names[-6:] == ["Cara +X", "Cara −X", "Cara +Y", "Cara −Y", "Extremo inicio", "Extremo fin"],
          "la lista del desplegable: primero los componentes y al final la envolvente y los extremos (compatibilidad con los proyectos anteriores)")
    ff = AS.member_faces if False else OPS.member_faces(s, (0, 0, 0), (60, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    check(set(names) <= set(ff), "member_faces devuelve todas las caras de la lista")
    check(abs(ff["Cara +X"].O[1] - 200 * MM) < 1e-6, "envolvente: la cara +X de la caja queda en el borde exterior de las alas (200 mm)")
    # circulo, tubo, poligono y rectangulo girado
    comps = [{"t": "circ", "x": 0.0, "y": 0.0, "d": 4.0}, {"t": "ring", "x": 10.0, "y": 0.0, "d": 6.0, "ti": 0.5},
             {"t": "poly", "pts": [[20, 0], [24, 0], [22, 3]]}, {"t": "rect", "x": 30.0, "y": 0.0, "w": 2.0, "h": 1.0, "rot": 30.0}]
    g = make_general("MIX", comps)
    nm = [f["name"] for f in g.comp_faces()]
    check(nm[:4] == [f"Comp. 1 (Círculo) — Tangente {d}" for d in ("+X", "−X", "+Y", "−Y")] and nm[4].startswith("Comp. 2 (Tubo) — Tangente"), f"círculo y tubo: cuatro caras tangentes ({nm[:5]})")
    check([n for n in nm if "Polígono" in n] == [f"Comp. 3 (Polígono) — Lado {k}" for k in (1, 2, 3)], "polígono: una cara por lado")
    check([n for n in nm if "Rect." in n] == [f"Comp. 4 (Rect.) — Lado {k}" for k in (1, 2, 3, 4)], "rectángulo girado: Lado 1 a 4")
    tg = [f for f in g.comp_faces() if f["name"].endswith("Tangente +X") and "Tubo" in f["name"]][0]
    check(abs(tg["c"][0] - (10.0 + 3.0 - g.ox)) < 1e-9 and tg["wall"] == 0.5, "tubo: la tangente +X toca el exterior del tubo y su espesor es el de la pared")
    bad = make_general("DESC", [{"t": "rect", "x": 0.0, "y": 0.0, "w": 4.0, "h": 2.0, "rot": 0.0}, {"t": "rect", "x": 9.0, "y": 0.0, "w": 6.0, "h": 2.0, "rot": 0.0}])
    ex = bad.extent()
    check(abs(ex[0] + 7.4) < 1e-9 and abs(ex[2] - 6.6) < 1e-9, f"caja envolvente respecto del centroide, aunque la sección no esté centrada en su caja ({ex[0]:.2f}, {ex[2]:.2f})")


def modelo():
    print("\n== Placas y soldaduras sobre las caras de los componentes ==")
    s = doble()
    CATALOG.shapes[s.label] = s
    CATALOG._reindex()
    st = "ASTM A572 Gr.50"
    nd = Nodo(main_name="V", main_shape=s.label, main_steel=st, main_el=0.0, main_az=0.0, main_len_neg=60, main_len_pos=60)
    P = lambda **k: Operation(kind=OP_PLATE, member="", role=PLATE_ROLES[0], orient=PLATE_ORIENTS[0], shape=PLATE_SHAPES[0], attach=ATTACHES[2], plate_steel=st, plate_t=20 * MM, **k)   # noqa: E731
    nd.operations = [P(name="PA", parent="V", face="Comp. 6 (Rect.) — Cara +X", pl_L=1000 * MM, pl_W=500 * MM, pl_s=60.0),
                     P(name="PB", parent="V", face="Comp. 5 (Rect.) — Cara −X", pl_L=1000 * MM, pl_W=500 * MM, pl_s=60.0),
                     P(name="CP", parent="V", face="Comp. 1 (Rect.) — Cara +Y", pl_L=700 * MM, pl_W=340 * MM, pl_s=60.0),
                     Operation(kind=OP_FILLET, member="", weld_main="PA", weld_to=[["V", "Comp. 6 (Rect.) — Cara +X"]], weld_size=12 * MM, weld_all=True),
                     Operation(kind=OP_FILLET, member="", weld_main="PB", weld_to=[["V", "Comp. 5 (Rect.) — Cara −X"]], weld_size=12 * MM, weld_all=True),
                     Operation(kind=OP_FILLET, member="", weld_main="CP", weld_to=[["V", "Comp. 1 (Rect.) — Cara +Y"], ["V", "Comp. 3 (Rect.) — Cara +Y"]], weld_size=14 * MM, weld_all=True)]
    p = Project()
    p.ctype = CT_NODE
    p.node = nd
    m = AS.build_model(p)
    box = {x.name: tuple(round(v / MM, 1) for v in (*x.bbox()[0], *x.bbox()[1])) for x in m.parts if x.name in ("PA", "PB", "CP")}
    check(abs(box["PA"][1] - 105.5) < 0.1 and abs(box["PA"][4] - 125.5) < 0.1, f"PA apoya en la cara exterior del alma derecha (y = 105.5 a 125.5 mm): {box['PA'][1]} a {box['PA'][4]}")
    check(abs(box["PB"][4] + 105.5) < 0.1, f"PB apoya en la cara exterior del alma izquierda (y = −125.5 a −105.5 mm): {box['PB'][1]} a {box['PB'][4]}")
    check(abs(box["CP"][2] - 300.5) < 0.1 and abs(box["CP"][1] + 270.0) < 0.1, f"CP apoya sobre el ala superior izquierda (z = 300.5 mm), centrada en ella (y = −270 a 70): {box['CP'][1]} a {box['CP'][4]}")
    pairs = {(w.A, w.B) for w in m.welds}
    check(pairs == {("PA", "V"), ("PB", "V"), ("CP", "V")} and len(m.welds) == 13, f"soldaduras entre las placas y las caras de la sección ({len(m.welds)} cordones)")
    check(not [e for e in GC.check(m) if e["sev"] == "error"] and not [n for n in m.notes if "» no toca a «" in n], "sin errores de geometría ni avisos de que la placa no toca")
    el = OPS.elements(p)["elements"][0]
    check("Comp. 6 (Rect.) — Cara +X" in el["faces"] and len(el["faces"]) == 30, f"element_info ofrece las caras de los componentes ({len(el['faces'])} caras)")
    e2 = api.element_info({"connection": asdict(p)})["elements"][0]
    check("Comp. 1 (Rect.) — Cara +Y" in e2["faces"], "la API entrega las caras a la interfaz")
    # compatibilidad: una placa sobre la envolvente de la seccion (nombre antiguo) sigue armandose
    nd.operations = [P(name="PE", parent="V", face="Cara +X", pl_L=500 * MM, pl_W=300 * MM, pl_s=60.0)]
    mm = AS.build_model(p)
    pe = next(x for x in mm.parts if x.name == "PE")
    check(abs(pe.bbox()[0][1] / MM - 200.0) < 0.1, f"la cara «Cara +X» de la envolvente sigue funcionando (proyectos anteriores): y = {pe.bbox()[0][1] / MM:.1f} mm")


def ejemplo():
    print("\n== Ejemplo TP-V45 ==")
    f = glob.glob(os.path.join(ROOT, "ejemplos", "TP-V45_*.scp"))
    check(len(f) == 1, "existe el ejemplo TP-V45")
    if not f:
        return
    p = load_book(f[0])[0]
    check(len(p.node.members) == 1 and CATALOG.get("2XHN600X200X11X17") is not None and CATALOG.get("2XHN600X200X11X17").kind == "GEN",
          "solo 2 miembros (principal y V2) con la sección personalizada guardada en el archivo")
    m = AS.build_model(p)
    check(not [e for e in GC.check(m) if e["sev"] == "error"] and len(m.welds) == 28, f"sin errores de geometría; 28 cordones ({len(m.welds)})")
    v = api.verify({"connection": asdict(p)})
    res = [c for c in v["checks"] if "resistencia" in c["title"]]
    check(len(res) == 12 and max(c["demand"] / c["capacity"] for c in res) < 1.0, f"soldaduras con las fuerzas de diseño (D/C máx {max(c['demand'] / c['capacity'] for c in res):.2f})")


if __name__ == "__main__":
    caras()
    modelo()
    ejemplo()
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)
