# -*- coding: utf-8 -*-
"""Ventana principal de PlacaBasePro (PySide6)."""
from __future__ import annotations
import math
import os
import sys
import datetime
import tempfile
import traceback
from pathlib import Path

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject, QEvent
from PySide6.QtGui import QAction, QKeySequence, QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QMainWindow, QWidget, QTabWidget, QSplitter,
                               QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
                               QComboBox, QPushButton, QTextEdit, QToolBar, QCheckBox,
                               QStatusBar, QDoubleSpinBox, QProgressDialog, QSizePolicy)

from . import __version__
from .model import (INSTALL_TYPES, ADH_ENV, ADH_CATEGORY)
from .model import (Project, PATTERNS, ANCHOR_TYPES, WELD_TYPES, PLATE_SHAPES,
                    LUG_DIRS, STIFF_POSITIONS, STIFF_SHAPES, STIFF_SPACING, WELD_CRITERIA, U_TYPES)
from . import materials as M
from .shapes import CATALOG, W_SHAPE, HSS_RECT, HSS_ROUND, PIPE, KIND_LABELS
from .model import LUG_TYPES, save_book, load_book, MESH3D_MODES, WELD_MODELS, FIXITY, LoadCombo, REBAR
from .dialogs import SectionDialog, MaterialsDialog
from PySide6.QtWidgets import QListWidget, QInputDialog
from .solver import solve
from .units import parse_xy_clipboard
from . import draw, report, mesh3d, view3d, brand
from .rep3d import make_fem
from .ui_widgets import Form, scroll, PasteTable, ThemeSwitch
from . import gl3d
from .units import (UnitSet, LEN_UNITS, FORCE_UNITS, STRESS_UNITS, MOMENT_UNITS,
                    DEFAULT_SETS, KIP_TO_KN, IN_TO_MM, KIPIN_TO_KNM)

KIND_NAMES = {W_SHAPE: "W (ala ancha)", HSS_RECT: "HSS cuadrado/rectangular",
              HSS_ROUND: "HSS circular", PIPE: "Pipe (tuberia)"}
KIND_BY_NAME = {v: k for k, v in KIND_NAMES.items()}


FAMILY_DESC = {"W": "W — ala ancha", "M": "M — perfil I liviano", "S": "S — I americano",
               "HP": "HP — pilote", "C": "C — canal", "MC": "MC — canal miscelaneo",
               "L": "L — angulo", "WT": "WT — te de W", "MT": "MT — te de M",
               "ST": "ST — te de S", "HSS": "HSS — rectangular / cuadrado",
               "HSS circular": "HSS — circular", "Pipe": "Pipe — tuberia",
               "Personalizado": "Secciones personalizadas", "Importado": "Importados"}
FAMILY_STEEL = {"W": "ASTM A992", "M": "ASTM A36", "S": "ASTM A36", "HP": "ASTM A572 Gr.50",
                "C": "ASTM A36", "MC": "ASTM A36", "L": "ASTM A36", "WT": "ASTM A992",
                "MT": "ASTM A36", "ST": "ASTM A36", "HSS": "ASTM A500 Gr.B (HSS rect.)",
                "HSS circular": "ASTM A500 Gr.B (HSS red.)", "Pipe": "ASTM A53 Gr.B (Pipe)"}


def fam_label(f):
    return FAMILY_DESC.get(f, f)


def fam_from_label(t):
    for k, v in FAMILY_DESC.items():
        if v == t:
            return k
    return t


def _wheel_zoom(canvas, ax_getter, three_d=False):
    """Zoom con la rueda del mouse (centrado en el cursor en 2D)."""
    def on_scroll(ev):
        ax = ax_getter()
        if ax is None:
            return
        k = 0.85 if ev.button == "up" else 1 / 0.85
        if three_d:
            for get, set_ in ((ax.get_xlim3d, ax.set_xlim3d), (ax.get_ylim3d, ax.set_ylim3d),
                              (ax.get_zlim3d, ax.set_zlim3d)):
                a, b = get()
                c = (a + b) / 2
                set_(c - (b - a) / 2 * k, c + (b - a) / 2 * k)
        else:
            if ev.inaxes is not ax or ev.xdata is None:
                return
            for get, set_, c in ((ax.get_xlim, ax.set_xlim, ev.xdata),
                                 (ax.get_ylim, ax.set_ylim, ev.ydata)):
                a, b = get()
                set_(c - (c - a) * k, c + (b - c) * k)
        canvas.draw_idle()
    canvas.mpl_connect("scroll_event", on_scroll)


class Canvas(QWidget):
    def __init__(self, parent=None, size=(6, 6)):
        super().__init__(parent)
        self.fig = Figure(figsize=size, dpi=100, tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        self.cv = FigureCanvasQTAgg(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.nav = NavigationToolbar2QT(self.cv, self)
        lay.addWidget(self.nav)
        lay.addWidget(self.cv)
        self.cbar = None
        _wheel_zoom(self.cv, lambda: self.ax)

    def reset(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.cbar = None


class Canvas3D(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(figsize=(7, 6), dpi=100)
        self.ax = self.fig.add_axes([0.0, 0.0, 0.88, 0.95], projection="3d")
        self.cv = FigureCanvasQTAgg(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(self.cv, self))
        lay.addWidget(self.cv)
        self.cbar = None
        _wheel_zoom(self.cv, lambda: self.ax, three_d=True)
        self.cv.mpl_connect("motion_notify_event", self._on_rotate)
        self.cv.mpl_connect("resize_event", self._on_resize)
        self.cv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _on_resize(self, ev):
        # el modelo se re-ajusta al ancho/alto disponibles
        from . import view3d as _v
        if getattr(self.ax, "_pb_aspect", None) is not None:
            _v.fit_to_axes(self.ax)
            self.cv.draw_idle()

    def _on_rotate(self, ev):
        # al girar la camara, reordena el dibujo (arriba/abajo de la placa)
        if ev.button is not None and getattr(self.ax, "_pb_groups", None):
            from . import view3d as _v
            _v.update_order(self.ax)

    def reset(self, cbar=True):
        self.fig.clf()
        # el eje ocupa todo el lienzo (menos la franja de la barra de colores si la hay),
        # asi el modelo queda centrado
        self.ax = self.fig.add_axes([0.0, 0.0, 0.88 if cbar else 1.0, 0.95], projection="3d")
        self.cbar = None


class Worker3D(QThread):
    """Corre el ciclo geometria -> Gmsh -> CalculiX de cada combinacion de carga en segundo plano para que
    la ventana siga respondiendo.  `jobs`: lista de (indice, nombre, proyecto, firma)."""
    progress = Signal(str)
    done = Signal(object, str)

    def __init__(self, jobs, folder):
        super().__init__()
        self.jobs, self.folder = jobs, folder
        self.token = mesh3d.CancelToken()

    def cancel(self):
        """Mata el proceso en curso (Gmsh o CalculiX) y termina el analisis."""
        self.token.cancel()

    def run(self):
        out = []
        n = len(self.jobs)
        for k, (idx, name, q, sig) in enumerate(self.jobs):
            pre = f"Combinacion {k + 1} de {n}: {name}\n" if n > 1 else ""
            try:
                res, msg = mesh3d.full_3d(q, str(Path(self.folder) / f"comb{idx + 1}"), "modelo3d",
                                          progress=lambda m, p=pre: self.progress.emit(p + m),
                                          cancel=self.token)
            except Exception as e:
                res, msg = None, f"{type(e).__name__}: {e}"
            out.append((idx, name, q, sig, res, msg))
            if res is None:
                break
        self.done.emit(out, "")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.prj = Project()
        self.prj.date = datetime.date.today().isoformat()
        self.book = [self.prj]
        self.cur = 0
        self.fem_cache = {}          # (id(conexion), combinacion) -> Fem3D (con la firma del proyecto que lo genero)
        self.raw_cache = {}          # (id(conexion), combinacion) -> (firma, resultado crudo del 3D para dibujar)
        self.pairs = []              # [(proyecto de la combinacion, Results)] de la conexion actual
        self.res = None
        self.worker = None
        self.path = None
        self._loading = False
        self.us = UnitSet(self.prj.u_len, self.prj.u_force,
                          self.prj.u_stress, self.prj.u_moment)

        self.setWindowTitle(f"PlacaBasePro {__version__} — Diseno de placas base")
        self.setWindowIcon(QIcon(brand.ICO()))
        self.resize(1500, 920)

        self._build_actions()
        self._build_forms()
        self._build_views()

        left = QSplitter(Qt.Vertical)
        cw = QWidget(); cl = QVBoxLayout(cw); cl.setContentsMargins(4, 4, 4, 0)
        lg = QLabel()
        self.lg = lg
        lg.setPixmap(brand.logo_pixmap(_theme_dark(), 250))
        lg.setAlignment(Qt.AlignCenter)
        lg.setToolTip(f"PlacaBasePro {__version__}")
        cl.addWidget(lg)
        cl.addWidget(QLabel("<b>Conexiones del proyecto</b>"))
        self.lst_con = QListWidget()
        self.lst_con.setMaximumHeight(140)
        self.lst_con.currentRowChanged.connect(self.on_select_connection)
        cl.addWidget(self.lst_con)
        hb = QHBoxLayout()
        for txt, fn in (("Nueva", self.con_new), ("Duplicar", self.con_dup),
                        ("Renombrar", self.con_rename), ("Eliminar", self.con_del)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hb.addWidget(bt)
        cl.addLayout(hb)
        left.addWidget(cw)
        tw = QWidget(); tl = QVBoxLayout(tw); tl.setContentsMargins(4, 2, 4, 0); tl.setSpacing(4)
        tl.addWidget(self.btn3d)
        tl.addWidget(self.tabs_in)
        left.addWidget(tw)
        left.setSizes([190, 800])
        spl = QSplitter(Qt.Horizontal)
        spl.addWidget(left)
        spl.addWidget(self.tabs_out)
        spl.setSizes([470, 1030])
        self.setCentralWidget(spl)
        self.setStatusBar(QStatusBar())

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.recalc)

        self.load_ui()
        self._refresh_list()
        self.recalc()
        self._dark = _theme_dark()
        if self._dark:
            brand.retheme(self, True)
            self.recalc()
        self._ready = True

    # =============================================================== acciones
    def _build_actions(self):
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)
        mb = self.menuBar()
        m_file = mb.addMenu("&Archivo")
        m_calc = mb.addMenu("&Calculo")
        m_exp = mb.addMenu("&Exportar")
        m_mat = mb.addMenu("&Materiales")
        m_help = mb.addMenu("A&yuda")
        self.sw_theme = ThemeSwitch(_theme_dark())
        self.sw_theme.toggled.connect(self._set_dark)
        self._corner = cw_ = QWidget(); cl_ = QHBoxLayout(cw_); cl_.setContentsMargins(0, 2, 8, 2); cl_.addWidget(self.sw_theme)
        mb.setCornerWidget(cw_, Qt.TopRightCorner)

        def act(menu, text, slot, key=None, toolbar=False):
            a = QAction(text, self)
            if key:
                a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            menu.addAction(a)
            if toolbar:
                tb.addAction(a)
            return a

        act(m_file, "Nuevo", self.new, "Ctrl+N", True)
        act(m_file, "Abrir...", self.open, "Ctrl+O", True)
        act(m_file, "Guardar", self.save, "Ctrl+S", True)
        act(m_file, "Guardar como...", self.save_as, "Ctrl+Shift+S")
        m_file.addSeparator()
        act(m_file, "Importar base de datos AISC v14.1...", self.import_aisc)
        m_file.addSeparator()
        act(m_file, "Salir", self.close, "Ctrl+Q")
        tb.addSeparator()
        act(m_calc, "Recalcular ahora", self.recalc, "F5")
        m_calc.addSeparator()
        act(m_calc, "CALCULAR (analisis 3D de todas las combinaciones)...", self.run_3d, "F8")
        tb.addSeparator()
        act(m_exp, "Memoria de calculo PDF (.pdf)...", self.export_pdf)
        act(m_exp, "Memoria de calculo Word (.docx)...", self.export_docx)
        act(m_exp, "Imagenes (.png)...", self.export_png)
        m_exp.addSeparator()
        act(m_exp, "Modelo solido 3D para Gmsh (.geo)...", self.export_3d)
        act(m_help, "Acerca de", self.about)
        act(m_mat, "Biblioteca de materiales...", self.materials_dialog)
        m_exp.addSeparator()
        act(m_exp, "Reportes PDF de TODAS las conexiones...", lambda: self.export_all("pdf"))
        act(m_exp, "Reportes Word de TODAS las conexiones...", lambda: self.export_all("docx"))

        self.btn3d = QPushButton("CALCULAR  (F8)")
        self.btn3d.setStyleSheet(f"QPushButton{{background:{brand.ORANGE};color:white;font-weight:bold;"
                                 f"padding:7px 14px;border-radius:4px;font-size:10pt;}}"
                                 f"QPushButton:hover{{background:{brand.ORANGE_DK};}}"
                                 f"QPushButton:disabled{{background:#e9b999;}}")
        self.btn3d.setToolTip("Corre el analisis 3D (Gmsh + CalculiX) de todas las combinaciones de carga y "
                              "entrega el veredicto. Mientras no se calcule no se muestra ningun resultado.")
        self.btn3d.clicked.connect(self.run_3d)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)                     # empuja el D/C a la esquina superior derecha
        self.lbl_verdict = QLabel("  ")
        f = QFont(); f.setBold(True); f.setPointSize(11)
        self.lbl_verdict.setFont(f)
        tb.addWidget(self.lbl_verdict)

    # ============================================================= formularios
    def _build_forms(self):
        self.tabs_in = QTabWidget()
        self.forms = []

        self.fnamed = {}

        def new_form(title):
            f = Form()
            f.changed.connect(self.on_change)
            self.forms.append(f)
            self.fnamed[title] = f
            self.tabs_in.addTab(scroll(f), title)
            return f

        # ---- proyecto
        f = new_form("Proyecto")
        f.group("Identificacion")
        f.text("Proyecto", "name")
        f.text("Elemento", "element")
        f.text("Calculo", "author")
        f.text("Fecha", "date")
        f.group("Unidades de trabajo")
        self.cb_preset = QComboBox()
        self.cb_preset.addItem("(personalizado)")
        self.cb_preset.addItems(list(DEFAULT_SETS.keys()))
        self.cb_preset.currentTextChanged.connect(self.on_preset)
        f._lay.addRow("Sistema", self.cb_preset)
        f.combo("Longitud", "u_len", list(LEN_UNITS.keys()))
        f.combo("Fuerza", "u_force", list(FORCE_UNITS.keys()))
        f.combo("Momento", "u_moment", list(MOMENT_UNITS.keys()))
        f.combo("Esfuerzo", "u_stress", list(STRESS_UNITS.keys()))
        f.note("Se aplican a TODA la aplicacion: entradas, tabla de resultados y "
               "reportes.  El calculo interno siempre se hace en in-kip-ksi, que son "
               "las unidades nativas de AISC v14 y de los pernos en pulgadas.")
        f.finish()

        # ---- cargas (combinaciones)
        f = new_form("Cargas")
        f.group("Combinaciones de carga factorizadas (LRFD)")
        self.tbl_cb = QTableWidget(0, 6)
        self.tbl_cb.setMinimumHeight(190)
        self.tbl_cb.verticalHeader().setDefaultSectionSize(24)
        hh = self.tbl_cb.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.Interactive)
        self.tbl_cb.setColumnWidth(0, 110)
        self.tbl_cb.itemChanged.connect(lambda *_: self._combo_changed())
        self.tbl_cb.itemSelectionChanged.connect(self._combo_row_selected)
        f._lay.addRow(self.tbl_cb)
        rowc = QWidget(); hc = QHBoxLayout(rowc); hc.setContentsMargins(0, 0, 0, 0)
        for txt, fn in (("Agregar", self._combo_add), ("Duplicar", self._combo_dup),
                        ("Quitar", self._combo_del)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hc.addWidget(bt)
        f._lay.addRow(rowc)
        f.note("Cada fila es una combinacion (por ejemplo 1.2D+1.6L, 1.2D+1.0E, 0.9D+1.0W). El boton CALCULAR "
               "corre el analisis 3D de TODAS las combinaciones y el veredicto es el de la mas desfavorable; "
               "el combo 'Combinacion' de la barra superior elige cual se dibuja y se detalla.")
        f.note("CONVENCION DE SIGNOS — Pu positivo en compresion (negativo = traccion o levantamiento).  Mux "
               "positivo tracciona el lado +Y, que es el borde superior del dibujo en planta; si su momento "
               "tracciona el lado opuesto, cambie el signo o gire la placa 180°.  Vux y Vuy son las componentes "
               "del cortante en los ejes de la placa.  Todos son valores YA FACTORIZADOS (LRFD).  Muy entra en el "
               "perfil, la soldadura y el 3D; el equilibrio cerrado de DG1 es uniaxial (usa Mux).")
        f.note("La INCLINACION DE LA COLUMNA se define en la pestaña Perfil. Si esta inclinada, estas cargas se "
               "ingresan en los ejes de la columna.")
        f.group("Friccion")
        f.check("Descontar friccion placa-mortero del cortante en pernos", "loads.friction", help="Permite restar el producto del coeficiente de friccion por Pu del cortante que llega a los anclajes. Uselo solo si puede garantizar la compresion permanente y el estado de la interfaz.")
        f.num("Coeficiente μ", "loads.mu_fric", 0.2, 0.9, 0.05, 2, help="Coeficiente de friccion entre la placa y el mortero. Valores habituales de 0.40 a 0.55.")
        self.lbl_si = QLabel("")
        self.lbl_si.setStyleSheet("color:#595959; font-size:8pt;")
        f._lay.addRow("Combinacion activa", self.lbl_si)
        f.finish()

        # ---- perfil
        f = new_form("Perfil")
        f.group("Catalogo AISC (1,660 perfiles) y secciones propias")
        self.cb_kind = QComboBox()
        self.cb_kind.currentTextChanged.connect(self.on_kind)
        f._lay.addRow("Familia", self.cb_kind)
        self.cb_shape = f.combo("Perfil", "section.label", [], help="Perfiles de la AISC Shapes Database: W, M, S, HP, C, MC, L, WT, MT, ST, HSS y tuberias. Las secciones creadas con 'Nueva seccion' aparecen en la familia 'Secciones personalizadas'.")
        rowb = QWidget(); hb = QHBoxLayout(rowb); hb.setContentsMargins(0, 0, 0, 0)
        for txt, fn in (("Nueva seccion...", self.new_section),
                        ("Editar", self.edit_section), ("Eliminar", self.del_section)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hb.addWidget(bt)
        f._lay.addRow("", rowb)
        self.lbl_shape = QLabel("")
        self.lbl_shape.setStyleSheet("color:#1f3864; font-size:8pt;")
        f._lay.addRow("", self.lbl_shape)
        f.combo("Acero", "section.steel", [s.name for s in M.SHAPE_STEELS], help="Grado del acero del perfil. Define Fy y Fu para la verificacion del propio perfil y del metal base de la soldadura.")
        f.group("Seccion doble")
        f.check("Doble, espalda con espalda", "section.double", help="Dos piezas iguales espalda con espalda (por ejemplo 2L o 2C), simetricas respecto al eje Y. Se calculan A, Ix, Sx y Zx dobles, e Iy, Sy y Zy con la separacion real. La soldadura se verifica como grupo en todo el contorno. No aplica a secciones redondas.")
        f.num("Separacion entre piezas", "section.gap", 0, 12, uk="L", help="Distancia libre entre las espaldas de las dos piezas (espesor de la cartela o del separador). En dobles angulos AISC tabula 0, 3/8 y 3/4 in.")
        f.group("Orientacion respecto a la placa")
        f.num("Rotacion", "section.rotation", -180, 180, 15.0, 1, "°", help="Giro del perfil respecto a la placa. 0° = eje fuerte paralelo a N, de modo que Mux flexiona el perfil en su eje fuerte. 90° = eje debil. Con angulos intermedios las formulas cerradas de DG1 usan el rectangulo envolvente; el modelo 3D usa la geometria real.")
        f.num("Desplazamiento de la columna en X", "section.cx", -1000, 1000, uk="L", help="Posicion del centro de la columna respecto al centro de la placa, en la direccion X (positivo hacia +X). Los pernos y la placa no se mueven. Las cargas se ingresan en el eje de la columna: el programa las traslada al centro de la placa (Mux' = Mux − Pu·cy, Muy' = Muy + Pu·cx) y el modelo 3D las aplica en el eje real de la columna. Los voladizos de la placa se toman del lado mas largo.")
        f.num("Desplazamiento de la columna en Y", "section.cy", -1000, 1000, uk="L", help="Posicion del centro de la columna respecto al centro de la placa, en la direccion Y (positivo hacia +Y, el lado traccionado con Mux > 0). 0 = columna centrada.")
        f.note("0° = eje fuerte paralelo a N (Y).  90° = eje debil paralelo a N.  "
               "Con angulos distintos de 0/90 las formulas de DG1 usan el rectangulo "
               "envolvente; el modelo 3D usa la geometria real.")
        f.group("Inclinacion de la columna (respecto a la normal de la placa)")
        f.num("Giro alrededor de X", "loads.tilt_x", -85, 85, 1.0, 2, "°", help="Inclinacion de la columna respecto a la normal de la placa, girando alrededor del eje X (la columna se inclina hacia +Y/-Y). 0° = perpendicular. Con inclinacion, Pu, Vux, Vuy, Mux y Muy se ingresan en los ejes de la COLUMNA (Pu = axial, V = transversal) y el programa los proyecta a los ejes de la placa para todas las verificaciones.")
        f.num("Giro alrededor de Y", "loads.tilt_y", -85, 85, 1.0, 2, "°", help="Inclinacion de la columna respecto a la normal de la placa, girando alrededor del eje Y (la columna se inclina hacia +X/-X). 0° = perpendicular. Puede combinarse con el giro alrededor de X.")
        self.lbl_tilt = QLabel("")
        self.lbl_tilt.setStyleSheet("color:#595959; font-size:8pt;")
        f._lay.addRow("En ejes de la placa", self.lbl_tilt)
        f.finish()

        # ---- placa
        f = new_form("Placa")
        f.group("Geometria")
        f.combo("Forma", "plate.shape", PLATE_SHAPES, help="Rectangular o circular. En placa circular las formulas cerradas usan el cuadrado equivalente de igual area (Leq = 0.8862·Dp); el modelo 3D modela el circulo real.")
        f.num("N (largo, dir. Y)", "plate.N", 1, 200, uk="L", help="Dimension de la placa en la direccion Y, que es la direccion en que actua el momento Mux. Es el lado que gobierna el equilibrio de aplastamiento.")
        f.num("B (ancho, dir. X)", "plate.B", 1, 200, uk="L", help="Dimension de la placa en la direccion X, perpendicular a Mux. Es el ancho sobre el que se reparte la presion de contacto.")
        f.num("Dp (si es circular)", "plate.Dp", 1, 200, uk="L", help="Diametro de la placa. Solo se usa cuando la forma es Circular.")
        f.num("tp (espesor)", "plate.tp", 0.25, 12, uk="L", help="Espesor propuesto de la placa. El programa calcula el espesor requerido por las lineas de fluencia y lo compara contra este valor.")
        f.num("Mortero de nivelacion", "plate.grout", 0, 6, uk="L", help="Espesor del mortero de nivelacion bajo la placa. Reduce la altura embebida util de la llave de corte y, si no hay llave, aplica el factor 0.80 al cortante del anclaje (ACI 17.7.1.2.1).")
        f.group("Material")
        f.combo("Acero de placa", "plate.steel", [s.name for s in M.PLATE_STEELS], help="Grado del acero de la placa base. Su Fy gobierna el espesor requerido.")
        f.finish()

        # ---- pernos
        f = new_form("Pernos")
        f.group("Varilla de anclaje")
        f.combo("Diametro", "bolts.size", M.BOLT_SIZES, help="Diametro nominal del anclaje en pulgadas. De el se derivan Ab, el area de esfuerzo Ase de rosca UNC, el diametro de agujero en la placa segun AISC Tabla 14-2 y el area de apoyo de la tuerca hexagonal pesada.")
        self.lbl_bolt = QLabel("")
        self.lbl_bolt.setStyleSheet("color:#1f3864; font-size:8pt;")
        f._lay.addRow("", self.lbl_bolt)
        f.combo("Material", "bolts.steel", [s.name for s in M.ANCHOR_STEELS], help="Grado de la varilla de anclaje. Ademas de Fy y Fu define si el elemento es ductil, lo que decide el factor de reduccion de ACI Tabla 17.5.3.")
        f.combo("Tipo de anclaje", "bolts.atype", ANCHOR_TYPES, help="Con cabeza: la extraccion se calcula con 8·Abrg·f'c. Gancho L o J: con 0.9·f'c·eh·da. Recto: ACI no le reconoce resistencia a la extraccion y el programa lo marca como no valido si hay traccion.")
        f.combo("Instalacion (varilla recta)", "bolts.install", INSTALL_TYPES,
                help="Solo se usa con varilla recta. Preinstalada (vaciada en sitio): ACI no "
                     "le reconoce resistencia a la extraccion y no es valida a traccion. "
                     "Postinstalada con adhesivo (epoxico): se diseña por adherencia segun "
                     "ACI 318-19 17.6.5, con kc = 17 en el arrancamiento y el factor φ de la "
                     "categoria del producto.")
        f.num("hef (embebido efectivo)", "bolts.hef", 2, 120, uk="L", help="Profundidad efectiva de embebido, desde la superficie del concreto hasta el plano de apoyo de la cabeza o del gancho. Es el parametro que mas pesa en el arrancamiento del concreto.")
        f.num("eh gancho (0 = 3·db)", "bolts.eh", 0, 20, uk="L", help="Longitud del gancho medida desde el eje de la varilla. ACI la limita a 3·db <= eh <= 4.5·db. Deje 0 para que el programa use 3·db.")
        f.combo("Criterio del agujero", "bolts.hole_rule", M.HOLE_RULES,
                help="La Tabla 14-2 del Manual AISC (= Tabla 2.3 de la DG1) da los "
                     "diametros MAXIMOS recomendados: son muy holgados a proposito "
                     "para absorber la tolerancia de colocacion de los anclajes en el "
                     "concreto, y obligan a cubrirlos con arandela de placa. Ejemplo: "
                     "Ø5/8 in lleva agujero de 1-3/16 in = 30.2 mm. Si el grupo se "
                     "coloca con plantilla se justifica uno menor: la regla F844 (nota "
                     "al pie de la tabla) da db+5/16 hasta 1 in, y la ajustada db+1/16.")
        f.num("Diametro de arandela (0 = automatico)", "bolts.washer_d", 0, 20, uk="L", help="Diametro exterior de la arandela o de la zona donde la tuerca apoya sobre la placa. 0 = automatico: el mayor entre el ancho de la tuerca hex pesada y 2.2 veces el diametro del perno. (Solo modelo solido; el de placas aplica la carga en el anillo del perno.) El modelo 3D aplica la carga del perno sobre esa corona (no en el borde del agujero).")
        f.num("Espesor de arandela (-1 = auto, 0 = sin)", "bolts.washer_t", -1, 5, uk="L", help="Espesor de la arandela del modelo 3D, unida a la placa: rigidiza la zona del agujero y reparte la carga del perno. -1 = automatico (0.25·db); 0 = sin arandela (la carga entra en la corona de la propia placa). Una arandela de placa gruesa se acerca a una zona rigida.")
        f.num("Separacion libre placa-concreto (stand-off)", "bolts.standoff", 0, 24, uk="L", help="Altura libre entre la superficie del concreto (o del mortero) y la cara inferior de la placa cuando esta se apoya en tuercas de nivelacion. El tramo libre del perno es stand-off + espesor de mortero: si supera medio diametro (un mortero delgado lo cubre el factor 0.80 de ACI 17.7.1.2.1) el cortante flexiona el perno y se verifica la flexion y la interaccion traccion-flexion (AISC F11 / H1). Tambien aumenta el brazo del cortante en el 3D. 0 con mortero delgado = sin flexion.")
        f.combo("Condicion de apoyo del perno", "bolts.fixity", FIXITY, help="Doble empotramiento: la placa, sujeta por las dos tuercas, no gira y el perno trabaja en doble curvatura (M = V·l/2). Voladizo: la placa puede girar y el perno es un voladizo (M = V·l), mas conservador. l = stand-off + mortero + tp/2.")
        f.num("Abrg manual (0 = hex pesada)", "bolts.Abrg_user", 0, 100, uk="A", help="Area neta de aplastamiento de la cabeza. Deje 0 para que se calcule de la tuerca hexagonal pesada; indique un valor si usa una placa de anclaje soldada en la punta.")
        f.group("Anclaje adhesivo (postinstalado)")
        f.combo("Adherencia caracteristica", "bolts.adh_env", ADH_ENV,
                help="Sin datos del producto, ACI 318-19 Tabla 17.6.5.2.5 da valores minimos: "
                     "interior seco τcr = 300 psi, τuncr = 1000 psi; exterior 200 / 650 psi. "
                     "El programa aplica los factores de la tabla (0.4 si hay traccion "
                     "sostenida; 0.8 y 0.4 con sismo). Con 'Datos del producto' use los "
                     "valores del reporte ESR/ICC-ES, que ya traen sus propios factores.")
        f.num("τcr (concreto fisurado)", "bolts.tau_cr", 0.01, 5, uk="S",
              help="Esfuerzo de adherencia caracteristico en concreto fisurado, del reporte "
                   "del producto. Solo se usa con 'Datos del producto'.")
        f.num("τuncr (concreto no fisurado)", "bolts.tau_uncr", 0.01, 5, uk="S",
              help="Esfuerzo de adherencia caracteristico en concreto no fisurado. Tambien "
                   "define la distancia critica cNa = 10·da·√(τuncr/1100).")
        f.combo("Categoria del anclaje", "bolts.adh_cat", ADH_CATEGORY,
                help="Categoria de sensibilidad a la instalacion segun ACI 355.4, dada por el "
                     "reporte del producto. Define φ en traccion: cat. 1 = 0.75/0.65, "
                     "cat. 2 = 0.65/0.55, cat. 3 = 0.55/0.45 (condicion A/B).")
        f.num("Fraccion de traccion sostenida", "bolts.sustained", 0, 1, 0.05, 2,
              help="Parte de la traccion que actua de forma permanente (peso propio, "
                   "empuje de tierras). Si es mayor que cero se verifica 0.55·φ·Nba >= Nua,s "
                   "(ACI 17.5.2.2) y se reducen los valores de la Tabla 17.6.5.2.5.")
        f.group("Disposicion")
        f.combo("Patron", "bolts.pattern", PATTERNS, help="Coordenadas manuales: escriba x, y "
                "de cada anclaje en la tabla de abajo, respecto al centro de la placa. Perimetral coloca pernos en los cuatro lados; las opciones de 2 lados solo en los dos lados perpendiculares al eje indicado; Circular los reparte equiespaciados sobre un circulo.")
        f.int_("Pernos en eje MAYOR (fila en X)", "bolts.n_major", 2, 12, help="Cantidad de pernos por fila a lo largo del eje X, es decir en los lados perpendiculares a la direccion del momento. Son los que toman la traccion.")
        f.int_("Pernos en eje MENOR (fila en Y)", "bolts.n_minor", 2, 12, help="Cantidad de pernos por fila a lo largo del eje Y, en los lados paralelos al momento.")
        f.int_("Pernos en patron circular", "bolts.n_circ", 3, 36, help="Cantidad total de pernos equiespaciados sobre el circulo. Solo se usa con el patron Circular.")
        f.num("ex (borde en X)", "bolts.ex", 0.5, 20, uk="L", help="Distancia del centro del perno al borde de la placa en direccion X. Debe dejar material suficiente para la arandela; el programa avisa si baja del minimo recomendado.")
        f.num("ey (borde en Y)", "bolts.ey", 0.5, 20, uk="L", help="Distancia del centro del perno al borde de la placa en direccion Y. Junto con N fija el brazo f de la resultante de traccion.")
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-weight:bold;")
        f._lay.addRow("Total", self.lbl_count)
        f.note("Perimetral: 2·mayor + 2·menor − 4.   2 lados (eje mayor): 2·mayor.   "
               "2 lados (eje menor): 2·menor.")
        f.group("Coordenadas manuales")
        self.tbl_xy = PasteTable(0, 2)
        self.tbl_xy.pasted.connect(self._xy_paste)
        self.tbl_xy.setMinimumHeight(170)
        self.tbl_xy.verticalHeader().setDefaultSectionSize(22)
        self.tbl_xy.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_xy.itemChanged.connect(lambda *_: self._xy_changed())
        f._lay.addRow(self.tbl_xy)
        row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(0, 0, 0, 0)
        for txt, fn in (("Agregar", self._xy_add), ("Quitar", self._xy_del),
                        ("Pegar desde Excel", self._xy_paste_btn),
                        ("Copiar del patron actual", self._xy_copy)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hl.addWidget(bt)
        f._lay.addRow(row)
        f.note("PEGAR DESDE EXCEL: copie dos columnas (x, y) en Excel y use el boton "
               "'Pegar desde Excel' (reemplaza toda la lista) o seleccione una celda y "
               "presione Ctrl+V (sobrescribe desde esa celda y agrega filas si hace falta). "
               "Los valores se leen en las unidades actuales; se aceptan coma o punto "
               "decimal, y los encabezados se ignoran.")
        f.note("Origen en el centro de la placa; +Y es el lado traccionado por Mux. "
               "Las filas se numeran P1, P2... igual que en los dibujos y en la tabla del modelo 3D.")
        f.finish()

        # ---- llave
        f = new_form("Llave de corte")
        f.group("Llave de corte (shear lug)")
        f.check("Usar llave de corte", "lug.enabled", help="Al activarla, todo el cortante se asigna a la llave y deja de exigirse a los pernos, que es la practica habitual cuando el cortante es alto.")
        f.combo("Tipo de llave", "lug.ltype", LUG_TYPES, help="Placa: una pletina (o dos cruzadas). Perfil: cualquier seccion del catalogo (W, HSS, angulo, canal, tubo...). Con perfil se verifica cada direccion de cortante con la proyeccion del perfil: aplastamiento, flexion con Z, cortante, soldadura como grupo y desprendimiento del concreto.")
        self.cb_lugfam = QComboBox()
        self.cb_lugfam.currentTextChanged.connect(self.on_lug_family)
        f._lay.addRow("Familia (si es perfil)", self.cb_lugfam)
        self.cb_lugshape = f.combo("Perfil de la llave", "lug.label", [], help="Seccion usada como llave de corte.")
        f.num("Giro del perfil (0 o 90°)", "lug.rotation", 0, 90, 90.0, 0, "°", help="0°: el perfil queda con su eje fuerte a lo largo de X. 90°: girado. Se usa para decidir que momento resistente (Zx o Zy) trabaja en cada direccion de cortante.")
        f.combo("Orientacion", "lug.direction", LUG_DIRS, help="Eje al que es perpendicular la cara de aplastamiento de la llave. Con Ambos ejes se colocan dos llaves cruzadas y el cortante se reparte entre ellas.")
        f.num("W (ancho)", "lug.W", 1, 60, uk="L", help="Ancho de la llave medido perpendicular a la direccion del cortante. Es el ancho de aplastamiento contra el concreto.")
        f.num("H (altura bajo la placa)", "lug.H", 1, 30, uk="L", help="Altura total de la llave por debajo de la placa. La altura util de aplastamiento es H menos el espesor del mortero.")
        f.num("t (espesor)", "lug.t", 0.25, 6, uk="L", help="Espesor de la pletina de la llave. Gobierna su flexion en la cara inferior de la placa.")
        f.combo("Acero", "lug.steel", [s.name for s in M.PLATE_STEELS])
        f.num("Filete a cada lado", "lug.weld_size", 0.125, 1.5, uk="L")
        f.combo("Electrodo", "lug.electrode", [e.name for e in M.ELECTRODES])
        f.note("Con llave activa el cortante se asigna a la llave y no a los pernos. "
               "La altura embebida descuenta el espesor del mortero.")
        f.finish()

        # ---- rigidizadores
        f = new_form("Rigidizadores")
        f.group("Pletinas rigidizadoras")
        self.lbl_stiff_lock = QLabel("Rigidizadores NO disponibles: la columna esta inclinada "
                                     "(pestaña Cargas). Ponga el giro en 0° para usarlos.")
        self.lbl_stiff_lock.setStyleSheet("color:#9c0006; font-size:8pt;")
        self.lbl_stiff_lock.setWordWrap(True)
        f._lay.addRow("", self.lbl_stiff_lock)
        self.chk_stiff = f.check("Usar rigidizadores", "stiff.enabled", help="Las pletinas reducen el voladizo de la placa y por tanto el espesor requerido, a cambio de soldadura adicional.")
        f.combo("Posicion", "stiff.position", STIFF_POSITIONS, help="Cara del perfil a la que se sueldan las pletinas. En HSS lo habitual es Perimetro de 4 caras; en perfiles W, Alas o Ambos.")
        f.int_("Cantidad total", "stiff.count", 1, 16, help="Numero total de pletinas del conjunto; el programa las reparte entre las caras segun la posicion elegida.")
        f.num("L (proyeccion desde el perfil)", "stiff.L", 0.5, 40, uk="L", help="Cuanto sobresale la pletina desde la cara del perfil hacia el borde de la placa. Si excede el voladizo disponible el programa la recorta y lo avisa.")
        f.num("h (altura)", "stiff.h", 1, 40, uk="L", help="Altura de la pletina sobre la placa, medida en la cara del perfil. Define el modulo de seccion y la longitud de la soldadura a la columna.")
        f.num("t (espesor)", "stiff.t", 0.25, 3, uk="L", help="Espesor de la pletina. Junto con la altura define la esbeltez del borde libre, que se compara con 0.56·√(E/Fy).")
        f.combo("Acero", "stiff.steel", [s.name for s in M.PLATE_STEELS])
        f.group("Ubicacion a lo largo de la cara")
        f.combo("Criterio", "stiff.spacing_mode", STIFF_SPACING, help="Como se ubican las pletinas a lo largo de la cara: repartidas automaticamente, con una separacion que usted fija, o alineadas con los pernos que caen dentro de la cara del perfil.")
        f.num("Separacion centro a centro", "stiff.spacing", 0.5, 100, uk="L", help="Distancia entre pletinas contiguas de una misma cara. Solo se usa con el criterio de separacion fija. Es el parametro para acomodarlas respecto a los anclajes.")
        f.num("Angulo de arranque (columna circular)", "stiff.offset_angle", -180, 180, 5.0, 1, "°", help="Solo columna circular: los rigidizadores se disponen en forma RADIAL, repartidos por igual en 360°. Este es el angulo de la primera pletina medido desde +X. Con columna circular 'Posicion' y 'Criterio' no se usan; la cantidad es el numero total de pletinas radiales.")
        f.num("Corrimiento del grupo", "stiff.offset", -50, 50, uk="L", help="Desplaza todo el grupo de pletinas a lo largo de la cara. Util para esquivar un perno o para centrar el conjunto.")
        f.note("'Separacion fija' reparte las pletinas simetricamente con esa "
               "distancia entre ellas; el corrimiento desplaza todo el grupo. "
               "'Alineado con los pernos' usa las coordenadas de los pernos que "
               "caen dentro de la cara del perfil.")
        f.group("Forma de la pletina")
        f.combo("Forma", "stiff.shape", STIFF_SHAPES, help="Rectangular, triangular, o rectangular con la esquina exterior recortada. En las dos ultimas la seccion critica no esta en la cara del perfil y el programa barre toda la proyeccion.")
        f.num("Recorte horizontal de la esquina", "stiff.clip_h", 0, 20, uk="L", help="Longitud del recorte medida desde el extremo exterior. Solo aplica a la forma con esquina recortada.")
        f.num("Recorte vertical de la esquina", "stiff.clip_v", 0, 20, uk="L", help="Altura del recorte medida desde el borde superior. Solo aplica a la forma con esquina recortada.")
        f.num("Destaje en el vertice placa-columna", "stiff.clip_root", 0, 4, uk="L", help="Pequeno destaje en el encuentro de los dos cordones, practica habitual para evitar el cruce de soldaduras. Se descuenta de ambas longitudes de soldadura.")
        f.group("Soldadura")
        f.num("Filete a cada lado", "stiff.weld_size", 0.125, 1.5, uk="L")
        f.combo("Electrodo", "stiff.electrode", [e.name for e in M.ELECTRODES])
        f.finish()

        # ---- soldadura
        f = new_form("Soldadura")
        f.group("Alas (perfiles W)")
        f.combo("Tipo", "welds.flange.wtype", WELD_TYPES)
        f.num("Tamano (cateto / garganta)", "welds.flange.size", 0.0625, 2, uk="L")
        f.combo("Electrodo", "welds.flange.electrode", [e.name for e in M.ELECTRODES])
        f.check("Ambos lados del ala", "welds.flange.both_sides")
        f.group("Alma (perfiles W)")
        f.combo("Tipo", "welds.web.wtype", WELD_TYPES)
        f.num("Tamano", "welds.web.size", 0.0625, 2, uk="L")
        f.combo("Electrodo", "welds.web.electrode", [e.name for e in M.ELECTRODES])
        f.check("Ambos lados del alma", "welds.web.both_sides")
        f.group("Perimetral (HSS / Pipe)")
        f.combo("Tipo", "welds.perimeter.wtype", WELD_TYPES)
        f.num("Tamano", "welds.perimeter.size", 0.0625, 2, uk="L")
        f.combo("Electrodo", "welds.perimeter.electrode", [e.name for e in M.ELECTRODES])
        f.group("Opciones")
        f.check("Incremento direccional de resistencia (AISC J2-5)", "welds.directional")
        f.note("CJP con metal de aporte compatible: la resistencia es la del metal base "
               "(AISC J2.4) y no se calcula el deposito.")
        f.finish()

        # ---- concreto
        f = new_form("Concreto")
        f.group("Concreto y pedestal")
        self.cb_conc = f.combo("Material", "conc.material", ["(personalizado)"] + [c.name for c in M.CONCRETES], help="Concretos de la biblioteca (Materiales > Biblioteca de materiales). Al elegir uno se copian f'c y λ; con '(personalizado)' se escriben a mano.")
        self.cb_conc.currentTextChanged.connect(self.on_conc_material)
        f.num("f'c", "conc.fc", 2, 15, uk="S", help="Resistencia a compresion especificada del concreto del pedestal a 28 dias.")
        f.num("N2 pedestal (dir. Y)", "conc.N2", 4, 400, uk="L", help="Dimension del pedestal en direccion Y. Junto con B2 define el confinamiento y las distancias al borde que gobiernan el arrancamiento del concreto.")
        f.num("B2 pedestal (dir. X)", "conc.B2", 4, 400, uk="L", help="Dimension del pedestal en direccion X.")
        f.num("ha (altura del elemento)", "conc.ha", 4, 400, uk="L", help="Altura del elemento de concreto medida desde la superficie donde apoya la placa. Interviene en el factor de espesor del arrancamiento en cortante.")
        f.num("λa (concreto liviano)", "conc.lam", 0.5, 1.0, 0.05, 2, help="Factor de concreto liviano de ACI. Use 1.00 para concreto de peso normal.")
        f.check("Concreto fisurado en servicio", "conc.cracked", help="Marque si el concreto estara fisurado en la zona del anclaje bajo cargas de servicio, que es la hipotesis por defecto de ACI. Sin fisurar, las resistencias del concreto aumentan.")
        f.check("Diseno sismico (ACI 17.10, factor 0.75)", "conc.seismic", help="Aplica el factor 0.75 a la resistencia del concreto de los anclajes. No verifica por usted el requisito de que el anclaje sea gobernado por la fluencia ductil del acero.")
        f.group("Refuerzo del arrancamiento (barras U)")
        f.check("Agregar barras de refuerzo (U u Omega)", "conc.u_on", help="Barras en forma de U invertida (herradura) que abrazan el grupo de pernos: un tramo horizontal cerca de la superficie y dos patas verticales a cada lado. Segun ACI 318-19 17.5.2 el refuerzo del anclaje puede sustituir la resistencia del concreto al arrancamiento en traccion y en cortante: la capacidad pasa a ser φ·(n° de patas)·Ab·fy con φ = 0.75, siempre que las patas esten desarrolladas a ambos lados del cono de falla. Se dibujan en la elevacion y en el 3D. El analisis 3D no las modela (solo el calculo cerrado).")
        f.combo("Tipo de barra", "conc.u_type", U_TYPES, help="Opcion A, barra U: patas rectas; bajo la punta del anclaje se desarrolla ld (ACI 25.4.2.3) y el tramo horizontal actua como gancho sobre la punta del anclaje (ldh). Opcion B, barra Omega: las patas terminan en un gancho estandar de 90 grados hacia afuera (cola de 12 db) y bajo la punta del anclaje se desarrolla ldh (ACI 25.4.3). Cada opcion se dibuja en 3D y en la elevacion y se revisa: resistencia a traccion, desarrollo bajo y sobre la punta del anclaje, altura del pedestal y, en la Omega, el recubrimiento de la cola.")
        f.combo("Diametro de la barra", "conc.u_size", list(REBAR.keys()), help="Numero de barra (ASTM A615). #4 = 1/2 in, #5 = 5/8 in, #6 = 3/4 in...")
        f.int_("Cantidad de barras U", "conc.u_n", 1, 12, help="Cada barra aporta 2 patas.  Las barras se colocan FUERA del grupo de anclajes, a 5 cm de la fila extrema (mitad a cada lado), para que no choquen con los pernos; las patas quedan a 0.3·hef de los pernos extremos en X (maximo 0.5·hef, como exige ACI).")
        f.num("fy de la barra", "conc.u_fy", 40, 100, uk="S", help="Esfuerzo de fluencia del refuerzo (Gr. 60 = 60 ksi).")
        f.num("Profundidad del tramo horizontal", "conc.u_depth", 0.5, 24, uk="L", help="Distancia desde la superficie del concreto hasta el tramo horizontal de la U (recubrimiento + barras).")
        f.num("Longitud de la pata (0 = automatica)", "conc.u_leg", 0, 200, uk="L", help="Largo de cada pata medido desde el tramo horizontal. 0 = automatica: la que desarrolla ld (barra U) o ldh (barra Omega) bajo la punta del anclaje (la seccion critica es el extremo inferior del anclaje, z = hef). Si pone un valor, se verifica el desarrollo.")
        f.note("Verifica: capacidad del refuerzo en traccion y cortante (ACI 17.5.2.1, φ = 0.75), desarrollo de la pata bajo la punta del anclaje (ld, ACI 25.4.2.3) y gancho sobre la punta del anclaje (ldh, ACI 25.4.3). El refuerzo sustituye al concreto solo si resiste mas que el.")
        f.finish()

        # ---- FEM 3D y modelo de apoyo
        f = new_form("Elementos finitos")
        f.group("Apoyo y cargas")
        f.combo("Modulo de balasto", "fea.ks_mode", ["Ec/hped", "manual"], help="Ec/hped estima el modulo de balasto como el modulo elastico del concreto dividido entre la altura del pedestal (minimo 6 in). Con manual usted lo impone. Lo usa el modelo solido 3D.")
        f.num("ks manual", "fea.ks_manual", 1, 1e5, uk="K", help="Modulo de balasto del apoyo de concreto. Solo se usa en modo manual.")
        f.num("Brazo del cortante (-1 = automatico)", "fea.shear_arm", -1, 60, uk="L", help="Distancia entre donde el cortante entra en la placa (cara superior) y donde lo devuelven los pernos o la llave. El par V·e es un momento sobre la placa: hace que los pernos de un lado tengan mas traccion que los del otro. -1 = automatico: tp/2 + mortero sin llave; tp + H/2 con llave. 0 = sin efecto del cortante. Lo usa el modelo 3D (altura del punto de aplicacion de las cargas).")
        f.group("Analisis de elementos finitos (Gmsh + CalculiX)")
        f.text("CalculiX propio (opcional)", "fea.ccx_path", help="Dejelo vacio: el programa usa el CalculiX incluido en la carpeta solvers. Solo escriba una ruta si quiere usar otra version de ccx.exe.")
        f.combo("Calidad de la malla 3D", "fea.mesh3d_mode", MESH3D_MODES, help="Automatica (recomendada): el programa calcula el tamano de elemento del proyecto: el mayor entre 1.2 veces el radio de promedio del von Mises (con eso el esfuerzo promediado converge, ±2 % en el estudio de convergencia) y la raiz del area de la placa / 400 (limita el costo en placas grandes, ~70-90 mil nodos). Fina: 0.65 veces ese tamano (mas lenta). Si el calculo falla, el programa reintenta solo con una malla mas gruesa. Un tamano manual mayor que 0 (abajo) tiene prioridad.")
        f.combo("Modelo de la soldadura", "fea.weld_model", WELD_MODELS, help="Conectores (recomendado): el perfil y la placa son cuerpos separados; la compresion pasa por contacto y cada linea de cordon es un conector de traccion y cortante cuya fuerza se lee directo del resorte (una zona sin soldar o un lado sin cordon no transmite). Fusionado: union monolitica que equivale a una CJP; la fuerza del cordon se deduce de los esfuerzos del perfil y una zona sin soldar transmite igual.")
        f.combo("Criterio del cordon (FEM)", "fea.weld_criterion", WELD_CRITERIA, help="Plastico 5 % (Ghimire et al. 2023): los conectores del cordon son elasto-plasticos; fluyen en la resistencia de diseno AISC J2.4 con una rama plastica corta, lo que redistribuye los picos locales, y el D/C del cordon vale 1 cuando la deformacion plastica de su garganta llega al limite. Elastico: los conectores son lineales; el D/C PICO se admite hasta el limite indicado y la MEDIA hasta 1.0.")
        f.num("Deformacion plastica limite del cordon (%)", "fea.weld_plastic_limit", 1, 20, 0.5, 1, help="Deformacion plastica de la garganta del cordon a la que el D/C vale 1.0. 5 % es el valor del articulo de Ghimire et al. (2023) y el limite habitual de EN 1993-1-5 (C.8); AISC 360 admite hasta 10 % en cordones transversales y 48 % en longitudinales, pero no se debe contar con la ductilidad del cordon.")
        f.check("Reduccion por cordon largo (AISC J2.2b(d))", "fea.weld_long_reduction", help="El FEM no captura la reduccion de resistencia de los cordones largos (Ghimire et al. 2023). Si se marca, la capacidad de los filetes con L > 100·w se multiplica por β = 1.2 − 0.002·L/w (β = 0.6 a 300·w; longitud efectiva 180·w despues). Es conservador para cordones que no estan cargados en sus extremos.")
        f.check("Acero elasto-plastico en todas las piezas (sin picos de esfuerzo)", "fea.plastic", help="Modela el acero de TODAS las piezas (placa, perfil, rigidizadores, llave y arandelas) como elasto-plastico perfecto con limite φ·Fy de su propio acero: el esfuerzo no pasa de φ·Fy, los picos puntuales desaparecen y se verifica la deformacion plastica equivalente (PEEQ). Placa: maximo nodal; perfil, rigidizadores y llave: promedio en un circulo de radio ≈ espesor (el borde del cordon es una singularidad de malla). Cuesta unas 4 veces mas tiempo que el calculo elastico. El von Mises que se muestra se recorta en φ·Fy de cada pieza (CalculiX lo extrapola a los nodos y puede pasarse del tope aunque el material no lo haga). Si CalculiX no converge con plasticidad, el programa usa solo el criterio elastico y lo avisa. Desactivado: criterio elastico de von Mises promediado ≤ 0.9·Fy.")
        f.num("Deformacion plastica maxima admitida (%)", "fea.plastic_limit", 0.1, 20, 0.5, 1, help="Limite de la deformacion plastica equivalente en la placa. Valor habitual: 5 % (EN 1993-1-5, C.8).")
        f.num("Limite del D/C pico de la soldadura (FEM)", "fea.weld_peak_factor", 1.0, 3.0, 0.05, 2, help="El FEM da en cada cara del cordon un D/C PICO (el punto mas cargado, tipicamente en las esquinas, en regimen elastico) y un D/C MEDIA (la fuerza de la cara repartida en su longitud). Un filete ductil redistribuye plasticamente el pico antes de fallar, por eso el pico se admite hasta este valor (1.5 por defecto) y la media hasta 1.0. El D/C de la fila es max(pico / limite, media). Ponga 1.0 para exigir el pico completo (muy conservador).")
        f.num("Radio de promedio del von Mises 3D (× espesor)", "fea.vm_avg_factor", 0.1, 3.0, 0.1, 2, help="El von Mises puntual del modelo solido crece sin limite al refinar la malla (singularidades en el borde de los agujeros y en el pie del perfil). El programa verifica el maximo PROMEDIADO: promedio del tensor de esfuerzos, ponderado por area, en un circulo de este radio (en espesores de placa) sobre la misma cara. Predeterminado 1.0. Un radio menor da valores mas altos y mas sensibles a la malla; el radio nunca baja de 1/1.2 del tamano del elemento. Este valor si converge con la malla.")
        f.num("Tamano de malla 3D (0 = automatico)", "fea.mesh3d", 0, 20, uk="L", help="Tamano caracteristico de los tetraedros. Deje 0 para que el programa lo calcule segun la placa y el radio de promedio (recomendado). Un valor manual muy pequeno en una placa grande hace el modelo enorme y el calculo muy lento o no converge; el radio de promedio nunca baja del tamano de elemento.")
        f.num("Malla sobre la soldadura (0 = automatica)", "fea.weld_mesh", 0, 10, uk="L", help="Tamano del elemento junto al cordon (pie del perfil). Con 0 el programa usa ~28 mm aunque la malla global sea muy gruesa, que es lo que calibra el D/C de la soldadura. La fuerza maxima del cordon es un pico local: al afinar esta malla el D/C baja ~5 % y converge; el tamano global casi no lo afecta, pero un cordon muy fino con malla global muy gruesa (> 250 mm) puede dar un pico mayor por la transicion brusca.")
        f.note("El analisis solido 3D es el unico analisis de elementos finitos del programa: sus "
               "resultados (traccion en pernos, presion de contacto, von Mises promediado en la "
               "placa y fuerzas en la soldadura) entran al veredicto y a la memoria de calculo. "
               "Exportar > Modelo solido 3D escribe el .geo con la geometria real mas un script "
               "correr_3d.py que lo malla con Gmsh, arma el .inp y lo resuelve con CalculiX.")
        f.finish()

    # ================================================================== vistas
    def _build_views(self):
        self.tabs_out = QTabWidget()
        self.cv_plan = Canvas(size=(5, 5))
        self.cv_elev = Canvas(size=(6, 4))

        # ---------------- vista general: SOLO la geometria (3D + planta + elevacion)
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        l3.setContentsMargins(0, 0, 0, 0)
        sph = QSplitter(Qt.Horizontal)
        self.use_gl = gl3d.available()
        self.cv_3d = gl3d.GLCanvas3D(dims_button=True) if self.use_gl else Canvas3D()
        gw = QWidget(); gl = QVBoxLayout(gw); gl.setContentsMargins(0, 0, 0, 0)
        def header(widget_left, widget_right=None):
            """Fila de cabecera de altura fija: las barras de herramientas (linea naranja) quedan alineadas."""
            hw = QWidget(); hl = QHBoxLayout(hw); hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(widget_left)
            hl.addStretch(1)
            if widget_right is not None:
                hl.addWidget(widget_right)
            hw.setFixedHeight(28)
            return hw
        self.lbl_geom = QLabel("<b>Geometria de la conexion</b>")
        self.chk_loads_geom = QCheckBox("Mostrar cargas")
        self.chk_loads_geom.setChecked(True)
        self.chk_loads_geom.setToolTip("Flechas de la combinacion activa: Pu (rojo), cortantes (azul) y momentos (violeta).")
        self.chk_loads_geom.toggled.connect(self.draw_geom)
        gl.addWidget(header(self.lbl_geom, self.chk_loads_geom)); gl.addWidget(self.cv_3d)
        self.cb_elev = None
        if self.use_gl:
            # UN SOLO visor: iso, planta, frontal y lateral con sus cotas (reemplaza a los dibujos de planta y elevacion)
            l3.addWidget(gw, 1)
        else:
            sph.addWidget(gw)
            spv = QSplitter(Qt.Vertical)
            pw = QWidget(); pl = QVBoxLayout(pw); pl.setContentsMargins(0, 0, 0, 0)
            pl.addWidget(header(QLabel("<b>Planta</b>"))); pl.addWidget(self.cv_plan)
            ew = QWidget(); el = QVBoxLayout(ew); el.setContentsMargins(0, 0, 0, 0)
            eh = QHBoxLayout()
            eh.addWidget(QLabel("<b>Vista:</b>"))
            self.cb_elev = QComboBox()
            self.cb_elev.addItems(["Elevacion", "Detalle del rigidizador"])
            self.cb_elev.currentIndexChanged.connect(self._draw_elev)
            eh.addWidget(self.cb_elev)
            eh.addStretch(1)
            el.addLayout(eh); el.addWidget(self.cv_elev)
            spv.addWidget(pw); spv.addWidget(ew)
            spv.setSizes([400, 300])
            sph.addWidget(spv)
            sph.setSizes([620, 380])
            l3.addWidget(sph, 1)
        self.tabs_out.addTab(w3, "Modelo y vistas")

        # ---------------- resultados del 3D (campos, soldadura y pernos): solo tras calcular
        wr3 = QWidget()
        lr3 = QVBoxLayout(wr3)
        t3 = QHBoxLayout()
        t3.addWidget(QLabel("<b>Combinacion:</b>"))
        self.cb_combo = QComboBox()
        self.cb_combo.setMinimumWidth(150)
        self.cb_combo.setToolTip("Combinacion de carga que se dibuja y se detalla en los resultados.")
        self.cb_combo.currentIndexChanged.connect(self._on_combo_pick)
        t3.addWidget(self.cb_combo)
        t3.addSpacing(12)
        t3.addWidget(QLabel("Campo:"))
        self.cb_f3 = QComboBox()
        self.cb_f3.addItems(["Von Mises", "Desplazamiento |U|", "Desplazamiento Uz"])
        self.cb_f3.currentIndexChanged.connect(self.draw_3d)
        t3.addWidget(self.cb_f3)
        t3.addWidget(QLabel("Elemento:"))
        self.cb_part = QComboBox()
        self.PARTS = [("all", "Todo el conjunto"), ("plate", "Placa base"), ("column", "Columna (perfil)"),
                      ("stiff", "Rigidizadores"), ("lug", "Llave de corte"), ("washer", "Arandelas")]
        self.cb_part.addItems([b for _, b in self.PARTS])
        self.cb_part.setToolTip("Muestra el esfuerzo (o el desplazamiento) de una sola pieza, con su propia escala "
                                "de colores. El maximo promediado corresponde a la placa; en las demas piezas "
                                "se marca el pico puntual (depende de la malla).")
        self.cb_part.currentIndexChanged.connect(self.draw_3d)
        t3.addWidget(self.cb_part)
        t3.addWidget(QLabel("Escala de deformada:"))
        self.sp_sc = QDoubleSpinBox()
        self.sp_sc.setRange(0, 100000); self.sp_sc.setDecimals(0)
        self.sp_sc.setValue(0); self.sp_sc.setSingleStep(50)
        self.sp_sc.setToolTip("0 = geometria sin deformar.  Un valor mayor amplifica "
                              "los desplazamientos para poder verlos.")
        self.sp_sc.valueChanged.connect(self.draw_3d)
        t3.addWidget(self.sp_sc)
        self.chk_loads_fem = QCheckBox("Mostrar cargas")
        self.chk_loads_fem.setChecked(False)
        self.chk_loads_fem.toggled.connect(self.draw_3d)
        t3.addWidget(self.chk_loads_fem)
        t3.addStretch(1)
        lr3.addLayout(t3)
        sp3 = QSplitter(Qt.Vertical)
        self.cv_res3d = gl3d.GLCanvas3D() if self.use_gl else Canvas3D()
        if self.use_gl:                              # la linea naranja del visor 3D, a la misma altura que la de Planta
            hb = self.cv_plan.nav.sizeHint().height()
            self.cv_3d.match_height(hb)
            self.cv_res3d.match_height(hb)
        sp3.addWidget(self.cv_res3d)
        low = QWidget(); ll = QHBoxLayout(low); ll.setContentsMargins(0, 0, 0, 0)
        self.tbl_w3 = QTableWidget(0, 7)
        self.tbl_b3 = QTableWidget(0, 4)
        for tb in (self.tbl_w3, self.tbl_b3):
            tb.verticalHeader().setVisible(False)
            tb.setEditTriggers(QTableWidget.NoEditTriggers)
            tb.setAlternatingRowColors(True)
            tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        bw = QWidget(); bl = QVBoxLayout(bw); bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(QLabel("<b>Soldadura perfil-placa (leida del solido)</b>"))
        bl.addWidget(self.tbl_w3)
        bb = QWidget(); b2 = QVBoxLayout(bb); b2.setContentsMargins(0, 0, 0, 0)
        b2.addWidget(QLabel("<b>Traccion por perno (3D)</b>"))
        b2.addWidget(self.tbl_b3)
        ll.addWidget(bw, 3); ll.addWidget(bb, 2)
        sp3.addWidget(low)
        sp3.setSizes([560, 230])
        lr3.addWidget(sp3, 1)
        self.lbl_3d = QLabel("")
        self.lbl_3d.setWordWrap(True)
        lr3.addWidget(self.lbl_3d)
        self._lbl_3d_idle()
        self.tabs_out.addTab(wr3, "Analisis FEM")

        # ---------------- resultados + memoria detallada (una sola pestaña)
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Combinacion mostrada:</b>"))
        self.cb_combo2 = QComboBox()
        self.cb_combo2.setMinimumWidth(170)
        self.cb_combo2.setToolTip("Combinacion de carga que se dibuja y se detalla.")
        self.cb_combo2.currentIndexChanged.connect(self._on_combo_pick)
        top.addWidget(self.cb_combo2)
        top.addStretch(1)
        for txt, fn in (("Memoria de calculo PDF", self.export_pdf), ("Memoria de calculo Word", self.export_docx)):
            bt = QPushButton(txt); bt.clicked.connect(fn); top.addWidget(bt)
        self.chk_mem = QCheckBox("Incluir la memoria detallada en los reportes")
        self.chk_mem.setChecked(True)
        top.addWidget(self.chk_mem)
        l2.addLayout(top)
        l2.addWidget(QLabel("<b>Combinaciones de carga</b>"))
        self.tbl_cmb = QTableWidget(0, 5)
        self.tbl_cmb.setHorizontalHeaderLabels(["Combinacion", "D/C max", "Gobierna", "Estado", "Mostrada"])
        self.tbl_cmb.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_cmb.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_cmb.verticalHeader().setVisible(False)
        self.tbl_cmb.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_cmb.setMaximumHeight(95)
        self.tbl_cmb.cellClicked.connect(lambda r, c: self.cb_combo.setCurrentIndex(r))
        l2.addWidget(self.tbl_cmb)
        self.lbl_res_ck = QLabel("<b>Verificaciones de la combinacion mostrada</b>")
        l2.addWidget(self.lbl_res_ck)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Verificacion", "Demanda", "Capacidad",
                                            "Unid.", "D/C", "Referencia / observacion"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        l2.addWidget(self.tbl, 1)
        self.tbl.cellClicked.connect(self._goto_calc)
        self.tbl.setToolTip("Haga clic en una fila para ir a su calculo detallado.")
        l2.addWidget(self.tbl, 3)
        self.txt_info = QTextEdit()
        self.txt_info.setReadOnly(True)
        self.txt_info.setMaximumHeight(80)
        l2.addWidget(self.txt_info)
        bm = QHBoxLayout()
        self.btn_mem = QPushButton("Mostrar calculos detallados")
        self.btn_mem.setCheckable(True)
        self.btn_mem.toggled.connect(self._toggle_mem)
        bm.addWidget(self.btn_mem)
        bcp = QPushButton("Copiar al portapapeles")
        bcp.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_mem.toPlainText()))
        bm.addWidget(bcp)
        bm.addStretch(1)
        l2.addLayout(bm)
        self.txt_mem = QTextEdit()
        self.txt_mem.setReadOnly(True)
        self.txt_mem.setVisible(False)
        l2.addWidget(self.txt_mem, 4)
        self.tabs_out.addTab(w2, "Resultados")

    # palabras de la memoria que corresponden a cada verificacion (clave -> textos a buscar, en orden)
    MEMO_KEYS = {
        "brg": ["Aplastamiento del concreto"], "tp": ["Espesor de la placa"],
        "blt_t": ["Perno en traccion"], "blt_v": ["Perno en cortante"],
        "blt_tv": ["Perno en cortante"], "blt_m": ["Flexion del perno"],
        "blt_tm": ["Interaccion traccion-flexion"], "blt_edge": ["PERNOS DE ANCLAJE"],
        "aci_nsa": ["Acero del anclaje en traccion"], "aci_ncb": ["Arrancamiento del concreto en traccion"],
        "aci_np": ["Extraccion (pullout)"], "aci_vsa": ["Acero del anclaje en cortante"],
        "aci_vcb": ["Arrancamiento del concreto en cortante"], "aci_vcp": ["Pryout"],
        "aci_int": ["ANCLAJES AL CONCRETO"],
        "weld_fl": ["Soldadura de ala"], "weld_fl_min": ["Soldadura de ala"],
        "weld_web": ["Soldadura de alma"], "weld_web_min": ["Soldadura de alma"],
        "lug_brg": ["Aplastamiento del concreto contra la llave"], "lug_flex": ["Flexion de la pletina de la llave"],
        "lug_brkout": ["Desprendimiento del concreto delante de la llave"],
        "lug_shear": ["LLAVE DE CORTE"], "lug_weld": ["LLAVE DE CORTE"],
        "stf_flex": ["Flexion del rigidizador"], "stf_weld_col": ["Soldadura rigidizador-columna"],
        "stf_weld_pl": ["RIGIDIZADORES"], "stf_shear": ["RIGIDIZADORES"], "stf_fit": ["RIGIDIZADORES"],
        "stf_slend": ["RIGIDIZADORES"], "col_norm": ["DATOS DE PARTIDA"], "col_shear": ["DATOS DE PARTIDA"],
        "fem_bolt": ["Tmax perno"], "fem_peeq": ["PEEQ placa"], "fem_press": ["pmax"], "fem_vm": ["σvM promediado"],
    }

    def _goto_calc(self, row, _col=0):
        """Despliega los calculos detallados y salta al paso de la verificacion elegida."""
        if self.res is None or not (0 <= row < len(self.res.checks)):
            return
        ch = self.res.checks[row]
        self.btn_mem.setChecked(True)
        doc = self.txt_mem.document()
        from PySide6.QtGui import QTextDocument, QTextCursor
        cands = list(self.MEMO_KEYS.get(ch.key, []))
        if ch.key.startswith("fem_weld"):
            cands += ["Traccion en cordones", "ELEMENTOS FINITOS"]
        t = ch.title
        cands += [t, t.split(" — ")[-1], t.split(" (")[0]]
        for c in cands:
            if not c.strip():
                continue
            cur = doc.find(c, 0, QTextDocument.FindCaseSensitively)
            if not cur.isNull():
                self.txt_mem.setTextCursor(cur)
                sb = self.txt_mem.verticalScrollBar()
                sb.setValue(sb.value() + self.txt_mem.cursorRect(cur).top() - 8)
                return
        self.txt_mem.moveCursor(QTextCursor.Start)

    def _toggle_mem(self, on):
        self.txt_mem.setVisible(on)
        self.btn_mem.setText("Ocultar calculos detallados" if on else "Mostrar calculos detallados")

    # ============================================================ sincronizacion
    def apply_units(self):
        """Propaga el sistema de unidades elegido a todos los formularios."""
        self.us.set_units(self.prj.u_len, self.prj.u_force,
                          self.prj.u_stress, self.prj.u_moment)
        for f in self.forms:
            f.us = self.us
        cur = (self.prj.u_len, self.prj.u_force, self.prj.u_stress)
        name = "(personalizado)"
        for k, v in DEFAULT_SETS.items():
            if v == cur:
                name = k
                break
        self.cb_preset.blockSignals(True)
        self.cb_preset.setCurrentText(name)
        self.cb_preset.blockSignals(False)

    def on_preset(self, name):
        if self._loading or name not in DEFAULT_SETS:
            return
        L, F, S = DEFAULT_SETS[name]
        self.prj.u_len, self.prj.u_force, self.prj.u_stress = L, F, S
        self.prj.u_moment = {"in": "kip·in", "ft": "kip·ft", "mm": "kN·m",
                             "m": "kN·m", "cm": "tonf·m"}.get(L, "kip·in")
        self.load_ui()
        self.fill_table()
        self.recalc()                       # dibujos, etiquetas y tablas con las unidades nuevas

    def load_ui(self):
        for msg in self.prj.normalize():
            self.statusBar().showMessage(msg, 10000)
        self._loading = True
        try:
            self.apply_units()
            s = self.prj.section.shape()
            self.cb_kind.blockSignals(True)
            self.cb_kind.clear()
            self.cb_kind.addItems([fam_label(f) for f in CATALOG.families()])
            self.cb_kind.setCurrentText(fam_label(s.family))
            self.cb_kind.blockSignals(False)
            self._fill_shapes(s.family, s.label)
            ls = self.prj.lug.shape()
            self.cb_lugfam.blockSignals(True)
            self.cb_lugfam.clear()
            self.cb_lugfam.addItems([fam_label(f) for f in CATALOG.families()])
            self.cb_lugfam.setCurrentText(fam_label(ls.family))
            self.cb_lugfam.blockSignals(False)
            self._fill_lug(ls.family, ls.label)
            for f in self.forms:
                f.load(self.prj)
            self._xy_load()
            self._combo_load()
        finally:
            self._loading = False
        self._update_visibility()
        self._update_labels()

    def store_ui(self):
        for f in self.forms:
            f.store(self.prj)
        self._xy_store()
        self._combo_store()

    # ------------------------------------------ coordenadas manuales de pernos
    def _xy_load(self):
        u = self.us
        t = self.tbl_xy
        t.blockSignals(True)
        t.setHorizontalHeaderLabels([f"x ({u.L})", f"y ({u.L})"])
        t.setRowCount(0)
        for i, (x, y) in enumerate(self.prj.bolts.coords):
            t.insertRow(i)
            t.setVerticalHeaderItem(i, QTableWidgetItem(f"P{i + 1}"))
            for j, v in enumerate((x, y)):
                t.setItem(i, j, QTableWidgetItem(f"{u.out('L', v):.6g}"))
        t.blockSignals(False)

    def _xy_store(self):
        u = self.us
        out = []
        for i in range(self.tbl_xy.rowCount()):
            try:
                x = float(self.tbl_xy.item(i, 0).text().replace(",", ""))
                y = float(self.tbl_xy.item(i, 1).text().replace(",", ""))
            except (AttributeError, ValueError):
                continue
            out.append([u.inn("L", x), u.inn("L", y)])
        if out or self.tbl_xy.rowCount() == 0:
            self.prj.bolts.coords = out

    def _xy_changed(self):
        if self._loading:
            return
        self._xy_store()
        self.on_change()

    def _xy_paste_btn(self):
        rows = parse_xy_clipboard(QApplication.clipboard().text())
        if not rows:
            QMessageBox.information(self, "Pegar coordenadas",
                                    "El portapapeles no contiene dos columnas numericas (x, y).")
            return
        self._xy_paste(rows, 0, True)

    def _xy_paste(self, rows, start, replace=False):
        """Escribe las filas pegadas en la tabla (en unidades del usuario)."""
        self._xy_store()
        u = self.us
        t = self.tbl_xy
        data = [] if replace else [
            [float(t.item(i, j).text().replace(",", "")) if t.item(i, j) and t.item(i, j).text()
             else 0.0 for j in (0, 1)] for i in range(t.rowCount())]
        for k, (x, y) in enumerate(rows):
            i = (0 if replace else start) + k
            while len(data) <= i:
                data.append([0.0, 0.0])
            data[i] = [x, y]
        self._loading = True
        try:
            t.blockSignals(True)
            t.setRowCount(0)
            for i, (x, y) in enumerate(data):
                t.insertRow(i)
                t.setVerticalHeaderItem(i, QTableWidgetItem(f"P{i + 1}"))
                for j, v in enumerate((x, y)):
                    t.setItem(i, j, QTableWidgetItem(f"{v:.6g}"))
            t.blockSignals(False)
        finally:
            self._loading = False
        self._xy_store()
        self.on_change()

    def _xy_add(self):
        self._xy_store()
        c = self.prj.bolts.coords
        self.prj.bolts.coords = c + [[0.0, 0.0]]
        self._xy_load(); self.on_change()

    def _xy_del(self):
        self._xy_store()
        r = self.tbl_xy.currentRow()
        c = list(self.prj.bolts.coords)
        if c:
            c.pop(r if 0 <= r < len(c) else -1)
        self.prj.bolts.coords = c
        self._xy_load(); self.on_change()

    def _xy_copy(self):
        from . import geometry as GG
        self.store_ui()
        old = self.prj.bolts.pattern
        if old.startswith("Coordenadas"):
            return
        self.prj.bolts.coords = [[x, y] for x, y in GG.bolt_positions(self.prj)]
        self.prj.bolts.pattern = "Coordenadas manuales"
        self.load_ui(); self.on_change()

    def _fill_shapes(self, family, select=None):
        self.cb_shape.blockSignals(True)
        self.cb_shape.clear()
        labels = CATALOG.by_family(family)
        self.cb_shape.addItems(labels)
        if select and select in labels:
            self.cb_shape.setCurrentText(select)
        self.cb_shape.blockSignals(False)

    def _fill_lug(self, family, select=None):
        self.cb_lugshape.blockSignals(True)
        self.cb_lugshape.clear()
        labels = CATALOG.by_family(family)
        self.cb_lugshape.addItems(labels)
        if select and select in labels:
            self.cb_lugshape.setCurrentText(select)
        self.cb_lugshape.blockSignals(False)

    def on_kind(self, name):
        if self._loading:
            return
        fam = fam_from_label(name)
        self._fill_shapes(fam)
        steel = FAMILY_STEEL.get(fam)
        if steel:
            for fld in self.forms[2].fields:
                if fld[0] == "section.steel":
                    fld[1].setCurrentText(steel)
        self.on_change()

    def on_lug_family(self, name):
        if self._loading:
            return
        self._fill_lug(fam_from_label(name))
        self.on_change()

    def on_conc_material(self, name):
        if self._loading:
            return
        m = next((c for c in M.CONCRETES if c.name == name), None)
        if m is None:
            return
        self.store_ui()
        self.prj.conc.fc, self.prj.conc.lam = m.fc, m.lam
        self.load_ui()
        self.on_change()

    # ------------------------------------------------ secciones personalizadas
    def _after_custom(self, label):
        self.store_ui()
        self.prj.section.label = label
        self.load_ui()
        self.on_change()

    def new_section(self):
        d = SectionDialog(self.us, self)
        if d.exec() and d.result_shape is not None:
            CATALOG.add_custom(d.result_shape)
            self._after_custom(d.result_shape.label)

    def edit_section(self):
        s = self.prj.section.shape()
        if s.source == "AISC":
            QMessageBox.information(self, "Seccion", "Los perfiles AISC no se editan. "
                                    "Use 'Nueva seccion' para crear una a partir de sus "
                                    "dimensiones.")
            d = SectionDialog(self.us, self, s)
            d.ed_name.setText(s.label + "-MOD")
        else:
            d = SectionDialog(self.us, self, s)
        if d.exec() and d.result_shape is not None:
            CATALOG.add_custom(d.result_shape)
            self._after_custom(d.result_shape.label)

    def del_section(self):
        s = self.prj.section.shape()
        if s.source == "AISC":
            QMessageBox.information(self, "Seccion", "Solo se pueden eliminar secciones "
                                    "personalizadas o importadas.")
            return
        if QMessageBox.question(self, "Seccion", f"¿Eliminar {s.label}?") == QMessageBox.Yes:
            CATALOG.remove(s.label)
            self._after_custom("W14X90")

    # ------------------------------------------------------------- materiales
    def materials_dialog(self):
        d = MaterialsDialog(self.us, self)
        if d.exec():
            self.store_ui()
            self._refresh_material_combos()
            self.load_ui()
            self.on_change()

    def _refresh_material_combos(self):
        lists = {"section.steel": [x.name for x in M.SHAPE_STEELS] +
                 [x.name for x in M.PLATE_STEELS if x.note == "usuario"],
                 "plate.steel": [x.name for x in M.PLATE_STEELS],
                 "lug.steel": [x.name for x in M.PLATE_STEELS],
                 "stiff.steel": [x.name for x in M.PLATE_STEELS],
                 "bolts.steel": [x.name for x in M.ANCHOR_STEELS],
                 "conc.material": ["(personalizado)"] + [c.name for c in M.CONCRETES]}
        for f in self.forms:
            for fld in f.fields:
                if fld[0] in lists:
                    w = fld[1]
                    cur = w.currentText()
                    w.blockSignals(True)
                    w.clear()
                    w.addItems(list(dict.fromkeys(lists[fld[0]])))
                    w.setCurrentText(cur)
                    w.blockSignals(False)

    # ------------------------------------------------------------ conexiones
    def _refresh_list(self):
        self.lst_con.blockSignals(True)
        self.lst_con.clear()
        for p in self.book:
            self.lst_con.addItem(f"{p.element or '(sin nombre)'}   —   {p.section.describe()}")
        self.lst_con.setCurrentRow(self.cur)
        self.lst_con.blockSignals(False)

    def _switch(self, i):
        self.cur = max(0, min(i, len(self.book) - 1))
        self.prj = self.book[self.cur]
        self.load_ui()
        self._refresh_list()
        self.recalc()

    def on_select_connection(self, i):
        if i < 0 or i == self.cur or i >= len(self.book):
            return
        self.store_ui()
        self._switch(i)

    def con_new(self):
        self.store_ui()
        p = Project()
        p.name = self.prj.name
        p.date = datetime.date.today().isoformat()
        p.u_len, p.u_force, p.u_stress, p.u_moment = (self.prj.u_len, self.prj.u_force,
                                                      self.prj.u_stress, self.prj.u_moment)
        p.element = f"PB-{len(self.book) + 1:02d}"
        self.book.append(p)
        self._switch(len(self.book) - 1)

    def con_dup(self):
        import copy
        self.store_ui()
        p = copy.deepcopy(self.prj)
        p.element = (self.prj.element or "PB") + "-copia"
        self.book.insert(self.cur + 1, p)
        self._switch(self.cur + 1)

    def con_rename(self):
        self.store_ui()
        t, ok = QInputDialog.getText(self, "Renombrar conexion", "Nombre / elemento:",
                                     text=self.prj.element)
        if ok and t.strip():
            self.prj.element = t.strip()
            self.load_ui()
            self._refresh_list()

    def con_del(self):
        if len(self.book) <= 1:
            QMessageBox.information(self, "Conexiones", "El proyecto debe tener al menos "
                                    "una conexion.")
            return
        if QMessageBox.question(self, "Conexiones",
                                f"¿Eliminar la conexion {self.prj.element}?") != QMessageBox.Yes:
            return
        self.fem_cache = {k: v for k, v in self.fem_cache.items() if k[0] != id(self.prj)}
        del self.book[self.cur]
        self._switch(min(self.cur, len(self.book) - 1))

    def export_all(self, fmt):
        self.store_ui()
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para los reportes")
        if not folder:
            return
        dlg = QProgressDialog("Generando reportes...", "Cancelar", 0, len(self.book), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        hechos = []
        for i, p in enumerate(self.book):
            if dlg.wasCanceled():
                break
            dlg.setLabelText(f"{p.element}  ({i + 1} de {len(self.book)})")
            QApplication.processEvents()
            try:
                p, r = self.export_target(p)
                tmp = tempfile.mkdtemp(prefix="pbase_")
                figs = report.save_figures(p, r, tmp)
                safe = "".join(ch if ch.isalnum() or ch in "-_ ." else "_"
                               for ch in (p.element or f"conexion_{i+1}"))
                fn = str(Path(folder) / f"{safe}.{fmt}")
                (report.export_pdf if fmt == "pdf" else report.export_docx)(
                    p, r, fn, figs, self.chk_mem.isChecked())
                hechos.append(Path(fn).name)
            except Exception as e:
                hechos.append(f"{p.element}: ERROR {e}")
            dlg.setValue(i + 1)
        dlg.close()
        QMessageBox.information(self, "Reportes", f"Generados en {folder}:\n\n" +
                                "\n".join(hechos))

    def on_change(self):
        if self._loading:
            return
        before = (self.prj.u_len, self.prj.u_force, self.prj.u_stress,
                  self.prj.u_moment)
        # los campos numericos se leen con las unidades ANTERIORES
        self.store_ui()
        changes = self.prj.normalize()
        if changes:
            self.load_ui()                  # refleja el cambio en la casilla
            QMessageBox.information(self, "Columna inclinada", "\n".join(changes))
        after = (self.prj.u_len, self.prj.u_force, self.prj.u_stress,
                 self.prj.u_moment)
        if before != after:
            self.load_ui()          # reescribe todo en las unidades nuevas
            self.fill_table()
        self._update_labels()
        self.timer.start(350)

    def _update_visibility(self):
        """Cada pestaña muestra solo los campos que aplican a lo seleccionado."""
        prj, F = self.prj, self.fnamed
        # ---- placa
        fp, pl = F["Placa"], prj.plate
        circ = pl.shape == "Circular"
        fp.show_field("plate.N", not circ)
        fp.show_field("plate.B", not circ)
        fp.show_field("plate.Dp", circ)
        # ---- perfil
        F["Perfil"].show_field("section.gap", bool(prj.section.double))
        # ---- pernos
        fb, b = F["Pernos"], prj.bolts
        recto = b.atype.startswith("Recto")
        gancho = "Gancho" in b.atype
        adh = recto and b.install == INSTALL_TYPES[1]
        fb.show_field("bolts.install", recto)
        fb.show_group("Anclaje adhesivo (postinstalado)", adh)
        fb.show_field("bolts.eh", gancho)
        fb.show_field("bolts.Abrg_user", b.atype.startswith("Con cabeza"))
        fb.show_field("bolts.fixity", float(getattr(b, "standoff", 0.0)) > 1e-9)
        manual = b.pattern.startswith("Coordenadas")
        circp = b.pattern == "Circular" or circ
        fb.show_field("bolts.n_major", not manual and not circp)
        fb.show_field("bolts.n_minor", not manual and not circp)
        fb.show_field("bolts.n_circ", not manual and circp)
        fb.show_field("bolts.ex", not manual)
        fb.show_field("bolts.ey", not manual and not circp)
        fb.show_group("Coordenadas manuales", manual)
        # ---- llave de corte
        fl, lg = F["Llave de corte"], prj.lug
        on = bool(lg.enabled)
        sec = on and lg.is_section
        for path in ("lug.ltype", "lug.H", "lug.steel", "lug.weld_size", "lug.electrode"):
            fl.show_field(path, on)
        fl.show_field(self.cb_lugfam, sec)
        fl.show_field("lug.label", sec)
        fl.show_field("lug.rotation", sec)
        fl.show_field("lug.direction", on and not sec)
        fl.show_field("lug.W", on and not sec)
        fl.show_field("lug.t", on and not sec)
        # ---- rigidizadores
        fr, st = F["Rigidizadores"], prj.stiff
        on = bool(st.enabled) and not prj.loads.tilted
        for path in ("stiff.position", "stiff.count", "stiff.L", "stiff.h", "stiff.t", "stiff.steel",
                     "stiff.spacing_mode", "stiff.offset", "stiff.shape", "stiff.clip_root", "stiff.weld_size",
                     "stiff.electrode"):
            fr.show_field(path, on)
        fr.show_field("stiff.spacing", on and st.spacing_mode == STIFF_SPACING[1])
        fr.show_field("stiff.offset_angle", on and prj.section.shape().is_round)
        recort = st.shape == STIFF_SHAPES[2]
        fr.show_field("stiff.clip_h", on and recort)
        fr.show_field("stiff.clip_v", on and recort)
        for g in ("Ubicacion a lo largo de la cara", "Forma de la pletina", "Soldadura"):
            fr.show_group(g, on)
        # ---- soldadura (segun el perfil)
        fw = F["Soldadura"]
        hollow = prj.section.shape().is_hollow
        fw.show_group("Alas (perfiles W)", not hollow)
        fw.show_group("Alma (perfiles W)", not hollow)
        fw.show_group("Perimetral (HSS / Pipe)", hollow)
        # ---- concreto: barras U
        fc, cn = F["Concreto"], prj.conc
        for path in ("conc.u_type", "conc.u_size", "conc.u_n", "conc.u_fy", "conc.u_depth", "conc.u_leg"):
            fc.show_field(path, bool(cn.u_on))
        # ---- elementos finitos
        ff, fe = F["Elementos finitos"], prj.fea
        ff.show_field("fea.ks_manual", fe.ks_mode == "manual")
        ff.show_field("fea.plastic_limit", bool(fe.plastic))
        conn = str(fe.weld_model).startswith("Conectores")
        pl = str(fe.weld_criterion).startswith("Plastico")
        ff.show_field("fea.weld_criterion", conn)
        ff.show_field("fea.weld_plastic_limit", conn and pl)
        ff.show_field("fea.weld_peak_factor", conn and not pl)

    def _update_labels(self):
        self._update_visibility()
        tilted = self.prj.loads.tilted
        self.chk_stiff.setEnabled(not tilted)
        self.chk_stiff.setToolTip("No disponible con la columna inclinada." if tilted else "")
        self.lbl_stiff_lock.setVisible(tilted)
        s = self.prj.section.shape()
        e = self.prj.section.eff()
        uu = self.us
        dims = (f"OD={uu.q('L', s.d)}  t={uu.q('L', s.tw)}" if s.is_round else
                f"d={uu.q('L', s.d)}  bf={uu.q('L', s.bf)}  tw={uu.q('L', s.tw)}"
                + (f"  tf={uu.q('L', s.tf)}" if s.tf else ""))
        self.lbl_shape.setText(
            f"{KIND_LABELS.get(s.kind, s.kind)} · {dims}<br>"
            f"{'Seccion doble: ' if self.prj.section.is_double else ''}"
            f"A={uu.q('A', e.A)}  Ix={e.Ix / uu.fl ** 4:.4g}  Iy={e.Iy / uu.fl ** 4:.4g} {uu.L}⁴  "
            f"Sx={e.Sx / uu.fl ** 3:.4g}  Sy={e.Sy / uu.fl ** 3:.4g} {uu.L}³   [{s.source}]"
            + ("<br><i>Rigidizadores no disponibles: la soldadura se verifica como "
               "grupo en todo el contorno.</i>" if self.prj.section.generic else ""))
        it = self.lst_con.item(self.cur) if hasattr(self, "lst_con") else None
        if it is not None:
            it.setText(f"{self.prj.element or '(sin nombre)'}   —   {self.prj.section.describe()}")
        g = self.prj.bolts.geom()
        u = self.us
        self.lbl_bolt.setText(f"db={u.q('L', g.db)}  Ab={u.q('A', g.Ab)}  "
                              f"Ase={u.q('A', g.Ase)}  agujero {u.q('L', g.dh)}  "
                              f"Abrg={u.q('A', g.Abrg)}")
        self.lbl_count.setText(f"{self.prj.bolts.n_total} pernos")
        L = self.prj.eloads
        self.lbl_tilt.setText(
            (f"Pu={u.q('F', L.Pu)}  Vux={u.q('F', L.Vux)}  Vuy={u.q('F', L.Vuy)};  "
             f"Mux={u.q('M', L.Mux)}  Muy={u.q('M', L.Muy)}") if self.prj.loads.tilted
            else "(columna perpendicular: sin cambios)")
        self.lbl_si.setText(f"Pu={u.q('F', L.Pu)}   Mux={u.q('M', L.Mux)}   "
                            f"Muy={u.q('M', L.Muy)}   Vu={u.q('F', L.Vu)}")

    # =================================================================== calculo
    def _fem_now(self, prj=None, idx=None):
        """Analisis 3D vigente de una combinacion: solo si se corrio con el proyecto tal como esta."""
        p = prj if prj is not None else self.prj
        i = p.combo_idx if idx is None else idx
        f = self.fem_cache.get((id(p), i))
        return f if (f is not None and f.sig == p.with_combo(i).sig3d()) else None

    def _raw_now(self):
        """Resultado crudo (para dibujar) del ultimo 3D vigente de la combinacion mostrada."""
        e = self.raw_cache.get((id(self.prj), self.prj.combo_idx))
        if e is not None and e[0] == self.prj.with_combo(self.prj.combo_idx).sig3d():
            return e[1]
        return None

    def _solve_all(self, p):
        """Resultados de TODAS las combinaciones de la conexion p: lista de (proyecto_de_la_combinacion, Results)."""
        out = []
        for i in range(len(p.combo_list())):
            q = p.with_combo(i)
            out.append((q, solve(q, fem=self._fem_now(p, i))))
        return out

    @staticmethod
    def _governing(pairs):
        """Indice de la combinacion que gobierna (mayor D/C)."""
        return max(range(len(pairs)), key=lambda k: pairs[k][1].max_ratio)

    def _combo_rows(self, pairs):
        rows = []
        for q, R in pairs:
            g = R.governing
            rows.append({"name": q.combos[q.combo_idx].name, "ratio": R.max_ratio, "ok": R.ok,
                         "pending": R.pending, "gov": g.title if g else "-"})
        return rows

    def export_target(self, p=None):
        """(proyecto, Results) de la combinacion que gobierna, con la tabla resumen de combinaciones."""
        p = p or self.prj
        pairs = self._solve_all(p)
        k = self._governing(pairs)
        q, R = pairs[k]
        R.combo_rows = self._combo_rows(pairs)
        R.combo_gov = k
        return q, R

    def recalc(self):
        if hasattr(self, "timer"):
            self.timer.stop()                   # evita que un recalculo pendiente pise este
        self.store_ui()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.pairs = self._solve_all(self.prj)
            self.res = self.pairs[self.prj.combo_idx][1]
            self.res.combo_rows = self._combo_rows(self.pairs)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error de calculo",
                                 f"{e}\n\n{traceback.format_exc()[-1500:]}")
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self._fill_combo_box()
        if not self.calculated:
            self._lbl_3d_idle()
        for fn in (self.draw_all, self.fill_table, self.fill_3d_tables):
            try:
                fn()
            except Exception as e:                  # un error de dibujo o de tabla no debe tumbar el resto
                log = self._log_error(fn.__name__, e)
                traceback.print_exc()
                self.statusBar().showMessage(f"Error en {fn.__name__}: {e}  (detalle en {log})", 15000)
        if self.calculated and self.res.rec is not None:
            self.txt_mem.setHtml(self.res.rec.to_html())
        else:
            self.txt_mem.setHtml(f"<p style='color:{self.tc('#7f6000')}'><b>Sin calcular.</b> Presione <b>CALCULAR (F8)</b> "
                                 "para correr el analisis 3D de todas las combinaciones; la memoria de calculo "
                                 "aparece al terminar.</p>")
        self.statusBar().showMessage("Calculo completo" if self.calculated else
                                     "Sin calcular: presione CALCULAR (F8)", 5000)

    @property
    def calculated(self) -> bool:
        """True si TODAS las combinaciones tienen un analisis 3D vigente."""
        pairs = getattr(self, "pairs", None)
        return bool(pairs) and all(not R.pending for _, R in pairs)

    def draw_all(self):
        if not self.use_gl:
            try:
                draw.plan_view(self.cv_plan.ax, self.prj)
                self.cv_plan.cv.draw_idle()
            except Exception as e:
                self.statusBar().showMessage(f"Error de dibujo: {e}", 8000)
            self._draw_elev()
        self.draw_geom()                        # la geometria 3D siempre esta al dia
        self.draw_3d()

    def _draw_elev(self):
        if self.cb_elev is None:
            return
        try:
            self.cv_elev.reset()
            (draw.stiffener_detail if self.cb_elev.currentIndex() == 1 else draw.elevation_view)(
                self.cv_elev.ax, self.prj)
            self.cv_elev.cv.draw_idle()
        except Exception as e:
            self.statusBar().showMessage(f"Error de dibujo: {e}", 8000)

    @staticmethod
    def _log_error(tag, exc):
        """Guarda el traceback en error.log (carpeta de datos del programa) y devuelve la ruta."""
        try:
            base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PlacaBasePro"
            base.mkdir(parents=True, exist_ok=True)
            fn = base / "error.log"
            with open(fn, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {tag}\n")
                f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            return str(fn)
        except Exception:
            return ""

    def draw_geom(self):
        """Pestaña 'Modelo y vistas': solo la geometria, nunca resultados.  Si falla con las flechas de carga se
        reintenta sin ellas (el fallo queda en error.log); si falla la geometria se muestra el motivo en el lienzo."""
        import math as _m
        if self.use_gl:
            try:
                sc = gl3d.scene_geometry(self.prj, loads=self.chk_loads_geom.isChecked())
                self.cv_3d.view.set_scene(sc)
                tl = self.prj.loads
                self.lbl_geom.setText("<b>Geometria de la conexion</b>" + (
                    f"   —   columna inclinada  X {tl.tilt_x:g}°, Y {tl.tilt_y:g}°" if tl.tilted else ""))
            except Exception as e:
                log = self._log_error("draw_geom (GL)", e)
                sc = gl3d.Scene(); sc.message = (f"No se pudo dibujar la geometria 3D:\n{type(e).__name__}: "
                                                 f"{str(e)[:160]}\n\nDetalle en: {log}", "#9c0006")
                self.cv_3d.view.set_scene(sc)
            return
        try:                                    # conserva la orientacion de la camara
            elev, azim = self.cv_3d.ax.elev, self.cv_3d.ax.azim
            if not (_m.isfinite(elev) and _m.isfinite(azim)):
                elev = azim = None
        except Exception:
            elev = azim = None
        want_loads = self.chk_loads_geom.isChecked()
        err, first_err, log = None, None, ""
        for with_loads in ([True, False] if want_loads else [False]):
            self.cv_3d.reset(cbar=False)
            try:
                view3d.plot_geometry(self.cv_3d.ax, self.prj, title=False, loads=with_loads)
                err = None
                if want_loads and not with_loads:
                    self.statusBar().showMessage(
                        f"No se pudieron dibujar las flechas de carga ({first_err}). Detalle en {log}", 12000)
                break
            except Exception as e:
                err = e
                first_err = first_err or e
                log = self._log_error("draw_geom" + (" con cargas" if with_loads else ""), e)
                traceback.print_exc()
        if err is not None:
            # no deja la vista en blanco: muestra el error en el propio lienzo
            self.cv_3d.reset()
            self.cv_3d.ax.set_axis_off()
            self.cv_3d.ax.text2D(0.5, 0.5, "No se pudo dibujar la geometria 3D:\n"
                                 f"{type(err).__name__}: {str(err)[:160]}\n\nDetalle en: {log}",
                                 ha="center", va="center", color="#9c0006",
                                 transform=self.cv_3d.ax.transAxes, fontsize=9)
            self.statusBar().showMessage(f"Error de dibujo 3D: {err}", 8000)
        else:
            tl = self.prj.loads
            self.lbl_geom.setText("<b>Geometria de la conexion</b>" + (
                f"   —   columna inclinada  X {tl.tilt_x:g}°, Y {tl.tilt_y:g}°" if tl.tilted else ""))
        if elev is not None:
            self.cv_3d.ax.view_init(elev=elev, azim=azim)
        view3d.fit_to_axes(self.cv_3d.ax)
        self.cv_3d.cv.draw_idle()

    def _bolt_loads(self):
        """(k, x, y, T) de cada perno del ultimo 3D vigente de la combinacion mostrada."""
        fem = self._fem_now()
        post = getattr(fem, "post", None) if fem is not None else None
        return list(getattr(post, "bolts", []) or [])

    def draw_3d(self):
        """Pestaña 'Analisis FEM': campo de resultados; vacia hasta que el calculo termina."""
        if self.use_gl:
            raw = self._raw_now() if self.calculated else None
            if raw is None or not raw.ok:
                sc = gl3d.Scene()
                sc.message = ("Sin calcular.\nPresione CALCULAR (F8) para ver los resultados.", "#7f6000")
                self.cv_res3d.view.set_scene(sc)
                return
            try:
                sc = gl3d.scene_results(raw, self.prj, ["vm", "u", "uz"][self.cb_f3.currentIndex()],
                                        float(self.sp_sc.value()), part=self.PARTS[self.cb_part.currentIndex()][0],
                                        bolts=self._bolt_loads(), loads=self.chk_loads_fem.isChecked())
            except Exception as e:
                log = self._log_error("draw_3d (resultados GL)", e)
                sc = gl3d.Scene(); sc.message = (f"No se pudo dibujar el campo de resultados:\n{type(e).__name__}: "
                                                 f"{str(e)[:160]}\n\nDetalle en: {log}", "#9c0006")
            self.cv_res3d.view.set_scene(sc)
            return
        try:
            elev, azim = self.cv_res3d.ax.elev, self.cv_res3d.ax.azim
        except Exception:
            elev = azim = None
        raw = self._raw_now() if self.calculated else None
        ok = raw is not None and raw.ok
        self.cv_res3d.reset(cbar=ok)
        if not ok:
            self.cv_res3d.ax.set_axis_off()
            self.cv_res3d.ax.text2D(0.5, 0.5, "Sin calcular.\nPresione CALCULAR (F8) para ver los resultados.",
                                    ha="center", va="center", color="#7f6000",
                                    transform=self.cv_res3d.ax.transAxes, fontsize=11)
            self.cv_res3d.cv.draw_idle()
            return
        fld = ["vm", "u", "uz"][self.cb_f3.currentIndex()]
        try:
            m = view3d.plot3d(self.cv_res3d.ax, raw, self.prj, fld,
                              float(self.sp_sc.value()), part=self.PARTS[self.cb_part.currentIndex()][0],
                              bolts=self._bolt_loads(), loads=self.chk_loads_fem.isChecked())
            if m is not None:
                cax = self.cv_res3d.fig.add_axes([0.90, 0.18, 0.018, 0.64])
                self.cv_res3d.fig.colorbar(m, cax=cax)
        except Exception as e:
            log = self._log_error("draw_3d (resultados)", e)
            self.cv_res3d.reset(cbar=False)
            self.cv_res3d.ax.set_axis_off()
            self.cv_res3d.ax.text2D(0.5, 0.5, f"No se pudo dibujar el campo de resultados:\n{type(e).__name__}: "
                                    f"{str(e)[:160]}\n\nDetalle en: {log}", ha="center", va="center",
                                    color="#9c0006", transform=self.cv_res3d.ax.transAxes, fontsize=9)
            self.statusBar().showMessage(f"Error al dibujar los resultados: {e}", 10000)
            self.cv_res3d.cv.draw_idle()
            return
        if elev is not None:
            self.cv_res3d.ax.view_init(elev=elev, azim=azim)
        view3d.fit_to_axes(self.cv_res3d.ax)
        self.cv_res3d.cv.draw_idle()

    def _lbl_3d_idle(self):
        self.lbl_3d.setText("Ningun resultado se muestra hasta presionar CALCULAR (F8), que corre el analisis "
                            "solido 3D (Gmsh + CalculiX, incluidos) de todas las combinaciones de carga.")

    # ------------------------------------------------------ combinaciones de carga
    def _fill_combo_box(self):
        cs = self.prj.combo_list()
        for cb in (self.cb_combo, self.cb_combo2):
            cb.blockSignals(True)
            cb.clear()
            for c in cs:
                cb.addItem(c.name)
            cb.setCurrentIndex(self.prj.combo_idx)
            cb.blockSignals(False)

    def _on_combo_pick(self, i):
        if self._loading or i < 0 or i == self.prj.combo_idx:
            return
        self.store_ui()
        self.prj.apply_combo(i)
        self.load_ui()
        self.recalc()

    def _combo_load(self):
        u = self.us
        t = self.tbl_cb
        t.blockSignals(True)
        t.setHorizontalHeaderLabels(["Nombre", f"Pu ({u.F})", f"Mux ({u.label('M')})",
                                     f"Muy ({u.label('M')})", f"Vux ({u.F})", f"Vuy ({u.F})"])
        cs = self.prj.combo_list()
        t.setRowCount(len(cs))
        for i, c in enumerate(cs):
            t.setItem(i, 0, QTableWidgetItem(c.name))
            for j, (v, k) in enumerate(((c.Pu, "F"), (c.Mux, "M"), (c.Muy, "M"), (c.Vux, "F"), (c.Vuy, "F")), 1):
                t.setItem(i, j, QTableWidgetItem(f"{u.out(k, v):.6g}"))
        t.selectRow(self.prj.combo_idx)
        t.blockSignals(False)

    def _combo_store(self):
        u = self.us
        t = self.tbl_cb
        cs = []
        for i in range(t.rowCount()):
            try:
                nm = t.item(i, 0).text().strip() or f"Comb {i + 1}"
                v = [float(t.item(i, j).text().replace(",", "")) for j in range(1, 6)]
                if not all(math.isfinite(x) for x in v):
                    raise ValueError("valor no finito")
            except (AttributeError, ValueError):
                old = self.prj.combos[i] if i < len(self.prj.combos) else LoadCombo(f"Comb {i + 1}")
                cs.append(old)
                continue
            cs.append(LoadCombo(nm, u.inn("F", v[0]), u.inn("M", v[1]), u.inn("M", v[2]),
                                u.inn("F", v[3]), u.inn("F", v[4])))
        if cs:
            self.prj.combos = cs
        self.prj.apply_combo(self.prj.combo_idx)

    def _combo_changed(self):
        if self._loading:
            return
        self._combo_store()
        self.on_change()

    def _combo_row_selected(self):
        if self._loading:
            return
        r = self.tbl_cb.currentRow()
        if 0 <= r < len(self.prj.combos) and r != self.prj.combo_idx:
            self._combo_store()
            self.prj.apply_combo(r)
            self.on_change()

    def _combo_add(self):
        self._combo_store()
        n = len(self.prj.combos) + 1
        c = self.prj.combos[self.prj.combo_idx]
        self.prj.combos.append(LoadCombo(f"Comb {n}", c.Pu, c.Mux, c.Muy, c.Vux, c.Vuy))
        self.prj.apply_combo(len(self.prj.combos) - 1)
        self._loading = True
        try:
            self._combo_load()
        finally:
            self._loading = False
        self.on_change()

    def _combo_dup(self):
        self._combo_add()

    def _combo_del(self):
        self._combo_store()
        if len(self.prj.combos) <= 1:
            QMessageBox.information(self, "Combinaciones", "Debe quedar al menos una combinacion.")
            return
        r = self.tbl_cb.currentRow()
        del self.prj.combos[r if 0 <= r < len(self.prj.combos) else -1]
        self.prj.apply_combo(0)
        self._loading = True
        try:
            self._combo_load()
        finally:
            self._loading = False
        self.on_change()

    # --------------------------------------------------------------- ejecutar
    def run_3d(self):
        self.store_ui()
        if self.worker is not None and self.worker.isRunning():
            return
        self.recalc()
        jobs = []
        for i in range(len(self.prj.combo_list())):
            if self._fem_now(self.prj, i) is None:                # solo las combinaciones sin 3D vigente
                q = self.prj.with_combo(i)
                jobs.append((i, self.prj.combos[i].name, q, q.sig3d()))
        if not jobs:
            self.statusBar().showMessage("Todas las combinaciones ya estan calculadas", 4000)
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = (Path(self.path).parent if self.path else
                Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PlacaBasePro")
        folder = str(base / f"{self.prj.element or 'placa'}_3D_{stamp}")
        self.dlg3d = QProgressDialog("Preparando el modelo 3D ...", "Cancelar",
                                     0, 0, self)
        self.dlg3d.setWindowTitle("Analisis 3D")
        self.dlg3d.setWindowModality(Qt.WindowModal)
        self.dlg3d.setMinimumWidth(460)
        self.dlg3d.setCancelButtonText("Cancelar analisis")
        self.dlg3d.setAutoClose(False)
        self.dlg3d.setAutoReset(False)
        self.dlg3d.show()
        self.btn3d.setEnabled(False)
        self._job_prj = self.prj
        self.worker = Worker3D(jobs, folder)      # copias: editar mientras corre no las afecta
        self.worker.progress.connect(self.dlg3d.setLabelText)
        self.dlg3d.canceled.connect(self._cancel_3d)
        self.worker.done.connect(self._on_3d)
        self.worker.start()

    def _cancel_3d(self):
        """Boton 'Cancelar analisis': mata Gmsh/CalculiX en curso."""
        if self.worker is not None and self.worker.isRunning():
            self.dlg3d.setLabelText("Cancelando ...")
            self.worker.cancel()

    def _on_3d(self, out, _msg=""):
        """Termino el calculo: cualquier error al procesar o dibujar se muestra (y se guarda en error.log) en vez
        de dejar la ventana sin resultados."""
        try:
            self._on_3d_impl(out, _msg)
        except Exception as e:
            log = self._log_error("fin del calculo", e)
            traceback.print_exc()
            self.btn3d.setEnabled(True)
            QMessageBox.critical(self, "Error al mostrar los resultados",
                                 f"El calculo termino pero no se pudieron mostrar los resultados:\n\n"
                                 f"{type(e).__name__}: {e}\n\nDetalle en: {log}")

    def _on_3d_impl(self, out, _msg=""):
        try:
            self.dlg3d.canceled.disconnect(self._cancel_3d)
        except Exception:
            pass
        self.dlg3d.close()
        self.btn3d.setEnabled(True)
        p = self._job_prj
        cancelled, failed = False, None
        for idx, name, q, sig, res, msg in out:
            if res is None:
                if msg.startswith(mesh3d.CANCELADO):
                    cancelled = True
                else:
                    failed = (name, msg)
                continue
            fem = make_fem(q, res)
            fem.sig = sig                           # firma del proyecto con que SE CORRIO
            self.fem_cache[(id(p), idx)] = fem
            self.raw_cache[(id(p), idx)] = (sig, res)
        if p is not self.prj:                       # el usuario cambio de conexion mientras corria
            self.recalc()
            return
        self.recalc()                               # el 3D entra al veredicto y a la memoria
        if cancelled:
            self.lbl_3d.setText("Analisis cancelado.")
            self.statusBar().showMessage("Analisis 3D cancelado", 5000)
        if failed:
            self.lbl_3d.setText(f"<span style='color:{self.tc('#9c0006')}'>{failed[0]}: {failed[1][:600]}</span>")
            QMessageBox.warning(self, "Analisis 3D", f"Combinacion {failed[0]}:\n\n{failed[1][-2500:]}")
        raw, fem = self._raw_now(), self._fem_now()
        if raw is not None and fem is not None:
            u = self.us
            vmx = getattr(raw, "vm_avg", None)
            pk = getattr(fem, "peeq", None)
            if pk is not None:
                stress_txt = (f"<b>von Mises maximo</b> = {u.q('S', raw.vmmax)}  ·  "
                              f"<b>deformacion plastica maxima en la placa</b> = {pk[0] * 100:.3f} % "
                              f"(limite {self.prj.fea.plastic_limit:g} %)  ·  ")
                tail = ""
            else:
                stress_txt = ((f"<b>von Mises promediado en la placa</b> (r = {u.q('L', vmx['radius'])}) = "
                               f"{u.q('S', vmx['vm'])}  ·  " if vmx else "")
                              + f"<b>von Mises pico puntual</b> = {u.q('S', raw.vmmax)} (depende de la malla)  ·  ")
                tail = ("Los picos de von Mises en aristas vivas (borde de agujero, encuentro perfil-placa) son "
                        "singularidades de malla: dependen del tamano de elemento y no deben leerse como esfuerzo real.")
            self.lbl_3d.setText(
                f"<b>Combinacion {self.prj.combos[self.prj.combo_idx].name}:</b> "
                f"<b>{raw.n_nodes:,} nodos</b> y {raw.n_elems:,} elementos.  "
                f"<b>|U| max</b> = {u.q('L', raw.umax)}  ·  " + stress_txt
                + (f"equilibrio: {fem.msg}<br>" if fem.msg else "<br>")
                + f"Archivos en: {getattr(raw, 'folder', '')}<br>"
                + (f"<span style='color:{self.tc('#595959')}'>Tamano de elemento: {u.q('L', fem.lc)}.</span><br>" if fem.lc else "")
                + tail)
            self.tabs_out.setCurrentIndex(1)        # muestra el analisis FEM al terminar
        if self.calculated and len(self.pairs) > 1:
            self.statusBar().showMessage(f"Calculo completo; gobierna la combinacion "
                                         f"{self.pairs[self._governing(self.pairs)][0].combos[self._governing(self.pairs)].name}",
                                         8000)

    def fill_3d_tables(self):
        """Tablas del modelo 3D: soldadura por zona y traccion por perno."""
        from .weld3d import summary_rows
        fem = self._fem_now()
        post = fem.post if fem is not None else None
        for tb in (self.tbl_w3, self.tbl_b3):
            tb.setRowCount(0)
        if post is None or not self.calculated:
            return
        u = self.us
        welds, _ = summary_rows(self.prj, post)
        phi = None
        try:
            from .fem_checks import bolt_phiRnt
            phi = bolt_phiRnt(self.prj)
        except Exception:
            pass
        bolts = [["Perno", f"x ({u.L})", f"y ({u.L})", f"T ({u.F})", "D/C"]]
        for (k, x, y, T) in sorted(post.bolts, key=lambda b: -b[3]):
            bolts.append([f"P{k}", u.fmt("L", x), u.fmt("L", y), u.fmt("F", T),
                          f"{T / phi:.3f}" if phi else "—"])
        red, green = QColor("#ffc7ce"), QColor("#c6efce")
        for tb, rows, dc_cols in ((self.tbl_w3, welds, (5, 6)), (self.tbl_b3, bolts, (4,))):
            tb.setColumnCount(len(rows[0]))
            tb.setHorizontalHeaderLabels(rows[0])
            if tb is self.tbl_w3:
                tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            for r in rows[1:]:
                i = tb.rowCount(); tb.insertRow(i)
                for j, v in enumerate(r):
                    it = QTableWidgetItem(v)
                    if j in dc_cols:
                        try:
                            ok = float(v) <= (float(getattr(self.prj.fea, 'weld_peak_factor', 1.5)) if (tb is self.tbl_w3 and j == dc_cols[0]) else 1.0)
                        except ValueError:
                            ok = False
                        it.setBackground(green if ok else red)
                        it.setForeground(QColor("#1b1b1b"))     # texto oscuro sobre verde/rojo/gris (tema oscuro)
                    tb.setItem(i, j, it)
        self.tbl_w3.setToolTip(
            "D/C pico: el punto mas cargado del cordon (concentracion elastica, por "
            "ejemplo donde el alma llega al ala). D/C media: la fuerza de toda la pared "
            "repartida en su longitud, que es lo que supone el calculo DG1. La "
            "compresion se transmite por contacto; el cordon se verifica a traccion y "
            "cortante.")

    def fill_table(self):
        r = self.res
        self.tbl.setRowCount(0)
        self.tbl_cmb.setRowCount(0)
        red, green, grey = QColor("#ffc7ce"), QColor("#c6efce"), QColor("#eeeeee")
        pairs = self.pairs
        done = self.calculated
        u = self.us

        # ---- barra superior: veredicto
        if not done:
            # ningun resultado se muestra hasta terminar el calculo
            falta = [q.combos[q.combo_idx].name for q, R in pairs if R.pending]
            self.lbl_verdict.setText("  SIN CALCULAR  ")
            self.lbl_verdict.setToolTip("Presione CALCULAR (F8): el veredicto sale del analisis solido 3D. "
                                        + (("Pendientes: " + ", ".join(falta)) if falta else ""))
            bg, fg = "#ffeb9c", "#9c5700"
            self.lbl_verdict.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:4px; padding:2px 8px;")
            fatal = [w for w in r.warnings if w.startswith("**")]
            html = ["<b>Sin calcular.</b> Presione <b>CALCULAR (F8)</b> (barra superior): se corre el analisis "
                    "3D de " + (f"las {len(pairs)} combinaciones de carga" if len(pairs) > 1 else "la conexion")
                    + " y aparecen aqui las verificaciones, el D/C y la memoria de calculo."]
            for w in fatal:
                html.append(f"<span style='color:{self.tc('#9c0006')}'>• {w}</span>")
            self.txt_info.setHtml("<br>".join(html))
            self.lbl_res_ck.setText("<b>Verificaciones</b> (aparecen al terminar el calculo)")
            return

        gk = self._governing(pairs)
        cmb = self.tbl_cmb
        for k, (q, R) in enumerate(pairs):
            g = R.governing
            cmb.insertRow(k)
            vals = [q.combos[q.combo_idx].name, f"{R.max_ratio:.3f}", g.title if g else "-",
                    "CUMPLE" if R.ok else "NO CUMPLE", "◄" if k == self.prj.combo_idx else ""]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 3:
                    it.setBackground(green if R.ok else red)
                    it.setForeground(QColor("#1b1b1b"))     # texto oscuro sobre verde/rojo/gris (tema oscuro)
                if k == gk and j == 0:
                    f_ = it.font(); f_.setBold(True); it.setFont(f_)
                    it.setToolTip("Combinacion que gobierna")
                cmb.setItem(k, j, it)
        self.lbl_res_ck.setText(f"<b>Verificaciones de la combinacion mostrada: "
                                f"{self.prj.combos[self.prj.combo_idx].name}</b>")
        for ch in r.checks:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)
            dv, cv, ul = report.ck_vals(self.us, ch)
            vals = [ch.title, f"{dv:,.3f}", f"{cv:,.3f}", ul,
                    "—" if ch.skip else f"{ch.ratio:.3f}",
                    ch.ref + ("  —  " + ch.note if ch.note else "")]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j in (1, 2, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 4:
                    it.setBackground(grey if ch.skip else (green if ch.ok else red))
                    it.setForeground(QColor("#1b1b1b"))     # texto oscuro sobre verde/rojo/gris (tema oscuro)
                    f = it.font(); f.setBold(True); it.setFont(f)
                it.setToolTip(v)
                self.tbl.setItem(i, j, it)

        br = r.br
        gov = r.governing
        ee = "∞" if br.e == float("inf") else u.q("L", br.e)
        html = [f"<b>{br.case}</b> — e = {ee}, ecrit = {u.q('L', br.ecrit)}, "
                f"Y = {u.q('L', br.Y)}, fp = {u.fmt('S', br.fp)} / {u.q('S', br.fp_max)}, "
                f"Tu = {u.q('F', br.Tu)} en {br.n_t} pernos (f = {u.q('L', br.f_arm)}).  "
                f"t requerido = <b>{u.q('L', r.treq)}</b> vs tp = {u.q('L', self.prj.plate.tp)}."]
        if gov:
            html.append(f"Gobierna: <b>{gov.title}</b>  (D/C = {gov.ratio:.3f})")
        for w in r.warnings:
            col = self.tc("#9c0006" if w.startswith("**") else "#7f6000")
            html.append(f"<span style='color:{col}'>• {w}</span>")
        self.txt_info.setHtml("<br>".join(html))

        ok = all(R.ok for _, R in pairs)
        dcm = max(R.max_ratio for _, R in pairs)
        gname = pairs[gk][0].combos[pairs[gk][0].combo_idx].name
        self.lbl_verdict.setText(f"  {'CUMPLE' if ok else 'NO CUMPLE'}   D/C max = {dcm:.3f}"
                                 + (f"  ({gname})" if len(pairs) > 1 else "") + "  ")
        bg, fg = ("#c6efce", "#006100") if ok else ("#ffc7ce", "#9c0006")
        self.lbl_verdict.setToolTip("")
        self.lbl_verdict.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:4px; padding:2px 8px;")

    # ================================================================= archivo
    def new(self):
        if QMessageBox.question(self, "Nuevo", "¿Descartar el proyecto actual?") != QMessageBox.Yes:
            return
        self.prj = Project()
        self.prj.date = datetime.date.today().isoformat()
        self.book = [self.prj]
        self.cur = 0
        self.fem_cache = {}
        self.raw_cache = {}
        self.path = None
        self._switch(0)

    def open(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", "",
                                            "Placa base (*.pbase *.json)")
        if not fn:
            return
        try:
            self.book = load_book(fn)
            self.fem_cache = {}
            self.raw_cache = {}
            self.path = fn
            self._refresh_material_combos()
            self._switch(0)
            self.setWindowTitle(f"PlacaBasePro {__version__} — {Path(fn).name}")
        except Exception as e:
            QMessageBox.critical(self, "Abrir", f"No se pudo abrir el archivo:\n{e}")

    def save(self):
        if not self.path:
            return self.save_as()
        self.store_ui()
        save_book(self.path, self.book)
        self.statusBar().showMessage(f"Guardado: {self.path}", 4000)

    def save_as(self):
        self.store_ui()
        # el archivo guarda TODO el proyecto (todas las conexiones): se sugiere el nombre del proyecto
        safe = "".join(ch if (ch.isalnum() or ch in "-_ .") else "_" for ch in (self.prj.name or "").strip()) \
            .strip(" .") or "Proyecto"
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", f"{safe}.pbase", "Placa base (*.pbase)")
        if fn:
            self.path = fn
            self.save()
            self.setWindowTitle(f"PlacaBasePro {__version__} — {Path(fn).name}")

    def import_aisc(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "Importar AISC Shapes Database v14.1", "",
            "AISC shapes (*.xlsx *.xlsm *.csv)")
        if not fn:
            return
        try:
            n, msg = CATALOG.import_aisc(fn)
            s = self.prj.section.shape()
            self._fill_shapes(s.kind, s.label)
            QMessageBox.information(self, "Importar AISC", msg)
        except Exception as e:
            QMessageBox.critical(self, "Importar AISC", f"Error:\n{e}")

    # ================================================================ exportar
    def _ensure_results(self):
        self.store_ui()
        if self.res is None:
            self.recalc()
        if not self.calculated:
            QMessageBox.information(self, "Exportar", "El calculo no esta terminado: el reporte saldra marcado como "
                                    "PENDIENTE. Presione CALCULAR (F8) para incluir el analisis 3D.")

    def export_pdf(self):
        self._ensure_results()
        fn, _ = QFileDialog.getSaveFileName(self, "Memoria de calculo en PDF",
                                            f"Memoria_{self.prj.element}.pdf", "PDF (*.pdf)")
        if not fn:
            return
        try:
            tmp = tempfile.mkdtemp(prefix="pbase_")
            q, R = self.export_target()
            figs = report.save_figures(q, R, tmp)
            report.export_pdf(q, R, fn, figs, self.chk_mem.isChecked())
            self._done(fn)
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"{e}\n\n{traceback.format_exc()[-1200:]}")

    def export_3d(self):
        self.store_ui()
        fn, _ = QFileDialog.getSaveFileName(
            self, "Modelo solido 3D (Gmsh)",
            f"{self.prj.element or 'placa'}_3d.geo", "Gmsh (*.geo)")
        if not fn:
            return
        try:
            geo, drv = mesh3d.export_3d(self.prj, fn, mesh3d.mesh_size_for(self.prj))
        except Exception as e:
            QMessageBox.critical(self, "Modelo 3D", f"{e}")
            return
        if QMessageBox.question(
                self, "Modelo 3D",
                f"Generados:\n\n{geo}\n{drv}\n\n"
                "¿Mallar ahora con Gmsh?  (puede tardar varios minutos)"
                ) != QMessageBox.Yes:
            self._done(geo)
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        ok, out, inp = mesh3d.run_gmsh(geo)
        QApplication.restoreOverrideCursor()
        if ok:
            QMessageBox.information(
                self, "Modelo 3D",
                f"Malla generada:\n{inp}\n\n"
                f"Ejecute ahora, en esa carpeta:\n    python correr_3d.py\n\n"
                "arma el .inp de CalculiX con apoyos, resortes de perno y cargas, "
                "y lo resuelve.")
        else:
            QMessageBox.warning(self, "Gmsh", out[-2500:])

    def export_docx(self):
        self._ensure_results()
        fn, _ = QFileDialog.getSaveFileName(self, "Memoria de calculo",
                                            f"Memoria_{self.prj.element}.docx", "Word (*.docx)")
        if not fn:
            return
        try:
            tmp = tempfile.mkdtemp(prefix="pbase_")
            q, R = self.export_target()
            figs = report.save_figures(q, R, tmp)
            report.export_docx(q, R, fn, figs, self.chk_mem.isChecked())
            self._done(fn)
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"{e}\n\n{traceback.format_exc()[-1200:]}")

    def export_png(self):
        self._ensure_results()
        d = QFileDialog.getExistingDirectory(self, "Carpeta de destino")
        if d:
            q, R = self.export_target()
            paths = report.save_figures(q, R, d)
            self._done(f"{len(paths)} imagenes en {d}")

    def _done(self, what):
        self.statusBar().showMessage(f"Exportado: {what}", 6000)
        QMessageBox.information(self, "Exportar", f"Archivo generado:\n{what}")

    def about(self):
        mb = QMessageBox(self)
        mb.setWindowTitle("Acerca de PlacaBasePro")
        pm = QPixmap(brand.LOGO())
        if not pm.isNull():
            mb.setIconPixmap(pm.scaledToWidth(360, Qt.SmoothTransformation))
        mb.setText(
            f"<b>PlacaBasePro {__version__}</b><br>"
            "Diseno y verificacion de placas base para perfiles W, HSS y Pipe.<br><br>"
            "AISC 360-22 · AISC Design Guide 1 (2ª Ed.) · ACI 318-19 Cap. 17<br>"
            "Modelo solido 3D (Gmsh + CalculiX) "
            "con el concreto como resortes solo a compresion.<br><br>"
            "Los resultados deben ser revisados por un ingeniero responsable.")
        mb.exec()

    def tc(self, c):
        """Color de texto adecuado al tema (los rojos y ambares oscuros se aclaran sobre fondo oscuro)."""
        if not getattr(self, "_dark", False):
            return c
        return {"#9c0006": "#ff8a8a", "#7f6000": "#e6c15a", "#595959": "#aab2bb"}.get(c, c)

    def _set_dark(self, on):
        self._dark = bool(on)
        brand.apply_theme(QApplication.instance(), on)
        brand.retheme(self, on)
        if getattr(self, "_ready", False):
            self.recalc()                  # regenera los textos con los colores del tema
        if getattr(self, "lg", None) is not None:
            self.lg.setPixmap(brand.logo_pixmap(on, 250))
        try:
            from PySide6.QtCore import QSettings
            QSettings("PlacaBasePro", "PlacaBasePro").setValue("dark", bool(on))
        except Exception:
            pass

    def closeEvent(self, ev):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()                  # no deja Gmsh/CalculiX corriendo al cerrar
            self.worker.wait(5000)
        ev.accept()


def _theme_dark():
    """El programa abre en claro salvo que el usuario haya elegido el tema oscuro."""
    try:
        from PySide6.QtCore import QSettings
        v = QSettings("PlacaBasePro", "PlacaBasePro").value("dark", False)
        return str(v).lower() in ("true", "1")
    except Exception:
        return False


class _WheelGuard(QObject):
    """La rueda del raton solo cambia campos numericos/listas que tengan el foco (clic previo);
    si no, el giro se reenvia al panel para que haga scroll."""
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Wheel or not isinstance(obj, QWidget):
            return False
        w = obj
        while w is not None and not w.isWindow():
            if isinstance(w, (QAbstractSpinBox, QComboBox)):
                if w.hasFocus() or (w.isEditable() if isinstance(w, QComboBox) else False) and w.lineEdit().hasFocus():
                    return False
                par = w.parentWidget()
                if par is not None:
                    QApplication.sendEvent(par, ev)
                return True
            w = w.parentWidget()
        return False


def main():
    if sys.platform.startswith("win"):
        try:                      # la barra de tareas de Windows agrupa y muestra el icono propio
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PlacaBasePro.App")
        except Exception:
            pass
    gl3d.set_default_format()
    app = QApplication(sys.argv)
    app.setApplicationName("PlacaBasePro")
    gl3d.available()                       # sondea OpenGL antes de crear la ventana (ajusta el suavizado si es por software)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(brand.ICO()))
    brand.apply_theme(app, _theme_dark())
    app._wheel_guard = _WheelGuard(app)
    app.installEventFilter(app._wheel_guard)
    splash = None
    pm = QPixmap(brand.LOGO())
    if not pm.isNull():
        from PySide6.QtWidgets import QSplashScreen
        card = QPixmap(560, 220)
        card.fill(QColor(brand.GREY))
        from PySide6.QtGui import QPainter
        pt = QPainter(card)
        lw = pm.scaledToWidth(480, Qt.SmoothTransformation)
        pt.drawPixmap((560 - lw.width()) // 2, 40, lw)
        pt.setPen(QColor(brand.SLATE))
        pt.drawText(card.rect().adjusted(0, 0, 0, -14), Qt.AlignHCenter | Qt.AlignBottom,
                    f"Version {__version__}  ·  cargando ...")
        pt.end()
        splash = QSplashScreen(card)
        splash.show()
        app.processEvents()
    w = MainWindow()
    w.show()
    if splash is not None:
        splash.finish(w)
    return app.exec()
