# -*- coding: utf-8 -*-
"""La placa base como una operacion mas del nudo (no hay modulo individual de placa base).

La operacion `OP_BASE` va en un extremo libre de un miembro (el miembro principal o cualquiera de los conectados).  El calculo es el motor de la
placa base de siempre (anclajes ACI 318, placa, soldadura, llave, rigidizadores y, si se corre, el analisis 3D por elementos finitos), que trabaja
sobre un `Project` «derivado» de la conexion:

  · los datos de la placa (placa, pernos, llave, rigidizadores, soldadura, concreto, cargas por combinacion y opciones del FEM) siguen en los
    bloques del `Project` de la conexion: `section.label` y `section.steel` se toman del miembro;
  · la placa queda perpendicular al eje del miembro (salvo la inclinacion `loads.tilt_x/y`, que es la del miembro respecto a la normal de la placa);
    `section.rotation` gira la placa respecto del perfil, igual que antes.

`derive` arma el proyecto del motor, `plate_transform` coloca la geometria de la placa en el nudo, y `unify` convierte una placa base de la version
anterior (archivos y plantillas) en una conexion de nudo con esta operacion.
"""
from __future__ import annotations
import copy
import math

import numpy as np

from .specs import (CT_BASEPLATE, CT_NODE, END_LABELS, OP_BASE, Nodo, Operation)

PROJECT_BLOCKS = ("section", "plate", "bolts", "lug", "stiff", "welds", "conc", "loads", "fea")


def base_member(nd: Nodo, op: Operation):
    """(nombre, Member | None) del miembro que lleva la placa; None si es el principal."""
    if op.member == nd.main_name or not op.member:
        return nd.main_name, None
    m = nd.member_named(op.member)
    return (op.member, m) if m is not None else (None, None)


def derive(prj, nd: Nodo = None, into=None):
    """Proyecto para el motor de la placa base: una copia de la conexion con `ctype` de placa base y el perfil del miembro que lleva la placa.
    Con `into` (un proyecto derivado anterior) se actualiza ese mismo objeto, para que sus resultados guardados en cache sigan siendo suyos."""
    nd = nd or prj.node
    op = nd.base_op()
    q = copy.deepcopy(prj) if into is None else into
    if into is not None:
        for k in PROJECT_BLOCKS + ("combos", "combo_idx", "name", "element", "author", "date", "metric", "u_len", "u_force", "u_stress", "u_moment"):
            setattr(q, k, copy.deepcopy(getattr(prj, k)))
    q.ctype = CT_BASEPLATE
    if op is not None:
        from . import nodal
        nc = nodal.base_combos(prj, nd)             # con casos de carga del nudo, las combinaciones de la placa salen del analisis nodal
        if nc:
            q.combos, q.combo_idx = nc, 0
            q.apply_combo(0)
    q.colweld_off = bool(op is not None and str(getattr(op, "col_weld", "")).startswith("No modelar"))       # el cordón columna-placa lo define otra operación
    if op is not None:
        name, m = base_member(nd, op)
        if m is None and name is not None:
            q.section.label, q.section.steel = nd.main_shape, nd.main_steel
        elif m is not None:
            q.section.label, q.section.steel = m.shape, m.steel
    return q


def _rz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def tilt_matrix(prj):
    from ..view3d import _rot_matrix
    return _rot_matrix(prj.loads.tilt_x, prj.loads.tilt_y)


def plate_transform(prj, E, A_in, sx, sy):
    """(O, F): coordenadas de placa (x, y, z) -> mundo: O + F·(x, y, z).
    E = punto del eje del miembro donde apoya en la placa (cara superior), A_in = eje del miembro desde la placa hacia adentro del miembro,
    (sx, sy) = ejes de su seccion con sx × sy = A_in.  La placa queda con su normal en A_in, girada `section.rotation` respecto del perfil y con la
    inclinacion `loads.tilt_x/y` entre el miembro y la normal."""
    Fm = np.column_stack([np.asarray(sx, float), np.asarray(sy, float), np.asarray(A_in, float)])
    F = Fm @ _rz(-float(prj.section.rotation)) @ tilt_matrix(prj).T
    cx, cy = float(prj.section.cx), float(prj.section.cy)
    O = np.asarray(E, float) - F @ np.array([cx, cy, float(prj.plate.tp)])
    return O, F


def plate_faces(prj, E, A_in, sx, sy):
    """Piezas de la placa base (sin el perfil, que ya lo dibuja el nudo) como caras en el mundo: [(etiqueta, caras, color, alfa)].  `prj` es el
    proyecto derivado."""
    from .. import view3d as V
    O, F = plate_transform(prj, E, A_in, sx, sy)
    out = []
    for part in V.geometry_faces(prj):
        tag = part[5] if len(part) > 5 else "other"
        if tag == "column":
            continue
        faces = [[tuple(O + F @ np.asarray(q, float)) for q in f] for f in part[1]]
        out.append((tag, faces, part[2], part[3]))
    return _heal_parts(out)


def _heal_parts(out):
    """Las caras heredadas (view3d) no forman una superficie cerrada ni estan orientadas (la placa viene en tapas, borde y paredes de agujeros por
    separado): se unen por etiqueta, se cierran las uniones en T y se orientan hacia afuera, y se devuelven con su color por parte."""
    from .fem.prismmesh import heal_soup
    res, by_tag = [], {}
    for i, (tag, faces, color, alpha) in enumerate(out):
        by_tag.setdefault(tag, []).append(i)
    done = {}
    for tag, idxs in by_tag.items():
        soup, grp = [], []
        for i in idxs:
            soup += out[i][1]
            grp += [i] * len(out[i][1])
        try:
            fs, gs = heal_soup(soup, grp)
        except Exception:                                   # nunca debe impedir armar el modelo
            fs, gs = soup, grp
        for i in idxs:
            done[i] = [f for f, g in zip(fs, gs) if g == i]
    for i, (tag, faces, color, alpha) in enumerate(out):
        res.append((tag, done.get(i, faces), color, alpha))
    return res


def end_of_member(nd: Nodo, op: Operation, axes: dict, frames: dict):
    """(E, A_in, sx, sy) del extremo libre del miembro que lleva la placa, o None si no se puede colocar."""
    from . import assembly as AS
    name, m = base_member(nd, op)
    if name is None:
        return None
    if m is None:                                          # el principal: lado − (op.end = −1) o + (op.end = +1)
        A, msx, msy = AS.main_frame(nd)
        lneg, lpos = nd.lengths()
        if lneg + lpos < 1.0:
            lneg = lpos = 24.0
        if op.end >= 0:
            if lpos <= 1e-9:
                return None
            return A * lpos, -A, msx, -msy
        if lneg <= 1e-9:
            return A * 0.0, A, msx, msy
        return A * (-lneg), A, msx, msy
    if name not in axes:
        return None
    start, end, dirv = axes[name]
    _, sx, sy = frames[name]
    return np.asarray(end, float), -np.asarray(dirv, float), sx, -sy


# ================================================================== verificaciones
def add_checks(prj, nd: Nodo, R, rec, fem_map=None):
    """Agrega a `R` (resultado del nudo) las verificaciones de la placa base de todas las combinaciones de carga de la placa: se muestran las de la
    combinacion que gobierna, y la memoria de calculo de esa combinacion se agrega a `rec`.  `fem_map` = {combinacion: Fem3D vigente} del analisis 3D
    de la placa base (si se corrio)."""
    from ..solver import solve
    from ..design import Check
    op = nd.base_op()
    if op is None:
        return
    name, m = base_member(nd, op)
    if name is None:
        R.warnings.append(f"Placa base: el miembro «{op.member}» no existe.")
        return
    bp = derive(prj, nd)
    best, rows = None, []
    for i, cb in enumerate(bp.combo_list()):
        Ri = solve(bp.with_combo(i), True, fem=(fem_map or {}).get(i))
        rows.append({"name": f"Placa base — {cb.name}", "ratio": Ri.max_ratio, "ok": Ri.ok, "pending": False,
                     "gov": Ri.governing.title if Ri.governing else "-"})
        if best is None or Ri.max_ratio > best[0].max_ratio:
            best = (Ri, i, cb.name)
    Rb, ib, cname = best
    multi = len(rows) > 1
    oi = next((k for k, x in enumerate(nd.operations) if x is op), 0)
    for c in Rb.checks:
        c2 = Check(f"bp_{c.key}", f"[Placa base — {name}] {c.title}" + (f"  ({cname})" if multi and not c.skip else ""), c.demand, c.capacity, c.unit,
                   c.ref, c.note, c.skip, c.steps)
        c2.group = f"{oi + 1}. {op.kind} — {name}"
        R.checks.append(c2)
    for w in Rb.warnings:
        if w.startswith("REALIZAR ANALISIS 3D"):                    # el aviso del motor remite a F8 de la placa base; aqui lo da la nota de abajo
            continue
        R.warnings.append(("** " if w.startswith("**") else "") + "Placa base: " + w.lstrip("* ").strip())
    if Rb.fem is None:
        R.warnings.append("Placa base: verificada con el calculo cerrado (DG1 + ACI 318); el analisis 3D por elementos finitos de la placa base se corre aparte "
                          "(pestaña FEM).")
    if Rb.rec is not None and rec is not None:
        rec.section(f"OPERACION: PLACA BASE — {name}  (combinación {cname})")
        rec.sections.extend(Rb.rec.sections)
    R.combo_rows = list(R.combo_rows) + rows
    gov = max(range(len(R.combo_rows)), key=lambda k: R.combo_rows[k]["ratio"]) if R.combo_rows else 0
    R.combo_gov = gov


# ================================================================== archivos de la version anterior (placa base independiente)
def unify(p):
    """Convierte una conexion de placa base de la version anterior en una conexion de nudo: el miembro principal es la columna del perfil de la
    placa (vertical, o inclinada como estaba; nace en la placa) con la operacion de placa base.  Los datos de la placa se conservan tal cual."""
    from .assembly import frame, main_frame, axis_dir
    if p.ctype != CT_BASEPLATE:
        return p
    from ..view3d import _rot_matrix
    s = p.section
    R = _rot_matrix(p.loads.tilt_x, p.loads.tilt_y)
    Az = R @ np.array([0.0, 0.0, 1.0])
    az = math.degrees(math.atan2(Az[1], Az[0])) % 360.0 if math.hypot(Az[0], Az[1]) > 1e-9 else 0.0
    el = math.degrees(math.asin(max(-1.0, min(1.0, float(Az[2])))))
    nd = Nodo(main_name="Columna", main_shape=s.label, main_steel=s.steel, main_az=az, main_el=el, main_end=END_LABELS[2],
              main_len_neg=0.0, main_len_pos=max(60.0, 3.0 * float(s.shape().d)))
    # giro de la seccion que deja la placa como estaba en el mundo (plate_transform = identidad)
    Fm_target = R @ _rz(float(s.rotation))
    pref = [0, 0, 1] if abs(Az[2]) < 0.995 else [1, 0, 0]
    A0, sx0, sy0 = frame(Az, pref, 0.0)
    tx = Fm_target[:, 0]
    nd.main_roll = math.degrees(math.atan2(float(np.dot(tx, sy0)), float(np.dot(tx, sx0)))) % 360.0
    if nd.main_roll > 180.0:
        nd.main_roll -= 360.0
    nd.operations = [Operation(kind=OP_BASE, member=nd.main_name, end=-1)]
    p.node = nd
    p.ctype = CT_NODE
    return p


# ================================================================== cordones modelados (columna-placa y rigidizadores-placa/columna)
def _wkind(wtype: str) -> str:
    from .specs import WELD_TYPES
    t = str(wtype or "")
    return WELD_TYPES[1] if t.startswith("CJP") else WELD_TYPES[2] if t.startswith("PJP") else WELD_TYPES[0]


def weld_lines(bpd, E, A_in, sx, sy, col_part: str, with_column: bool = True):
    """Cordones de la placa base como geometria del nudo: [(nombre, A, B, p0, p1, nA, nB, cateto, tipo, grupo)] en coordenadas del mundo.
    · columna -> placa: por las paredes del perfil (alas / alma / cara de tubo), a los dos lados si la especificación lo pide (`both_sides`), con el
      cateto y el tipo del bloque `welds`; solo si `with_column` (opción «Modelar aquí»);
    · rigidizador -> placa y rigidizador -> columna: a los dos lados de cada pletina, con `stiff.weld_size`.
    La placa base y los rigidizadores no son piezas de prismas: sus nombres («Placa base», «stiff») son elementos virtuales para el revisor."""
    from .. import geometry as G
    from ..weld3d import _walls
    O, F = plate_transform(bpd, E, A_in, sx, sy)
    tp = float(bpd.plate.tp)
    up = F[:, 2]

    def W(x, y, z):
        return O + F @ np.array([x, y, z], float)

    def D(x, y):                                                  # dirección horizontal de la placa en el mundo
        return F @ np.array([x, y, 0.0], float)
    out = []
    if with_column:
        walls = _walls(bpd)
        pts = [q for (_n, a, b, _t, _s) in walls for q in (a, b)]
        cx, cy = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)) if pts else (0.0, 0.0)
        for (name, (x1, y1), (x2, y2), t, spec) in walls:
            if str(spec.wtype).startswith("Sin") or spec.size <= 0:
                continue
            L = math.hypot(x2 - x1, y2 - y1)
            if L < 1e-6:
                continue
            nx, ny = -(y2 - y1) / L, (x2 - x1) / L
            mx, my = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
            sg_out = 1.0 if (mx - cx) * nx + (my - cy) * ny >= -1e-9 else -1.0
            sides = (sg_out, -sg_out) if getattr(spec, "both_sides", True) else (sg_out,)
            for k, sg in enumerate(sides):
                ox, oy = nx * sg * t / 2.0, ny * sg * t / 2.0
                out.append((f"Columna-Placa base {name}{'' if k == 0 else ' int.'}", col_part, "Placa base", tuple(W(x1 + ox, y1 + oy, tp)), tuple(W(x2 + ox, y2 + oy, tp)),
                            tuple(D(nx * sg, ny * sg)), tuple(up), float(spec.size), _wkind(spec.wtype), "Cordón columna-placa"))
    st = bpd.stiff
    if st.enabled and st.count > 0 and not bpd.section.generic:
        prof = st.outline()[:-1]
        u0 = min(q[0] for q in prof)
        v0 = min(q[1] for q in prof)
        col_v = [q[1] for q in prof if abs(q[0] - u0) < 1e-9]
        base_u = [q[0] for q in prof if abs(q[1] - v0) < 1e-9]
        w = float(st.weld_size)
        for i, (x1, y1, x2, y2) in enumerate(G.stiffener_lines(bpd)):
            Ls = math.hypot(x2 - x1, y2 - y1)
            if Ls < 1e-6:
                continue
            ux, uy = (x2 - x1) / Ls, (y2 - y1) / Ls
            tx, ty = -uy, ux
            for k, sg in enumerate((1.0, -1.0)):
                ox, oy = tx * sg * st.t / 2.0, ty * sg * st.t / 2.0
                na = D(tx * sg, ty * sg)
                ub0, ub1 = min(base_u), max(base_u)
                out.append((f"Rigidizador {i + 1}-Placa base {k + 1}", "stiff", "Placa base", tuple(W(x1 + ux * ub0 + ox, y1 + uy * ub0 + oy, tp)),
                            tuple(W(x1 + ux * ub1 + ox, y1 + uy * ub1 + oy, tp)), tuple(na), tuple(up), w, _wkind("Filete"), "Cordón rigidizador-placa"))
                vc0, vc1 = min(col_v), max(col_v)
                out.append((f"Rigidizador {i + 1}-Columna {k + 1}", "stiff", col_part, tuple(W(x1 + ox, y1 + oy, tp + vc0)), tuple(W(x1 + ox, y1 + oy, tp + vc1)),
                            tuple(na), tuple(D(ux, uy)), w, _wkind("Filete"), "Cordón rigidizador-columna"))
    return out
