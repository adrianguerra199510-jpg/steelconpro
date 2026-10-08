# -*- coding: utf-8 -*-
"""Visor 3D en tiempo real (OpenGL via Qt): rotacion fluida con orden de profundidad exacto (z-buffer por pixel).

Si el equipo no ofrece OpenGL >= 2.1 (o se define PB_NO_GL=1) la aplicacion usa el visor matplotlib de siempre.
Las escenas se construyen con las mismas funciones de geometria que usa la memoria de calculo (view3d)."""
from __future__ import annotations
import math
import os

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import (QColor, QFont, QPainter, QPen, QPolygonF, QSurfaceFormat, QMatrix4x4,
                           QOpenGLContext, QOffscreenSurface, QImage, QPainterPath)
from PySide6.QtOpenGL import QOpenGLShaderProgram, QOpenGLShader, QOpenGLBuffer
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QToolBar, QToolButton, QSizePolicy, QFileDialog)

from . import view3d as V

# constantes de OpenGL (valores estandar)
GL_DEPTH_TEST, GL_BLEND, GL_POLYGON_OFFSET_FILL = 0x0B71, 0x0BE2, 0x8037
GL_TRIANGLES, GL_LINES, GL_FLOAT = 0x0004, 0x0001, 0x1406
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT = 0x4000, 0x0100
GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_LEQUAL, GL_ONE = 0x0302, 0x0303, 0x0203, 0x0001

FLOATS = 10                       # x y z  nx ny nz  r g b a
_VERT = """#version 120
attribute vec3 aPos; attribute vec3 aNor; attribute vec4 aCol;
uniform mat4 uMVP; uniform vec3 uCam; uniform vec3 uL;
varying vec4 vCol;
void main(){
  float k = 1.0;
  float l = length(aNor);
  if (l > 0.5) {
    vec3 n = aNor / l;
    if (dot(n, uCam) < 0.0) n = -n;
    k = 0.45 + 0.35 * max(dot(n, uL), 0.0) + 0.25 * max(dot(n, uCam), 0.0);
  }
  vCol = vec4(aCol.rgb * min(k, 1.0), aCol.a);
  gl_Position = uMVP * vec4(aPos, 1.0);
}
"""
_FRAG = """#version 120
varying vec4 vCol;
void main(){ gl_FragColor = vCol; }
"""


# ============================================================================ disponibilidad
_AVAIL = None
SOFTWARE = False


def available() -> bool:
    """True si se puede abrir un contexto OpenGL >= 2.1 y compilar el shader (se comprueba una sola vez)."""
    global _AVAIL
    if _AVAIL is not None:
        return _AVAIL
    _AVAIL = False
    if os.environ.get("PB_NO_GL") == "1":
        return False
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None or app.platformName() in ("offscreen", "minimal"):
            return False
        fmt = QSurfaceFormat.defaultFormat()
        surf = QOffscreenSurface()
        surf.setFormat(fmt)
        surf.create()
        ctx = QOpenGLContext()
        ctx.setFormat(fmt)
        if not (ctx.create() and surf.isValid() and ctx.makeCurrent(surf)):
            return False
        try:
            f = ctx.format()
            if (f.majorVersion(), f.minorVersion()) < (2, 1):
                return False
            try:        # render por software (sin GPU): se desactiva el suavizado 4x para mantener > 30 fps
                gl = ctx.functions()
                gl.initializeOpenGLFunctions()
                ren = str(gl.glGetString(0x1F01) or "").lower()
                global SOFTWARE
                SOFTWARE = any(k in ren for k in ("llvmpipe", "software", "gdi generic", "basic render", "swrast"))
                if SOFTWARE:
                    nf = QSurfaceFormat.defaultFormat()
                    nf.setSamples(0)
                    QSurfaceFormat.setDefaultFormat(nf)
            except Exception:
                pass
            prog = QOpenGLShaderProgram()
            ok = (prog.addShaderFromSourceCode(QOpenGLShader.Vertex, _VERT)
                  and prog.addShaderFromSourceCode(QOpenGLShader.Fragment, _FRAG) and prog.link())
            _AVAIL = bool(ok)
        finally:
            ctx.doneCurrent()
    except Exception:
        _AVAIL = False
    return _AVAIL


def set_default_format():
    """Debe llamarse ANTES de crear la QApplication: contexto 2.1 con z-buffer de 24 bits y suavizado 4x."""
    f = QSurfaceFormat()
    f.setVersion(2, 1)
    f.setDepthBufferSize(24)
    f.setSamples(4)
    f.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(f)


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


# ============================================================================ visor
def _qcolor(c):
    """'#rrggbb' o '#rrggbbaa' (alfa al final, como matplotlib) -> QColor."""
    if isinstance(c, str) and len(c) == 9 and c.startswith("#"):
        q = QColor("#" + c[1:7])
        q.setAlpha(int(c[7:9], 16))
        return q
    return QColor(c)


class GLView(QOpenGLWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setFocusPolicy(Qt.StrongFocus)
        self.scene = Scene()
        self.elev, self.azim = 24.0, -58.0
        self.dist = 1.0            # distancia de la camara (o escala ortografica)
        self.pan = np.zeros(3)
        self.center = np.zeros(3)
        self.persp = True
        self.mode = "iso"          # iso | plan | front | side | free   (define que piezas y cotas se ven)
        self.dims_on = True
        self.radius = 1.0
        self.fov = 28.0
        self._last = None
        self._user = False
        self._dirty = True
        self._prog = None
        self._bufs = None
        self.frames = 0
        self.setToolTip("Izquierdo: girar    Derecho o central: desplazar    Rueda: zoom    Doble clic: encuadrar")

    # ------------------------------------------------------------------ camara
    def _cam_dir(self):
        e, a = math.radians(self.elev), math.radians(self.azim)
        return np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])

    def _view_proj(self):
        w, h = max(self.width(), 1), max(self.height(), 1)
        asp = w / h
        d = self._cam_dir()
        tgt = self.center + self.pan
        eye = tgt + d * self.dist
        z = d
        x = np.cross([0, 0, 1.0], z)
        x /= max(np.linalg.norm(x), 1e-12)
        y = np.cross(z, x)
        V_ = np.eye(4)
        V_[0, :3], V_[1, :3], V_[2, :3] = x, y, z
        V_[:3, 3] = -V_[:3, :3] @ eye
        R = max(self.radius, 1e-6)
        near, far = max(self.dist - 1.6 * R, 0.02 * self.dist), self.dist + 1.6 * R
        if self.persp and self.mode in ("iso", "free"):
            f = 1.0 / math.tan(math.radians(self.fov) / 2)
            P_ = np.zeros((4, 4))
            P_[0, 0], P_[1, 1] = f / asp, f
            P_[2, 2], P_[2, 3] = (far + near) / (near - far), 2 * far * near / (near - far)
            P_[3, 2] = -1.0
        else:
            hh = self.dist * math.tan(math.radians(self.fov) / 2)
            P_ = np.zeros((4, 4))
            P_[0, 0], P_[1, 1] = 1.0 / (hh * asp), 1.0 / hh
            P_[2, 2], P_[2, 3] = -2.0 / (far - near), -(far + near) / (far - near)
            P_[3, 3] = 1.0
        return P_ @ V_

    def fit(self):
        """Encuadra el modelo: ocupa ~90 % del ancho o del alto disponibles."""
        pts = self.scene.bounds_points(self.mode, self.dims_on)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        self.center = (lo + hi) / 2
        self.radius = float(np.linalg.norm(hi - lo)) / 2 or 1.0
        self.pan = np.zeros(3)
        sub = pts[:: max(1, len(pts) // 3000)]
        self.dist = self.radius * 3.0
        for _ in range(6):
            M = self._view_proj()
            q = np.c_[sub, np.ones(len(sub))] @ M.T
            ndc = q[:, :2] / np.maximum(q[:, 3:4], 1e-9)
            ext = float(np.abs(ndc).max()) or 1.0
            k = ext / 0.92
            if self.persp and self.mode in ("iso", "free"):
                # al acercar la camara el escorzo cambia: iteracion sobre la distancia al centro
                self.dist = max(self.dist * k, self.radius * 0.5)
            else:
                self.dist *= k
        self.update()

    MODES = {"iso": (24.0, -58.0), "plan": (89.9, -90.0), "front": (0.0, -90.0), "side": (0.0, 0.0)}

    def set_mode(self, mode):
        """Vista estandar: define la camara, las piezas visibles y las cotas.  Planta, frontal y lateral son ortograficas."""
        self.mode = mode
        self.elev, self.azim = self.MODES.get(mode, self.MODES["iso"])
        self._dirty = True
        self._user = False
        self.fit()

    def set_dims(self, on):
        self.dims_on = bool(on)
        self._dirty = True
        self.update()

    def set_view(self, elev, azim):
        self.elev, self.azim = float(elev), float(azim)
        self.update()

    # ------------------------------------------------------------------ escena
    def set_scene(self, scene: Scene, keep_view=True):
        """Cambia la escena.  Si ya habia una vista (o el usuario la movio), la camara se conserva: solo se ajusta
        proporcionalmente al nuevo tamano del modelo, sin saltos al editar.  El primer dibujo, o 'Encuadrar', re-encuadra."""
        first = not getattr(self, "_has_scene", False)
        old_r, old_c = self.radius, self.center.copy()
        self.scene = scene
        self._dirty = True
        pts = scene.bounds_points(self.mode, self.dims_on)
        if first or len(pts) < 2 or not keep_view:
            self._has_scene = len(pts) >= 2
            self.radius = 1.0
            self.fit()
            return
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        new_c, new_r = (lo + hi) / 2, float(np.linalg.norm(hi - lo)) / 2 or 1.0
        k = new_r / max(old_r, 1e-9)
        if abs(k - 1.0) > 0.02 or float(np.linalg.norm(new_c - old_c)) > 0.02 * old_r:
            self.dist *= k                      # el modelo cambio de tamano: mismo encuadre relativo
        self.radius, self.center = new_r, new_c
        self.update()

    # ------------------------------------------------------------------ OpenGL
    def initializeGL(self):
        self.gl = self.context().functions()
        self.gl.initializeOpenGLFunctions()
        prog = QOpenGLShaderProgram(self)
        prog.addShaderFromSourceCode(QOpenGLShader.Vertex, _VERT)
        prog.addShaderFromSourceCode(QOpenGLShader.Fragment, _FRAG)
        prog.bindAttributeLocation("aPos", 0)
        prog.bindAttributeLocation("aNor", 1)
        prog.bindAttributeLocation("aCol", 2)
        prog.link()
        self._prog = prog
        self._bufs = [QOpenGLBuffer(QOpenGLBuffer.VertexBuffer) for _ in range(4)]
        for b in self._bufs:
            b.create()
        self._counts = [0, 0, 0, 0]

    def _upload(self):
        o, t, l = self.scene.packed(self.mode)
        arrow = 0.022 * max(self.radius, 1e-6)
        dl, self._dim_texts = (self.scene.dim_segments(self.mode, arrow) if self.dims_on
                               else (np.zeros((0, FLOATS), np.float32), []))
        for b, arr, i in zip(self._bufs, (o, t, l, dl), range(4)):
            b.bind()
            data = np.ascontiguousarray(arr, np.float32)
            b.allocate(data.tobytes(), data.nbytes)
            b.release()
            self._counts[i] = len(arr)
        self._dirty = False

    def _draw_buf(self, i, mode):
        n = self._counts[i]
        if n == 0:
            return
        gl, prog = self.gl, self._prog
        self._bufs[i].bind()
        st = FLOATS * 4
        for loc, off, size in ((0, 0, 3), (1, 12, 3), (2, 24, 4)):
            prog.enableAttributeArray(loc)
            prog.setAttributeBuffer(loc, GL_FLOAT, off, size, st)
        gl.glDrawArrays(mode, 0, n)
        for loc in (0, 1, 2):
            prog.disableAttributeArray(loc)
        self._bufs[i].release()

    def resizeGL(self, w, h):
        if not self._user and len(self.scene.bounds_points(self.mode, self.dims_on)) > 1:
            self.fit()

    def paintGL(self):
        gl = self.gl
        for cap in (GL_BLEND, 0x0B44, 0x0C11, 0x0B90):        # Qt/QPainter dejan estados: mezcla, cull, scissor, stencil
            gl.glDisable(cap)
        gl.glDepthMask(True)
        gl.glColorMask(True, True, True, True)
        gl.glClearColor(1, 1, 1, 1)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._dirty:
            self._upload()
        M = self._view_proj()
        if sum(self._counts):
            prog = self._prog
            prog.bind()
            prog.setUniformValue("uMVP", QMatrix4x4(*[float(v) for v in M.flatten()]))
            c = self._cam_dir()
            prog.setUniformValue("uCam", float(c[0]), float(c[1]), float(c[2]))
            L = np.array([0.35, -0.5, 0.8])
            L /= np.linalg.norm(L)
            prog.setUniformValue("uL", float(L[0]), float(L[1]), float(L[2]))
            gl.glEnable(GL_DEPTH_TEST)
            gl.glDepthFunc(GL_LEQUAL)
            gl.glEnable(GL_POLYGON_OFFSET_FILL)
            gl.glPolygonOffset(1.0, 1.0)
            self._draw_buf(0, GL_TRIANGLES)                    # acero opaco
            gl.glDisable(GL_POLYGON_OFFSET_FILL)
            gl.glEnable(GL_BLEND)                              # el alfa del framebuffer se conserva en 1
            gl.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
            self._draw_buf(2, GL_LINES)                        # aristas vivas
            gl.glDepthMask(False)
            self._draw_buf(1, GL_TRIANGLES)                    # concreto translucido (sin escribir profundidad)
            gl.glDepthMask(True)
            gl.glDisable(GL_DEPTH_TEST)                        # las cotas van siempre encima
            self._draw_buf(3, GL_LINES)
            gl.glDisable(GL_BLEND)
            prog.release()
        self._overlay(M)
        self.frames += 1

    # ------------------------------------------------------------------ superposicion (texto)
    def _project(self, M, p):
        q = M @ np.array([p[0], p[1], p[2], 1.0])
        if q[3] <= 1e-9:
            return None
        return QPointF((q[0] / q[3] * 0.5 + 0.5) * self.width(), (1 - (q[1] / q[3] * 0.5 + 0.5)) * self.height())

    def _box(self, pt, text, fg, bg, border, bold, anchor="c"):
        f = QFont()
        f.setPointSizeF(8.5)
        f.setBold(bold)
        pt.setFont(f)
        fm = pt.fontMetrics()
        lines = text.split("\n")
        w = max(fm.horizontalAdvance(s) for s in lines) + 10
        h = fm.height() * len(lines) + 6
        return f, lines, w, h, fm

    def _draw_box(self, p, x, y, text, fg, bg, border, bold=False):
        f, lines, w, h, fm = self._box(p, text, fg, bg, border, bold)
        r = QRectF(x - w / 2, y - h / 2, w, h)
        if bg:
            p.setBrush(_qcolor(bg))
            p.setPen(QPen(_qcolor(border), 1.0) if border else Qt.NoPen)
            p.drawRoundedRect(r, 4, 4)
        p.setPen(_qcolor(fg))
        p.drawText(r, Qt.AlignCenter, text)

    def _overlay(self, M):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        sc = self.scene
        W, H = self.width(), self.height()
        for pos, text, fg, bg, border, bold in sc.labels:
            q = self._project(M, pos)
            if q is not None:
                self._draw_box(p, q.x(), q.y() - 10, text, fg, bg, border, bold)
        vm = "iso" if self.mode == "free" else self.mode
        for pos, text, fg, bg, border, bold, views in sc.vlabels:
            if self.mode in views:
                q = self._project(M, pos)
                if q is not None:
                    self._draw_box(p, q.x(), q.y() + 12, text, fg, bg, border, bold)
        if self.dims_on:
            for pos, text in getattr(self, "_dim_texts", []):
                q = self._project(M, pos)
                if q is not None:
                    self._draw_box(p, q.x(), q.y(), text, "#2b3138", "#ffffffee", None, False)
        for pos, color in sc.markers:
            q = self._project(M, pos)
            if q is not None:
                star = QPolygonF()
                for i in range(10):
                    r = 9 if i % 2 == 0 else 4
                    a = math.pi / 2 + i * math.pi / 5
                    star.append(QPointF(q.x() + r * math.cos(a), q.y() - r * math.sin(a)))
                p.setBrush(QColor(color))
                p.setPen(QPen(QColor("black"), 1.0))
                p.drawPolygon(star)
        if sc.title:
            f = QFont(); f.setPointSizeF(9); p.setFont(f)
            p.setPen(QColor("#222222"))
            p.drawText(8, 16, sc.title)
        y_bl = H - 8
        for corner, text, fg, bg, border in sc.hud:
            f = QFont(); f.setPointSizeF(8.5); f.setBold(bg is not None); p.setFont(f)
            fm = p.fontMetrics()
            lines = text.split("\n")
            w = max(fm.horizontalAdvance(s) for s in lines) + 12
            h = fm.height() * len(lines) + 8
            if corner == "bl2":
                p.setPen(_qcolor(fg))
                p.drawText(QRectF(8, H - h - 2, w + 10, h), Qt.AlignLeft | Qt.AlignVCenter, text)
                continue
            r = QRectF(8, y_bl - h - 22, w, h)
            if bg:
                p.setBrush(_qcolor(bg)); p.setPen(QPen(_qcolor(border), 1.0))
                p.drawRoundedRect(r, 4, 4)
            p.setPen(_qcolor(fg))
            p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, text)
        if sc.cbar:
            cb = sc.cbar
            x0, x1 = W - 70, W - 52
            y0, y1 = H * 0.18, H * 0.82
            cols = cb["colors"]
            n = len(cols)
            seg = (y1 - y0) / n
            p.setPen(Qt.NoPen)
            for i, c in enumerate(cols[::-1]):
                p.setBrush(QColor(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)))
                p.drawRect(QRectF(x0, y0 + i * seg, x1 - x0, seg + 1))
            p.setPen(QPen(QColor("#555555"), 1.0)); p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
            f = QFont(); f.setPointSizeF(8); p.setFont(f)
            p.setPen(QColor("#222222"))
            for t in np.linspace(0, 1, 6):
                v = cb["vmin"] + t * (cb["vmax"] - cb["vmin"])
                yy = y1 - t * (y1 - y0)
                p.drawLine(QPointF(x1, yy), QPointF(x1 + 4, yy))
                p.drawText(QPointF(x1 + 6, yy + 4), f"{v:.4g}")
            if cb.get("note"):
                f = QFont(); f.setPointSizeF(8.5); f.setBold(True); p.setFont(f)
                fm = p.fontMetrics()
                lines = cb["note"].split("\n")
                w = max(fm.horizontalAdvance(s) for s in lines) + 12
                h = fm.height() * len(lines) + 8
                r = QRectF(max(4, x0 - 8), y1 + 14, w, h)
                p.setBrush(QColor("#fff3e0")); p.setPen(QPen(QColor("#d62728"), 1.0))
                p.drawRoundedRect(r, 4, 4)
                p.setPen(QColor("#7a1010"))
                p.drawText(r, Qt.AlignCenter, cb["note"])
        if sc.message:
            f = QFont(); f.setPointSizeF(11); p.setFont(f)
            p.setPen(_qcolor(sc.message[1]))
            p.drawText(QRectF(0, 0, W, H), Qt.AlignCenter, sc.message[0])
        p.end()

    # ------------------------------------------------------------------ raton
    def mousePressEvent(self, ev):
        self._last = ev.position()
        self._btn = ev.button()
        self._user = True
        self.setFocus()

    def mouseReleaseEvent(self, ev):
        self._last = None

    def mouseDoubleClickEvent(self, ev):
        self.fit()

    def mouseMoveEvent(self, ev):
        if self._last is None:
            return
        pos = ev.position()
        dx, dy = pos.x() - self._last.x(), pos.y() - self._last.y()
        self._last = pos
        if self._btn == Qt.LeftButton and not (ev.modifiers() & Qt.ShiftModifier):
            if self.mode in ("plan", "front", "side"):          # al girar a mano deja de ser una vista de plano
                self.mode = "free"
                self._dirty = True
            self.azim -= dx * 0.45
            self.elev = float(np.clip(self.elev + dy * 0.45, -89.0, 89.0))
        else:
            d = self._cam_dir()
            x = np.cross([0, 0, 1.0], d); x /= max(np.linalg.norm(x), 1e-12)
            y = np.cross(d, x)
            world_h = 2 * self.dist * math.tan(math.radians(self.fov) / 2)      # alto visible en el plano del centro
            k = world_h / max(self.height(), 1)
            self.pan += (-dx * x + dy * y) * k
        self.update()

    def wheelEvent(self, ev):
        self._user = True
        s = 0.88 if ev.angleDelta().y() > 0 else 1 / 0.88
        self.dist = float(np.clip(self.dist * s, self.radius * 0.15, self.radius * 40))
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Home, Qt.Key_Escape):
            self.fit()
        else:
            super().keyPressEvent(ev)


class GLCanvas3D(QWidget):
    """Visor OpenGL con barra de vistas, equivalente a Canvas3D (matplotlib) para la aplicacion."""

    def __init__(self, parent=None, dims_button=False):
        super().__init__(parent)
        self.view = GLView(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QToolBar()                       # mismo estilo (linea naranja de 2 px) que las barras de matplotlib
        bar.setMovable(False)
        bar.setIconSize(QSize(24, 24))
        self.bar = bar

        def btn(text, tip, fn, checkable=False):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setAutoRaise(True)
            b.clicked.connect(fn)
            bar.addWidget(b)
            return b
        btn("Encuadrar", "Encuadra el modelo (doble clic o tecla Inicio)", lambda: self.view.fit())
        btn("Iso", "Vista isometrica (con perspectiva)", lambda: self.view.set_mode("iso"))
        btn("Planta", "Vista en planta: solo la placa con sus agujeros y cotas, la columna en gris tenue", lambda: self.view.set_mode("plan"))
        btn("Frontal", "Vista frontal (desde -Y): longitud de anclaje y cotas verticales", lambda: self.view.set_mode("front"))
        btn("Lateral", "Vista lateral (desde +X): longitud de anclaje y cotas verticales", lambda: self.view.set_mode("side"))
        b = btn("Perspectiva", "Alterna perspectiva / ortografica en la vista isometrica", self._toggle_persp, True)
        b.setChecked(True)
        self._bp = b
        if dims_button:
            bd = btn("Cotas", "Muestra u oculta las cotas de la vista", self._toggle_dims, True)
            bd.setChecked(True)
            self._bd = bd
        btn("Guardar imagen", "Guarda la vista actual como PNG", self.save_png)
        lay.addWidget(bar)
        lay.addWidget(self.view, 1)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def match_height(self, h):
        """Misma altura que la barra de los otros visores, para que las lineas naranjas queden alineadas."""
        self.bar.setFixedHeight(int(h))

    def _set(self, e, a):
        self.view.set_view(e, a)
        self.view.fit()

    def _toggle_dims(self):
        self.view.set_dims(self._bd.isChecked())

    def _toggle_persp(self):
        self.view.persp = self._bp.isChecked()
        self.view.fit()

    def save_png(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar imagen", "vista3d.png", "PNG (*.png)")
        if fn:
            self.view.grabFramebuffer().save(fn)

    @property
    def elev(self):
        return self.view.elev

    @property
    def azim(self):
        return self.view.azim
