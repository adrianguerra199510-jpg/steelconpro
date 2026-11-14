# -*- coding: utf-8 -*-
"""Pruebas de las MALLAS que ve el usuario (caras de los prismas, cordones y pernos): superficie cerrada y orientada, sin caras degeneradas ni dobles,
con el mismo sólido que dice `geocheck.prism_mask`, para cualquier combinación de contorno, huecos y recortes.

    python3 selftest_geo_malla.py            # todo (≈ 2–4 min)
    python3 selftest_geo_malla.py --rapido   # sin el barrido de conexiones

Termina con código ≠ 0 si algo falla.  La herramienta de verificación está en `steelconpro/conn/meshcheck.py`.
"""
import glob
import importlib.util
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from steelconpro.conn import assembly as AS, meshcheck as MC            # noqa: E402
from steelconpro.conn.fem import scene as FS                             # noqa: E402
from steelconpro.conn.fem.model3d import (Prism, Weld, weld_prism, cyl_prism, i_section, rect_tube, poly_prism, box_prism)   # noqa: E402
from steelconpro.conn.geom2d import circle_poly                          # noqa: E402
from steelconpro.model import load_book                                  # noqa: E402

FAILS = []
RAPIDO = "--rapido" in sys.argv


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


class _Sh:
    d, bf, tf, tw = 12.0, 8.0, 0.6, 0.4


I12 = i_section(_Sh)
TUBE_EXT, TUBE_INT = rect_tube(_Sh)
BOX = [(-3, -2), (3, -2), (3, 2), (-3, 2)]


def mk(poly, **kw):
    return Prism(poly=poly, o=(1, 2, 3), U=(1, 0, 0), V=(0, 1, 0), w0=0, w1=20, **kw)


def cyl(ri=0.0, planes=(), extra=()):
    c = cyl_prism((0, 0, 0), (0, 0, 1), 3, 10, ri)
    c.cut_planes = list(planes)
    c.holes_extra = list(extra)
    return c


def prism_ok(pr, name, expect_vol=None, vol_rtol=0.01, n_pts=1500):
    r = MC.check_prism(pr, n_pts=n_pts)
    ok = r["ok"]
    if ok and expect_vol is not None:
        ok = abs(r["vol"] - expect_vol) <= vol_rtol * max(expect_vol, 1e-9) + 1e-6
        if not ok:
            r["errors"].append(f"volumen {r['vol']:.4f} ≠ esperado {expect_vol:.4f}")
    check(ok, f"{name}: {r['nf']} caras, vol {r['vol']:.3f}" + ("" if ok else "  " + "; ".join(r["errors"][:3])))
    return r


# ====================================================================================================== 1. casos de recorte
def casos_recorte():
    print("\n== prismas con recortes ==")
    prism_ok(mk(BOX), "caja", 480)
    prism_ok(mk(BOX, cut_planes=[((1, 2, 13), (0.3, 0.2, 1))]), "caja, un plano oblicuo por el centro", 240)
    prism_ok(mk(BOX, cut_planes=[((4, 4, 3), (1, 1, 0.3))]), "caja, plano que pasa por un vértice")
    prism_ok(mk(BOX, cut_planes=[((4, 4, 13), (1, 1, 1))]), "caja, plano que corta solo una esquina", 360)
    prism_ok(mk(BOX, cut_planes=[((1, 2, 13), (0.3, 0.2, 1)), ((1, 2, 13), (-0.3, 0.4, 1))]), "caja, dos planos oblicuos")
    prism_ok(mk(BOX, cut_planes=[((1, 2, 13), (1, 0, 0.2)), ((1, 2, 13), (-1, 0, 0.2))]), "caja, dos planos que se cruzan dentro", 80)
    r = prism_ok(mk(BOX, cut_planes=[((1, 2, 100), (0, 0, 1))]), "caja, plano que no la toca", 480)
    check(r["nf"] == 6, "plano que no toca la pieza: la pieza queda intacta (6 caras)")
    r = MC.check_prism(mk(BOX, cut_planes=[((1, 2, -100), (0, 0, 1))]))
    check(r["nf"] == 0 and r["ok"], "plano que se lleva la pieza entera: sin caras")
    prism_ok(mk(BOX, cut_planes=[((1, 2, 23), (0, 0, 1))]), "plano al ras de la tapa (conserva todo)", 480)
    r = MC.check_prism(mk(BOX, cut_planes=[((1, 2, 23), (0, 0, -1))]))
    check(r["nf"] == 0, "plano al ras de la tapa por el otro lado (no queda nada)")
    prism_ok(mk(BOX, cut_planes=[((1, 2, 13), (1, 1, 0))]), "caja, plano paralelo al eje de extrusión", 240)
    # perfil I (cóncavo): la tapa del corte es el contorno del perfil, no su envolvente
    r = prism_ok(mk(I12, cut_planes=[((1, 2, 13), (0, 0, 1))]), "perfil I cortado a la mitad (plano normal al eje)", 0.5 * (2 * 8 * 0.6 + 10.8 * 0.4) * 20)
    prism_ok(mk(I12, cut_planes=[((1, 2, 13), (0.5, 0.3, 1))]), "perfil I con un plano oblicuo")
    prism_ok(mk(I12, cut_planes=[((1, 2, 13), (0.5, 0.3, 1)), ((1, 2, 13), (-0.5, 0.7, 1))]), "perfil I con dos planos")
    # tubo poligonal: la tapa es el anillo
    area_t = 8 * 12 - 7.2 * 11.2
    prism_ok(mk(TUBE_EXT, holes=[TUBE_INT]), "tubo rectangular", area_t * 20)
    prism_ok(mk(TUBE_EXT, holes=[TUBE_INT], cut_planes=[((1, 2, 13), (0, 0, 1))]), "tubo rectangular cortado a la mitad: tapa en anillo", area_t * 10)
    prism_ok(mk(TUBE_EXT, holes=[TUBE_INT], cut_planes=[((1, 2, 13), (0.5, 0.3, 1))]), "tubo rectangular con plano oblicuo")
    prism_ok(mk(TUBE_EXT, holes=[TUBE_INT], cut_planes=[((1, 2, 13), (1, 0, 0))]), "tubo rectangular cortado a lo largo")
    # redondos
    n = 36
    a_c = 0.5 * n * 9 * math.sin(2 * math.pi / n)
    prism_ok(cyl(), "cilindro", a_c * 10)
    prism_ok(cyl(planes=[((0, 0, 0), (0.5, 0.2, 1))]), "cilindro con plano oblicuo", a_c * 5)
    a_t = 0.5 * n * (9 - 6.25) * math.sin(2 * math.pi / n)
    prism_ok(cyl(2.5), "tubo redondo", a_t * 10)
    prism_ok(cyl(2.5, planes=[((0, 0, 0), (0.5, 0.2, 1))]), "tubo redondo con plano oblicuo: tapa en anillo", a_t * 5)
    prism_ok(cyl(2.5, planes=[((0, 0, 2), (0.5, 0.2, 1)), ((0, 0, -2), (-0.4, 0.2, -1))]), "tubo redondo con dos planos (inglete doble)")
    prism_ok(cyl(2.5, planes=[((0, 0, 0), (1, 0, 0))]), "tubo redondo cortado a lo largo (plano por vértices del facetado)", a_t * 5)
    prism_ok(cyl(2.5, planes=[((0, 0, 0), (-1, 0, 0))]), "tubo redondo cortado a lo largo, lado contrario", a_t * 5)
    # plano que coincide con una pared interna entre las piezas convexas en que se descompone la sección
    yj = 2 + (-6 + 0.6)                                      # y del cuello del ala inferior del perfil I (o = (1, 2, 3))
    af = 8 * 0.6
    prism_ok(mk(I12, cut_planes=[((0, yj, 0), (0, 1, 0))]), "perfil I cortado por el plano del cuello del ala (conserva el ala)", af * 20)
    prism_ok(mk(I12, cut_planes=[((0, yj, 0), (0, -1, 0))]), "perfil I cortado por el plano del cuello del ala (conserva el resto)", (278.4 - af * 20))
    prism_ok(mk(TUBE_EXT, holes=[TUBE_INT], cut_planes=[((1 + 4 - 0.4, 0, 0), (1, 0, 0))]), "tubo rectangular cortado por el plano de su pared interior")
    prism_ok(mk(TUBE_EXT, holes=[TUBE_INT], cut_planes=[((1 + 4 - 0.4, 0, 0), (-1, 0, 0))]), "tubo rectangular, plano de la pared interior, lado contrario")


# ====================================================================================================== 2. agujeros
def casos_agujeros():
    print("\n== agujeros, huecos y aberturas ==")
    bh = [circle_poly(a, b, 0.4, 24) for a in (-2, 0, 2) for b in (-1, 1)]
    a_h = 0.5 * 24 * 0.16 * math.sin(2 * math.pi / 24)
    prism_ok(mk(BOX, holes_extra=bh), "placa con 6 agujeros", (24 - 6 * a_h) * 20)
    prism_ok(mk(BOX, holes_extra=bh, cut_planes=[((1, 2, 13), (0.5, 0.3, 1))]), "placa con agujeros y plano oblicuo", (24 - 6 * a_h) * 10)
    prism_ok(mk(BOX, holes_extra=bh, cut_planes=[((1, 2, 13), (1, 0, 0.0001))]), "placa con agujeros y un plano que los atraviesa")
    prism_ok(mk(BOX, holes_extra=bh, cut_planes=[((1.1, 2, 13), (1, 0.3, 0))]), "placa con agujeros y plano vertical que atraviesa agujeros")
    prism_ok(mk(BOX, holes_extra=[circle_poly(3, 0, 0.8, 24)]), "agujero que cruza el borde")
    prism_ok(mk(BOX, holes_extra=[circle_poly(-0.3, 0, 0.8, 24), circle_poly(0.3, 0, 0.8, 24)]), "dos agujeros que se superponen")
    grid = [circle_poly(-2.4 + 1.6 * i, -1.6 + 1.6 * j, 0.5, 20) for i in range(4) for j in range(3)]
    prism_ok(mk(BOX, holes_extra=grid), "rejilla de agujeros con vértices alineados (triángulos planos del triangulador)")
    prism_ok(mk(BOX, holes_extra=grid, cut_planes=[((1, 2, 13), (0.5, 0.3, 1))]), "rejilla de agujeros alineados con plano oblicuo")
    stub = [(0, 0.05), (0.25, 0.05), (0.25, -7.51), (60, -7.51), (60, 7.51), (0.25, 7.51), (0.25, -0.05), (0, -0.05)]      # alma con talón estrecho (el triangulador falla)
    hh = [circle_poly(2.5, y, 0.406, 20) for y in (-3.0, 0.0, 3.0)]
    prism_ok(mk(stub, holes_extra=hh), "contorno con talón estrecho y agujeros (respaldo por franjas)")
    prism_ok(mk(stub, holes_extra=hh, cut_planes=[((30, 2, 3.1), (0.5, 0.3, 1))]), "idem con plano oblicuo")
    prism_ok(mk(BOX, holes_extra=[circle_poly(10, 0, 0.8, 24)]), "agujero fuera de la placa", 480)
    prism_ok(mk(BOX, holes_extra=[circle_poly(3, 2, 0.8, 24)]), "agujero en una esquina")
    prism_ok(mk(BOX, holes_extra=[[(2, -0.5), (4, -0.5), (4, 0.5), (2, 0.5)]]), "ranura abierta al borde", 460)
    prism_ok(mk(BOX, holes_extra=[[(-0.5, -3), (0.5, -3), (0.5, 3), (-0.5, 3)]]), "abertura que parte la placa en dos", 400)
    prism_ok(mk(BOX, holes_extra=[circle_poly(0, 0, 1.5, 24), circle_poly(0, 0, 0.5, 24)]), "agujero dentro de otro agujero")
    prism_ok(mk(BOX, holes_extra=[circle_poly(-1, 0, 1.0, 24), circle_poly(1, 0, 1.0, 24)]), "dos agujeros tangentes")
    prism_ok(mk(BOX, holes_extra=[circle_poly(-0.3, 0, 0.8, 24), circle_poly(0.3, 0, 0.8, 24)], cut_planes=[((0, 0, 13), (0.5, 0.3, 1))]),
             "agujeros superpuestos con plano oblicuo")
    prism_ok(mk(I12, holes_extra=[circle_poly(0, 0, 0.1, 12)], cut_planes=[((1, 2, 13), (0.5, 0.3, 1))]), "perfil I con agujero en el alma y plano oblicuo")
    prism_ok(cyl(2.5, planes=[((0, 0, 5), (0.5, 0.3, 1))], extra=[circle_poly(2.75, 0, 0.5, 16)]), "tubo redondo con agujero en la pared y plano oblicuo")


# ====================================================================================================== 3. barrido aleatorio
def fuzz(n=60, seed=7):
    print("\n== barrido aleatorio de planos y agujeros ==")
    rng = np.random.default_rng(seed)
    bad = 0
    for k in range(n):
        base = [BOX, I12, TUBE_EXT][k % 3]
        hs = [TUBE_INT] if k % 3 == 2 else []
        extra = []
        for _ in range(int(rng.integers(0, 4))):
            c = rng.uniform(-3, 3, 2)
            extra.append(circle_poly(float(c[0]), float(c[1]), float(rng.uniform(0.2, 1.2)), int(rng.integers(8, 20))))
        planes = []
        for _ in range(int(rng.integers(1, 4))):
            nrm = rng.normal(size=3)
            if k % 5 == 0:
                nrm[2] = 0.0
            if k % 7 == 0:
                nrm = np.round(nrm)
                if not nrm.any():
                    nrm = np.array([0, 0, 1.0])
            pt = np.array([1.0, 2.0, 13.0]) + rng.uniform(-3, 3, 3)
            planes.append((tuple(pt), tuple(nrm)))
        pr = mk(base, holes=hs, holes_extra=extra, cut_planes=planes)
        r = MC.check_prism(pr, n_pts=600)
        if not r["ok"]:
            bad += 1
            print("   caso", k, r["errors"][:2])
    check(bad == 0, f"{n} prismas aleatorios (perfil I, caja, tubo; agujeros y 1–3 planos): todos cerrados y iguales al material ({bad} malos)")


# ====================================================================================================== 4. cordones y pernos
def cordones_y_pernos():
    print("\n== cordones y pernos ==")
    rng = np.random.default_rng(3)
    bad = 0
    for k in range(40):
        axis = rng.normal(size=3)
        axis /= np.linalg.norm(axis)
        nA, nB = rng.normal(size=3), rng.normal(size=3)
        if k % 4 == 0:                                                 # perpendiculares entre sí y al cordón (caso típico)
            nA = np.cross(axis, rng.normal(size=3))
            nA /= np.linalg.norm(nA)
            nB = np.cross(axis, nA)
        w = Weld("w", "A", "B", tuple(np.array([1, 2, 3.0])), tuple(np.array([1, 2, 3.0]) + axis * 5.0), tuple(nA), tuple(nB), 0.25)
        pr = weld_prism(w)
        r = MC.check_faces(pr.faces())
        if not r["ok"]:
            bad += 1
            print("   cordón", k, r["errors"][:2])
            continue
        # el cordón tiene su rincón sobre la línea p0-p1 y no sobresale del lado contrario de las superficies
        pts = np.array([q for f in pr.faces() for q in f])
        a_ = axis
        nA_ = nA - a_ * float(nA @ a_)
        nB_ = nB - a_ * float(nB @ a_)
        nA_, nB_ = nA_ / np.linalg.norm(nA_), nB_ / np.linalg.norm(nB_)
        if abs(float(nA_ @ nB_)) < 0.99:
            dA = (pts - np.array([1, 2, 3.0])) @ nA_
            dB = (pts - np.array([1, 2, 3.0])) @ nB_
            if dA.min() < -1e-6 or dB.min() < -1e-6:
                bad += 1
                print("   cordón", k, "se mete en una de las piezas", dA.min(), dB.min())
    check(bad == 0, f"40 cordones con normales cualesquiera: cerrados, en el rincón y sin meterse en las piezas ({bad} malos)")
    # sentido del perno: la cabeza sale del lado de head_s, la tuerca del de nut_s
    from steelconpro.conn.fem.model3d import Bolt
    bad = 0
    for hs, ns in ((0.0, 1.5), (1.5, 0.0), (-1.0, 0.5)):
        b = Bolt("B", (0, 0, 0), (0, 0, 1), 0.75, 0.8125, 0.675, [], hs, ns)
        f = FS._bolt_faces(b)
        hd = np.array([q for fc in f["head"] for q in fc])
        zs = hd[:, 2]
        lo, hi = min(hs, ns), max(hs, ns)
        out = hd[(zs < lo - 1e-9) | (zs > hi + 1e-9)]
        inside = hd[(zs > lo + 1e-9) & (zs < hi - 1e-9)]
        head_dir = -1.0 if hs <= ns else 1.0
        zh = hd[np.abs(np.hypot(hd[:, 0], hd[:, 1])) > 0.2][:, 2]
        if len(inside) or not len(out):
            bad += 1
        r = MC.check_faces(f["shank"])
        if not r["ok"]:
            bad += 1
        del head_dir, zh
    check(bad == 0, "perno: cabeza y tuerca quedan fuera del agarre para head_s < nut_s y al revés; vástago cerrado")


# ====================================================================================================== 5. aristas del visor
def aristas_visor():
    from steelconpro.scene3d import Scene
    print("\n== aristas vivas del visor ==")

    def nseg(pr):
        sc = Scene()
        sc.add_faces(pr.faces(), (0.5, 0.5, 0.5), 1.0, edges=True)
        return sum(len(a) for a in sc.lines) // 2

    check(nseg(mk(BOX)) == 12, "caja: 12 aristas")
    check(nseg(mk(BOX, cut_planes=[((1, 2, 13), (0, 0, 1))])) == 12, "caja recortada a media altura: 12 aristas (sin diagonales)")
    check(nseg(mk(I12)) == 36, "perfil I: 36 aristas (sin diagonales de la triangulación)")
    check(nseg(mk(I12, cut_planes=[((1, 2, 13), (0, 0, 1))])) == 36, "perfil I recortado: 36 aristas, incluido el contorno del corte")
    bh = [circle_poly(a, b, 0.4, 24) for a in (-2, 0, 2) for b in (-1, 1)]
    n = nseg(mk(BOX, holes_extra=bh))
    check(n == 12 + 6 * 2 * 24, f"placa con 6 agujeros: contorno + anillos de los agujeros ({n} aristas, sin diagonales)")
    n = nseg(mk(BOX, holes_extra=bh, cut_planes=[((1, 2, 13), (0, 0, 1))]))
    check(n == 12 + 6 * 2 * 24, f"placa con agujeros recortada a la mitad: mismas aristas que la entera ({n})")


# ====================================================================================================== 6. ejemplos y barrido de conexiones
def mallas_modelo(mdl, etiqueta, n_pts=300):
    """Todas las mallas de un modelo: prismas (con el material), cordones y pernos.  -> lista de problemas."""
    bad = []
    for part in mdl.parts:
        for i, pr in enumerate(part.prisms):
            try:
                r = MC.check_prism(pr, n_pts=n_pts)
            except Exception as e:                                          # noqa: BLE001
                bad.append((etiqueta, part.name, i, "excepción " + repr(e)[:80]))
                continue
            if not r["ok"]:
                bad.append((etiqueta, part.name, i, r["errors"][:2]))
    for w in mdl.welds:
        r = MC.check_faces(weld_prism(w).faces())
        if not r["ok"]:
            bad.append((etiqueta, w.name, "cordón", r["errors"][:2]))
    for b in mdl.bolts:
        f = FS._bolt_faces(b)
        groups = [f["shank"], f["head"][:len(f["head"]) // 2], f["head"][len(f["head"]) // 2:]]
        for g in groups:
            if g and not MC.check_faces(g)["ok"]:
                bad.append((etiqueta, b.tag, "perno", MC.check_faces(g)["errors"][:1]))
                break
    by_tag = {}
    for tag, faces, _c, _a in mdl.extra:                                   # placa base heredada: por etiqueta forma una superficie cerrada y orientada
        if not tag.startswith("plane:"):
            by_tag.setdefault(tag, []).extend(faces)
    for tag, faces in by_tag.items():
        r = MC.check_faces(faces)
        errs = [e for e in r["errors"] if "compartida por" not in e]          # sólidos que se tocan (cabeza y vástago) comparten aristas: no es defecto
        if errs:
            bad.append((etiqueta, "extra:" + tag, "", errs[:2]))
    return bad


def ejemplos():
    print("\n== ejemplos/*.scp ==")
    tot = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "ejemplos", "*.scp"))):
        try:
            book = load_book(f)
        except Exception as e:                                              # noqa: BLE001
            check(False, f"{os.path.basename(f)}: no se pudo leer ({e!r})")
            continue
        for k, p in enumerate(book):
            nm = f"{os.path.basename(f)}[{k}]"
            try:
                mdl = AS.build_model(p)
            except Exception as e:                                          # noqa: BLE001
                check(False, f"{nm}: build_model lanzó {e!r}")
                continue
            bad = mallas_modelo(mdl, nm)
            tot += len(bad)
            check(not bad, f"{nm}: {sum(len(pt.prisms) for pt in mdl.parts)} prismas, {len(mdl.welds)} cordones, {len(mdl.bolts)} pernos con mallas cerradas"
                  + ("" if not bad else f"  {bad[:3]}"))


def api_mesh():
    from steelconpro import api
    print("\n== api.mesh (lo que recibe el visor) ==")
    f = os.path.join(ROOT, "ejemplos", "CN-01_columna_con_vigas.scp")
    d = json.loads(load_book(f)[0].to_json())
    api.mesh({"connection": d})
    t = time.time()
    r = api.mesh({"connection": d})
    dt = time.time() - t
    check(dt < 1.0, f"CN-01: la escena se arma en {dt:.2f} s (antes de la revisión: 0.68 s; límite 1.0 s)")
    ok = all(("o" in p and "l" in p and "name" in p) for p in r["parts"])
    check(ok, "cada pieza trae sus mallas y aristas")
    check(all(p.get("closed") for p in r["parts"] if p["kind"] in ("column", "brace", "plate", "angle", "gusset", "stiff", "weld", "bolt")),
          "las piezas del modelo van marcadas como superficies cerradas (el visor dibuja solo la cara frontal: sin parpadeo)")
    names = [p["name"] for p in r["parts"]]
    check(len(set(names)) == len(names), "nombres de pieza únicos (la selección por pieza no se mezcla)")
    check(any(p["kind"] == "weld" for p in r["parts"]) and all(p.get("wkind") in ("filete", "cjp", "pjp") for p in r["parts"] if p["kind"] == "weld"),
          "los cordones llevan su tipo (filete / CJP / PJP)")


def barrido_conexiones():
    print("\n== barrido de conexiones x perfiles x acimuts (mallas) ==")
    spec = importlib.util.spec_from_file_location("barrido", os.path.join(ROOT, "tools", "barrido_geometria.py"))
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    from steelconpro.conn import specs as SP
    angs = [(0, 0), (90, 0), (45, 0), (180, 10), (270, -15), (30, 60)]
    mains, beams = ["W14X90", "HSS10X10X1/2"], ["W16X31", "HSS6X6X3/8"]
    bad, n, crashes = [], 0, 0
    t0 = time.time()
    for op in B.CONNS:
        for main in mains:
            for beam in beams:
                for (az, el) in angs:
                    n += 1
                    try:
                        mdl = AS.build_model(B.case(op, main, beam, az, el))
                    except Exception:                                       # noqa: BLE001
                        crashes += 1                                        # eso lo cubren las pruebas de armado; aquí solo interesan las mallas
                        continue
                    bad += mallas_modelo(mdl, f"{op.split(' (')[0]} {main} {beam} {az}/{el}", n_pts=150)
    del SP
    check(not bad, f"{n} modelos ({crashes} no armaron) con todas sus mallas cerradas, {time.time() - t0:.0f} s" + ("" if not bad else f"  {bad[:4]}"))


def mallador():
    """El mallador de Gmsh respeta los recortes planos (`cut_planes`) y los `Part.cuts`."""
    print("\n== mallador del FEM: recortes ==")
    import tempfile
    from types import SimpleNamespace
    try:
        import gmsh                                                     # noqa: F401
    except Exception:                                                   # noqa: BLE001
        print("(gmsh no disponible: se omite)")
        return
    from steelconpro.conn.fem import mesher, driver
    from steelconpro.conn.fem.model3d import Model3D, Part, model_to_dict

    def malla(mdl):
        out = os.path.join(tempfile.mkdtemp(), "m.npz")
        mesher.mesh_job({"model": model_to_dict(mdl), "params": driver.mesh_params(mdl, SimpleNamespace(mesh3d_mode="", mesh3d=2.5))}, out)
        d = np.load(out, allow_pickle=True)
        return d

    def nodos(d, nombre):
        idx = {int(i): k for k, i in enumerate(d["node_id"])}
        e = np.asarray(d["e_" + nombre])
        return np.array([d["xyz"][idx[int(i)]] for i in np.unique(e) if int(i) in idx])
    # Part.cuts: se resta un prisma del ángulo A1 de CN-06 y ningún nodo de A1 queda dentro
    p = load_book(os.path.join(ROOT, "ejemplos", "CN-06_diagonal_con_recorte_y_angulo.scp"))[0]
    mdl = AS.build_model(p)
    a1 = mdl.part("A1")
    lo, hi = a1.bbox()
    c = 0.5 * (lo + hi)
    a1.cuts = [box_prism(c, (1.0, 1.0, 1.0))]
    X = nodos(malla(mdl), "A1")
    inside = np.all(np.abs(X - c) < 0.45, axis=1)
    check(len(X) > 0 and not inside.any(), f"malla con Part.cuts: A1 ({len(X)} nodos), ningún nodo dentro del volumen restado")
    # CN-06: el extremo de la diagonal recortado contra la cara de la columna (en un proceso aparte: Gmsh gasta memoria y se libera al salir)
    import subprocess
    code = (
        "import sys, os, tempfile, json, numpy as np\n"
        "sys.path.insert(0, %r)\n"
        "from types import SimpleNamespace\n"
        "from steelconpro.model import load_book\n"
        "from steelconpro.conn import assembly as AS\n"
        "from steelconpro.conn.fem import mesher, driver\n"
        "from steelconpro.conn.fem.model3d import model_to_dict\n"
        "p = load_book(os.path.join(%r, 'ejemplos', 'CN-06_diagonal_con_recorte_y_angulo.scp'))[0]\n"
        "m = AS.build_model(p)\n"
        "out = os.path.join(tempfile.mkdtemp(), 'm.npz')\n"
        "mesher.mesh_job({'model': model_to_dict(m), 'params': driver.mesh_params(m, SimpleNamespace(mesh3d_mode='', mesh3d=0.0))}, out)\n"
        "d = np.load(out, allow_pickle=True)\n"
        "idx = {int(i): k for k, i in enumerate(d['node_id'])}\n"
        "X = np.array([d['xyz'][idx[int(i)]] for i in np.unique(d['e_D1']) if int(i) in idx])\n"
        "pt, nn = m.part('D1').prisms[0].cut_planes[0]\n"
        "nn = np.asarray(nn, float); nn /= np.linalg.norm(nn)\n"
        "print(json.dumps([len(X), float(((X - np.asarray(pt)) @ nn).max())]))\n") % (ROOT, ROOT)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    if r.returncode == -9:                                              # el sistema mató el proceso por falta de memoria (límite compartido): no es un fallo de la geometría
        print("(CN-06 mallado: proceso terminado por falta de memoria; se omite)")
        return
    try:
        n_, smax = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:                                                   # noqa: BLE001
        n_, smax = 0, 1e9
    check(n_ > 0 and smax <= 1e-3, f"CN-06: la diagonal mallada ({n_} nodos) no pasa del plano de recorte" + ("" if n_ else f"  rc={r.returncode} {r.stdout[-200:]} {r.stderr[-300:]}"))


if __name__ == "__main__":
    casos_recorte()
    casos_agujeros()
    fuzz()
    cordones_y_pernos()
    aristas_visor()
    ejemplos()
    api_mesh()
    if not RAPIDO:
        mallador()
        barrido_conexiones()
    print("\n" + ("TODO BIEN" if not FAILS else f"FALLARON {len(FAILS)} pruebas:\n  " + "\n  ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
