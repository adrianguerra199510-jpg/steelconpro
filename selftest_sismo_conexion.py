# -*- coding: utf-8 -*-
"""Pruebas del diseño sísmico de conexiones a momento (pórtico especial): placa extrema extendida con 8 pernos por ala (disposición 8ES) armada
con las herramientas del chat, verificación con las filas dibujadas, combinaciones con sobrerresistencia limitadas por la capacidad de la viga
(1.1·Ry·Fy·Z en flexión y, con Lh en la ficha de la viga, 2·M/Lh + cortante de gravedad).

    python3 selftest_sismo_conexion.py
"""
import os
import sys
import tempfile
from dataclasses import asdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from steelconpro import api, chat as C, model as M, seismic as SE          # noqa: E402
from steelconpro.shapes import CATALOG                                    # noqa: E402

FAILS = []


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def conexion_8es(ws):
    s = C.Session(ws)
    C.nueva_conexion(s, "SMF 8ES", elemento="SMF-01", principal={"perfil": "W14X257"})
    C.agregar_miembro(s, "V1", "W24X76")
    b = CATALOG.get("W24X76")
    d, tf, pf, pb = b.d, b.tf, 1.75, 3.75
    rows = [d / 2 + pf + pb, d / 2 + pf, d / 2 - tf - pf, d / 2 - tf - pf - pb]
    rows += [-r for r in rows]
    hh = rows[0] + 1.875
    C.agregar_operacion(s, "Placa extrema extendida", {"member": "V1", "bolt_size": "1-1/8", "bolt_grade": "A490-N", "plate_t": 1.25, "ep_w": b.bf + 1.0,
                                                       "ep_h": 2 * hh, "ep_g": 5.5, "ep_rows": rows, "ep_ext": hh - d / 2,
                                                       "wf_top": "CJP (penetración completa)", "wf_bot": "CJP (penetración completa)", "weld_size": 0.5})
    for face in ("Ala superior", "Ala inferior"):
        C.agregar_operacion(s, "Placa (refuerzo", {"role": "Rigidizador", "parent": "V1", "face": face, "orient": "Perpendicular, longitudinal", "shape": "Triangular",
                                                    "pl_L": 12.78, "pl_W": 7.38, "pl_s": 6.39, "plate_t": 0.5, "weld_size": 0.3125})
    C.agregar_operacion(s, "Placas de continuidad", {"member": "V1", "cont_t": 0.75})
    return s


def run():
    with tempfile.TemporaryDirectory() as ws:
        s = conexion_8es(ws)
        g = C.revisar_geometria(s)
        check(g["errores"] == 0, f"la conexión 8ES armada por chat no tiene errores de geometría ({g['errores']})")
        C.definir_cargas(s, [{"caso": "D", "miembro": "V1", "Vz": -25.0, "My": -1500.0}, {"caso": "L", "miembro": "V1", "Vz": -12.0, "My": -700.0},
                             {"caso": "QEx", "miembro": "V1", "Vz": -30.0, "My": 4500.0}])
        p = s.p
        p.node.case_kind = {"D": "D", "L": "L", "QEx": "QEx"}
        se = p.seis
        se.enabled, se.system, se.sdc, se.Omega0, se.SDS, se.f1 = True, M.SEIS_SYSTEMS[0], "D", 3.0, 1.0, 0.5
        # ---- verificación con las filas dibujadas (4 por ala)
        v = api.verify({"connection": asdict(p)})
        epm = next(c for c in v["checks"] if "momento resistente" in c["title"])
        check(epm["note"].count("fila") == 4 and "exterior 2" in epm["note"] and "interior 2" in epm["note"],
              f"la placa extrema se verifica con las 4 filas por ala que se dibujan ({epm['note'][:90]}…)")
        sv = next(c for c in v["checks"] if "lado comprimido — cortante" in c["title"])
        check("8 pernos" in sv["note"], f"el cortante lo toman los 8 pernos del lado comprimido ({sv['note']})")
        mb = next(c for c in v["checks"] if "sin palanca" in c["title"])
        cap = mb["capacity"] * (12.0 if "ft" in mb["unit"] else 1.0)
        check(abs(cap - 0.75 * 113.0 * 0.994 * 2 * 92.9) < 0.03 * cap, f"capacidad de los 16 pernos sin palanca = φ·2·Pt·Σh ({cap:.0f} kip·in)")
        # ---- combinaciones con sobrerresistencia limitadas por la capacidad de la viga
        n = SE.generate_node_cases(p)
        cap_M = 1.1 * SE.ry_of("ASTM A992") * 50.0 * CATALOG.get("W24X76").Zx
        om = [l for l in p.node.loads if l.case.startswith("Ω") and l.member == "V1"]
        check(n == 11 and om and max(abs(l.My) for l in om) <= cap_M + 1e-6 and any("lím. capacidad" in l.case for l in om),
              f"Ωo·QE no exige a la viga más de 1.1·Ry·Fy·Zx = {cap_M:.0f} kip·in (máx. {max(abs(l.My) for l in om):.0f})")
        el = [l for l in p.node.loads if l.case.startswith("E") and l.member == "V1"]
        check(el and max(abs(l.My) for l in el) > 6000, "las combinaciones sísmicas sin Ωo no se limitan")
        C.modificar_miembro(s, "V1", {"sism_Lh": 300.0, "sism_Vg": 40.0})
        SE.generate_node_cases(s.p)
        om = [l for l in s.p.node.loads if l.case.startswith("Ω") and l.member == "V1"]
        vcap = 2 * cap_M / 300.0 + 40.0
        check(max(abs(l.Vz) for l in om) <= vcap + 1e-6, f"con Lh en la ficha de la viga, el cortante con Ωo no pasa de 2·M/Lh + Vg = {vcap:.1f} kip")
        d = C.describir_conexion(s)
        check(d["miembros"][0]["punto_de_carga"] == "Automático", "la ficha conserva el punto de aplicación")
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    run()
