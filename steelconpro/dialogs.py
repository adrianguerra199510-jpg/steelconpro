# -*- coding: utf-8 -*-
"""Dialogos: seccion personalizada (dimensiones).  La biblioteca de materiales esta en ui_materials.py y la de secciones en ui_sections.py."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QComboBox, QDoubleSpinBox, QLabel, QDialogButtonBox,
                               QTabWidget, QTableWidget, QTableWidgetItem, QPushButton,
                               QWidget, QHeaderView, QMessageBox)

from . import materials as M
from .shapes import (make_custom, KIND_LABELS, W_SHAPE, CHANNEL, ANGLE, TEE, HSS_RECT,
                     HSS_ROUND, PIPE, PLATE)

# que dimensiones pide cada tipo:  (d, bf, tw, tf) -> etiqueta o None
DIMS = {
    W_SHAPE: ("d  (peralte)", "bf (ancho de ala)", "tw (alma)", "tf (ala)"),
    CHANNEL: ("d  (peralte)", "bf (ancho de ala)", "tw (alma)", "tf (ala)"),
    TEE: ("d  (altura total)", "bf (ancho de ala)", "tw (alma)", "tf (ala)"),
    ANGLE: ("Ala larga (vertical)", "Ala corta (horizontal)", "t (espesor)", None),
    HSS_RECT: ("H (alto)", "B (ancho)", "t (pared)", None),
    HSS_ROUND: ("OD (diametro)", None, "t (pared)", None),
    PIPE: ("OD (diametro)", None, "t (pared)", None),
    PLATE: ("Largo (dir. Y)", "Ancho (dir. X)", None, None),
}


class SectionDialog(QDialog):
    """Crea o edita una seccion con dimensiones libres; las propiedades se
    calculan de los rectangulos que la forman (sin redondeos de laminacion)."""

    def __init__(self, us, parent=None, shape=None):
        super().__init__(parent)
        self.setWindowTitle("Seccion personalizada")
        self.us = us
        self.result_shape = None
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.ed_name = QLineEdit(shape.label if shape else "MI-SECCION-1")
        fl.addRow("Nombre", self.ed_name)
        self.cb_kind = QComboBox()
        self.kinds = list(DIMS.keys())
        self.cb_kind.addItems([KIND_LABELS[k] for k in self.kinds])
        fl.addRow("Tipo", self.cb_kind)
        self.sp = []
        self.lbl = []
        for _ in range(4):
            w = QDoubleSpinBox()
            w.setDecimals(us.dec("L"))
            w.setRange(0.0, us.out("L", 200.0))
            w.setSuffix(" " + us.L)
            w.valueChanged.connect(self._props)
            lb = QLabel("")
            fl.addRow(lb, w)
            self.sp.append(w)
            self.lbl.append(lb)
        lay.addLayout(fl)
        self.info = QLabel("")
        self.info.setStyleSheet("color:#1f3864;")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.cb_kind.currentIndexChanged.connect(self._kind)
        if shape:
            self.cb_kind.setCurrentIndex(self.kinds.index(shape.kind)
                                         if shape.kind in self.kinds else 0)
            vals = (shape.d, shape.bf, shape.tw, shape.tf)
        else:
            vals = (12.0, 8.0, 0.375, 0.5)
        self._kind()
        for w, v in zip(self.sp, vals):
            w.setValue(us.out("L", v))
        self._props()

    def _kind(self):
        k = self.kinds[self.cb_kind.currentIndex()]
        for w, lb, txt in zip(self.sp, self.lbl, DIMS[k]):
            w.setVisible(txt is not None)
            lb.setVisible(txt is not None)
            lb.setText(txt or "")
        self._props()

    def _vals(self):
        k = self.kinds[self.cb_kind.currentIndex()]
        d, bf, tw, tf = (self.us.inn("L", w.value()) for w in self.sp)
        if k in (HSS_ROUND, PIPE):
            bf = d
        if k == PLATE:
            tw = min(d, bf)
        return k, d, bf, tw, tf

    def _props(self):
        try:
            k, d, bf, tw, tf = self._vals()
            s = make_custom("tmp", k, d, bf, tw, tf)
            u = self.us
            self.info.setText(
                f"A = {u.q('A', s.A)}   Ix = {s.Ix:.4g} in⁴   Iy = {s.Iy:.4g} in⁴<br>"
                f"Sx = {s.Sx:.4g} in³   Zx = {s.Zx:.4g} in³   "
                f"Sy = {s.Sy:.4g} in³   Zy = {s.Zy:.4g} in³<br>"
                "Propiedades calculadas de los rectangulos (sin redondeos de laminacion).")
            return s
        except Exception as e:
            self.info.setText(f"Dimensiones no validas: {e}")
            return None

    def _ok(self):
        name = self.ed_name.text().strip()
        if not name:
            return
        k, d, bf, tw, tf = self._vals()
        if d <= 0 or (bf <= 0 and k not in (HSS_ROUND, PIPE)) or tw <= 0:
            QMessageBox.warning(self, "Seccion", "Complete todas las dimensiones.")
            return
        self.result_shape = make_custom(name, k, d, bf, tw, tf)
        self.accept()
