# -*- coding: utf-8 -*-
"""Lógica de las herramientas del servidor MCP (`mcp_server.py`): crear, modificar, analizar y obtener resultados de conexiones desde un chat
(Claude Desktop).  No depende de MCP: cada función recibe y devuelve datos simples (dict, list, str) y se prueba sola (`selftest_mcp.py`).

Una `Session` tiene abierto un proyecto (.scp, un «libro» de conexiones) del espacio de trabajo de la aplicación (Documentos/SteelConPro) y una
conexión activa.  Cada cambio se guarda en el archivo, así que lo que se hace por chat se abre en la aplicación.

Unidades de ENTRADA: in, kip, kip·in, ksi y grados (las del cálculo interno).  Los RESULTADOS salen en las unidades de la conexión.
"""
from __future__ import annotations
import copy
import datetime
import math
import os
import threading
import time
from dataclasses import asdict, fields
from pathlib import Path

from . import api
from .conn import ops as OPS, specs as SP
from .conn.specs import Member, Load, Operation
from .model import load_book, save_book, new_connection
from .shapes import CATALOG


class ChatError(Exception):
    """Error que se devuelve al chat con un mensaje que explica qué corregir."""


# ================================================================================================== descripción de las operaciones
_BOLT = {"bolt_size": ("Diámetro del perno (in)", "opcion", ["5/8", "3/4", "7/8", "1", "1-1/8"]),
         "bolt_grade": ("Calidad del perno (N = rosca incluida en el plano de corte, X = excluida)", "opcion", ["A325-N", "A325-X", "A490-N", "A490-X", "A307"])}
_PLATE = {"plate_t": ("Espesor de la placa o del ángulo (in)", "in", None),
          "plate_steel": ("Acero de la placa", "opcion", None)}
_WELD = {"weld_size": ("Cateto del filete (in)", "in", None),
         "weld_type": ("Tipo de soldadura", "opcion", ["Filete", "CJP (penetración completa)", "PJP (penetración parcial)"]),
         "weld_side": ("Lado del filete", "opcion", ["Ambos lados", "Solo lado 1", "Solo lado 2"])}

OPERACIONES = {
    SP.OP_TAB: ("Conexión de corte con placa simple (shear tab) soldada al principal y atornillada (o soldada) al alma de la viga.",
                {"member": ("Miembro que se conecta (llega al principal)", "miembro", None), **_BOLT,
                 "n_bolts": ("Filas de pernos", "int", None), "n_cols": ("Columnas de pernos (1 a 4)", "int", None),
                 "bolt_s": ("Separación entre filas (in)", "in", None), "bolt_g": ("Separación entre columnas (in)", "in", None),
                 "tab_H": ("Alto de la placa (in; 0 = automático)", "in", None), "tab_W": ("Ancho de la placa (in; 0 = automático)", "in", None),
                 **_PLATE, **_WELD, "beam_conn": ("Unión de la placa a la viga", "opcion", ["Atornillada", "Soldada"]),
                 "tab_mode": ("Posición de la placa", "opcion", ["Sobre la cara del soporte", "Hasta el interior de las alas del principal"]),
                 "cope_auto": ("Cortar la viga si choca con las alas del principal", "bool", None)}),
    SP.OP_DANG: ("Conexión de corte con doble ángulo atornillado al alma de la viga y al principal.",
                 {"member": ("Miembro que se conecta", "miembro", None), **_BOLT, "n_bolts": ("Pernos por fila", "int", None),
                  "bolt_s": ("Separación de los pernos (in)", "in", None), "plate_t": ("Espesor del ángulo (in)", "in", None),
                  "plate_steel": ("Acero de los ángulos", "opcion", None), "dang_lo": ("Pierna al soporte (in)", "in", None),
                  "dang_la": ("Pierna sobre el alma (in; 0 = automático)", "in", None), "dang_H": ("Largo del ángulo (in; 0 = automático)", "in", None),
                  "cope_auto": ("Cortar la viga si choca con las alas del principal", "bool", None)}),
    SP.OP_SEAT: ("Asiento de ángulo bajo el ala inferior de la viga (corte).",
                 {"member": ("Miembro que se conecta", "miembro", None), **_BOLT, "n_bolts": ("Pernos por fila", "int", None),
                  "plate_t": ("Espesor del ángulo (in)", "in", None), "plate_steel": ("Acero", "opcion", None),
                  "seat_Lh": ("Pierna horizontal (in)", "in", None), "seat_Lv": ("Pierna vertical (in)", "in", None),
                  "seat_W": ("Ancho del asiento (in; 0 = automático)", "in", None), "seat_stiff": ("Asiento rigidizado", "bool", None)}),
    SP.OP_EP_FLUSH: ("Conexión a momento con placa extrema a ras, atornillada al principal (columna I por el ala).",
                     {"member": ("Miembro que se conecta", "miembro", None), **_BOLT, "plate_t": ("Espesor de la placa extrema (in)", "in", None),
                      "plate_steel": ("Acero", "opcion", None), "ep_w": ("Ancho de la placa (in; 0 = automático)", "in", None),
                      "ep_h": ("Alto de la placa (in; 0 = automático)", "in", None), "ep_g": ("Gramil de los pernos (in; 0 = automático)", "in", None),
                      **_WELD, "wf_top": ("Soldadura del ala superior", "opcion", ["Filete", "CJP (penetración completa)", "PJP (penetración parcial)"]),
                      "wf_bot": ("Soldadura del ala inferior", "opcion", ["Filete", "CJP (penetración completa)", "PJP (penetración parcial)"])}),
    SP.OP_EP_EXT: ("Conexión a momento con placa extrema extendida.", None),
    SP.OP_WELD: ("Conexión a momento con alas soldadas (CJP) y alma atornillada con placa simple.",
                 {"member": ("Miembro que se conecta", "miembro", None), **_BOLT, "n_bolts": ("Filas de pernos del alma", "int", None),
                  "bolt_s": ("Separación (in)", "in", None), **_PLATE, **_WELD}),
    SP.OP_GUSSET: ("Cartela atornillada para una diagonal (2 pernos por fila).",
                   {"member": ("Diagonal", "miembro", None), **_BOLT, "n_bolts": ("Filas de pernos", "int", None), "bolt_s": ("Separación (in)", "in", None),
                    "plate_t": ("Espesor de la cartela (in)", "in", None), "plate_steel": ("Acero", "opcion", None), "weld_size": ("Filete de la cartela al principal (in)", "in", None),
                    "gus_L": ("Largo de la cartela (in; 0 = automático)", "in", None)}),
    SP.OP_GUSSET_W: ("Cartela con la diagonal soldada.", None),
    SP.OP_COPE: ("Corte del extremo (cope) de una viga.",
                 {"member": ("Viga", "miembro", None), "cope_top": ("Profundidad del corte superior (in)", "in", None),
                  "cope_bot": ("Profundidad del corte inferior (in)", "in", None), "cope_len": ("Largo del corte (in)", "in", None)}),
    SP.OP_CONT: ("Placas de continuidad (rigidizadores) en la columna frente a las alas de la viga.",
                 {"member": ("Viga a momento", "miembro", None), "cont_t": ("Espesor de las placas (in)", "in", None), "plate_steel": ("Acero", "opcion", None),
                  "weld_size": ("Filete (in)", "in", None)}),
    SP.OP_BASE: ("Placa base del miembro principal sobre concreto (anclajes, mortero, rigidizadores); sus datos se cambian con configurar_placa_base.",
                 {"member": ("Miembro que lleva la placa (normalmente el principal)", "miembro", None)}),
    SP.OP_PLATE: ("Placa general (refuerzo, cartela o rigidizador) sobre una cara de un elemento, soldada o atornillada.",
                  {"name": ("Nombre de la placa (único)", "texto", None), "role": ("Función", "opcion", ["Refuerzo", "Cartela", "Rigidizador"]),
                   "parent": ("Elemento sobre el que se coloca (miembro u otra placa)", "elemento", None), "face": ("Cara del elemento (ver describir_conexion)", "texto", None),
                   "orient": ("Orientación", "opcion", ["Paralela a la cara", "Perpendicular, transversal", "Perpendicular, longitudinal"]),
                   "shape": ("Forma", "opcion", ["Rectangular", "Triangular", "Con esquina recortada", "Circular", "Trapecio", "Ranurada (extremos redondeados)"]),
                   "attach": ("Unión", "opcion", ["Soldada", "Atornillada", "Sin unión propia"]),
                   "pl_L": ("Largo a lo largo del elemento (in)", "in", None), "pl_W": ("Ancho (in)", "in", None),
                   "pl_s": ("Posición del centro a lo largo de la cara, desde el inicio del elemento (in)", "in", None),
                   "pl_u": ("Desplazamiento transversal del centro (in)", "in", None), **_PLATE, "weld_size": ("Filete (in)", "in", None),
                   **_BOLT, "rows": ("Filas de pernos", "int", None), "cols": ("Columnas de pernos", "int", None),
                   "bolt_s": ("Separación entre filas (in)", "in", None), "bolt_g": ("Separación entre columnas (in)", "in", None),
                   "force_V": ("Cortante de diseño que toma la placa (kip; verificación de fórmulas)", "kip", None),
                   "force_T": ("Tracción de diseño (kip)", "kip", None)}),
    SP.OP_BOLTS: ("Grupo de pernos entre un elemento y otros (placas, miembros, bloque de concreto = anclajes).",
                  {"parent": ("Elemento de la cara donde se ponen los pernos", "elemento", None), "face": ("Cara", "texto", None),
                   "targets": ("Elementos que atraviesan (lista)", "lista", None), **_BOLT, "rows": ("Filas", "int", None), "cols": ("Columnas", "int", None),
                   "bolt_s": ("Separación entre filas (in)", "in", None), "bolt_g": ("Separación entre columnas (in)", "in", None),
                   "pl_s": ("Posición del centro del grupo a lo largo de la cara (in)", "in", None), "pl_u": ("Desplazamiento transversal (in)", "in", None),
                   "force_V": ("Cortante de diseño del grupo (kip)", "kip", None), "force_T": ("Tracción (kip)", "kip", None)}),
    SP.OP_FILLET: ("Soldadura de filete entre un elemento y las caras de otros.",
                   {"weld_main": ("Elemento que se suelda", "elemento", None), "weld_to": ("Caras de destino: lista de [elemento, cara]", "lista", None),
                    "weld_size": ("Cateto (in)", "in", None), "weld_all": ("Soldar todo el contorno que toca", "bool", None),
                    "force_V": ("Cortante de diseño (kip)", "kip", None), "force_T": ("Tracción (kip)", "kip", None)}),
    SP.OP_TRIM: ("Recorte de un miembro contra otro elemento (cara, inglete o volumen; boca de pez en tubos redondos), con soldadura opcional.",
                 {"targets": ("Miembros que se recortan (lista)", "lista", None), "parent": ("Elemento contra el que se recorta", "elemento", None),
                  "trim_mode": ("Modo", "opcion", ["Contra una cara de otro elemento", "Inglete con otro miembro", "Contra el volumen de otro elemento"]),
                  "trim_gap": ("Holgura (in)", "in", None), "trim_end": ("Extremo que se recorta", "opcion", ["Inicio", "Fin"]),
                  "trim_weld": ("Soldar donde toca", "bool", None), "weld_size": ("Filete (in)", "in", None)}),
    SP.OP_BLOCK: ("Bloque de concreto (muro, dado o pedestal) para apoyar placas y anclajes.",
                  {"name": ("Nombre", "texto", None), "wp_x": ("Centro de la cara superior, x (in)", "in", None), "wp_y": ("y (in)", "in", None),
                   "wp_z": ("z (in)", "in", None), "blk_L": ("Largo (in)", "in", None), "blk_W": ("Ancho (in)", "in", None), "blk_H": ("Alto (in)", "in", None)}),
}
OPERACIONES[SP.OP_EP_EXT] = (OPERACIONES[SP.OP_EP_EXT][0], {**OPERACIONES[SP.OP_EP_FLUSH][1], "ep_ext": ("Extensión de la placa sobre el ala (in)", "in", None)})
OPERACIONES[SP.OP_GUSSET_W] = (OPERACIONES[SP.OP_GUSSET_W][0], {k: v for k, v in OPERACIONES[SP.OP_GUSSET][1].items() if not k.startswith("bolt") and k != "n_bolts"})
_OP_FIELDS = {f.name: f for f in fields(Operation)}

MIEMBRO = {"name": ("Nombre único del miembro", "texto"), "shape": ("Perfil AISC (p. ej. W18X35, HSS6X6X3/8, L4X4X3/8, Pipe3STD); ver buscar_perfil", "perfil"),
           "steel": ("Acero del perfil", "texto"), "az": ("Azimut en planta (°): 0 = +x, 90 = +y", "grados"),
           "el": ("Elevación (°): 0 = horizontal, 90 = vertical hacia arriba, −45 = diagonal hacia abajo", "grados"),
           "pos": ("Posición a lo largo del principal (in, desde el nudo; + hacia el extremo +)", "in"),
           "off": ("Desplazamiento del eje en la dirección del peralte (in)", "in"), "off2": ("Desplazamiento lateral (in)", "in"),
           "roll": ("Giro del perfil sobre su eje (°)", "grados"), "gap": ("Separación del extremo a la cara del principal (in)", "in"),
           "attach_to": ("Miembro al que llega (vacío = al principal)", "texto"),
           "load_at": ("Punto de aplicación de sus acciones en el análisis de placas: «Automático» (pernos en corte y cartelas, extremo en momento), "
                       "«En el extremo del elemento» o «En los pernos»; no cambia las fórmulas", "opcion")}


# ================================================================================================== sesión
class Session:
    def __init__(self, root: str | None = None):
        self.root = Path(root or api.ws_default()["root"])
        self.path: Path | None = None
        self.book: list = []
        self.idx = 0
        self.job = None                      # trabajo del análisis de placas en curso
        self.job_sig = None
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- utilidades
    @property
    def p(self):
        if not self.book:
            raise ChatError("No hay un proyecto abierto: use abrir_proyecto o nuevo_proyecto.")
        return self.book[self.idx]

    @property
    def nd(self):
        return self.p.node

    def conn(self) -> dict:
        return asdict(self.p)

    def save(self):
        if self.path is None:
            raise ChatError("El proyecto no tiene archivo: use nuevo_proyecto o guardar_proyecto con una ruta.")
        for q in self.book:
            q.normalize()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        save_book(str(self.path), self.book)

    def _resolve(self, ruta: str) -> Path:
        q = Path(ruta)
        if not q.is_absolute():
            q = self.root / ruta
        if q.suffix.lower() not in (".scp", ".pbase"):
            q = q.with_suffix(".scp")
        return q

    def element_names(self):
        return [self.nd.main_name] + [m.name for m in self.nd.members] + [o.name for o in self.nd.operations if o.makes_element and o.name]

    def summary_line(self):
        nd = self.nd
        return (f"Conexión {self.idx + 1}/{len(self.book)} «{self.p.name or self.p.element}» ({self.p.element}): principal {nd.main_name} {nd.main_shape}, "
                f"{len(nd.members)} miembros, {len(nd.operations)} operaciones, {len({l.case for l in nd.loads})} casos de carga.")


# ================================================================================================== proyectos
def listar_proyectos(s: Session) -> dict:
    d = api.ws_list({"root": str(s.root)})
    return {"carpeta": str(s.root), "proyectos": [{"ruta": q["path"], "nombre": q.get("name", ""), "conexiones": q.get("n", q.get("count", "")),
                                                    "fecha": q.get("date", q.get("mtime", ""))} for q in d.get("projects", [])]}


def abrir_proyecto(s: Session, ruta: str) -> dict:
    q = s._resolve(ruta)
    if not q.exists():
        cand = [x for x in s.root.rglob("*.scp") if ruta.lower() in x.stem.lower()]
        if len(cand) == 1:
            q = cand[0]
        elif cand:
            raise ChatError("Hay varios proyectos con ese nombre: " + "; ".join(str(x.relative_to(s.root)) for x in cand[:12]))
        else:
            raise ChatError(f"No existe «{ruta}» en {s.root} (use listar_proyectos).")
    s.book = load_book(str(q))
    s.path = q if q.suffix.lower() == ".scp" else q.with_suffix(".scp")
    s.idx = 0
    return {"archivo": str(s.path), "conexiones": _conn_list(s), "activa": s.summary_line()}


def nuevo_proyecto(s: Session, nombre: str, carpeta: str = "", unidades: str = "Imperial") -> dict:
    d = api.ws_create_project({"root": str(s.root), "folder": carpeta, "name": nombre})
    s.path = Path(d["path"]) if "path" in d else s._resolve(os.path.join(carpeta, nombre))
    s.book = load_book(str(s.path))
    s.idx = 0
    _set_units(s.p, unidades)
    s.save()
    return {"archivo": str(s.path), "activa": s.summary_line()}


def guardar_proyecto(s: Session, ruta: str = "") -> dict:
    if ruta:
        s.path = s._resolve(ruta)
    s.save()
    return {"archivo": str(s.path)}


def _conn_list(s: Session):
    return [{"indice": i + 1, "nombre": q.name, "elemento": q.element, "principal": f"{q.node.main_name} {q.node.main_shape}", "miembros": len(q.node.members),
             "operaciones": len(q.node.operations)} for i, q in enumerate(s.book)]


def listar_conexiones(s: Session) -> dict:
    s.p
    return {"conexiones": _conn_list(s), "activa": s.idx + 1}


def seleccionar_conexion(s: Session, conexion) -> dict:
    s.p
    if isinstance(conexion, int) or str(conexion).isdigit():
        i = int(conexion) - 1
    else:
        i = next((k for k, q in enumerate(s.book) if str(conexion).lower() in (q.name.lower(), q.element.lower())), -1)
    if not 0 <= i < len(s.book):
        raise ChatError(f"No hay una conexión «{conexion}» (hay {len(s.book)}).")
    s.idx = i
    return {"activa": s.summary_line()}


def _set_units(p, unidades: str):
    u = (unidades or "Imperial").lower()
    if u.startswith("si") or "mm" in u or "metr" in u:
        p.u_len, p.u_force, p.u_stress, p.u_moment = "mm", "kN", "MPa", "kN·m"
    else:
        p.u_len, p.u_force, p.u_stress, p.u_moment = "in", "kip", "ksi", "kip·ft"


def nueva_conexion(s: Session, nombre: str, elemento: str = "", tipologia: str = "", parametros: dict | None = None, principal: dict | None = None,
                   unidades: str = "") -> dict:
    """Agrega una conexión al proyecto abierto (o crea un proyecto si no hay) y la deja activa."""
    if not s.book:
        nuevo_proyecto(s, nombre or "Proyecto", unidades=unidades or "Imperial")
        p = s.p
    else:
        p = new_connection()
        p.date = datetime.date.today().isoformat()
        s.book.append(p)
        s.idx = len(s.book) - 1
    p.name = nombre or p.name
    p.element = elemento or f"CN-{s.idx + 1:02d}"
    if unidades:
        _set_units(p, unidades)
    if tipologia:
        ids = [t["id"] for t in api.typologies()["types"]]
        if tipologia not in ids:
            raise ChatError(f"Tipología desconocida «{tipologia}»; las disponibles son {ids} (ver tipologias).")
        api._apply_typology(p, {"typology": tipologia, "params": parametros or {}})
    if principal:
        definir_principal(s, **principal)
    s.save()
    return {"activa": s.summary_line(), "conexion": describir_conexion(s)}


# ================================================================================================== catálogo
def buscar_perfil(s: Session, texto: str, limite: int = 25) -> dict:
    d = api.catalog_search({"q": texto, "limit": limite})
    keep = ("label", "kind", "d", "bf", "tw", "tf", "A", "W", "t", "OD")
    return {"perfiles": [{k: v for k, v in x.items() if k in keep} for x in d["shapes"]], "nota": "Dimensiones en in."}


def tipologias(s: Session) -> dict:
    return {"tipologias": api.typologies()["types"], "nota": "Use nueva_conexion(tipologia=id, parametros={key: valor}); las longitudes en in."}


def operaciones_disponibles(s: Session, tipo: str = "") -> dict:
    if not tipo:
        return {"operaciones": [{"tipo": k, "descripcion": v[0]} for k, v in OPERACIONES.items()],
                "nota": "Pida operaciones_disponibles(tipo) para ver sus parámetros, valores típicos y opciones."}
    k = _kind(tipo)
    desc, flds = OPERACIONES[k]
    base = OPS.defaults(k) if k in OPS._DEFAULTS else {}
    ref = Operation(kind=k)
    out = {}
    for f, (d, t, opts) in flds.items():
        v = base.get(f, getattr(ref, f, None))
        if f == "plate_steel":
            opts = [m["name"] for m in api.constants()["plate_steels"]]
        out[f] = {"descripcion": d, "tipo": t, "tipico": v, **({"opciones": opts} if opts else {})}
    return {"tipo": k, "descripcion": desc, "parametros": out,
            "nota": "Valores en in y kip. Cualquier parámetro omitido toma su valor típico. Las conexiones de catálogo (corte, momento, cartelas) se arman contra el miembro principal."}


def _kind(tipo: str) -> str:
    if tipo in OPERACIONES:
        return tipo
    t = tipo.lower().strip()
    hits = [k for k in OPERACIONES if t in k.lower()]
    if len(hits) == 1:
        return hits[0]
    raise ChatError(f"Tipo de operación «{tipo}» " + ("ambiguo: " + "; ".join(hits) if hits else "desconocido") + ". Use operaciones_disponibles().")


# ================================================================================================== modelado
def _shape_ok(lab: str) -> str:
    s = CATALOG.get(lab) or CATALOG.get(lab.upper().replace(" ", ""))
    if s is None:
        cand = [x["label"] for x in api.catalog_search({"q": lab.upper().replace(" ", ""), "limit": 8})["shapes"]]
        raise ChatError(f"Perfil «{lab}» no está en el catálogo." + (f" Parecidos: {', '.join(cand)}." if cand else " Use buscar_perfil."))
    return s.label


def _steel_ok(name: str, plate=False) -> str:
    c = api.constants()
    names = [m["name"] for m in (c["plate_steels"] if plate else c["steels"])] + ([m["name"] for m in c["steels"]] if plate else [m["name"] for m in c["plate_steels"]])
    if name in names:
        return name
    hit = [n for n in names if name.lower().replace(" ", "") in n.lower().replace(" ", "")]
    if hit:
        return hit[0]
    raise ChatError(f"Acero «{name}» desconocido. Opciones: {', '.join(dict.fromkeys(names))}.")


def definir_principal(s: Session, perfil: str = "", acero: str = "", nombre: str = "", azimut: float | None = None, elevacion: float | None = None,
                      giro: float | None = None, extremo: str | None = None) -> dict:
    nd = s.nd
    if nombre and nombre != nd.main_name:
        if nombre in s.element_names():
            raise ChatError(f"Ya hay un elemento «{nombre}».")
        old = nd.main_name
        nd.main_name = nombre
        for o in nd.operations:
            for f in ("member", "parent", "weld_main", "op_member", "align_to"):
                if getattr(o, f, "") == old:
                    setattr(o, f, nombre)
            o.targets = [nombre if x == old else x for x in (o.targets or [])]
        for m in nd.members:
            if m.attach_to == old:
                m.attach_to = nombre
        for l in nd.loads:
            if l.member == old:
                l.member = nombre
    if perfil:
        nd.main_shape = _shape_ok(perfil)
    if acero:
        nd.main_steel = _steel_ok(acero)
    if azimut is not None:
        nd.main_az = float(azimut)
    if elevacion is not None:
        nd.main_el = float(elevacion)
    if giro is not None:
        nd.main_roll = float(giro)
    if extremo is not None:
        ends = api.constants()["end_labels"]
        if extremo not in ends:
            raise ChatError(f"Extremo inválido; opciones: {ends}.")
        nd.main_end = extremo
    s.save()
    return {"principal": {"nombre": nd.main_name, "perfil": nd.main_shape, "acero": nd.main_steel, "azimut": nd.main_az, "elevacion": nd.main_el,
                          "extremo": nd.main_end or "Continuo (pasa por el nudo)"}}


def _member_kw(s: Session, d: dict, m: Member | None = None) -> dict:
    out = {}
    for k, v in d.items():
        if k not in MIEMBRO:
            raise ChatError(f"Campo de miembro desconocido «{k}». Campos: {', '.join(MIEMBRO)}.")
        if k == "shape":
            v = _shape_ok(str(v))
        elif k == "steel":
            v = _steel_ok(str(v))
        elif k == "attach_to":
            v = str(v or "")
            if v and v not in [s.nd.main_name] + [x.name for x in s.nd.members]:
                raise ChatError(f"«{v}» no es un miembro de la conexión.")
            if m is not None and v == m.name:
                raise ChatError("Un miembro no puede llegar a sí mismo.")
        elif k in ("name",):
            v = str(v)
        elif k == "load_at":
            if v not in SP.LOAD_AT:
                hit = [o for o in SP.LOAD_AT if str(v).lower() in o.lower()]
                if len(hit) != 1:
                    raise ChatError(f"load_at = «{v}» no es válido; opciones: {SP.LOAD_AT}.")
                v = hit[0]
        else:
            v = float(v)
        out[k] = v
    return out


def agregar_miembro(s: Session, nombre: str, perfil: str, azimut: float = 0.0, elevacion: float = 0.0, posicion: float = 0.0, acero: str = "",
                    se_une_a: str = "", desplazamiento: float = 0.0, desplazamiento_lateral: float = 0.0, giro: float = 0.0, separacion: float = 0.0) -> dict:
    nd = s.nd
    if nombre in s.element_names():
        raise ChatError(f"Ya hay un elemento «{nombre}».")
    from .conn import presets
    m = presets.new_member(nd)
    kw = _member_kw(s, {"name": nombre, "shape": perfil, "az": azimut, "el": elevacion, "pos": posicion, "off": desplazamiento, "off2": desplazamiento_lateral,
                        "roll": giro, "gap": separacion, "attach_to": se_une_a, **({"steel": acero} if acero else {})})
    for k, v in kw.items():
        setattr(m, k, v)
    nd.members.append(m)
    s.save()
    return {"miembro": _member_json(m), "geometria": _geo_brief(s)}


def modificar_miembro(s: Session, nombre: str, cambios: dict) -> dict:
    nd = s.nd
    m = next((x for x in nd.members if x.name == nombre), None)
    if m is None:
        if nombre == nd.main_name:
            raise ChatError("Para el miembro principal use definir_principal.")
        raise ChatError(f"No hay un miembro «{nombre}».")
    kw = _member_kw(s, cambios, m)
    if "name" in kw and kw["name"] != m.name:
        if kw["name"] in s.element_names():
            raise ChatError(f"Ya hay un elemento «{kw['name']}».")
        new_name = kw.pop("name")
        nd.rename_member(m.name, new_name)
        for l in nd.loads:
            if l.member == m.name:
                l.member = new_name
        m.name = new_name
    for k, v in kw.items():
        setattr(m, k, v)
    s.save()
    return {"miembro": _member_json(m), "geometria": _geo_brief(s)}


def eliminar_miembro(s: Session, nombre: str) -> dict:
    nd = s.nd
    m = next((x for x in nd.members if x.name == nombre), None)
    if m is None:
        raise ChatError(f"No hay un miembro «{nombre}».")
    nd.members.remove(m)
    for x in nd.members:
        if x.attach_to == nombre:
            x.attach_to = m.attach_to
    quit_ = [i for i, o in enumerate(nd.operations) if o.member == nombre or nombre in (o.targets or []) or o.parent == nombre]
    for i in sorted(quit_, reverse=True):
        nd.operations.pop(i)
    nd.loads = [l for l in nd.loads if l.member != nombre]
    s.save()
    return {"eliminado": nombre, "operaciones_quitadas": len(quit_)}


def _member_json(m: Member) -> dict:
    return {"nombre": m.name, "perfil": m.shape, "acero": m.steel, "azimut": m.az, "elevacion": m.el, "posicion": m.pos, "desplazamiento": m.off,
            "desplazamiento_lateral": m.off2, "giro": m.roll, "separacion": m.gap, "se_une_a": m.attach_to or "(principal)",
            "punto_de_carga": getattr(m, "load_at", SP.LOAD_AT[0])}


def _op_kw(s: Session, kind: str, params: dict) -> dict:
    flds = OPERACIONES[kind][1]
    out = {}
    for k, v in (params or {}).items():
        if k not in _OP_FIELDS or k == "kind":
            raise ChatError(f"Parámetro desconocido «{k}» para «{kind}». Parámetros: {', '.join(flds)}.")
        spec = flds.get(k)
        dflt = getattr(Operation(), k)
        if spec is not None and spec[1] == "opcion":
            opts = spec[2] or ([m["name"] for m in api.constants()["plate_steels"]] if k == "plate_steel" else None)
            if k == "plate_steel":
                v = _steel_ok(str(v), plate=True)
            elif opts and v not in opts:
                hit = [o for o in opts if str(v).lower() in o.lower()]
                if len(hit) != 1:
                    raise ChatError(f"«{k}» = «{v}» no es válido; opciones: {opts}.")
                v = hit[0]
        elif spec is not None and spec[1] in ("miembro", "elemento"):
            names = [s.nd.main_name] + [m.name for m in s.nd.members] if spec[1] == "miembro" else s.element_names()
            if v not in names:
                raise ChatError(f"«{k}» = «{v}» no existe; elementos: {names}.")
        elif isinstance(dflt, bool):
            v = bool(v)
        elif isinstance(dflt, int) and not isinstance(dflt, bool):
            v = int(v)
        elif isinstance(dflt, float):
            v = float(v)
        out[k] = v
    return out


def agregar_operacion(s: Session, tipo: str, parametros: dict | None = None) -> dict:
    k = _kind(tipo)
    kw = _op_kw(s, k, parametros or {})
    nd = s.nd
    if k in SP.CONNECTION_OPS:
        mem = kw.get("member")
        if not mem:
            raise ChatError(f"«{k}» necesita el parámetro member (el miembro que se conecta al principal).")
        if nd.is_child(mem):
            raise ChatError(f"«{mem}» llega a otro miembro: las conexiones de catálogo solo se arman contra el principal; use operaciones generales (placa, pernos, soldadura).")
    if k in (SP.OP_COPE, SP.OP_CONT) and not kw.get("member"):
        raise ChatError(f"«{k}» necesita member.")
    o = OPS.add_operation(nd, k, **kw)
    s.save()
    i = next(j for j, x in enumerate(nd.operations) if x is o)
    return {"operacion": _op_json(i, o), "geometria": _geo_brief(s)}


def modificar_operacion(s: Session, indice: int, cambios: dict) -> dict:
    nd = s.nd
    i = int(indice) - 1
    if not 0 <= i < len(nd.operations):
        raise ChatError(f"No hay una operación {indice} (hay {len(nd.operations)}; use describir_conexion).")
    o = nd.operations[i]
    kw = _op_kw(s, o.kind, cambios)
    for k, v in kw.items():
        setattr(o, k, v)
    s.save()
    return {"operacion": _op_json(i, o), "geometria": _geo_brief(s)}


def eliminar_operacion(s: Session, indice: int) -> dict:
    nd = s.nd
    i = int(indice) - 1
    if not 0 <= i < len(nd.operations):
        raise ChatError(f"No hay una operación {indice}.")
    quit_ = OPS.delete_operation(nd, i)
    s.save()
    return {"eliminadas": [f"{x.kind} — {x.name or x.member}" for x in quit_]}


def _op_json(i, o: Operation) -> dict:
    flds = OPERACIONES.get(o.kind, ("", {}))[1] or {}
    return {"indice": i + 1, "tipo": o.kind, "miembro": o.member, "nombre": o.name,
            "parametros": {k: getattr(o, k) for k in flds if k not in ("member",)}}


def configurar_placa_base(s: Session, cambios: dict) -> dict:
    """Cambia datos de la placa base: rutas «grupo.campo» de plate, bolts, conc, stiff, lug (p. ej. {"plate.tp": 1.5, "bolts.size": "1"})."""
    p = s.p
    if s.nd.base_op() is None:
        raise ChatError("La conexión no tiene placa base: agréguela con agregar_operacion(tipo='Placa base').")
    for path, v in (cambios or {}).items():
        if "." not in path:
            raise ChatError(f"Use rutas «grupo.campo» (grupos: plate, bolts, conc, stiff, lug); «{path}» no lo es.")
        g, f = path.split(".", 1)
        obj = getattr(p, g, None)
        if obj is None or g not in ("plate", "bolts", "conc", "stiff", "lug"):
            raise ChatError(f"Grupo «{g}» desconocido (plate, bolts, conc, stiff, lug).")
        names = [x.name for x in fields(obj)]
        if f not in names:
            raise ChatError(f"«{g}» no tiene el campo «{f}»; campos: {', '.join(names)}.")
        cur = getattr(obj, f)
        if isinstance(cur, bool):
            v = bool(v)
        elif isinstance(cur, int):
            v = int(v)
        elif isinstance(cur, float):
            v = float(v)
        setattr(obj, f, v)
    s.save()
    return {k: {x.name: getattr(getattr(p, k), x.name) for x in fields(getattr(p, k)) if not isinstance(getattr(getattr(p, k), x.name), list)}
            for k in ("plate", "bolts", "conc")}


def definir_cargas(s: Session, cargas: list, reemplazar: bool = True) -> dict:
    """cargas = [{caso, miembro, N, Vy, Vz, T, My, Mz}] (kip, kip·in) en ejes locales del miembro en su extremo junto al nudo."""
    nd = s.nd
    names = [nd.main_name] + [m.name for m in nd.members] + ["@nudo"]
    new = []
    for c in cargas or []:
        c = dict(c)
        mem = c.pop("miembro", c.pop("member", ""))
        if mem not in names:
            raise ChatError(f"Miembro «{mem}» desconocido; opciones: {names}.")
        case = str(c.pop("caso", c.pop("case", "Caso 1")))
        kw = {}
        for k in ("N", "Vy", "Vz", "T", "My", "Mz"):
            if k in c:
                kw[k] = float(c.pop(k))
        side = int(c.pop("lado", c.pop("side", 0)))
        if c:
            raise ChatError(f"Campos de carga desconocidos: {list(c)} (use caso, miembro, N, Vy, Vz, T, My, Mz, lado).")
        new.append(Load(case=case, member=mem, side=side, **kw))
    if reemplazar:
        nd.loads = new
    else:
        nd.loads += new
    s.save()
    return {"casos": sorted({l.case for l in nd.loads}), "cargas": [asdict(l) for l in nd.loads],
            "nudo": _nodal_brief(s)}


def _nodal_brief(s: Session):
    try:
        a = api.nodal({"connection": s.conn()})
        return [{"caso": c["case"], "reaccion_principal_F": [round(x, 3) for x in (c.get("R") or [0, 0, 0])], "reaccion_principal_M": [round(x, 2) for x in (c.get("M") or [0, 0, 0])]}
                for c in a.get("cases", [])]
    except Exception as e:                                                   # noqa: BLE001
        return f"(análisis nodal: {e})"


def analisis_nodal(s: Session) -> dict:
    a = api.nodal({"connection": s.conn()})
    return {"casos": [{k: v for k, v in c.items() if k not in ("draw",)} for c in a.get("cases", [])],
            "nota": "Fuerzas en kip y momentos en kip·in, ejes globales; la reacción del principal sale del equilibrio."}


def describir_conexion(s: Session) -> dict:
    p, nd = s.p, s.nd
    info = api.element_info({"connection": s.conn()})
    return {"conexion": {"nombre": p.name, "elemento": p.element, "unidades": f"{p.u_len}, {p.u_force}, {p.u_stress}"},
            "principal": {"nombre": nd.main_name, "perfil": nd.main_shape, "acero": nd.main_steel, "azimut": nd.main_az, "elevacion": nd.main_el,
                          "extremo": nd.main_end or "Continuo (pasa por el nudo)", "largo_dibujado_in": nd.auto_len()},
            "miembros": [_member_json(m) for m in nd.members],
            "operaciones": [_op_json(i, o) for i, o in enumerate(nd.operations)],
            "cargas": [asdict(l) for l in nd.loads],
            "elementos_y_caras": [{"nombre": e["name"], "caras": e.get("faces", [])} for e in info.get("elements", [])]}


def _geo_brief(s: Session):
    g = api.geometry_check({"connection": s.conn()})
    return {"errores": g["errors"], "avisos": g["warnings"], "detalle": [f"[{e['sev']}] {e['text']}" for e in g["issues"][:8]], "notas": g.get("notes", [])[:6]}


def revisar_geometria(s: Session) -> dict:
    g = api.geometry_check({"connection": s.conn()})
    return {"errores": g["errors"], "avisos": g["warnings"], "hallazgos": [{"severidad": e["sev"], "texto": e["text"], "piezas": e["parts"]} for e in g["issues"]],
            "notas": g.get("notes", [])}


# ================================================================================================== análisis y resultados
def calcular(s: Session, analisis_placas: bool = True) -> dict:
    """Verificaciones de fórmulas cerradas (inmediatas) y análisis del modelo de placas con CalculiX en segundo plano."""
    v = api.verify({"connection": s.conn()})
    out = {"formulas": _summary(v), "analisis_placas": "no solicitado"}
    if analisis_placas:
        if not s.nd.loads:
            out["analisis_placas"] = "sin casos de carga: defina cargas para analizar el modelo de placas"
        else:
            r = api.fem_node_start({"connection": s.conn()})
            s.job, s.job_sig = r["job"], api._node_sig(s.p)
            st = api.job_status({"job": s.job})
            out["analisis_placas"] = ("terminado (resultados vigentes)" if st["done"] and st["state"] == "done"
                                      else "en curso: consulte estado_analisis cada 30-60 s y luego resultados")
    return out


def estado_analisis(s: Session, esperar_s: float = 20.0) -> dict:
    if s.job is None:
        return {"estado": "sin análisis en curso"}
    t0 = time.time()
    while True:
        st = api.job_status({"job": s.job})
        if st["done"] or time.time() - t0 >= max(0.0, min(float(esperar_s), 50.0)):
            break
        time.sleep(1.0)
    out = {"estado": {"running": "en curso", "done": "terminado", "error": "error", "cancelled": "cancelado"}.get(st["state"], st["state"]),
           "mensaje": st.get("message", ""), "casos_terminados": f"{st.get('finished', 0)} de {st.get('total', 0)}"}
    if st["state"] == "error":
        out["error"] = st.get("error", "")[:1500]
    if st["done"] and api._node_sig(s.p) != s.job_sig:
        out["aviso"] = "La conexión cambió durante el análisis: vuelva a calcular."
    return out


def _summary(v: dict) -> dict:
    cats = v.get("categories") or []
    by = {}
    for c in v["checks"]:
        by.setdefault(c.get("cat") or "Otras", {}).setdefault(c.get("comp") or c.get("group") or "Otras", []).append(c)

    def mx(lst):
        ev = [c for c in lst if not c["skip"]]
        return max((c["ratio"] for c in ev), default=None)
    out = []
    for cat in cats + [k for k in by if k not in cats]:
        if cat not in by:
            continue
        allc = [c for lst in by[cat].values() for c in lst]
        gov = max((c for c in allc if not c["skip"]), key=lambda c: c["ratio"], default=None)
        out.append({"categoria": cat, "componentes": len(by[cat]), "dc_max": None if mx(allc) is None else round(mx(allc), 3),
                    "cumple": mx(allc) is None or mx(allc) <= 1.0 + 1e-9,
                    "gobierna": None if gov is None else f"{gov.get('comp') or gov.get('group')} — {gov['title']} (D/C {gov['ratio']:.3f})",
                    "fuentes": sorted({("FEM" if c.get("src") == "fem" else "fórmulas") for c in allc})})
    return {"cumple": bool(v["ok"]), "dc_max": round(v["max_ratio"], 3), "gobierna": v["governing"], "categorias": out,
            "avisos": v["warnings"][:15], "geometria": v.get("geometry"), "analisis_placas_vigente": bool(v.get("node_fem"))}


def resultados(s: Session, categoria: str = "", componente: str = "", solo_no_cumple: bool = False) -> dict:
    """Resumen estándar por categorías; con `categoria`, sus componentes; con `componente`, sus verificaciones."""
    v = api.verify({"connection": s.conn()})
    res = {"resumen": _summary(v)}
    fem = api._node_fem(s.p)
    if fem:
        us = s.p.units()
        res["modelo_placas"] = [{"caso": R.case, "nodos": R.n_nodes, "elementos": R.n_elems, "desplazamiento_max": us.q("L", R.umax, 3),
                                 "von_mises_max": us.q("S", R.vmmax, 1), "deformacion_plastica_max_pct": round(100 * R.peeqmax, 3), "plastico": R.plastic,
                                 "notas": R.notes[:6] + ([R.msg] if R.msg else [])} for _i, (R, _c) in sorted(fem.items())]
    checks = v["checks"]
    if categoria:
        sel = [c for c in checks if (c.get("cat") or "").lower().startswith(categoria.lower())]
        comps = {}
        for c in sel:
            comps.setdefault(c.get("comp") or c.get("group"), []).append(c)
        res["componentes"] = [{"componente": k, "fuente": "FEM" if any(c.get("src") == "fem" for c in lst) else "fórmulas",
                               "dc_max": round(max((c["ratio"] for c in lst if not c["skip"]), default=0.0), 3), "verificaciones": len(lst)}
                              for k, lst in sorted(comps.items(), key=lambda kv: -max((c["ratio"] for c in kv[1] if not c["skip"]), default=0.0))]
    if componente or solo_no_cumple:
        sel = [c for c in checks if (not componente or componente.lower() in (c.get("comp") or c.get("group") or "").lower())
               and (not solo_no_cumple or (not c["skip"] and c["ratio"] > 1.0 + 1e-9))]
        res["verificaciones"] = [{"componente": c.get("comp") or c.get("group"), "verificacion": c["title"], "demanda": _r(c["demand"]), "capacidad": _r(c["capacity"]),
                                  "unidad": c["unit"], "dc": round(c["ratio"], 3), "cumple": c["ok"], "no_evaluado": c["skip"], "referencia": c["ref"], "nota": c["note"]}
                                 for c in sel[:120]]
    return res


def _r(x):
    try:
        return round(float(x), 3)
    except (TypeError, ValueError):
        return x


def generar_informe(s: Session, formato: str = "pdf", ruta: str = "") -> dict:
    fmt = "docx" if formato.lower() in ("docx", "word") else "pdf"
    if ruta:
        q = s._resolve(ruta).with_suffix("." + fmt)
    else:
        base = s.path.with_suffix("") if s.path else s.root / "informe"
        q = Path(f"{base}_{s.p.element or 'conexion'}.{fmt}")
    api.report({"connection": s.conn(), "format": fmt, "path": str(q), "detail": True})
    return {"archivo": str(q)}


def imagen(s: Session, tipo: str = "modelo", caso: int = 1, azimut: float = 50.0, elevacion: float = 24.0, ancho: int = 1000, alto: int = 720) -> bytes:
    """PNG del modelo 3D o de un campo de resultados del modelo de placas (sobre la deformada automática)."""
    import io
    from .conn import assembly as AS
    from .conn.fem import scene as FS, shellpost as SPo
    t = (tipo or "modelo").lower()
    p = s.p
    if t.startswith("mod") or t.startswith("geo"):
        sc = FS.scene_model(AS.build_model(p), loads=False, tags=True)
        title = f"{p.element} - {p.name}"
    else:
        ent = api.NODE_SHELL.get((api._node_sig(p), int(caso) - 1))
        if ent is None:
            raise ChatError("No hay un análisis de placas vigente para ese caso: use calcular y espere a que termine (estado_analisis).")
        R = ent[0]
        field = "peeq" if "plast" in t else "u" if "despl" in t or "deform" in t else "vm"
        sc = SPo.scene(R, p.units(), field=field, scale=SPo.auto_scale(R), edges=False)
        hud = sc.hud[0][1] if sc.hud else ""
        title = f"{R.case} - " + hud.replace("—", "-")
    import unicodedata                                                       # la fuente del render no tiene acentos ni «×»
    title = "".join(ch for ch in unicodedata.normalize("NFKD", title.replace("×", "x").replace("Ω", "Omega ").replace("φ", "phi").replace("−", "-")) if not unicodedata.combining(ch) and ord(ch) < 128)
    im = FS.render_scene_image(sc, float(elevacion), float(azimut), (int(ancho), int(alto)), title=title, ss=2, margin=0.05)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
