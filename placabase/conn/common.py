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


# ====================================================================== mas utilitarios
FNT = {"A325-N": 90.0, "A325-X": 90.0, "A490-N": 113.0, "A490-X": 113.0, "A307": 45.0}   # Tabla J3.2, ksi
E_STEEL = 29000.0


def bolt_tension_rn(db: float, grade: str) -> float:
    """Resistencia nominal a traccion de un perno, Rn = Fnt·Ab (kip), J3.6."""
    return FNT[grade] * math.pi * db ** 2 / 4.0


def bolt_tension_shear(db: float, grade: str, frv: float):
    """Interaccion traccion-cortante, AISC J3.7 (LRFD): F'nt = 1.3·Fnt − Fnt/(φ·Fnv)·frv ≤ Fnt.
    Devuelve la resistencia a traccion disponible por perno, φ·F'nt·Ab (kip), con frv el esfuerzo cortante requerido (ksi)."""
    Ab = math.pi * db ** 2 / 4.0
    fnt = min(FNT[grade], 1.3 * FNT[grade] - FNT[grade] / (PHI_BOLT * FNV[grade]) * max(frv, 0.0))
    return PHI_BOLT * max(fnt, 0.0) * Ab


def long_joint_factor(L_joint: float) -> float:
    """Tabla J3.2, nota: conexiones con pernos cargados en los extremos y L > 38 in: Fnv se reduce a 0.833."""
    return 0.833 if L_joint > 38.0 else 1.0


def prying_available(Bc, b, a, p, t, Fu, db, dh):
    """Traccion maxima por perno T de una T equivalente con efecto palanca (AISC Manual, Parte 9, LRFD).
        b' = b − db/2 ;  a' = min(a, 1.25·b) + db/2 ;  ρ = b'/a' ;  δ = 1 − dh/p
        β  = (1/ρ)·(Bc/T − 1) ;  α' = 1 si β ≥ 1, si no  min[ β / (δ·(1 − β)) , 1 ]  (≥ 0)
        t_min(T) = √( 4.44·T·b' / (p·Fu·(1 + δ·α')) )
    La capacidad es la mayor T ≤ Bc tal que t ≥ t_min(T) (biseccion); si t ≥ tc = √(4.44·Bc·b'/(p·Fu)) no hay palanca y T = Bc.
    Bc = φ·Rn del perno a traccion; p = ancho tributario por perno; Fu del ala de la T (la placa).
    Devuelve (T, alpha, tc)."""
    bp = b - db / 2.0
    ap = min(a, 1.25 * b) + db / 2.0
    rho = bp / ap if ap > 0 else 1.0
    delta = 1.0 - dh / p if p > dh else 0.05
    tc = math.sqrt(4.44 * Bc * max(bp, 1e-9) / (p * Fu))
    if t >= tc:
        return Bc, 0.0, tc

    def tmin(T):
        beta = (1.0 / rho) * (Bc / T - 1.0)
        alpha = 1.0 if beta >= 1.0 else min(1.0, max(0.0, beta / (delta * (1.0 - beta))))
        return math.sqrt(4.44 * T * max(bp, 1e-9) / (p * Fu * (1.0 + delta * alpha))), alpha

    lo, hi = 1e-9, Bc
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if tmin(mid)[0] <= t:
            lo = mid
        else:
            hi = mid
    return lo, tmin(lo)[1], tc


def column_fcr(Fy: float, KL_r: float) -> float:
    """Esfuerzo critico de pandeo por flexion, AISC E3 (E3-2, E3-3)."""
    if KL_r <= 0:
        return Fy
    Fe = math.pi ** 2 * E_STEEL / KL_r ** 2
    if KL_r <= 4.71 * math.sqrt(E_STEEL / Fy):
        return (0.658 ** (Fy / Fe)) * Fy
    return 0.877 * Fe


# ---- fuerzas concentradas sobre alas y almas, AISC 360 J10
def web_local_yielding(Fyw, tw, k, N, at_end=False):
    """J10.2 (φ = 1.00): Rn = Fyw·tw·(5k + N)  (2.5k + N si la carga esta a menos de d del extremo)."""
    return Fyw * tw * ((2.5 if at_end else 5.0) * k + N)


def web_crippling(Fyw, tw, tf, d, N, at_end=False):
    """J10.3 (φ = 0.75), perfiles I (Qf = 1): interior J10-4; extremo J10-5a/b."""
    r = math.sqrt(E_STEEL * Fyw * tf / tw)
    ratio = (tw / tf) ** 1.5
    if not at_end:
        return 0.80 * tw ** 2 * (1.0 + 3.0 * (N / d) * ratio) * r
    if N / d <= 0.2:
        return 0.40 * tw ** 2 * (1.0 + 3.0 * (N / d) * ratio) * r
    return 0.40 * tw ** 2 * (1.0 + (4.0 * N / d - 0.2) * ratio) * r


def flange_local_bending(Fyf, tf):
    """J10.1 (φ = 0.90): Rn = 6.25·tf²·Fyf."""
    return 6.25 * tf ** 2 * Fyf


def panel_zone_shear(Fy, dc, tw):
    """J10.6(a) (φ = 0.90), Pr ≤ 0.4·Pc: Rn = 0.60·Fy·dc·tw."""
    return 0.60 * Fy * dc * tw


# ---- grupo de pernos, metodo elastico (cualquier disposicion)
def elastic_bolt_group(pts, Vx: float, Vy: float, M: float = 0.0):
    """Fuerza de cada perno de un grupo cualquiera: reparto directo + torsion respecto al centroide.
    `pts` = [(x, y)] ; (Vx, Vy) = cortante resultante en el centroide ; M = momento torsor sobre el grupo (kip·in).
    Devuelve [(fx, fy)] por perno.  Metodo elastico: conservador respecto al centro instantaneo."""
    n = len(pts)
    xc = sum(p[0] for p in pts) / n
    yc = sum(p[1] for p in pts) / n
    J = sum((x - xc) ** 2 + (y - yc) ** 2 for x, y in pts)
    out = []
    for x, y in pts:
        fx, fy = Vx / n, Vy / n
        if J > 0:
            fx += -M * (y - yc) / J
            fy += M * (x - xc) / J
        out.append((fx, fy))
    return out


# ---- soldadura: lineas verticales paralelas y segmentos cualesquiera
def weld_lines_vertical(V: float, e: float, L: float, w: float, FEXX: float, nlines: int = 2, directional: bool = True):
    """`nlines` lineas verticales coincidentes (en planta) de largo L con cortante V a la excentricidad e.
    fv = V/(n·L) ;  fh = 6·V·e/(n·L²)  (n = 2 reproduce weld_pair_vertical).  Devuelve (f, cap, theta, fv, fh)."""
    fv = V / (nlines * L)
    fh = 6.0 * V * e / (nlines * L * L)
    f = math.hypot(fv, fh)
    th = math.degrees(math.atan2(fh, fv)) if f > 0 else 0.0
    kd = (1.0 + 0.5 * math.sin(math.radians(th)) ** 1.5) if directional else 1.0
    return f, PHI_WELD * 0.60 * FEXX * kd * 0.707 * w, th, fv, fh


def weld_segments_elastic(segs, Fx: float, Fy: float, xa: float, ya: float, w: float, FEXX: float,
                          directional: bool = True, ds: float = 0.25):
    """Grupo de soldadura plano formado por segmentos rectos [(x1, y1, x2, y2)], cargado en su plano con la fuerza
    (Fx, Fy) aplicada en (xa, ya).  Metodo elastico: f = (F/L) + torsion respecto al centroide (M/Ip)·r.
    En cada punto la capacidad por unidad de longitud usa el angulo θ entre el esfuerzo y el eje del segmento
    (J2-5).  Devuelve dict con el punto critico: ratio, f, cap, theta, L total."""
    pts = []                                  # (x, y, dL, tx, ty)
    for x1, y1, x2, y2 in segs:
        Ls = math.hypot(x2 - x1, y2 - y1)
        if Ls <= 0:
            continue
        m = max(1, int(math.ceil(Ls / ds)))
        tx, ty = (x2 - x1) / Ls, (y2 - y1) / Ls
        for i in range(m):
            u = (i + 0.5) / m
            pts.append((x1 + u * (x2 - x1), y1 + u * (y2 - y1), Ls / m, tx, ty))
    L = sum(q[2] for q in pts)
    xc = sum(q[0] * q[2] for q in pts) / L
    yc = sum(q[1] * q[2] for q in pts) / L
    Ip = sum(q[2] * ((q[0] - xc) ** 2 + (q[1] - yc) ** 2) for q in pts)
    M = (xa - xc) * Fy - (ya - yc) * Fx
    best = dict(ratio=0.0, f=0.0, cap=0.0, theta=0.0, L=L)
    ends = []                                  # los extremos de cada segmento tambien se evaluan (alli esta el pico)
    for x1, y1, x2, y2 in segs:
        Ls = math.hypot(x2 - x1, y2 - y1)
        if Ls > 0:
            ends += [(x1, y1, 0.0, (x2 - x1) / Ls, (y2 - y1) / Ls), (x2, y2, 0.0, (x2 - x1) / Ls, (y2 - y1) / Ls)]
    for x, y, dL, tx, ty in pts + ends:
        fx = Fx / L - (M * (y - yc) / Ip if Ip > 0 else 0.0)
        fy = Fy / L + (M * (x - xc) / Ip if Ip > 0 else 0.0)
        f = math.hypot(fx, fy)
        if f <= 0:
            continue
        cos_t = abs(fx * tx + fy * ty) / f
        th = math.degrees(math.acos(min(1.0, cos_t)))          # 0 = a lo largo de la soldadura
        kd = (1.0 + 0.5 * math.sin(math.radians(th)) ** 1.5) if directional else 1.0
        cap = PHI_WELD * 0.60 * FEXX * kd * 0.707 * w
        if f / cap > best["ratio"]:
            best.update(ratio=f / cap, f=f, cap=cap, theta=th)
    return best


def bearing_group(Fx, Fy, db, t, Fu, Lc_v, Lc_h, phi=PHI_BOLT):
    """Aplastamiento por perno: la componente vertical y la horizontal se combinan en elipse.
    `Fx`, `Fy`: fuerza de cada perno sobre la pieza; `Lc_v(i)`: distancia libre en la direccion en que empuja el perno i
    (vertical); `Lc_h`: {i: distancia libre} de los pernos cuya componente horizontal empuja hacia un borde libre
    (el resto empuja hacia material continuo).  Devuelve (peor D/C, indice, fuerza del perno critico)."""
    worst, wi = 0.0, 0
    for i in range(len(Fx)):
        rv = phi * bearing_rn(db, t, Fu, Lc_v(i))
        rh = phi * bearing_rn(db, t, Fu, Lc_h.get(i, 1e9))
        r = math.hypot(abs(Fy[i]) / rv, abs(Fx[i]) / rh) if rv > 0 and rh > 0 else 99.0
        if r > worst:
            worst, wi = r, i
    return worst, wi, math.hypot(Fx[wi], Fy[wi])


def weld_segments_oop(segs, Fy: float, Mx: float, w: float, FEXX: float, directional: bool = True, ds: float = 0.25):
    """Grupo de soldadura plano de segmentos [(z1, y1, z2, y2)] (coordenadas en el plano del soporte, y vertical) con
    cortante vertical `Fy` en su plano y momento `Mx` FUERA del plano (eje horizontal z).  Metodo elastico:
        fv = Fy/L  (vertical, en el plano) ;   fn = Mx·(y − yc)/Ix  (normal al plano, perpendicular al eje de toda linea)
    El angulo θ de la resultante con el eje del segmento sale de la componente a lo largo del eje (fv·|ty|) y de la
    perpendicular (hipot(fv·|tz|, fn)).  Devuelve dict del punto critico: ratio, f, cap, theta, L."""
    pts = []
    for z1, y1, z2, y2 in segs:
        Ls = math.hypot(z2 - z1, y2 - y1)
        if Ls <= 0:
            continue
        m = max(1, int(math.ceil(Ls / ds)))
        tz, ty = (z2 - z1) / Ls, (y2 - y1) / Ls
        for i in range(m):
            u = (i + 0.5) / m
            pts.append((y1 + u * (y2 - y1), Ls / m, tz, ty))
    L = sum(q[1] for q in pts)
    yc = sum(q[0] * q[1] for q in pts) / L
    Ix = sum(q[1] * (q[0] - yc) ** 2 for q in pts)
    ends = []
    for z1, y1, z2, y2 in segs:
        Ls = math.hypot(z2 - z1, y2 - y1)
        if Ls > 0:
            ends += [(y1, 0.0, (z2 - z1) / Ls, (y2 - y1) / Ls), (y2, 0.0, (z2 - z1) / Ls, (y2 - y1) / Ls)]
    best = dict(ratio=0.0, f=0.0, cap=0.0, theta=0.0, L=L, Ix=Ix)
    fv = abs(Fy) / L
    for y, dL, tz, ty in pts + ends:
        fn = abs(Mx * (y - yc) / Ix) if Ix > 0 else 0.0
        along = fv * abs(ty)
        perp = math.hypot(fv * abs(tz), fn)
        f = math.hypot(along, perp)
        if f <= 0:
            continue
        th = math.degrees(math.atan2(perp, along))
        kd = (1.0 + 0.5 * math.sin(math.radians(th)) ** 1.5) if directional else 1.0
        cap = PHI_WELD * 0.60 * FEXX * kd * 0.707 * w
        if f / cap > best["ratio"]:
            best.update(ratio=f / cap, f=f, cap=cap, theta=th)
    return best


# ---- factores de sobrerresistencia (AISC 341, Tabla A3.1) por acero
RY = {"ASTM A992": 1.1, "ASTM A36": 1.5, "ASTM A572 Gr.50": 1.1, "ASTM A913 Gr.50": 1.1}


def ry_of(steel_name: str) -> float:
    return RY.get(steel_name, 1.1)
