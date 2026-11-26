# -*- coding: utf-8 -*-
"""Validación de la placa extrema precalificada contra los ejemplos de AISC Design Guide 4, 2.ª ed. (Murray y Sumner, 2003):
4.2 (4E, ejemplos A sísmico y B no sísmico), 4.3 (4ES) y 4.4 (8ES): viga W21X55 y columna W14X109, ASTM A992, placa ASTM A572 Gr. 50.
Además, la conexión armada en el modelo (filas, rigidizadores, geometría sin errores) y su verificación desde el nudo.

Diferencias conocidas con los ejemplos (se comprueban con el valor correcto):
  · cortante de los pernos: Fnv de AISC 360-22 (A325-N 54, A490-N 68 ksi) en lugar de las de AISC 1999 (48, 60);
  · 8ES: la guía redondea Lp ≈ 11.5 in (Muc = 8083); aquí Lp = Lst + tp = 10.39 + 0.875 = 11.27 in (Muc = 8074);
  · esbeltez del rigidizador: 0.56·√(29000/50) = 13.49 (la guía escribe 13.5 en el 4ES y 13.4 en el 8ES);
  · 4E B, rotura de la extensión: la guía escribe An = 6.13 in², pero (9 − 2·1.125)·0.875 = 5.91 in² (φRn = 172.8 kip, no 179).

    python3 selftest_dg4.py
"""
import os
import sys
import tempfile
from dataclasses import asdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from steelconpro.conn.checks import endplate_dg4 as D          # noqa: E402

FAILS = []


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def near(a, b, tol=0.006, ab=0.0051):
    return abs(a - b) <= max(tol * abs(b), ab)


def comp(name, I, expected):
    bad = []
    for k, v in expected.items():
        got = I[k]
        if isinstance(v, tuple):
            ok = all(near(x, y) for x, y in zip(got, v))
        else:
            ok = near(got, v)
        if not ok:
            bad.append(f"{k}: {got if not isinstance(got, tuple) else tuple(round(x, 2) for x in got)} ≠ {v}")
    check(not bad, f"{name}: {len(expected)} valores del ejemplo" + (" — " + "; ".join(bad) if bad else ""))


def ejemplos():
    print("== Ejemplos de la Design Guide 4 ==")
    I = {}
    D.design(D.DG4("4E", bolt_size="1-1/4", bolt_grade="A490-N", tp=1.25, Vg=40.0, cont_plates=True, cont_t=0.5), info=I)
    comp("4E ejemplo A (sísmico)", I, {"Mpe": 7623, "Lp": 10.4, "Muc": 8039, "h": (22.54, 18.02), "Pt": 138.7, "phiMnp": 8438, "db_req": 1.22, "s": 3.52, "Yp": 148.2,
                                      "tp_req": 1.19, "Ffu": 396, "ext_y": 304, "ext_r": 228, "bearing": 732, "Yc": 170.1, "tfc_req": 1.10, "Ycs": 309.1, "tfc_req_s": 0.82,
                                      "phiMcf": 5661, "R15": 279, "R16": 309, "R17": 330, "R18": 268, "Fsu": 128})
    check(near(I["bolt_shear"], 0.75 * 4 * 68 * 1.2272), f"4E A: cortante de los pernos con Fnv = 68 ksi de AISC 360-22 ({I['bolt_shear']:.0f} kip; la guía, con 60 ksi: 221)")
    I = {}
    D.design(D.DG4("4E", bolt_size="1", bolt_grade="A325-N", tp=0.875, seismic=False), 4000.0, 40.0, info=I)
    comp("4E ejemplo B (no sísmico)", I, {"Muc": 4000, "phiMnp": 4301, "db_req": 0.96, "Yp": 148.2, "tp_req": 0.85, "Ffu": 197, "ext_y": 213, "bearing": 411,
                                         "Yc": 170.1, "tfc_req": 0.790, "R16": 289, "R17": 330, "R18": 268})
    check(near(I["ext_r"], 0.75 * 0.6 * 65 * (9.0 - 2 * 1.125) * 0.875), f"4E B: rotura de la extensión con An = 5.91 in² ({I['ext_r']:.1f} kip; la guía escribe 6.13 in² → 179)")
    I = {}
    D.design(D.DG4("4ES", bolt_size="1-1/4", bolt_grade="A490-N", tp=1.125, ts=0.375, Vg=40.0), info=I)
    comp("4ES", I, {"Yp": 194.6, "tp_req": 1.03, "ts_req": 0.375, "hst": 3.625, "Lst": 6.28, "slender": 9.67, "slender_lim": 13.49})
    I = {}
    D.design(D.DG4("8ES", bolt_size="1", bolt_grade="A325-N", tp=0.875, ts=0.375, Vg=40.0, cont_plates=True, cont_t=0.5), info=I)
    comp("8ES", I, {"Mpe": 7623, "h": (25.29, 22.29, 18.27, 15.27), "Pt": 70.7, "phiMnp": 8603, "db_req": 0.97, "s": 3.52, "Yp": 277.6, "tp_req": 0.87, "ts_req": 0.375,
                    "hst": 6.0, "Lst": 10.4, "slender": 16.0, "slender_lim": 13.49, "ts_bk": 0.448, "bearing": 807, "Yc": 224.6, "tfc_req": 0.97, "Ycs": 377.7,
                    "tfc_req_s": 0.75, "phiMcf": 7475, "R15": 369, "R16": 290, "R17": 330, "R18": 268})
    check(near(I["Muc"], 7623 + 40 * (10.392 + 0.875)) and near(I["Muc"], 8083, 0.002), f"8ES: Muc = Mpe + Vu·(Lst + tp) = {I['Muc']:.0f} kip·in (la guía, con Lp ≈ 11.5: 8083)")
    check(I["slender"] > I["slender_lim"], "8ES: con ts = 3/8 el rigidizador no cumple la esbeltez (la guía pide ts ≥ 0.448 → 1/2 in)")
    ck = D.design(D.DG4("8ES", bolt_size="1", bolt_grade="A325-N", tp=0.875, Vg=40.0))
    ts = next(c for c in ck if c.key == "dg4_ts")
    check("0.5" in ts.note or abs(ts.capacity - 0.5) < 1e-9, f"8ES: con ts = 0 se toma el requerido redondeado a 1/16 in ({ts.capacity:g} in, la guía usa 1/2)")
    rng = next(c for c in D.design(D.DG4("4E", bolt_size="1-1/4", bolt_grade="A490-N", tp=1.25, Vg=40.0)) if c.key == "dg4_rng")
    check(rng.skip and "d = 20.8" in rng.note, f"el rango ensayado (tabla 3.6) es un aviso, no una falla ({rng.note[:70]})")


def modelo():
    print("\n== Conexión 8ES en el modelo ==")
    from steelconpro import api, chat as C
    from steelconpro.conn import assembly as AS
    with tempfile.TemporaryDirectory() as ws:
        s = C.Session(ws)
        C.nueva_conexion(s, "DG4 8ES", principal={"perfil": "W14X109"})
        C.agregar_miembro(s, "V1", "W21X55")
        C.agregar_operacion(s, "Placa extrema extendida", {"member": "V1", "ep_dg4": "8ES", "bolt_size": "1", "bolt_grade": "A325-N", "plate_t": 0.875, "plate_steel": "ASTM A572 Gr.50",
                                                           "wf_top": "CJP (penetración completa)", "wf_bot": "CJP (penetración completa)", "weld_size": 0.3125})
        C.agregar_operacion(s, "Placas de continuidad", {"member": "V1", "cont_t": 0.5})
        C.modificar_miembro(s, "V1", {"sism_Vg": 40.0})
        C.definir_cargas(s, [{"caso": "Caso 1", "miembro": "V1", "Vz": -40.0, "My": 4000.0}])
        mdl = AS.build_model(s.p)
        stf = [p_ for p_ in mdl.parts if p_.name.startswith("Rigidizador V1")]
        check(len(mdl.bolts) == 16 and len(stf) == 2, f"8ES: 16 pernos y 2 rigidizadores ({len(mdl.bolts)}, {len(stf)})")
        lay = AS.endplate_layout(s.p.node.operations[0], __import__("steelconpro.shapes", fromlist=["CATALOG"]).CATALOG.get("W21X55"), True)
        check([round(y, 3) for y in lay["rows"][:4]] == [round(20.8 / 2 + 1.75 + 3.0, 3), round(20.8 / 2 + 1.75, 3), round(20.8 / 2 - 0.522 - 1.75, 3), round(20.8 / 2 - 0.522 - 1.75 - 3.0, 3)]
              and abs(lay["hh"] - (10.4 + 1.75 + 3.0 + 1.25)) < 1e-9 and abs(lay["wide"] - 9.22) < 1e-9, "8ES: filas, alto (pfo + pb + de) y ancho (bf + 1) según la guía")
        g = C.revisar_geometria(s)
        check(g["errores"] == 0, f"8ES armada sin errores de geometría ({g['errores']}: {g['hallazgos'][:2]})")
        v = api.verify({"connection": asdict(s.p)})
        tp = next((c for c in v["checks"] if "líneas de fluencia — tp,req" in c["title"]), None)
        check(tp is not None and abs(tp["demand"] - 0.87) < 0.01, f"verificación DG4 desde el nudo: tp,req = {tp and round(tp['demand'], 3)} in (ejemplo 8ES: 0.87, con bp = 9 en vez de bf + 1 = 9.22)")
        mb = next(c for c in v["checks"] if "Pernos sin palanca" in c["title"])
        check("Mpe = 1.1·Ry·Fy·Zx" in mb["note"] and "8074" not in mb["note"], "diseño sísmico con Mpe y el cortante de gravedad de la ficha de la viga")
        check(not any("T equivalente" in w for w in v["warnings"]), "la placa precalificada no usa la aproximación de T equivalente")
        C.modificar_operacion(s, 1, {"ep_dg4": "4E", "plate_t": 1.25, "bolt_size": "1-1/4", "bolt_grade": "A490-N"})
        mdl = AS.build_model(s.p)
        check(len(mdl.bolts) == 8 and not [p_ for p_ in mdl.parts if p_.name.startswith("Rigidizador V1")], "4E: 8 pernos y sin rigidizadores")


def nudo():
    """Verificaciones del nudo SMF (AISC 341-22 E3.4a, E3.6e, E3.6f; AISC 360-22 J10.6, J10.8) y la plantilla fija «smf» de Nuevo proyecto."""
    print("\n== Nudo de pórtico especial (AISC 341) y plantilla fija ==")
    import math
    from steelconpro import api, chat as C
    from steelconpro.shapes import CATALOG
    from steelconpro.conn import typologies as TY, assembly as AS, geocheck as GC
    from steelconpro.conn.specs import CT_NODE, END_LABELS
    from steelconpro.model import Project
    check(any(k == "smf" for k, _ in TY.TYPES) and any(t["id"] == "smf" for t in api.typologies()["types"]), "la plantilla «smf» está entre las tipologías de Nuevo proyecto")
    col, bm = CATALOG.get("W14X109"), CATALOG.get("W21X55")
    I = {}
    D.design(D.DG4("8ES", bolt_size="1", bolt_grade="A325-N", tp=0.875, ts=0.5, Vg=40.0, cont_plates=True, cont_t=0.5), info=I)
    Mpb1 = I["Mpe"] + I["Vu"] * (I["Lp"] + col.d / 2)
    for prm, n, ncol in (({}, 1, 2), ({"two_sided": True, "cont_t": 0.5}, 2, 2), ({"two_sided": True}, 2, 2), ({"top": True}, 1, 1), ({"two_sided": True, "top": True, "dg4": "4E", "bolt_size": "1-1/4", "bolt_grade": "A490-N", "plate_t": 1.25}, 2, 1)):
        c = api.connection_new({"typology": "smf", "params": prm, "u_len": "in", "u_force": "kip", "u_stress": "ksi", "u_moment": "kip-in"})
        p = Project(); p.ctype = CT_NODE; p.node = TY.build_nodo("smf", prm)
        err = [e for e in GC.check(AS.build_model(p)) if e["sev"] == "error"]
        check(not err, f"plantilla {prm or 'por omisión'}: sin errores de geometría ({len(err)}: {[e['text'][:80] for e in err[:1]]})")
        v = api.verify({"connection": c})
        ck = {x["key"]: x for x in v["checks"]}
        need = ["smf_scwb", "smf_pz", "smf_pzt", "smf_cp_t", "smf_cp_b", "smf_cp_t16", "smf_cp_bt", "smf_cp_ww", "smf_cp_wf"]
        check(all(k in ck for k in need), f"plantilla {prm or 'por omisión'}: las verificaciones del nudo están ({[k for k in need if k not in ck]} faltan)")
        if not all(k in ck for k in need):
            continue
        check(f"{ncol}·Zc" in ck["smf_scwb"]["note"] and f"de {n} viga(s)" in ck["smf_scwb"]["note"], f"  columna fuerte–viga débil con {ncol} columna(s) y {n} viga(s)")
        if prm == {}:
            Prc = float(ck["smf_scwb"]["note"].split("Prc = ")[1].split(" ")[0])
            check(near(ck["smf_scwb"]["demand"], Mpb1, 0.002) and near(ck["smf_scwb"]["capacity"], 2 * col.Zx * (50.0 - Prc / col.A), 0.002),
                  f"  E3.4a: ΣM*pb = Mpe + Vu·(Lp + dc/2) = {Mpb1:.0f} y ΣM*pc = 2·Zc·(Fy − Prc/Ag) = {ck['smf_scwb']['capacity']:.0f} kip·in")
            Ru = I["Muc"] / (bm.d - bm.tf) - Mpb1 / 157.48
            Rv = 0.6 * 50 * col.d * col.tw * (1 + 3 * col.bf * col.tf ** 2 / (bm.d * col.d * col.tw))
            check(near(ck["smf_pz"]["demand"], Ru, 0.002) and near(ck["smf_pz"]["capacity"], Rv, 0.002), f"  E3.6e: Ru = Muc/(d − tf) − Vc = {Ru:.0f}, Rv (J10.6(b)) = {Rv:.0f} kip")
            check(near(ck["smf_pzt"]["demand"], (bm.d - 2 * bm.tf + col.d - 2 * col.tf) / 90), "  E3.6e.2: (dz + wz)/90")
            check(near(ck["smf_cp_t"]["demand"], 0.5 * bm.tf) and near(ck["smf_cp_b"]["capacity"], col.bf / 2), "  E3.6f.2: placas ≥ 0.5·tbf con una viga; ancho bs + twc/2 = bfc/2")
            check(near(ck["smf_cp_bt"]["capacity"], 0.56 * math.sqrt(29000 / 36.0)), "  esbeltez de la placa de continuidad 0.56·√(E/Fy)")
        if prm == {"two_sided": True}:
            check(abs(ck["smf_cp_t"]["capacity"] - 0.625) < 1e-9 and ck["smf_cp_t"]["demand"] <= ck["smf_cp_t"]["capacity"], "  espesor automático de las placas de continuidad con dos vigas: tbf = 0.522 → 5/8 in")
            dg = [x for x in v["checks"] if "_dg4_" in x["key"] and "V2" in x["title"] and not x.get("skip")]
            check(max(x["demand"] / x["capacity"] for x in dg) < 1.0, "  las placas de continuidad de V1 también rigidizan la columna frente a V2 (DG4 de V2 con placas de continuidad)")
        if prm == {"two_sided": True, "cont_t": 0.5}:
            check(near(ck["smf_cp_t"]["demand"], bm.tf) and ck["smf_cp_t"]["demand"] > ck["smf_cp_t"]["capacity"], "  con dos vigas, placas ≥ tbf: 1/2 in no alcanza (tbf = 0.522)")
            check(ck["smf_pz"]["demand"] > ck["smf_pz"]["capacity"] and "placa adosada" in ck["smf_pz"]["note"], "  la zona del panel con dos vigas no alcanza e indica la placa adosada")
    with tempfile.TemporaryDirectory() as ws:                    # MCP: misma plantilla por chat
        s = C.Session(ws)
        C.nueva_conexion(s, "SMF", tipologia="smf", parametros={"dg4": "4ES", "plate_t": 1.125, "bolt_size": "1-1/4", "bolt_grade": "A490-N", "H": 144.0})
        check(abs(s.p.seis.H - 144.0) < 1e-9 and s.p.node.operations[0].ep_dg4 == "4ES" and s.p.node.main_end == END_LABELS[0], "por chat (MCP): la plantilla toma el tipo, los pernos y la altura del piso")
        check(C.revisar_geometria(s)["errores"] == 0, "por chat (MCP): sin errores de geometría")


if __name__ == "__main__":
    ejemplos()
    modelo()
    nudo()
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)
