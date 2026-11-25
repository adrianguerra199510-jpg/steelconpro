# -*- coding: utf-8 -*-
"""Pruebas del ANÁLISIS del modelo de placas (CalculiX): reducción de piezas a placas (ángulos en cualquier orientación, uniones solo donde hay
soldadura, agujeros que no impiden compartir la arista), modelo de CalculiX (pernos, contacto, concreto, anclajes, apoyos y cargas), solución
(conjunto activo + elasto-plástico) y verificaciones por componente (miembros, placas, pernos, soldaduras, anclajes).

    python3 selftest_fem_placas.py            (CN-02 y CN-04 completos; TP-G22 solo el modelo)
    python3 selftest_fem_placas.py --rapido   (sin resolver con CalculiX)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from steelconpro.conn import assembly as AS                                                    # noqa: E402
from steelconpro.conn.fem import shellmesh as SM, shellccx as SC, shellpost as SP, shellchecks as SCK   # noqa: E402
from steelconpro.model import load_book                                                         # noqa: E402

FAILS = []
RAPIDO = "--rapido" in sys.argv


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def ejemplo(nombre):
    return load_book(os.path.join(ROOT, "ejemplos", nombre))[0]


def mallar(p, mdl, td):
    plates, notes = SM.build_plates(mdl)
    jf, npz = os.path.join(td, "j.json"), os.path.join(td, "m.npz")
    SM.write_job(plates, SM.shell_params(p.fea, mdl, 1.0), jf)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), "--meshs", jf, npz], capture_output=True, text=True, timeout=600)
    check(r.returncode == 0 and os.path.exists(npz), f"malla de placas generada ({r.stdout.strip()[-60:]})")
    return plates, json.load(open(jf, encoding="utf-8")), SM.ShellMesh(npz)


def nodos_de(sm, pred):
    s = set()
    for i, k in enumerate(sm.keys):
        if pred(i):
            for row in list(sm.tri[i]) + list(sm.quad[i]):
                s.update(int(x) for x in row)
    return s


def cn02(td):
    print("\n== CN-02: viga con secundarias (placa extrema, placa simple, doble ángulo) ==")
    p = ejemplo("CN-02_viga_con_secundarias.scp")
    mdl = AS.build_model(p, {"case": 0})
    plates, job, sm = mallar(p, mdl, td)
    # ángulos: cada pierna con el espesor del ángulo (también el ángulo espejado)
    # ángulos: el ángulo espejado (S3-2) se reduce igual que S3-1: mismas piernas y espesores, en posición simétrica respecto del alma de S3
    a1 = sorted(((round(q.t, 4), tuple(np.round(q.c, 3))) for q in plates if q.part == "Angulo S3-1"), key=lambda t: t[0])
    a2 = sorted(((round(q.t, 4), tuple(np.round(q.c, 3))) for q in plates if q.part == "Angulo S3-2"), key=lambda t: t[0])
    check(len(a1) == len(a2) == 2 and [t for t, _c in a1] == [t for t, _c in a2], f"ángulos S3-1 y S3-2: dos piernas con los mismos espesores ({[t for t, _c in a1]}, {[t for t, _c in a2]})")
    check(len(a1) == 2 and all(abs((c1[0] - 36.0) + (c2[0] - 36.0)) < 0.02 for (_t, c1), (_t2, c2) in zip(a1, a2)), "el ángulo espejado queda simétrico respecto del alma de S3")
    # el talón del ángulo atornillado NO se une al alma del principal (no hay soldadura); la viga sí se une a su placa extrema soldada
    ang = nodos_de(sm, lambda i: sm.parts[i].startswith("Angulo"))
    main = nodos_de(sm, lambda i: sm.parts[i] == "Viga principal")
    check(not (ang & main), "los ángulos atornillados no comparten nodos con el principal (solo apoyan)")
    s1 = nodos_de(sm, lambda i: sm.parts[i] == "S1")
    ep = nodos_de(sm, lambda i: sm.parts[i] == "Placa extrema S1")
    check(len(s1 & ep) >= 20, f"la viga S1 comparte nodos con su placa extrema soldada ({len(s1 & ep)})")
    # punto de aplicación de la carga: «Automático» = en los pernos para la placa simple de S2; «En el extremo» = donde el eje llega al nudo
    from steelconpro.conn import nodal as NOD
    from steelconpro.conn.specs import LOAD_AT
    check(NOD.load_point_mode(p.node, "S2") == "pernos" and NOD.load_point_mode(p.node, "S1") == "nudo",
          "automático: en los pernos para la placa simple (S2), en el extremo para la placa extrema (S1)")
    pb = NOD.load_points(p.node, mdl).get("S2")
    bs = [np.asarray(b.p) + np.asarray(b.axis) * 0.5 * (s0 + s1) for b in mdl.bolts for (pn, s0, s1) in b.grip if pn == "S2"]
    check(pb is not None and np.allclose(pb, np.mean(bs, axis=0)), "el punto de aplicación de S2 es el centro de sus pernos")
    ld_auto = next(l for l in mdl.loads if l.name == "Carga de S2")
    import copy
    q = copy.deepcopy(p)
    q.node.member_named("S2").load_at = LOAD_AT[1]
    ld_end = next(l for l in AS.build_model(q, {"case": 0}).loads if l.name == "Carga de S2")
    dM = np.cross(pb - NOD._node_point(p.node, "S2"), np.asarray(ld_auto.F))
    check(np.allclose(np.asarray(ld_auto.M) - np.asarray(ld_end.M), dM, atol=1e-6) and np.allclose(ld_auto.F, ld_end.F),
          f"la carga del análisis se traslada desde los pernos (diferencia de momento {np.round(dM, 1).tolist()} kip·in)")
    case = SC.ShellCase(mdl, sm, job)
    check(len(case.bolt_ax) == len(mdl.bolts), f"los {len(mdl.bolts)} pernos entran al modelo ({len(case.bolt_ax)})")
    aux = [n2 for (_e, _n1, n2, _k, kind) in case.gaps if kind == "contacto"]
    check(aux and all(max(abs(float(SC.unit(case.coord(n2) - case.coord(n1)) @ SC.unit(case.plates[q]["n"]))) for q in case.node_plates[n1]) > 1.0 - 1e-6
                      for (_e, n1, n2, _k, kind) in case.gaps if kind == "contacto"), "los resortes de contacto actúan solo normales a las placas")
    check(len(case.gaps) > 100 and all(k == "contacto" for *_x, k in case.gaps), f"contacto solo-compresión entre placas atornilladas ({len(case.gaps)} resortes)")
    check(len(case.meta["loads"]) == 3 and len(case.meta["supports"]) == 1, "tres cargas (extremos de S1, S2, S3) y el apoyo del principal")
    if RAPIDO:
        return
    t0 = time.time()
    ok, msg, info = SC.solve(case, os.path.join(td, "ccx"))
    check(ok and not info.get("plastic_failed"), f"CalculiX resuelve el caso ({time.time() - t0:.0f} s, {info.get('iters')} iteraciones; {msg[:80]})")
    if not ok:
        return
    R = SP.postprocess(case, info, [p.node.main_name] + [m.name for m in p.node.members], "Caso 1")
    check(0.05 < R.umax < 2.0, f"desplazamiento máximo razonable ({R.umax:.3f} in)")
    b2 = [b for b in R.bolts if b["tag"].startswith("S2")]
    vs = sorted(b["V"] for b in b2)
    # los pernos de la placa simple de S2 llevan el cortante de S2 (25 kip en 3 pernos, con excentricidad)
    check(len(b2) == 3 and vs[-1] - vs[0] < 1.5 and abs(sum(vs) - 25.0) < 2.5,
          f"carga en los pernos: los 3 pernos de S2 toman el cortante de 25 kip por partes iguales ({', '.join(f'{v:.1f}' for v in vs)} kip)")
    cks = SCK.checks(R, case, mdl, [p.node.main_name] + [m.name for m in p.node.members], p.units())
    cats = {c.cat for c in cks}
    check({"Miembros", "Placas", "Pernos", "Soldaduras"} <= cats, f"verificaciones por categoría ({', '.join(sorted(cats))})")
    check(all(c.comp for c in cks), "cada verificación nombra su componente")
    sc = SP.scene(R, p.units(), "vm", SP.auto_scale(R))
    check(sc.cbar is not None and len(sc.opaque) == 1, "escena de resultados (von Mises sobre la deformada)")


def cn04(td):
    print("\n== CN-04: columna con placa base ==")
    p = ejemplo("CN-04_columna_con_placa_base.scp")
    mdl = AS.build_model(p, {"case": 0})
    plates, job, sm = mallar(p, mdl, td)
    fl = [i for i, k in enumerate(sm.keys) if sm.parts[i] == "Columna" and job["plates"][i]["holes"]]
    web = [i for i, k in enumerate(sm.keys) if sm.parts[i] == "Columna" and abs(sm.thick[i] - 0.44) < 1e-6]
    if fl and web:
        sh = nodos_de(sm, lambda i: i == fl[0]) & nodos_de(sm, lambda i: i == web[0])
        check(len(sh) > 30, f"el ala con agujeros comparte la arista con el alma ({len(sh)} nodos)")
    case = SC.ShellCase(mdl, sm, job)
    anc = [b for b in case.meta["bolts"] if b.get("anchor")]
    check(len(anc) == 8 and not case.bolt_bidir, f"8 anclajes a punto fijo, solo a tracción porque la placa apoya en el concreto ({len(anc)})")
    check(sum(1 for *_x, k in case.gaps if k == "concreto") > 50 and not case.meta["supports"], "concreto como resortes solo-compresión bajo la placa y sin apoyo rígido")
    if RAPIDO:
        return
    t0 = time.time()
    ok, msg, info = SC.solve(case, os.path.join(td, "ccx"))
    check(ok, f"CalculiX resuelve el caso ({time.time() - t0:.0f} s; {msg[:80]})")
    if ok:
        R = SP.postprocess(case, info, [p.node.main_name] + [m.name for m in p.node.members], "Caso 1")
        check(R.umax < 1.5, f"desplazamiento máximo razonable ({R.umax:.3f} in)")
        cks = SCK.checks(R, case, mdl, [p.node.main_name] + [m.name for m in p.node.members], p.units())
        check(any(c.cat == "Anclajes y concreto" for c in cks), "verificaciones de los anclajes con las fuerzas del modelo")


def g22(td):
    print("\n== TP-G22: torre de cuatro tubos sobre placa separada del pedestal ==")
    p = ejemplo("TP-G22_torre_cuatro_tubos_sobre_placa.scp")
    mdl = AS.build_model(p, {"case": 0})
    plates, job, sm = mallar(p, mdl, td)
    case = SC.ShellCase(mdl, sm, job)
    anc = [b for b in case.meta["bolts"] if b.get("anchor")]
    check(len(anc) == 4, f"los pernos que entran al pedestal son anclajes ({len(anc)})")
    check(case.bolt_bidir == {b["index"] for b in anc}, "placa separada del concreto: los anclajes trabajan a tracción y compresión")
    check(not case.meta["supports"], "la columna se apoya en el pedestal a través de la placa (sin empotramiento)")
    check(not any("nonpositive" in n for n in case.notes), "sin elementos degenerados en el modelo")


def main():
    with tempfile.TemporaryDirectory() as td:
        for f in (cn02, cn04, g22):
            sub = os.path.join(td, f.__name__)
            os.makedirs(sub)
            f(sub)
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
