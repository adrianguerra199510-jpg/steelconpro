# -*- coding: utf-8 -*-
"""
Lectura de resultados de CalculiX (.frd) y dibujo 3D dentro del programa.

Del .frd se sacan los desplazamientos nodales y el tensor de esfuerzos; de la
malla (.inp de Gmsh) las coordenadas y los tetraedros.  Para dibujar no hace
falta el volumen completo: basta la PIEL del solido, es decir las caras de
tetraedro que pertenecen a un solo elemento.  Eso se colorea con el campo
elegido y se dibuja con matplotlib en 3D.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import math
import re

import numpy as np


@dataclass
class Result3D:
    ok: bool = False
    msg: str = ""
    nodes: dict = field(default_factory=dict)      # id -> (x, y, z)
    tris: list = field(default_factory=list)       # caras exteriores (n1,n2,n3)
    disp: dict = field(default_factory=dict)       # id -> (ux, uy, uz)
    vm: dict = field(default_factory=dict)         # id -> von Mises
    stress: dict = field(default_factory=dict)     # id -> (sx,sy,sz,sxy,syz,szx)
    forc: dict = field(default_factory=dict)       # id -> reaccion (RF)
    n_nodes: int = 0
    n_elems: int = 0
    umax: float = 0.0
    vmmax: float = 0.0
    rf_sum: tuple = (0.0, 0.0, 0.0)
    vm_avg: dict = None                             # ver smoothed_plate_vm
    elems: list = field(default_factory=list)       # nodos de cada elemento solido (para separar piezas)
    parts: dict = field(default_factory=dict)       # pieza -> caras exteriores de esa pieza (ver classify_parts)
    part_avg: dict = field(default_factory=dict)    # pieza -> von Mises promediado (ver smoothed_part_vm)


# ============================================================ malla (.inp)
def read_mesh_inp(path: str):
    """Devuelve (nodos, elementos) del .inp que escribe Gmsh."""
    nodes, elems = {}, []
    mode, etype = None, None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            t = ln.strip()
            if not t:
                continue
            up = t.upper()
            if up.startswith("*NODE"):
                mode = "N"; continue
            if up.startswith("*ELEMENT"):
                mode = "E"
                etype = ("C3D10" if "C3D10" in up else
                         ("C3D4" if "C3D4" in up else None))
                continue
            if t.startswith("*"):
                mode = None; continue
            v = [x.strip() for x in t.rstrip(",").split(",") if x.strip()]
            if mode == "N" and len(v) >= 4:
                nodes[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]))
            elif mode == "E" and etype and len(v) >= 5:
                elems.append([int(x) for x in v[1:]])
    return nodes, elems


def skin(elems):
    """Caras exteriores: las que aparecen en un solo tetraedro.

    Con tetraedros de 10 nodos solo se usan los 4 vertices; para dibujar la
    piel eso es suficiente y evita triangulos curvos."""
    faces = {}
    for e in elems:
        a, b, c, d = e[0], e[1], e[2], e[3]
        for f in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            k = tuple(sorted(f))
            faces[k] = faces.get(k, 0) + 1
    return [k for k, n in faces.items() if n == 1]


# ============================================================ resultados (.frd)
def read_frd(path: str):
    """Devuelve (disp, stress) como dicts nodo -> tupla."""
    disp, stress, forc = {}, {}, {}
    block = None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            s = ln.rstrip("\n")
            if len(s) > 5 and s[1:3] == "-4":
                name = s[5:13].strip().upper()
                block = ("U" if name.startswith("DISP") else
                         "S" if name.startswith("STRESS") else
                         "F" if name.startswith("FORC") else None)
                continue
            if s.startswith(" -3"):
                block = None
                continue
            if block and s.startswith(" -1"):
                try:
                    nid = int(s[3:13])
                except ValueError:
                    continue
                rest = s[13:]
                vals = []
                for i in range(0, len(rest), 12):
                    chunk = rest[i:i + 12].strip()
                    if not chunk:
                        continue
                    try:
                        vals.append(float(chunk))
                    except ValueError:
                        pass
                if block == "U" and len(vals) >= 3:
                    disp[nid] = tuple(vals[:3])
                elif block == "S" and len(vals) >= 6:
                    stress[nid] = tuple(vals[:6])
                elif block == "F" and len(vals) >= 3:
                    forc[nid] = tuple(vals[:3])
    return disp, stress, forc


def read_peeq(path: str) -> dict:
    """Deformacion plastica equivalente por nodo (bloque PE del .frd), o {} si el analisis fue elastico."""
    pe, blk = {}, False
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if len(ln) > 5 and ln[1:3] == "-4":
                blk = ln[5:13].strip().upper() == "PE"
                continue
            if ln.startswith(" -3"):
                blk = False
                continue
            if blk and ln.startswith(" -1"):
                try:
                    pe[int(ln[3:13])] = float(ln[13:25])
                except ValueError:
                    pass
    return pe


def clip_vm_to_yield(res, prj) -> int:
    """Con acero elasto-plastico el esfuerzo en los puntos de integracion no pasa de φ·Fy, pero CalculiX lo extrapola
    a los nodos y ahi puede quedar por encima (sobre todo en esquinas con singularidad).  Para mostrar un campo acotado
    se recorta el von Mises nodal en φ·Fy del acero de la pieza a la que pertenece cada nodo
    (nodos compartidos entre piezas: el mayor).  El original queda en res.vm_raw.  Devuelve cuantos nodos se recortaron."""
    tp = prj.plate.tp
    caps = {"plate": prj.plate.mat().Fy, "washer": prj.plate.mat().Fy, "column": prj.section.mat().Fy,
            "stiff": prj.stiff.mat().Fy, "lug": prj.lug.mat().Fy}
    N = res.nodes
    cap = {}
    for e in res.elems:
        c = e[:4]
        xc = sum(N[n][0] for n in c) / 4.0
        yc = sum(N[n][1] for n in c) / 4.0
        zc = sum(N[n][2] for n in c) / 4.0
        if zc < 0:
            k = "lug"
        elif zc < tp:
            k = "plate"
        elif washer_elements(prj, xc, yc, zc):
            k = "washer"
        elif _covered_by_profile(prj, xc, yc):
            k = "column"
        else:
            k = "stiff"
        f = 0.9 * caps[k]
        for n in e:
            if f > cap.get(n, 0.0):
                cap[n] = f
    res.vm_raw = dict(res.vm)
    n_clip = 0
    for n, v_ in res.vm.items():
        c_ = cap.get(n)
        if c_ is not None and v_ > c_:
            res.vm[n] = c_
            n_clip += 1
    res.vmmax = max(res.vm.values(), default=0.0)
    return n_clip


def part_peeq(res, prj, radius: float) -> dict:
    """PEEQ por pieza -> {pieza: {"raw": (v, x, y, z), "avg": (v, x, y, z)}}.
    raw = maximo nodal; avg = maximo del promedio de los nodos de la pieza dentro de `radius` (no depende de la
    singularidad de un solo nodo, igual que el von Mises promediado)."""
    from scipy.spatial import cKDTree
    pe = getattr(res, "peeq", None)
    out = {}
    if not pe:
        return out
    for part, tris in res.parts.items():
        ids_ = sorted({n for t in tris for n in t if n in pe and n in res.nodes})
        if not ids_:
            continue
        P = np.array([res.nodes[n] for n in ids_], float)
        V = np.array([pe[n] for n in ids_], float)
        i = int(V.argmax())
        tree = cKDTree(P)
        sm = np.array([V[ix].mean() for ix in tree.query_ball_point(P, radius)])
        j = int(sm.argmax())
        out[part] = {"raw": (float(V[i]), *map(float, P[i])), "avg": (float(sm[j]), *map(float, P[j]))}
    return out


def plate_peeq(res, tp: float, tol: float = 1e-4):
    """(PEEQ maximo en la placa [fraccion], x, y, z) o None."""
    pe = getattr(res, "peeq", None)
    if not pe:
        return None
    best = None
    for n, v in pe.items():
        xyz = res.nodes.get(n)
        if xyz is None or xyz[2] > tp + tol:
            continue
        if best is None or v > best[0]:
            best = (v, xyz[0], xyz[1], xyz[2])
    return best


def von_mises(sx, sy, sz, sxy, syz, szx):
    return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                     + 3.0 * (sxy ** 2 + syz ** 2 + szx ** 2))


def load_results(mesh_inp: str, frd: str) -> Result3D:
    r = Result3D()
    try:
        nodes, elems = read_mesh_inp(mesh_inp)
    except Exception as e:
        r.msg = f"No se pudo leer la malla: {e}"
        return r
    if not nodes or not elems:
        r.msg = "La malla no contiene nodos o elementos solidos."
        return r
    try:
        disp, stress, forc = read_frd(frd)
    except Exception as e:
        r.msg = f"No se pudo leer el .frd: {e}"
        return r
    if not disp:
        r.msg = ("El .frd no contiene desplazamientos. Revise que CalculiX haya "
                 "terminado sin errores (archivo .sta / .dat).")
        return r

    r.nodes = nodes
    r.tris = skin(elems)
    r.elems = elems
    r.disp = disp
    r.vm = {n: von_mises(*s) for n, s in stress.items()}
    r.stress = stress
    r.forc = forc
    r.n_nodes, r.n_elems = len(nodes), len(elems)
    r.umax = max((math.sqrt(sum(c * c for c in u)) for u in disp.values()),
                 default=0.0)
    r.vmmax = max(r.vm.values(), default=0.0)
    if forc:
        r.rf_sum = tuple(sum(v[i] for v in forc.values()) for i in range(3))
    r.ok = True
    r.msg = (f"{r.n_nodes:,} nodos y {r.n_elems:,} tetraedros.  "
             f"|U| max = {r.umax:.5f} in ;  von Mises max = {r.vmmax:.2f} ksi")
    return r


# ==================================================================== dibujo
def set_aspect(ax, aspect, zoom=0.72, pts=None):
    """Proporciones reales del modelo + zoom inicial conservador (luego fit_to_axes lo ajusta).
    `pts`: puntos (N, 3) del modelo, para encuadrar lo que realmente se dibuja."""
    ax._pb_aspect, ax._pb_zoom = aspect, zoom
    if pts is not None and len(pts) > 6000:
        pts = pts[:: max(1, len(pts) // 6000)]
    ax._pb_pts = None if pts is None else np.asarray(pts, dtype=float)
    try:
        ax.set_box_aspect(aspect, zoom=zoom)
    except TypeError:
        ax.set_box_aspect(aspect)


def fit_to_axes(ax, margin=0.05):
    """Encuadra el modelo dentro del area del grafico: ocupa el 90 % del ancho o del alto disponible (el
    que limite) y queda centrado, sin cortarse, para cualquier tamano de ventana y cualquier vista.

    Se proyectan los puntos del modelo (o las 8 esquinas de su caja) a pixeles con la transformacion real
    del eje y se calcula el zoom con que el mayor alejamiento del centro cabe en la mitad del area:
    ancho y alto por separado, sin suponer que el area de dibujo es cuadrada.  Es iterativo (2 pasadas) y
    el zoom se calcula de forma absoluta, asi que no se acumula al redimensionar."""
    asp = getattr(ax, "_pb_aspect", None)
    if asp is None:
        return
    from mpl_toolkits.mplot3d import proj3d
    try:
        pts = getattr(ax, "_pb_pts", None)
        if pts is None:
            (x0, x1), (y0, y1), (z0, z1) = ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()
            pts = np.array([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=float)
        for _ in range(2):
            ax.set_box_aspect(asp, zoom=ax._pb_zoom)
            ax.apply_aspect()                # area de dibujo vigente para el tamano actual de la ventana
            X, Y, _z = proj3d.proj_transform(pts[:, 0], pts[:, 1], pts[:, 2], ax.get_proj())
            px = ax.transData.transform(np.column_stack([X, Y]))
            # area DISPONIBLE = todo el rectangulo asignado al eje (no el cuadrado que usa el eje 3D para
            # dibujar): los artistas se dibujan sin recorte, asi el modelo puede usar todo el ancho
            (bx0, by0), (bx1, by1) = ax.figure.transFigure.transform(ax.get_position(original=True).get_points())
            bw, bh = bx1 - bx0, by1 - by0
            if bw <= 1 or bh <= 1:
                return
            cx, cy = 0.5 * (bx0 + bx1), 0.5 * (by0 + by1)
            ex = max(np.abs(px[:, 0] - cx).max(), 1e-9)
            ey = max(np.abs(px[:, 1] - cy).max(), 1e-9)
            k = min((1 - 2 * margin) * 0.5 * bw / ex, (1 - 2 * margin) * 0.5 * bh / ey)
            ax._pb_zoom = float(np.clip(ax._pb_zoom * k, 0.05, 6.0))
        ax.set_box_aspect(asp, zoom=ax._pb_zoom)
    except Exception:
        pass


def _soft_cmap(diverging=False):
    """Paletas suaves para los resultados 3D (azul -> verde -> amarillo -> coral)."""
    from matplotlib.colors import LinearSegmentedColormap
    cols = (["#4a7fc1", "#f5f5f2", "#e2705f"] if diverging else
            ["#4a7fc1", "#63b7c4", "#9fd3a0", "#f1e08a", "#f4b26b", "#e2705f"])
    return LinearSegmentedColormap.from_list("pb_suave", cols, N=256)


def plot3d(ax, res: Result3D, prj, field="vm", scale=0.0, shrink_tris=12000, tag_max=True, part="all", bolts=None, loads=False):
    """Dibuja la piel del solido coloreada por el campo elegido.  `part`: all | plate | column | stiff | lug."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    ax.clear()
    if res is None or not res.ok:
        ax.text2D(0.5, 0.5, "Sin resultados 3D.\nUse  Calculo > Analisis 3D.",
                  ha="center", va="center", transform=ax.transAxes, fontsize=11,
                  color="#777777")
        ax.set_axis_off()
        return None

    u = prj.units()
    kl, ks = u.fl, u.fs

    tris = res.tris if part == "all" else res.parts.get(part, [])
    if not tris:
        ax.text2D(0.5, 0.5, f"Sin elementos de tipo '{PART_LABELS.get(part, part)}' en este modelo.",
                  ha="center", va="center", transform=ax.transAxes, fontsize=11, color="#777777")
        ax.set_axis_off()
        return None
    used = sorted({n for t in tris for n in t})
    ids = used
    idx = {n: i for i, n in enumerate(ids)}
    P = np.array([res.nodes[n] for n in ids], dtype=float)
    if scale > 0 and res.disp:
        D = np.array([res.disp.get(n, (0, 0, 0)) for n in ids], dtype=float)
        P = P + scale * D

    if field == "u":
        val = np.array([math.sqrt(sum(c * c for c in res.disp.get(n, (0, 0, 0))))
                        for n in ids])
        val = val / kl
        title, cmap, unit = "Desplazamiento |U|", _soft_cmap(), u.L
    elif field == "uz":
        val = np.array([res.disp.get(n, (0, 0, 0))[2] for n in ids]) / kl
        title, cmap, unit = "Desplazamiento vertical Uz", _soft_cmap(True), u.L
    else:
        val = np.array([res.vm.get(n, 0.0) for n in ids]) / ks
        title, cmap, unit = "Esfuerzo de von Mises", _soft_cmap(), u.S

    if len(tris) > shrink_tris:                 # muestreo para que la vista fluya
        step = max(1, len(tris) // shrink_tris)
        tris = tris[::step]

    verts = [[P[idx[a]] / kl, P[idx[b]] / kl, P[idx[c]] / kl] for a, b, c in tris]
    face_val = np.array([(val[idx[a]] + val[idx[b]] + val[idx[c]]) / 3.0
                         for a, b, c in tris])

    import matplotlib.cm as cm
    from matplotlib.colors import Normalize
    vmin, vmax = float(np.min(face_val)), float(np.max(face_val))
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    norm = Normalize(vmin=vmin, vmax=vmax)
    mapper = cm.ScalarMappable(norm=norm, cmap=cmap)

    coll = Poly3DCollection(verts, facecolors=mapper.to_rgba(face_val),
                            edgecolors=(0, 0, 0, 0.06), linewidths=0.1)
    coll.set_clip_on(False)                     # el eje 3D recorta a un cuadrado: sin recorte usa todo el ancho
    ax.add_collection3d(coll)

    Pm = P / kl
    load_items = []
    if loads:
        load_items, lpts = load_arrows(prj, kl, ztop=max(c_[2] for c_ in res.nodes.values()))
        Pe = np.vstack([Pm, np.array(lpts)])
    else:
        Pe = Pm
    mins, maxs = Pe.min(axis=0), Pe.max(axis=0)
    # proporciones reales y margen minimo: el modelo llena el lienzo y queda
    # centrado; la rueda del mouse hace zoom sobre el centro
    spans = np.maximum(maxs - mins, 1e-6)
    pad = 0.03 * float(spans.max())
    ax.set_xlim(mins[0] - pad, maxs[0] + pad)
    ax.set_ylim(mins[1] - pad, maxs[1] + pad)
    ax.set_zlim(mins[2] - pad, maxs[2] + pad)
    set_aspect(ax, tuple(float(v) + 2 * pad for v in spans), pts=Pe)
    if load_items:
        draw_loads(ax, load_items)
    if tag_max and len(val):
        try:
            ax.computed_zorder = False
        except Exception:
            pass
        k = int(np.argmax(val))
        mx, my_, mz = Pm[k]
        # el promediado se calculo sobre la placa: vale para el conjunto y para la placa
        avg = None
        plastic = bool(getattr(res, "peeq", None))
        if field == "vm" and not plastic:
            avg = (res.vm_avg if part in ("all", "plate") else res.part_avg.get(part))
        if avg:                               # maximo PROMEDIADO (converge con la malla)
            mx, my_, mz = avg["x"] / kl, avg["y"] / kl, avg["z"] / kl
        ax.scatter([mx], [my_], [mz], s=170, color="#d62728", marker="*", edgecolors="black",
                   linewidths=0.8, depthshade=False, zorder=20, clip_on=False)
        lbl = {"vm": "Esfuerzo maximo", "u": "Desplazamiento maximo",
               "uz": "Uz maximo"}.get(field, "Maximo")
        if avg:
            txt = (f"Esfuerzo maximo (promediado, r = {avg['radius'] / kl:.2g} {u.L}) = "
                   f"{avg['vm'] / ks:.4g} {unit}\npico puntual {avg['vm_point'] / ks:.4g} {unit} "
                   f"(depende de la malla)"
                   + ("" if part in ("all", "plate") else
                      "\nReferencia: la singularidad en el extremo del rigidizador persiste;\n"
                      "la malla rapida subestima ~15 %. No usar para verificar"))
        else:
            txt = (f"{lbl}" + (f" — {PART_LABELS[part]}" if part != "all" else "") + f" = {val[k]:.4g} {unit}"
                   + ("   (pico puntual: depende de la malla)" if field == "vm" else f"   (nodo {ids[k]})"))
        if plastic:
            # acero elasto-plastico: el esfuerzo ya esta acotado, solo se reporta el punto maximo, bajo la escala
            ax.figure.text(0.885, 0.15, f"{lbl.replace(' maximo', '')}\nmaximo\n{val[k]:.4g} {unit}", fontsize=9,
                           color="#7a1010", fontweight="bold", ha="left", va="top",
                           bbox=dict(boxstyle="round,pad=0.3", fc="#fff3e0", ec="#d62728", lw=1.0))
        else:
            ax.text2D(0.02, 0.12, txt,
                      transform=ax.transAxes, fontsize=9, color="#7a1010", fontweight="bold",
                      va="bottom", bbox=dict(boxstyle="round,pad=0.35", fc="#fff3e0", ec="#d62728", lw=1.0))
    if bolts and part == "plate":
        # una etiqueta por anclaje (P# y traccion): el perno mas exigido va en rojo, igual que en la tabla
        zt = float(Pm[:, 2].max()) + 0.02 * float(spans.max())
        Tmax = max(b[3] for b in bolts)
        for kb, bx, by, T in bolts:
            hot = T >= Tmax - 1e-9 and Tmax > 1e-9
            ax.text(bx / kl, by / kl, zt, f"P{kb}\n{u.fmt('F', T)}", ha="center", va="bottom", fontsize=8,
                    fontweight="bold" if hot else "normal", color="white" if hot else "#08306b", zorder=30,
                    bbox=dict(boxstyle="round,pad=0.25", fc="#d62728" if hot else "#ffffffd9",
                              ec="#d62728" if hot else "#08306b", lw=0.9))
            ax.scatter([bx / kl], [by / kl], [zt], s=14, color="#d62728" if hot else "#08306b",
                       depthshade=False, zorder=29, clip_on=False)
        ax.text2D(0.02, 0.04, f"Etiquetas: P# y traccion del perno ({u.F}); en rojo, el mas exigido",
                  transform=ax.transAxes, fontsize=8, color="#444444", va="bottom")
    ax.set_axis_off()                     # sin ejes ni reglas
    ax.set_title(f"{title}  ({unit})" + (f" — {PART_LABELS[part]}" if part != "all" else "")
                 + (f"   —  deformada ×{scale:g}" if scale > 0 else ""),
                 fontsize=9, loc="left")
    mapper.set_array(face_val)
    return mapper


# ============================================================ solo geometria
def _bar_faces(p0, p1, r):
    """Prisma de seccion cuadrada (lado 2r) a lo largo del segmento p0-p1: caras como cuadrilateros."""
    a, b = np.array(p0, float), np.array(p1, float)
    ax_ = b - a
    n = np.linalg.norm(ax_)
    if n < 1e-9:
        return []
    ax_ = ax_ / n
    ref = np.array([0.0, 0.0, 1.0]) if abs(ax_[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u_ = np.cross(ax_, ref); u_ /= np.linalg.norm(u_)
    w_ = np.cross(ax_, u_)
    ring = [(u_ * sx + w_ * sy) * r for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    pa = [tuple(a + q) for q in ring]
    pb = [tuple(b + q) for q in ring]
    f = [[pa[i], pa[(i + 1) % 4], pb[(i + 1) % 4], pb[i]] for i in range(4)]
    f += [pa, pb]
    return f


# ======================================================================== cargas
C_PU, C_V, C_M = "#c0392b", "#1d4ed8", "#7c3aed"


def load_arrows(prj, kl, ztop=None):
    """Flechas de las cargas de la combinacion activa, en el sistema de la placa (ejes de la columna si no esta inclinada).
    -> (lista de elementos a dibujar, puntos para el encuadre).  Coordenadas ya divididas por kl."""
    L = prj.loads if (prj.loads.tilted and ztop is None) else prj.cloads      # inclinada: las cargas se dan en ejes de la columna y asi se dibujan
    if not all(np.isfinite(x) for x in (L.Pu, L.Mux, L.Muy, L.Vux, L.Vuy)):
        return [], []                           # cargas invalidas: no se dibujan flechas
    u = prj.units()
    s = prj.section.shape()
    N, B = (prj.plate.Dp, prj.plate.Dp) if prj.plate.shape == "Circular" else (prj.plate.N, prj.plate.B)
    size = 1.25 * max(N, B)
    pr = "'" if (prj.loads.tilted and ztop is None) else ""          # columna inclinada: notacion en ejes de la columna (x', y', z')
    H = max(3.0 * s.d, 12.0)
    from . import geometry as _G
    bw, bh = _G.profile_bbox(prj)
    R = _rot_matrix(prj.loads.tilt_x, prj.loads.tilt_y)
    cx_, cy_ = _G.col_shift(prj)                  # la columna puede estar descentrada respecto a la placa
    T = np.array(R @ np.array([0.0, 0.0, H])) + np.array([cx_, cy_, prj.plate.tp])
    if ztop is not None:                          # en los resultados el perfil tiene la altura del modelo (vertical)
        T = np.array([cx_, cy_, float(ztop)])
        R = np.eye(3)
    ex, ey, ez = R[:, 0], R[:, 1], R[:, 2]        # ejes de la columna (inclinada o no) en el sistema de la placa
    items, pts = [], []

    def arrow(tail, head, color, label, far):
        a_, b_ = np.array(tail) / kl, np.array(head) / kl
        items.append(("arrow", a_, b_, color, label, np.array(far) / kl))
        pts.extend([a_, b_])

    F = [abs(L.Pu), abs(L.Vux), abs(L.Vuy)]
    fmax = max(F) if max(F) > 1e-9 else 1.0

    def ln(v):                                   # largo creciente con la carga pero comprimido (raiz): el cortante no
        return size * (0.55 + 0.45 * (abs(v) / fmax) ** 0.4)       # queda diminuto junto a una axial muy grande

    if abs(L.Pu) > 1e-9:
        l_ = ln(L.Pu)
        if L.Pu > 0:                              # compresion: la flecha empuja hacia abajo sobre la columna
            tail = T + ez * l_                    # la flecha sigue el eje de la columna
            arrow(tail, T, C_PU, f"Pu{pr} = {u.q('F', L.Pu)} (compresion" + (", a lo largo de la columna)" if pr else ")"), tail)
        else:                                     # traccion: tira hacia arriba
            head = T + ez * l_
            arrow(T, head, C_PU, f"Pu{pr} = {u.q('F', abs(L.Pu))} (traccion" + (", a lo largo de la columna)" if pr else ")"), head)
    for comp, name, vec, hw_ in ((L.Vux, "Vux" + pr, ex, 0.5 * bw), (L.Vuy, "Vuy" + pr, ey, 0.5 * bh)):
        if abs(comp) > 1e-9:
            l_ = ln(comp)
            sg = np.sign(comp)
            hw = hw_
            tip = T - vec * sg * hw                   # la punta toca la cara de la columna sobre la que empuja
            tail = tip - vec * sg * l_
            arrow(tail, tip, C_V, f"{name} = {u.q('F', comp)}", tail)
    for comp, name, axis in ((L.Mux, "Mux" + pr, 0), (L.Muy, "Muy" + pr, 1)):
        if abs(comp) > 1e-9:
            # arco de ~160° por ENCIMA de la columna (en el plano perpendicular al eje del momento) con la punta
            # al final; el sentido es el de la regla de la mano derecha respecto a +X (Mux) o +Y (Muy)
            wcol = bh if axis == 0 else bw
            r_ = max(0.9 * wcol, 0.45 * size)
            th = np.radians(np.linspace(10.0, 170.0, 50))
            if (axis == 0 and comp < 0) or (axis == 1 and comp > 0):
                th = th[::-1]
            if axis == 0:       # giro alrededor de +X, plano YZ: de +y a -y por arriba si Mux > 0
                P_ = [T + ey * r_ * np.cos(t) + ez * r_ * np.sin(t) for t in th]
            else:               # giro alrededor de +Y, plano ZX: de -x a +x por arriba si Muy > 0
                P_ = [T + ex * r_ * np.cos(t) + ez * r_ * np.sin(t) for t in th]
            P_ = [p / kl for p in P_]
            items.append(("arc", P_, C_M, f"{name} = {u.q('M', comp)}"))
            pts.extend(P_)
    return items, pts


def _cone(tip, direction, length, radius, n=16):
    """Triangulos de un cono (punta en `tip`, mirando a `direction`) y su base."""
    d = np.array(direction, float)
    d = d / max(np.linalg.norm(d), 1e-12)
    ref = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    p1 = np.cross(d, ref); p1 /= np.linalg.norm(p1)
    p2 = np.cross(d, p1)
    base = np.array(tip, float) - d * length
    ring = [base + radius * (np.cos(t) * p1 + np.sin(t) * p2) for t in np.linspace(0, 2 * np.pi, n + 1)]
    tris = [[tuple(tip), tuple(ring[i]), tuple(ring[i + 1])] for i in range(n)]
    tris += [[tuple(base), tuple(ring[i + 1]), tuple(ring[i])] for i in range(n)]
    return tris


def _arrow3d(ax, tail, head, color, lw=4.2):
    """Flecha 3D solida: fuste grueso y cabeza conica grande."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.colors import to_rgb
    d = np.array(head, float) - np.array(tail, float)
    L = float(np.linalg.norm(d))
    if L < 1e-9:
        return
    u_ = d / L
    hl = 0.18 * L                                   # largo de la cabeza
    base = np.array(head) - u_ * hl
    ax.plot([tail[0], base[0]], [tail[1], base[1]], [tail[2], base[2]], color=color, lw=lw, zorder=40,
            solid_capstyle="butt", clip_on=False)
    coll = Poly3DCollection(_cone(head, u_, hl, 0.42 * hl), facecolors=(*to_rgb(color), 1.0),
                            edgecolors=(*to_rgb(color), 1.0), linewidths=0.3, zorder=41)
    coll.set_clip_on(False)
    ax.add_collection3d(coll)


def draw_loads(ax, items):
    """Dibuja las flechas de load_arrows en un eje 3D."""
    for it in items:
        if it[0] == "arrow":
            _, a, b, color, label, far = it
            _arrow3d(ax, a, b, color)
            ax.text(*far, label, fontsize=9, color=color, fontweight="bold", zorder=50,
                    ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="#ffffffcc", ec=color, lw=0.8))
        else:
            _, P_, color, label = it
            xs, ys, zs = zip(*[tuple(p) for p in P_])
            ax.plot(xs, ys, zs, color=color, lw=4.2, zorder=40, solid_capstyle="butt", clip_on=False)
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection
            from matplotlib.colors import to_rgb
            p_end, p_prev = np.array(P_[-1]), np.array(P_[-4])
            dirv = (p_end - p_prev) / max(np.linalg.norm(p_end - p_prev), 1e-12)
            rad = float(np.linalg.norm(np.array(P_[0]) - np.array(P_[len(P_) // 2]))) / 1.6
            hl = 0.30 * rad
            coll = Poly3DCollection(_cone(p_end + dirv * hl, dirv, hl, 0.42 * hl), facecolors=(*to_rgb(color), 1.0),
                                    edgecolors=(*to_rgb(color), 1.0), linewidths=0.3, zorder=41)
            coll.set_clip_on(False)
            ax.add_collection3d(coll)
            # la etiqueta va junto a la punta de la flecha, hacia afuera del arco (no en el vertice, donde se
            # cruzan los arcos de Mux y Muy)
            centre = 0.5 * (np.array(P_[0]) + np.array(P_[-1]))
            out_ = p_end - centre
            out_[2] = 0.0
            out_ = out_ / max(np.linalg.norm(out_), 1e-12)
            pos = p_end + out_ * 0.55 * rad + np.array([0.0, 0.0, -0.35 * rad])
            ax.text(*pos, label, fontsize=9, color=color, fontweight="bold", zorder=50, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="#ffffffcc", ec=color, lw=0.8))


def _clean_poly(poly):
    pts = list(poly)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts = pts[:-1]
    return pts


def _prism(poly, z0, z1, cap=True):
    """Caras (lista de poligonos 3D) de un prisma vertical sobre un poligono 2D."""
    pts = _clean_poly(poly)
    faces = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        faces.append([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)])
    if cap and n >= 3:
        faces.append([(x, y, z1) for x, y in pts])
        faces.append([(x, y, z0) for x, y in pts])
    return faces


def _rot_matrix(tilt_x, tilt_y):
    """Misma matriz que Loads.eff(): R = Ry(tilt_y)·Rx(tilt_x)."""
    cx, sx = math.cos(math.radians(tilt_x)), math.sin(math.radians(tilt_x))
    cy, sy = math.cos(math.radians(tilt_y)), math.sin(math.radians(tilt_y))
    return np.array([[cy, sy * sx, sy * cx], [0.0, cx, -sx], [-sy, cy * sx, cy * cx]])


def _tilted_prism(poly, H, R, cap=True, o=(0.0, 0.0)):
    """Prisma de altura axial H sobre `poly` (en el plano de la seccion), inclinado
    con la matriz R y CORTADO al ras de la placa (z = 0): la base de la columna es
    un corte a bisel que apoya plano sobre la placa."""
    pts = _clean_poly(poly)
    n = len(pts)
    bot, top = [], []
    sh = np.array([o[0], o[1], 0.0])                # la columna gira (se inclina) alrededor de su propio eje, no del centro de la placa
    for (x, y) in pts:
        x, y = x - o[0], y - o[1]
        v0 = R @ np.array([x, y, 0.0])
        t0 = -v0[2] / R[2, 2]                      # eje de la columna donde z = 0
        bot.append(tuple(R @ np.array([x, y, t0]) + sh))
        top.append(tuple(R @ np.array([x, y, H]) + sh))
    faces = [[bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]] for i in range(n)]
    if cap and n >= 3:
        faces.append(list(top))
        faces.append(list(bot))
    return faces


def _plate_top_mesh(prj, holes, zt):
    """Triangulos de la cara superior de la placa con los agujeros REALMENTE vacios:
    Delaunay sobre contorno, aros de agujero y una rejilla interior; se descartan los
    triangulos cuyo centro cae dentro de un agujero."""
    from scipy.spatial import Delaunay
    from . import geometry as G
    p = prj.plate
    outer = _clean_poly(G.plate_outline(prj))
    pts = [tuple(q) for q in outer]
    xs = [q[0] for q in outer]; ys = [q[1] for q in outer]
    # refina el contorno
    if p.shape != "Circular":
        m = 10
        pts = []
        for i in range(len(outer)):
            a, b = outer[i], outer[(i + 1) % len(outer)]
            pts += [(a[0] + (b[0] - a[0]) * k / m, a[1] + (b[1] - a[1]) * k / m) for k in range(m)]
    step = max(max(xs) - min(xs), max(ys) - min(ys)) / 14.0
    circ = p.shape == "Circular"
    R = p.Dp / 2 if circ else 0
    gx = np.arange(min(xs) + step / 2, max(xs), step)
    gy = np.arange(min(ys) + step / 2, max(ys), step)
    for x in gx:
        for y in gy:
            if circ and x * x + y * y > (R - step * 0.4) ** 2:
                continue
            pts.append((float(x), float(y)))
    for (cx, cy, r) in holes:
        for a in np.linspace(0, 2 * math.pi, 25)[:-1]:
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    P = np.array(pts)
    # descarta puntos interiores demasiado cerca de un agujero (dentro del hueco)
    keep = np.ones(len(P), bool)
    for (cx, cy, r) in holes:
        d = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
        keep &= ~(d < r * 0.98)
    P = P[keep]
    tri = Delaunay(P)
    out = []
    for s_ in tri.simplices:
        c = P[s_].mean(axis=0)
        if any(math.hypot(c[0] - cx, c[1] - cy) < r for (cx, cy, r) in holes):
            continue
        if circ and math.hypot(c[0], c[1]) > R:
            continue
        out.append([(P[k][0], P[k][1], zt) for k in s_])
    return out


def _tube(path, r, axis_n, n=16):
    """Barra redonda barrida a lo largo de `path` (puntos 3D de un recorrido plano); `axis_n` = normal al plano del
    recorrido.  -> caras (cuadrilateros) + dos tapas."""
    P = [np.array(q, float) for q in path]
    ring = []
    for i, q in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)])
        t = t / max(np.linalg.norm(t), 1e-12)
        w = np.cross(t, axis_n)
        w = w / max(np.linalg.norm(w), 1e-12)
        ring.append([q + r * (math.cos(a) * axis_n + math.sin(a) * w) for a in np.linspace(0, 2 * math.pi, n + 1)[:-1]])
    faces = []
    for i in range(len(P) - 1):
        for k in range(n):
            k2 = (k + 1) % n
            faces.append([tuple(ring[i][k]), tuple(ring[i][k2]), tuple(ring[i + 1][k2]), tuple(ring[i + 1][k])])
    faces.append([tuple(x) for x in ring[0]])
    faces.append([tuple(x) for x in ring[-1]])
    return faces


def _fillet_path(pts, radius, steps=7):
    """Poligonal con las esquinas redondeadas por arcos tangentes de radio `radius` (se reduce si el tramo es corto)."""
    P = [np.array(q, float) for q in pts]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        d1, d2 = P[i] - P[i - 1], P[i + 1] - P[i]
        l1, l2 = np.linalg.norm(d1), np.linalg.norm(d2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        d1, d2 = d1 / l1, d2 / l2
        cos_t = float(np.clip(d1 @ d2, -1.0, 1.0))
        th = math.acos(cos_t)
        if th < 1e-6:
            out.append(P[i])
            continue
        r_ = min(radius, 0.45 * l1 / math.tan(th / 2), 0.45 * l2 / math.tan(th / 2))
        t = r_ * math.tan(th / 2)
        A = P[i] - d1 * t
        nn = d2 - d1 * cos_t
        nn = nn / max(np.linalg.norm(nn), 1e-12)
        C = A + nn * r_
        for s_ in np.linspace(0.0, th, steps):
            out.append(C - nn * r_ * math.cos(s_) + d1 * r_ * math.sin(s_))
    out.append(P[-1])
    return [tuple(q) for q in out]


def geometry_faces(prj):
    """Piezas de la conexion como caras 3D (pulgadas).
    -> lista de (grupo, caras, color, alfa); grupo: 'conc' | 'below' | 'plate' | 'above'.
    No requiere Gmsh ni CalculiX."""
    from . import geometry as G
    p, b, st, lug = prj.plate, prj.bolts, prj.stiff, prj.lug
    s = prj.section.shape()
    g = b.geom()
    parts = []
    bpos = G.bolt_positions(prj)
    gr = max(0.0, float(p.grout))
    so = max(0.0, float(getattr(b, "standoff", 0.0)))
    zs = -(gr + so)                    # superficie del concreto (hef se mide desde aqui): placa, luz libre, mortero, concreto

    # ---- placa con agujeros
    holes = [(bx, by, g.dh / 2) for bx, by in bpos]
    top = _plate_top_mesh(prj, holes, p.tp)
    bot = [[(x, y, 0.0) for x, y, _ in t] for t in top]
    side = _prism(G.plate_outline(prj), 0.0, p.tp, cap=False)
    wall = []
    for (cx, cy, r) in holes:
        ring = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 25)[:-1]]
        wall += _prism(ring, 0.0, p.tp, cap=False)
    parts.append(("plate", top + bot, "#9aa5b1", 1.0, "flat", "plate"))
    parts.append(("plate", side, "#9aa5b1", 1.0, None, "plate"))
    parts.append(("plate", wall, "#3b434b", 1.0, None, "plate"))
    if gr > 1e-9:                      # mortero de nivelacion bajo la placa (sobre el concreto)
        outl = G.plate_outline(prj)
        parts.append(("plate", _prism(outl, zs, zs + gr, cap=True), "#d9d2c5", 1.0, None, "grout"))

    # ---- pernos (vastago inferior / parte sobre la placa) y tuercas
    from .params3d import washer_radius, washer_thickness
    low, up, nuts, ends, wash = [], [], [], [], []
    tw = max(washer_thickness(prj), 0.0)
    rw = washer_radius(prj)
    hef = max(float(b.hef), 1.0)
    eh = float(b.eh) if b.eh and b.eh > 0 else 3.0 * g.db
    kind = ("gancho_L" if "en L" in b.atype else "gancho_J" if "en J" in b.atype
            else "recto" if b.atype.startswith("Recto") else "cabeza")
    for (bx, by) in bpos:
        r = g.db / 2
        c = [(bx + r * math.cos(a), by + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 17)[:-1]]
        # extremo embebido segun el tipo de anclaje
        if kind == "cabeza":                       # cabeza hexagonal pesada
            low += _prism(c, zs - hef, 0.0, cap=True)
            F = max(g.Fhex, 1.5 * g.db)
            hr = F / math.sqrt(3.0)
            hx = [(bx + hr * math.cos(math.radians(60 * k)), by + hr * math.sin(math.radians(60 * k)))
                  for k in range(6)]
            ends += _prism(hx, zs - hef - 0.7 * g.db, zs - hef)
        elif kind in ("gancho_L", "gancho_J"):     # doblez circular (radio interior 1.5·db) hacia el exterior
            from .params3d import hook_profile
            n = math.hypot(bx, by)
            ux, uy = (bx / n, by / n) if n > 1e-6 else (1.0, 0.0)
            prof, rc = hook_profile(kind, g.db, eh)
            low += _prism(c, zs - hef + rc, 0.0, cap=True)           # vastago recto hasta donde empieza el doblez
            path = [(bx + ux * s_, by + uy * s_, zs - hef + z_) for s_, z_ in prof]
            ends += _tube(path, r, np.array([-uy, ux, 0.0]), n=16)
        else:                                      # recto: sin anclaje mecanico
            low += _prism(c, zs - hef, 0.0, cap=True)
        up += _prism(c, 0.0, p.tp + tw + 1.25 * g.db, cap=True)
        if tw > 0:                                 # arandela sobre la placa, bajo la tuerca
            wr_ = [(bx + rw * math.cos(a), by + rw * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 33)[:-1]]
            wash += _prism(wr_, p.tp, p.tp + tw)
        hexr = 0.9 * g.db
        hx = [(bx + hexr * math.cos(math.radians(60 * k)), by + hexr * math.sin(math.radians(60 * k)))
              for k in range(6)]
        nuts += _prism(hx, p.tp + tw, p.tp + tw + 0.875 * g.db)
        if so > 1e-9:                              # tuerca de nivelacion bajo la placa
            nuts += _prism(hx, -0.875 * g.db, 0.0)
    parts.append(("below", low, "#c9a227", 1.0, None, "bolts"))
    parts.append(("below", ends, "#a8861c", 1.0, None, "bolts"))
    parts.append(("above", up, "#c9a227", 1.0, None, "bolts"))
    parts.append(("above", nuts, "#8d7514", 1.0, None, "bolts"))
    if wash:
        parts.append(("above", wash, "#aab2bb", 1.0, None, "bolts"))

    # ---- columna (inclinada y con la base cortada a bisel sobre la placa)
    H = max(3.0 * s.d, 12.0)
    R = _rot_matrix(prj.loads.tilt_x, prj.loads.tilt_y)
    col = []
    co = G.col_shift(prj)
    if prj.section.generic:
        for poly in G.section_rects(prj):
            col += _tilted_prism(poly, H, R, o=co)
    else:
        ext, inn = G.profile_outline(prj)
        col += _tilted_prism(ext, H, R, cap=not inn, o=co)
        if inn:
            col += _tilted_prism(inn, H, R, cap=False, o=co)
            e, i_ = _clean_poly(ext), _clean_poly(inn)
            if len(e) == len(i_):                    # corona superior del tubo
                for k in range(len(e)):
                    k2 = (k + 1) % len(e)
                    q = [tuple(R @ np.array([x - co[0], y - co[1], H]) + np.array([co[0], co[1], 0.0])) for x, y in (e[k], e[k2], i_[k2], i_[k])]
                    col.append(q)
    col = [[(x, y, z + p.tp) for x, y, z in f] for f in col]
    parts.append(("above", col, "#4c78a8", 1.0, None, "column"))

    # ---- rigidizadores (solo columna vertical)
    if st.enabled and st.count > 0 and not prj.loads.tilted:
        prof2d = st.outline()[:-1]
        faces = []
        for (x1, y1, x2, y2) in G.stiffener_lines(prj):
            ang = math.atan2(y2 - y1, x2 - x1)
            ca, sa = math.cos(ang), math.sin(ang)

            def T(u, v, w):
                return (x1 + u * ca - w * sa, y1 + u * sa + w * ca, p.tp + v)
            w = st.t / 2
            for i, (u0, v0) in enumerate(prof2d):
                u1, v1 = prof2d[(i + 1) % len(prof2d)]
                faces.append([T(u0, v0, -w), T(u1, v1, -w), T(u1, v1, w), T(u0, v0, w)])
            faces.append([T(u, v, w) for u, v in prof2d])
            faces.append([T(u, v, -w) for u, v in prof2d])
        parts.append(("above", faces, "#59a14f", 1.0, None, "stiff"))

    # ---- llave de corte (bajo la placa)
    if lug.enabled:
        faces = []
        for poly in G.lug_outline(prj):
            faces += _prism(poly, -lug.H, 0.0)
        parts.append(("below", faces, "#e15759", 1.0, None, "lug"))

    # ---- barras de refuerzo del arrancamiento: U (patas rectas) u Omega (patas con gancho de 90° hacia afuera)
    from .ubar import ubar
    ub = ubar(prj)
    if ub is not None:
        faces = []
        r = ub["db"] / 2.0
        z0 = zs - ub["depth"]
        zb_ = z0 - ub["leg"]
        for yy in ub["yu"]:
            xl, xr, tl = ub["xl"], ub["xr"], ub["tail"]
            if ub["kind"] == "OMEGA":
                pts = [(xl - tl, yy, zb_), (xl, yy, zb_), (xl, yy, z0), (xr, yy, z0), (xr, yy, zb_), (xr + tl, yy, zb_)]
            else:
                pts = [(xl, yy, zb_), (xl, yy, z0), (xr, yy, z0), (xr, yy, zb_)]
            path = _fillet_path(pts, ub["rb"], steps=7)
            faces += _tube(path, r, np.array([0.0, 1.0, 0.0]), n=16)
        parts.append(("below", faces, "#d43c3c", 1.0, None, "ubar"))

    # ---- pedestal de concreto (transparente)
    c = prj.conc
    ped = [(-c.B2 / 2, -c.N2 / 2), (c.B2 / 2, -c.N2 / 2), (c.B2 / 2, c.N2 / 2), (-c.B2 / 2, c.N2 / 2)]
    zc = zs - min(c.ha, max(b.hef * 1.15, 12.0))
    if ub is not None:
        zc = min(zc, zs - (ub["depth"] + ub["leg"]) - 1.0)
    conc = _prism(ped, zc, zs, cap=False)                  # caras laterales
    conc.append([(x, y, zc) for x, y in ped])              # fondo
    conc.append([(x, y, zs) for x, y in ped])              # cara superior (bajo el mortero / la placa)
    parts.append(("conc", conc, "#a9b4bd", 0.16, None, "conc"))        # UNICO elemento translucido
    return parts


ZSORT = "min"          # criterio de orden de las caras del acero: "min" (el que mejor resuelve placa, pernos y columna), "average" o "max"


def _pad_faces(faces):
    """Poligonos de distinto numero de lados -> arreglo uniforme (se repite el ultimo vertice: no cambia el dibujo)."""
    nmax = max(len(f) for f in faces)
    return np.array([list(f) + [f[-1]] * (nmax - len(f)) for f in faces], dtype=float)


def update_order(ax):
    """Pedestal translucido segun la camara: las caras traseras se pintan ANTES del acero y las delanteras DESPUES.
    (El acero va en una sola coleccion cuyas caras matplotlib ordena por profundidad todas juntas.)"""
    conc = getattr(ax, "_pb_conc", None)
    if not conc:
        return
    e, a = math.radians(float(ax.elev)), math.radians(float(ax.azim))
    cam = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    front = [f for f, n in zip(conc["faces"], conc["normals"]) if float(n @ cam) > 1e-9]
    back = [f for f, n in zip(conc["faces"], conc["normals"]) if float(n @ cam) <= 1e-9]
    for key, lst in (("back", back), ("front", front)):
        coll = conc[key]
        if lst:
            coll.set_verts(lst)
            coll.set_visible(True)
        else:
            coll.set_visible(False)


def plot_geometry(ax, prj, show_concrete=True, title=True, loads=False):
    """Dibuja el conjunto de la conexion (solo geometria) en un eje 3D."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.colors import to_rgb

    ax.clear()
    try:
        ax.computed_zorder = False           # respeta el orden de los grupos
    except Exception:
        pass
    u = prj.units()
    kl = u.fl
    allp = []
    steel_f, steel_fc, steel_ec = [], [], []
    conc_f = None
    for part in geometry_faces(prj):
        grp, faces, color, alpha = part[:4]
        flat = len(part) > 4 and part[4] == "flat"
        if not faces or (grp == "conc" and not show_concrete):
            continue
        v_ = [[(x / kl, y / kl, z / kl) for x, y, z in f] for f in faces]
        allp += [pt for f in v_ for pt in f]      # incluye el concreto: si no, queda fuera del encuadre
        rgb = to_rgb(color)
        if grp == "conc":
            conc_f = (v_, rgb, alpha)
            continue
        # los triangulos de la malla de la placa no llevan aristas
        edge = (*rgb, 1.0) if flat else ((0, 0, 0, 0.35) if alpha > 0.5 else (0.3, 0.35, 0.4, 0.35))
        steel_f += v_
        steel_fc += [(*rgb, alpha)] * len(v_)
        steel_ec += [edge] * len(v_)
    groups = []
    if steel_f:
        # TODAS las caras opacas en una sola coleccion: matplotlib las ordena por profundidad juntas (algoritmo del
        # pintor por cara), en vez de ordenar por pieza.  Se ordena por el vertice mas lejano de cada cara.
        coll = Poly3DCollection(_pad_faces(steel_f), facecolors=steel_fc, edgecolors=steel_ec, linewidths=0.35)
        coll.set_zsort(ZSORT)
        coll.set_clip_on(False)
        coll.set_zorder(2)
        ax.add_collection3d(coll)
        groups.append(("acero", coll))
    ax._pb_conc = None
    if conc_f is not None:
        cf, rgb, alpha = conc_f
        centre = np.mean(np.array([p for f in cf for p in f]), axis=0)
        normals = []
        for f in cf:
            n = np.cross(np.array(f[1]) - np.array(f[0]), np.array(f[2]) - np.array(f[0]))
            n = n / max(np.linalg.norm(n), 1e-12)
            if float(n @ (np.mean(np.array(f), axis=0) - centre)) < 0:      # normal hacia afuera del pedestal
                n = -n
            normals.append(n)
        cols = []
        for z_ in (1, 3):                    # 1: caras traseras (antes del acero), 3: delanteras (despues)
            c_ = Poly3DCollection(_pad_faces(cf), facecolors=(*rgb, alpha), edgecolors=(0.3, 0.35, 0.4, 0.35),
                                  linewidths=0.35)
            c_.set_clip_on(False)
            c_.set_zorder(z_)
            ax.add_collection3d(c_)
            cols.append(c_)
        ax._pb_conc = {"faces": [np.array(f) for f in cf], "normals": normals, "back": cols[0], "front": cols[1]}
        groups += [("conc_tras", cols[0]), ("conc_del", cols[1])]
    ax._pb_groups = groups
    update_order(ax)
    load_items = []
    if loads:
        load_items, lpts = load_arrows(prj, kl)
        allp += [tuple(p) for p in lpts]

    P = np.array(allp, dtype=float)
    mins, maxs = P.min(axis=0), P.max(axis=0)
    spans = np.maximum(maxs - mins, 1e-6)
    pad = 0.03 * float(spans.max())
    ax.set_xlim(mins[0] - pad, maxs[0] + pad)
    ax.set_ylim(mins[1] - pad, maxs[1] + pad)
    ax.set_zlim(mins[2] - pad, maxs[2] + pad)
    set_aspect(ax, tuple(float(v) + 2 * pad for v in spans), pts=P)
    ax.set_axis_off()                     # sin ejes ni reglas
    if load_items:
        draw_loads(ax, load_items)
    tl = prj.loads
    if title:
        ax.set_title("Geometria de la conexion"
                     + (f"   —   columna inclinada  X {tl.tilt_x:g}°, Y {tl.tilt_y:g}°"
                        if tl.tilted else ""), fontsize=9, loc="left")


def render_result_png(res: Result3D, prj, field: str, path: str, scale: float = 0.0,
                      size=(7.0, 4.6), dpi=150):
    """Imagen de un campo de resultados 3D con la etiqueta del maximo (para el reporte).
    -> (ruta, valor_maximo, nodo) o (None, 0, 0)."""
    import matplotlib
    from matplotlib.figure import Figure
    try:
        fig = Figure(figsize=size, dpi=dpi)
        ax = fig.add_axes([0.0, 0.0, 0.87, 0.93], projection="3d")
        m = plot3d(ax, res, prj, field, scale, tag_max=True)
        ax.view_init(elev=24, azim=-58)
        fit_to_axes(ax)
        if m is not None:
            cax = fig.add_axes([0.90, 0.16, 0.02, 0.66])
            fig.colorbar(m, cax=cax)
        fig.savefig(path)
        return path
    except Exception:
        return None


# ====================================== esfuerzo promediado en la placa (convergente)
def _covered_by_profile(prj, x, y):
    """True si (x, y) esta bajo el metal del perfil (union placa-perfil)."""
    from . import geometry as G
    if prj.section.generic:
        return any(G._inside(x, y, poly) for poly in G.section_rects(prj))
    ext, inn = G.profile_outline(prj)
    if not G._inside(x, y, ext):
        return False
    return not (inn and G._inside(x, y, inn))


from .params3d import washer_elements

PART_LABELS = {"all": "Todo el conjunto", "plate": "Placa base", "column": "Columna (perfil)",
               "stiff": "Rigidizadores", "lug": "Llave de corte", "washer": "Arandelas"}


def classify_parts(res: "Result3D", prj) -> dict:
    """Separa los elementos del solido por pieza segun la posicion de su centroide:
        z < 0                 llave de corte
        0 <= z < tp           placa
        z > tp, bajo el perfil  columna;  z > tp, fuera de la huella del perfil  rigidizadores
    -> {pieza: [caras exteriores de la pieza]} (solo las piezas que existen)."""
    tp = prj.plate.tp
    groups = {"plate": [], "column": [], "stiff": [], "lug": [], "washer": []}
    N = res.nodes
    for e in res.elems:
        c = e[:4]
        xc = sum(N[n][0] for n in c) / 4.0
        yc = sum(N[n][1] for n in c) / 4.0
        zc = sum(N[n][2] for n in c) / 4.0
        if zc < 0:
            groups["lug"].append(e)
        elif zc < tp:
            groups["plate"].append(e)
        elif washer_elements(prj, xc, yc, zc):                     # arandelas: pieza aparte (no se ven en la placa)
            groups["washer"].append(e)
        elif _covered_by_profile(prj, xc, yc):
            groups["column"].append(e)
        else:
            groups["stiff"].append(e)
    return {k: skin(v) for k, v in groups.items() if v}


def smoothed_part_vm(res: "Result3D", prj, part: str, radius: float):
    """von Mises PROMEDIADO en una pieza de acero que no es la placa (columna, rigidizadores).

    Igual que en la placa se promedia el TENSOR y no el von Mises, con peso = area tributaria de cada nodo de
    la piel, pero aqui las paredes son delgadas y una esfera de radio r tocaria las dos caras de la pared (la
    flexion se anularia): solo se promedian los nodos de la MISMA CARA, es decir con la normal exterior casi
    paralela (cos > 0.7) dentro de la esfera.  Se excluyen la cara que apoya en la placa (interfaz, donde
    esta la singularidad del cordon) y el tope donde se aplican las cargas.
    -> dict(vm, x, y, z, radius, vm_point, n) o None."""
    import numpy as np
    from scipy.spatial import cKDTree
    tris = res.parts.get(part)
    if not tris:
        return None
    tp = prj.plate.tp
    ztop = max(p[2] for p in res.nodes.values())
    tol = 1e-3
    pts = {}
    for t in tris:
        P3 = [res.nodes[n] for n in t]
        if all(abs(p[2] - tp) < 0.05 for p in P3):          # base apoyada en la placa (z = tp o tp + δ)
            continue
        if all(p[2] > ztop - tol for p in P3):              # tope de carga
            continue
        a, b, c = (np.array(p) for p in P3)
        nv = np.cross(b - a, c - a)
        ar = 0.5 * float(np.linalg.norm(nv))
        if ar <= 1e-12:
            continue
        nv = nv / (2 * ar)
        cen = (a + b + c) / 3.0
        for n in t:                                           # normal exterior: hacia fuera del centroide de la pieza
            d = pts.setdefault(n, [0.0, np.zeros(3), cen * 0.0, 0])
            d[0] += ar / 3.0
            d[1] += nv * (ar / 3.0)
    ids = [n for n in pts if n in res.stress]
    if len(ids) < 4:
        return None
    X = np.array([res.nodes[n] for n in ids], float)
    S = np.array([res.stress[n] for n in ids], float)
    W = np.array([pts[n][0] for n in ids], float)
    N = np.array([pts[n][1] for n in ids], float)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    # las normales de los triangulos pueden salir invertidas segun el orden de los nodos: se orientan hacia
    # fuera de la pieza (lejos de su centroide); en paredes delgadas sirve el signo respecto al centroide local
    cen = X.mean(axis=0)
    # orientacion local: normal * signo((x - c_local) . n) con c_local = media de los nodos vecinos
    tree = cKDTree(X)
    for i in range(len(ids)):
        nb = tree.query_ball_point(X[i], 3.0 * radius)
        cl = X[nb].mean(axis=0)
        if np.dot(X[i] - cl, N[i]) < 0 and np.linalg.norm(X[i] - cl) > 1e-6:
            N[i] = -N[i]
    vm_pt = np.array([von_mises(*s_) for s_ in S])
    best = None
    for i in range(len(ids)):
        nb = np.array(tree.query_ball_point(X[i], radius))
        ok = nb[(N[nb] @ N[i]) > 0.7]
        if len(ok) == 0:
            ok = np.array([i])
        ww = W[ok]
        sm = (S[ok] * ww[:, None]).sum(axis=0) / ww.sum()
        v = von_mises(*sm)
        if best is None or v > best["vm"]:
            best = dict(vm=float(v), x=float(X[i][0]), y=float(X[i][1]), z=float(X[i][2]), radius=float(radius))
    best["vm_point"] = float(vm_pt.max())
    best["n"] = len(ids)
    return best


def smoothed_face_fields(res: "Result3D", prj, radius: float = 0.0):
    """Campo de von Mises PROMEDIADO nodo a nodo en cada cara de la placa (ver smoothed_plate_vm).
    -> dict(radius, top=dict(xy, vm, vm_point, z), bot=dict(...)); una cara ausente no aparece.
    xy: (n,2) nodos usados; vm: von Mises del tensor promediado en el circulo de radio r alrededor de
    cada nodo; vm_point: von Mises puntual del nodo."""
    import numpy as np
    from scipy.spatial import Delaunay, cKDTree
    from . import geometry as G

    tp = prj.plate.tp
    r = radius if radius and radius > 0 else tp
    g = prj.bolts.geom()
    bolts = np.array(G.bolt_positions(prj), dtype=float).reshape(-1, 2)
    r_hole = g.dh / 2.0
    tol = 1e-4

    ids = [n for n in res.nodes if n in res.stress]
    out = dict(radius=float(r))
    if not ids:
        return out
    P = np.array([res.nodes[n] for n in ids], dtype=float)
    S = np.array([res.stress[n] for n in ids], dtype=float)

    def in_hole(x, y):
        return bolts.size > 0 and bool(np.any(np.hypot(bolts[:, 0] - x, bolts[:, 1] - y) < r_hole - 1e-6))

    for name, zl, is_top in (("bot", 0.0, False), ("top", tp, True)):
        sel = np.where(np.abs(P[:, 2] - zl) < tol)[0]
        if is_top:
            sel = np.array([k for k in sel if not _covered_by_profile(prj, P[k, 0], P[k, 1])], dtype=int)
        if len(sel) < 4:
            continue
        xy = P[sel, :2]
        tri = Delaunay(xy)
        w = np.zeros(len(sel))
        for s_ in tri.simplices:
            a, b, c = xy[s_[0]], xy[s_[1]], xy[s_[2]]
            cen = (a + b + c) / 3.0
            if in_hole(cen[0], cen[1]):
                continue
            if is_top and _covered_by_profile(prj, cen[0], cen[1]):
                continue
            ar = 0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if ar > 50.0 * (r * r):                # triangulo espurio que cruza vacios grandes
                continue
            w[s_] += ar / 3.0
        keep = w > 0
        if keep.sum() < 4:
            continue
        idx = sel[keep]; xyk = xy[keep]; wk = w[keep]; Sk = S[idx]
        tree = cKDTree(xyk)
        vm_pt = np.array([von_mises(*s) for s in Sk])
        vm_sm = np.empty(len(idx))
        for i in range(len(idx)):
            nb = tree.query_ball_point(xyk[i], r)
            ww = wk[nb]
            vm_sm[i] = von_mises(*((Sk[nb] * ww[:, None]).sum(axis=0) / ww.sum()))
        out[name] = dict(xy=xyk, vm=vm_sm, vm_point=vm_pt, z=float(zl))
    return out


def smoothed_plate_vm(res: "Result3D", prj, radius: float = 0.0):
    """Esfuerzo de von Mises PROMEDIADO en la placa, para leer un maximo que no dependa
    de la malla.  El von Mises puntual crece sin limite al refinar en las aristas vivas
    (borde de agujero, pie del perfil); en cambio el promedio ponderado por area sobre
    un circulo de radio fijo (por defecto el espesor de la placa) SI converge.

    Se promedia el TENSOR de esfuerzos (no el von Mises) y solo entre nodos de la misma
    cara (superior o inferior de la placa), para no anular la flexion a traves del
    espesor.  La cara superior excluye lo cubierto por el perfil.  Los pesos son el area
    tributaria de cada nodo (triangulacion de la cara), asi la densidad de la malla no
    sesga el promedio.

    -> dict(vm=maximo promediado, x, y, z, radius, vm_point=maximo puntual de la misma
    zona, n=nodos) o None."""
    import numpy as np
    F = smoothed_face_fields(res, prj, radius)
    best = None
    for name in ("bot", "top"):
        f = F.get(name)
        if f is None:
            continue
        i = int(np.argmax(f["vm"]))
        if best is None or f["vm"][i] > best["vm"]:
            best = dict(vm=float(f["vm"][i]), x=float(f["xy"][i][0]), y=float(f["xy"][i][1]),
                        z=f["z"], radius=F["radius"], vm_point=0.0, n=0)
    if best is not None:
        for name in ("bot", "top"):
            f = F.get(name)
            if f is not None:
                best["vm_point"] = max(best["vm_point"], float(f["vm_point"].max()))
                best["n"] += int(len(f["vm"]))
    return best
