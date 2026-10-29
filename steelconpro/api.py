# -*- coding: utf-8 -*-
"""API del motor para la aplicacion Electron: funciones que reciben y devuelven JSON (diccionarios), sin Qt.

El libro de un proyecto es una lista de conexiones; cada conexion es el diccionario de `Project` (`dataclasses.asdict`).  La aplicacion guarda el
documento y manda la conexion completa en cada llamada, asi el servidor no guarda estado salvo las cuentas largas (analisis FEM) y la cache de sus
resultados.  `server.py` las expone por HTTP local (POST /api/<funcion>).
"""
from __future__ import annotations
import base64
import hashlib
import copy
import datetime
import json
import math
import os
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import __version__
from . import materials as M
from . import units as UN
from .model import Project, new_connection, save_book, load_book
from .shapes import CATALOG
from .conn import assembly as AS, baseplate as BP, solve_conn, module_for
from .conn import specs as SP
from .conn.fem import scene as FS
from .scene3d import Scene, FLOATS


class ApiError(Exception):
    pass


# ================================================================================================== utilidades
def _prj(d) -> Project:
    p = Project.from_json(json.dumps(d))
    if p.ctype != SP.CT_NODE:
        from .conn.baseplate import unify
        p = unify(p)
    return p


def _dump(p: Project) -> dict:
    return json.loads(p.to_json())


def _b64(a) -> str:
    a = np.asarray(a, np.float32)
    return base64.b64encode(a.tobytes()).decode("ascii") if a.size else ""


def _rgb(hexcol):
    return FS._rgb(hexcol)


# ================================================================================================== informacion general
def app_info(_=None) -> dict:
    return {"version": __version__, "name": "SteelConPro"}


def constants(_=None) -> dict:
    """Datos fijos que la interfaz necesita para armar formularios: operaciones, calidades de pernos, textos del miembro principal, unidades y esquema de la placa base."""
    sch = json.load(open(Path(__file__).parent / "data" / "schema_baseplate.json", encoding="utf-8"))
    bolt_steels = [{"name": b.name, "Fnt": b.Fnt, "Fnv": b.Fnv} for b in M.bolt_grades()]
    return {
        "version": __version__,
        "ops": {"kinds": SP.OPERATIONS, "groups": SP.OP_GROUPS, "connection": list(SP.CONNECTION_OPS), "base": SP.OP_BASE},
        "op": {"TAB": SP.OP_TAB, "DANG": SP.OP_DANG, "SEAT": SP.OP_SEAT, "EP_FLUSH": SP.OP_EP_FLUSH, "EP_EXT": SP.OP_EP_EXT, "WELD": SP.OP_WELD, "GUSSET": SP.OP_GUSSET,
               "GUSSET_W": SP.OP_GUSSET_W, "COPE": SP.OP_COPE, "CONT": SP.OP_CONT, "BASE": SP.OP_BASE, "PLATE": SP.OP_PLATE, "BOLTS": SP.OP_BOLTS, "FILLET": SP.OP_FILLET, "CUT": SP.OP_CUT},
        "orients": SP.PLATE_ORIENTS, "shapes": SP.PLATE_SHAPES, "attaches": SP.ATTACHES, "faces_i": SP.FACES_I, "faces_box": SP.FACES_BOX,
        "end_labels": SP.END_LABELS,
        "bolt_sizes": SP.SHEAR_BOLT_SIZES, "bolt_grades": [b["name"] for b in bolt_steels],
        "units": {"len": UN.LEN_UNITS, "force": UN.FORCE_UNITS, "stress": UN.STRESS_UNITS, "moment": UN.MOMENT_UNITS,
                  "sets": {k: list(v) for k, v in UN.DEFAULT_SETS.items()}},
        "steels": [{"name": m.name, "Fy": m.Fy, "Fu": m.Fu} for m in M.SHAPE_STEELS],
        "plate_steels": [{"name": m.name, "Fy": m.Fy, "Fu": m.Fu} for m in M.PLATE_STEELS],
        "electrodes": [{"name": m.name, "FEXX": m.FEXX} for m in M.ELECTRODES],
        "schema_baseplate": sch,
        "roles": SP.PLATE_ROLES,
    }


# ================================================================================================== libros (archivos .scp)
def book_new(_=None) -> dict:
    p = new_connection()
    p.date = datetime.date.today().isoformat()
    p.element = "CN-01"
    return {"connections": [_dump(p)]}


def connection_new(args=None) -> dict:
    args = args or {}
    p = new_connection()
    p.date = datetime.date.today().isoformat()
    for k in ("name", "u_len", "u_force", "u_stress", "u_moment"):
        if k in args:
            setattr(p, k, args[k])
    p.element = args.get("element") or f"CN-{int(args.get('n', 1)):02d}"
    return _dump(p)


def book_load(args) -> dict:
    path = args["path"]
    book = load_book(path)
    from .model import LAST_SKIPPED
    return {"path": path, "connections": [_dump(p) for p in book], "skipped": [list(x) for x in LAST_SKIPPED]}


def book_save(args) -> dict:
    path = args["path"]
    book = [_prj(c) for c in args["connections"]]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    save_book(path, book)
    return {"path": path}


def normalize(args) -> dict:
    """Aplica las restricciones entre datos de la conexion; devuelve la conexion y los cambios hechos."""
    p = _prj(args["connection"])
    changes = p.normalize()
    return {"connection": _dump(p), "changes": changes}


# ================================================================================================== modelo de la conexion
def op_defaults(args) -> dict:
    from .conn import ops as OPS
    return OPS.defaults(args["kind"], args.get("role", ""))


def add_operation(args) -> dict:
    """Agrega una operacion a la conexion con sus valores tipicos (`params` los cambia).  Devuelve la conexion y el indice de la operacion nueva."""
    from .conn import ops as OPS
    p = _prj(args["connection"])
    o = OPS.add_operation(p.node, args["kind"], **(args.get("params") or {}))
    return {"connection": _dump(p), "index": next(i for i, x in enumerate(p.node.operations) if x is o), "name": o.name}


def delete_operation(args) -> dict:
    """Quita una operacion y, en cascada, las que dependen del elemento que crea (por ejemplo, una placa que rigidiza otra)."""
    from .conn import ops as OPS
    p = _prj(args["connection"])
    removed = OPS.delete_operation(p.node, int(args["index"]))
    return {"connection": _dump(p), "removed": [{"kind": o.kind, "name": o.name} for o in removed]}


def dependents(args) -> dict:
    p = _prj(args["connection"])
    nd = p.node
    return {"operations": nd.dependents(args["name"])}


def designate_main(args) -> dict:
    p = _prj(args["connection"])
    notes = AS.set_main(p.node, args["name"])
    return {"connection": _dump(p), "notes": notes}


def new_member(args) -> dict:
    from .conn import presets
    p = _prj(args["connection"])
    m = presets.new_member(p.node)
    return {"member": asdict(m)}


def element_info(args) -> dict:
    """Elementos de la conexion a los que se puede hacer referencia (para elegir en los dialogos): miembros, placas de operaciones y caras."""
    from .conn import ops as OPS
    p = _prj(args["connection"])
    return OPS.elements(p)


def section_info(args) -> dict:
    s = CATALOG.get(args["label"])
    if s is None:
        raise ApiError(f"Perfil desconocido: {args['label']}")
    return _shape_json(s, full=True)


def _shape_json(s, full=False):
    d = {"label": s.label, "family": s.family, "kind": s.kind, "d": s.d, "bf": s.bf, "tf": s.tf, "tw": s.tw, "hollow": s.is_hollow, "round": s.is_round,
         "source": s.source}
    if full:
        d.update({"A": s.A, "Ix": s.Ix, "Iy": s.Iy, "Zx": s.Zx, "Zy": s.Zy, "Sx": s.Sx, "Sy": s.Sy, "rects": s.rects(), "pieces": s.pieces() if s.kind == "GEN" else None})
    return d


def catalog_families(args=None) -> dict:
    free = bool((args or {}).get("free", True))
    fams = CATALOG.families(free=free)
    return {"families": [{"id": f, "label": f} for f in fams]}


def catalog_shapes(args) -> dict:
    labs = CATALOG.by_family(args["family"]) if args.get("family") else CATALOG.all_labels() if hasattr(CATALOG, "all_labels") else []
    q = (args.get("q") or "").strip().lower()
    out = []
    for lab in labs:
        if q and q not in lab.lower():
            continue
        s = CATALOG.get(lab)
        if s is not None:
            out.append(_shape_json(s))
        if len(out) >= int(args.get("limit", 400)):
            break
    return {"shapes": out}


def catalog_search(args) -> dict:
    """Busca un perfil por texto en todas las familias."""
    q = (args.get("q") or "").strip().lower()
    out = []
    for fam in CATALOG.families(free=True):
        for lab in CATALOG.by_family(fam):
            if q in lab.lower():
                s = CATALOG.get(lab)
                out.append(_shape_json(s))
                if len(out) >= int(args.get("limit", 60)):
                    return {"shapes": out}
    return {"shapes": out}


# ================================================================================================== geometria 3D para el visor
def _faces_scene(faces, rgb, alpha, edges=True, group="g"):
    sc = Scene()
    sc.group = group
    sc.add_faces(faces, rgb, alpha, edges=edges)
    return sc


def _scene_to_json(sc, name, kind, extra=None):
    """Arreglos (x y z nx ny nz r g b a) de una escena de una pieza: triangulos opacos y translucidos y lineas de aristas (float32 en base64)."""
    def cat(lst):
        return np.concatenate(lst).astype(np.float32) if lst else np.zeros((0, FLOATS), np.float32)
    d = {"name": name, "kind": kind, "o": _b64(cat(sc.opaque)), "t": _b64(cat(sc.trans)), "l": _b64(cat(sc.lines))}
    if extra:
        d.update(extra)
    return d


def mesh(args) -> dict:
    """Modelo 3D de la conexion: una malla por pieza (miembros, placas, angulos), los pernos, las soldaduras y la placa base, mas etiquetas y cotas."""
    p = _prj(args["connection"])
    mdl = AS.build_model(p)
    parts, pts = [], []
    for part in mdl.parts:
        faces = []
        for pr in part.prisms:
            faces += [[tuple(map(float, q)) for q in f] for f in pr.faces()]
        pts += [q for f in faces for q in f]
        sc = _faces_scene(faces, _rgb(FS.COLORS.get(part.kind, FS.COLORS["other"])), 1.0 if part.kind != "support" else 0.55)
        parts.append(_scene_to_json(sc, part.name, part.kind, {"label": part.label}))
    for w in mdl.welds:
        pr = FS.weld_prism(w)
        faces = [[tuple(map(float, q)) for q in f] for f in pr.faces()]
        sc = _faces_scene(faces, _rgb(FS.COLORS["weld"]), 1.0, edges=False)
        parts.append(_scene_to_json(sc, w.name or "Soldadura", "weld", {"label": "Soldadura"}))
    shank, head = [], []
    for b in mdl.bolts:
        f = FS._bolt_faces(b)
        shank += [[tuple(map(float, q)) for q in fc] for fc in f["shank"]]
        head += [[tuple(map(float, q)) for q in fc] for fc in f["head"]]
    if shank or head:
        sc = Scene()
        sc.add_faces(shank, _rgb("#2f4b7c"), 1.0, edges=False)
        sc.add_faces(head, _rgb("#44546a"), 1.0, edges=True)
        parts.append(_scene_to_json(sc, "Pernos", "bolt", {"label": f"{len(mdl.bolts)} pernos"}))
    for tag, faces, color, alpha in mdl.extra:
        fl = [[tuple(map(float, q)) for q in f] for f in faces]
        pts += [q for f in fl for q in f]
        sc = _faces_scene(fl, _rgb(color), alpha, edges=tag != "conc")
        parts.append(_scene_to_json(sc, f"Placa base · {tag}", "base_" + tag, {"label": "Placa base"}))
    P = np.asarray(pts, float).reshape(-1, 3)
    lo, hi = (P.min(axis=0).tolist(), P.max(axis=0).tolist()) if len(P) else ([0, 0, 0], [1, 1, 1])
    dims = [{"a": list(map(float, a)), "b": list(map(float, b)), "off": list(map(float, off)),
             "value": float(val) if not isinstance(val, str) else val, "views": list(views)} for a, b, off, val, views in mdl.dims]
    labels = [{"pos": list(map(float, pos)), "text": text} for pos, text in mdl.tags]
    return {"parts": parts, "dims": dims, "labels": labels, "notes": mdl.notes, "bounds": [lo, hi], "unit": "in"}


def thumbnail(args) -> dict:
    """Imagen PNG (base64) de la primera conexion para las tarjetas del inicio."""
    import io
    p = _prj(args["connection"])
    w, h = int(args.get("w", 360)), int(args.get("h", 240))
    mdl = AS.build_model(p)
    sc = FS.scene_model(mdl, loads=False, tags=False)
    im = FS.render_scene_image(sc, 24.0, 50.0, (w, h), ss=2, margin=0.05)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return {"png": base64.b64encode(buf.getvalue()).decode("ascii")}


# ================================================================================================== verificacion
FEM_CACHE: dict = {}            # firma del proyecto de la placa base de una combinacion -> (Fem3D, resultado crudo)
JOBS: dict = {}


def _fem_map(prj: Project) -> dict:
    if prj.node.base_op() is None:
        return {}
    bp = BP.derive(prj, prj.node)
    out = {}
    for i in range(len(bp.combo_list())):
        q = bp.with_combo(i)
        e = FEM_CACHE.get(q.sig3d())
        if e is not None:
            out[i] = e[0]
    return out


def _check_json(us, ch):
    from . import report
    dv, cv, ul = report.ck_vals(us, ch)
    return {"key": ch.key, "title": ch.title, "group": getattr(ch, "group", ""), "demand": dv, "capacity": cv, "unit": ul, "ratio": ch.ratio, "ok": ch.ok,
            "skip": ch.skip, "ref": ch.ref, "note": ch.note}


def verify(args) -> dict:
    p = _prj(args["connection"])
    R = solve_conn(p, fem_map=_fem_map(p))
    us = p.units()
    nd = p.node
    gov = R.governing
    ops = []
    for i, o in enumerate(nd.operations):
        ops.append({"index": i, "kind": o.kind, "member": o.member, "name": o.name})
    return {
        "ok": bool(R.ok), "max_ratio": R.max_ratio, "governing": gov.title if gov else "",
        "checks": [_check_json(us, c) for c in R.checks], "warnings": list(R.warnings), "combos": list(R.combo_rows or []), "combo_gov": R.combo_gov,
        "memory": R.rec.to_html() if R.rec is not None else "", "operations": ops, "has_fem": bool(_fem_map(p)),
    }


# ================================================================================================== analisis FEM de la placa base (trabajos largos)
def fem_start(args) -> dict:
    from . import mesh3d
    from .rep3d import make_fem
    p = _prj(args["connection"])
    if p.node.base_op() is None:
        raise ApiError("La conexion no tiene la operacion de placa base.")
    bp = BP.derive(p, p.node)
    todo = []
    for i in range(len(bp.combo_list())):
        q = bp.with_combo(i)
        if q.sig3d() not in FEM_CACHE:
            todo.append((i, bp.combos[i].name, q))
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "state": "running", "messages": [], "done": False, "error": "", "total": len(todo), "finished": 0, "cancel": None}
    JOBS[jid] = job
    if not todo:
        job.update(state="done", done=True)
        return {"job": jid}
    from .mesh3d import CancelToken
    tok = CancelToken()
    job["cancel"] = tok
    folder_base = Path(args.get("folder") or os.path.join(os.path.expanduser("~"), "SteelConPro", "fem"))
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def run():
        try:
            for k, (i, name, q) in enumerate(todo):
                pre = f"Combinacion {k + 1} de {len(todo)}: {name}\n" if len(todo) > 1 else ""
                res, msg = mesh3d.full_3d(q, str(folder_base / f"{p.element or 'placa'}_{stamp}" / f"comb{i + 1}"), "modelo3d",
                                          progress=lambda m, pre=pre: job["messages"].append(pre + m), cancel=tok)
                if res is None:
                    job.update(state="cancelled" if str(msg).startswith(mesh3d.CANCELADO) else "error", error=str(msg), done=True)
                    return
                fem = make_fem(q, res)
                fem.sig = q.sig3d()
                FEM_CACHE[q.sig3d()] = (fem, res)
                job["finished"] = k + 1
            job.update(state="done", done=True)
        except Exception as e:                                                  # noqa: BLE001
            job.update(state="error", error=f"{type(e).__name__}: {e}", done=True)
            job["trace"] = traceback.format_exc()

    threading.Thread(target=run, daemon=True).start()
    return {"job": jid}


def job_status(args) -> dict:
    j = JOBS.get(args["job"])
    if j is None:
        raise ApiError("Trabajo desconocido.")
    return {k: v for k, v in j.items() if k != "cancel"} | {"message": j["messages"][-1] if j["messages"] else ""}


def job_cancel(args) -> dict:
    j = JOBS.get(args["job"])
    if j is not None and j.get("cancel") is not None:
        j["cancel"].cancel()
    return {"ok": True}


def fem_scene(args) -> dict:
    """Escena (mallas con color por vertice) del campo de resultados del analisis FEM de la placa base, para el visor."""
    from . import scene3d
    p = _prj(args["connection"])
    bp = BP.derive(p, p.node)
    i = int(args.get("combo", 0))
    q = bp.with_combo(i)
    e = FEM_CACHE.get(q.sig3d())
    if e is None:
        raise ApiError("No hay un analisis FEM vigente de esa combinacion: corralo primero.")
    fem, raw = e
    sc = scene3d.scene_results(raw, q, field=args.get("field", "vm"), scale=float(args.get("scale", 0.0)), part=args.get("part", "all"))
    cb = sc.cbar
    d = {"parts": [_scene_to_json(sc, "Resultados", "fem")], "message": sc.message, "unit": q.units().L}
    if cb is not None:
        d["cbar"] = {"colors": np.asarray(cb["colors"], float).tolist(), "vmin": float(cb["vmin"]), "vmax": float(cb["vmax"]), "title": cb.get("title", ""), "note": cb.get("note", "")}
    P = np.asarray(sc.pts, float).reshape(-1, 3) if len(sc.pts) else np.zeros((1, 3))
    d["bounds"] = [P.min(axis=0).tolist(), P.max(axis=0).tolist()]
    d["summary"] = {"nodes": int(raw.n_nodes), "elems": int(raw.n_elems), "umax": float(raw.umax), "vmmax": float(raw.vmmax), "msg": fem.msg or ""}
    d["parts_list"] = [{"id": k, "label": v} for k, v in __import__("steelconpro.view3d", fromlist=["PART_LABELS"]).PART_LABELS.items()]
    return d


# ================================================================================================== informes y exportacion
def report(args) -> dict:
    from . import report as R
    from .conn import save_figures
    import tempfile
    p = _prj(args["connection"])
    res = solve_conn(p, fem_map=_fem_map(p))
    figs = save_figures(p, res, tempfile.mkdtemp(prefix="scp_"))
    fmt = args.get("format", "pdf")
    path = args["path"]
    if fmt == "pdf":
        R.export_pdf(p, res, path, figs, bool(args.get("detail", True)))
    else:
        R.export_docx(p, res, path, figs, bool(args.get("detail", True)))
    return {"path": path}


def save_png(args) -> dict:
    """Guarda una imagen enviada por la interfaz como data URL (captura del visor 3D)."""
    data = args["data"].split(",", 1)[-1]
    Path(args["path"]).write_bytes(base64.b64decode(data))
    return {"path": args["path"]}


def export_step(args) -> dict:
    from .conn.fem import driver
    p = _prj(args["connection"])
    driver.export_step(p, None, args["path"])
    return {"path": args["path"]}


# ================================================================================================== biblioteca de secciones (Section Designer)
def section_templates(_=None) -> dict:
    from . import sections as SEC
    return {"templates": [{"name": n, "params": [{"key": k, "label": lb, "default": v, "length": k not in SEC.LENGTH_PARAMS} for k, lb, v in spec]}
                          for n, (spec, _fn) in SEC.TEMPLATES.items()]}


def section_build(args) -> dict:
    from . import sections as SEC
    comps = SEC.build_template(args["template"], **(args.get("values") or {}))
    return section_analyze({"components": comps})


def section_analyze(args) -> dict:
    """Propiedades exactas y contornos (para dibujar) de una lista de componentes (rectangulo, circulo, anillo, poligono)."""
    from . import sections as SEC
    comps = args["components"]
    bad = [SEC.valid_comp(c) for c in comps]
    props = SEC.section_props([c for c, b in zip(comps, bad) if not b]) if any(not b for b in bad) else None
    outlines = []
    for c, b in zip(comps, bad):
        if b:
            outlines.append(None)
            continue
        o = SEC.comp_outline(c)
        outlines.append([[list(map(float, q)) for q in ring] for ring in o] if o and isinstance(o[0], (list, tuple)) and o and isinstance(o[0][0], (list, tuple)) else
                        [[list(map(float, q)) for q in o]])
    return {"components": comps, "errors": bad, "props": props, "outlines": outlines,
            "overlap": SEC.overlap_area([c for c, b in zip(comps, bad) if not b]) if props else 0.0}


def section_save(args) -> dict:
    from . import shapes as SH
    name = args["name"].strip()
    if not name:
        raise ApiError("La seccion necesita un nombre.")
    sh = SH.make_general(name, args["components"])
    CATALOG.add_free(sh, replace=args.get("replace", ""))
    CATALOG.save_user()
    return {"shape": _shape_json(sh, full=True)}


def section_delete(args) -> dict:
    CATALOG.remove(args["label"])
    CATALOG.save_user()
    return {"ok": True}


def section_components(args) -> dict:
    from . import sections as SEC
    s = CATALOG.get(args["label"])
    if s is None:
        raise ApiError("Perfil desconocido.")
    return section_analyze({"components": SEC.comps_of_shape(s)})


# ================================================================================================== biblioteca de materiales
def materials_get(_=None) -> dict:
    um = M.user_materials()
    return {"user": um,
            "all": {"steel": [{"name": m.name, "Fy": m.Fy, "Fu": m.Fu, "E": m.E, "nu": m.nu, "rho": m.rho, "extra": M.is_extra("steel", m.name)} for m in M.SHAPE_STEELS],
                    "bolt": [{"name": b.name, "Fnt": b.Fnt, "Fnv": b.Fnv, "note": b.note, "extra": M.is_extra("bolt", b.name)} for b in M.bolt_grades()],
                    "electrode": [{"name": m.name, "FEXX": m.FEXX, "extra": M.is_extra("electrode", m.name)} for m in M.ELECTRODES],
                    "anchor": [{"name": m.name, "Fy": m.Fy, "Fu": m.Fu, "dmax": m.dmax, "ductile": m.ductile, "extra": M.is_extra("anchor", m.name)} for m in M.ANCHOR_STEELS],
                    "concrete": [{"name": m.name, "fc": m.fc, "lam": m.lam, "extra": M.is_extra("concrete", m.name)} for m in M.CONCRETES]}}


def materials_save(args) -> dict:
    M.save_user_materials(args["user"])
    return materials_get()


# ================================================================================================== espacio de trabajo de proyectos (pantalla de inicio)
def _ws_meta_path(root: Path) -> Path:
    return root / ".steelconpro" / "meta.json"


def _ws_meta(root: Path) -> dict:
    f = _ws_meta_path(root)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"favorites": [], "recent": []}


def _ws_save_meta(root: Path, meta: dict):
    f = _ws_meta_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")


def _safe(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise ApiError("Ruta fuera del espacio de trabajo.")
    return p


def ws_default(_=None) -> dict:
    root = Path(os.environ.get("SCP_WORKSPACE") or Path.home() / "Documents" / "SteelConPro")
    root.mkdir(parents=True, exist_ok=True)
    return {"root": str(root)}


def _thumb_for(path: Path, root: Path):
    """PNG (base64) de la primera conexion de un proyecto, en cache junto al proyecto segun su fecha."""
    tdir = root / ".steelconpro" / "thumbs"
    tag = hashlib.md5(str(path).encode("utf-8")).hexdigest()[:12]
    key = f"{tag}_{int(path.stat().st_mtime)}.png"
    f = tdir / key
    if f.exists():
        return base64.b64encode(f.read_bytes()).decode("ascii")
    try:
        book = load_book(str(path))
        out = thumbnail({"connection": _dump(book[0]), "w": 360, "h": 220})["png"]
    except Exception:
        return ""
    tdir.mkdir(parents=True, exist_ok=True)
    for old in tdir.glob(f"{tag}_*.png"):
        old.unlink(missing_ok=True)
    f.write_bytes(base64.b64decode(out))
    return out


def ws_list(args) -> dict:
    """Carpetas y proyectos (.scp) del espacio de trabajo: nombre, carpeta, fecha, numero de conexiones y si es favorito."""
    root = Path(args["root"])
    root.mkdir(parents=True, exist_ok=True)
    meta = _ws_meta(root)
    folders, projects = [], []
    for d in sorted(root.rglob("*")):
        rel = d.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if d.is_dir():
            folders.append({"path": str(rel).replace(os.sep, "/"), "name": d.name, "parent": str(rel.parent).replace(os.sep, "/") if str(rel.parent) != "." else ""})
        elif d.suffix.lower() in (".scp", ".pbase"):
            st = d.stat()
            n, names, ok = 0, [], None
            try:
                data = json.loads(d.read_text(encoding="utf-8"))
                cons = data.get("conexiones") if isinstance(data, dict) else None
                n = len(cons) if cons is not None else 1
                names = [str(c.get("element", "")) for c in (cons or [data])][:6]
            except Exception:
                pass
            r = str(rel).replace(os.sep, "/")
            projects.append({"path": r, "name": d.stem, "folder": str(rel.parent).replace(os.sep, "/") if str(rel.parent) != "." else "", "modified": st.st_mtime,
                             "size": st.st_size, "connections": n, "elements": names, "favorite": r in meta.get("favorites", []),
                             "thumb": _thumb_for(d, root) if args.get("thumbs", True) else ""})
    return {"root": str(root), "folders": folders, "projects": projects, "recent": meta.get("recent", [])}


def ws_create_project(args) -> dict:
    root = Path(args["root"])
    folder = _safe(root, args.get("folder", ""))
    folder.mkdir(parents=True, exist_ok=True)
    name = "".join(ch for ch in args["name"].strip() if ch not in '\\/:*?"<>|') or "Proyecto"
    path = folder / f"{name}.scp"
    k = 2
    while path.exists():
        path = folder / f"{name} ({k}).scp"
        k += 1
    p = new_connection()
    p.name = args["name"].strip() or "Proyecto"
    p.date = datetime.date.today().isoformat()
    p.element = "CN-01"
    for kk in ("u_len", "u_force", "u_stress", "u_moment"):
        if kk in args:
            setattr(p, kk, args[kk])
    save_book(str(path), [p])
    return {"path": str(path), "rel": str(path.relative_to(root)).replace(os.sep, "/")}


def ws_create_folder(args) -> dict:
    root = Path(args["root"])
    d = _safe(root, (args.get("parent", "") + "/" + args["name"]).strip("/"))
    d.mkdir(parents=True, exist_ok=True)
    return {"ok": True}


def ws_rename(args) -> dict:
    root = Path(args["root"])
    src = _safe(root, args["path"])
    new = args["name"].strip()
    if not new:
        raise ApiError("Nombre vacio.")
    dst = src.with_name(new + (src.suffix if src.is_file() else ""))
    if dst.exists():
        raise ApiError("Ya existe uno con ese nombre.")
    src.rename(dst)
    meta = _ws_meta(root)
    old = args["path"]
    meta["favorites"] = [str(dst.relative_to(root)).replace(os.sep, "/") if f == old else f for f in meta.get("favorites", [])]
    _ws_save_meta(root, meta)
    return {"path": str(dst.relative_to(root)).replace(os.sep, "/")}


def ws_move(args) -> dict:
    root = Path(args["root"])
    src = _safe(root, args["path"])
    dst_dir = _safe(root, args.get("folder", ""))
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        raise ApiError("Ya existe uno con ese nombre en la carpeta de destino.")
    shutil.move(str(src), str(dst))
    return {"path": str(dst.relative_to(root)).replace(os.sep, "/")}


def ws_duplicate(args) -> dict:
    root = Path(args["root"])
    src = _safe(root, args["path"])
    dst = src.with_name(src.stem + " (copia)" + src.suffix)
    k = 2
    while dst.exists():
        dst = src.with_name(f"{src.stem} (copia {k})" + src.suffix)
        k += 1
    shutil.copy2(str(src), str(dst))
    return {"path": str(dst.relative_to(root)).replace(os.sep, "/")}


def ws_delete(args) -> dict:
    root = Path(args["root"])
    p = _safe(root, args["path"])
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True}


def ws_favorite(args) -> dict:
    root = Path(args["root"])
    meta = _ws_meta(root)
    fav = meta.setdefault("favorites", [])
    if args["path"] in fav:
        fav.remove(args["path"])
    else:
        fav.append(args["path"])
    _ws_save_meta(root, meta)
    return {"favorite": args["path"] in fav}


def ws_touch(args) -> dict:
    """Marca un proyecto como abierto recientemente."""
    root = Path(args["root"])
    meta = _ws_meta(root)
    rec = [x for x in meta.get("recent", []) if x != args["path"]]
    meta["recent"] = ([args["path"]] + rec)[:30]
    _ws_save_meta(root, meta)
    return {"ok": True}


def ws_import(args) -> dict:
    """Copia un archivo de proyecto (.scp / .pbase) al espacio de trabajo."""
    root = Path(args["root"])
    src = Path(args["source"])
    folder = _safe(root, args.get("folder", ""))
    folder.mkdir(parents=True, exist_ok=True)
    dst = folder / (src.stem + ".scp")
    k = 2
    while dst.exists():
        dst = folder / f"{src.stem} ({k}).scp"
        k += 1
    save_book(str(dst), load_book(str(src)))              # abre como conexion de nudo (placas base antiguas incluidas)
    return {"path": str(dst.relative_to(root)).replace(os.sep, "/")}


# ================================================================================================== plantillas del usuario
def tpl_list(_=None) -> dict:
    from . import templates as TPL
    return {"templates": TPL.list_templates(SP.CT_NODE)}


def tpl_save(args) -> dict:
    from . import templates as TPL
    p = _prj(args["connection"])
    path = TPL.save_template(p, args["name"], args.get("desc", ""), bool(args.get("loads", True)))
    return {"path": path}


def tpl_load(args) -> dict:
    from . import templates as TPL
    p = TPL.load_template(args["path"])
    return {"connection": _dump(p)}


def tpl_delete(args) -> dict:
    from . import templates as TPL
    TPL.delete_template(args["path"])
    return {"ok": True}


# ================================================================================================== registro de funciones
EXPORTED = {k: v for k, v in dict(globals()).items() if callable(v) and not k.startswith("_") and getattr(v, "__module__", "") == __name__ and not isinstance(v, type)}
