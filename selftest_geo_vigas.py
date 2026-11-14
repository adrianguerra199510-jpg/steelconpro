# -*- coding: utf-8 -*-
"""Pruebas de la geometría de las conexiones de viga a soporte (corte y momento): ejemplos TP-V*, barridos de orientaciones, perfiles y opciones.

    python3 selftest_geo_vigas.py        (código de salida ≠ 0 si algo falla)
"""
import glob
import itertools
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from steelconpro.model import load_book                                            # noqa: E402
from steelconpro.conn import assembly as AS, geocheck as GC                        # noqa: E402
from steelconpro.conn.specs import (Nodo, Member, Operation, TAB_MODES, BEAM_CONNS, OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD,   # noqa: E402
                                    OP_CONT, WELD_TYPES, WELD_SIDES)

FAIL = []


def errores(mdl):
    return [e for e in GC.check(mdl) if e["sev"] == "error"]


def centrar(nd, m, cara):
    A, msx, msy = AS.main_frame(nd)
    ms = AS.shape_of(nd.main_shape)
    d = AS.member_dir(m)
    dx, dy = float(d @ msx), float(d @ msy)
    if cara == "y":
        m.off, m.off2 = 0.0, -((1.0 if dy > 0 else -1.0) * ms.d / 2.0) / dy * dx
    else:
        m.off2, m.off = 0.0, -((1.0 if dx > 0 else -1.0) * (ms.bf / 2.0 if ms.is_hollow else ms.tw / 2.0)) / dx * dy


def caso(kind, main, el, base, cara, beam, delta=0.0, mel=0.0, **okw):
    m = Member(name="V1", shape=beam, az=(base + delta) % 360.0, el=mel)
    nd = Nodo(main_name="P", main_shape=main, main_el=el, members=[m], operations=[Operation(kind=kind, member="V1", **okw)])
    centrar(nd, m, cara)
    return nd


def construir(nd, titulo):
    try:
        return AS.build_nodo(nd)
    except Exception as e:                                                         # noqa: BLE001
        FAIL.append(f"{titulo}: excepción {e!r}")
        return None


# ---------------------------------------------------------------- 1. ejemplos TP-V*
def ejemplos():
    from steelconpro import api
    files = sorted(glob.glob(os.path.join(ROOT, "ejemplos", "TP-V*.scp")))
    if not files:
        FAIL.append("ejemplos TP-V*: no hay archivos (python3 tools/ejemplos_vigas.py)")
    for f in files:
        for p in load_book(f):
            try:
                mdl = AS.build_model(p)
                err = errores(mdl)
                if err:
                    FAIL.append(f"{os.path.basename(f)}: {len(err)} error(es) del revisor, p. ej. {err[0]['text'][:120]}")
                api.verify({"connection": api._dump(p)})
            except Exception as e:                                                 # noqa: BLE001
                FAIL.append(f"{os.path.basename(f)}: excepción {e!r}")
    print(f"{'ejemplos TP-V*':34} {len(files)} archivos: modelo, revisor sin errores y verificaciones: {'OK' if not FAIL else 'FALLA'}")


# ---------------------------------------------------------------- 2. barridos
KINDS = [OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD]
APOYOS = [("W14X90", 90.0, 0, "y"), ("W14X90", 90.0, 180, "y"), ("HSS10X10X1/2", 90.0, 0, "y"), ("HSS10X10X1/2", 90.0, 90, "x"), ("W24X55", 0.0, 90, "x")]
VIGAS = ["W16X31", "W10X22"]


def barrido():
    n = 0
    for tag, deltas, els in (("ortogonal", (0.0,), (0.0,)), ("esviajes", (30.0, -30.0), (0.0,)), ("pendientes", (0.0, 25.0), (10.0, -15.0))):
        bad = []
        for kind, (main, el, base, cara), beam in itertools.product(KINDS, APOYOS, VIGAS):
            if kind == OP_SEAT and main.startswith("HSS") and base == 90:
                pass
            for dl, mel in itertools.product(deltas, els):
                n += 1
                nd = caso(kind, main, el, base, cara, beam, dl, mel)
                mdl = construir(nd, f"{kind}/{main}/{beam}/az {base + dl}/el {mel}")
                if mdl is None:
                    continue
                err = errores(mdl)
                if err:
                    bad.append(f"{kind[:12]} {main} {beam} az {base + dl:g} el {mel:g}: {err[0]['text'][:100]}")
        if bad:
            FAIL.append(f"barrido {tag}: {len(bad)} caso(s) con errores, p. ej. {bad[0]}")
    print(f"{'barridos':34} {n} casos (ortogonal, esviajes ±30°, pendientes): sin excepciones y sin errores del revisor")


# ---------------------------------------------------------------- 3. opciones y casos puntuales
def opciones():
    # placa simple: posición sobre el eje, columnas de pernos, medidas manuales, tipos de soldadura
    for okw in (dict(n_bolts=4, n_cols=2, tab_H=12.0, tab_W=8.0), dict(weld_type=WELD_TYPES[1]), dict(weld_type=WELD_TYPES[2]), dict(weld_side=WELD_SIDES[1]),
                dict(beam_conn=BEAM_CONNS[1]), dict(tab_clip=1.0), dict(tab_y=1.0), dict(plate_t=0.75)):
        mdl = construir(caso(OP_TAB, "W14X90", 90.0, 0, "y", "W16X31", **okw), f"tab {okw}")
        if mdl is not None and errores(mdl):
            FAIL.append(f"placa simple {okw}: {errores(mdl)[0]['text'][:120]}")
    for gap in (-0.25, 0.0, 1.0):
        for kind in (OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_WELD):
            nd = caso(kind, "W14X90", 90.0, 0, "y", "W16X31")
            nd.members[0].gap = gap
            mdl = construir(nd, f"gap {gap} {kind}")
            if mdl is not None and errores(mdl):
                FAIL.append(f"desplazamiento {gap:+g} in en «{kind}»: {errores(mdl)[0]['text'][:120]}")
    # hasta las alas: columna (alas a los lados de la viga) frente a viga maestra (alas arriba y abajo)
    for main, el, base, cara, esp in (("W14X90", 90.0, 90, "x", "columna"), ("W24X55", 0.0, 90, "x", "viga maestra")):
        for split in (False, True):
            nd = caso(OP_TAB, main, el, base, cara, "W16X31", tab_mode=TAB_MODES[1], tab_split=split)
            mdl = construir(nd, f"hasta las alas {esp} split={split}")
            if mdl is None:
                continue
            if errores(mdl):
                FAIL.append(f"hasta las alas ({esp}, split={split}): {errores(mdl)[0]['text'][:120]}")
            nplates = len([p for p in mdl.parts if p.name.startswith("Placa V1-")])
            if split and esp == "columna" and nplates != 2:
                FAIL.append("dos placas arriba y abajo en columna: deben ser 2 placas horizontales")
            if split and esp == "viga maestra" and (nplates != 0 or not any("dos placas" in x.lower() for x in mdl.notes)):
                FAIL.append("dos placas en viga maestra horizontal: no se arman y se avisa")
            if not split and esp == "columna":                                      # placa plana: soldada solo al alma, sin filetes a las alas
                if any("-F" in w.name for w in mdl.welds):
                    FAIL.append("hasta las alas en columna: la placa no toca las alas, no lleva filetes a ellas")
                pl = mdl.part("Placa V1")
                z = np.vstack([q.corners() for q in pl.prisms])[:, 2]
                if z.max() - z.min() > 10.0:
                    FAIL.append(f"hasta las alas en columna: la placa debe medir el alto de los pernos, no el espacio entre alas ({z.max() - z.min():.1f})")
            if not split and esp == "viga maestra":
                pl = mdl.part("Placa V1")
                z = np.vstack([q.corners() for q in pl.prisms])[:, 2]
                wm = AS.shape_of(main)
                if abs((z.max() - z.min()) - (wm.d - 2 * wm.tf)) > 0.05 or sum(1 for w in mdl.welds if "-F" in w.name) != 4:
                    FAIL.append(f"hasta las alas en viga maestra: la placa llena el espacio entre alas y lleva 4 filetes ({z.max() - z.min():.2f})")
    # esviaje: la placa queda sobre la cara (ningún punto penetra) y la viga se retrasa
    mdl = construir(caso(OP_TAB, "W14X90", 90.0, 0, "y", "W16X31", 30.0), "esviaje 30")
    if mdl is not None:
        xmin = min(float(pr.corners()[:, 0].min()) for pr in mdl.part("V1").prisms)
        if xmin < 7.0 + 0.4:
            FAIL.append(f"esviaje 30°: la viga debe librar la cara de la columna (x = 7): empieza en {xmin:.2f}")
    mdl = construir(caso(OP_EP_FLUSH, "W14X90", 90.0, 0, "y", "W16X31", 30.0), "placa extrema esviada")
    if mdl is not None and (not mdl.bolts or any(p.name.startswith("Placa extrema") and not p.prisms for p in mdl.parts)):
        FAIL.append("placa extrema esviada: faltan pernos")
    # soporte angosto: el ángulo se acorta y se avisa, sin excepción ni choque
    mdl = construir(caso(OP_DANG, "W12X40", 90.0, 0, "y", "HSS6X6X3/8"), "doble angulo en cara angosta")
    if mdl is not None and (not any("más ancha" in x or "angosta" in x for x in mdl.notes) or errores(mdl)):
        FAIL.append("doble ángulo en una cara angosta: debe avisar y no dar errores")
    # llegada casi paralela a la cara o sin tocar el principal: nunca excepción
    for az in (88.0, 90.0, 0.0):
        nd = caso(OP_TAB, "W14X90", 90.0, 0, "y", "W16X31")
        nd.members[0].az = az
        construir(nd, f"az {az} sin centrar")
    print(f"{'opciones y casos puntuales':34} tipos de soldadura, gap, hasta las alas (columna / viga maestra), esviaje, cara angosta: {'OK' if not FAIL else 'FALLA'}")


if __name__ == "__main__":
    ejemplos()
    opciones()
    barrido()
    if FAIL:
        print("\nFALLAS (%d):" % len(FAIL))
        for f in FAIL:
            print("  -", f)
        sys.exit(1)
    print("\nTODAS LAS PRUEBAS DE GEOMETRIA DE VIGAS PASARON")
