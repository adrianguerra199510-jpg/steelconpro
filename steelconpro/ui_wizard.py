# -*- coding: utf-8 -*-
"""Asistente «Nueva conexion»: 1. Clase  →  2. Geometria  →  3. Diseño, con miniaturas 3D (z-buffer propio, sin OpenGL).

La clase elige el modulo (nudo viga-columna, viga a viga, crucetas, placa base); la geometria, la configuracion inicial del nudo y el tipo de seccion
(I, HSS rectangular, HSS circular); el diseño, la conexion que se asigna a todos los miembros.  Despues todo se puede editar miembro por miembro.
Las miniaturas se dibujan de una en una desde un temporizador para no congelar la ventana.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QPushButton, QAbstractButton, QScrollArea, QWidget,
                               QDialogButtonBox, QSizePolicy)
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QImage
from PySide6.QtCore import Qt, QTimer, QSize, QRectF, Signal

from .conn import presets as PRE, assembly as AS
from .conn.specs import (CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS, MODE_OF, MODE_COL, MODE_BEAM, MODE_CHORD)

ORANGE = "#E85D0C"
CLASSES = [(CT_NODE, "Nudo viga-columna"), (CT_B2B, "Viga a viga"), (CT_TRUSS, "Crucetas (celosía y diagonales)"), (CT_BASEPLATE, "Placa base de columna")]
CLASS_SAMPLE = {CT_NODE: ("int2", "I", "tab"), CT_B2B: ("sec2", "I", "tab"), CT_TRUSS: ("V", "I", "gus_bolt")}


def pil_to_pixmap(im) -> QPixmap:
    im = im.convert("RGB")
    w, h = im.size
    qi = QImage(im.tobytes("raw", "RGB"), w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qi.copy())


def render_thumb(mdl, size, gray=False):
    from .conn.fem import scene as S
    sc = S.scene_model(mdl, loads=False, gray=gray, bolts=not gray)
    return S.render_scene_image(sc, 24.0, 50.0, size, ss=2, margin=0.04)


def baseplate_thumb(size):
    from . import gl3d
    from .model import Project
    from .conn.fem import scene as S
    return S.render_scene_image(gl3d.scene_geometry(Project(), loads=False), 24.0, 50.0, size, ss=2, margin=0.04)


class Tile(QAbstractButton):
    """Miniatura seleccionable con el marco naranja redondeado de la seleccion."""
    def __init__(self, size=(120, 92), tip="", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self._sz = QSize(*size)
        self.setFixedSize(self._sz.width() + 10, self._sz.height() + 10)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self._pm = None

    def set_pixmap(self, pm):
        self._pm = pm
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        p.setBrush(QColor("#ffffff"))
        if self.isChecked():
            p.setPen(QPen(QColor(ORANGE), 3.0))
        elif self.underMouse():
            p.setPen(QPen(QColor("#9aa4b0"), 1.5))
        else:
            p.setPen(QPen(QColor("#e3e7ec"), 1.0))
        p.drawRoundedRect(r, 9, 9)
        if self._pm is not None:
            pm = self._pm.scaled(self._sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - pm.width()) // 2, (self.height() - pm.height()) // 2, pm)
        else:
            p.setPen(QColor("#b0b7c0"))
            p.drawText(self.rect(), Qt.AlignCenter, "…")


def _hdr(text):
    lb = QLabel(f"<span style='color:{ORANGE}; font-size:13pt; font-weight:600'>{text}</span>")
    return lb


def _sub(text):
    return QLabel(f"<span style='color:#9aa4b0'>{text}</span>")


def _clear(layout):
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            _clear(it.layout())


class NewConnectionDialog(QDialog):
    """Elige (modulo, geometria, seccion, diseño); `choice()` lo devuelve."""

    def __init__(self, parent=None, current=CT_NODE):
        super().__init__(parent)
        self.setWindowTitle("Nueva conexión")
        self.resize(1340, 740)
        self.cls = current if current in dict(CLASSES) else CT_NODE
        self.geom, self.sec, self.design = None, "I", None
        self._cache = {}
        self._jobs = []                # [(tile, clave, fn)]
        self._gen = {"c2": 0, "c3": 0}
        root = QVBoxLayout(self)
        cols = QHBoxLayout()
        root.addLayout(cols, 1)

        self.c1 = QVBoxLayout()
        self.c2 = QVBoxLayout()
        self.c3 = QVBoxLayout()
        for lay, w in ((self.c1, 360), (self.c2, 600), (self.c3, 300)):
            box = QWidget()
            box.setLayout(lay)
            sa = QScrollArea()
            sa.setWidget(box)
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sa.setMinimumWidth(w)
            cols.addWidget(sa, 1)
            if lay is not self.c3:
                ln = QFrame()
                ln.setFrameShape(QFrame.VLine)
                ln.setStyleSheet("color:#c8cdd3")
                cols.addWidget(ln)
        self.lbl_sel = QLabel("")
        self.lbl_sel.setStyleSheet("color:#44546a")
        root.addWidget(self.lbl_sel)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Crear conexión")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.timer = QTimer(self)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self._tick)

        self._build_col1()
        self._pick_class(self.cls, first=True)

    # ------------------------------------------------------------------ resultado
    def choice(self) -> dict:
        return {"ctype": self.cls, "geom": self.geom, "sec": self.sec, "design": self.design}

    def _summary(self):
        names = dict(CLASSES)
        if self.cls == CT_BASEPLATE:
            self.lbl_sel.setText(f"Clase: {names[self.cls]}")
            return
        mode = MODE_OF[self.cls]
        gn = next((n for k, n, _f in PRE.GEOMS[mode] if k == self.geom), "")
        dn = ""
        for _g, items in PRE.DESIGNS[mode]:
            for k, n, _ck in items:
                if k == self.design:
                    dn = n
        sn = dict(PRE.SECTION_KEYS).get(self.sec, "")
        self.lbl_sel.setText(f"<b>Clase:</b> {names[self.cls]}   ·   <b>Geometría:</b> {gn} ({sn})   ·   <b>Diseño:</b> {dn}")

    # ------------------------------------------------------------------ cola de miniaturas
    def _enqueue(self, tile, key, fn, gen):
        if key in self._cache:
            tile.set_pixmap(self._cache[key])
            return
        self._jobs.append((tile, key, fn, gen))
        if not self.timer.isActive():
            self.timer.start()

    def _tick(self):
        while self._jobs:
            tile, key, fn, gen = self._jobs.pop(0)
            if gen is not None and gen[1] != self._gen[gen[0]]:
                continue
            try:
                pm = pil_to_pixmap(fn())
            except Exception:
                pm = QPixmap()
            self._cache[key] = pm
            try:
                tile.set_pixmap(pm)
            except RuntimeError:                       # la miniatura ya se destruyo (cambio de seleccion)
                pass
            return                                     # una por tick: la ventana sigue respondiendo
        self.timer.stop()

    def render_all(self):
        """Dibuja todas las miniaturas pendientes ahora (pruebas)."""
        while self._jobs:
            self._tick()

    # ------------------------------------------------------------------ columna 1: clase
    def _build_col1(self):
        self.c1.addWidget(_hdr("1.  Clase"))
        grid = QGridLayout()
        self.class_tiles = {}
        for i, (ct, nm) in enumerate(CLASSES):
            t = Tile((150, 112), nm)
            t.clicked.connect(lambda _c=False, c=ct: self._pick_class(c))
            self.class_tiles[ct] = t
            lab = QLabel(nm)
            lab.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            lab.setWordWrap(True)
            lab.setMaximumWidth(165)
            lab.setStyleSheet("color:#44546a; font-size:8.5pt")
            box = QVBoxLayout()
            box.addWidget(t, 0, Qt.AlignHCenter)
            box.addWidget(lab)
            grid.addLayout(box, i // 2, i % 2)
            if ct == CT_BASEPLATE:
                self._enqueue(t, ("cls", ct), lambda: baseplate_thumb((150, 112)), None)
            else:
                g, s, d = CLASS_SAMPLE[ct]
                mode = MODE_OF[ct]
                self._enqueue(t, ("cls", ct), lambda m=mode, g=g, s=s, d=d, nm=nm: render_thumb(AS.build_nodo(PRE.build(m, g, s, d), nm), (150, 112)), None)
        self.c1.addLayout(grid)
        self.c1.addStretch(1)

    def _pick_class(self, ct, first=False):
        self.cls = ct
        for k, t in self.class_tiles.items():
            t.setChecked(k == ct)
        self._build_col2()

    # ------------------------------------------------------------------ columna 2: geometria
    def _build_col2(self):
        self._gen["c2"] += 1
        _clear(self.c2)
        self.c2.addWidget(_hdr("2.  Geometría"))
        if self.cls == CT_BASEPLATE:
            self.geom, self.design = None, None
            note = QLabel("La placa base de columna se define en las pestañas de entrada: perfil, placa, pernos de anclaje, llave de corte, "
                          "rigidizadores, soldadura y concreto.")
            note.setWordWrap(True)
            note.setStyleSheet("color:#44546a")
            self.c2.addWidget(note)
            self.c2.addStretch(1)
            self._build_col3()
            self._summary()
            return
        mode = MODE_OF[self.cls]
        geoms = PRE.GEOMS[mode]
        if self.geom not in [k for k, _n, _f in geoms]:
            self.geom = geoms[0][0]
        self.geom_tiles = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        for r, (sk, sn) in enumerate(PRE.SECTION_KEYS):
            for c, (gk, gn, _f) in enumerate(geoms):
                t = Tile((100, 78), f"{gn} — {sn}")
                t.setChecked(gk == self.geom and sk == self.sec)
                t.clicked.connect(lambda _c=False, g=gk, s=sk: self._pick_geom(g, s))
                self.geom_tiles[(gk, sk)] = t
                grid.addWidget(t, r, c)
                key = ("geo", self.cls, gk, sk)
                self._enqueue(t, key, lambda m=mode, g=gk, s=sk, nm=gn: render_thumb(AS.build_nodo(PRE.build(m, g, s, "blank"), nm, hardware=False), (100, 78), gray=True),
                              ("c2", self._gen["c2"]))
        self.c2.addLayout(grid)
        self.c2.addStretch(1)
        if self.design is None or self.design not in [k for _g, it in PRE.DESIGNS[mode] for k, _n, _c in it]:
            self.design = {MODE_COL: "tab", MODE_BEAM: "tab", MODE_CHORD: "gus_bolt"}[mode]
        self._build_col3()
        self._summary()

    def _pick_geom(self, g, s):
        self.geom, self.sec = g, s
        for (gk, sk), t in self.geom_tiles.items():
            t.setChecked(gk == g and sk == s)
        self._build_col3()
        self._summary()

    # ------------------------------------------------------------------ columna 3: diseño
    def _build_col3(self):
        self._gen["c3"] += 1
        _clear(self.c3)
        self.c3.addWidget(_hdr("3.  Diseño"))
        if self.cls == CT_BASEPLATE:
            self.c3.addStretch(1)
            return
        mode = MODE_OF[self.cls]
        self.design_tiles = {}
        for gname, items in PRE.DESIGNS[mode]:
            self.c3.addWidget(_sub(gname))
            grid = QGridLayout()
            for i, (dk, dn, _ck) in enumerate(items):
                t = Tile((120, 92), dn)
                t.setChecked(dk == self.design)
                t.clicked.connect(lambda _c=False, d=dk: self._pick_design(d))
                self.design_tiles[dk] = t
                grid.addWidget(t, i // 2, i % 2)
                key = ("dis", self.cls, self.geom, self.sec, dk)
                self._enqueue(t, key, lambda m=mode, g=self.geom, s=self.sec, d=dk, nm=dn: render_thumb(AS.build_nodo(PRE.build(m, g, s, d), nm), (120, 92)),
                              ("c3", self._gen["c3"]))
            self.c3.addLayout(grid)
        self.c3.addStretch(1)

    def _pick_design(self, d):
        self.design = d
        for k, t in self.design_tiles.items():
            t.setChecked(k == d)
        self._summary()
