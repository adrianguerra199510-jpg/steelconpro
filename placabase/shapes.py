# -*- coding: utf-8 -*-
"""
Catalogo de perfiles.

ATENCION: la tabla integrada es un SUBCONJUNTO de la AISC Shapes Database
v14.1 con los perfiles de uso mas frecuente en placas base.  Las dimensiones
estan en pulgadas y provienen de la Parte 1 del Manual AISC 14a Ed.

Para trabajar con el catalogo COMPLETO y con valores verificados, use el
menu  Archivo > Importar base de datos AISC...  y seleccione el archivo
oficial  aisc-shapes-database-v14.1.xlsx  (o su exportacion a CSV).  El
importador reconoce las columnas nativas de ese archivo:

    Type, AISC_Manual_Label, d, bf, tf, tw, A, Ix, Zx, Sx, Iy, Zy, Sy,
    Ht, B, tnom, tdes, OD, kdes

Los perfiles importados quedan guardados en   %APPDATA%/PlacaBasePro/shapes.json
y tienen prioridad sobre la tabla integrada.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import math
import os

W_SHAPE, HSS_RECT, HSS_ROUND, PIPE = "W", "HSS-R", "HSS-C", "PIPE"
CHANNEL, ANGLE, TEE, PLATE = "C", "L", "T", "PL"
# tipos que se describen como rectangulos (todo salvo los redondos)
RECT_KINDS = (W_SHAPE, HSS_RECT, CHANNEL, ANGLE, TEE, PLATE)
# tipos que el calculo trata de forma "generica" (grupo de soldadura, sin
# rigidizadores de ala/alma)
GENERIC_KINDS = (CHANNEL, ANGLE, TEE, PLATE)
KIND_LABELS = {W_SHAPE: "Perfil I (W, M, S, HP)", CHANNEL: "Canal (C, MC)",
               ANGLE: "Angulo (L)", TEE: "Te (WT, MT, ST)",
               HSS_RECT: "HSS rectangular / cuadrado", HSS_ROUND: "HSS circular",
               PIPE: "Tuberia (Pipe)", PLATE: "Pletina / placa (PL)"}


@dataclass
class Shape:
    label: str
    kind: str                # W_SHAPE | HSS_RECT | HSS_ROUND | PIPE
    d: float = 0.0           # peralte (W) / Ht (HSS rect) / OD (redondo)
    bf: float = 0.0          # ancho de ala (W) / B (HSS rect) / = OD (redondo)
    tf: float = 0.0          # espesor de ala (W)
    tw: float = 0.0          # espesor de alma (W) / pared de diseno (HSS)
    A: float = 0.0           # area, in^2
    Ix: float = 0.0
    Sx: float = 0.0
    Zx: float = 0.0
    Iy: float = 0.0
    Sy: float = 0.0
    Zy: float = 0.0
    kdes: float = 0.0
    source: str = "integrado"
    family: str = ""
    aw: float = 0.0          # area de cortante impuesta (secciones dobles)

    # --------------------------------------------------- geometria por rectangulos
    def rects(self):
        """Rectangulos (x0, y0, x1, y1) que forman la seccion, con el centroide en
        el origen, d a lo largo de Y y bf a lo largo de X.  None si es redonda."""
        d, bf, tf, tw = self.d, self.bf, self.tf, self.tw
        k = self.kind
        if k == W_SHAPE:
            r = [(-bf / 2, d / 2 - tf, bf / 2, d / 2), (-bf / 2, -d / 2, bf / 2, -d / 2 + tf),
                 (-tw / 2, -d / 2 + tf, tw / 2, d / 2 - tf)]
        elif k == HSS_RECT:
            t = tw
            r = [(-bf / 2, d / 2 - t, bf / 2, d / 2), (-bf / 2, -d / 2, bf / 2, -d / 2 + t),
                 (-bf / 2, -d / 2 + t, -bf / 2 + t, d / 2 - t),
                 (bf / 2 - t, -d / 2 + t, bf / 2, d / 2 - t)]
        elif k == CHANNEL:
            r = [(0.0, -d / 2, tw, d / 2), (tw, d / 2 - tf, bf, d / 2),
                 (tw, -d / 2, bf, -d / 2 + tf)]
        elif k == ANGLE:
            t = tw
            r = [(0.0, 0.0, t, d), (t, 0.0, bf, t)]
        elif k == TEE:
            r = [(-bf / 2, d - tf, bf / 2, d), (-tw / 2, 0.0, tw / 2, d - tf)]
        elif k == PLATE:
            r = [(-bf / 2, -d / 2, bf / 2, d / 2)]
        else:
            return None
        cx, cy = rect_centroid(r)
        return [(a - cx, b - cy, c - cx, e - cy) for a, b, c, e in r]

    @property
    def generic(self) -> bool:
        return self.kind in GENERIC_KINDS

    # --------------------------------------------------- propiedades utiles
    @property
    def is_round(self) -> bool:
        return self.kind in (HSS_ROUND, PIPE)

    @property
    def is_hollow(self) -> bool:
        return self.kind in (HSS_RECT, HSS_ROUND, PIPE)

    @property
    def bbox(self):
        """(ancho en X local, alto en Y local) del perfil sin rotar."""
        if self.is_round:
            return self.d, self.d
        return self.bf, self.d

    @property
    def Aw(self) -> float:
        """Area de alma para cortante."""
        if self.aw > 0:
            return self.aw
        if self.kind == PLATE:
            return self.A
        if self.kind in (CHANNEL, TEE):
            return self.d * self.tw
        if self.kind == ANGLE:
            return self.d * self.tw
        if self.kind == W_SHAPE:
            return self.d * self.tw
        if self.kind == HSS_RECT:
            return 2.0 * (self.d - 2 * self.tw) * self.tw
        return 0.5 * self.A          # HSS circular: ~A/2 efectiva

    @property
    def Af(self) -> float:
        """Area de un ala (W)."""
        return self.bf * self.tf if self.kind == W_SHAPE else 0.0

    def perimeter_weld_len(self) -> float:
        """Longitud de linea de soldadura al perimetro."""
        if self.is_round:
            return math.pi * self.d
        if self.kind == HSS_RECT:
            return 2.0 * (self.d + self.bf)
        return 0.0


# ==================================================== propiedades por rectangulos
def rect_centroid(rs):
    A = sum((c - a) * (e - b) for a, b, c, e in rs)
    if A <= 0:
        return 0.0, 0.0
    return (sum((c - a) * (e - b) * (a + c) / 2 for a, b, c, e in rs) / A,
            sum((c - a) * (e - b) * (b + e) / 2 for a, b, c, e in rs) / A)


def rect_props(rs):
    """A, Ix, Iy, Sx, Sy, Zx, Zy de un conjunto de rectangulos (sin redondeos),
    respecto a su centroide."""
    A = sum((c - a) * (e - b) for a, b, c, e in rs)
    cx, cy = rect_centroid(rs)
    Ix = sum((c - a) * (e - b) ** 3 / 12 + (c - a) * (e - b) * ((b + e) / 2 - cy) ** 2
             for a, b, c, e in rs)
    Iy = sum((e - b) * (c - a) ** 3 / 12 + (c - a) * (e - b) * ((a + c) / 2 - cx) ** 2
             for a, b, c, e in rs)
    ymax = max(max(abs(b - cy), abs(e - cy)) for a, b, c, e in rs)
    xmax = max(max(abs(a - cx), abs(c - cx)) for a, b, c, e in rs)

    def plastic(axis):
        # franjas finas: eje neutro plastico = mitad del area; Z = suma |d|·dA
        strips = []
        for a, b, c, e in rs:
            lo, hi, w = (b, e, c - a) if axis == "x" else (a, c, e - b)
            n = 60
            h = (hi - lo) / n
            strips += [(lo + (i + 0.5) * h, w * h) for i in range(n)]
        strips.sort()
        acc, half, pna = 0.0, A / 2, strips[0][0]
        for pos, dA in strips:
            acc += dA
            if acc >= half:
                pna = pos
                break
        return sum(abs(pos - pna) * dA for pos, dA in strips)
    return dict(A=A, Ix=Ix, Iy=Iy, Sx=Ix / ymax if ymax else 0.0,
                Sy=Iy / xmax if xmax else 0.0, Zx=plastic("x"), Zy=plastic("y"))


def make_custom(label: str, kind: str, d: float, bf: float, tw: float, tf: float = 0.0):
    """Seccion definida por el usuario: propiedades calculadas de sus dimensiones
    (sin los redondeos de laminacion)."""
    if kind in (HSS_ROUND, PIPE):
        ro, ri = d / 2, d / 2 - tw
        A = math.pi * (ro ** 2 - ri ** 2)
        I = math.pi / 4 * (ro ** 4 - ri ** 4)
        Z = 4 / 3 * (ro ** 3 - ri ** 3)
        return Shape(label, kind, d, d, 0.0, tw, A, I, I / ro, Z, I, I / ro, Z, 0.0,
                     "personalizado", "Personalizado")
    if kind == ANGLE:
        tf = tw
    if kind == HSS_RECT:
        tf = 0.0
    s = Shape(label, kind, d, bf, tf, tw, 0, 0, 0, 0, 0, 0, 0, 0.0,
              "personalizado", "Personalizado")
    pr = rect_props(s.rects())
    s.A, s.Ix, s.Iy, s.Sx, s.Sy, s.Zx, s.Zy = (pr[k] for k in
                                               ("A", "Ix", "Iy", "Sx", "Sy", "Zx", "Zy"))
    return s


def _norm(label: str) -> str:
    """Nombre normalizado para reconocer etiquetas antiguas (HSS10.75X0.5,
    'Pipe 8 XS') con las de la base AISC (HSS10.750X0.500, Pipe8XS)."""
    import re
    t = label.replace(" ", "").upper()
    return re.sub(r"\d+\.\d+", lambda m: repr(float(m.group(0))), t)


# =================================================================== W (14a Ed.)
#            label        d      bf     tf     tw     A     Ix     Sx     Zx    kdes
_W = [
    ("W4X13",           4.16,  4.06, 0.345, 0.280,  3.83,  11.3,  5.46,  6.28, 0.595),
    ("W5X16",           5.01,  5.00, 0.360, 0.240,  4.68,  21.3,  8.51,  9.63, 0.640),
    ("W5X19",           5.15,  5.03, 0.430, 0.270,  5.56,  26.2, 10.20, 11.60, 0.710),
    ("W6X9",            5.90,  3.94, 0.215, 0.170,  2.68,  16.4,  5.56,  6.23, 0.465),
    ("W6X12",           6.03,  4.00, 0.280, 0.230,  3.55,  22.1,  7.31,  8.30, 0.530),
    ("W6X15",           5.99,  5.99, 0.260, 0.230,  4.43,  29.1,  9.72, 10.80, 0.510),
    ("W6X16",           6.28,  4.03, 0.405, 0.260,  4.74,  32.1, 10.20, 11.70, 0.655),
    ("W6X20",           6.20,  6.02, 0.365, 0.260,  5.87,  41.4, 13.40, 14.90, 0.615),
    ("W6X25",           6.38,  6.08, 0.455, 0.320,  7.34,  53.4, 16.70, 18.90, 0.705),
    ("W8X10",           7.89,  3.94, 0.205, 0.170,  2.96,  30.8,  7.81,  8.87, 0.455),
    ("W8X13",           7.99,  4.00, 0.255, 0.230,  3.84,  39.6,  9.91, 11.40, 0.505),
    ("W8X15",           8.11,  4.01, 0.315, 0.245,  4.44,  48.0, 11.80, 13.60, 0.565),
    ("W8X18",           8.14,  5.25, 0.330, 0.230,  5.26,  61.9, 15.20, 17.00, 0.580),
    ("W8X21",           8.28,  5.27, 0.400, 0.250,  6.16,  75.3, 18.20, 20.40, 0.650),
    ("W8X24",           7.93,  6.50, 0.400, 0.245,  7.08,  82.7, 20.90, 23.10, 0.650),
    ("W8X28",           8.06,  6.54, 0.465, 0.285,  8.25,  98.0, 24.30, 27.20, 0.715),
    ("W8X31",           8.00,  8.00, 0.435, 0.285,  9.13, 110.0, 27.50, 30.40, 0.700),
    ("W8X35",           8.12,  8.02, 0.495, 0.310, 10.30, 127.0, 31.20, 34.70, 0.760),
    ("W8X40",           8.25,  8.07, 0.560, 0.360, 11.70, 146.0, 35.50, 39.80, 0.825),
    ("W8X48",           8.50,  8.11, 0.685, 0.400, 14.10, 184.0, 43.20, 49.00, 0.950),
    ("W8X58",           8.75,  8.22, 0.810, 0.510, 17.10, 228.0, 52.00, 59.80, 1.080),
    ("W8X67",           9.00,  8.28, 0.935, 0.570, 19.70, 272.0, 60.40, 70.10, 1.200),
    ("W10X12",          9.87,  3.96, 0.210, 0.190,  3.54,  53.8, 10.90, 12.60, 0.460),
    ("W10X15",          9.99,  4.00, 0.270, 0.230,  4.41,  68.9, 13.80, 16.00, 0.520),
    ("W10X17",         10.10,  4.01, 0.330, 0.240,  4.99,  81.9, 16.20, 18.70, 0.580),
    ("W10X19",         10.20,  4.02, 0.395, 0.250,  5.62,  96.3, 18.80, 21.60, 0.645),
    ("W10X22",         10.20,  5.75, 0.360, 0.240,  6.49, 118.0, 23.20, 26.00, 0.610),
    ("W10X26",         10.30,  5.77, 0.440, 0.260,  7.61, 144.0, 27.90, 31.30, 0.690),
    ("W10X30",         10.50,  5.81, 0.510, 0.300,  8.84, 170.0, 32.40, 36.60, 0.760),
    ("W10X33",          9.73,  7.96, 0.435, 0.290,  9.71, 171.0, 35.00, 38.80, 0.935),
    ("W10X39",          9.92,  7.99, 0.530, 0.315, 11.50, 209.0, 42.10, 46.80, 1.030),
    ("W10X45",         10.10,  8.02, 0.620, 0.350, 13.30, 248.0, 49.10, 54.90, 1.120),
    ("W10X49",          9.98, 10.00, 0.560, 0.340, 14.40, 272.0, 54.60, 60.40, 1.060),
    ("W10X54",         10.10, 10.00, 0.615, 0.370, 15.80, 303.0, 60.00, 66.60, 1.120),
    ("W10X60",         10.20, 10.10, 0.680, 0.420, 17.70, 341.0, 66.70, 74.60, 1.180),
    ("W10X68",         10.40, 10.10, 0.770, 0.470, 19.90, 394.0, 75.70, 85.30, 1.270),
    ("W10X77",         10.60, 10.20, 0.870, 0.530, 22.60, 455.0, 85.90, 97.60, 1.370),
    ("W10X88",         10.80, 10.30, 0.990, 0.605, 26.00, 534.0, 98.50,113.00, 1.490),
    ("W10X100",        11.10, 10.30, 1.120, 0.680, 29.30, 623.0,112.00,130.00, 1.620),
    ("W10X112",        11.40, 10.40, 1.250, 0.755, 32.90, 716.0,126.00,147.00, 1.750),
    ("W12X14",         11.90,  3.97, 0.225, 0.200,  4.16,  88.6, 14.90, 17.40, 0.475),
    ("W12X16",         12.00,  3.99, 0.265, 0.220,  4.71, 103.0, 17.10, 20.10, 0.515),
    ("W12X19",         12.20,  4.01, 0.350, 0.235,  5.57, 130.0, 21.30, 24.70, 0.600),
    ("W12X22",         12.30,  4.03, 0.425, 0.260,  6.48, 156.0, 25.40, 29.30, 0.680),
    ("W12X26",         12.20,  6.49, 0.380, 0.230,  7.65, 204.0, 33.40, 37.20, 0.680),
    ("W12X30",         12.30,  6.52, 0.440, 0.260,  8.79, 238.0, 38.60, 43.10, 0.740),
    ("W12X35",         12.50,  6.56, 0.520, 0.300, 10.30, 285.0, 45.60, 51.20, 0.820),
    ("W12X40",         11.90,  8.01, 0.515, 0.295, 11.70, 307.0, 51.50, 57.00, 0.995),
    ("W12X45",         12.10,  8.05, 0.575, 0.335, 13.10, 348.0, 57.70, 64.20, 1.055),
    ("W12X50",         12.20,  8.08, 0.640, 0.370, 14.60, 391.0, 64.20, 71.90, 1.120),
    ("W12X53",         12.10, 10.00, 0.575, 0.345, 15.60, 425.0, 70.60, 77.90, 1.060),
    ("W12X58",         12.20, 10.00, 0.640, 0.360, 17.00, 475.0, 78.00, 86.40, 1.120),
    ("W12X65",         12.10, 12.00, 0.605, 0.390, 19.10, 533.0, 87.90, 96.80, 1.200),
    ("W12X72",         12.30, 12.00, 0.670, 0.430, 21.10, 597.0, 97.40,108.00, 1.270),
    ("W12X79",         12.40, 12.10, 0.735, 0.470, 23.20, 662.0,107.00,119.00, 1.330),
    ("W12X87",         12.50, 12.10, 0.810, 0.515, 25.60, 740.0,118.00,132.00, 1.410),
    ("W12X96",         12.70, 12.20, 0.900, 0.550, 28.20, 833.0,131.00,147.00, 1.500),
    ("W12X106",        12.90, 12.20, 0.990, 0.610, 31.20, 933.0,145.00,164.00, 1.590),
    ("W12X120",        13.10, 12.30, 1.105, 0.710, 35.30,1070.0,163.00,186.00, 1.700),
    ("W12X136",        13.40, 12.40, 1.250, 0.790, 39.90,1240.0,186.00,214.00, 1.850),
    ("W12X152",        13.70, 12.50, 1.400, 0.870, 44.70,1430.0,209.00,243.00, 2.000),
    ("W12X170",        14.00, 12.60, 1.560, 0.960, 50.00,1650.0,235.00,275.00, 2.160),
    ("W12X190",        14.40, 12.70, 1.735, 1.060, 56.00,1890.0,263.00,311.00, 2.330),
    ("W12X210",        14.70, 12.80, 1.900, 1.180, 61.80,2140.0,292.00,348.00, 2.500),
    ("W12X230",        15.10, 13.00, 2.070, 1.290, 67.70,2420.0,321.00,386.00, 2.670),
    ("W12X252",        15.40, 13.20, 2.250, 1.400, 74.00,2720.0,353.00,428.00, 2.850),
    ("W12X279",        15.90, 13.10, 2.470, 1.530, 81.90,3110.0,393.00,481.00, 3.070),
    ("W12X305",        16.30, 13.20, 2.710, 1.630, 89.60,3550.0,435.00,537.00, 3.310),
    ("W12X336",        16.80, 13.40, 2.955, 1.775, 98.90,4060.0,483.00,603.00, 3.550),
    ("W14X22",         13.70,  5.00, 0.335, 0.230,  6.49, 199.0, 29.00, 33.20, 0.735),
    ("W14X26",         13.90,  5.03, 0.420, 0.255,  7.69, 245.0, 35.30, 40.20, 0.820),
    ("W14X30",         13.80,  6.73, 0.385, 0.270,  8.85, 291.0, 42.00, 47.30, 0.785),
    ("W14X34",         14.00,  6.75, 0.455, 0.285, 10.00, 340.0, 48.60, 54.60, 0.855),
    ("W14X38",         14.10,  6.77, 0.515, 0.310, 11.20, 385.0, 54.60, 61.50, 0.915),
    ("W14X43",         13.70,  8.00, 0.530, 0.305, 12.60, 428.0, 62.60, 69.60, 0.965),
    ("W14X48",         13.80,  8.03, 0.595, 0.340, 14.10, 484.0, 70.20, 78.40, 1.030),
    ("W14X53",         13.90,  8.06, 0.660, 0.370, 15.60, 541.0, 77.80, 87.10, 1.095),
    ("W14X61",         13.90, 10.00, 0.645, 0.375, 17.90, 640.0, 92.10,102.00, 1.080),
    ("W14X68",         14.00, 10.00, 0.720, 0.415, 20.00, 722.0,103.00,115.00, 1.155),
    ("W14X74",         14.20, 10.10, 0.785, 0.450, 21.80, 795.0,112.00,126.00, 1.220),
    ("W14X82",         14.30, 10.10, 0.855, 0.510, 24.00, 881.0,123.00,139.00, 1.290),
    ("W14X90",         14.00, 14.50, 0.710, 0.440, 26.50, 999.0,143.00,157.00, 1.310),
    ("W14X99",         14.20, 14.60, 0.780, 0.485, 29.10,1110.0,157.00,173.00, 1.380),
    ("W14X109",        14.30, 14.60, 0.860, 0.525, 32.00,1240.0,173.00,192.00, 1.460),
    ("W14X120",        14.50, 14.70, 0.940, 0.590, 35.30,1380.0,190.00,212.00, 1.540),
    ("W14X132",        14.70, 14.70, 1.030, 0.645, 38.80,1530.0,209.00,234.00, 1.630),
    ("W14X145",        14.80, 15.50, 1.090, 0.680, 42.70,1710.0,232.00,260.00, 1.690),
    ("W14X159",        15.00, 15.60, 1.190, 0.745, 46.70,1900.0,254.00,287.00, 1.790),
    ("W14X176",        15.20, 15.70, 1.310, 0.830, 51.80,2140.0,281.00,320.00, 1.910),
    ("W14X193",        15.50, 15.70, 1.440, 0.890, 56.80,2400.0,310.00,355.00, 2.040),
    ("W14X211",        15.70, 15.80, 1.560, 0.980, 62.00,2660.0,338.00,390.00, 2.160),
    ("W14X233",        16.00, 15.90, 1.720, 1.070, 68.50,3010.0,375.00,436.00, 2.320),
    ("W14X257",        16.40, 16.00, 1.890, 1.175, 75.60,3400.0,415.00,487.00, 2.490),
    ("W14X283",        16.70, 16.10, 2.070, 1.290, 83.30,3840.0,459.00,542.00, 2.670),
    ("W14X311",        17.10, 16.20, 2.260, 1.410, 91.40,4330.0,506.00,603.00, 2.860),
    ("W14X342",        17.50, 16.40, 2.470, 1.540,101.00,4900.0,559.00,672.00, 3.070),
    ("W14X370",        17.90, 16.50, 2.660, 1.660,109.00,5440.0,607.00,736.00, 3.260),
    ("W14X398",        18.30, 16.60, 2.845, 1.770,117.00,6000.0,656.00,801.00, 3.440),
    ("W14X426",        18.70, 16.70, 3.035, 1.875,125.00,6600.0,706.00,869.00, 3.630),
    ("W14X455",        19.00, 16.80, 3.210, 2.015,134.00,7190.0,756.00,936.00, 3.810),
    ("W14X500",        19.60, 17.00, 3.500, 2.190,147.00,8210.0,838.00,1050.0, 4.100),
    ("W14X550",        20.20, 17.20, 3.820, 2.380,162.00,9430.0,931.00,1180.0, 4.420),
    ("W14X605",        20.90, 17.40, 4.160, 2.595,178.00,10800.,1040.0,1320.0, 4.760),
    ("W14X665",        21.60, 17.70, 4.520, 2.830,196.00,12400.,1150.0,1480.0, 5.120),
    ("W14X730",        22.40, 17.90, 4.910, 3.070,215.00,14300.,1280.0,1660.0, 5.510),
    ("W16X26",         15.70,  5.50, 0.345, 0.250,  7.68, 301.0, 38.40, 44.20, 0.747),
    ("W16X31",         15.90,  5.53, 0.440, 0.275,  9.13, 375.0, 47.20, 54.00, 0.842),
    ("W16X36",         15.90,  6.99, 0.430, 0.295, 10.60, 448.0, 56.50, 64.00, 0.832),
    ("W16X40",         16.00,  7.00, 0.505, 0.305, 11.80, 518.0, 64.70, 73.00, 0.907),
    ("W16X45",         16.10,  7.04, 0.565, 0.345, 13.30, 586.0, 72.70, 82.30, 0.967),
    ("W16X50",         16.30,  7.07, 0.630, 0.380, 14.70, 659.0, 81.00, 92.00, 1.030),
    ("W16X57",         16.40,  7.12, 0.715, 0.430, 16.80, 758.0, 92.20,105.00, 1.120),
    ("W16X67",         16.30, 10.20, 0.665, 0.395, 19.60, 954.0,117.00,130.00, 1.090),
    ("W16X77",         16.50, 10.30, 0.760, 0.455, 22.60,1110.0,134.00,150.00, 1.190),
    ("W16X89",         16.80, 10.40, 0.875, 0.525, 26.20,1300.0,155.00,175.00, 1.300),
    ("W16X100",        17.00, 10.40, 0.985, 0.585, 29.50,1490.0,175.00,198.00, 1.410),
    ("W18X35",         17.70,  6.00, 0.425, 0.300, 10.30, 510.0, 57.60, 66.50, 0.827),
    ("W18X40",         17.90,  6.02, 0.525, 0.315, 11.80, 612.0, 68.40, 78.40, 0.927),
    ("W18X46",         18.10,  6.06, 0.605, 0.360, 13.50, 712.0, 78.80, 90.70, 1.010),
    ("W18X50",         18.00,  7.50, 0.570, 0.355, 14.70, 800.0, 88.90,101.00, 0.972),
    ("W18X55",         18.10,  7.53, 0.630, 0.390, 16.20, 890.0, 98.30,112.00, 1.030),
    ("W18X60",         18.20,  7.56, 0.695, 0.415, 17.60, 984.0,108.00,123.00, 1.100),
    ("W18X65",         18.40,  7.59, 0.750, 0.450, 19.10,1070.0,117.00,133.00, 1.150),
    ("W18X71",         18.50,  7.64, 0.810, 0.495, 20.80,1170.0,127.00,146.00, 1.210),
    ("W18X76",         18.20, 11.00, 0.680, 0.425, 22.30,1330.0,146.00,163.00, 1.180),
    ("W18X86",         18.40, 11.10, 0.770, 0.480, 25.30,1530.0,166.00,186.00, 1.270),
    ("W18X97",         18.60, 11.10, 0.870, 0.535, 28.50,1750.0,188.00,211.00, 1.370),
    ("W18X106",        18.70, 11.20, 0.940, 0.590, 31.10,1910.0,204.00,230.00, 1.440),
    ("W18X119",        19.00, 11.30, 1.060, 0.655, 35.10,2190.0,231.00,262.00, 1.560),
    ("W21X44",         20.70,  6.50, 0.450, 0.350, 13.00, 843.0, 81.60, 95.40, 0.950),
    ("W21X50",         20.80,  6.53, 0.535, 0.380, 14.70, 984.0, 94.50,110.00, 1.040),
    ("W21X57",         21.10,  6.56, 0.650, 0.405, 16.70,1170.0,111.00,129.00, 1.150),
    ("W21X62",         21.00,  8.24, 0.615, 0.400, 18.30,1330.0,127.00,144.00, 1.120),
    ("W21X68",         21.10,  8.27, 0.685, 0.430, 20.00,1480.0,140.00,160.00, 1.190),
    ("W21X73",         21.20,  8.30, 0.740, 0.455, 21.50,1600.0,151.00,172.00, 1.240),
    ("W21X83",         21.40,  8.36, 0.835, 0.515, 24.30,1830.0,171.00,196.00, 1.340),
    ("W21X93",         21.60,  8.42, 0.930, 0.580, 27.30,2070.0,192.00,221.00, 1.430),
    ("W21X101",        21.40, 12.30, 0.800, 0.500, 29.80,2420.0,227.00,253.00, 1.300),
    ("W21X111",        21.50, 12.30, 0.875, 0.550, 32.70,2670.0,249.00,279.00, 1.380),
    ("W21X122",        21.70, 12.40, 0.960, 0.600, 35.90,2960.0,273.00,307.00, 1.460),
    ("W21X147",        22.10, 12.50, 1.150, 0.720, 43.20,3630.0,329.00,373.00, 1.650),
    ("W24X55",         23.60,  7.01, 0.505, 0.395, 16.20,1350.0,114.00,134.00, 1.010),
    ("W24X62",         23.70,  7.04, 0.590, 0.430, 18.20,1550.0,131.00,153.00, 1.090),
    ("W24X68",         23.70,  8.97, 0.585, 0.415, 20.10,1830.0,154.00,177.00, 1.090),
    ("W24X76",         23.90,  8.99, 0.680, 0.440, 22.40,2100.0,176.00,200.00, 1.180),
    ("W24X84",         24.10,  9.02, 0.770, 0.470, 24.70,2370.0,196.00,224.00, 1.270),
    ("W24X94",         24.30,  9.07, 0.875, 0.515, 27.70,2700.0,222.00,254.00, 1.380),
    ("W24X104",        24.10, 12.80, 0.750, 0.500, 30.60,3100.0,258.00,289.00, 1.250),
    ("W24X117",        24.30, 12.80, 0.850, 0.550, 34.40,3540.0,291.00,327.00, 1.350),
    ("W24X131",        24.50, 12.90, 0.960, 0.605, 38.60,4020.0,329.00,370.00, 1.460),
    ("W24X146",        24.70, 12.90, 1.090, 0.650, 43.00,4580.0,371.00,418.00, 1.590),
    ("W24X162",        25.00, 13.00, 1.220, 0.705, 47.70,5170.0,414.00,468.00, 1.720),
]

# ======================================================== HSS cuadrado / rect.
#   (Ht, B, tnom)  ->  tdes = 0.93*tnom  (ASTM A500 soldado por resistencia)
_HSS_R = [
    (4, 4, "1/4"), (4, 4, "5/16"), (4, 4, "3/8"), (4, 4, "1/2"),
    (5, 5, "1/4"), (5, 5, "5/16"), (5, 5, "3/8"), (5, 5, "1/2"),
    (6, 6, "1/4"), (6, 6, "5/16"), (6, 6, "3/8"), (6, 6, "1/2"), (6, 6, "5/8"),
    (7, 7, "1/4"), (7, 7, "3/8"), (7, 7, "1/2"), (7, 7, "5/8"),
    (8, 8, "1/4"), (8, 8, "5/16"), (8, 8, "3/8"), (8, 8, "1/2"), (8, 8, "5/8"),
    (9, 9, "3/8"), (9, 9, "1/2"), (9, 9, "5/8"),
    (10, 10, "1/4"), (10, 10, "3/8"), (10, 10, "1/2"), (10, 10, "5/8"), (10, 10, "3/4"),
    (12, 12, "3/8"), (12, 12, "1/2"), (12, 12, "5/8"), (12, 12, "3/4"),
    (14, 14, "1/2"), (14, 14, "5/8"), (14, 14, "3/4"),
    (16, 16, "1/2"), (16, 16, "5/8"), (16, 16, "3/4"),
    (18, 18, "1/2"), (18, 18, "5/8"), (18, 18, "3/4"),
    (20, 20, "1/2"), (20, 20, "5/8"), (20, 20, "3/4"),
    (6, 4, "3/8"), (6, 4, "1/2"),
    (8, 4, "3/8"), (8, 4, "1/2"),
    (8, 6, "3/8"), (8, 6, "1/2"),
    (10, 6, "3/8"), (10, 6, "1/2"),
    (12, 6, "1/2"), (12, 8, "1/2"), (12, 8, "5/8"),
    (14, 10, "1/2"), (16, 8, "1/2"), (16, 12, "1/2"), (20, 12, "1/2"),
]

# ============================================================ HSS circular
_HSS_C = [
    (4.500, 0.237), (5.000, 0.258), (5.563, 0.258), (6.625, 0.280),
    (6.625, 0.375), (8.625, 0.322), (8.625, 0.500), (10.000, 0.375),
    (10.750, 0.365), (10.750, 0.500), (12.750, 0.375), (12.750, 0.500),
    (14.000, 0.375), (14.000, 0.500), (16.000, 0.438), (16.000, 0.500),
    (16.000, 0.625), (18.000, 0.500), (20.000, 0.500), (20.000, 0.625),
    (24.000, 0.500), (24.000, 0.625),
]

# ================================================================== PIPE
#   (NPS, OD, t_nom)  STD / XS
_PIPE = [
    ("Pipe 3 STD", 3.500, 0.216), ("Pipe 3 XS", 3.500, 0.300),
    ("Pipe 4 STD", 4.500, 0.237), ("Pipe 4 XS", 4.500, 0.337),
    ("Pipe 5 STD", 5.563, 0.258), ("Pipe 5 XS", 5.563, 0.375),
    ("Pipe 6 STD", 6.625, 0.280), ("Pipe 6 XS", 6.625, 0.432),
    ("Pipe 8 STD", 8.625, 0.322), ("Pipe 8 XS", 8.625, 0.500),
    ("Pipe 10 STD", 10.750, 0.365), ("Pipe 10 XS", 10.750, 0.500),
    ("Pipe 12 STD", 12.750, 0.375), ("Pipe 12 XS", 12.750, 0.500),
]


def _build_builtin() -> dict[str, Shape]:
    from .units import frac_to_float
    out: dict[str, Shape] = {}
    for lab, d, bf, tf, tw, A, Ix, Sx, Zx, kd in _W:
        Iy = bf ** 3 * tf / 6.0 + (d - 2 * tf) * tw ** 3 / 12.0
        out[lab] = Shape(lab, W_SHAPE, d, bf, tf, tw, A, Ix, Sx, Zx,
                         Iy, 2 * Iy / bf, 0.0, kd)
    for Ht, B, tn in _HSS_R:
        tnom = frac_to_float(tn)
        t = 0.93 * tnom
        lab = f"HSS{Ht:g}X{B:g}X{tn}"
        A = 2 * t * ((Ht - 2 * t) + (B - 2 * t)) + 4 * (math.pi * t ** 2 / 4 +
                                                        (2 * t) ** 2 - math.pi * (2 * t) ** 2 / 4) * 0
        A = Ht * B - (Ht - 2 * t) * (B - 2 * t)
        Ix = (B * Ht ** 3 - (B - 2 * t) * (Ht - 2 * t) ** 3) / 12.0
        Iy = (Ht * B ** 3 - (Ht - 2 * t) * (B - 2 * t) ** 3) / 12.0
        out[lab] = Shape(lab, HSS_RECT, Ht, B, 0.0, t, A, Ix, 2 * Ix / Ht,
                         2.2 * Ix / Ht, Iy, 2 * Iy / B, 0.0, 0.0)
    for OD, tn in _HSS_C:
        t = 0.93 * tn
        lab = f"HSS{OD:.3f}X{tn:.3f}".rstrip("0").rstrip(".")
        lab = f"HSS{OD:g}X{tn:g}"
        ri = OD / 2 - t
        A = math.pi * ((OD / 2) ** 2 - ri ** 2)
        I = math.pi / 4 * ((OD / 2) ** 4 - ri ** 4)
        out[lab] = Shape(lab, HSS_ROUND, OD, OD, 0.0, t, A, I, 2 * I / OD,
                         4 / 3 * ((OD / 2) ** 3 - ri ** 3), I, 2 * I / OD, 0.0, 0.0)
    for lab, OD, tn in _PIPE:
        t = 0.93 * tn
        ri = OD / 2 - t
        A = math.pi * ((OD / 2) ** 2 - ri ** 2)
        I = math.pi / 4 * ((OD / 2) ** 4 - ri ** 4)
        out[lab] = Shape(lab, PIPE, OD, OD, 0.0, t, A, I, 2 * I / OD,
                         4 / 3 * ((OD / 2) ** 3 - ri ** 3), I, 2 * I / OD, 0.0, 0.0)
    return out


BUILTIN: dict[str, Shape] = _build_builtin()


# ========================================================= catalogo activo
def _user_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    p = Path(base) / "PlacaBasePro"
    p.mkdir(parents=True, exist_ok=True)
    return p


USER_DB = _user_dir() / "shapes.json"


def _load_aisc() -> dict[str, Shape]:
    f = Path(__file__).with_name("data") / "aisc_shapes.json"
    out: dict[str, Shape] = {}
    try:
        for d in json.loads(f.read_text(encoding="utf-8"))["shapes"]:
            fam = d.pop("family")
            s = Shape(**d, source="AISC", family=fam)
            out[s.label] = s
    except Exception:
        pass
    return out


class Catalog:
    def __init__(self):
        self.shapes: dict[str, Shape] = _load_aisc() or dict(BUILTIN)
        for sh in self.shapes.values():
            if not sh.family:
                sh.family = {W_SHAPE: "W", HSS_RECT: "HSS", HSS_ROUND: "HSS circular",
                             PIPE: "Pipe"}.get(sh.kind, "")
        self.load_user()
        self._alias = {}
        self._reindex()

    def _reindex(self):
        self._alias = {_norm(k): k for k in self.shapes}

    # ------------------------------------------------------------- consulta
    def get(self, label: str) -> Shape | None:
        s = self.shapes.get(label)
        if s is None and label:
            k = self._alias.get(_norm(label))
            s = self.shapes.get(k) if k else None
        return s

    FAMILIES = ["W", "M", "S", "HP", "C", "MC", "L", "WT", "MT", "ST", "HSS",
                "HSS circular", "Pipe", "Personalizado"]

    def families(self) -> list[str]:
        have = {s.family for s in self.shapes.values()}
        return [f for f in self.FAMILIES if f in have] + sorted(have - set(self.FAMILIES) - {""})

    def by_family(self, fam: str) -> list[str]:
        def keyf(lab: str):
            s = self.shapes[lab]
            return (round(s.d, 3), round(s.bf, 3), round(s.A, 3))
        return sorted([k for k, v in self.shapes.items() if v.family == fam],
                      key=keyf, reverse=fam not in ("Personalizado",))

    def add_custom(self, s: Shape):
        s.source, s.family = "personalizado", "Personalizado"
        self.shapes[s.label] = s
        self._reindex()
        self.save_user()

    def remove(self, label: str):
        if label in self.shapes and self.shapes[label].source != "AISC":
            del self.shapes[label]
            self._reindex()
            self.save_user()

    def by_kind(self, kind: str) -> list[str]:
        def keyf(lab: str):
            s = self.shapes[lab]
            return (round(s.d, 3), round(s.bf, 3), round(s.tw, 4))
        return sorted([k for k, v in self.shapes.items() if v.kind == kind], key=keyf)

    def kinds(self) -> list[str]:
        return [W_SHAPE, HSS_RECT, HSS_ROUND, PIPE]

    # ------------------------------------------------------------ persistencia
    def load_user(self):
        if USER_DB.exists():
            try:
                data = json.loads(USER_DB.read_text(encoding="utf-8"))
                for d in data:
                    s = Shape(**d)
                    if not s.family:
                        s.family = "Personalizado" if s.source == "personalizado" else "Importado"
                    self.shapes[s.label] = s
            except Exception:
                pass

    def save_user(self, only_imported=True):
        data = [asdict(s) for s in self.shapes.values()
                if s.source not in ("integrado", "AISC")]
        USER_DB.write_text(json.dumps(data, indent=1), encoding="utf-8")

    # -------------------------------------------------------------- importar
    def import_aisc(self, path: str) -> tuple[int, str]:
        """Lee aisc-shapes-database-v14.1.xlsx / .csv y anade los perfiles.

        Devuelve (numero de perfiles, mensaje).
        """
        import pandas as pd
        p = Path(path)
        if p.suffix.lower() in (".xlsx", ".xlsm"):
            df = None
            xl = pd.ExcelFile(p)
            for sh in xl.sheet_names:
                t = xl.parse(sh)
                if "AISC_Manual_Label" in t.columns or "AISC Manual Label" in t.columns:
                    df = t
                    break
            if df is None:
                df = xl.parse(xl.sheet_names[0])
        else:
            df = pd.read_csv(p)

        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
        lab_col = "AISC_Manual_Label" if "AISC_Manual_Label" in df.columns else df.columns[1]

        def g(row, *names, default=0.0):
            for n in names:
                if n in df.columns:
                    v = row.get(n)
                    try:
                        f = float(v)
                        if f == f:      # descarta NaN
                            return f
                    except (TypeError, ValueError):
                        continue
            return default

        n = 0
        for _, row in df.iterrows():
            typ = str(row.get("Type", "")).strip().upper()
            lab = str(row.get(lab_col, "")).strip()
            if not lab or lab.lower() == "nan":
                continue
            if typ in ("W", "M", "S", "HP"):
                s = Shape(lab, W_SHAPE, g(row, "d"), g(row, "bf"), g(row, "tf"),
                          g(row, "tw"), g(row, "A"), g(row, "Ix"), g(row, "Sx"),
                          g(row, "Zx"), g(row, "Iy"), g(row, "Sy"), g(row, "Zy"),
                          g(row, "kdes"), "AISC v14.1")
            elif typ == "HSS":
                OD = g(row, "OD")
                if OD > 0:
                    t = g(row, "tdes", "tnom")
                    s = Shape(lab, HSS_ROUND, OD, OD, 0.0, t, g(row, "A"),
                              g(row, "Ix"), g(row, "Sx"), g(row, "Zx"),
                              g(row, "Iy"), g(row, "Sy"), g(row, "Zy"), 0.0, "AISC v14.1")
                else:
                    s = Shape(lab, HSS_RECT, g(row, "Ht", "H"), g(row, "B"), 0.0,
                              g(row, "tdes", "tnom"), g(row, "A"), g(row, "Ix"),
                              g(row, "Sx"), g(row, "Zx"), g(row, "Iy"),
                              g(row, "Sy"), g(row, "Zy"), 0.0, "AISC v14.1")
            elif typ in ("C", "MC"):
                s = Shape(lab, CHANNEL, g(row, "d"), g(row, "bf"), g(row, "tf"),
                          g(row, "tw"), g(row, "A"), g(row, "Ix"), g(row, "Sx"),
                          g(row, "Zx"), g(row, "Iy"), g(row, "Sy"), g(row, "Zy"),
                          g(row, "kdes"), "AISC importado", typ)
            elif typ == "L":
                t = g(row, "t")
                s = Shape(lab, ANGLE, g(row, "d"), g(row, "b"), t, t, g(row, "A"),
                          g(row, "Ix"), g(row, "Sx"), g(row, "Zx"), g(row, "Iy"),
                          g(row, "Sy"), g(row, "Zy"), g(row, "kdes"), "AISC importado", "L")
            elif typ in ("WT", "MT", "ST"):
                s = Shape(lab, TEE, g(row, "d"), g(row, "bf"), g(row, "tf"),
                          g(row, "tw"), g(row, "A"), g(row, "Ix"), g(row, "Sx"),
                          g(row, "Zx"), g(row, "Iy"), g(row, "Sy"), g(row, "Zy"),
                          g(row, "kdes"), "AISC importado", typ)
            elif typ == "PIPE":
                OD = g(row, "OD")
                s = Shape(lab, PIPE, OD, OD, 0.0, g(row, "tdes", "tnom"), g(row, "A"),
                          g(row, "Ix"), g(row, "Sx"), g(row, "Zx"), g(row, "Iy"),
                          g(row, "Sy"), g(row, "Zy"), 0.0, "AISC v14.1")
            else:
                continue
            if s.d > 0:
                self.shapes[s.label] = s
                n += 1
        for sh in self.shapes.values():
            if not sh.family:
                sh.family = {W_SHAPE: "W", HSS_RECT: "HSS", HSS_ROUND: "HSS circular",
                             PIPE: "Pipe"}.get(sh.kind, "Importado")
        self._reindex()
        self.save_user()
        return n, f"{n} perfiles importados de {p.name}"


CATALOG = Catalog()
