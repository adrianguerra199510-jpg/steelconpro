# -*- coding: utf-8 -*-
"""Empalme de viga con cubreplacas (operación «Empalme de viga con cubreplacas (momento)»): geometría de las variantes atornilladas y soldadas, sin
errores del revisor; verificaciones AISC 360-22 comparadas con cálculos a mano; fracción de la resistencia de la viga; empalme de columna; Claude Desktop.

    python3 selftest_empalme.py
"""
import math
import os
import sys
import tempfile
from dataclasses import asdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from steelconpro import api                                                    # noqa: E402
from steelconpro.model import Project                                          # noqa: E402
from steelconpro.shapes import CATALOG                                         # noqa: E402
from steelconpro.conn.specs import CT_NODE, Nodo, Member, Operation, Load, END_LABELS, OP_SPLICE   # noqa: E402
from steelconpro.conn import assembly as AS, geocheck as GC, ops as OPS        # noqa: E402

FAILS = []


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def near(a, b, tol=0.005):
    return abs(a - b) <= tol * max(abs(b), 1e-9)


def proyecto(**kw):
    p = Project()
    p.ctype = CT_NODE
    p.u_len, p.u_force, p.u_stress, p.u_moment = "in", "kip", "ksi", "kip-in"
    nd = Nodo(main_name="V1", main_shape="W18X50", main_steel="ASTM A992", main_el=0.0, main_az=0.0, main_end=END_LABELS[1])
    nd.members = [Member(name="V2", shape="W18X50", steel="ASTM A992", az=0.0, el=0.0)]
    nd.operations = [Operation(kind=OP_SPLICE, member="V2", bolt_size="7/8", bolt_grade="A325-N", plate_t=0.5, plate_steel="ASTM A572 Gr.50", weld_size=0.25, **kw)]
    nd.loads = [Load("Caso 1", "V2", Vz=-30.0, My=1500.0)]
    p.node = nd
    return p


def checks_of(p):
    v = api.verify({"connection": asdict(p)})
    return {c["key"].split("_", 1)[1]: c for c in v["checks"] if c["key"].startswith("op0_")}, v


def geometria():
    print("== Geometría ==")
    for kw, nb, nw in (({}, 24 + 10, 0), ({"sp_inner": True}, 24 + 10, 0), ({"sp_flange": "Soldada"}, 10, 12), ({"sp_web": "Soldada"}, 24, 12),
                       ({"sp_flange": "Soldada", "sp_web": "Soldada", "sp_inner": True}, 0, 40)):
        p = proyecto(**kw)
        mdl = AS.build_model(p)
        err = [e for e in GC.check(mdl) if e["sev"] == "error"]
        nplates = len([x for x in mdl.parts if x.name.startswith(("Cubreplaca", "Placa alma"))])
        check(not err and len(mdl.bolts) == nb and len(mdl.welds) == nw and nplates == (8 if kw.get("sp_inner") else 4),
              f"{kw or 'atornillado'}: {len(mdl.bolts)} pernos, {len(mdl.welds)} filetes, {nplates} placas, {len(err)} errores de geometría")
    mdl = AS.build_model(proyecto(sp_inner=True))
    check(all(b.planes == 2 for b in mdl.bolts), "con cubreplacas interiores los pernos de las alas trabajan en doble cortante (y los del alma siempre)")
    v2 = next(x for x in mdl.parts if x.name == "V2")
    x0 = min(pr.corners()[:, 0].min() for pr in v2.prisms)
    check(abs(x0 - 0.25) < 1e-6, f"V2 empieza a la separación de la junta (sp_gap = 0.25 in): x = {x0:.3f}")


def verificaciones():
    print("\n== Verificaciones (AISC 360-22) ==")
    b = CATALOG.get("W18X50")
    ck, v = checks_of(proyecto())
    Ff = 1500.0 / (b.d + 0.5)
    check(near(ck["sp_fb"]["demand"], Ff) and near(ck["sp_fb"]["capacity"], 0.75 * 54.0 * math.pi * 0.875 ** 2 / 4 * 6),
          f"pernos de las alas: Ff = M/(d + tp) = {Ff:.1f} kip contra 6 pernos en simple cortante ({ck['sp_fb']['capacity']:.1f} kip)")
    Afg, Afn = b.bf * b.tf, (b.bf - 2 * 1.0) * b.tf
    Mn = min(b.Zx * 50.0, 65.0 * Afn / Afg * b.Sx) if 65.0 * Afn < 50.0 * Afg else b.Zx * 50.0
    check(near(ck["sp_f13"]["capacity"], 0.9 * Mn), f"F13.1: flexión de la viga con los agujeros del ala ({ck['sp_f13']['capacity']:.0f} kip·in)")
    check(near(ck["sp_wbeam"]["capacity"], 0.75 * 0.6 * 65.0 * (b.d - 5 * 1.0) * b.tw), "rotura por cortante del alma de la viga en la línea de pernos (5 pernos)")
    check(ck["sp_wb"]["demand"] > 30.0 / 5 and "Mw" in ck["sp_wb"]["note"], "pernos del alma: cortante con excentricidad y la parte del momento de las placas del alma")
    check(any("todo el momento" in w for w in v["warnings"]), "aviso del reparto de fuerzas")
    ck2, _ = checks_of(proyecto(sp_cap=1.0))
    check(near(ck2["sp_f13"]["demand"], 0.9 * 50.0 * b.Zx) and ck2["sp_f13"]["demand"] > ck2["sp_f13"]["capacity"],
          "con la resistencia completa de la viga (sp_cap = 1) el empalme atornillado no alcanza: F13.1 lo limita")
    ck3, _ = checks_of(proyecto(sp_flange="Soldada", sp_web="Soldada"))
    q = 0.6 * 70 * 0.707 * 0.25
    lf, bo = max(6.0, math.ceil(1.5 * (b.bf - 1.0))), b.bf - 1.0
    Rn = max(q * 2 * lf + q * bo, 0.85 * q * 2 * lf + 1.5 * q * bo)
    check(near(ck3["sp_fw"]["capacity"], 0.75 * Rn), f"alas soldadas: filetes longitudinales y transversal, J2-10 ({ck3['sp_fw']['capacity']:.0f} kip)")
    check({"sp_ww", "sp_wwmin", "sp_fwmin", "sp_fwmax"} <= set(ck3) and "sp_fb" not in ck3, "soldado: filetes en C del alma y tamaños de filete; sin pernos")
    ck4, _ = checks_of(proyecto(sp_inner=True))
    check(near(ck4["sp_fb"]["capacity"], 2 * ck["sp_fb"]["capacity"]), "con cubreplacas interiores, doble cortante en los pernos de las alas")


def columna_y_mcp():
    print("\n== Empalme de columna y Claude Desktop ==")
    nd = Nodo(main_name="C1", main_shape="W14X90", main_steel="ASTM A992", main_el=90.0)
    nd.members = [Member(name="C2", shape="W14X90", steel="ASTM A992", az=45.0, el=10.0, pos=12.0)]
    OPS.add_operation(nd, OP_SPLICE, member="C2")
    m = nd.members[0]
    check(abs(m.el - 90.0) < 1e-9 and m.pos == 0.0 and nd.main_end == END_LABELS[1], "al agregar el empalme el miembro se alinea con el principal, que pasa a terminar en el nudo")
    p = Project()
    p.ctype = CT_NODE
    p.node = nd
    mdl = AS.build_model(p)
    check(not [e for e in GC.check(mdl) if e["sev"] == "error"] and len(mdl.bolts) > 0, f"empalme de columna W14X90 sin errores de geometría ({len(mdl.bolts)} pernos)")
    p2 = proyecto()
    p2.node.members[0].az = 30.0
    mdl2 = AS.build_model(p2)
    check(any("en línea" in n for n in mdl2.notes) and not [x for x in mdl2.parts if x.name.startswith("Cubreplaca")], "si el miembro no sigue al principal, el empalme no se arma y lo avisa")
    from steelconpro import chat as C
    with tempfile.TemporaryDirectory() as ws:
        s = C.Session(ws)
        C.nueva_conexion(s, "Empalme", principal={"perfil": "W18X50"})
        C.agregar_miembro(s, "V2", "W18X50")
        C.agregar_operacion(s, "Empalme de viga", {"member": "V2", "sp_flange": "Soldada", "sp_inner": True, "sp_cap": 0.5})
        check(s.nd.operations[0].sp_flange == "Soldada" and C.revisar_geometria(s)["errores"] == 0, "por chat (MCP): empalme soldado con interiores, sin errores de geometría")


def viga_doble():
    """TP-V44: empalme soldado de viga doble 2 × HN600×200×11×17 armado con operaciones generales (placas y soldaduras entre elementos)."""
    print("\n== Viga doble con operaciones generales (TP-V44) ==")
    import glob
    from steelconpro.model import load_book
    f = glob.glob(os.path.join(ROOT, "ejemplos", "TP-V44_*.scp"))
    check(len(f) == 1, "existe el ejemplo TP-V44")
    if not f:
        return
    p = load_book(f[0])[0]
    mdl = AS.build_model(p)
    err = [e for e in GC.check(mdl) if e["sev"] == "error"]
    pl = sorted(x.name for x in mdl.parts if x.name[:3] in ("CP-", "PA-"))
    pairs = {(w.A, w.B) for w in mdl.welds}
    check(not err and pl == ["CP-I", "CP-S", "PA-a", "PA-b"] and not [n for n in mdl.notes if "» no toca a «" in n],
          f"cuatro vigas, 2 cubreplacas y 2 placas de alma (cara exterior), sin errores de geometría ({pl}, {len(err)} errores)")
    check({("CP-S", b) for b in ("V1a", "V1b", "V2a", "V2b")} <= pairs and {("PA-a", "V1a"), ("PA-a", "V2a"), ("PA-b", "V1b"), ("PA-b", "V2b")} <= pairs,
          "cada cubreplaca soldada a las cuatro vigas y cada placa de alma a las dos vigas de su lado")
    v = api.verify({"connection": asdict(p)})
    res = [c for c in v["checks"] if "resistencia" in c["title"]]
    check(len(res) == 12 and max(c["demand"] / c["capacity"] for c in res) < 1.0, f"soldaduras con las fuerzas de diseño (D/C máx {max(c['demand'] / c['capacity'] for c in res):.2f})")
    from steelconpro.conn import nodal as NOD
    for cn, loads in NOD.cases_of(p.node):
        b = NOD.balance(p.node, loads)
        check(abs(b["main_local"]["Vz"]) > 1.0, f"«{cn}»: V1b equilibra a V2b y el principal toma la acción de V2a (Vz = {b['main_local']['Vz']:.0f} kip)")


if __name__ == "__main__":
    viga_doble()
    geometria()
    verificaciones()
    columna_y_mcp()
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)
