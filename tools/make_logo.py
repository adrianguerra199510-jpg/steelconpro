# -*- coding: utf-8 -*-
"""Genera el logo de SteelConPro (logo horizontal con lema, icono cuadrado y .ico; todos con fondo transparente).

    python tools/make_logo.py            -> escribe steelconpro/data/logo.png, logo_dark.png (para el tema oscuro), icon.png y steelconpro.ico

Necesita Pillow y la tipografia Inter (https://rsms.me/inter/, licencia OFL); sin ella usa DejaVu Sans, que viene con matplotlib.
La marca: una viga I (en elevacion) que llega a una columna con la placa de corte y tres pernos."""
from __future__ import annotations
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DARK = (18, 23, 30)            # negro azulado
ORANGE = (232, 93, 12)
ORANGE_DK = (178, 66, 4)
LIGHT = (243, 244, 241)
STEEL = (200, 206, 212)
SLATE = (74, 85, 99)

OUT = Path(__file__).resolve().parent.parent / "steelconpro" / "data"
SS = 4                          # supersampling


def font(bold: str, size: int):
    cands = {"black": ["/usr/share/fonts/opentype/inter/Inter-Black.otf", "C:/Windows/Fonts/segoeuib.ttf"],
             "bold": ["/usr/share/fonts/opentype/inter/Inter-Bold.otf", "C:/Windows/Fonts/segoeuib.ttf"],
             "medium": ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", "C:/Windows/Fonts/segoeui.ttf"]}[bold]
    try:
        import matplotlib
        cands.append(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVuSans-Bold.ttf"))
    except Exception:
        pass
    for c in cands:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def mark(size: int, dark_bg: bool = False) -> Image.Image:
    """Icono cuadrado `size` px con fondo TRANSPARENTE: la union viga-columna sin recuadro.
    Para fondos claros la columna y los pernos van en grises oscuros; con `dark_bg` la columna es clara (para el tema oscuro)."""
    s = size * SS
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    u = lambda v: v * s
    col, col_edge = ((STEEL, LIGHT) if dark_bg else (SLATE, (112, 124, 138)))
    plate, bolt = (LIGHT, DARK) if dark_bg else (STEEL, DARK)
    # columna (alas y alma vistas de canto): barra con una veta en cada borde
    d.rectangle([u(0.115), u(0.115), u(0.305), u(0.885)], fill=col)
    d.rectangle([u(0.115), u(0.115), u(0.150), u(0.885)], fill=col_edge)
    d.rectangle([u(0.270), u(0.115), u(0.305), u(0.885)], fill=col_edge)
    # viga I en elevacion: alas naranja, alma mas oscura
    x0, x1 = u(0.305), u(0.905)
    d.rectangle([x0, u(0.285), x1, u(0.355)], fill=ORANGE)
    d.rectangle([x0, u(0.645), x1, u(0.715)], fill=ORANGE)
    d.rectangle([x0, u(0.355), x1, u(0.645)], fill=ORANGE_DK)
    # placa de corte y tres pernos
    d.rounded_rectangle([u(0.305), u(0.385), u(0.545), u(0.615)], radius=u(0.018), fill=plate)
    r = u(0.030)
    for cy in (0.435, 0.500, 0.565):
        cx = 0.455
        d.ellipse([u(cx) - r, u(cy) - r, u(cx) + r, u(cy) + r], fill=bolt)
    return im.resize((size, size), Image.LANCZOS)


def wordmark(height: int, dark_bg: bool = False) -> Image.Image:
    """'SteelConPro' (SteelCon oscuro, Pro naranja) y el lema; fondo transparente."""
    ink, sub = ((242, 244, 246), (170, 180, 190)) if dark_bg else (DARK, SLATE)
    h = height * SS
    f1 = font("black", int(h * 0.50))
    f2 = font("medium", int(h * 0.150))
    a, b = "SteelCon", "Pro"
    ba = f1.getbbox(a)
    bb = f1.getbbox(b)
    wa, wb = ba[2] - ba[0], bb[2] - bb[0]
    tag = "CONEXIONES DE ACERO"
    sp = int(h * 0.040)                                  # espaciado entre letras del lema
    wt = sum(f2.getlength(c) + sp for c in tag) - sp
    W = int(max(wa + wb, wt) + h * 0.06)
    im = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y0 = int(h * 0.06) - ba[1]
    d.text((-ba[0], y0), a, font=f1, fill=ink)
    d.text((wa - bb[0] - ba[0] + int(h * 0.005), y0), b, font=f1, fill=ORANGE)
    x = 0.0
    yt = int(h * 0.60)
    for c in tag:
        d.text((x, yt), c, font=f2, fill=sub)
        x += f2.getlength(c) + sp
    return im.crop(im.getbbox())


def logo(height: int = 250, dark_bg: bool = False) -> Image.Image:
    """Logo horizontal: marca + palabra."""
    m = mark(height, dark_bg=dark_bg)
    w = wordmark(int(height * 0.80), dark_bg)
    w = w.resize((int(w.width / SS), int(w.height / SS)), Image.LANCZOS)
    gap = int(height * 0.14)
    im = Image.new("RGBA", (m.width + gap + w.width + 4, height), (0, 0, 0, 0))
    im.alpha_composite(m, (0, 0))
    im.alpha_composite(w, (m.width + gap, (height - w.height) // 2))
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    logo(250).save(OUT / "logo.png")
    logo(250, dark_bg=True).save(OUT / "logo_dark.png")
    mark(256).save(OUT / "icon.png")
    big = mark(256)
    big.save(OUT / "steelconpro.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("logo escrito en", OUT)


if __name__ == "__main__":
    main()
