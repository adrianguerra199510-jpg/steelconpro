# -*- coding: utf-8 -*-
"""Dialogos: seccion personalizada y biblioteca de materiales."""
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


class MaterialsDialog(QDialog):
    """Biblioteca de materiales del usuario (acero, anclajes, concreto).
    Se guarda en %APPDATA%/PlacaBasePro/materials.json."""

    COLS = {"steel": ["Nombre", "Fy", "Fu"],
            "anchor": ["Nombre", "Fy", "Fu", "Ductil (si/no)"],
            "concrete": ["Nombre", "f'c", "λ (1 = peso normal)"]}
    TITLES = {"steel": "Acero (placa, perfil, llave)", "anchor": "Anclajes",
              "concrete": "Concreto"}

    def __init__(self, us, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de materiales")
        self.resize(640, 420)
        self.us = us
        data = M.user_materials()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Esfuerzos en {us.S}. Los materiales quedan disponibles en "
                             "todas las listas del programa y se guardan dentro de cada "
                             "proyecto que los use."))
        self.tabs = QTabWidget()
        self.tbl = {}
        for kind in ("steel", "anchor", "concrete"):
            w = QWidget(); vl = QVBoxLayout(w)
            t = QTableWidget(0, len(self.COLS[kind]))
            t.setHorizontalHeaderLabels(self.COLS[kind])
            t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for d in data.get(kind, []):
                self._add_row(t, kind, d)
            vl.addWidget(t)
            hl = QHBoxLayout()
            for txt, fn in (("Agregar", lambda _=0, k=kind: self._add_row(self.tbl[k], k)),
                            ("Quitar", lambda _=0, k=kind: self._del_row(self.tbl[k]))):
                b = QPushButton(txt); b.clicked.connect(fn); hl.addWidget(b)
            hl.addStretch(1)
            vl.addLayout(hl)
            self.tbl[kind] = t
            self.tabs.addTab(w, self.TITLES[kind])
        lay.addWidget(self.tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add_row(self, t, kind, d=None):
        u = self.us
        i = t.rowCount(); t.insertRow(i)
        if d is None:
            d = {"steel": {"name": "Acero nuevo", "Fy": 50.0, "Fu": 65.0},
                 "anchor": {"name": "Anclaje nuevo", "Fy": 55.0, "Fu": 75.0, "ductile": True},
                 "concrete": {"name": "Concreto nuevo", "fc": 4.0, "lam": 1.0}}[kind]
        if kind == "steel":
            vals = [d["name"], u.fmt("S", d["Fy"]), u.fmt("S", d["Fu"])]
        elif kind == "anchor":
            vals = [d["name"], u.fmt("S", d["Fy"]), u.fmt("S", d["Fu"]),
                    "si" if d.get("ductile", True) else "no"]
        else:
            vals = [d["name"], u.fmt("S", d["fc"]), f"{d.get('lam', 1.0):g}"]
        for j, v in enumerate(vals):
            t.setItem(i, j, QTableWidgetItem(str(v)))

    @staticmethod
    def _del_row(t):
        r = t.currentRow()
        if r >= 0:
            t.removeRow(r)

    def _save(self):
        u = self.us
        out = {}
        try:
            for kind, t in self.tbl.items():
                lst = []
                for i in range(t.rowCount()):
                    c = [t.item(i, j).text().strip() if t.item(i, j) else ""
                         for j in range(t.columnCount())]
                    if not c[0]:
                        continue
                    num = lambda x: float(x.replace(",", ""))
                    if kind == "steel":
                        lst.append({"name": c[0], "Fy": u.inn("S", num(c[1])),
                                    "Fu": u.inn("S", num(c[2]))})
                    elif kind == "anchor":
                        lst.append({"name": c[0], "Fy": u.inn("S", num(c[1])),
                                    "Fu": u.inn("S", num(c[2])),
                                    "ductile": c[3].lower().startswith(("s", "y", "1"))})
                    else:
                        lst.append({"name": c[0], "fc": u.inn("S", num(c[1])),
                                    "lam": num(c[2]) if c[2] else 1.0})
                out[kind] = lst
        except ValueError as e:
            QMessageBox.warning(self, "Materiales", f"Revise los valores numericos: {e}")
            return
        M.save_user_materials(out)
        self.accept()
