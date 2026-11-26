# -*- coding: utf-8 -*-
"""Reporte (PDF y Word) de una conexión de nudo: secciones de los perfiles, isométricos frontal y posterior, modo alámbrico con cargas, reacción y resultante,
malla del modelo de placas, von Mises con la malla, deformada con la malla y tablas de resultados (placas y miembros, pernos, cordones).

    python3 selftest_reporte.py            (con el análisis de placas de CalculiX)
    python3 selftest_reporte.py --rapido   (sin CalculiX: comprueba las figuras del modelo y las tablas con un resultado sintético)
"""
import glob
import os
import sys
import tempfile
import time
from dataclasses import asdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
RAPIDO = "--rapido" in sys.argv

import numpy as np                                                              # noqa: E402
from PIL import Image                                                           # noqa: E402
from steelconpro import api                                                     # noqa: E402
from steelconpro.model import load_book                                         # noqa: E402
from steelconpro.conn import report_figs as RF                                  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def texto(pdf):
    import pypdf
    r = pypdf.PdfReader(pdf)
    return len(r.pages), "\n".join(p.extract_text() for p in r.pages)


def imagenes(td):
    print("== Figuras del modelo (sin análisis) ==")
    p = load_book(glob.glob(os.path.join(ROOT, "ejemplos", "CN-02_*.scp"))[0])[0]
    sec = RF.sections_figure(p, td)
    im = Image.open(sec)
    check(im.size[0] > 800 and np.asarray(im.convert("L")).min() < 100, f"imagen de las secciones de los 4 perfiles ({im.size[0]}×{im.size[1]})")
    rows = RF.section_rows(p, p.units())
    check([r[0] for r in rows] == ["W24X55", "W18X35", "W16X31", "W14X22"] and all(r[1] > 0 for r in rows), f"propiedades de las secciones: {[r[0] for r in rows]}")
    mv = RF.model_views(p, td)
    check([t for t, _f in mv] == ["Isométrico frontal", "Isométrico posterior"], "isométrico frontal y posterior")
    a, b = (np.asarray(Image.open(f).convert("L"), float) for _t, f in mv)
    check(np.abs(a - b).mean() > 3.0, f"las dos vistas son distintas (diferencia media {np.abs(a - b).mean():.1f})")
    wv = RF.wire_views(p, td)
    check(len(wv) == 1 and "alámbrico" in wv[0][0], f"isométrico alámbrico del caso de carga: {wv[0][0]}")
    arr = np.asarray(Image.open(wv[0][1]).convert("RGB"), int)
    red = ((arr[..., 0] > 150) & (arr[..., 1] < 60) & (arr[..., 2] < 60)).sum()
    green = ((arr[..., 1] > 90) & (arr[..., 0] < 40) & (arr[..., 2] < 80)).sum()
    check(red > 500 and green > 150, f"el alámbrico dibuja las cargas (rojo, {red} px) y la reacción (verde, {green} px)")
    return p


def tablas_sinteticas(p):
    """Tablas de resultados con un ShellResult armado a mano (sin CalculiX)."""
    print("\n== Tablas de resultados (resultado sintético) ==")
    from steelconpro.conn.fem import shellpost as SP
    R = SP.ShellResult(ok=True, case="Caso 1")
    R.xyz = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0.0]])
    R.U = np.array([[0, 0, 0], [0.1, 0, 0.2], [0.1, 0, 0.4], [0, 0, 0.1]])
    R.elems = [(1, [0, 1, 2, 3], 0)]
    R.plate_part, R.plate_kind, R.plate_t = ["P1"], ["plate"], [0.5]
    R.e_vm = np.array([30.0])
    R.e_peeq = np.array([0.0])
    R.parts = {"P1": {"kind": "plate", "Fy": 36.0, "vm": 30.0, "vm_peak": 33.0, "peeq": 0.0, "t": 0.5, "n_el": 1}, "V1": {"kind": "beam", "Fy": 50.0, "vm": 20.0, "vm_peak": 21.0, "peeq": 0.001, "t": 0.4, "n_el": 3}}
    R.member_names = {"V1"}
    R.bolts = [{"tag": "S1-B1", "pos": [0, 0, 0], "db": 0.75, "dh": 0.8, "grade": "A325-N", "anchor": False, "parts": ["P1", "V1"], "planes": [], "V": 10.0, "T": 5.0, "axis": [1, 0, 0], "group": "S1"},
               {"tag": "S1-B2", "pos": [0, 0, 0], "db": 0.75, "dh": 0.8, "grade": "A325-N", "anchor": False, "parts": ["P1", "V1"], "planes": [], "V": 12.0, "T": 0.0, "axis": [1, 0, 0], "group": "S1"}]
    R.welds = [{"name": "W1", "A": "P1", "B": "V1", "group": "g", "q": 0.5, "cap": 1.2, "w": 0.25, "L": 8.0, "sides": 1, "from": "P1", "p0": [0, 0, 0], "p1": [1, 0, 0]}]
    R.umax, R.vmmax, R.peeqmax, R.n_nodes, R.n_elems = 0.4, 30.0, 0.001, 4, 1
    t = RF.fem_tables(p, [("Caso 1", R, None)])[0]
    check([r[0] for r in t["parts"][1]] == ["V1", "P1"] and t["parts"][1][0][1] == "Miembro", f"piezas: primero los miembros y después las placas ({[r[0] for r in t['parts'][1]]})")
    check(t["parts"][1][1][8] != "-" and float(t["parts"][1][1][8].replace(",", "")) > 5.0, f"desplazamiento máximo de la placa P1 en mm ({t['parts'][1][1][8]})")
    check(t["bolt_groups"][1][0][2] == "2" and t["bolts"][1][0][0] == "S1-B2", "pernos: un grupo de 2 y el más exigido (V = 12 kip) primero")
    check(len(t["welds"][1]) == 1 and float(t["welds"][1][0][6]) < 1.0, "cordones: una unión con su D/C")
    return R


def reporte(p, td):
    print("\n== Reporte PDF y Word ==")
    c = asdict(p)
    pdf = os.path.join(td, "r.pdf")
    t0 = time.time()
    api.report({"connection": c, "format": "pdf", "path": pdf, "detail": True})
    n, txt = texto(pdf)
    check(n >= 6 and os.path.getsize(pdf) > 100000, f"PDF de {n} páginas ({os.path.getsize(pdf) // 1024} kB, {time.time() - t0:.0f} s)")
    for s in ("Secciones de los perfiles", "Isométrico frontal", "Isométrico posterior", "Modo alámbrico", "Verificaciones", "Anexo A"):
        check(s in txt, f"el PDF incluye «{s}»")
    check("φ" in txt or "Cálculo" in txt, "tipografía con acentos y letras griegas")
    docx = os.path.join(td, "r.docx")
    api.report({"connection": c, "format": "docx", "path": docx, "detail": False})
    from docx import Document
    d = Document(docx)
    check(len(d.inline_shapes) >= 4 and any("Secciones" in x.text for x in d.paragraphs), f"Word con {len(d.inline_shapes)} figuras")
    return txt


def con_fem(p, td):
    print("\n== Reporte con el análisis de placas (CalculiX) ==")
    c = asdict(p)
    r = api.fem_node_start({"connection": c, "folder": os.path.join(td, "fem")})
    t0 = time.time()
    while True:
        j = api.job_status({"job": r["job"]})
        if j["done"]:
            break
        time.sleep(3)
    check(j["state"] == "done", f"análisis de placas terminado ({time.time() - t0:.0f} s) {j.get('error', '')[:80]}")
    pdf = os.path.join(td, "rf.pdf")
    api.report({"connection": c, "format": "pdf", "path": pdf, "detail": False})
    n, txt = texto(pdf)
    for s in ("Malla del modelo de placas", "von Mises en las caras, con la malla", "Deformada con la malla", "Resumen de resultados", "Placas y miembros", "Pernos", "Cordones de soldadura"):
        check(s in txt, f"el PDF con análisis incluye «{s}»")
    check("no incluye la malla" not in txt.replace("\n", " "), "sin el aviso de falta de análisis")
    import pypdf
    imgs = sum(len(pg.images) for pg in pypdf.PdfReader(pdf).pages)
    check(imgs >= 8, f"{imgs} imágenes en el PDF (secciones, 2 isométricos, alámbrico, malla, von Mises y deformada)")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        p = imagenes(td)
        tablas_sinteticas(p)
        txt = reporte(p, td)
        check("no incluye la malla" in txt.replace("\n", " "), "sin análisis vigente, el reporte lo avisa")
        if not RAPIDO:
            con_fem(p, td)
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)
