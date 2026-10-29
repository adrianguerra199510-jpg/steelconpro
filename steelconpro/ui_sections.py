# -*- coding: utf-8 -*-
"""Biblioteca de secciones y Section Designer.

    SectionCanvas    lienzo que dibuja una seccion (componentes, centroide, ejes principales) y deja mover los componentes con el mouse
    SectionDesigner  editor de una seccion libre: plantillas, componentes (rectangulo, circulo, tubo, poligono), propiedades en vivo
    SectionLibrary   lista de todas las secciones (AISC, personalizadas y libres) con vista previa; abre el Section Designer

Las unidades de longitud que se muestran son las del proyecto (`us`); internamente todo va en pulgadas.
"""
from __future__ import annotations
import copy
import math

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF, QFont, QPainterPath
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QDoubleSpinBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSplitter, QTextBrowser, QMessageBox, QGroupBox,
                               QPlainTextEdit, QDialogButtonBox, QFileDialog, QSizePolicy, QCheckBox)

from . import sections as SEC
from .shapes import CATALOG, GEN, FREE_FAMILY, KIND_LABELS, make_general

COLORS = ["#7aa6d6", "#e0a15a", "#82c29a", "#c490d1", "#d9c55e", "#e08a8a", "#6ec1c8", "#a3a3a3"]
TYPE_NAMES = {"rect": "Rectángulo", "circ": "Círculo", "ring": "Tubo", "poly": "Polígono"}
FAMILY_NAMES = {"Personalizado": "Personalizadas (dimensiones)", FREE_FAMILY: "Libres (Section Designer)", "Importado": "Importadas"}


def _dark(w) -> bool:
    return w.palette().window().color().lightness() < 128


# ================================================================================================== lienzo
class SectionCanvas(QWidget):
    """Dibujo de una seccion.  Rueda: zoom; arrastrar el fondo con el boton central o derecho: desplazar; arrastrar un componente (boton izquierdo):
    moverlo (solo si `editable`)."""
    picked = Signal(int)                       # indice del componente bajo el mouse (-1: ninguno)
    moved = Signal()                           # un componente cambio de lugar
    moving = Signal()                          # mientras se arrastra

    def __init__(self, parent=None, editable=False):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.editable = editable
        self.comps = []
        self.sel = -1
        self.props = {}
        self.us = None
        self.snap = 0.0                       # paso de la rejilla de arrastre, in (0 = libre)
        self._k = 20.0                        # pixeles por pulgada
        self._c = QPointF(0.0, 0.0)           # punto del modelo (in) al centro del lienzo
        self._drag = None
        self._fit_pending = True

    # ------------------------------------------------------------------ datos
    def set_comps(self, comps, keep_view=False):
        self.comps = comps
        self.props = SEC.section_props(comps) if comps else {}
        if not keep_view:
            self.fit()
        self.update()

    def fit(self):
        ok = [c for c in self.comps if not SEC.valid_comp(c)]
        if not ok:
            self._k, self._c = 20.0, QPointF(0, 0)
            return
        x0, y0, x1, y1 = SEC._points_for_extent(ok)
        w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        self._k = 0.8 * min(self.width() / w, self.height() / h)
        self._c = QPointF((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def resizeEvent(self, ev):
        if self._fit_pending or not self.editable:
            self.fit()
        super().resizeEvent(ev)

    # ------------------------------------------------------------------ transformaciones
    def _to_px(self, x, y):
        return QPointF(self.width() / 2.0 + (x - self._c.x()) * self._k, self.height() / 2.0 - (y - self._c.y()) * self._k)

    def _to_model(self, px, py):
        return ((px - self.width() / 2.0) / self._k + self._c.x(), -(py - self.height() / 2.0) / self._k + self._c.y())

    # ------------------------------------------------------------------ dibujo
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = _dark(self)
        bg, grid, ink = (QColor("#1e2530"), QColor("#2b3442"), QColor("#d6dde8")) if dark else (QColor("#ffffff"), QColor("#e6eaf0"), QColor("#24405f"))
        p.fillRect(self.rect(), bg)
        self._grid(p, grid, ink)
        ok = [(i, c) for i, c in enumerate(self.comps) if not SEC.valid_comp(c)]
        for i, c in ok:
            col = QColor(COLORS[i % len(COLORS)])
            col.setAlpha(210 if i != self.sel else 255)
            pen = QPen(QColor("#d62728") if i == self.sel else QColor(ink), 2.2 if i == self.sel else 1.0)
            p.setPen(pen)
            p.setBrush(QBrush(col))
            p.drawPath(self._path(c))
        pr = self.props
        if pr:
            cx, cy = pr["cx"], pr["cy"]
            q = self._to_px(cx, cy)
            p.setPen(QPen(QColor("#c00000"), 1.6))
            p.drawLine(QPointF(q.x() - 8, q.y()), QPointF(q.x() + 8, q.y()))
            p.drawLine(QPointF(q.x(), q.y() - 8), QPointF(q.x(), q.y() + 8))
            p.drawEllipse(q, 4, 4)
            th = math.radians(pr.get("theta", 0.0))
            if abs(pr.get("Ixy", 0.0)) > 1e-9 * max(pr["Ix"], pr["Iy"], 1e-9):         # ejes principales (solo si no coinciden con X, Y)
                L = 0.5 * max(pr["W"], pr["H"]) * self._k * 0.9
                p.setPen(QPen(QColor("#7b3fb3"), 1.2, Qt.DashLine))
                for ang in (th, th + math.pi / 2):
                    p.drawLine(QPointF(q.x() - L * math.cos(ang), q.y() + L * math.sin(ang)), QPointF(q.x() + L * math.cos(ang), q.y() - L * math.sin(ang)))
            self._dims(p, pr, ink)
        elif not self.comps:
            p.setPen(QColor(ink))
            p.drawText(self.rect(), Qt.AlignCenter, "Sin componentes")
        p.end()

    def _path(self, c):
        path = QPainterPath()
        t = c["t"]
        if t in ("circ", "ring"):
            r = float(c["d"]) / 2.0
            q = self._to_px(float(c["x"]), float(c["y"]))
            path.addEllipse(q, r * self._k, r * self._k)
            if t == "ring":
                ri = max(r - float(c["ti"]), 0.0)
                inner = QPainterPath()
                inner.addEllipse(q, ri * self._k, ri * self._k)
                path = path.subtracted(inner)
        else:
            pts = SEC.comp_outline(c)
            path.addPolygon(QPolygonF([self._to_px(x, y) for x, y in pts]))
            path.closeSubpath()
        return path

    def _grid(self, p, grid, ink):
        us = self.us
        fl = us.fl if us is not None else 1.0
        # paso de la rejilla: una potencia de 1, 2 o 5 en unidades del usuario con al menos ~40 px
        raw = 40.0 / self._k / fl
        mag = 10 ** math.floor(math.log10(max(raw, 1e-9)))
        step = next((m * mag for m in (1, 2, 5, 10) if m * mag >= raw), 10 * mag) * fl
        x0, y0 = self._to_model(0, self.height())
        x1, y1 = self._to_model(self.width(), 0)
        font = QFont(self.font())
        font.setPointSizeF(7.0)
        p.setFont(font)
        gx = math.floor(x0 / step) * step
        while gx <= x1:
            q = self._to_px(gx, 0)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(q.x(), 0), QPointF(q.x(), self.height()))
            if abs(gx) > 1e-9:
                p.setPen(QColor(ink))
                p.drawText(QPointF(q.x() + 2, self.height() - 3), f"{gx / fl:g}")
            gx += step
        gy = math.floor(y0 / step) * step
        while gy <= y1:
            q = self._to_px(0, gy)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(0, q.y()), QPointF(self.width(), q.y()))
            if abs(gy) > 1e-9:
                p.setPen(QColor(ink))
                p.drawText(QPointF(3, q.y() - 2), f"{gy / fl:g}")
            gy += step
        o = self._to_px(0, 0)
        p.setPen(QPen(QColor(ink), 1.2))
        p.drawLine(QPointF(o.x(), 0), QPointF(o.x(), self.height()))
        p.drawLine(QPointF(0, o.y()), QPointF(self.width(), o.y()))
        p.drawText(QPointF(self.width() - 14, o.y() - 3), "X")
        p.drawText(QPointF(o.x() + 4, 11), "Y")

    def _dims(self, p, pr, ink):
        us = self.us
        fl = us.fl if us is not None else 1.0
        ul = us.L if us is not None else "in"
        x0, x1 = pr["cx"] + pr["xmin"], pr["cx"] + pr["xmax"]
        y0, y1 = pr["cy"] + pr["ymin"], pr["cy"] + pr["ymax"]
        p.setPen(QPen(QColor("#44546a"), 1))
        a, b = self._to_px(x0, y0 - 0.0), self._to_px(x1, y0)
        yy = a.y() + 14
        p.drawLine(QPointF(a.x(), yy), QPointF(b.x(), yy))
        p.drawText(QPointF((a.x() + b.x()) / 2 - 20, yy + 11), f"{(x1 - x0) / fl:.4g} {ul}")
        a, b = self._to_px(x1, y0), self._to_px(x1, y1)
        xx = a.x() + 14
        p.drawLine(QPointF(xx, a.y()), QPointF(xx, b.y()))
        p.save()
        p.translate(xx + 12, (a.y() + b.y()) / 2 + 20)
        p.rotate(-90)
        p.drawText(QPointF(0, 0), f"{(y1 - y0) / fl:.4g} {ul}")
        p.restore()

    # ------------------------------------------------------------------ mouse
    def _hit(self, mx, my):
        for i in range(len(self.comps) - 1, -1, -1):
            c = self.comps[i]
            if SEC.valid_comp(c):
                continue
            if c["t"] in ("circ", "ring"):
                r = float(c["d"]) / 2.0
                d = math.hypot(mx - float(c["x"]), my - float(c["y"]))
                if d <= r and (c["t"] == "circ" or d >= r - float(c["ti"])):
                    return i
            elif _in_poly(mx, my, SEC.comp_outline(c)):
                return i
        return -1

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            mx, my = self._to_model(ev.position().x(), ev.position().y())
            i = self._hit(mx, my)
            self.sel = i
            self.picked.emit(i)
            if self.editable and i >= 0:
                c = self.comps[i]
                x0, y0 = _comp_pos(c)
                self._drag = ("move", mx, my, x0, y0, copy.deepcopy(c))
            self.update()
        elif ev.button() in (Qt.MiddleButton, Qt.RightButton):
            self._drag = ("pan", ev.position().x(), ev.position().y(), self._c.x(), self._c.y())

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            return
        if self._drag[0] == "pan":
            _t, px, py, cx, cy = self._drag
            self._c = QPointF(cx - (ev.position().x() - px) / self._k, cy + (ev.position().y() - py) / self._k)
            self.update()
        elif self._drag[0] == "move" and 0 <= self.sel < len(self.comps):
            _t, mx, my, x0, y0, orig = self._drag
            nx, ny = self._to_model(ev.position().x(), ev.position().y())
            dx, dy = nx - mx, ny - my
            if self.snap > 0:
                dx, dy = round((x0 + dx) / self.snap) * self.snap - x0, round((y0 + dy) / self.snap) * self.snap - y0
            c = copy.deepcopy(orig)
            _move(c, dx, dy)
            self.comps[self.sel] = c
            self.props = SEC.section_props(self.comps)
            self.moving.emit()
            self.update()

    def mouseReleaseEvent(self, ev):
        if self._drag is not None and self._drag[0] == "move":
            self.moved.emit()
        self._drag = None

    def wheelEvent(self, ev):
        k = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        mx, my = self._to_model(ev.position().x(), ev.position().y())
        self._k *= k
        self._fit_pending = False
        nx, ny = self._to_model(ev.position().x(), ev.position().y())
        self._c = QPointF(self._c.x() + (mx - nx), self._c.y() + (my - ny))
        self.update()

    def mouseDoubleClickEvent(self, ev):
        self.fit()
        self.update()


def _in_poly(x, y, poly) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def _comp_pos(c):
    if c["t"] == "poly":
        return float(c["pts"][0][0]), float(c["pts"][0][1])
    return float(c["x"]), float(c["y"])


def _move(c, dx, dy):
    if c["t"] == "poly":
        c["pts"] = [[float(x) + dx, float(y) + dy] for x, y in c["pts"]]
    else:
        c["x"], c["y"] = float(c["x"]) + dx, float(c["y"]) + dy


# ================================================================================================== propiedades en texto
def props_html(pr, us, label="") -> str:
    if not pr:
        return "<i>Sin propiedades: agregue componentes válidos.</i>"
    fl = us.fl if us is not None else 1.0
    ul = us.L if us is not None else "in"

    def L(v):
        return f"{v / fl:.5g}"

    def A(v):
        return f"{v / fl ** 2:.5g}"

    def I(v):
        return f"{v / fl ** 4:.5g}"

    def S(v):
        return f"{v / fl ** 3:.5g}"

    rows = [("Área A", f"{A(pr['A'])} {ul}²"), ("Centroide (x, y)", f"({L(pr['cx'])}, {L(pr['cy'])}) {ul}"),
            ("Ancho × alto", f"{L(pr['W'])} × {L(pr['H'])} {ul}"),
            ("Ix", f"{I(pr['Ix'])} {ul}⁴"), ("Iy", f"{I(pr['Iy'])} {ul}⁴"), ("Ixy", f"{I(pr['Ixy'])} {ul}⁴"),
            ("I principales I1 / I2", f"{I(pr['I1'])} / {I(pr['I2'])} {ul}⁴ (θ = {pr['theta']:.1f}°)"),
            ("Sx / Sy", f"{S(pr['Sx'])} / {S(pr['Sy'])} {ul}³"), ("Zx / Zy", f"{S(pr['Zx'])} / {S(pr['Zy'])} {ul}³"),
            ("rx / ry", f"{L(pr['rx'])} / {L(pr['ry'])} {ul}"), ("J (aprox.)", f"{I(pr['J'])} {ul}⁴"),
            ("Peso (acero)", f"{pr['weight']:.4g} lb/ft  =  {pr['weight'] * 1.48816:.4g} kg/m")]
    body = "".join(f"<tr><td style='padding-right:10px'><b>{a}</b></td><td>{b}</td></tr>" for a, b in rows)
    return (f"<div style='font-size:9pt'>{('<b>' + label + '</b><br>') if label else ''}<table>{body}</table>"
            "<span style='color:#7f7f7f'>Ix, Iy: respecto de los ejes del dibujo por el centroide. J: suma de los componentes "
            "(no considera celdas cerradas).</span></div>")


def _table_item(txt, align_right=False):
    it = QTableWidgetItem(txt)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if align_right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


# ================================================================================================== Section Designer
class SectionDesigner(QDialog):
    """Editor de una seccion libre.  Resultado: `result_shape` (Shape tipo GEN) al aceptar."""

    def __init__(self, us, parent=None, shape=None, name=""):
        super().__init__(parent)
        self.setWindowTitle("Section Designer")
        self.resize(1250, 760)
        self.us = us
        self.fl = us.fl
        self.result_shape = None
        self._orig_label = shape.label if shape is not None and shape.kind == GEN and shape.source != "AISC" else ""
        self._busy = False
        self.comps = SEC.comps_of_shape(shape) if shape is not None else SEC.t_i_shape(12.0, 8.0, 0.5, 0.35)
        if shape is not None and shape.kind != GEN:
            name = name or f"{shape.label}-copia"
        self.name0 = (shape.label if self._orig_label else name) or "SECCION-LIBRE-1"

        root = QHBoxLayout(self)
        # ------------------------------------------------------------ izquierda: nombre, plantillas, componentes
        left = QVBoxLayout()
        fn = QFormLayout()
        self.ed_name = QLineEdit(self.name0)
        fn.addRow("Nombre", self.ed_name)
        left.addLayout(fn)

        gt = QGroupBox("Plantilla")
        tl = QVBoxLayout(gt)
        self.cb_tpl = QComboBox()
        self.cb_tpl.addItems(list(SEC.TEMPLATES.keys()))
        self.cb_tpl.currentIndexChanged.connect(self._tpl_changed)
        tl.addWidget(self.cb_tpl)
        self.tpl_form = QFormLayout()
        tl.addLayout(self.tpl_form)
        self.tpl_spins = {}
        b = QPushButton("Reemplazar los componentes con la plantilla")
        b.clicked.connect(self._apply_tpl)
        tl.addWidget(b)
        left.addWidget(gt)

        gc = QGroupBox("Componentes")
        cl = QVBoxLayout(gc)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["#", "Tipo", "Descripción"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.setMinimumHeight(150)
        self.tbl.itemSelectionChanged.connect(self._row_selected)
        cl.addWidget(self.tbl)
        row = QHBoxLayout()
        for txt, kind in (("+ Rectángulo", "rect"), ("+ Círculo", "circ"), ("+ Tubo", "ring"), ("+ Polígono", "poly")):
            bt = QPushButton(txt)
            bt.clicked.connect(lambda _c=False, k=kind: self._add(k))
            row.addWidget(bt)
        cl.addLayout(row)
        row = QHBoxLayout()
        for txt, fn_ in (("Duplicar", self._dup), ("Quitar", self._del), ("Espejo X", lambda: self._mirror(0)), ("Espejo Y", lambda: self._mirror(1)),
                         ("Centrar", self._center)):
            bt = QPushButton(txt)
            bt.clicked.connect(fn_)
            row.addWidget(bt)
        cl.addLayout(row)
        left.addWidget(gc, 1)

        self.ed_box = QGroupBox("Componente seleccionado")
        self.ed_form = QFormLayout(self.ed_box)
        self.fields = {}
        for key, lab, kinds in (("x", "Centro X", ("rect", "circ", "ring")), ("y", "Centro Y", ("rect", "circ", "ring")), ("w", "Ancho", ("rect",)),
                                ("h", "Alto", ("rect",)), ("rot", "Giro (°)", ("rect",)), ("d", "Diámetro", ("circ", "ring")),
                                ("ti", "Espesor de pared", ("ring",))):
            sp = QDoubleSpinBox()
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(4 if key != "rot" else 2)
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(self._field_changed)
            lb = QLabel(lab)
            self.ed_form.addRow(lb, sp)
            self.fields[key] = (lb, sp, kinds)
        self.ed_pts = QPlainTextEdit()
        self.ed_pts.setPlaceholderText("Un vértice por línea:  x, y")
        self.ed_pts.setFixedHeight(90)
        self.lb_pts = QLabel("Vértices (x, y)")
        self.ed_form.addRow(self.lb_pts, self.ed_pts)
        self.bt_pts = QPushButton("Aplicar vértices")
        self.bt_pts.clicked.connect(self._pts_changed)
        self.ed_form.addRow(self.bt_pts)
        left.addWidget(self.ed_box)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(430)
        root.addWidget(lw)

        # ------------------------------------------------------------ centro: lienzo
        mid = QVBoxLayout()
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Arrastrar con paso:"))
        self.cb_snap = QComboBox()
        self.cb_snap.addItem("libre", 0.0)
        for v in (0.05, 0.1, 0.25, 0.5, 1.0):
            self.cb_snap.addItem(f"{v / self.fl:.3g} {us.L}", v)
        self.cb_snap.setCurrentIndex(0)
        self.cb_snap.currentIndexChanged.connect(lambda: setattr(self.canvas, "snap", float(self.cb_snap.currentData())))
        bar.addWidget(self.cb_snap)
        bar.addStretch(1)
        bar.addWidget(QLabel("Rueda: zoom · botón derecho: desplazar · doble clic: encuadrar"))
        mid.addLayout(bar)
        self.canvas = SectionCanvas(editable=True)
        self.canvas.us = us
        self.canvas.picked.connect(self._canvas_picked)
        self.canvas.moving.connect(self._canvas_moving)
        self.canvas.moved.connect(self._canvas_moved)
        mid.addWidget(self.canvas, 1)
        root.addLayout(mid, 1)

        # ------------------------------------------------------------ derecha: propiedades y avisos
        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Propiedades de la sección</b>"))
        self.props = QTextBrowser()
        self.props.setMinimumWidth(330)
        right.addWidget(self.props, 1)
        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        right.addWidget(self.warn)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Guardar en la biblioteca")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(360)
        root.addWidget(rw)

        self._tpl_changed()
        self._refresh(select=0)

    # ------------------------------------------------------------------ plantillas
    def _tpl_changed(self):
        while self.tpl_form.rowCount():
            self.tpl_form.removeRow(0)
        self.tpl_spins = {}
        spec, _fn = SEC.TEMPLATES[self.cb_tpl.currentText()]
        for key, lab, default in spec:
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 1e6)
            if key in SEC.LENGTH_PARAMS:
                sp.setDecimals(0)
                sp.setValue(float(default))
            else:
                sp.setDecimals(4)
                sp.setSuffix(" " + self.us.L)
                sp.setValue(float(default) / self.fl)
            self.tpl_form.addRow(lab, sp)
            self.tpl_spins[key] = sp

    def _apply_tpl(self):
        vals = {k: (sp.value() if k in SEC.LENGTH_PARAMS else sp.value() * self.fl) for k, sp in self.tpl_spins.items()}
        if "n" in vals:
            vals["n"] = int(vals["n"])
        try:
            comps = SEC.build_template(self.cb_tpl.currentText(), **vals)
        except Exception as e:
            QMessageBox.warning(self, "Plantilla", f"Revise las dimensiones: {e}")
            return
        self.comps = comps
        self._refresh(select=0)
        self.canvas.fit()
        self.canvas.update()

    # ------------------------------------------------------------------ componentes
    def _refresh(self, select=None, fit=False):
        self._busy = True
        self.tbl.setRowCount(len(self.comps))
        for i, c in enumerate(self.comps):
            self.tbl.setItem(i, 0, _table_item(str(i + 1)))
            self.tbl.setItem(i, 1, _table_item(TYPE_NAMES.get(c["t"], c["t"])))
            self.tbl.setItem(i, 2, _table_item(self._describe(c)))
        if select is not None and self.comps:
            self.tbl.selectRow(max(0, min(select, len(self.comps) - 1)))
        self._busy = False
        self.canvas.sel = self.tbl.currentRow() if self.comps else -1
        self.canvas.set_comps(self.comps, keep_view=not fit)
        self._load_fields()
        self._update_props()

    def _describe(self, c):
        u, f = self.us.L, self.fl
        t = c["t"]
        bad = SEC.valid_comp(c)
        if bad:
            return f"⚠ {bad}"
        if t == "rect":
            return f"{c['w'] / f:.4g} × {c['h'] / f:.4g} {u} en ({c['x'] / f:.4g}, {c['y'] / f:.4g})" + (f", giro {c.get('rot', 0):g}°" if abs(c.get("rot", 0)) > 1e-9 else "")
        if t == "circ":
            return f"Ø {c['d'] / f:.4g} {u} en ({c['x'] / f:.4g}, {c['y'] / f:.4g})"
        if t == "ring":
            return f"Ø {c['d'] / f:.4g} {u}, pared {c['ti'] / f:.4g} {u} en ({c['x'] / f:.4g}, {c['y'] / f:.4g})"
        return f"{len(c['pts'])} vértices"

    def _row_selected(self):
        if self._busy:
            return
        self.canvas.sel = self.tbl.currentRow()
        self.canvas.update()
        self._load_fields()

    def _canvas_picked(self, i):
        if i >= 0:
            self._busy = True
            self.tbl.selectRow(i)
            self._busy = False
            self._load_fields()

    def _canvas_moving(self):
        self._update_props(live=True)

    def _canvas_moved(self):
        self.comps = self.canvas.comps
        i = self.canvas.sel
        self._refresh(select=i)

    def _cur(self):
        i = self.tbl.currentRow()
        return (i, self.comps[i]) if 0 <= i < len(self.comps) else (-1, None)

    def _load_fields(self):
        i, c = self._cur()
        self._busy = True
        self.ed_box.setEnabled(c is not None)
        for key, (lb, sp, kinds) in self.fields.items():
            vis = c is not None and c["t"] in kinds
            lb.setVisible(vis)
            sp.setVisible(vis)
            if vis:
                v = float(c.get(key, 0.0))
                if key == "rot":
                    sp.setSuffix("")
                    sp.setValue(v)
                else:
                    sp.setSuffix(" " + self.us.L)
                    sp.setValue(v / self.fl)
        isp = c is not None and c["t"] == "poly"
        for w in (self.ed_pts, self.lb_pts, self.bt_pts):
            w.setVisible(isp)
        if isp:
            self.ed_pts.setPlainText("\n".join(f"{x / self.fl:.5g}, {y / self.fl:.5g}" for x, y in c["pts"]))
        self._busy = False

    def _field_changed(self, *_):
        if self._busy:
            return
        i, c = self._cur()
        if c is None:
            return
        for key, (lb, sp, kinds) in self.fields.items():
            if c["t"] in kinds:
                c[key] = sp.value() if key == "rot" else sp.value() * self.fl
        self._refresh(select=i)

    def _pts_changed(self):
        i, c = self._cur()
        if c is None or c["t"] != "poly":
            return
        pts = []
        try:
            for ln in self.ed_pts.toPlainText().splitlines():
                ln = ln.strip().replace(";", ",")
                if not ln:
                    continue
                a, b = [float(x) for x in ln.replace(" ", ",").split(",") if x != ""][:2]
                pts.append([a * self.fl, b * self.fl])
        except ValueError:
            QMessageBox.warning(self, "Polígono", "Cada línea debe tener dos números:  x, y")
            return
        c["pts"] = pts
        self._refresh(select=i)

    def _add(self, kind):
        d = {"rect": {"t": "rect", "x": 0.0, "y": 0.0, "w": 4.0, "h": 0.5, "rot": 0.0}, "circ": {"t": "circ", "x": 0.0, "y": 0.0, "d": 4.0},
             "ring": {"t": "ring", "x": 0.0, "y": 0.0, "d": 6.0, "ti": 0.5},
             "poly": {"t": "poly", "pts": [[-2.0, -1.5], [2.0, -1.5], [0.0, 2.0]]}}[kind]
        self.comps.append(copy.deepcopy(d))
        self._refresh(select=len(self.comps) - 1)

    def _dup(self):
        i, c = self._cur()
        if c is None:
            return
        n = copy.deepcopy(c)
        _move(n, 0.5, 0.5)
        self.comps.insert(i + 1, n)
        self._refresh(select=i + 1)

    def _del(self):
        i, c = self._cur()
        if c is None:
            return
        del self.comps[i]
        self._refresh(select=min(i, len(self.comps) - 1))

    def _mirror(self, axis):
        pr = self.canvas.props
        if not pr:
            return
        c0 = pr["cx"] if axis == 0 else pr["cy"]
        for c in self.comps:
            if c["t"] == "poly":
                c["pts"] = [[(2 * c0 - x) if axis == 0 else x, (2 * c0 - y) if axis == 1 else y] for x, y in c["pts"]][::-1]
            else:
                if axis == 0:
                    c["x"] = 2 * c0 - float(c["x"])
                    if c["t"] == "rect":
                        c["rot"] = -float(c.get("rot", 0.0))
                else:
                    c["y"] = 2 * c0 - float(c["y"])
                    if c["t"] == "rect":
                        c["rot"] = -float(c.get("rot", 0.0))
        self._refresh(select=self.tbl.currentRow())

    def _center(self):
        pr = self.canvas.props
        if not pr:
            return
        for c in self.comps:
            _move(c, -pr["cx"], -pr["cy"])
        self._refresh(select=self.tbl.currentRow(), fit=True)

    # ------------------------------------------------------------------ propiedades y avisos
    def _update_props(self, live=False):
        pr = self.canvas.props if live else (SEC.section_props(self.comps) if self.comps else {})
        self.props.setHtml(props_html(pr, self.us, self.ed_name.text().strip()))
        msgs = []
        bad = [i + 1 for i, c in enumerate(self.comps) if SEC.valid_comp(c)]
        if bad:
            msgs.append(f"Componente(s) {', '.join(map(str, bad))} con datos no válidos: no se usan.")
        if not live and len([c for c in self.comps if not SEC.valid_comp(c)]) >= 2:
            ov = SEC.overlap_area(self.comps)
            if pr and ov > 0.002 * pr["A"]:
                msgs.append(f"Hay {ov / self.fl ** 2:.3g} {self.us.L}² donde se superponen componentes: se cuentan dos veces en las propiedades.")
        self.warn.setText("".join(f"<span style='color:#9c0006'>• {m}</span><br>" for m in msgs))

    # ------------------------------------------------------------------ guardar
    def _ok(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Sección", "Escriba un nombre.")
            return
        old = CATALOG.get(name)
        if old is not None and old.source == "AISC":
            QMessageBox.warning(self, "Sección", f"«{name}» es una sección del catálogo AISC: use otro nombre.")
            return
        if old is not None and name != self._orig_label:
            if QMessageBox.question(self, "Sección", f"Ya existe «{name}». ¿Reemplazarla?") != QMessageBox.Yes:
                return
        ok = [c for c in self.comps if not SEC.valid_comp(c)]
        if not ok:
            QMessageBox.warning(self, "Sección", "Agregue al menos un componente válido.")
            return
        try:
            self.result_shape = make_general(name, ok)
        except Exception as e:
            QMessageBox.warning(self, "Sección", str(e))
            return
        self.replaced = self._orig_label
        self.accept()


# ================================================================================================== biblioteca
class SectionLibrary(QDialog):
    """Todas las secciones del programa.  Con `pick=True` devuelve la elegida en `selected_label`."""
    COLS = ["Sección", "Familia", "d", "bf", "tw", "tf", "A", "Ix", "Zx"]

    def __init__(self, us, parent=None, pick=False, current=""):
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de secciones")
        self.resize(1200, 720)
        self.us = us
        self.pick = pick
        self.selected_label = ""
        self._rows = []
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Familia"))
        self.cb_fam = QComboBox()
        top.addWidget(self.cb_fam)
        top.addWidget(QLabel("Buscar"))
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("W14, HSS8, L4X4...")
        self.ed_find.textChanged.connect(self._fill)
        top.addWidget(self.ed_find, 1)
        self.lbl_n = QLabel("")
        top.addWidget(self.lbl_n)
        root.addLayout(top)
        sp = QSplitter(Qt.Horizontal)
        self.tbl = QTableWidget(0, len(self.COLS))
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setDefaultSectionSize(22)
        self.tbl.itemSelectionChanged.connect(self._selected)
        self.tbl.itemDoubleClicked.connect(lambda *_: self._open_designer())
        sp.addWidget(self.tbl)
        pv = QWidget()
        pl = QVBoxLayout(pv)
        pl.setContentsMargins(0, 0, 0, 0)
        self.canvas = SectionCanvas()
        self.canvas.us = us
        pl.addWidget(self.canvas, 2)
        self.props = QTextBrowser()
        pl.addWidget(self.props, 2)
        sp.addWidget(pv)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 2)
        sp.setSizes([760, 440])
        root.addWidget(sp, 1)
        row = QHBoxLayout()
        for txt, fn in (("Nueva sección (Section Designer)...", self._new), ("Abrir en el Section Designer...", self._open_designer),
                        ("Eliminar", self._delete), ("Importar base AISC...", self._import)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        self.bt_del = row.itemAt(2).widget()
        row.addStretch(1)
        if pick:
            self.bt_use = QPushButton("Usar esta sección")
            self.bt_use.setDefault(True)
            self.bt_use.clicked.connect(self._use)
            row.addWidget(self.bt_use)
        bc = QPushButton("Cerrar")
        bc.clicked.connect(self.reject)
        row.addWidget(bc)
        root.addLayout(row)
        self._fill_families(current)
        self.cb_fam.currentIndexChanged.connect(self._fill)
        self._fill(select=current)

    # ------------------------------------------------------------------ datos
    def _fill_families(self, current=""):
        self.cb_fam.blockSignals(True)
        self.cb_fam.clear()
        self.cb_fam.addItem("Todas", "")
        for f in CATALOG.families(free=True):
            self.cb_fam.addItem(FAMILY_NAMES.get(f, f), f)
        s = CATALOG.get(current) if current else None
        if s is not None and s.family:
            i = self.cb_fam.findData(s.family)
            if i >= 0:
                self.cb_fam.setCurrentIndex(i)
        self.cb_fam.blockSignals(False)

    def _fill(self, *_a, select=""):
        fam = self.cb_fam.currentData() or ""
        q = self.ed_find.text().strip().upper().replace(" ", "")
        keep = select or (self._rows[self.tbl.currentRow()] if 0 <= self.tbl.currentRow() < len(self._rows) else "")
        if fam:
            labs = CATALOG.by_family(fam)
        else:
            labs = []
            for f in CATALOG.families(free=True):
                labs += CATALOG.by_family(f)
        if q:
            labs = [x for x in labs if q in x.upper().replace(" ", "")]
        self._rows = labs
        fl = self.us.fl
        self.tbl.setUpdatesEnabled(False)
        self.tbl.setRowCount(len(labs))
        self.tbl.setHorizontalHeaderLabels(["Sección", "Familia", f"d ({self.us.L})", f"bf ({self.us.L})", f"tw ({self.us.L})", f"tf ({self.us.L})",
                                           f"A ({self.us.L}²)", f"Ix ({self.us.L}⁴)", f"Zx ({self.us.L}³)"])
        for i, lab in enumerate(labs):
            s = CATALOG.shapes[lab]
            vals = [lab, FAMILY_NAMES.get(s.family, s.family), f"{s.d / fl:.4g}", f"{s.bf / fl:.4g}", f"{s.tw / fl:.4g}", f"{s.tf / fl:.4g}",
                    f"{s.A / fl ** 2:.4g}", f"{s.Ix / fl ** 4:.5g}", f"{s.Zx / fl ** 3:.5g}"]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, _table_item(v, j >= 2))
        self.tbl.setUpdatesEnabled(True)
        for j, w in enumerate((130, 70, 62, 62, 62, 62, 72, 82)):
            self.tbl.setColumnWidth(j, w)
        self.lbl_n.setText(f"{len(labs)} secciones")
        if keep in labs:
            self.tbl.selectRow(labs.index(keep))
        elif labs:
            self.tbl.selectRow(0)
        self._selected()

    def _cur(self):
        r = self.tbl.currentRow()
        return CATALOG.shapes.get(self._rows[r]) if 0 <= r < len(self._rows) else None

    def _selected(self):
        s = self._cur()
        if s is None:
            self.canvas.set_comps([])
            self.props.setHtml("")
            return
        comps = SEC.comps_of_shape(s)
        self.canvas.set_comps(comps)
        pr = SEC.section_props(comps)
        html = props_html(pr, self.us, f"{s.label}  ·  {KIND_LABELS.get(s.kind, s.kind)}")
        if s.source == "AISC":
            html += (f"<div style='font-size:8.5pt;color:#44546a'>Valores del catálogo AISC (con redondeos de laminación): A = {s.A / self.us.fl ** 2:.5g} {self.us.L}², "
                     f"Ix = {s.Ix / self.us.fl ** 4:.5g}, Zx = {s.Zx / self.us.fl ** 3:.5g}. El dibujo es la sección idealizada con rectángulos.</div>")
        self.props.setHtml(html)
        self.bt_del.setEnabled(s.source != "AISC")

    # ------------------------------------------------------------------ acciones
    def _after_edit(self, label):
        self._fill_families(label)
        self._fill(select=label)

    def _designer(self, shape=None):
        d = SectionDesigner(self.us, self, shape)
        if d.exec() and d.result_shape is not None:
            CATALOG.add_free(d.result_shape, replace=getattr(d, "replaced", ""))
            self._after_edit(d.result_shape.label)
            return d.result_shape.label
        return None

    def _new(self):
        self._designer(None)

    def _open_designer(self):
        s = self._cur()
        if s is not None:
            self._designer(s)

    def _delete(self):
        s = self._cur()
        if s is None or s.source == "AISC":
            return
        if QMessageBox.question(self, "Sección", f"¿Eliminar «{s.label}» de la biblioteca?") == QMessageBox.Yes:
            CATALOG.remove(s.label)
            self._fill_families()
            self._fill()

    def _import(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Base de datos AISC (xlsx o csv)", "", "AISC (*.xlsx *.xlsm *.csv)")
        if not fn:
            return
        try:
            n, msg = CATALOG.import_aisc(fn)
        except Exception as e:
            QMessageBox.warning(self, "Importar", str(e))
            return
        QMessageBox.information(self, "Importar", msg)
        self._fill_families()
        self._fill()

    def _use(self):
        s = self._cur()
        if s is None:
            return
        self.selected_label = s.label
        self.accept()
