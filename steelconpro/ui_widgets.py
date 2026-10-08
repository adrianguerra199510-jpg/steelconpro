# -*- coding: utf-8 -*-
"""Widgets auxiliares para construir formularios enlazados al modelo."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QFormLayout, QDoubleSpinBox, QSpinBox,
                               QComboBox, QCheckBox, QLineEdit, QLabel, QGroupBox,
                               QVBoxLayout, QScrollArea, QFrame, QTableWidget, QApplication, QAbstractButton,
                               QTextBrowser)
from PySide6.QtGui import QKeySequence, QPainter, QPen, QColor, QPainterPath
from PySide6.QtCore import Qt, Signal, QEvent, QObject, QPointF

from .units import UnitSet, parse_xy_clipboard


def _get(obj, path):
    for p in path.split("."):
        obj = getattr(obj, p)
    return obj


def _set(obj, path, val):
    parts = path.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], val)


class Form(QWidget):
    """Formulario cuyos campos leen/escriben rutas del Project ('plate.tp')."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(4, 4, 4, 4)
        self.fields = []          # (path, widget, tipo, magnitud)
        self.us = UnitSet()       # la ventana principal la reemplaza
        self._lay = None
        self._help = {}           # widget -> descripcion
        self.groups = {}          # titulo -> caja del grupo
        self.info = None          # panel de ayuda al pie del formulario
        self.group("")

    def _emit(self, *_):
        self.changed.emit()

    # -------------------------------------------------------------- ayuda
    def _register_help(self, w, label, txt):
        if not txt:
            return
        full = f"<b>{label}</b><br>{txt}" if label else txt
        w.setToolTip(full)
        self._help[w] = full
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.FocusIn, QEvent.Enter, QEvent.HoverEnter):
            txt = self._help.get(obj)
            if txt and self.info is not None:
                self.info.setHtml(txt)
        return False

    def help_panel(self):
        """Panel fijo al pie que describe el campo sobre el que esta el cursor."""
        fr = QFrame()
        fr.setFrameShape(QFrame.StyledPanel)
        fr.setStyleSheet("QFrame{background:#f4f7fb;border:1px solid #c8d6e8;}")
        lay = QVBoxLayout(fr)
        lay.setContentsMargins(8, 6, 8, 6)
        # altura FIJA con su propio scroll: si el texto cambiara el alto del panel, aparecian/desaparecian las barras
        # del formulario y todo se movia bajo el cursor (se notaba sobre todo en Pernos)
        self.info = QTextBrowser()
        self.info.setFrameShape(QFrame.NoFrame)
        self.info.setStyleSheet("QTextBrowser{background:transparent;color:#24405f;font-size:8.5pt;border:0;}")
        self.info.setFixedHeight(84)
        self.info.setHtml("Pase el cursor sobre cualquier campo para ver su descripcion.")
        lay.addWidget(self.info)
        self.outer.addWidget(fr)
        return fr

    # ----------------------------------------------------------- estructura
    def group(self, title):
        box = QGroupBox(title) if title else QWidget()
        self.groups[title] = box
        lay = QFormLayout(box)
        lay.setLabelAlignment(Qt.AlignRight)
        lay.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.outer.addWidget(box)
        self._lay = lay
        return box

    def w(self, path):
        """Widget del campo enlazado a `path` ('plate.N')."""
        for f in self.fields:
            if f[0] == path:
                return f[1]
        raise KeyError(path)

    def show_field(self, path_or_widget, on):
        """Muestra u oculta la fila completa (etiqueta + campo) de un campo."""
        wd = self.w(path_or_widget) if isinstance(path_or_widget, str) else path_or_widget
        par = wd.parentWidget()
        lay = par.layout() if par is not None else None
        if isinstance(lay, QFormLayout):
            lay.setRowVisible(wd, bool(on))
        else:
            wd.setVisible(bool(on))

    def show_group(self, title, on):
        self.groups[title].setVisible(bool(on))

    def note(self, text):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setStyleSheet("color:#595959; font-size:8pt;")
        self._lay.addRow(lb)
        return lb

    def finish(self, with_help=True):
        self.outer.addStretch(1)
        if with_help and self._help:
            self.help_panel()

    # --------------------------------------------------------------- campos
    def num(self, label, path, lo=0.0, hi=1e6, step=0.125, dec=3, suffix="",
            uk=None, help=""):
        """uk = magnitud ('L','F','M','S','A','K'); si se indica, el campo se
        muestra y se lee en las unidades que haya elegido el usuario."""
        w = QDoubleSpinBox()
        w.setRange(-1e12 if lo < 0 else 0.0, 1e12)
        w._lo, w._hi = lo, hi
        w.setDecimals(dec); w.setSingleStep(step)
        w.setKeyboardTracking(False)
        if suffix and not uk:
            w.setSuffix(" " + suffix)
        w.valueChanged.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "f", uk))
        return w

    def int_(self, label, path, lo=0, hi=999, help=""):
        w = QSpinBox(); w.setRange(lo, hi); w.setKeyboardTracking(False)
        w.valueChanged.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "i", None))
        return w

    def combo(self, label, path, items, editable=False, help=""):
        w = QComboBox(); w.addItems(list(items)); w.setEditable(editable)
        w.setMaxVisibleItems(25)
        w.currentTextChanged.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "c", None))
        return w

    def check(self, label, path, help=""):
        w = QCheckBox(label)
        w.toggled.connect(self._emit)
        self._lay.addRow("", w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "b", None))
        return w

    def text(self, label, path, help=""):
        w = QLineEdit()
        w.editingFinished.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "t", None))
        return w

    # ----------------------------------------------------------- sincronizar
    def load(self, prj):
        for path, w, k, uk in self.fields:
            w.blockSignals(True)
            try:
                v = _get(prj, path)
                if k == "f":
                    if uk:
                        w.setSuffix(" " + self.us.label(uk))
                        w.setDecimals(self.us.dec(uk))
                        w.setSingleStep(self.us.step(uk))
                        lo = self.us.out(uk, w._lo)
                        hi = self.us.out(uk, w._hi)
                        w.setRange(min(lo, hi), max(lo, hi))
                        w.setValue(self.us.out(uk, float(v)))
                    else:
                        w.setRange(w._lo, w._hi)
                        w.setValue(float(v))
                elif k == "i":
                    w.setValue(int(v))
                elif k == "c":
                    i = w.findText(str(v))
                    if i < 0 and w.isEditable():
                        w.setEditText(str(v))
                    elif i >= 0:
                        w.setCurrentIndex(i)
                elif k == "b":
                    w.setChecked(bool(v))
                elif k == "t":
                    w.setText(str(v))
            finally:
                w.blockSignals(False)

    def store(self, prj):
        for path, w, k, uk in self.fields:
            if k == "f":
                _set(prj, path, self.us.inn(uk, float(w.value())) if uk
                     else float(w.value()))
            elif k == "i":
                _set(prj, path, int(w.value()))
            elif k == "c":
                _set(prj, path, w.currentText())
            elif k == "b":
                _set(prj, path, bool(w.isChecked()))
            elif k == "t":
                _set(prj, path, w.text())


def scroll(widget):
    sa = QScrollArea()
    sa.setWidget(widget)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)      # el ancho no cambia al aparecer/desaparecer la barra
    return sa


class PasteTable(QTableWidget):
    """Tabla de coordenadas que acepta Ctrl+V desde Excel y Ctrl+C hacia Excel."""
    pasted = Signal(list, int)          # filas [(x, y)], fila de inicio

    def keyPressEvent(self, ev):
        if ev.matches(QKeySequence.Paste):
            rows = parse_xy_clipboard(QApplication.clipboard().text())
            if rows:
                r = self.currentRow()
                self.pasted.emit(rows, max(0, r))
            return
        if ev.matches(QKeySequence.Copy):
            sel = sorted({(i.row(), i.column()) for i in self.selectedIndexes()})
            if sel:
                r0, r1 = sel[0][0], sel[-1][0]
                lines = []
                for r in range(r0, r1 + 1):
                    lines.append("\t".join(
                        (self.item(r, c).text() if self.item(r, c) else "") for c in (0, 1)))
                QApplication.clipboard().setText("\n".join(lines))
            return
        super().keyPressEvent(ev)


class ThemeSwitch(QAbstractButton):
    """Interruptor compacto claro/oscuro: solo un sol y una luna (sin texto); la mitad activa se resalta."""
    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(dark))
        self.setFixedSize(54, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Tema claro / oscuro (los graficos siempre van sobre fondo blanco)")

    def paintEvent(self, ev):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        dark = self.isChecked()
        p.setPen(QPen(QColor("#E85D0C" if self.underMouse() else "#8a929c"), 1.0))
        p.setBrush(QColor("#2c3643" if dark else "#e4e7eb"))
        p.drawRoundedRect(0.5, 0.5, w - 1, h - 1, 5, 5)
        # perilla bajo la opcion activa
        kx = w / 2 if dark else 1
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#E85D0C"))
        p.drawRoundedRect(kx + 1, 2, w / 2 - 3, h - 4, 4, 4)
        # sol (izquierda)
        cx, cy = w * 0.25, h / 2
        col = QColor("#ffffff" if not dark else "#f5b942")
        p.setBrush(col)
        p.drawEllipse(QPointF(cx, cy), 3.6, 3.6)
        p.setPen(QPen(col, 1.3))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(cx + 5.6 * math.cos(a), cy + 5.6 * math.sin(a)),
                       QPointF(cx + 7.4 * math.cos(a), cy + 7.4 * math.sin(a)))
        # luna (derecha): disco menos otro desplazado
        mx, my = w * 0.75, h / 2
        path = QPainterPath()
        path.addEllipse(QPointF(mx, my), 6.0, 6.0)
        cut = QPainterPath()
        cut.addEllipse(QPointF(mx + 3.2, my - 2.2), 5.2, 5.2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff" if dark else "#59626d"))
        p.drawPath(path.subtracted(cut))
        p.end()

    def sizeHint(self):
        return self.size()
