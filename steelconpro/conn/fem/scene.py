# -*- coding: utf-8 -*-
"""Escenas 3D de las conexiones para el visor (gl3d.Scene): geometria del modelo y campos de resultados; y una salida PNG con matplotlib
(respaldo cuando el equipo no ofrece OpenGL y para los reportes)."""
from __future__ import annotations
import math

import numpy as np

from .model3d import COLORS, KIND_NAMES, Model3D, weld_prism, unit, cyl_prism, Prism


def _rgb(hexcol):
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _bolt_faces(b):
    """Caras del perno: cabeza y tuerca (prismas hexagonales) y vastago."""
    ax = unit(b.axis)
    p = np.asarray(b.p, float)
    out = {"shank": [], "head": []}
    r = 0.5 * b.db
    sh = cyl_prism(p + ax * 0.5 * (b.head_s + b.nut_s), ax, r, abs(b.nut_s - b.head_s) + 0.0)
    out["shank"] += sh.faces(16)
    th = 0.65 * b.db
    hexr = 0.5 * 1.5 * b.db / math.cos(math.radians(30))
    for s0, sgn in ((b.head_s, -1.0), (b.nut_s, 1.0)):
        c = p + ax * (s0 + sgn * th / 2.0 * (1.0 if sgn > 0 else -1.0) * -1.0)
    # cabeza: sobresale hacia fuera desde head_s (sentido -axis); tuerca desde nut_s (sentido +axis)
    for s0, sg in ((b.head_s, -1.0), (b.nut_s, 1.0)):
        c = p + ax * (s0 + sg * th / 2.0)
        h = cyl_prism(c, ax, hexr, th)
        h.circle = None
        U = unit(np.cross(ax, [0.0, 0.0, 1.0] if abs(ax[2]) < 0.9 else [1.0, 0.0, 0.0]))
        V = np.cross(ax, U)
        h.U, h.V = tuple(U), tuple(V)
        h.poly = [(hexr * math.cos(math.radians(60 * k)), hexr * math.sin(math.radians(60 * k))) for k in range(6)]
        out["head"] += h.faces()
    return out


GRAY = "#a6a6a6"


def scene_model(mdl: Model3D, loads: bool = True, scale: float = 1.0, load_label=None, hide=(), bolts: bool = True, gray: bool = False,
                tags: bool = False):
    """Escena de la geometria. `scale` convierte las coordenadas (in) a las unidades mostradas.  gray: todas las piezas en gris (miniaturas de
    geometria); bolts: dibujar los pernos; tags: nombre de cada miembro en su extremo."""
    from .. .gl3d import Scene
    sc = Scene()
    pts = []
    for p in mdl.parts:
        if p.kind in hide:
            continue
        faces = []
        for pr in p.prisms:
            faces += [[tuple(np.asarray(q) * scale) for q in f] for f in pr.faces()]
        pts += [q for f in faces for q in f]
        sc.group = "g_" + p.kind
        sc.add_faces(faces, _rgb(GRAY if gray else COLORS.get(p.kind, COLORS["other"])), 1.0 if p.kind not in ("support",) else 0.55, edges=True)
    for w in (mdl.welds if not gray else []):
        pr = weld_prism(w)
        fs = [[tuple(np.asarray(q) * scale) for q in f] for f in pr.faces()]
        sc.group = "g_weld"
        sc.add_faces(fs, _rgb(COLORS["weld"]), 1.0, edges=False)
    bolt_parts = {"shank": [], "head": []}
    for b in (mdl.bolts if bolts else []):
        f = _bolt_faces(b)
        for k in bolt_parts:
            bolt_parts[k] += [[tuple(np.asarray(q) * scale) for q in fc] for fc in f[k]]
    sc.group = "g_bolt"
    sc.add_faces(bolt_parts["shank"], _rgb("#2f4b7c"), 1.0, edges=False)
    sc.add_faces(bolt_parts["head"], _rgb("#44546a"), 1.0, edges=True)
    sc.group = "other"
    sc.pts = pts
    sc.title = mdl.name
    if tags:
        for pos, text in getattr(mdl, "tags", []):
            sc.labels.append((tuple(np.asarray(pos, float) * scale), text, "#1f3864", "#ffffffd9", "#1f3864", True))
    if loads:
        _add_loads(sc, mdl, scale, load_label)
    return sc


def _add_loads(sc, mdl, scale, label=None):
    """Flechas de fuerza (rojo) y de momento (violeta, doble punta) en el punto de aplicacion."""
    lo, hi = mdl.bounds()
    span = float(np.max(hi - lo)) * scale
    sc.group = "load"
    for ld in mdl.loads:
        ref = np.asarray(ld.show if ld.show is not None else ld.ref, float) * scale
        F = np.asarray(ld.F, float)
        M = np.asarray(ld.M, float)
        nF = float(np.linalg.norm(F))
        if nF > 1e-9:
            d = F / nF
            L = 0.22 * span
            tail = ref - d * L
            sc.add_arrow(tuple(tail), tuple(ref), (0.85, 0.1, 0.1), 0.012 * span)
            sc.labels.append((tuple(tail), label("F", nF) if label else f"F = {nF:.4g}", "#9c0006", "#ffffffd9", "#9c0006", True))
        nM = float(np.linalg.norm(M))
        if nM > 1e-9:
            d = M / nM
            L = 0.18 * span
            sc.add_arrow(tuple(ref - d * L), tuple(ref + d * L), (0.5, 0.1, 0.7), 0.010 * span)
            sc.add_arrow(tuple(ref), tuple(ref + d * L * 1.15), (0.5, 0.1, 0.7), 0.010 * span)
            sc.labels.append((tuple(ref + d * L * 1.2), label("M", nM) if label else f"M = {nM:.4g}", "#5b2c83", "#ffffffd9", "#5b2c83", True))
    sc.group = "other"


# ============================================================================== salida PNG (z-buffer propio)
def scene_arrays(sc, mode=None):
    """(tris (n,3,3), colores (n,3,4), segmentos (m,2,3)) de una escena."""
    o, t, l = sc.packed(mode)
    arrs = [a for a in (o, t) if len(a)]
    if arrs:
        A = np.concatenate(arrs).reshape(-1, 3, 10)
        tris, cols = A[:, :, :3].astype(float), A[:, :, 6:10].astype(float)
    else:
        tris, cols = np.zeros((0, 3, 3)), np.zeros((0, 3, 4))
    segs = l[:, :3].reshape(-1, 2, 3).astype(float) if len(l) else np.zeros((0, 2, 3))
    return tris, cols, segs


def render_scene_image(sc, elev=24.0, azim=50.0, size=(1100, 800), title="", mode=None, ss=2, margin=0.06):
    """Imagen PIL de la escena con z-buffer. Las etiquetas de la escena se dibujan sobre la imagen."""
    from PIL import ImageDraw
    from .raster import render
    tris, cols, segs = scene_arrays(sc, mode)
    if not len(tris):
        raise ValueError("escena vacia")
    pts = np.asarray(sc.pts, float) if len(sc.pts) else tris.reshape(-1, 3)
    im = render(tris, cols, segs, elev, azim, size, bounds=pts, ss=ss, margin=margin)
    if title:
        ImageDraw.Draw(im).text((10, 8), title, fill=(30, 30, 30))
    return im


def render_scene_png(sc, path, elev=24.0, azim=50.0, size=(1100, 800), title="", mode=None):
    """Imagen de la escena con z-buffer (PNG)."""
    render_scene_image(sc, elev, azim, size, title, mode).save(path)
    return path


# ============================================================================== resultados del 3D (campos sobre la piel de las piezas)
FIELDS = [("vm", "Von Mises"), ("u", "Desplazamiento |U|"), ("uz", "Desplazamiento Uz"), ("peeq", "Deformacion plastica (PEEQ)")]


def part_choices(R):
    """[(clave, texto)] de lo que se puede mostrar: todo el conjunto y cada pieza."""
    out = [("all", "Todo el conjunto")]
    for k in R.parts:
        out.append((k, R.labels.get(k, k)))
    return out


def scene_fem(R, prj, field="vm", scale=0.0, part="all", loads=False, bolts=True):
    """Escena (gl3d.Scene) del campo de resultados sobre la piel del solido; `scale` amplifica los desplazamientos."""
    from ...gl3d import Scene
    from ...view3d import _soft_cmap
    sc = Scene()
    u = prj.units()
    kl, ks = u.fl, u.fs
    if R is None or not R.ok:
        sc.message = ("Sin resultados 3D.", "#777777")
        return sc
    keys = list(R.parts) if part == "all" else [part]
    tris = [t for k in keys for t in R.parts.get(k, [])]
    if not tris:
        sc.message = ("Sin elementos de esa pieza en el modelo.", "#777777")
        return sc
    ids = sorted({n for t in tris for n in t})
    idx = {n: i for i, n in enumerate(ids)}
    P = np.array([R.nodes[n] for n in ids], float)
    if scale > 0:
        P = P + scale * np.array([R.disp.get(n, (0.0, 0.0, 0.0)) for n in ids], float)
    if field == "u":
        val = np.array([math.sqrt(sum(c * c for c in R.disp.get(n, (0, 0, 0)))) for n in ids]) / kl
        title, unit_, cmap = "Desplazamiento |U|", u.L, _soft_cmap()
    elif field == "uz":
        val = np.array([R.disp.get(n, (0, 0, 0))[2] for n in ids]) / kl
        title, unit_, cmap = "Desplazamiento vertical Uz", u.L, _soft_cmap(True)
    elif field == "peeq":
        val = np.array([R.peeq.get(n, 0.0) for n in ids]) * 100.0
        title, unit_, cmap = "Deformacion plastica equivalente", "%", _soft_cmap()
    else:
        val = np.array([R.vm.get(n, 0.0) for n in ids]) / ks
        title, unit_, cmap = "Esfuerzo de von Mises", u.S, _soft_cmap()
    T = np.array([[idx[a], idx[b], idx[c]] for a, b, c in tris], dtype=np.int64)
    fv = val[T].mean(axis=1)
    vmin, vmax = float(fv.min()), float(fv.max())
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    vcol = cmap(np.clip((val - vmin) / (vmax - vmin), 0.0, 1.0))
    Pm = P / kl
    sc.add_mesh(Pm, T, vcol)
    pts = [Pm]
    if bolts and scale <= 0 and R.model is not None and part == "all":
        bf = {"shank": [], "head": []}
        for b in R.model.bolts:
            f = _bolt_faces(b)
            for k in bf:
                bf[k] += [[tuple(np.asarray(q) / kl) for q in fc] for fc in f[k]]
        sc.group = "g_bolt"
        sc.add_faces(bf["shank"], (0.30, 0.34, 0.42), 1.0, edges=False)
        sc.add_faces(bf["head"], (0.22, 0.26, 0.34), 1.0, edges=True)
        sc.group = "other"
    sc.pts = np.vstack(pts)
    k = int(np.argmax(val))
    sc.markers.append((tuple(Pm[k]), "#d62728"))
    note = None
    txt = f"{title}: maximo = {val[k]:.4g} {unit_}   (pico puntual: depende de la malla)" if field == "vm" else f"{title}: maximo = {val[k]:.4g} {unit_}"
    if field == "peeq":
        txt = f"{title}: maximo = {val[k]:.4g} {unit_}   (limite {getattr(prj.fea, 'plastic_limit', 5.0):g} %)"
    sc.hud.append(("bl", txt, "#7a1010", "#fff3e0", "#d62728"))
    if bolts and part == "all" and R.bolts:
        Vmax = max((b.V for b in R.bolts), default=0.0)
        top = sorted(R.bolts, key=lambda b: -max(b.V, b.T))[:6]
        for b in top:
            hot = b is top[0]
            sc.labels.append(((b.pos[0] / kl, b.pos[1] / kl, b.pos[2] / kl), f"{b.tag}\nV {u.fmt('F', b.V)}  T {u.fmt('F', b.T)}", "#ffffff" if hot else "#08306b",
                              "#d62728" if hot else "#ffffffd9", "#d62728" if hot else "#08306b", hot))
    if loads and R.model is not None:
        _add_loads(sc, R.model, 1.0 / kl)
    sc.title = f"{title}  ({unit_})" + (f"   —  deformada ×{scale:g}" if scale > 0 else "")
    cols = cmap(np.linspace(0, 1, 64))[:, :3]
    sc.cbar = dict(colors=cols, vmin=vmin, vmax=vmax, note=None)
    return sc


def draw_scene_mpl(ax, sc, max_tris=30000, sub=True):
    """Respaldo con matplotlib (sin OpenGL): dibuja las mallas de la escena con orden de profundidad por el centro del triangulo."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    ax.clear()
    ax.set_axis_off()
    arrs = [a for a in (sc.opaque + sc.trans) if len(a)]
    if not arrs:
        if sc.message:
            ax.text2D(0.5, 0.5, sc.message[0], ha="center", va="center", color=sc.message[1], transform=ax.transAxes, fontsize=11)
        return None
    A = np.concatenate(arrs).reshape(-1, 3, 10)
    V, C = A[:, :, :3].astype(float), A[:, :, 6:10].astype(float)
    if sub:
        pts = V.reshape(-1, 3)
        span = float(np.ptp(pts, axis=0).max())
        V, C = _subdivide(V, C, span / 14.0, max_tris)
    elif len(V) > max_tris:
        st = len(V) // max_tris + 1
        V, C = V[::st], C[::st]
    N = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    k = 0.55 + 0.45 * np.abs(N @ np.array([0.45, -0.55, 0.7]) / 1.0)
    col = np.concatenate([np.clip(C[:, :, :3].mean(axis=1) * k[:, None], 0, 1), C[:, 0, 3:4]], axis=1)
    pc = Poly3DCollection(V, facecolors=col, edgecolors=col * 0.8, linewidths=0.1)
    ax.add_collection3d(pc)
    pts = V.reshape(-1, 3)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(tuple(np.maximum(hi - lo, 1e-6)))
    for pos, text, fg, _bg, border, bold in getattr(sc, "labels", []):
        ax.text(pos[0], pos[1], pos[2], text, color=fg, fontsize=8, weight="bold" if bold else "normal", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=border or fg, alpha=0.9, lw=0.8))
    return pc


def _subdivide(V, C, maxlen, max_tris):
    """Divide en 4 los triangulos de arista mayor que `maxlen` (para que el orden de profundidad por centro sea fiable)."""
    for _ in range(5):
        e = np.max([np.linalg.norm(V[:, i] - V[:, (i + 1) % 3], axis=1) for i in range(3)], axis=0)
        big = e > maxlen
        if not big.any() or len(V) + 3 * big.sum() > max_tris:
            break
        keep, B, CB = V[~big], V[big], C[big]
        a, b, c = B[:, 0], B[:, 1], B[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        ca_, cb_, cc_ = CB[:, 0], CB[:, 1], CB[:, 2]
        cab, cbc, cca = (ca_ + cb_) / 2, (cb_ + cc_) / 2, (cc_ + ca_) / 2
        newV = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
        newC = np.concatenate([np.stack([ca_, cab, cca], 1), np.stack([cab, cb_, cbc], 1), np.stack([cca, cbc, cc_], 1), np.stack([cab, cbc, cca], 1)])
        V, C = np.concatenate([keep, newV]), np.concatenate([C[~big], newC])
    return V, C
