# -*- coding: utf-8 -*-
"""Identidad visual de SteelConPro: ruta de los recursos graficos y colores de marca."""
from __future__ import annotations
import os
import sys
from pathlib import Path

DARK = "#12171E"          # negro azulado del logo
ORANGE = "#E85D0C"        # naranja del logo
ORANGE_DK = "#C44A06"
GREY = "#F3F4F1"          # fondo claro del logo
SLATE = "#4A5563"         # gris del lema


def asset(name: str) -> str:
    """Ruta de un recurso de steelconpro/data (tambien dentro del ejecutable de PyInstaller)."""
    for base in (Path(__file__).parent / "data", Path(getattr(sys, "_MEIPASS", ".")) / "steelconpro" / "data"):
        p = base / name
        if p.exists():
            return str(p)
    return str(Path(__file__).parent / "data" / name)


LOGO = lambda: asset("logo.png")          # logo horizontal con lema (fondo transparente)
LOGO_DARK = lambda: asset("logo_dark.png")   # el mismo, con el texto claro para el tema oscuro
ICON = lambda: asset("icon.png")          # icono cuadrado 256 px
ICO = lambda: asset("steelconpro.ico")   # icono de Windows (.ico multi-tamano)

def _style(c: dict) -> str:
    """Hoja de estilo comun a los dos temas; `c` trae los colores (borde, fondo suave, texto, acento...)."""
    return f"""
QToolBar {{ background: {c['bar']}; border: 0; border-bottom: 2px solid {ORANGE}; spacing: 6px; padding: 3px 6px; }}
QToolBar QToolButton {{ border: 1px solid transparent; border-radius: 5px; padding: 3px 8px; }}
QToolBar QToolButton:hover {{ border-color: {c['line']}; background: {c['hover']}; }}
QMenuBar {{ background: {c['bar']}; }}
QMenuBar::item {{ padding: 4px 9px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {c['hover']}; }}
QMenu {{ border: 1px solid {c['line']}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ORANGE}; color: white; }}
QTabWidget::pane {{ border: 0; border-top: 1px solid {c['line']}; }}
QTabBar::tab {{ padding: 6px 13px; margin-right: 1px; border: 0; border-bottom: 3px solid transparent; color: {c['muted']}; background: transparent; }}
QTabBar::tab:hover {{ color: {c['text']}; background: {c['hover']}; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
QTabBar::tab:selected {{ border-bottom: 3px solid {ORANGE}; font-weight: bold; color: {c['text']}; }}
QTabBar::tab:disabled {{ color: {c['faint']}; }}
QGroupBox {{ font-weight: bold; color: {c['text']}; border: 0; border-top: 1px solid {c['line']}; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 0px; padding: 0 6px 0 0; color: {c['accent']}; }}
QHeaderView::section {{ background: {c['bar']}; color: {c['text']}; border: 0; border-bottom: 1px solid {c['line']}; border-right: 1px solid {c['soft']}; padding: 4px 6px; font-weight: 600; }}
QTableView, QTableWidget {{ gridline-color: {c['soft']}; alternate-background-color: {c['alt']}; selection-background-color: {ORANGE}; selection-color: #ffffff;
                           border: 1px solid {c['line']}; border-radius: 4px; }}
QListWidget {{ border: 1px solid {c['line']}; border-radius: 4px; alternate-background-color: {c['alt']}; }}
QListWidget::item {{ padding: 3px 4px; }}
QListWidget::item:selected {{ background: {ORANGE}; color: white; border-radius: 3px; }}
QTextBrowser, QTextEdit, QPlainTextEdit {{ border: 1px solid {c['line']}; border-radius: 4px; }}
QStatusBar {{ background: {c['bar']}; color: {c['text']}; border-top: 1px solid {c['line']}; }}
QStatusBar::item {{ border: 0; }}
QPushButton {{ border: 1px solid {c['line']}; border-radius: 5px; padding: 5px 12px; background: {c['btn']}; }}
QPushButton:hover {{ border-color: {ORANGE}; background: {c['hover']}; }}
QPushButton:pressed {{ background: {c['soft']}; }}
QPushButton:disabled {{ color: {c['faint']}; background: {c['bar']}; }}
QPushButton:default {{ border-color: {ORANGE}; }}
QToolButton {{ border: 1px solid {c['line']}; border-radius: 5px; padding: 4px 8px; background: {c['btn']}; }}
QToolButton:hover {{ border-color: {ORANGE}; background: {c['hover']}; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['handle']}; border-radius: 4px; min-height: 28px; margin: 1px 2px; }}
QScrollBar::handle:vertical:hover {{ background: {ORANGE}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {c['handle']}; border-radius: 4px; min-width: 28px; margin: 2px 1px; }}
QScrollBar::handle:horizontal:hover {{ background: {ORANGE}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QToolTip {{ border: 1px solid {c['line']}; padding: 4px; }}
QSplitter::handle {{ background: {c['soft']}; }}
QSplitter::handle:hover {{ background: {ORANGE}; }}
"""


_LIGHT = dict(bar="#eef1f5", line="#cdd4dd", soft="#e3e8ee", alt="#f6f8fa", hover="#e6ebf1", btn="#f7f8fa", text="#12171e", muted="#4d5866",
              faint="#9aa3ae", accent="#1f3864", handle="#b9c2cd")
_DARKC = dict(bar="#1b222b", line="#3a4452", soft="#2c3541", alt="#1b232c", hover="#313c4a", btn="#2c3643", text="#e6e8ea", muted="#9aa6b4",
              faint="#6d7886", accent="#9fc3f0", handle="#4a5667")
STYLE = _style(_LIGHT)
STYLE_DARK = _style(_DARKC)


def apply_theme(app, dark=False):
    """Paleta explicita (no depende del tema de Windows). Los graficos siempre van sobre blanco."""
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import Qt
    pal = QPalette()
    if dark:
        c = dict(Window="#232b35", WindowText="#e6e8ea", Base="#161c23", AlternateBase="#1d252e",
                 Text="#e6e8ea", Button="#2c3643", ButtonText="#e6e8ea", ToolTipBase="#fffbe6",
                 ToolTipText="#12171e", Highlight=ORANGE, HighlightedText="#ffffff",
                 BrightText="#ffffff", Link="#6cb6ff", PlaceholderText="#8a94a0")
    else:
        c = dict(Window="#f4f6f9", WindowText="#12171e", Base="#ffffff", AlternateBase="#f6f8fa",
                 Text="#12171e", Button="#efefef", ButtonText="#12171e", ToolTipBase="#fffbe6",
                 ToolTipText="#12171e", Highlight=ORANGE, HighlightedText="#ffffff",
                 BrightText="#ffffff", Link="#1f5fa8", PlaceholderText="#7a7f85")
    for k, v in c.items():
        pal.setColor(getattr(QPalette.ColorRole, k), QColor(v))
    dis = "#7d8793" if dark else "#9a9a9a"
    for r in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, r, QColor(dis))
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    except Exception:
        pass
    app.setPalette(pal)
    app.setStyleSheet(STYLE_DARK if dark else STYLE)


def logo_ratio() -> float:
    """Alto / ancho del logo horizontal (para colocarlo en los reportes)."""
    try:
        from PIL import Image
        w, h = Image.open(LOGO()).size
        return h / float(w)
    except Exception:
        return 0.274


def logo_pixmap(dark=False, width=250):
    """Logo para el fondo actual (el del tema oscuro lleva el texto claro)."""
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtCore import Qt
    img = QImage(LOGO_DARK() if dark else LOGO())
    if img.isNull():
        return QPixmap()
    return QPixmap.fromImage(img.scaledToWidth(width, Qt.SmoothTransformation))


# colores de las hojas de estilo en linea (claro -> oscuro): textos azules/grises y el panel de ayuda
DARK_MAP = {"#f4f7fb": "#1d252e", "#c8d6e8": "#3a4452", "#24405f": "#c3d4ea", "#1f3864": "#9fc3f0",
            "#595959": "#aab2bb", "#9c0006": "#ff8a8a", "#08306b": "#9fc3f0", "#444444": "#aab2bb"}


def retheme(root, dark):
    """Reescribe los colores de las hojas de estilo en linea del arbol de widgets para el tema oscuro (y los
    restituye en el claro)."""
    from PySide6.QtWidgets import QWidget
    for w in [root] + root.findChildren(QWidget):
        ss = w.styleSheet()
        if not ss and w.property("_ss0") is None:
            continue
        orig = w.property("_ss0")
        if orig is None:
            if not any(k in ss for k in DARK_MAP):
                continue
            orig = ss
            w.setProperty("_ss0", orig)
        new = orig
        if dark:
            for a, b in DARK_MAP.items():
                new = new.replace(a, b)
        if new != ss:
            w.setStyleSheet(new)
