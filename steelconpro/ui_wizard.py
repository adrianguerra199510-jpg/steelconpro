# -*- coding: utf-8 -*-
"""Asistente «Nueva conexion» y guardado de plantillas.

No hay plantillas predefinidas: se elige el modulo (conexion de nudo o placa base) y se parte de una conexion en blanco o de una
plantilla propia (una conexion terminada que se guardo antes con «Guardar como plantilla»).  `NewConnectionDialog.choice()` devuelve el modulo y la
ruta de la plantilla (None = en blanco).  `SaveTemplateDialog` pide el nombre y la descripcion de una plantilla nueva.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QDialogButtonBox, QLineEdit,
                               QPlainTextEdit, QCheckBox, QFormLayout, QMessageBox, QInputDialog, QSizePolicy)
from PySide6.QtGui import QColor, QPixmap, QImage
from PySide6.QtCore import Qt

from . import templates as TPL
from .conn.specs import CT_BASEPLATE, CT_NODE

CLASSES = [(CT_NODE, "Conexión de nudo"), (CT_BASEPLATE, "Placa base de columna")]
BLANK_TEXT = {CT_NODE: "Un miembro principal solo: agregue después los demás miembros, designe cuál es el principal, y defina las operaciones y las cargas.",
              CT_BASEPLATE: "Una placa base con los valores iniciales del programa."}


def pil_to_pixmap(im) -> QPixmap:
    im = im.convert("RGB")
    w, h = im.size
    qi = QImage(im.tobytes("raw", "RGB"), w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qi.copy())


def render_project(prj, size):
    """Imagen (z-buffer propio, sin OpenGL) del modelo 3D de una conexion para la vista previa."""
    from .conn.specs import CT_BASEPLATE as BP
    from .conn.fem import scene as S
    if prj.ctype == BP:
        from . import gl3d
        sc = gl3d.scene_geometry(prj, loads=False)
    else:
        from .conn import assembly as AS
        sc = S.scene_model(AS.build_model(prj), loads=False, tags=True)
    return S.render_scene_image(sc, 24.0, 50.0, size, ss=2, margin=0.04)


class NewConnectionDialog(QDialog):
    """Elige el modulo y si se parte de cero o de una plantilla propia; `choice()` lo devuelve."""

    def __init__(self, parent=None, current=CT_NODE, where=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva conexión")
        self.resize(1040, 600)
        self.where = where
        self.cls = current if current in dict(CLASSES) else CT_NODE
        root = QVBoxLayout(self)
        cols = QHBoxLayout()
        root.addLayout(cols, 1)

        left = QVBoxLayout()
        left.addWidget(QLabel("<b>1. Módulo</b>"))
        self.lst_cls = QListWidget()
        self.lst_cls.setMaximumWidth(280)
        for ct, nm in CLASSES:
            it = QListWidgetItem(nm)
            it.setData(Qt.UserRole, ct)
            self.lst_cls.addItem(it)
        left.addWidget(self.lst_cls, 1)
        cols.addLayout(left)

        mid = QVBoxLayout()
        mid.addWidget(QLabel("<b>2. Punto de partida</b>"))
        self.lst_tpl = QListWidget()
        self.lst_tpl.setMinimumWidth(330)
        self.lst_tpl.setWordWrap(True)
        mid.addWidget(self.lst_tpl, 1)
        row = QHBoxLayout()
        self.bt_ren = QPushButton("Renombrar plantilla")
        self.bt_del = QPushButton("Eliminar plantilla")
        self.bt_ren.clicked.connect(self._rename)
        self.bt_del.clicked.connect(self._delete)
        row.addWidget(self.bt_ren)
        row.addWidget(self.bt_del)
        mid.addLayout(row)
        cols.addLayout(mid)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Vista previa</b>"))
        self.lbl_img = QLabel("")
        self.lbl_img.setMinimumSize(380, 280)
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setStyleSheet("background:#ffffff; border:1px solid #cdd4dd; border-radius:6px; color:#4d5866;")
        self.lbl_img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right.addWidget(self.lbl_img, 1)
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        right.addWidget(self.lbl_info)
        cols.addLayout(right, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Crear conexión")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.lst_cls.currentItemChanged.connect(lambda *_: self._pick_class(self.lst_cls.currentItem().data(Qt.UserRole)) if self.lst_cls.currentItem() else None)
        self.lst_tpl.currentItemChanged.connect(lambda *_: self._preview())
        self.lst_tpl.itemDoubleClicked.connect(lambda *_: self.accept())
        self._pick_class(self.cls)

    # ------------------------------------------------------------------ lista
    def _pick_class(self, ct):
        self.cls = ct
        self.lst_cls.blockSignals(True)
        self.lst_cls.setCurrentRow([c for c, _n in CLASSES].index(ct))
        self.lst_cls.blockSignals(False)
        self.lst_tpl.blockSignals(True)
        self.lst_tpl.clear()
        it = QListWidgetItem("▸  Conexión en blanco (desde cero)")
        it.setData(Qt.UserRole, None)
        f = it.font()
        f.setBold(True)
        it.setFont(f)
        self.lst_tpl.addItem(it)
        for t in TPL.list_templates(ct, self.where):
            w = QListWidgetItem(f"{t['name']}" + (f"\n    {t['desc']}" if t["desc"] else ""))
            w.setData(Qt.UserRole, t["file"])
            w.setToolTip(f"{t['name']} — guardada el {t['date']}" + (f"\n{t['desc']}" if t["desc"] else ""))
            self.lst_tpl.addItem(w)
        if self.lst_tpl.count() == 1:
            h = QListWidgetItem("(Aún no hay plantillas propias: termine una conexión y use «Guardar como plantilla».)")
            h.setFlags(Qt.NoItemFlags)
            self.lst_tpl.addItem(h)
        self.lst_tpl.setCurrentRow(0)
        self.lst_tpl.blockSignals(False)
        self._preview()

    def _preview(self):
        path = self.choice()["template"]
        self.bt_ren.setEnabled(path is not None)
        self.bt_del.setEnabled(path is not None)
        try:
            if path is None:
                from .model import Project
                p = Project()
                p.ctype = self.cls
                self.lbl_info.setText(BLANK_TEXT[self.cls])
            else:
                p = TPL.load_template(path)
                t = next((x for x in TPL.list_templates(self.cls, self.where) if x["file"] == path), None)
                self.lbl_info.setText((f"<b>{t['name']}</b> — guardada el {t['date']}<br>" + (t["desc"] if t["desc"] else "")) if t else "")
            self.lbl_img.setPixmap(pil_to_pixmap(render_project(p, (420, 300))))
        except Exception as e:
            self.lbl_img.setPixmap(QPixmap())
            self.lbl_img.setText(f"Sin vista previa ({type(e).__name__}: {str(e)[:80]})")

    # ------------------------------------------------------------------ gestion de plantillas
    def _selected(self):
        it = self.lst_tpl.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _rename(self):
        path = self._selected()
        if path is None:
            return
        cur = next((t["name"] for t in TPL.list_templates(self.cls, self.where) if t["file"] == path), "")
        name, ok = QInputDialog.getText(self, "Renombrar plantilla", "Nombre:", text=cur)
        if ok and name.strip():
            try:
                TPL.rename_template(path, name)
            except ValueError as e:
                QMessageBox.warning(self, "Plantilla", str(e))
                return
            self._pick_class(self.cls)

    def _delete(self):
        path = self._selected()
        if path is None:
            return
        if QMessageBox.question(self, "Plantilla", "¿Eliminar esta plantilla? No se puede deshacer.") == QMessageBox.Yes:
            TPL.delete_template(path)
            self._pick_class(self.cls)

    def choice(self) -> dict:
        return {"ctype": self.cls, "template": self._selected()}


class SaveTemplateDialog(QDialog):
    """Nombre y descripcion de una plantilla nueva a partir de la conexion actual."""

    def __init__(self, parent, prj, where=None):
        super().__init__(parent)
        from .conn.specs import ATTR_OF
        self.setWindowTitle("Guardar como plantilla")
        self.resize(460, 300)
        self.prj, self.where = prj, where
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Se guarda la conexión <b>{prj.element or prj.ctype}</b> ({prj.ctype}) para crear conexiones nuevas a partir de ella."))
        fl = QFormLayout()
        self.ed_name = QLineEdit(f"{prj.element}" if prj.element else "")
        self.ed_desc = QPlainTextEdit()
        self.ed_desc.setPlaceholderText("Descripción opcional: para qué sirve, supuestos...")
        self.ed_desc.setFixedHeight(90)
        fl.addRow("Nombre", self.ed_name)
        fl.addRow("Descripción", self.ed_desc)
        lay.addLayout(fl)
        self.chk_loads = QCheckBox("Incluir las cargas")
        self.chk_loads.setChecked(True)
        self.chk_loads.setVisible(prj.ctype in ATTR_OF)
        lay.addWidget(self.chk_loads)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.path = ""

    def _ok(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Plantilla", "Escriba un nombre.")
            return
        if TPL.find(name, self.prj.ctype, self.where) is not None:
            if QMessageBox.question(self, "Plantilla", f"Ya existe la plantilla «{name}» de este módulo. ¿Reemplazarla?") != QMessageBox.Yes:
                return
        try:
            self.path = TPL.save_template(self.prj, name, self.ed_desc.toPlainText(), self.chk_loads.isChecked(), self.where)
        except Exception as e:
            QMessageBox.warning(self, "Plantilla", str(e))
            return
        self.accept()
