# -*- coding: utf-8 -*-
"""Pestaña de entrada de los modulos de nudo, con el flujo de trabajo por operaciones de IDEA StatiCa Connection:

    1 Miembros      el miembro principal y los miembros conectados (seccion, posicion, azimut, elevacion)
    2 Operaciones   lista ordenada de operaciones sobre los miembros (placa simple, doble angulo, placa extrema, cartela, corte, continuidad...)
    3 Cargas        esfuerzos internos en el extremo de cada miembro, por caso de carga
    4 Analisis      verificaciones por codigo (AISC 360-22) y analisis 3D por elementos finitos

`NodeForm` es un `ui_widgets.Form` (se carga y se guarda como los demas formularios) que reparte `load` / `store` entre las cuatro paginas.
"""
from __future__ import annotations
import copy
from types import SimpleNamespace

from PySide6.QtWidgets import (QWidget, QComboBox, QSizePolicy, QHBoxLayout, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
                               QAbstractItemView, QTabWidget, QToolButton, QMenu)
from PySide6.QtCore import Qt, Signal

from . import materials as M
from .shapes import CATALOG
from .ui_widgets import Form
from .conn import presets as PRE
from .conn.specs import (MODE_COL, MODE_BEAM, MODE_CHORD, END_LABELS, MAIN_NAMES, MEMBER_NAMES, POS_LABELS, OFF_LABELS, BOLT_GRADES,
                         SHEAR_BOLT_SIZES, OPERATIONS, OP_GROUPS, Operation, Load, OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET,
                         OP_GUSSET_W, OP_COPE, OP_CONT, CONNECTION_OPS, GUSSET_OPS)


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


def _ensure_item(cb, text):
    """Agrega al combo un valor que no esta en la lista (p. ej. un acero personalizado del proyecto) para que no se pierda al guardar."""
    if text and cb.findText(text) < 0:
        cb.addItem(text)


def _compact(widget):
    """El ancho de un combo no depende de su opcion mas larga (si no, el panel izquierdo se desborda)."""
    for cb in widget.findChildren(QComboBox):
        cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(10)
        cb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)


def _table(cols, widths, height=(150, 210)):
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.Interactive)
    hh.setStretchLastSection(True)
    for j, w in enumerate(widths):
        t.setColumnWidth(j, w)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setMinimumHeight(height[0])
    t.setMaximumHeight(height[1])
    t.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)      # el ancho lo da el panel, no las columnas
    return t


def _buttons(layout_owner, items):
    row = QWidget()
    hb = QHBoxLayout(row)
    hb.setContentsMargins(0, 0, 0, 0)
    out = []
    for txt, fn in items:
        b = QPushButton(txt)
        b.clicked.connect(fn)
        hb.addWidget(b)
        out.append(b)
    layout_owner._lay.addRow(row)
    return out


# ====================================================================================================== 1. miembros
class MembersPage(Form):
    """Miembro principal + tabla de miembros conectados y su editor (solo geometria: la conexion se define en Operaciones)."""
    renamed = Signal(str, str)               # nombre anterior, nombre nuevo
    removed = Signal(str)
    duplicated = Signal(str, str)

    def __init__(self, mod):
        self._us = None
        super().__init__()
        self.mod = mod
        mode, attr = mod.MODE, mod.ATTR
        self.mode, self.attr = mode, attr
        self._sel, self._busy, self._old = 0, False, ""
        self._hold = SimpleNamespace(m=None)

        self.group(MAIN_NAMES[mode])
        self.main_pick = SectionPicker()
        self.main_pick.changed.connect(self._emit)
        self._lay.addRow("Sección", self.main_pick)
        self.combo("Acero", f"{attr}.main_steel", _steel_names())
        self.combo("Extremo", f"{attr}.main_end", END_LABELS[mode],
                   help="Intermedio: el miembro continúa a los dos lados del nudo. Extremo: termina en el nudo (por ejemplo la columna del último piso).")
        self.num("Largo hacia abajo (bajo el nudo)" if mode == MODE_COL else "Largo hacia −X", f"{attr}.main_len_neg", 1.0, 5000.0, uk="L")
        self.num("Largo hacia arriba (sobre el nudo)" if mode == MODE_COL else "Largo hacia +X", f"{attr}.main_len_pos", 1.0, 5000.0, uk="L")
        self.num("Giro de la sección sobre su eje", f"{attr}.main_roll", -180.0, 180.0, step=15.0, dec=1, suffix="°",
                 help="0° = alma en el plano de las vigas que llegan por la cara del ala (eje fuerte).")
        if mode != MODE_COL:
            self.num("Inclinación del eje", f"{attr}.main_slope", -80.0, 80.0, step=5.0, dec=1, suffix="°")
        self.check("Dibujar los herrajes", f"{attr}.show_hw", help="Placas, ángulos y pernos de las operaciones.")

        self.group("Miembros conectados")
        self.tbl = _table(["Nombre", "Sección", "Azimut", "Elevación", "Posición"], (50, 90, 60, 70, 80))
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.itemSelectionChanged.connect(self._row_selected)
        self._lay.addRow(self.tbl)
        _buttons(self, (("Agregar", self._add), ("Duplicar", self._dup), ("Quitar", self._del)))
        self.note("Cada miembro llega al principal con su azimut (ángulo en planta, desde +X hacia +Y) y su elevación (inclinación sobre la horizontal; "
                  "una diagonal lleva cartela). La posición se mide desde el nudo a lo largo del miembro principal. La conexión se define en el paso 2 (Operaciones).")

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
        mf.num("Azimut (planta)", "m.az", -360.0, 360.0, step=5.0, dec=1, suffix="°", help="Ángulo en planta desde +X hacia +Y, visto desde arriba.")
        mf.num("Elevación", "m.el", -90.0, 90.0, step=5.0, dec=1, suffix="°", help="Inclinación sobre la horizontal: 0° viga, ±45° diagonal, ±90° montante.")
        mf.num(POS_LABELS[mode], "m.pos", -5000.0, 5000.0, uk="L", help="Medida desde el nudo (origen) a lo largo del eje del miembro principal.")
        if OFF_LABELS[mode]:
            mf.num(OFF_LABELS[mode], "m.off", -500.0, 500.0, uk="L")
        mf.num("Largo del miembro", "m.L", 1.0, 5000.0, uk="L")
        mf.num("Giro sobre su eje", "m.roll", -180.0, 180.0, step=15.0, dec=1, suffix="°")
        mf.num("Retranqueo del extremo", "m.gap", 0.0, 24.0, uk="L", help="Separación entre el extremo del miembro y la cara del miembro principal.")
        self.outer.addWidget(mf)
        self.mf.setEnabled(False)
        _compact(self)

    @property
    def us(self):
        return self._us

    @us.setter
    def us(self, v):
        self._us = v
        if hasattr(self, "mf"):
            self.mf.us = v

    def _nodo(self):
        return getattr(self._prj, self.attr)

    def load(self, prj):
        self._prj = prj
        nd = self._nodo()
        _ensure_item(self.w(f"{self.attr}.main_steel"), nd.main_steel)
        super().load(prj)
        self._busy = True
        self.main_pick.set_label(nd.main_shape)
        self._sel = max(0, min(self._sel, len(nd.members) - 1))
        self._fill_table()
        self._busy = False
        self._load_member()

    def store(self, prj):
        self._prj = prj
        super().store(prj)
        getattr(prj, self.attr).main_shape = self.main_pick.label()
        self._store_member(prj)

    def _fill_table(self):
        nd = self._nodo()
        u = self.us
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(nd.members))
        for i, m in enumerate(nd.members):
            pos = f"{m.pos:g}" if u is None else f"{u.out('L', m.pos):.4g} {u.label('L')}"
            for j, txt in enumerate((m.name, m.shape, f"{m.az:g}°", f"{m.el:g}°", pos)):
                it = QTableWidgetItem(txt)
                if j >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl.setItem(i, j, it)
        if nd.members:
            self.tbl.selectRow(max(0, min(self._sel, len(nd.members) - 1)))
        self.tbl.blockSignals(False)

    def _row_selected(self):
        if self._busy:
            return
        r = self.tbl.currentRow()
        nd = self._nodo()
        if 0 <= r < len(nd.members) and r != self._sel:
            self._store_member(self._prj)
            self._sel = r
            self._load_member()

    def _load_member(self):
        nd = self._nodo()
        self._hold.m = nd.members[self._sel] if nd.members else None
        self.mf.setEnabled(self._hold.m is not None)
        if self._hold.m is None:
            return
        self._busy = True
        self.mf.us = self.us
        _ensure_item(self.mf.w("m.steel"), self._hold.m.steel)
        self.mf.load(self._hold)
        self.m_pick.set_label(self._hold.m.shape)
        self._old = self._hold.m.name
        self._busy = False

    def _store_member(self, prj):
        nd = getattr(prj, self.attr)
        if not nd.members or self._hold.m is None or self._hold.m not in nd.members:
            return
        self.mf.us = self.us
        self.mf.store(self._hold)
        self._hold.m.shape = self.m_pick.label()
        new = self._hold.m.name.strip() or self._old
        if new != self._hold.m.name:
            self._hold.m.name = new
        if self._old and new != self._old:                      # renombrar el miembro: las operaciones y las cargas lo siguen
            old, self._old = self._old, new
            nd.rename_member(old, new)
            self.renamed.emit(old, new)

    def _member_changed(self, *_):
        if self._busy or self._hold.m is None:
            return
        self._store_member(self._prj)
        self._busy = True
        self._fill_table()
        self._busy = False
        self.changed.emit()

    def _refill(self):
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_member()
        self.changed.emit()

    def _add(self):
        self._store_member(self._prj)
        nd = self._nodo()
        m = PRE.new_member(nd)
        names = {x.name for x in nd.members}
        while m.name in names:
            m.name += "'"
        nd.members.append(m)
        self._sel = len(nd.members) - 1
        self._refill()

    def _dup(self):
        nd = self._nodo()
        if not nd.members:
            return
        self._store_member(self._prj)
        src = nd.members[self._sel]
        m = copy.deepcopy(src)
        m.name = f"{src.name}'"
        m.az = (m.az + 90.0) % 360.0
        nd.members.insert(self._sel + 1, m)
        self._sel += 1
        self.duplicated.emit(src.name, m.name)
        self._refill()

    def _del(self):
        nd = self._nodo()
        if not (0 <= self._sel < len(nd.members)):
            return
        name = nd.members[self._sel].name
        del nd.members[self._sel]
        self._sel = max(0, min(self._sel, len(nd.members) - 1))
        self.removed.emit(name)
        self._refill()

    def select(self, name):
        nd = self._nodo()
        for i, m in enumerate(nd.members):
            if m.name == name:
                self._sel = i
                self._busy = True
                self.tbl.selectRow(i)
                self._busy = False
                self._load_member()
                return


# ====================================================================================================== 2. operaciones
OP_DEFAULTS = {OP_TAB: dict(plate_t=0.375, n_bolts=3), OP_DANG: dict(plate_t=0.375, n_bolts=3), OP_SEAT: dict(plate_t=0.5, n_bolts=2),
               OP_EP_FLUSH: dict(plate_t=0.75), OP_EP_EXT: dict(plate_t=0.75, ep_ext=3.0), OP_WELD: dict(plate_t=0.375, n_bolts=3),
               OP_GUSSET: dict(plate_t=0.5, n_bolts=3), OP_GUSSET_W: dict(plate_t=0.5), OP_COPE: dict(cope_top=2.0, cope_len=4.5), OP_CONT: dict(cont_t=0.5)}
OP_HELP = {OP_TAB: "Placa soldada al miembro principal y atornillada al alma del miembro conectado (una fila vertical de pernos).",
           OP_DANG: "Dos ángulos en el alma del miembro conectado, atornillados al principal.",
           OP_SEAT: "Ángulo de asiento bajo el ala inferior del miembro conectado.",
           OP_EP_FLUSH: "Placa soldada al extremo del miembro y atornillada al ala del principal; pernos entre las alas.",
           OP_EP_EXT: "Placa extrema que se extiende por encima (y debajo) de las alas; pernos dentro y fuera de ellas.",
           OP_WELD: "Alas soldadas al principal; el alma lleva una placa simple atornillada.",
           OP_GUSSET: "Cartela soldada al principal y atornillada a la diagonal; las diagonales del mismo plano comparten cartela.",
           OP_GUSSET_W: "Cartela soldada al principal con la diagonal soldada a la cartela (sin pernos).",
           OP_COPE: "Recorta las alas (y parte del alma) en el extremo del miembro conectado, para que quepa contra el principal.",
           OP_CONT: "Placas horizontales dentro de la columna I, a la altura de las alas del miembro conectado."}


def op_summary(o: Operation) -> str:
    if o.kind in (OP_TAB, OP_DANG, OP_WELD):
        return f"{o.n_bolts} pernos Ø{o.bolt_size} {o.bolt_grade}, e = {o.plate_t:g} in"
    if o.kind == OP_SEAT:
        return f"ángulo e = {o.plate_t:g} in, pernos Ø{o.bolt_size}"
    if o.kind in (OP_EP_FLUSH, OP_EP_EXT):
        return f"placa e = {o.plate_t:g} in, pernos Ø{o.bolt_size} {o.bolt_grade}" + (f", extensión {o.ep_ext:g} in" if o.kind == OP_EP_EXT else "")
    if o.kind == OP_GUSSET:
        return f"cartela e = {o.plate_t:g} in, {o.n_bolts} filas de pernos Ø{o.bolt_size}"
    if o.kind == OP_GUSSET_W:
        return f"cartela e = {o.plate_t:g} in, filete {o.weld_size:g} in"
    if o.kind == OP_COPE:
        return f"superior {o.cope_top:g} in, inferior {o.cope_bot:g} in, largo {o.cope_len:g} in"
    if o.kind == OP_CONT:
        return f"placas e = {o.cont_t:g} in"
    return ""


class OperationsPage(Form):
    """Lista ordenada de operaciones (como el panel Operations de IDEA) y editor de la seleccionada."""

    def __init__(self, mod):
        self._us = None
        super().__init__()
        self.mod = mod
        self.attr = mod.ATTR
        self._sel, self._busy = 0, False
        self._hold = SimpleNamespace(o=None)
        self.group("Operaciones del nudo")
        self.note("La conexión se arma aplicando operaciones, en orden, a los miembros (como en IDEA StatiCa Connection). El 3D se actualiza con cada cambio.")
        self.tbl = _table(["#", "Operación", "Miembro", "Resumen"], (28, 150, 60, 200), (140, 220))
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.itemSelectionChanged.connect(self._row_selected)
        self._lay.addRow(self.tbl)
        row = QWidget()
        hb = QHBoxLayout(row)
        hb.setContentsMargins(0, 0, 0, 0)
        self.btn_add = QToolButton()
        self.btn_add.setText("Agregar operación ▾")
        self.btn_add.setPopupMode(QToolButton.InstantPopup)
        self.btn_add.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(self.btn_add)
        for gname, kinds in OP_GROUPS:
            act = menu.addAction(gname)
            act.setEnabled(False)
            f = act.font()
            f.setBold(True)
            act.setFont(f)
            for k in kinds:
                a = menu.addAction("   " + k)
                a.triggered.connect(lambda _c=False, kind=k: self._add(kind))
                a.setToolTip(OP_HELP.get(k, ""))
        self.btn_add.setMenu(menu)
        hb.addWidget(self.btn_add)
        for txt, fn in (("Duplicar", self._dup), ("Quitar", self._del), ("▲", self._up), ("▼", self._down)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            if txt in ("▲", "▼"):
                b.setMaximumWidth(34)
            hb.addWidget(b)
        self._lay.addRow(row)

        self.of = Form()
        self.of.changed.connect(self._op_changed)
        self.of.outer.setContentsMargins(0, 0, 0, 0)
        of = self.of
        of.group("Operación seleccionada")
        self.lbl_help = QLabel("")
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet("color:#595959; font-size:8pt;")
        of._lay.addRow(self.lbl_help)
        of.combo("Tipo", "o.kind", OPERATIONS)
        of.combo("Miembro", "o.member", [])
        of.combo("Diámetro de los pernos", "o.bolt_size", SHEAR_BOLT_SIZES)
        of.combo("Calidad de los pernos", "o.bolt_grade", BOLT_GRADES)
        of.int_("Pernos por fila (o filas de la cartela)", "o.n_bolts", 1, 12)
        of.num("Separación de los pernos", "o.bolt_s", 1.0, 24.0, uk="L")
        of.num("Espesor de la placa / ángulo / cartela", "o.plate_t", 0.0625, 4.0, uk="L", step=0.0625)
        of.combo("Acero de la placa", "o.plate_steel", _plate_names())
        of.num("Cateto del filete", "o.weld_size", 0.0625, 1.0, uk="L", step=0.0625)
        of.num("Extensión de la placa extrema", "o.ep_ext", 0.5, 24.0, uk="L")
        of.num("Corte superior: profundidad", "o.cope_top", 0.0, 24.0, uk="L")
        of.num("Corte inferior: profundidad", "o.cope_bot", 0.0, 24.0, uk="L")
        of.num("Corte: largo desde el extremo", "o.cope_len", 0.0, 48.0, uk="L")
        of.num("Espesor de las placas de continuidad", "o.cont_t", 0.125, 4.0, uk="L", step=0.0625)
        self.outer.addWidget(of)
        self.of.setEnabled(False)
        _compact(self)

    @property
    def us(self):
        return self._us

    @us.setter
    def us(self, v):
        self._us = v
        if hasattr(self, "of"):
            self.of.us = v

    def _nodo(self):
        return getattr(self._prj, self.attr)

    def load(self, prj):
        self._prj = prj
        nd = self._nodo()
        cb = self.of.w("o.member")
        cb.blockSignals(True)
        cb.clear()
        cb.addItems([m.name for m in nd.members])
        cb.blockSignals(False)
        self._sel = max(0, min(self._sel, len(nd.operations) - 1))
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_op()

    def store(self, prj):
        self._prj = prj
        self._store_op()

    def _fill_table(self):
        nd = self._nodo()
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(nd.operations))
        for i, o in enumerate(nd.operations):
            for j, txt in enumerate((str(i + 1), o.kind, o.member, op_summary(o))):
                self.tbl.setItem(i, j, QTableWidgetItem(txt))
        if nd.operations:
            self.tbl.selectRow(max(0, min(self._sel, len(nd.operations) - 1)))
        self.tbl.blockSignals(False)

    def _row_selected(self):
        if self._busy:
            return
        r = self.tbl.currentRow()
        nd = self._nodo()
        if 0 <= r < len(nd.operations) and r != self._sel:
            self._store_op()
            self._sel = r
            self._load_op()

    def _load_op(self):
        nd = self._nodo()
        self._hold.o = nd.operations[self._sel] if nd.operations else None
        self.of.setEnabled(self._hold.o is not None)
        if self._hold.o is None:
            self.lbl_help.setText("Agregue una operación con «Agregar operación».")
            return
        self._busy = True
        self.of.us = self.us
        cb = self.of.w("o.member")
        _ensure_item(cb, self._hold.o.member)
        _ensure_item(self.of.w("o.plate_steel"), self._hold.o.plate_steel)
        self.of.load(self._hold)
        self._busy = False
        self._visibility()

    def _store_op(self):
        nd = self._nodo()
        if self._hold.o is None or self._hold.o not in nd.operations:
            return
        self.of.us = self.us
        self.of.store(self._hold)

    def _visibility(self):
        o = self._hold.o
        if o is None:
            return
        k = o.kind
        of = self.of
        self.lbl_help.setText(OP_HELP.get(k, ""))
        show = {
            "o.bolt_size": k in (OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET),
            "o.bolt_grade": k in (OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET),
            "o.n_bolts": k in (OP_TAB, OP_DANG, OP_WELD, OP_GUSSET),
            "o.bolt_s": k in (OP_TAB, OP_DANG, OP_WELD, OP_GUSSET),
            "o.plate_t": k not in (OP_COPE, OP_CONT),
            "o.plate_steel": k not in (OP_COPE, OP_CONT),
            "o.weld_size": k not in (OP_COPE, OP_CONT, OP_SEAT),
            "o.ep_ext": k == OP_EP_EXT,
            "o.cope_top": k == OP_COPE, "o.cope_bot": k == OP_COPE, "o.cope_len": k == OP_COPE,
            "o.cont_t": k == OP_CONT,
        }
        for p, on in show.items():
            of.show_field(p, on)

    def _op_changed(self, *_):
        if self._busy or self._hold.o is None:
            return
        old = self._hold.o.kind
        self._store_op()
        if self._hold.o.kind != old:                           # al cambiar el tipo se adoptan los valores tipicos del nuevo
            for k, v in OP_DEFAULTS.get(self._hold.o.kind, {}).items():
                setattr(self._hold.o, k, v)
            self._busy = True
            self.of.load(self._hold)
            self._busy = False
        self._visibility()
        self._busy = True
        self._fill_table()
        self._busy = False
        self.changed.emit()

    def _refill(self):
        self._busy = True
        self._fill_table()
        self._busy = False
        self._load_op()
        self.changed.emit()

    def _add(self, kind, member=None):
        self._store_op()
        nd = self._nodo()
        if not nd.members:
            return
        if member is None:
            sel = self.selected_member
            member = sel if sel in {m.name for m in nd.members} else nd.members[0].name
        o = Operation(kind=kind, member=member, **OP_DEFAULTS.get(kind, {}))
        if o.is_connection:                                    # una sola conexion por miembro: la nueva reemplaza a la anterior
            nd.operations = [x for x in nd.operations if not (x.member == member and x.is_connection)]
        nd.operations.append(o)
        self._sel = len(nd.operations) - 1
        self._refill()

    selected_member = ""

    def _dup(self):
        nd = self._nodo()
        if not nd.operations:
            return
        self._store_op()
        o = copy.deepcopy(nd.operations[self._sel])
        nd.operations.insert(self._sel + 1, o)
        self._sel += 1
        self._refill()

    def _del(self):
        nd = self._nodo()
        if not (0 <= self._sel < len(nd.operations)):
            return
        del nd.operations[self._sel]
        self._sel = max(0, min(self._sel, len(nd.operations) - 1))
        self._refill()

    def _move(self, d):
        nd = self._nodo()
        j = self._sel + d
        if 0 <= self._sel < len(nd.operations) and 0 <= j < len(nd.operations):
            self._store_op()
            nd.operations[self._sel], nd.operations[j] = nd.operations[j], nd.operations[self._sel]
            self._sel = j
            self._refill()

    def _up(self):
        self._move(-1)

    def _down(self):
        self._move(1)

    # ---- sincronizacion con la pagina de miembros
    def on_member_removed(self, name):
        nd = self._nodo()
        nd.operations = [o for o in nd.operations if o.member != name]
        nd.loads = [x for x in nd.loads if x.member != name]

    def on_member_duplicated(self, src, new):
        nd = self._nodo()
        for o in [o for o in nd.operations if o.member == src]:
            c = copy.deepcopy(o)
            c.member = new
            nd.operations.append(c)


# ====================================================================================================== 3. cargas
LOAD_COLS = [("N", "F"), ("Vy", "F"), ("Vz", "F"), ("T", "M"), ("My", "M"), ("Mz", "M")]


class LoadsPage(Form):
    """Esfuerzos internos en el extremo de cada miembro, por caso de carga."""

    def __init__(self, mod):
        self._us = None
        super().__init__()
        self.mod = mod
        self.attr = mod.ATTR
        self._busy = False
        self.group("Cargas")
        self.note("Esfuerzos internos del miembro junto al nudo, en sus ejes locales: x a lo largo del miembro (desde el nudo hacia fuera; N > 0 = tracción), "
                  "z en el peralte (vertical en una viga) e y = z × x. Cada fila es un miembro en un caso de carga; los casos se verifican todos y gobierna el peor.")
        self.tbl = _table(["Caso", "Miembro"] + [n for n, _k in LOAD_COLS], (70, 60) + (52,) * 6, (170, 280))
        self.tbl.itemChanged.connect(lambda *_: self._edited())
        self._lay.addRow(self.tbl)
        _buttons(self, (("Agregar caso", self._add_case), ("Agregar fila", self._add_row), ("Quitar", self._del)))
        _compact(self)

    def _nodo(self):
        return getattr(self._prj, self.attr)

    def _labels(self):
        u = self.us
        self.tbl.setHorizontalHeaderLabels(["Caso", "Miembro"] + [f"{n} ({u.label(k)})" if u else n for n, k in LOAD_COLS])

    def load(self, prj):
        self._prj = prj
        nd = self._nodo()
        u = self.us
        self._busy = True
        self.tbl.blockSignals(True)
        self._labels()
        self.tbl.setRowCount(len(nd.loads))
        for i, x in enumerate(nd.loads):
            self.tbl.setItem(i, 0, QTableWidgetItem(x.case))
            cb = QComboBox()
            cb.addItems([m.name for m in nd.members])
            if cb.findText(x.member) < 0:
                cb.addItem(x.member)
            cb.setCurrentText(x.member)
            cb.currentTextChanged.connect(lambda *_: self._edited())
            self.tbl.setCellWidget(i, 1, cb)
            for j, (n, k) in enumerate(LOAD_COLS):
                v = getattr(x, n)
                self.tbl.setItem(i, 2 + j, QTableWidgetItem(f"{(u.out(k, v) if u else v):.6g}"))
        self.tbl.blockSignals(False)
        self._busy = False

    def store(self, prj):
        self._prj = prj
        nd = self._nodo()
        u = self.us
        out = []
        for i in range(self.tbl.rowCount()):
            try:
                case = self.tbl.item(i, 0).text().strip() or f"Caso {i + 1}"
                mem = self.tbl.cellWidget(i, 1).currentText()
                vals = {}
                for j, (n, k) in enumerate(LOAD_COLS):
                    v = float(self.tbl.item(i, 2 + j).text().replace(",", ""))
                    if v != v or abs(v) == float("inf"):
                        raise ValueError
                    vals[n] = u.inn(k, v) if u else v
                out.append(Load(case, mem, **vals))
            except (AttributeError, ValueError):
                if i < len(nd.loads):
                    out.append(nd.loads[i])
        nd.loads = out

    def _edited(self):
        if self._busy:
            return
        self.store(self._prj)
        self.changed.emit()

    def _add_case(self):
        self.store(self._prj)
        nd = self._nodo()
        n = len({x.case for x in nd.loads}) + 1
        for m in nd.members:
            nd.loads.append(Load(f"Caso {n}", m.name))
        self.load(self._prj)
        self.changed.emit()

    def _add_row(self):
        self.store(self._prj)
        nd = self._nodo()
        case = nd.loads[-1].case if nd.loads else "Caso 1"
        used = {x.member for x in nd.loads if x.case == case}
        mem = next((m.name for m in nd.members if m.name not in used), nd.members[0].name if nd.members else "")
        nd.loads.append(Load(case, mem))
        self.load(self._prj)
        self.changed.emit()

    def _del(self):
        self.store(self._prj)
        nd = self._nodo()
        r = self.tbl.currentRow()
        if 0 <= r < len(nd.loads):
            del nd.loads[r]
            self.load(self._prj)
            self.changed.emit()

    def on_renamed(self, old, new):
        pass                                                   # nd.rename_member ya lo hizo; solo hay que redibujar


# ====================================================================================================== 4. analisis
class AnalysisPage(QWidget):
    """Lanza las verificaciones por codigo y el analisis 3D, y muestra el estado."""
    check_requested = Signal()
    fem_requested = Signal()
    report_requested = Signal()

    def __init__(self, mod):
        super().__init__()
        self.mod = mod
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(QLabel("<b>Análisis del nudo</b>"))
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.btn_chk = QPushButton("Verificar por código (AISC 360-22)")
        self.btn_chk.clicked.connect(self.check_requested.emit)
        self.btn_fem = QPushButton("Análisis 3D por elementos finitos")
        self.btn_fem.clicked.connect(self.fem_requested.emit)
        self.btn_rep = QPushButton("Informe del nudo (PDF)")
        self.btn_rep.clicked.connect(self.report_requested.emit)
        for b in (self.btn_chk, self.btn_fem, self.btn_rep):
            b.setMinimumHeight(30)
            lay.addWidget(b)
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        lay.addWidget(self.lbl_state)
        lay.addStretch(1)
        self.set_state("Sin verificar.", None)
        self.lbl.setText("Cada operación se verifica con las cargas de los miembros que toca: pernos (cortante, tracción, aplastamiento), placas (fluencia, rotura, "
                         "bloque de cortante, flexión) y soldaduras. Los resultados aparecen en la pestaña <b>Resultados</b>.")

    def set_state(self, text, ok):
        col = {True: "#006100", False: "#9c0006", None: "#595959"}[ok]
        self.lbl_state.setText(f"<span style='color:{col}'>{text}</span>")


# ====================================================================================================== contenedor
class NodeForm(Form):
    """Pestaña de un modulo de nudo: el flujo Miembros → Operaciones → Cargas → Análisis."""
    check_requested = Signal()
    fem_requested = Signal()
    report_requested = Signal()

    def __init__(self, mod, win=None):
        self._us = None
        super().__init__()
        self.mod, self.win = mod, win
        self.attr, self.mode = mod.ATTR, mod.MODE
        self.members_pg = MembersPage(mod)
        self.ops_pg = OperationsPage(mod)
        self.loads_pg = LoadsPage(mod)
        self.an_pg = AnalysisPage(mod)
        self.pages = [self.members_pg, self.ops_pg, self.loads_pg]
        self.steps = QTabWidget()
        self.steps.setDocumentMode(True)
        self.steps.setUsesScrollButtons(False)
        from .ui_widgets import scroll
        for title, pg in (("1  Miembros", self.members_pg), ("2  Operaciones", self.ops_pg), ("3  Cargas", self.loads_pg), ("4  Análisis", self.an_pg)):
            self.steps.addTab(scroll(pg) if isinstance(pg, Form) else pg, title)
        self.steps.setMinimumHeight(560)
        self.outer.addWidget(self.steps)
        for pg in self.pages:
            pg.changed.connect(self._on_page_changed)
        self.members_pg.renamed.connect(lambda *_: self._after_rename())
        self.members_pg.removed.connect(self.ops_pg.on_member_removed)
        self.members_pg.duplicated.connect(self.ops_pg.on_member_duplicated)
        self.an_pg.check_requested.connect(self.check_requested)
        self.an_pg.fem_requested.connect(self.fem_requested)
        self.an_pg.report_requested.connect(self.report_requested)
        self.steps.currentChanged.connect(self._step_changed)

    @property
    def us(self):
        return self._us

    @us.setter
    def us(self, v):
        self._us = v
        for pg in getattr(self, "pages", []):
            pg.us = v

    def _on_page_changed(self):
        self.changed.emit()

    def _after_rename(self):
        self.load(self._prj)

    def _step_changed(self, i):
        if hasattr(self, "_prj"):
            self.ops_pg.selected_member = self._current_member()
            self.load(self._prj)

    def _current_member(self):
        nd = getattr(self._prj, self.attr)
        i = self.members_pg._sel
        return nd.members[i].name if 0 <= i < len(nd.members) else ""

    def load(self, prj):
        self._prj = prj
        self.ops_pg.selected_member = self._current_member() if hasattr(self.members_pg, "_prj") else ""
        for pg in self.pages:
            pg.us = self.us
            pg.load(prj)

    def store(self, prj):
        self._prj = prj
        for pg in self.pages:
            pg.us = self.us
            pg.store(prj)

    def go_step(self, i):
        self.steps.setCurrentIndex(i)
