# -*- coding: utf-8 -*-
"""Plantillas de conexion del usuario: una conexion terminada se guarda como plantilla y sirve para crear conexiones nuevas despues.

No hay plantillas predefinidas: toda conexion nueva parte de cero (o de una plantilla propia).  Cada plantilla es un archivo `.json` en la carpeta
`plantillas` de los datos del usuario (%APPDATA%/SteelConPro/plantillas), con la conexion completa (cualquier modulo) y los perfiles y materiales
propios que usa, para que abra igual en otra computadora (se pueden copiar los archivos de una PC a otra).
"""
from __future__ import annotations
import copy
import datetime
import json
import re
from dataclasses import asdict
from pathlib import Path

from .appdata import data_dir

TAG = "steelconpro-plantilla"


def folder() -> Path:
    d = data_dir("APPDATA") / "plantillas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip().replace(" ", "_")
    return s[:60] or "plantilla"


def list_templates(ctype: str | None = None, where: Path | None = None) -> list:
    """[{name, ctype, desc, date, file}] de las plantillas (opcionalmente solo las de un modulo), por orden alfabetico."""
    out = []
    for f in sorted((where or folder()).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("formato") != TAG:
            continue
        if ctype is not None and d.get("ctype") != ctype:
            continue
        out.append({"name": str(d.get("nombre", f.stem)), "ctype": d.get("ctype", ""), "desc": str(d.get("descripcion", "")), "date": str(d.get("fecha", "")),
                    "file": str(f)})
    out.sort(key=lambda t: t["name"].lower())
    return out


def find(name: str, ctype: str, where: Path | None = None):
    return next((t for t in list_templates(ctype, where) if t["name"].lower() == name.strip().lower()), None)


def save_template(prj, name: str, desc: str = "", include_loads: bool = True, where: Path | None = None) -> str:
    """Guarda la conexion `prj` como plantilla (reemplaza la del mismo nombre y modulo).  Devuelve la ruta del archivo."""
    from .model import _used_extras
    from .conn.specs import CT_BASEPLATE, ATTR_OF
    name = name.strip()
    if not name:
        raise ValueError("La plantilla necesita un nombre.")
    q = copy.deepcopy(prj)
    q.element = ""
    if not include_loads and q.ctype in ATTR_OF:
        getattr(q, ATTR_OF[q.ctype]).loads = []
    shapes, mats = _used_extras([q])
    old = find(name, q.ctype, where)
    path = Path(old["file"]) if old else None
    if path is None:
        base = (where or folder()) / f"{_slug(q.ctype.split()[0])}_{_slug(name)}.json"
        path, k = base, 2
        while path.exists():
            path = base.with_name(f"{base.stem}_{k}.json")
            k += 1
    data = {"formato": TAG, "version": 1, "nombre": name, "descripcion": desc.strip(), "ctype": q.ctype, "fecha": datetime.date.today().isoformat(),
            "conexion": asdict(q), "perfiles": shapes, "materiales": mats}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return str(path)


def load_template(path: str):
    """Conexion (`Project`) guardada en la plantilla; registra antes los perfiles y materiales propios que lleva dentro."""
    from .model import Project
    from .shapes import CATALOG, Shape
    from . import materials as M
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("formato") != TAG:
        raise ValueError("El archivo no es una plantilla de SteelConPro.")
    for sd in d.get("perfiles", []):
        if not CATALOG.get(sd["label"]):
            CATALOG.shapes[sd["label"]] = Shape(**sd)
    CATALOG._reindex()
    M.register_embedded(d.get("materiales", {}))
    return Project.from_json(json.dumps(d["conexion"]))


def delete_template(path: str):
    Path(path).unlink(missing_ok=True)


def rename_template(path: str, new_name: str):
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("La plantilla necesita un nombre.")
    p = Path(path)
    d = json.loads(p.read_text(encoding="utf-8"))
    if find(new_name, d.get("ctype", ""), p.parent) not in (None,) and find(new_name, d.get("ctype", ""), p.parent)["file"] != str(p):
        raise ValueError(f"Ya existe una plantilla «{new_name}» de este módulo.")
    d["nombre"] = new_name
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
