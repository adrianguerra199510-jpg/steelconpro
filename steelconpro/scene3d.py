# -*- coding: utf-8 -*-
"""Escenas 3D sin Qt: mallas triangulares con color, lineas de aristas, etiquetas y cotas (clase `Scene`) y las funciones que arman la escena de la
placa base (`scene_geometry`, `scene_results`).  Las usan el servidor del motor (que las manda al visor three.js de la aplicacion Electron) y
las pruebas; el visor OpenGL de Qt (gl3d.py) las reexporta."""
from __future__ import annotations
import math

import numpy as np

from . import view3d as V

FLOATS = 10                       # x y z  nx ny nz  r g b a


# ============================================================================ escena
def tri_poly(P):
    """Triangula un poligono 3D (posiblemente concavo) por ear clipping en su plano -> lista de (i, j, k)."""
    P = np.asarray(P, float)
    n = len(P)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    nv = np.zeros(3)
    for i in range(n):
        nv += np.cross(P[i], P[(i + 1) % n])
    ax = int(np.argmax(np.abs(nv)))
    Q = P[:, [i for i in range(3) if i != ax]]
    area2 = sum(Q[i, 0] * Q[(i + 1) % n, 1] - Q[(i + 1) % n, 0] * Q[i, 1] for i in range(n))
    sgn = 1.0 if area2 > 0 else -1.0

    def cr(a, b, c):
        return (Q[b, 0] - Q[a, 0]) * (Q[c, 1] - Q[a, 1]) - (Q[b, 1] - Q[a, 1]) * (Q[c, 0] - Q[a, 0])
    ids, out, guard = list(range(n)), [], 0
    while len(ids) > 3 and guard < 5000:
        guard += 1
        for k in range(len(ids)):
            a, b, c = ids[k - 1], ids[k], ids[(k + 1) % len(ids)]
            if sgn * cr(a, b, c) <= 1e-12:
                continue
            if any(j not in (a, b, c) and sgn * cr(a, b, j) >= 0 and sgn * cr(b, c, j) >= 0 and sgn * cr(c, a, j) >= 0
                   for j in ids):
                continue
            out.append((a, b, c))
            ids.pop(k)
            break
        else:
            break
    if len(ids) == 3:
        out.append(tuple(ids))
    return out


def _newell(P):
    nv = np.zeros(3)
    for i in range(len(P)):
        nv += np.cross(P[i], P[(i + 1) % len(P)])
    ln = np.linalg.norm(nv)
    return nv / ln if ln > 1e-14 else nv


class Scene:
    """Mallas triangulares (opacas y translucidas), lineas, etiquetas y textos de una vista."""

    def __init__(self):
        self.opaque, self.trans, self.lines = [], [], []
        self.labels = []          # (pos3d, texto, color_texto, fondo, borde, negrita)
        self.hud = []             # (esquina, texto, color, fondo, borde)   esquina: 'tl' | 'bl' | 'br'
        self.markers = []         # (pos3d, color)  estrella sobre el punto maximo
        self.cbar = None          # dict(colors (n,3), vmin, vmax, title, note)
        self.pts = []             # puntos para encuadrar
        self.title = ""
        self.message = None       # (texto, color) si no hay nada que dibujar
        self.group = "other"      # grupo de pieza de lo que se agrega (ver MODE_RULES)
        self.tagged = []          # (grupo, 'o' | 't' | 'l', arreglo)
        self.dims = []            # cotas: dict(a, b, off, text, views)
        self.vlabels = []         # etiquetas que solo aparecen en ciertas vistas: (pos, texto, fg, bg, borde, negrita, vistas)

    # ---------------------------------------------------------------- primitivas
    def add_faces(self, faces, rgb, alpha=1.0, edges=True):
        """Poligonos 3D (lista de listas de (x, y, z)) con sombreado plano y aristas vivas opcionales."""
        tri_rows = []
        edge_map = {}
        col = np.array([*rgb, alpha], float)
        for f in faces:
            P = np.asarray(f, float)
            if len(P) < 3:
                continue
            nrm = _newell(P)
            for (i, j, k) in tri_poly(P):
                for q in (P[i], P[j], P[k]):
                    tri_rows.append(np.concatenate([q, nrm, col]))
            if edges:
                n = len(P)
                for i in range(n):
                    a, b = P[i], P[(i + 1) % n]
                    key = tuple(sorted((tuple(np.round(a, 5)), tuple(np.round(b, 5)))))
                    edge_map.setdefault(key, []).append(nrm)
        if tri_rows:
            arr_ = np.array(tri_rows, np.float32)
            (self.trans if alpha < 0.999 else self.opaque).append(arr_)
            self.tagged.append((self.group, "t" if alpha < 0.999 else "o", arr_))
        if edges and edge_map:
            ec = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           *(([0.3, 0.35, 0.4, 0.55] if alpha < 0.999 else [0.05, 0.07, 0.1, 0.75]))], float)
            seg = []
            for (a, b), ns in edge_map.items():
                sharp = len(ns) == 1 or min(float(ns[0] @ n_) for n_ in ns[1:]) < 0.88
                if sharp:
                    for q in (a, b):
                        seg.append(np.concatenate([q, ec[3:]]))
            if seg:
                arr_ = np.array(seg, np.float32)
                self.lines.append(arr_)
                self.tagged.append((self.group, "l", arr_))

    def add_mesh(self, P, tris, vcol):
        """Malla suave: P (n,3), tris (m,3) indices, vcol (n,4) color por vertice (interpolado)."""
        P = np.asarray(P, np.float32)
        T = np.asarray(tris, np.int64)
        a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        nrm = np.cross(b - a, c - a)
        ln = np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-20)
        nrm = (nrm / ln).astype(np.float32)
        arr = np.zeros((len(T), 3, FLOATS), np.float32)
        for k in range(3):
            arr[:, k, 0:3] = P[T[:, k]]
            arr[:, k, 3:6] = nrm
            arr[:, k, 6:10] = vcol[T[:, k]]
        self.opaque.append(arr.reshape(-1, FLOATS))
        self.tagged.append((self.group, "o", self.opaque[-1]))

    def add_polyline(self, pts, rgb, alpha=1.0):
        seg = []
        c = [0, 0, 0, *rgb, alpha]
        for a, b in zip(pts[:-1], pts[1:]):
            seg.append([*a, *c])
            seg.append([*b, *c])
        if seg:
            self.lines.append(np.array(seg, np.float32))

    def add_tris(self, tris, rgb):
        """Triangulos sueltos (conos de flecha)."""
        faces = [list(t) for t in tris]
        self.add_faces(faces, rgb, 1.0, edges=False)

    def add_arrow(self, tail, head, rgb, rad):
        d = np.array(head, float) - np.array(tail, float)
        L = float(np.linalg.norm(d))
        if L < 1e-9:
            return
        u_ = d / L
        hl = 0.18 * L
        base = np.array(head) - u_ * hl
        self.add_faces(V._bar_faces(tail, base, rad), rgb, 1.0, edges=False)
        self.add_tris(V._cone(head, u_, hl, 0.42 * hl), rgb)

    def add_loads(self, items):
        from matplotlib.colors import to_rgb
        for it in items:
            if it[0] == "arrow":
                _, a, b, color, label, far = it
                rgb = to_rgb(color)
                L = float(np.linalg.norm(np.array(b) - np.array(a)))
                self.add_arrow(a, b, rgb, 0.02 * L)
                self.labels.append((far, label, color, "#ffffffd9", color, True))
            else:
                _, P_, color, label = it
                rgb = to_rgb(color)
                rad = float(np.linalg.norm(np.array(P_[0]) - np.array(P_[len(P_) // 2]))) / 1.6
                for p0, p1 in zip(P_[:-1], P_[1:]):
                    self.add_faces(V._bar_faces(p0, p1, 0.035 * rad), rgb, 1.0, edges=False)
                p_end, p_prev = np.array(P_[-1]), np.array(P_[-4])
                dirv = (p_end - p_prev) / max(np.linalg.norm(p_end - p_prev), 1e-12)
                hl = 0.30 * rad
                self.add_tris(V._cone(p_end + dirv * hl, dirv, hl, 0.42 * hl), rgb)
                centre = 0.5 * (np.array(P_[0]) + np.array(P_[-1]))
                out_ = p_end - centre
                out_[2] = 0.0
                out_ = out_ / max(np.linalg.norm(out_), 1e-12)
                pos = p_end + out_ * 0.55 * rad + np.array([0.0, 0.0, -0.35 * rad])
                self.labels.append((tuple(pos), label, color, "#ffffffd9", color, True))

    # ---------------------------------------------------------------- empaquetado
    def packed(self, mode=None):
        """Mallas opacas, translucidas y lineas segun la vista (MODE_RULES): grupos ocultos o en gris tenue."""
        o, t, l = [], [], []
        rules = MODE_RULES.get(mode, {})
        for grp, kind, arr in self.tagged:
            how = rules.get(grp, "show")
            if how == "hide":
                continue
            if how == "ghost":
                # fantasma: relleno tenue del color de la pieza y contorno nitido (se lee la huella del perfil sobre la placa)
                fill, edge = GHOST.get(grp, ((0.55, 0.58, 0.62), (0.30, 0.33, 0.38)))
                g = arr.copy()
                if kind == "l":
                    g[:, 6:9] = edge
                    g[:, 9] = 0.95
                    l.append(g)
                else:
                    g[:, 6:9] = fill
                    g[:, 9] = 0.42
                    t.append(g)
                continue
            {"o": o, "t": t, "l": l}[kind].append(arr)

        def cat(lst):
            return np.concatenate(lst).astype(np.float32) if lst else np.zeros((0, FLOATS), np.float32)
        return cat(o), cat(t), cat(l)

    def bounds_points(self, mode=None, dims=False):
        pts = []
        if len(self.pts) > 0:
            pts.append(np.asarray(self.pts, float))
        else:
            rules = MODE_RULES.get(mode, {})
            for grp, kind, arr in self.tagged:
                if kind == "l" or rules.get(grp, "show") == "hide":
                    continue
                step = max(1, len(arr) // 1500)
                pts.append(arr[::step, :3].astype(float))
        if dims:
            for d in self.dims:
                if mode in d["views"]:
                    q = np.array([d["a"], d["b"]], float)
                    pts += [q + np.asarray(d["off"], float) * 1.7]
        return np.concatenate(pts) if pts else np.zeros((1, 3))

    # ---------------------------------------------------------------- cotas
    def add_dim(self, a, b, off, text, views, tshift=(0.0, 0.0, 0.0)):
        """Cota entre a y b, con su linea desplazada `off`; `tshift` mueve solo el texto (evita solapes en cotas cortas)."""
        self.dims.append(dict(a=tuple(a), b=tuple(b), off=tuple(off), text=text, views=set(views), tshift=tuple(tshift)))

    def dim_segments(self, mode, arrow):
        """Lineas (pares de puntos) y textos de las cotas visibles en `mode`: lineas de extension, linea de cota y
        puntas de flecha.  -> (arreglo de vertices (n, FLOATS), [(pos3d, texto)])"""
        seg, texts = [], []
        col = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25, 0.28, 0.32, 1.0]

        def add(p, q):
            for r in (p, q):
                row = list(r) + col[3:]
                seg.append(row)
        for d in self.dims:
            if mode not in d["views"]:
                continue
            a, b, off = np.array(d["a"], float), np.array(d["b"], float), np.array(d["off"], float)
            if np.linalg.norm(off) < 1e-9 or np.linalg.norm(b - a) < 1e-9:
                continue
            q1, q2 = a + off, b + off
            o = off / np.linalg.norm(off)
            t = (q2 - q1) / np.linalg.norm(q2 - q1)
            add(a + off * 0.12, q1 + o * 0.5 * arrow * 2)
            add(b + off * 0.12, q2 + o * 0.5 * arrow * 2)
            add(q1, q2)
            for tip, sg in ((q1, 1.0), (q2, -1.0)):
                add(tip, tip + sg * t * arrow + o * 0.35 * arrow)
                add(tip, tip + sg * t * arrow - o * 0.35 * arrow)
            texts.append((tuple((q1 + q2) / 2 + np.array(d.get("tshift", (0, 0, 0)), float)), d["text"]))
        return np.array(seg, np.float32).reshape(-1, FLOATS), texts


GHOST = {"column": ((0.36, 0.55, 0.78), (0.10, 0.25, 0.50)),      # (relleno, contorno) de las piezas en gris tenue
         "stiff": ((0.45, 0.72, 0.40), (0.20, 0.45, 0.18))}

# vistas: grupo -> 'show' | 'ghost' | 'hide'.  Planta: solo la placa y el mortero, la columna y los rigidizadores en gris tenue
MODE_RULES = {
    "plan": {"column": "ghost", "stiff": "ghost", "bolts": "hide", "lug": "hide", "ubar": "hide", "load": "hide"},
}


# ============================================================================ escenas del modelo
def scene_geometry(prj, loads=False, show_concrete=True):
    from matplotlib.colors import to_rgb
    sc = Scene()
    kl = prj.units().fl
    allp = []
    for part in V.geometry_faces(prj):
        grp, faces, color, alpha = part[:4]
        tag = part[5] if len(part) > 5 else "other"
        if not faces or (grp == "conc" and not show_concrete):
            continue
        v_ = [[(x / kl, y / kl, z / kl) for x, y, z in f] for f in faces]
        allp += [pt for f in v_ for pt in f]
        sc.group = tag
        sc.add_faces(v_, to_rgb(color), alpha, edges=True)
    sc.group = "other"
    sc.pts = allp
    if loads:
        items, lpts = V.load_arrows(prj, kl)
        sc.group = "load"
        sc.add_loads(items)
        sc.group = "other"
        for lab in sc.labels:                    # las flechas y sus etiquetas no se ven en planta
            sc.vlabels.append((*lab, {"iso", "free", "front", "side"}))
        sc.labels = []
        sc.pts = allp + [tuple(p) for p in lpts]
    try:
        _build_dims(sc, prj, kl)
    except Exception:
        sc.dims = []
    return sc


def _build_dims(sc, prj, kl):
    """Cotas por vista (planta, frontal, lateral, isometrica).  Coordenadas en la unidad mostrada; los valores se
    escriben con el modulo de unidades del proyecto."""
    from . import geometry as G
    from .params3d import washer_thickness
    u = prj.units()
    p, b = prj.plate, prj.bolts
    g = b.geom()
    circ = p.shape == "Circular"
    B = (p.Dp if circ else p.B) / kl
    N = (p.Dp if circ else p.N) / kl
    tp, gr = p.tp / kl, max(0.0, p.grout) / kl
    so = max(0.0, float(getattr(b, "standoff", 0.0))) / kl
    hef = max(float(b.hef), 1.0) / kl
    zs = -(gr + so)
    tw = max(washer_thickness(prj), 0.0) / kl
    ztop = tp + tw + 1.25 * g.db / kl
    bpos = G.bolt_positions(prj)
    xs = sorted({round(x / kl, 4) for x, _ in bpos})
    ys = sorted({round(y / kl, 4) for _, y in bpos})
    q = lambda v: u.fmt("L", v * kl) + " " + u.L            # longitud en unidades del proyecto
    Lm = max(B, N)
    d = 0.085 * Lm                                           # separacion base de la linea de cota
    R = ("plan",)

    # ---------------- PLANTA: placa (o diametro), cadenas de pernos y numeracion
    if circ:
        sc.add_dim((-B / 2, -N / 2, tp), (B / 2, -N / 2, tp), (0, -1.6 * d, 0), "Ø " + q(B), R)
    else:
        sc.add_dim((-B / 2, -N / 2, tp), (B / 2, -N / 2, tp), (0, -1.6 * d, 0), "B = " + q(B), R)
        sc.add_dim((B / 2, -N / 2, tp), (B / 2, N / 2, tp), (1.6 * d, 0, 0), "N = " + q(N), R)
    if not circ and 0 < len(xs) <= 7 and 0 < len(ys) <= 7:
        ch = [-B / 2] + xs + [B / 2]
        for a_, b_ in zip(ch[:-1], ch[1:]):
            if b_ - a_ > 1e-6:
                sc.add_dim((a_, N / 2, tp), (b_, N / 2, tp), (0, 0.9 * d, 0), q(b_ - a_), R)
        cv = [-N / 2] + ys + [N / 2]
        for a_, b_ in zip(cv[:-1], cv[1:]):
            if b_ - a_ > 1e-6:
                sc.add_dim((-B / 2, a_, tp), (-B / 2, b_, tp), (-0.9 * d, 0, 0), q(b_ - a_), R)
    for i, (x, y) in enumerate(bpos):
        sc.vlabels.append(((x / kl, y / kl, tp), f"P{i + 1}", "#00407a", "#ffffffd9", None, True, {"plan"}))

    # ---------------- FRONTAL (eje horizontal X) y LATERAL (eje horizontal Y)
    def elev(view, hx, ext, plane, mk):
        """hx: coordenadas de los pernos en el eje horizontal; ext: semiancho de la placa en ese eje;
        mk(h, z) -> punto 3D; plane = otro semiancho (para colocar las cotas del lado visible)."""
        V_ = (view,)
        zb = zs - hef
        dv = 0.09 * max(ext * 2, hef)
        # hef: desde la superficie del concreto hasta el extremo del anclaje
        sc.add_dim(mk(ext, zs), mk(ext, zb), (dv, 0, 0) if view == "front" else (0, dv, 0), "hef = " + q(hef), V_ + (("iso", "free") if view == "front" else ()))
        fx = (lambda v: (v, 0, 0)) if view == "front" else (lambda v: (0, v, 0))
        up_, dn_ = 0.045 * hef, -0.045 * hef
        sc.add_dim(mk(ext, 0.0), mk(ext, tp), fx(dv), "tp = " + q(tp), V_, tshift=(*fx(0.7 * dv)[:2], up_ + 0.5 * tp)
                   if view == "front" else (0, 0.7 * dv, up_ + 0.5 * tp))
        if gr > 1e-9:
            sc.add_dim(mk(ext, zs), mk(ext, zs + gr), fx(dv), "mortero = " + q(gr), V_,
                       tshift=(0.8 * dv, 0, dn_) if view == "front" else (0, 0.8 * dv, dn_))
        if so > 1e-9:
            sc.add_dim(mk(ext, zs + gr), mk(ext, 0.0), fx(dv), "stand-off = " + q(so), V_,
                       tshift=(0.8 * dv, 0, dn_ * 0.2) if view == "front" else (0, 0.8 * dv, dn_ * 0.2))
        # longitud total del anclaje (de la punta al extremo roscado)
        sc.add_dim(mk(-ext, zb), mk(-ext, ztop), (-dv, 0, 0) if view == "front" else (0, -dv, 0),
                   "L anclaje = " + q(ztop - zb), V_)
        # ancho de la placa en esta vista
        sc.add_dim(mk(-ext, tp), mk(ext, tp), (0, 0, 1.4 * dv), ("B = " if view == "front" else "N = ") + q(2 * ext), V_)
        # cadena de pernos bajo el anclaje
        if hx and len(hx) <= 7:
            ch = [-ext] + hx + [ext]
            for a_, b_ in zip(ch[:-1], ch[1:]):
                if b_ - a_ > 1e-6:
                    sc.add_dim(mk(a_, zb), mk(b_, zb), (0, 0, -1.2 * dv), q(b_ - a_), V_)
        # gancho
        if "Gancho" in b.atype and hx:
            eh = (b.eh if b.eh > 0 else 3 * g.db) / kl
            xr = max(hx)
            if xr > 0:
                sc.add_dim(mk(xr, zb), mk(xr + eh, zb), (0, 0, -2.2 * dv), "eh = " + q(eh), V_)
    # refuerzo del arrancamiento (barras U u Omega): longitudes sobre y bajo el cono de falla
    from .ubar import ubar
    ub = ubar(prj)
    if ub is not None:
        z0 = zs - ub["depth"] / kl
        zc = zs - ub["z_cross"] / kl
        zb2 = z0 - ub["leg"] / kl
        xl = ub["xl"] / kl
        y0 = -N / 2 - 0.01 * Lm
        dv0 = 0.09 * max(B, hef)
        nm = "ldh" if ub["kind"] == "OMEGA" else "ld"
        sc.add_dim((xl, y0, zc), (xl, y0, zb2), (-0.55 * dv0, 0, 0),
                   f"{nm} bajo la punta = " + q(ub["below"] / kl), ("front",), tshift=(-0.9 * dv0, 0, 0))
        # de la parte superior de la barra (tramo horizontal) a la punta inferior del anclaje
        xr = ub["xr"] / kl
        zb_anchor = zs - hef
        sc.add_dim((xr, y0, z0), (xr, y0, zb_anchor), (1.1 * dv0, 0, 0),
                   "U a punta del anclaje = " + q(abs(z0 - zb_anchor)), ("front", "iso", "free"),
                   tshift=(0.9 * dv0, 0, -0.12 * hef))
    if not circ:
        y0 = -N / 2 - 0.01 * Lm
        elev("front", xs, B / 2, N / 2, lambda h, z: (h, y0, z))
        x0 = B / 2 + 0.01 * Lm
        elev("side", ys, N / 2, B / 2, lambda h, z: (x0, h, z))
        # isometrica: hef y tp ya van en 'front' con las etiquetas iso/free; B y N sobre la placa
        sc.add_dim((-B / 2, -N / 2, tp), (B / 2, -N / 2, tp), (0, -d, 0), "B = " + q(B), ("iso", "free"))
        sc.add_dim((B / 2, -N / 2, tp), (B / 2, N / 2, tp), (d, 0, 0), "N = " + q(N), ("iso", "free"))
    else:
        for view in ("front", "side"):
            y0 = -N / 2 - 0.01 * Lm
            mk = (lambda h, z: (h, y0, z)) if view == "front" else (lambda h, z: (B / 2 + 0.01 * Lm, h, z))
            zb = zs - hef
            dv = 0.09 * max(B, hef)
            sc.add_dim(mk(B / 2, zs), mk(B / 2, zb), (dv, 0, 0) if view == "front" else (0, dv, 0), "hef = " + q(hef), (view,))
            sc.add_dim(mk(B / 2, 0.0), mk(B / 2, tp), (dv, 0, 0) if view == "front" else (0, dv, 0), "tp = " + q(tp), (view,))
            sc.add_dim(mk(-B / 2, zb), mk(-B / 2, ztop), (-dv, 0, 0) if view == "front" else (0, -dv, 0),
                       "L anclaje = " + q(ztop - zb), (view,))


def scene_results(res, prj, field="vm", scale=0.0, part="all", bolts=None, loads=False):
    """Escena del campo de resultados (misma logica de datos que view3d.plot3d)."""
    sc = Scene()
    u = prj.units()
    kl, ks = u.fl, u.fs
    if res is None or not res.ok:
        sc.message = ("Sin resultados 3D.", "#777777")
        return sc
    tris = res.tris if part == "all" else res.parts.get(part, [])
    if not tris:
        sc.message = (f"Sin elementos de tipo '{V.PART_LABELS.get(part, part)}' en este modelo.", "#777777")
        return sc
    ids = sorted({n for t in tris for n in t})
    idx = {n: i for i, n in enumerate(ids)}
    P = np.array([res.nodes[n] for n in ids], dtype=float)
    if scale > 0 and res.disp:
        P = P + scale * np.array([res.disp.get(n, (0, 0, 0)) for n in ids], dtype=float)
    if field == "u":
        val = np.array([math.sqrt(sum(c * c for c in res.disp.get(n, (0, 0, 0)))) for n in ids]) / kl
        title, cmap, unit = "Desplazamiento |U|", V._soft_cmap(), u.L
    elif field == "uz":
        val = np.array([res.disp.get(n, (0, 0, 0))[2] for n in ids]) / kl
        title, cmap, unit = "Desplazamiento vertical Uz", V._soft_cmap(True), u.L
    else:
        val = np.array([res.vm.get(n, 0.0) for n in ids]) / ks
        title, cmap, unit = "Esfuerzo de von Mises", V._soft_cmap(), u.S
    T = np.array([[idx[a], idx[b], idx[c]] for a, b, c in tris], dtype=np.int64)
    fv = val[T].mean(axis=1)
    vmin, vmax = float(fv.min()), float(fv.max())
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    # el color se interpola entre vertices; la escala es la de los valores de cara, igual que en matplotlib
    vcol = cmap(np.clip((val - vmin) / (vmax - vmin), 0.0, 1.0))
    Pm = P / kl
    sc.add_mesh(Pm, T, vcol)
    pts = [Pm]
    if loads:
        items, lpts = V.load_arrows(prj, kl, ztop=max(c_[2] for c_ in res.nodes.values()))
        sc.add_loads(items)
        pts.append(np.array(lpts))
    sc.pts = np.vstack(pts)
    span = float((sc.pts.max(axis=0) - sc.pts.min(axis=0)).max())
    k = int(np.argmax(val))
    mx, my_, mz = Pm[k]
    plastic = bool(getattr(res, "peeq", None))
    avg = None
    if field == "vm" and not plastic:
        avg = res.vm_avg if part in ("all", "plate") else res.part_avg.get(part)
    if avg:
        mx, my_, mz = avg["x"] / kl, avg["y"] / kl, avg["z"] / kl
    sc.markers.append(((mx, my_, mz), "#d62728"))
    lbl = {"vm": "Esfuerzo maximo", "u": "Desplazamiento maximo", "uz": "Uz maximo"}.get(field, "Maximo")
    if avg:
        txt = (f"Esfuerzo maximo (promediado, r = {avg['radius'] / kl:.2g} {u.L}) = {avg['vm'] / ks:.4g} {unit}\n"
               f"pico puntual {avg['vm_point'] / ks:.4g} {unit} (depende de la malla)"
               + ("" if part in ("all", "plate") else
                  "\nReferencia: la singularidad en el extremo del rigidizador persiste;\n"
                  "la malla rapida subestima ~15 %. No usar para verificar"))
    else:
        txt = (f"{lbl}" + (f" — {V.PART_LABELS[part]}" if part != "all" else "") + f" = {val[k]:.4g} {unit}"
               + ("   (pico puntual: depende de la malla)" if field == "vm" else f"   (nodo {ids[k]})"))
    note = None
    if plastic:
        note = f"{lbl.replace(' maximo', '')}\nmaximo\n{val[k]:.4g} {unit}"
    else:
        sc.hud.append(("bl", txt, "#7a1010", "#fff3e0", "#d62728"))
    if bolts and part == "plate":
        zt = float(Pm[:, 2].max()) + 0.02 * span
        Tmax = max(b[3] for b in bolts)
        for kb, bx, by, T_ in bolts:
            hot = T_ >= Tmax - 1e-9 and Tmax > 1e-9
            sc.labels.append(((bx / kl, by / kl, zt), f"P{kb}\n{u.fmt('F', T_)}",
                              "#ffffff" if hot else "#08306b", "#d62728" if hot else "#ffffffd9",
                              "#d62728" if hot else "#08306b", hot))
        sc.hud.append(("bl2", f"Etiquetas: P# y traccion del perno ({u.F}); en rojo, el mas exigido",
                       "#444444", None, None))
    sc.title = (f"{title}  ({unit})" + (f" — {V.PART_LABELS[part]}" if part != "all" else "")
                + (f"   —  deformada ×{scale:g}" if scale > 0 else ""))
    cols = cmap(np.linspace(0, 1, 64))[:, :3]
    sc.cbar = dict(colors=cols, vmin=vmin, vmax=vmax, note=note)
    return sc
