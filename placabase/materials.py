# -*- coding: utf-8 -*-
"""
Bases de datos de materiales.  Unidades: ksi, in.

Fuentes:
  - Aceros de placa: AISC 360-22 Tabla A3.1 / ASTM.
  - Varillas de anclaje: AISC Design Guide 1 (2a Ed.) Tabla 2.2 y ASTM F1554,
    F3125, A449, A193, A354, A307.
  - Geometria de tuerca/cabeza hexagonal pesada: ASME B18.2.2 (ancho entre
    caras F).  El area neta de aplastamiento se calcula como
    Abrg = 0.866*F^2 - pi*db^2/4  (hexagono menos agujero).
  - Diametros de agujero para varillas de anclaje: AISC Manual Tabla 14-2.
  - Areas de esfuerzo a tension (Ase): rosca UNC, ASME B1.1.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from .units import frac_to_float, float_to_frac


# ===================================================================== ACEROS
@dataclass(frozen=True)
class Steel:
    name: str
    Fy: float          # ksi
    Fu: float          # ksi
    note: str = ""


PLATE_STEELS = [
    Steel("ASTM A36",           36.0, 58.0, "Placa hasta 8 in"),
    Steel("ASTM A572 Gr.50",    50.0, 65.0, "Uso general estructural"),
    Steel("ASTM A572 Gr.55",    55.0, 70.0, ""),
    Steel("ASTM A572 Gr.60",    60.0, 75.0, "t <= 1-1/4 in"),
    Steel("ASTM A572 Gr.65",    65.0, 80.0, "t <= 1-1/4 in"),
    Steel("ASTM A588 Gr.50",    50.0, 70.0, "Patinable (weathering)"),
    Steel("ASTM A709 Gr.50",    50.0, 65.0, "Puentes"),
    Steel("ASTM A709 Gr.50W",   50.0, 70.0, "Puentes, patinable"),
    Steel("ASTM A709 Gr.HPS70W",70.0, 85.0, "Puentes, alto desempeno"),
    Steel("ASTM A514 Gr.B",    100.0,110.0, "Templado y revenido"),
]

SHAPE_STEELS = [
    Steel("ASTM A992",          50.0, 65.0, "Perfiles W (por defecto)"),
    Steel("ASTM A36",           36.0, 58.0, ""),
    Steel("ASTM A572 Gr.50",    50.0, 65.0, ""),
    Steel("ASTM A500 Gr.B (HSS rect.)", 46.0, 58.0, "HSS cuadrado/rectangular"),
    Steel("ASTM A500 Gr.B (HSS red.)",  42.0, 58.0, "HSS circular"),
    Steel("ASTM A500 Gr.C (HSS rect.)", 50.0, 62.0, ""),
    Steel("ASTM A500 Gr.C (HSS red.)",  46.0, 62.0, ""),
    Steel("ASTM A53 Gr.B (Pipe)",       35.0, 60.0, "Tuberia"),
    Steel("ASTM A1085",                 50.0, 65.0, "HSS de pared cte."),
]


# ============================================================ VARILLA ANCLAJE
@dataclass(frozen=True)
class AnchorSteel:
    name: str
    Fy: float
    Fu: float
    dmax: float = 4.0          # diametro maximo cubierto por el grado, in
    ductile: bool = True       # elemento de acero ductil (ACI 17.5.3)
    note: str = ""


ANCHOR_STEELS = [
    AnchorSteel("ASTM F1554 Gr.36",  36.0,  58.0, 4.00, True,  "Varilla de anclaje estandar"),
    AnchorSteel("ASTM F1554 Gr.55",  55.0,  75.0, 4.00, True,  "Soldable con suplemento S1"),
    AnchorSteel("ASTM F1554 Gr.105", 105.0, 125.0, 3.00, True, "Alta resistencia"),
    AnchorSteel("ASTM A307 Gr.C",    36.0,  58.0, 4.00, True,  "Equivale a F1554 Gr.36"),
    AnchorSteel("ASTM A36 (varilla)",36.0,  58.0, 4.00, True,  ""),
    AnchorSteel("ASTM F3125 Gr.A325 (d<=1)",  92.0, 120.0, 1.00, True, "Antes A325"),
    AnchorSteel("ASTM F3125 Gr.A325 (d>1)",   81.0, 105.0, 1.50, True, ""),
    AnchorSteel("ASTM F3125 Gr.A490", 130.0, 150.0, 1.50, False, "No galvanizar"),
    AnchorSteel("ASTM A449 (d<=1)",    92.0, 120.0, 1.00, True, ""),
    AnchorSteel("ASTM A449 (1<d<=1.5)",81.0, 105.0, 1.50, True, ""),
    AnchorSteel("ASTM A193 Gr.B7 (d<=2.5)", 105.0, 125.0, 2.50, True, "Alta temperatura"),
    AnchorSteel("ASTM A354 Gr.BD",    130.0, 150.0, 2.50, False, ""),
]


# ================================================================ ELECTRODOS
@dataclass(frozen=True)
class Electrode:
    name: str
    FEXX: float


ELECTRODES = [
    Electrode("E60XX",  60.0),
    Electrode("E70XX",  70.0),
    Electrode("E80XX",  80.0),
    Electrode("E90XX",  90.0),
    Electrode("E100XX", 100.0),
    Electrode("E110XX", 110.0),
]


# =============================================================== CONCRETO
CONCRETE_PRESETS = [
    ("3 ksi  (21 MPa)",  3.0),
    ("4 ksi  (28 MPa)",  4.0),
    ("5 ksi  (35 MPa)",  5.0),
    ("6 ksi  (42 MPa)",  6.0),
    ("8 ksi  (55 MPa)",  8.0),
    ("10 ksi (69 MPa)", 10.0),
]


# ============================================================ PERNOS (in)
# db : (Ase in^2, hilos/in UNC, F ancho entre caras hex pesada in,
#       dh agujero en placa base AISC T.14-2 in)
_BOLTS = {
    "1/2":   (0.1419, 13,  0.875,  1.0625),
    "5/8":   (0.2260, 11,  1.0625, 1.1875),
    "3/4":   (0.3340, 10,  1.2500, 1.3125),
    "7/8":   (0.4620,  9,  1.4375, 1.5625),
    "1":     (0.6060,  8,  1.6250, 1.8125),
    "1-1/8": (0.7630,  7,  1.8125, 2.0000),
    "1-1/4": (0.9690,  7,  2.0000, 2.0625),
    "1-3/8": (1.1550,  6,  2.1875, 2.1875),
    "1-1/2": (1.4050,  6,  2.3750, 2.3125),
    "1-3/4": (1.9000,  5,  2.7500, 2.7500),
    "2":     (2.5000, 4.5, 3.1250, 3.2500),
    "2-1/4": (3.2500, 4.5, 3.5000, 3.5000),
    "2-1/2": (4.0000, 4.0, 3.8750, 3.7500),
    "2-3/4": (4.9300, 4.0, 4.2500, 4.0000),
    "3":     (5.9700, 4.0, 4.6250, 4.2500),
}

BOLT_SIZES = list(_BOLTS.keys())


@dataclass(frozen=True)
class BoltGeom:
    label: str
    db: float          # diametro nominal, in
    Ab: float          # area nominal bruta, in^2
    Ase: float         # area de esfuerzo a tension, in^2
    dh: float          # agujero en la placa base, in
    Fhex: float        # ancho entre caras de la tuerca/cabeza hex pesada, in
    Abrg: float        # area neta de aplastamiento de la cabeza, in^2


HOLE_RULES = [
    "AISC Tabla 14-2 (maximo recomendado)",
    "Arandela F844: db + 5/16, 1/2, 1",
    "Ajustado: db + 1/16 (plantilla o camisa)",
]


def hole_dia(label: str, rule: str = "") -> float:
    """Diametro del agujero en la placa base.

    Por defecto la Tabla 14-2 del Manual AISC (identica a la Tabla 2.3 de la
    DG1), que son los diametros MAXIMOS recomendados: son muy holgados a
    proposito, para absorber la tolerancia de colocacion de los anclajes en el
    concreto, y obligan a cubrirlos con una arandela de placa.  Si el grupo de
    anclajes se coloca con plantilla se justifica un agujero menor, y para eso
    estan las otras dos reglas (la de la nota al pie de la tabla, para arandela
    normal F844, y la ajustada de plantilla).
    """
    db = frac_to_float(label)
    if rule.startswith("Arandela F844"):
        return db + (0.3125 if db <= 1.0 else (0.5 if db <= 2.0 else 1.0))
    if rule.startswith("Ajustado"):
        return db + 0.0625
    return _BOLTS[label][3]


def bolt_geom(label: str, rule: str = "") -> BoltGeom:
    if label not in _BOLTS:
        raise KeyError(f"Diametro de perno no catalogado: {label}")
    Ase, _thr, F, _dh = _BOLTS[label]
    db = frac_to_float(label)
    dh = hole_dia(label, rule)
    Ab = math.pi * db ** 2 / 4.0
    Abrg = 0.866 * F ** 2 - Ab
    return BoltGeom(label, db, Ab, Ase, dh, F, Abrg)


# ---- distancias minimas al borde para varillas de anclaje (AISC T. J3.4 /
#      practica de DG1: 1.5*db pero nunca menor que dh/2 + 0.75 in de material)
def min_edge_distance(label: str, rule: str = "") -> float:
    g = bolt_geom(label, rule)
    return max(1.5 * g.db, g.dh / 2.0 + 0.75)


# ---- tamano minimo de filete, AISC 360 Tabla J2.4  (t = parte mas delgada)
def min_fillet(t_thinner: float) -> float:
    if t_thinner <= 0.25:
        return 0.125
    if t_thinner <= 0.50:
        return 0.1875
    if t_thinner <= 0.75:
        return 0.25
    return 0.3125


def max_fillet(t_edge: float) -> float:
    """AISC J2.2b: en borde de material de t >= 1/4 in, wmax = t - 1/16."""
    return t_edge - 0.0625 if t_edge >= 0.25 else t_edge


# ---------------------------------------------------------------- lookups
def find(lst, name, default_idx=0):
    for x in lst:
        if x.name == name:
            return x
    return lst[default_idx]


# ====================================================== CONCRETOS Y BIBLIOTECA
@dataclass
class ConcreteMat:
    name: str
    fc: float                   # ksi
    lam: float = 1.0            # 1.0 peso normal; 0.85 / 0.75 livianos
    note: str = ""


CONCRETES = [ConcreteMat(n, v) for n, v in CONCRETE_PRESETS]


def _mat_file():
    import os
    from pathlib import Path
    base = Path(os.environ.get("APPDATA", Path.home())) / "PlacaBasePro"
    base.mkdir(parents=True, exist_ok=True)
    return base / "materials.json"


def _register(kind: str, d: dict, user=True):
    """Anade (o reemplaza) un material en su catalogo."""
    tag = "usuario" if user else "proyecto"
    if kind == "steel":
        m = Steel(d["name"], float(d["Fy"]), float(d["Fu"]), d.get("note") or tag)
        for lst in (PLATE_STEELS, SHAPE_STEELS):
            lst[:] = [x for x in lst if x.name != m.name] + [m]
    elif kind == "anchor":
        m = AnchorSteel(d["name"], float(d["Fy"]), float(d["Fu"]),
                        float(d.get("dmax", 4.0)), bool(d.get("ductile", True)),
                        d.get("note") or tag)
        ANCHOR_STEELS[:] = [x for x in ANCHOR_STEELS if x.name != m.name] + [m]
    elif kind == "concrete":
        m = ConcreteMat(d["name"], float(d["fc"]), float(d.get("lam", 1.0)),
                        d.get("note") or tag)
        CONCRETES[:] = [x for x in CONCRETES if x.name != m.name] + [m]


def user_materials() -> dict:
    import json
    f = _mat_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"steel": [], "anchor": [], "concrete": []}


def save_user_materials(data: dict):
    import json
    _mat_file().write_text(json.dumps(data, indent=1, ensure_ascii=False),
                           encoding="utf-8")
    load_user_materials()


def load_user_materials():
    for kind, lst in user_materials().items():
        for d in lst:
            try:
                _register(kind, d, user=True)
            except Exception:
                pass


def register_embedded(data: dict):
    """Materiales guardados dentro de un proyecto (para abrirlo en otra PC)."""
    for kind, lst in (data or {}).items():
        for d in lst:
            names = {"steel": [x.name for x in PLATE_STEELS],
                     "anchor": [x.name for x in ANCHOR_STEELS],
                     "concrete": [x.name for x in CONCRETES]}.get(kind, [])
            if d.get("name") not in names:
                _register(kind, d, user=False)


load_user_materials()
