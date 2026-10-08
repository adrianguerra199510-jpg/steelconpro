# -*- coding: utf-8 -*-
"""Pestaña de entrada de los modulos de nudo (viga-columna, viga a viga, crucetas): miembro principal + tabla de miembros conectados y su editor.

`NodeForm` es un `ui_widgets.Form` (se carga y se guarda como los demas formularios): los campos escalares del principal usan el mecanismo de
siempre y la lista de miembros se sincroniza a mano.  El miembro seleccionado se edita en un formulario interior cuyas rutas son 'm.campo'.
"""
from __future__ import annotations
import copy
from types import SimpleNamespace

from PySide6.QtWidgets import (QWidget, QComboBox, QSizePolicy, QHBoxLayout, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
                               QAbstractItemView)
from PySide6.QtCore import Qt, Signal

from . import materials as M
from .shapes import CATALOG
from .ui_widgets import Form
from .conn import presets as PRE
from .conn.specs import (MODE_COL, MODE_BEAM, MODE_CHORD, END_LABELS, MAIN_NAMES, MEMBER_NAMES, POS_LABELS, OFF_LABELS, CONNECT_KINDS, BOLT_GRADES,
                         SHEAR_BOLT_SIZES, CK_BLANK, CK_TAB, CK_DANG, CK_SEAT, CK_EP_FLUSH, CK_EP_EXT, CK_WELD, CK_GUSSET, CK_GUSSET_W,
                         GUSSET_KINDS)


class SectionPicker(QWidget):
    """Familia + perfil del catalogo (cualquier seccion: I, canal, angulo, te, HSS, tubo)."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.fam = QComboBox()
        self.fam.setMinimumWidth(70)
        self.shp = QComboBox()
        self.shp.setEditable(True)
        self.shp.setMaxVisibleItems(25)
        self.shp.setMinimumWidth(100)
        lay.addWidget(self.fam)
        lay.addWidget(self.shp, 1)
        self.fam.addItems(CATALOG.families())
        self.fam.currentTextChanged.connect(self._on_family)
        self.shp.currentTextChanged.connect(self._on_shape)
        self._silent = False
        self._fill(self.fam.currentText())

    def _fill(self, fam, select=None):
        self._silent = True
        self.shp.clear()
        self.shp.addItems(CATALOG.by_family(fam))
        if select:
            i = self.shp.findText(select)
            if i >= 0:
                self.shp.setCurrentIndex(i)
        self._silent = False

    def _on_family(self, fam):
        if self._silent:
            return
        self._fill(fam)
        self.changed.emit()

    def _on_shape(self, _t):
        if not self._silent:
            self.changed.emit()

    def set_label(self, label):
        s = CATALOG.get(label)
        self._silent = True
        if s is not None and s.family:
            self.fam.setCurrentText(s.family)
            self._fill(s.family, s.label)
        else:
            self.shp.setEditText(str(label))
        self._silent = False

    def label(self) -> str:
        t = self.shp.currentText().strip()
        s = CATALOG.get(t)
        return s.label if s is not None else t


def _steel_names():
    return [x.name for x in M.SHAPE_STEELS]


def _plate_names():
    return [x.name for x in M.PLATE_STEELS]


class NodeForm(Form):
    """Pestaña de un modulo de nudo."""

    def __init__(self, mod, win=None):
        self._us = None
        super().__init__()
        self.mod, self.win = mod, win
        mode, attr = mod.MODE, mod.ATTR
        self.mode, self.attr = mode, attr
        self._sel = 0
        self._busy = False
        self._hold = SimpleNamespace(m=None)

        # ---------------------------------------------------------------- miembro principal
        self.group(MAIN_NAMES[mode])
        self.main_pick = SectionPicker()
        self.main_pick.changed.connect(self._emit)
        self._lay.addRow("Sección", self.main_pick)
        self.combo("Acero", f"{attr}.main_steel", _steel_names())
        self.combo("Extremo", f"{attr}.main_end", END_LABELS[mode],
                   help="Intermedio: el miembro continúa a los dos lados del nudo. Extremo: termina en el nudo (por ejemplo la columna del último piso).")
        lneg = "Largo hacia abajo (bajo el nudo)" if mode == MODE_COL else "Largo hacia −X"
        lpos = "Largo hacia arriba (sobre el nudo)" if mode == MODE_COL else "Largo hacia +X"
        self.num(lneg, f"{attr}.main_len_neg", 1.0, 5000.0, uk="L")
        self.num(lpos, f"{attr}.main_len_pos", 1.0, 5000.0, uk="L")
        self.num("Giro de la sección sobre su eje", f"{attr}.main_roll", -180.0, 180.0, step=15.0, dec=1, suffix="°",
                 help="0° = alma en el plano de las vigas que llegan por la cara del ala (eje fuerte).")
        if mode != MODE_COL:
            self.num("Inclinación del eje", f"{attr}.main_slope", -80.0, 80.0, step=5.0, dec=1, suffix="°")
        self.check("Dibujar los herrajes", f"{attr}.show_hw", help="Placas, ángulos y pernos de cada conexión.")

        # ---------------------------------------------------------------- miembros conectados
        self.group("Miembros conectados")
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Nombre", "Sección", "Azimut", "Elevación", "Posición", "Conexión"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setMinimumHeight(150)
        self.tbl.setMaximumHeight(210)
        self.tbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)      # el ancho lo da el panel, no las columnas
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for j, wd in enumerate((46, 78, 58, 66, 76)):
            self.tbl.setColumnWidth(j, wd)
        self.tbl.itemSelectionChanged.connect(self._row_selected)
        self._lay.addRow(self.tbl)
        row = QWidget()
        hb = QHBoxLayout(row)
        hb.setContentsMargins(0, 0, 0, 0)
        for txt, fn in (("Agregar", self._add), ("Duplicar", self._dup), ("Quitar", self._del)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            hb.addWidget(b)
        self._lay.addRow(row)
        row2 = QWidget()
        h2 = QHBoxLayout(row2)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.addWidget(QLabel("Conexión de todos:"))
        self.cb_all = QComboBox()
        self.cb_all.addItems(CONNECT_KINDS)
        h2.addWidget(self.cb_all, 1)
        b = QPushButton("Aplicar")
        b.clicked.connect(self._apply_all)
        h2.addWidget(b)
        self._lay.addRow(row2)
        self.note("Cada miembro llega al principal con su azimut (ángulo en planta, desde +X hacia +Y) y su elevación (inclinación sobre la horizontal; "
                  "una diagonal lleva cartela). La posición se mide desde el nudo a lo largo del miembro principal.")

        # ---------------------------------------------------------------- editor del miembro seleccionado
        self.mf = Form()
        self.mf.changed.connect(self._member_changed)
        self.mf.outer.setContentsMargins(0, 0, 0, 0)
        mf = self.mf
        mf.group("Miembro seleccionado")
        mf.text("Nombre", "m.name")
        self.m_pick = SectionPicker()
        self.m_pick.changed.connect(self._member_changed)
        mf._lay.addRow("Sección", self.m_pick)
        mf.combo("Acero", "m.steel", _steel_names())
        mf.num("Azimut (planta)", "m.az", -360.0, 360.0, step=5.0, dec=1, suffix="°",
               help="Ángulo en planta desde +X hacia +Y, visto desde arriba.")
        mf.num("Elevación", "m.el", -90.0, 90.0, step=5.0, dec=1, suffix="°",
               help="Inclinación sobre la horizontal: 0° viga, ±45° diagonal, ±90° montante.")
        mf.num(POS_LABELS[mode], "m.pos", -5000.0, 5000.0, uk="L", help="Medida desde el nudo (origen) a lo largo del eje del miembro principal.")
        if OFF_LABELS[mode]:
            mf.num(OFF_LABELS[mode], "m.off", -500.0, 500.0, uk="L")
        mf.num("Largo del miembro", "m.L", 1.0, 5000.0, uk="L")
        mf.num("Giro sobre su eje", "m.roll", -180.0, 180.0, step=15.0, dec=1, suffix="°")
        mf.num("Retranqueo del extremo", "m.gap", 0.0, 24.0, uk="L", help="Separación entre el extremo del miembro y la cara del miembro principal.")
        mf.group("Conexión del miembro")
        mf.combo("Tipo", "m.conn", CONNECT_KINDS)
        mf.combo("Diámetro de los pernos", "m.bolt_size", SHEAR_BOLT_SIZES)
        mf.combo("Calidad de los pernos", "m.bolt_grade", BOLT_GRADES)
        mf.int_("Pernos por fila (o filas de la cartela)", "m.n_bolts", 1, 12)
        mf.num("Separación de los pernos", "m.bolt_s", 1.0, 24.0, uk="L")
        mf.num("Espesor de placas y ángulos", "m.plate_t", 0.0625, 4.0, uk="L", step=0.0625)
        mf.combo("Acero de las placas", "m.plate_steel", _plate_names())
        mf.num("Extensión de la placa extrema", "m.ep_ext", 0.5, 24.0, uk="L")
        mf.check("Placas de continuidad en la columna", "m.cont")
        self.outer.addWidget(mf)
        self._set_member_widgets(False)
        for cb in self.findChildren(QComboBox):                 # el ancho de un combo no depende de su opcion mas larga
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(10)
            cb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    # ---------------------------------------------------------------- unidades: se propagan al formulario interior
    @property
    def us(self):
        return self._us

    @us.setter
    def us(self, v):
        self._us = v
        if hasattr(self, "mf"):
            self.mf.us = v

    # ---------------------------------------------------------------- acceso al modelo
    def _nodo(self):
        return getattr(self._prj, self.attr)

    @staticmethod
    def _ensure_item(cb, text):
        """Agrega al combo un valor que no esta en la lista (p. ej. un acero personalizado del proyecto) para que no se pierda al guardar."""
        if text and cb.findText(text) < 0:
            cb.addItem(text)

    def load(self, prj):
        self._prj = prj
        nd0 = getattr(prj, self.attr)
        self._ensure_item(self.w(f"{self.attr}.main_steel"), nd0.main_steel)
        super().load(prj)
        nd = self._nodo()
        self._busy = True
        self.main_pick.set_label(nd.main_shape)
        self._sel = max(0, min(self._sel, len(nd.members) - 1))
        self._fill_table()
        self._busy = False
        self._load_member()

    def store(self, prj):
        self._prj = prj
        super().store(prj)
        nd = getattr(prj, self.attr)
        nd.main_shape = self.main_pick.label()
        self._store_member(prj)

    # ---------------------------------------------------------------- tabla
    def _fill_table(self):
        nd = self._nodo()
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(nd.members))
        for i, m in enumerate(nd.members):
            for j, txt in enumerate((m.name, m.shape, f"{m.az:g}°", f"{m.el:g}°", self._pos_text(m), m.conn)):
                it = QTableWidgetItem(txt)
                if j in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl.setItem(i, j, it)
        if nd.members:
            self.tbl.selectRow(max(0, min(self._sel, len(nd.members) - 1)))
        self.tbl.blockSignals(False)

    def _pos_text(self, m):
        u = self.us
        if u is None:
            return f"{m.pos:g}"
        return f"{u.out('L', m.pos):.4g} {u.label('L')}"

    def _row_selected(self):
        if self._busy:
            return
        r = self.tbl.currentRow()
        nd = self._nodo()
        if 0 <= r < len(nd.members) and r != self._sel:
            self._store_member(self._prj)
            self._sel = r
            self._load_member()

    # ---------------------------------------------------------------- editor del miembro
    def _set_member_widgets(self, on):
        self.mf.setEnabled(bool(on))

    def _load_member(self):
        nd = self._nodo()
        self._hold.m = nd.members[self._sel] if nd.members else None
        self._set_member_widgets(self._hold.m is not None)
        if self._hold.m is None:
            return
        self._busy = True
        self.mf.us = self.us
        self._ensure_item(self.mf.w("m.steel"), self._hold.m.steel)
        self._ensure_item(self.mf.w("m.plate_steel"), self._hold.m.plate_steel)
        self.mf.load(self._hold)
        self.m_pick.set_label(self._hold.m.shape)
        self._busy = False
        self._visibility()

    def _store_member(self, prj):
        nd = getattr(prj, self.attr)
        if not nd.members or self._hold.m is None or self._hold.m not in nd.members:
            return
        self.mf.us = self.us
        self.mf.store(self._hold)
        self._hold.m.shape = self.m_pick.label()

    def _member_changed(self, *_):
        if self._busy or self._hold.m is None:
            return
        self._store_member(self._prj)
        self._busy = True
        self._fill_table()
        self._busy = False
        self._visibility()
        self.changed.emit()

    def _visibility(self):
        m = self._hold.m
        if m is None:
            return
        mf, c = self.mf, m.conn
        hw = c != CK_BLANK
        for p in ("m.bolt_size", "m.bolt_grade", "m.n_bolts", "m.bolt_s", "m.plate_t", "m.plate_steel"):
            mf.show_field(p, hw and not (c == CK_WELD and False))
        mf.show_field("m.ep_ext", c == CK_EP_EXT)
        mf.show_field("m.cont", c == CK_WELD and self.mode == MODE_COL)
        mf.show_field("m.gap", c in (CK_BLANK, CK_TAB, CK_DANG, CK_SEAT, CK_WELD))

    # ---------------------------------------------------------------- botones
    def _add(self):
        self._store_member(self._prj)
        nd = self._nodo()
        nd.members.append(PRE.new_member(nd))
        self._sel = len(nd.members) - 1
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_member()
        self.changed.emit()

    def _dup(self):
        nd = self._nodo()
        if not nd.members:
            return
        self._store_member(self._prj)
        m = copy.deepcopy(nd.members[self._sel])
        m.name = f"{m.name}'"
        m.az = (m.az + 90.0) % 360.0
        nd.members.insert(self._sel + 1, m)
        self._sel += 1
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_member()
        self.changed.emit()

    def _del(self):
        nd = self._nodo()
        if len(nd.members) <= 0 or not (0 <= self._sel < len(nd.members)):
            return
        del nd.members[self._sel]
        self._sel = max(0, min(self._sel, len(nd.members) - 1))
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_member()
        self.changed.emit()

    def _apply_all(self):
        nd = self._nodo()
        self._store_member(self._prj)
        for m in nd.members:
            m.conn = self.cb_all.currentText()
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_member()
        self.changed.emit()
