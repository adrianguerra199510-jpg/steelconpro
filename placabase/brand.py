# -*- coding: utf-8 -*-
"""Identidad visual de PlacaBasePro: ruta de los recursos graficos y colores de marca."""
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
    """Ruta de un recurso de placabase/data (tambien dentro del ejecutable de PyInstaller)."""
    for base in (Path(__file__).parent / "data", Path(getattr(sys, "_MEIPASS", ".")) / "placabase" / "data"):
        p = base / name
        if p.exists():
            return str(p)
    return str(Path(__file__).parent / "data" / name)


LOGO = lambda: asset("logo.png")          # logo horizontal con lema (fondo transparente)
ICON = lambda: asset("icon.png")          # icono cuadrado 256 px
ICO = lambda: asset("placabasepro.ico")   # icono de Windows (.ico multi-tamano)

STYLE = f"""
QToolBar {{ background: {GREY}; border-bottom: 2px solid {ORANGE}; spacing: 4px; padding: 2px; }}
QTabBar::tab {{ padding: 5px 12px; }}
QTabBar::tab:selected {{ border-bottom: 3px solid {ORANGE}; font-weight: bold; color: {DARK}; }}
QGroupBox {{ font-weight: bold; color: {DARK}; }}
QHeaderView::section {{ background: {GREY}; color: {DARK}; border: 0; border-bottom: 1px solid #c9ccc6; padding: 3px; }}
QStatusBar {{ background: {GREY}; color: {DARK}; border-top: 1px solid #c9ccc6; }}
QStatusBar::item {{ border: 0; }}
QPushButton:hover {{ border-color: {ORANGE}; }}
"""


STYLE_DARK = f"""
QToolBar {{ background: #1b222b; border-bottom: 2px solid {ORANGE}; spacing: 4px; padding: 2px; }}
QTabBar::tab {{ padding: 5px 12px; }}
QTabBar::tab:selected {{ border-bottom: 3px solid {ORANGE}; font-weight: bold; color: #ffffff; }}
QGroupBox {{ font-weight: bold; color: #e6e8ea; }}
QHeaderView::section {{ background: #1b222b; color: #e6e8ea; border: 0; border-bottom: 1px solid #3a4452; padding: 3px; }}
QStatusBar {{ background: #1b222b; color: #e6e8ea; border-top: 1px solid #3a4452; }}
QStatusBar::item {{ border: 0; }}
QPushButton:hover {{ border-color: {ORANGE}; }}
"""


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
        c = dict(Window="#f0f0f0", WindowText="#12171e", Base="#ffffff", AlternateBase="#f5f5f5",
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


def logo_pixmap(dark=False, width=250):
    """Logo para el fondo actual: en el tema oscuro, los tonos oscuros y neutros (texto y caja) pasan a claro y el
    naranja de marca se conserva."""
    import numpy as np
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtCore import Qt
    img = QImage(LOGO())
    if img.isNull():
        return QPixmap()
    img = img.scaledToWidth(width, Qt.SmoothTransformation).convertToFormat(QImage.Format_RGBA8888)
    if dark:
        w, h = img.width(), img.height()
        a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4).astype(np.float32).copy()
        rgb = a[:, :, :3] / 255.0
        mx, mn = rgb.max(axis=2), rgb.min(axis=2)
        lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
        chroma = mx - mn
        wgt = np.clip((0.62 - lum) / 0.30, 0, 1) * np.clip((0.30 - chroma) / 0.15, 0, 1)
        light = np.array([0.95, 0.96, 0.97], np.float32)
        out = rgb * (1 - wgt[..., None]) + light * wgt[..., None]
        a[:, :, :3] = out * 255.0
        data = np.ascontiguousarray(a.astype(np.uint8))
        img = QImage(data.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(img)


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
