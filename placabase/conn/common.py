# -*- coding: utf-8 -*-
"""Utilitarios de calculo compartidos por las tipologias de conexion (in, kip, ksi).

Los valores tabulados de AISC 360 (Tablas J3.2, J3.3, J3.4) estan transcritos del texto de la
Especificacion; verifiquelos contra la edicion vigente antes de usar el programa en un proyecto.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

from ..units import frac_to_float

PHI_BOLT = 0.75         # J3: cortante y aplastamiento de pernos
PHI_RUPT = 0.75         # J4: rotura (cortante neto, bloque de cortante, traccion neta)
PHI_YIELD = 1.00        # J4.2(a): fluencia por cortante
PHI_FLEX = 0.90         # F: fluencia por flexion
PHI_WELD = 0.75         # J2.4

# ---- AISC 360-22 Tabla J3.2: Fnv, ksi (rosca incluida "N" o excluida "X" del plano de corte)
FNV = {"A325-N": 54.0, "A325-X": 68.0, "A490-N": 68.0, "A490-X": 84.0, "A307": 27.0}

# ---- AISC 360-22 Tabla J3.4: distancia minima del centro de un agujero estandar al borde, in
_EDGE_MIN = {0.5: 0.75, 0.625: 0.875, 0.75: 1.0, 0.875: 1.125, 1.0: 1.25, 1.125: 1.5, 1.25: 1.625}


def bolt_db(label: str) -> float:
    return frac_to_float(label)


def hole_std(db: float) -> float:
    """Agujero estandar, Tabla J3.3: db + 1/16 in."""
    return db + 0.0625


def hole_net(db: float) -> float:
    """Ancho del agujero para las areas netas, J4.1 / B4.3b: agujero + 1/16 in."""
    return hole_std(db) + 0.0625


def edge_min(db: float) -> float:
    """Tabla J3.4 (agujero estandar). Para db > 1-1/4 in: 1.25·db."""
    for k in sorted(_EDGE_MIN):
        if abs(db - k) < 1e-6:
            return _EDGE_MIN[k]
    return 1.25 * db if db > 1.25 else _EDGE_MIN[min(_EDGE_MIN, key=lambda k: abs(k - db))]


def bolt_shear_rn(db: float, grade: str) -> float:
    """Resistencia nominal de un perno a cortante simple, Rn = Fnv·Ab (kip), J3.6."""
    return FNV[grade] * math.pi * db ** 2 / 4.0


def bearing_rn(db: float, t: float, Fu: float, Lc: float) -> float:
    """Aplastamiento y desgarramiento en el agujero, J3.10 (deformacion considerada): kip por perno.
    Rn = min(1.2·Lc·t·Fu , 2.4·db·t·Fu)."""
    return min(1.2 * max(Lc, 0.0) * t * Fu, 2.4 * db * t * Fu)


# =============================================================== bloque de cortante
def block_shear_rn(Fy: float, Fu: float, t: float, Lgv: float, Lnv: float, Lnt: float,
                   Ubs: float = 1.0) -> float:
    """AISC J4.3:  Rn = min(0.6·Fu·Anv + Ubs·Fu·Ant , 0.6·Fy·Agv + Ubs·Fu·Ant)."""
    Ant = t * max(Lnt, 0.0)
    return min(0.6 * Fu * t * Lnv + Ubs * Fu * Ant, 0.6 * Fy * t * Lgv + Ubs * Fu * Ant)


# ====================================================== grupo de pernos: centro instantaneo
@dataclass
class ICResult:
    C: float                 # coeficiente: Rn del grupo = C · rn del perno
    x_ic: float              # distancia del centro instantaneo al centroide del grupo, in
    fx: list                 # componente horizontal de cada perno, por unidad de Rult, en el colapso
    fy: list                 # idem vertical
    ys: list
    C_elastic: float         # coeficiente del metodo elastico (referencia, siempre <= C)


DELTA_MAX = 0.34             # in, deformacion del perno mas alejado (Manual AISC, Parte 7)


def _R(d, dmax):
    """Curva carga-deformacion del perno (Crawford y Kulak), normalizada con Rult = 1."""
    return (1.0 - math.exp(-10.0 * DELTA_MAX * d / dmax)) ** 0.55


def ic_vertical_line(ys, e: float) -> ICResult:
    """Metodo del centro instantaneo para una fila vertical de pernos (AISC Manual, Parte 7).

    `ys`: ordenadas de los pernos respecto al centroide (simetricas); `e`: excentricidad horizontal de la
    carga vertical respecto a la fila.  Equilibrio con el CI a la distancia x del centroide, lado opuesto
    a la carga:
        P            = Σ R_i · x / d_i
        P · (x + e)  = Σ R_i · d_i          con  R_i = (1 − exp(−10·Δ_i))^0.55,  Δ_i = Δmax · d_i / dmax
    Fuerza del perno i en el colapso: (R_i·y_i/d_i , R_i·x/d_i)."""
    ys = [float(y) for y in ys]
    n = len(ys)
    ymax = max(abs(y) for y in ys) if ys else 0.0
    Ip = sum(y * y for y in ys)
    # elastico: P=1 -> cortante P/n y horizontal P·e·y/Ip en el perno extremo
    r_el = math.hypot(1.0 / n, (e * ymax / Ip) if Ip > 0 else 0.0)
    C_el = 1.0 / r_el if r_el > 0 else float(n)
    if abs(e) < 1e-9 or Ip <= 1e-12:
        # carga concentrica: todos los pernos con la misma fuerza
        r0 = (1.0 - math.exp(-10.0 * DELTA_MAX)) ** 0.55
        return ICResult(n * r0, 1e9, [0.0] * n, [r0] * n, ys, C_el)

    def parts(x):
        ds = [math.hypot(x, y) for y in ys]
        dm = max(ds)
        Rs = [_R(d, dm) for d in ds]
        return ds, Rs

    def g(x):
        ds, Rs = parts(x)
        return sum(R * d for R, d in zip(Rs, ds)) - (x + e) * sum(R * x / d for R, d in zip(Rs, ds))

    lo, hi = 1e-9, 1e5
    glo, ghi = g(lo), g(hi)
    if glo * ghi > 0:                       # no deberia pasar con e > 0; cae al elastico por seguridad
        x = hi if abs(ghi) < abs(glo) else lo
    else:
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if g(lo) * g(mid) <= 0:
                hi = mid
            else:
                lo = mid
            if hi - lo < 1e-12 * max(1.0, hi):
                break
        x = 0.5 * (lo + hi)
    ds, Rs = parts(x)
    P = sum(R * x / d for R, d in zip(Rs, ds))
    fx = [R * y / d for R, y, d in zip(Rs, ys, ds)]
    fy = [R * x / d for R, d in zip(Rs, ds)]
    return ICResult(P, x, fx, fy, ys, C_el)


# ============================================================ soldadura: dos lineas verticales
def weld_pair_vertical(V: float, e: float, L: float, w: float, FEXX: float, directional: bool = True):
    """Placa soldada a ambos lados (dos lineas verticales de largo L) con cortante V a la excentricidad e.
    Metodo elastico: fv = V/(2L) ; fh = 3·V·e/L²  (por linea, en el extremo).
    Resistencia por unidad de longitud y por linea: φ·0.60·FEXX·(1 + 0.5·sen^1.5θ)·0.707·w  (J2.4, J2-5)
    con θ el angulo de la resultante respecto al eje de la soldadura.
    Devuelve (f_resultante, capacidad, theta_deg, fv, fh)."""
    fv = V / (2.0 * L)
    fh = 3.0 * V * e / (L * L)
    f = math.hypot(fv, fh)
    th = math.degrees(math.atan2(fh, fv)) if f > 0 else 0.0
    kd = (1.0 + 0.5 * math.sin(math.radians(th)) ** 1.5) if directional else 1.0
    cap = PHI_WELD * 0.60 * FEXX * kd * 0.707 * w
    return f, cap, th, fv, fh


# ============================================================ propiedades de secciones por rectangulos
def rects_props(rects):
    """(A, yc, I, ymin, ymax) de una union de rectangulos (x0, y0, x1, y1) respecto al eje x horizontal."""
    A = sum((c - a) * (e - b) for a, b, c, e in rects)
    yc = sum((c - a) * (e - b) * (b + e) / 2 for a, b, c, e in rects) / A
    I = sum((c - a) * (e - b) ** 3 / 12 + (c - a) * (e - b) * ((b + e) / 2 - yc) ** 2 for a, b, c, e in rects)
    return A, yc, I, min(b for a, b, c, e in rects), max(e for a, b, c, e in rects)


def coped_section(shape, cope_top: float, cope_bot: float):
    """Seccion W de la viga en el extremo del cope (Snet, cm, etc.).  Se quitan `cope_top` por arriba y
    `cope_bot` por abajo (si el cope pasa del ala se corta tambien el alma). Devuelve dict con A, I, Sx, ybar."""
    d, bf, tf, tw = shape.d, shape.bf, shape.tf, shape.tw
    rects = [(-bf / 2, d / 2 - tf, bf / 2, d / 2), (-bf / 2, -d / 2, bf / 2, -d / 2 + tf),
             (-tw / 2, -d / 2 + tf, tw / 2, d / 2 - tf)]
    ytop, ybot = d / 2 - max(cope_top, 0.0), -d / 2 + max(cope_bot, 0.0)
    out = []
    for a, b, c, e in rects:
        b2, e2 = max(b, ybot), min(e, ytop)
        if e2 - b2 > 1e-9:
            out.append((a, b2, c, e2))
    if not out:
        return dict(A=0.0, I=0.0, S=0.0, ybar=0.0, h=0.0)
    A, yc, I, ymin, ymax = rects_props(out)
    c_ = max(yc - ymin, ymax - yc)
    return dict(A=A, I=I, S=I / c_ if c_ > 0 else 0.0, ybar=yc, h=ymax - ymin)


def net_flexure_plate(t: float, L: float, ys, dh_net: float):
    """Modulo de seccion neto de una placa rectangular de alto L con agujeros de ancho dh_net en las
    ordenadas `ys` (respecto al centro de la placa): S_net = I_net / (L/2)."""
    I = t * L ** 3 / 12.0 - sum(t * dh_net * y * y + t * dh_net ** 3 / 12.0 for y in ys)
    return I / (L / 2.0), I
