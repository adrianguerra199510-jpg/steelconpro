# -*- coding: utf-8 -*-
"""Visor 3D en tiempo real (OpenGL via Qt): rotacion fluida con orden de profundidad exacto (z-buffer por pixel).

Si el equipo no ofrece OpenGL >= 2.1 (o se define SCP_NO_GL=1) la aplicacion usa el visor matplotlib de siempre.
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


def gl_wanted() -> bool:
    """El visor OpenGL (el de la ultima version de PlacaBase Pro, tambien en los nudos) se usa por omision cuando el equipo lo ofrece.  Se puede
    cambiar al visor clasico de matplotlib con «Ver > Visor 3D OpenGL» (se guarda en la configuracion y se aplica al reiniciar) o con SCP_GL=0."""
    if os.environ.get("SCP_GL") == "0":
        return False
    if os.environ.get("SCP_GL") == "1":
        return True
    try:
        from PySide6.QtCore import QSettings
        v = QSettings("SteelConPro", "SteelConPro").value("viewer_gl", True)
        return str(v).lower() in ("true", "1")
    except Exception:
        return True


def available() -> bool:
    """True si el visor OpenGL esta permitido (ver gl_wanted) y se puede abrir un contexto OpenGL >= 2.1 y compilar el shader (se comprueba una sola vez)."""
    global _AVAIL
    if _AVAIL is not None:
        return _AVAIL
    _AVAIL = False
    if os.environ.get("SCP_NO_GL") == "1" or not gl_wanted():
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


# las escenas (Scene, scene_geometry, scene_results...) viven en scene3d.py (sin Qt); aqui solo queda el visor OpenGL de Qt
from .scene3d import (FLOATS, Scene, tri_poly, _newell, GHOST, MODE_RULES, scene_geometry, _build_dims, scene_results)  # noqa: F401


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
