# -*- coding: utf-8 -*-
"""Genera ejemplos/SIS-01_portico_SMF_placa_base.scp: el nudo CN-04 (columna W14X90 sobre placa base con dos vigas y una diagonal)
con casos de servicio D, L y QEx y las combinaciones de ASCE 7-05 generadas (SMF, SDC D).  Uso:  python tools/ejemplo_sismo.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steelconpro.model import load_book, save_book          # noqa: E402
from steelconpro.conn.specs import Load                     # noqa: E402
from steelconpro import seismic as SE                       # noqa: E402


def build():
    p = load_book(str(ROOT / "ejemplos" / "CN-04_columna_con_placa_base.scp"))[0]
    p.element, p.name = "SIS-01", "Ejemplo sismico: columna de portico especial (SMF) sobre placa base"
    nd = p.node
    for l in nd.loads:
        l.case = "D"
    nd.loads += [Load("L", "V1", Vz=-8.0), Load("L", "V2", Vz=-8.0),
                 Load("QEx", "D1", N=20.0), Load("QEx", "V1", My=400.0)]
    nd.case_kind = {"D": "D", "L": "L", "QEx": "QEx"}
    S = p.seis
    S.enabled, S.sdc, S.SDS, S.rho, S.f1 = True, "D", 1.0, 1.0, 0.5
    S.ductile = False                       # con AISC 341 los anclajes se disenan con Ωo (limitado por D2.6); el anclaje ductil es opcional
    p.bolts.steel = "ASTM F1554 Gr.55"
    p.conc.N2 = p.conc.B2 = 48.0
    p.conc.ha = 60.0
    p.conc.u_on, p.conc.u_size, p.conc.u_n, p.conc.u_fy = True, "#6", 4, 60.0     # refuerzo del anclaje (ACI 17.5.2.1), Gr.60 (17.10.4)
    p.plate.tp = 2.5
    SE.generate_node_cases(p)
    return p


if __name__ == "__main__":
    out = ROOT / "ejemplos" / "SIS-01_portico_SMF_placa_base.scp"
    save_book(str(out), [build()])
    print(out)
