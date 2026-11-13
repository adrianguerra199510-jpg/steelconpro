# -*- coding: utf-8 -*-
"""Barrido de geometría: un miembro con cada tipo de conexión, en distintas orientaciones y perfiles, y el revisor sobre cada modelo.
Uso: python3 tools/barrido_geometria.py [--detalle]      Devuelve código ≠ 0 si algún caso lanza una excepción o da errores de geometría."""
import copy
import itertools
import os
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from steelconpro.model import load_book                         # noqa: E402
from steelconpro.conn import assembly as AS, geocheck as GC, specs as SP   # noqa: E402

BASE = load_book(os.path.join(ROOT, "ejemplos", "CN-01_columna_con_vigas.scp"))[0]
CONNS = [SP.OP_TAB, SP.OP_DANG, SP.OP_SEAT, SP.OP_EP_FLUSH, SP.OP_EP_EXT, SP.OP_WELD, SP.OP_GUSSET, SP.OP_GUSSET_W]
MAINS = ["W14X90", "W12X40", "HSS10X10X1/2"]
BEAMS = ["W16X31", "W10X22", "HSS6X6X3/8"]
ANGLES = [(0, 0), (90, 0), (180, 0), (270, 0)] if os.environ.get("SOLO_ORTOGONAL", "1") == "1" else [(0, 0), (90, 0), (45, 0), (180, 10), (270, -15), (0, 35), (90, -45), (30, 60)]


def case(op_kind, main, beam, az, el, **kw):
    p = copy.deepcopy(BASE)
    nd = p.node
    nd.main_shape = main
    nd.main_steel = "ASTM A992" if main.startswith("W") else "ASTM A500 Gr.C (HSS rect.)"
    nd.operations = []
    nd.loads = []
    m = copy.deepcopy(nd.members[0])
    m.name, m.shape, m.az, m.el, m.pos, m.L, m.gap, m.off, m.off2 = "M", beam, float(az), float(el), 0.0, 60.0, 0.0, 0.0, 0.0
    m.steel = "ASTM A992" if beam.startswith("W") else "ASTM A500 Gr.C (HSS rect.)"
    nd.members = [m]
    o = SP.Operation(kind=op_kind, member="M")
    for k, v in kw.items():
        setattr(o, k, v)
    nd.operations = [o]
    return p


def run(detalle=False):
    bad, crashes, total = defaultdict(Counter), [], 0
    samples = {}
    t0 = time.time()
    for op, main, beam, (az, el) in itertools.product(CONNS, MAINS, BEAMS, ANGLES):
        if op in (SP.OP_GUSSET, SP.OP_GUSSET_W) and abs(el) < 10 and beam.startswith("W"):
            pass
        total += 1
        key = f"{op.split(' (')[0]}"
        try:
            p = case(op, main, beam, az, el)
            mdl = AS.build_model(p)
            iss = GC.check(mdl)
        except Exception as e:                                   # noqa: BLE001
            crashes.append((key, main, beam, az, el, repr(e)[:120]))
            continue
        for e in iss:
            if e["sev"] == "error":
                bad[key][e["code"]] += 1
                samples.setdefault((key, e["code"]), (main, beam, az, el, e["text"]))
    print(f"{total} casos en {time.time() - t0:.0f} s; excepciones: {len(crashes)}")
    for c in crashes[:15]:
        print("  EXCEPCIÓN", c)
    for key in sorted(bad):
        print(f"  {key:45} " + ", ".join(f"{c}: {n}" for c, n in bad[key].most_common()))
        if detalle:
            for (k2, code), s in samples.items():
                if k2 == key:
                    print(f"      {code}: {s[0]} / {s[1]} az {s[2]} el {s[3]} -> {s[4][:140]}")
    return crashes, bad


if __name__ == "__main__":
    cr, bad = run("--detalle" in sys.argv)
    sys.exit(1 if cr or bad else 0)
