# -*- coding: utf-8 -*-
"""Tipologías de nudo: plantillas que arman el nudo completo (miembros, operaciones y cargas) a partir de unos pocos datos.

    base   Plato base: columna que nace en la placa base, con las diagonales que llegan cerca de la base (cada una con su cartela).
    col    Nodo de columna intermedia o superior: la columna continúa (o termina) en el nudo y llegan las diagonales.
    vigas  Nodo de vigas: dos miembros que se cruzan en el nudo (una X), uno de ellos es el principal.
    smf    Pórtico especial a momento (plantilla fija): columna W con una o dos vigas W unidas a sus alas con placa extrema precalificada
           (AISC Design Guide 4: 4E, 4ES u 8ES) diseñada para sismo, y placas de continuidad.  Con ella se verifican la placa (DG4) y el
           nudo (AISC 341-22: columna fuerte–viga débil, zona del panel y detalle de las placas de continuidad).  Los valores por
           omisión son los del ejemplo 4.4 de la guía (W21X55 a W14X109, 8ES, pernos A325 de 1 in, placa de 7/8 in, Vu = 40 kip).

Todo queda editable después (miembros, operaciones, cargas); las tipologías solo ahorran armar el nudo a mano.
"""
from __future__ import annotations
import math

from .specs import Nodo, Member, Operation, Load, END_LABELS, OP_GUSSET, OP_BASE, OP_CONT, OP_EP_EXT, SHEAR_BOLT_SIZES
from .presets import MAIN_NAME

TYPES = [("base", "Plato base"), ("col", "Nodo de columna intermedia o superior"), ("vigas", "Nodo de vigas"),
         ("smf", "Pórtico especial: placa extrema precalificada (AISC DG4)")]
HSS_STEEL = "ASTM A500 Gr.C (HSS rect.)"
I_STEEL = "ASTM A992"


def schema(kind: str) -> list:
    """Campos del formulario de cada tipología: [{key, label, type, default, items?, unit?}].
    type: shape | num | int | bool | choice (con items); unit: 'L' (longitud) o 'F' (fuerza) para convertir en la interfaz."""
    brace = {"key": "brace_shape", "label": "Perfil de las diagonales", "type": "shape", "default": "HSS5X5X3/8"}
    ang = {"key": "angle", "label": "Ángulo de las diagonales sobre la horizontal (°)", "type": "num", "default": 45.0, "lo": 25, "hi": 80}
    if kind == "base":
        return [{"key": "col_shape", "label": "Perfil de la columna", "type": "shape", "default": "W14X90"}, brace, ang,
                {"key": "n_braces", "label": "Número de diagonales", "type": "int", "default": 2, "lo": 0, "hi": 4},
                {"key": "h", "label": "Altura donde llegan las diagonales sobre la placa base", "type": "num", "default": 20.0, "unit": "L", "lo": 8, "hi": 120}]
    if kind == "col":
        return [{"key": "col_shape", "label": "Perfil de la columna", "type": "shape", "default": "W14X90"}, brace, ang,
                {"key": "top", "label": "Nudo superior (la columna termina en el nudo)", "type": "bool", "default": False},
                {"key": "n_braces", "label": "Número de diagonales", "type": "int", "default": 4, "lo": 1, "hi": 4}]
    if kind == "smf":
        return [{"key": "col_shape", "label": "Perfil de la columna", "type": "shape", "default": "W14X109"},
                {"key": "beam_shape", "label": "Perfil de la viga", "type": "shape", "default": "W21X55"},
                {"key": "dg4", "label": "Placa extrema precalificada (AISC DG4)", "type": "choice", "default": "8ES", "items": ["4E", "4ES", "8ES"]},
                {"key": "two_sided", "label": "Vigas a los dos lados de la columna", "type": "bool", "default": False},
                {"key": "top", "label": "Nudo de cubierta (la columna termina en el nudo)", "type": "bool", "default": False},
                {"key": "bolt_size", "label": "Diámetro de los pernos (in)", "type": "choice", "default": "1", "items": SHEAR_BOLT_SIZES[1:]},
                {"key": "bolt_grade", "label": "Grado de los pernos", "type": "choice", "default": "A325-N", "items": ["A325-N", "A490-N"]},
                {"key": "plate_t", "label": "Espesor de la placa extrema", "type": "num", "default": 0.875, "unit": "L", "lo": 0.375, "hi": 3.0, "dec": 3},
                {"key": "cont_t", "label": "Espesor de las placas de continuidad (0 = automático)", "type": "num", "default": 0.0, "unit": "L", "lo": 0.0, "hi": 2.0, "dec": 3},
                {"key": "Lh", "label": "Distancia entre rótulas plásticas Lh (0 = solo el cortante de gravedad)", "type": "num", "default": 0.0, "unit": "L", "lo": 0.0, "hi": 1200.0},
                {"key": "Vg", "label": "Cortante de gravedad en la rótula Vg", "type": "num", "default": 40.0, "unit": "F", "lo": 0.0, "hi": 1000.0},
                {"key": "H", "label": "Altura del piso (cortante de la columna en la zona del panel)", "type": "num", "default": 157.48, "unit": "L", "lo": 60.0, "hi": 1200.0}]
    return [{"key": "main_shape", "label": "Perfil del miembro principal (pasa por el nudo)", "type": "shape", "default": "W16X31"},
            {"key": "brace_shape", "label": "Perfil de los otros miembros", "type": "shape", "default": "W16X31"}, ang,
            {"key": "n_members", "label": "Miembros que llegan al principal", "type": "int", "default": 2, "lo": 1, "hi": 2}]


def _vals(kind, params):
    out = {f["key"]: f["default"] for f in schema(kind)}
    lim = {f["key"]: (f.get("lo"), f.get("hi")) for f in schema(kind)}
    for k, v in (params or {}).items():
        if k in out and v not in (None, ""):
            try:
                if "items" in next(f for f in schema(kind) if f["key"] == k):
                    items = next(f for f in schema(kind) if f["key"] == k)["items"]
                    if str(v) in items:
                        out[k] = str(v)
                    continue
                out[k] = type(out[k])(v) if not isinstance(out[k], bool) else bool(v)
            except (TypeError, ValueError):
                continue                                           # dato inválido: se deja el valor por omisión
            lo, hi = lim[k]
            if lo is not None and not isinstance(out[k], bool):
                out[k] = type(out[k])(min(max(out[k], lo), hi))   # dentro de los límites del formulario
    return out


def _steel(label):
    from ..shapes import CATALOG
    s = CATALOG.get(label)
    return HSS_STEEL if (s is not None and s.is_hollow) else I_STEEL


def _member(name, shape, az, el, pos, L=60.0, gap=0.0) -> Member:
    return Member(name=name, shape=shape, steel=_steel(shape), az=az, el=el, pos=pos, L=L, gap=gap)


def _face(nd, m):
    """off2 del miembro para que su eje llegue al centro de la cara del ala de la columna (la viga queda en el plano del alma)."""
    from . import assembly as AS
    from ..shapes import CATALOG
    _A, msx, msy = AS.main_frame(nd)
    d = AS.member_dir(m)
    dx, dy = float(d @ msx), float(d @ msy)
    sg = 1.0 if dy > 0 else -1.0
    m.off, m.off2 = 0.0, -(sg * CATALOG.get(nd.main_shape).d / 2.0) / dy * dx


def _smf(v) -> Nodo:
    top = bool(v["top"])
    nd = Nodo(main_name="Columna", main_shape=v["col_shape"], main_steel=I_STEEL, main_el=90.0, main_end=END_LABELS[1] if top else END_LABELS[0],
              main_len_neg=72.0, main_len_pos=0.0 if top else 72.0)
    nd.balance_end = 1 if top else -1
    beams = [("V1", 0.0)] + ([("V2", 180.0)] if v["two_sided"] else [])
    nd.loads = []
    for k, (name, az) in enumerate(beams):
        m = Member(name=name, shape=v["beam_shape"], steel=I_STEEL, az=az, el=0.0, L=60.0)
        m.sism_Lh, m.sism_Vg = float(v["Lh"]), float(v["Vg"])
        nd.members.append(m)
        _face(nd, m)
        nd.operations.append(Operation(kind=OP_EP_EXT, member=name, ep_dg4=v["dg4"], ep_seis=True, bolt_size=v["bolt_size"], bolt_grade=v["bolt_grade"],
                                       plate_t=float(v["plate_t"]), plate_steel="ASTM A572 Gr.50", ep_st_t=0.5 if v["dg4"] != "4E" else 0.0,
                                       wf_top="CJP (penetración completa)", wf_bot="CJP (penetración completa)", weld_size=0.3125))
        nd.loads.append(Load("Caso 1", name, Vz=-float(v["Vg"]), My=4000.0 if k == 0 else -4000.0))   # sismo: los momentos de las dos vigas se suman en la columna
    t = float(v["cont_t"])
    if t <= 0:                                                       # automático: 0.5·tbf (un lado) o tbf (dos lados), AISC 341-22 E3.6f.2, y ≥ bs/16 (J10.8)
        from ..shapes import CATALOG
        b, c = CATALOG.get(v["beam_shape"]), CATALOG.get(v["col_shape"])
        req = max((1.0 if v["two_sided"] else 0.5) * b.tf, (c.bf - c.tw) / 2.0 / 16.0, 0.375)
        t = math.ceil(req * 8.0 - 1e-9) / 8.0
    nd.operations.append(Operation(kind=OP_CONT, member="V1", cont_t=t))   # un par de placas atraviesa la columna y sirve a las dos vigas
    return nd


def build_nodo(kind: str, params: dict | None = None) -> Nodo:
    v = _vals(kind, params)
    if kind == "smf":
        return _smf(v)
    if kind == "base":
        nd = Nodo(main_name="Columna", main_shape=v["col_shape"], main_steel=_steel(v["col_shape"]), main_end=END_LABELS[2], main_len_neg=0.0, main_len_pos=max(v["h"] * 3.5, 72.0))
        azs = [0.0, 180.0, 90.0, 270.0]
        for k in range(int(v["n_braces"])):
            nd.members.append(_member(f"D{k + 1}", v["brace_shape"], azs[k], v["angle"], v["h"], L=72.0))
            nd.operations.append(Operation(kind=OP_GUSSET, member=f"D{k + 1}", plate_t=0.5))
        nd.operations.append(Operation(kind=OP_BASE, member=nd.main_name, end=-1))
        nd.loads = [Load("Caso 1", nd.main_name, N=-40.0, side=1)]
        for k, m in enumerate(nd.members):
            nd.loads.append(Load("Caso 1", m.name, N=-10.0 if k % 2 == 0 else 10.0))
        return nd
    if kind == "col":
        top = bool(v["top"])
        nd = Nodo(main_name="Columna", main_shape=v["col_shape"], main_steel=_steel(v["col_shape"]), main_end=END_LABELS[1] if top else END_LABELS[0], main_len_neg=72.0, main_len_pos=0.0 if top else 72.0)
        # dos diagonales hacia abajo (una a cada lado) y, si la columna continúa, dos hacia arriba
        plan = [(0.0, -v["angle"]), (180.0, -v["angle"]), (0.0, v["angle"]), (180.0, v["angle"])]
        plan = [p for p in plan if not (top and p[1] > 0)]
        for k, (az, el) in enumerate(plan[:int(v["n_braces"])]):
            nd.members.append(_member(f"D{k + 1}", v["brace_shape"], az, el, 0.0, L=72.0))
            nd.operations.append(Operation(kind=OP_GUSSET, member=f"D{k + 1}", plate_t=0.5))
        nd.balance_end = 1 if top else -1                          # la acción de la columna sobre el nudo sale del equilibrio: no se le asignan cargas
        nd.loads = []
        for k, m in enumerate(nd.members):
            nd.loads.append(Load("Caso 1", m.name, N=-10.0 if k % 2 == 0 else 10.0))
        return nd
    nd = Nodo(main_name="Viga principal", main_shape=v["main_shape"], main_steel=_steel(v["main_shape"]), main_az=0.0, main_el=float(v["angle"]), main_end=END_LABELS[0], main_len_neg=60.0, main_len_pos=60.0)
    plan = [(0.0, -v["angle"]), (180.0, v["angle"])]
    for k, (az, el) in enumerate(plan[:int(v["n_members"])]):
        nd.members.append(_member(f"M{k + 1}", v["brace_shape"], az, el, 0.0, L=60.0))
        nd.operations.append(Operation(kind=OP_GUSSET, member=f"M{k + 1}", plate_t=0.5))
    nd.loads = []                                                    # el principal pasa por el nudo: su acción sale del equilibrio
    for k, m in enumerate(nd.members):
        nd.loads.append(Load("Caso 1", m.name, N=-10.0 if k % 2 == 0 else 10.0))
    return nd
