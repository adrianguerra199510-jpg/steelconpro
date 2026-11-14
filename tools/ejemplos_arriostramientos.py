# -*- coding: utf-8 -*-
"""Biblioteca de ejemplos de arriostramientos (diagonales con cartela) y nudos de armadura: `ejemplos/TP-A*.scp`.

    python3 tools/ejemplos_arriostramientos.py          # escribe los archivos
    python3 tools/ejemplos_arriostramientos.py --revisa  # ademas arma cada ejemplo, pasa el revisor de geometria y corre `api.verify`

Cada funcion `ex_*` devuelve un `Project` (nudo) con su titulo («Ejemplo: …»), su clave `TP-Axx` y cargas para el analisis nodal.  `EJEMPLOS` es la lista
(archivo, funcion, resumen) que usan la escritura, el indice y las pruebas (`selftest_geo_cartelas.py`).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steelconpro.model import Project, save_book, load_book                                     # noqa: E402
from steelconpro.conn.specs import (CT_NODE, OP_BASE, OP_GUSSET, OP_GUSSET_W, OP_TAB, OP_EP_FLUSH, END_LABELS, Member, Operation, Load, Nodo)   # noqa: E402
from steelconpro.conn import typologies as TY                                                   # noqa: E402

OUT = ROOT / "ejemplos"
HSS_STEEL = "ASTM A500 Gr.C (HSS rect.)"
I_STEEL = "ASTM A992"


def _steel(label):
    return HSS_STEEL if label.startswith("HSS") else I_STEEL


def _prj(key, title, nd):
    p = Project()
    p.ctype = CT_NODE
    p.element = key
    p.name = "Ejemplo: " + title
    p.node = nd
    return p


def _col(shape="W14X90", neg=96.0, pos=96.0, end=0):
    """Columna vertical principal (end 0 = continua, 1 = termina en el nudo por arriba, 2 = nace en el nudo)."""
    return Nodo(main_name="Columna", main_shape=shape, main_steel=_steel(shape), main_el=90.0, main_end=END_LABELS[end], main_len_neg=neg, main_len_pos=pos)


def _beam(shape="W24X55", half=96.0):
    """Viga horizontal principal (eje X) continua."""
    return Nodo(main_name="Viga principal", main_shape=shape, main_steel=_steel(shape), main_az=0.0, main_el=0.0, main_end=END_LABELS[0],
                main_len_neg=half, main_len_pos=half)


def _chord(shape="HSS10X10X3/8", half=96.0):
    """Cordon horizontal de una armadura."""
    return Nodo(main_name="Cordón", main_shape=shape, main_steel=_steel(shape), main_az=0.0, main_el=0.0, main_end=END_LABELS[0], main_len_neg=half, main_len_pos=half)


def _mem(name, shape, az, el, pos=0.0, L=72.0, **kw):
    return Member(name=name, shape=shape, steel=_steel(shape), az=az, el=el, pos=pos, L=L, **kw)


def _gus(name, bolted=True, t=0.5, **kw):
    return Operation(kind=OP_GUSSET if bolted else OP_GUSSET_W, member=name, plate_t=t, **kw)


def _loads(nd, n=35.0, main=None):
    """Caso 1: las diagonales alternan traccion / compresion; caso 2: al reves.  `main` = (N, lado) de la carga del principal (si no lo equilibra el nudo)."""
    nd.loads = []
    for case, sg in (("Caso 1", 1.0), ("Caso 2", -1.0)):
        for k, m in enumerate(nd.members):
            if any(o.member == m.name and o.is_connection for o in nd.operations):
                nd.loads.append(Load(case, m.name, N=sg * n * (1.0 if k % 2 == 0 else -1.0)))
        if main is not None:
            nd.loads.append(Load(case, nd.main_name, N=main[0], side=main[1]))
    return nd


def _with_base_data(p):
    """Datos de la placa base (placa, anclajes, llave, soldadura, concreto y cargas) tomados del ejemplo PB-01."""
    ref = load_book(str(OUT / "PB-01_W14X90.scp"))[0]
    for k in ("plate", "bolts", "lug", "stiff", "welds", "conc", "loads", "fea", "combos"):
        setattr(p, k, getattr(ref, k))
    p.u_len, p.u_force, p.u_stress, p.u_moment = ref.u_len, ref.u_force, ref.u_stress, ref.u_moment
    p.combo_list()
    p.apply_combo(0)
    return p


# ====================================================================================================== diagonal simple a columna
def ex_a01():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, -45.0)]
    nd.operations = [_gus("D1")]
    return _prj("TP-A01", "diagonal HSS con cartela atornillada al ala de una columna W", _loads(nd))


def ex_a02():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, 45.0)]
    nd.operations = [_gus("D1", bolted=False)]
    return _prj("TP-A02", "diagonal HSS soldada a la cartela (ranura en el tubo) soldada al ala de una columna W", _loads(nd))


def ex_a03():
    nd = _col()
    nd.members = [_mem("D1", "W8X31", 180.0, -40.0)]
    nd.operations = [_gus("D1", t=0.625)]
    return _prj("TP-A03", "diagonal W (alma contra la cartela) con cartela atornillada al ala de una columna W", _loads(nd, 45.0))


def ex_a04():
    nd = _col()
    nd.members = [_mem("D1", "W8X31", 0.0, 50.0)]
    nd.operations = [_gus("D1", bolted=False, t=0.625)]
    return _prj("TP-A04", "diagonal W soldada a la cartela soldada al ala de una columna W", _loads(nd, 45.0))


def ex_a05():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 90.0, -45.0)]
    nd.operations = [_gus("D1")]
    return _prj("TP-A05", "diagonal HSS con cartela atornillada al alma de una columna W (entre las alas)", _loads(nd))


def ex_a06():
    nd = _col("HSS12X12X1/2")
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, -45.0)]
    nd.operations = [_gus("D1")]
    return _prj("TP-A06", "diagonal HSS con cartela atornillada a una columna tubular HSS", _loads(nd))


def ex_a07():
    nd = _col("HSS12X12X1/2")
    nd.members = [_mem("D1", "W8X31", 90.0, 45.0)]
    nd.operations = [_gus("D1", bolted=False, t=0.625)]
    return _prj("TP-A07", "diagonal W soldada con cartela soldada a una columna tubular HSS", _loads(nd, 45.0))


def ex_a08():
    nd = _col("W14X90", 0.0, 120.0, end=2)
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, 45.0, pos=14.0)]
    nd.operations = [_gus("D1", gus_hb=26.0), Operation(kind=OP_BASE, member="Columna", end=-1)]
    nd.loads = [Load("Caso 1", "D1", N=-40.0), Load("Caso 1", "Columna", N=-60.0, side=1),
                Load("Caso 2", "D1", N=40.0), Load("Caso 2", "Columna", N=-60.0, side=1)]
    return _with_base_data(_prj("TP-A08", "placa base: diagonal HSS con cartela atornillada soldada a la columna y apoyada y soldada sobre la placa base", nd))


def ex_a09():
    nd = _col("W14X90", 0.0, 120.0, end=2)
    nd.members = [_mem("D1", "W8X31", 90.0, 50.0, pos=14.0)]
    nd.operations = [_gus("D1", bolted=False, t=0.625, gus_hb=26.0), Operation(kind=OP_BASE, member="Columna", end=-1)]
    nd.loads = [Load("Caso 1", "D1", N=-40.0), Load("Caso 1", "Columna", N=-60.0, side=1),
                Load("Caso 2", "D1", N=40.0), Load("Caso 2", "Columna", N=-60.0, side=1)]
    return _with_base_data(_prj("TP-A09", "placa base: diagonal W soldada con cartela contra el alma de la columna y apoyada en la placa base", nd))


def ex_a10():
    nd = TY.build_nodo("base", {"col_shape": "W14X90", "brace_shape": "HSS5X5X3/8", "angle": 50.0, "n_braces": 2, "h": 20.0})
    nd.operations = [o for o in nd.operations if o.kind != OP_BASE] + [Operation(kind=OP_BASE, member=nd.main_name, end=-1)]
    for o in nd.operations:
        if o.kind == OP_GUSSET:
            o.gus_hb = 24.0
    return _with_base_data(_prj("TP-A10", "placa base con dos diagonales en V (una a cada ala, cartelas apoyadas en la placa)", nd))


# ====================================================================================================== cartela de esquina (viga + columna)
def ex_a11():
    nd = _col("W14X90", 120.0, 96.0)
    nd.members = [_mem("V1", "W18X50", 0.0, 0.0, L=96.0), _mem("D1", "HSS6X6X3/8", 0.0, -45.0, gap=6.0)]
    nd.operations = [Operation(kind=OP_TAB, member="V1"), _gus("D1")]
    nd.loads = [Load("Caso 1", "V1", Vz=-20.0), Load("Caso 1", "D1", N=35.0), Load("Caso 2", "V1", Vz=-20.0), Load("Caso 2", "D1", N=-35.0)]
    return _prj("TP-A11", "cartela de esquina bajo la viga: soldada al ala inferior de la viga y al ala de la columna a la vez (diagonal hacia abajo)", nd)


def ex_a12():
    nd = _col("W14X90", 120.0, 96.0)
    nd.members = [_mem("V1", "W18X50", 0.0, 0.0, L=96.0), _mem("D1", "HSS6X6X3/8", 0.0, 45.0, gap=6.0)]
    nd.operations = [Operation(kind=OP_TAB, member="V1"), _gus("D1", bolted=False)]
    nd.loads = [Load("Caso 1", "V1", Vz=-20.0), Load("Caso 1", "D1", N=35.0), Load("Caso 2", "V1", Vz=-20.0), Load("Caso 2", "D1", N=-35.0)]
    return _prj("TP-A12", "cartela de esquina sobre la viga: soldada al ala superior de la viga y al ala de la columna (diagonal hacia arriba, soldada)", nd)


# ====================================================================================================== chevron, K y X
def ex_a13():
    nd = _beam("W24X55")
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, 50.0), _mem("D2", "HSS6X6X3/8", 180.0, 50.0)]
    nd.operations = [_gus("D1"), _gus("D2")]
    return _prj("TP-A13", "chevron (V invertida) sobre una viga: dos diagonales HSS con una cartela común soldada al ala superior", _loads(nd, 40.0))


def ex_a14():
    nd = _beam("W24X55")
    nd.members = [_mem("D1", "W8X31", 0.0, -50.0), _mem("D2", "W8X31", 180.0, -50.0)]
    nd.operations = [_gus("D1", t=0.625), _gus("D2", t=0.625)]
    return _prj("TP-A14", "chevron (V) bajo una viga: dos diagonales W con cartela común soldada al ala inferior", _loads(nd, 40.0))


def ex_a15():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, 45.0), _mem("D2", "HSS6X6X3/8", 0.0, -45.0)]
    nd.operations = [_gus("D1"), _gus("D2")]
    return _prj("TP-A15", "arriostramiento en K: dos diagonales HSS (una sube y otra baja) con cartela común contra el ala de la columna", _loads(nd, 40.0))


def ex_a16():
    nd = TY.build_nodo("col", {"col_shape": "W14X90", "brace_shape": "HSS5X5X3/8", "angle": 45.0, "top": False, "n_braces": 4})
    return _prj("TP-A16", "arriostramiento en X en una columna intermedia: cuatro diagonales (dos cartelas, una a cada lado de la columna)", nd)


def ex_a17():
    nd = _col("HSS12X12X1/2")
    nd.members = [_mem("D1", "HSS5X5X3/8", 0.0, 40.0), _mem("D2", "HSS5X5X3/8", 0.0, -40.0)]
    nd.operations = [_gus("D1", bolted=False), _gus("D2", bolted=False)]
    return _prj("TP-A17", "arriostramiento en K soldado sobre una columna tubular HSS", _loads(nd, 40.0))


# ====================================================================================================== nudos de armadura
def ex_a18():
    nd = _chord("HSS10X10X3/8")
    nd.members = [_mem("D1", "HSS4X4X1/4", 0.0, -45.0, L=60.0), _mem("D2", "HSS4X4X1/4", 180.0, -45.0, L=60.0)]
    nd.operations = [_gus("D1"), _gus("D2")]
    return _prj("TP-A18", "nudo de armadura Warren en el cordón superior HSS: dos diagonales HSS con cartela común bajo el cordón", _loads(nd, 30.0))


def ex_a19():
    nd = _chord("HSS10X10X3/8")
    nd.members = [_mem("D1", "HSS4X4X1/4", 0.0, -45.0, L=60.0), _mem("M1", "HSS4X4X1/4", 0.0, -90.0, L=48.0)]
    nd.operations = [_gus("D1", bolted=False), _gus("M1", bolted=False)]
    return _prj("TP-A19", "nudo de armadura Pratt: diagonal y montante HSS soldados a una cartela soldada bajo el cordón superior", _loads(nd, 30.0))


def ex_a20():
    nd = _chord("HSS10X10X3/8")
    nd.members = [_mem("D1", "HSS4X4X1/4", 0.0, 45.0, L=60.0), _mem("D2", "HSS4X4X1/4", 180.0, 45.0, L=60.0), _mem("M1", "HSS4X4X1/4", 0.0, 90.0, L=48.0)]
    nd.operations = [_gus("D1"), _gus("D2"), _gus("M1")]
    return _prj("TP-A20", "nudo del cordón inferior: dos diagonales y un montante HSS hacia arriba con cartela común sobre el cordón", _loads(nd, 30.0))


def ex_a21():
    nd = _chord("W14X61")
    nd.members = [_mem("D1", "HSS4X4X1/4", 0.0, -45.0, L=60.0), _mem("D2", "HSS4X4X1/4", 180.0, -45.0, L=60.0)]
    nd.operations = [_gus("D1"), _gus("D2")]
    return _prj("TP-A21", "nudo de armadura con cordón de perfil W: dos diagonales HSS con cartela soldada al ala inferior del cordón", _loads(nd, 30.0))


def ex_a22():
    nd = _chord("HSS10X10X3/8")
    nd.members = [_mem("D1", "HSS4X4X1/4", 0.0, -45.0, L=60.0), _mem("D2", "HSS4X4X1/4", 180.0, -45.0, L=60.0),
                  _mem("D3", "HSS4X4X1/4", 0.0, 45.0, L=60.0), _mem("D4", "HSS4X4X1/4", 180.0, 45.0, L=60.0)]
    nd.operations = [_gus(m.name) for m in nd.members]
    return _prj("TP-A22", "nudo en X sobre un cordón: cuatro diagonales (dos cartelas, una por cada cara del cordón)", _loads(nd, 25.0))


# ====================================================================================================== medidas editadas, esviajes y tipologías
def ex_a23():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, -45.0)]
    nd.operations = [_gus("D1", n_bolts=4, bolt_s=3.5, gus_L=24.0, gus_hb=16.0, gus_hm=9.0, gus_cut=2.5)]
    return _prj("TP-A23", "cartela con medidas editadas (largo 24, base 16, punta 9) y esquinas cortadas, diagonal HSS atornillada", _loads(nd))


def ex_a24():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 30.0, -45.0)]
    nd.operations = [_gus("D1")]
    return _prj("TP-A24", "diagonal en un plano esviado (30°) respecto de las caras de la columna: la cartela se corta en bisel contra el ala", _loads(nd))


def ex_a25():
    nd = _col()
    nd.members = [_mem("D1", "HSS6X6X3/8", 0.0, -45.0, off=10.0)]
    nd.operations = [_gus("D1")]
    return _prj("TP-A25", "diagonal que llega 10 in por encima del eje de trabajo del nudo (desplazamiento sobre la columna)", _loads(nd))


def ex_a26():
    return _prj("TP-A26", "tipología «Plato base»: columna sobre placa base con dos diagonales", _with_base_data(_prj("x", "x", TY.build_nodo("base", {}))).node)


def ex_a27():
    nd = TY.build_nodo("base", {"col_shape": "W12X79", "brace_shape": "HSS6X6X3/8", "angle": 40.0, "n_braces": 4, "h": 24.0})
    for o in nd.operations:
        if o.kind == OP_GUSSET:
            o.gus_hb = 28.0
    return _with_base_data(_prj("TP-A27", "tipología «Plato base» con cuatro diagonales (una en cada cara de la columna)", nd))


def ex_a28():
    return _prj("TP-A28", "tipología «Columna intermedia»: cuatro diagonales (dos por lado)", TY.build_nodo("col", {}))


def ex_a29():
    return _prj("TP-A29", "tipología «Columna superior»: la columna termina en el nudo con dos diagonales hacia abajo", TY.build_nodo("col", {"top": True, "n_braces": 2}))


def ex_a30():
    return _prj("TP-A30", "tipología «Nudo de vigas»: viga principal inclinada con dos miembros que la cruzan", TY.build_nodo("vigas", {}))


EJEMPLOS = [
    ("TP-A01_diagonal_HSS_cartela_atornillada_ala_columna", ex_a01, "diagonal HSS, cartela atornillada, ala de columna W"),
    ("TP-A02_diagonal_HSS_cartela_soldada_ala_columna", ex_a02, "diagonal HSS ranurada y soldada, ala de columna W"),
    ("TP-A03_diagonal_W_cartela_atornillada_ala_columna", ex_a03, "diagonal W, cartela atornillada, ala de columna W"),
    ("TP-A04_diagonal_W_cartela_soldada_ala_columna", ex_a04, "diagonal W soldada, ala de columna W"),
    ("TP-A05_diagonal_HSS_cartela_alma_columna", ex_a05, "diagonal HSS, cartela atornillada al alma de columna W"),
    ("TP-A06_diagonal_HSS_columna_HSS", ex_a06, "diagonal HSS atornillada a columna HSS"),
    ("TP-A07_diagonal_W_soldada_columna_HSS", ex_a07, "diagonal W soldada a columna HSS"),
    ("TP-A08_placa_base_diagonal_HSS_cartela_apoyada", ex_a08, "placa base + diagonal HSS atornillada, cartela sobre la placa"),
    ("TP-A09_placa_base_diagonal_W_soldada_alma", ex_a09, "placa base + diagonal W soldada al alma"),
    ("TP-A10_placa_base_dos_diagonales_V", ex_a10, "placa base con dos diagonales"),
    ("TP-A11_cartela_esquina_bajo_viga", ex_a11, "cartela de esquina viga-columna (diagonal hacia abajo)"),
    ("TP-A12_cartela_esquina_sobre_viga_soldada", ex_a12, "cartela de esquina viga-columna (diagonal hacia arriba, soldada)"),
    ("TP-A13_chevron_sobre_viga_HSS", ex_a13, "chevron sobre viga W con diagonales HSS"),
    ("TP-A14_chevron_bajo_viga_W", ex_a14, "chevron bajo viga W con diagonales W"),
    ("TP-A15_arriostramiento_K_columna_W", ex_a15, "K en columna W"),
    ("TP-A16_arriostramiento_X_columna_intermedia", ex_a16, "X en columna W (4 diagonales)"),
    ("TP-A17_arriostramiento_K_soldado_columna_HSS", ex_a17, "K soldado en columna HSS"),
    ("TP-A18_armadura_Warren_cordon_HSS", ex_a18, "nudo Warren en cordón HSS"),
    ("TP-A19_armadura_Pratt_soldada", ex_a19, "nudo Pratt soldado"),
    ("TP-A20_armadura_cordon_inferior", ex_a20, "cordón inferior con montante"),
    ("TP-A21_armadura_cordon_W", ex_a21, "cordón de perfil W"),
    ("TP-A22_armadura_X_cordon_HSS", ex_a22, "X sobre cordón HSS"),
    ("TP-A23_cartela_medidas_editadas", ex_a23, "cartela con gus_L, gus_hb, gus_hm y gus_cut"),
    ("TP-A24_diagonal_esviada_30", ex_a24, "diagonal en plano esviado 30°"),
    ("TP-A25_diagonal_desplazada_sobre_columna", ex_a25, "diagonal con desplazamiento off"),
    ("TP-A26_tipologia_plato_base", ex_a26, "tipología base por omisión"),
    ("TP-A27_tipologia_plato_base_4_diagonales", ex_a27, "tipología base con 4 diagonales"),
    ("TP-A28_tipologia_columna_intermedia", ex_a28, "tipología col intermedia"),
    ("TP-A29_tipologia_columna_superior", ex_a29, "tipología col superior"),
    ("TP-A30_tipologia_nudo_vigas", ex_a30, "tipología vigas"),
]


def main(revisa=False):
    OUT.mkdir(exist_ok=True)
    bad = 0
    for fn, mk, _res in EJEMPLOS:
        p = mk()
        save_book(str(OUT / (fn + ".scp")), [p])
        print("->", fn)
        if revisa:
            from steelconpro.conn import assembly as AS, geocheck as GC
            from steelconpro import api
            m = AS.build_model(p)
            iss = GC.check(m)
            v = api.verify({"connection": api._dump(p)})
            ne = sum(1 for e in iss if e["sev"] == "error")
            print(f"     piezas {len(m.parts)} pernos {len(m.bolts)} cordones {len(m.welds)}  errores {ne} avisos {len(iss) - ne}  verify ok={v['ok']} d/c={v['max_ratio']:.2f}")
            for e in iss:
                print("       ", e["sev"], e["code"], e["text"][:170])
            bad += ne
    return bad


if __name__ == "__main__":
    sys.exit(1 if main("--revisa" in sys.argv) else 0)
