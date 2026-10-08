# -*- coding: utf-8 -*-
"""Refuerzo del arrancamiento con barras en U (ACI 318-19 17.5.2 / 17.6.2.1.2 / 17.7.2.5).

Cada U es una barra en forma de "herradura invertida": un tramo horizontal cerca de la superficie del
concreto, que abraza el grupo de pernos, y dos patas verticales que bajan a ambos lados.  Cada pata aporta
As·fy; deben estar desarrolladas a los dos lados de la superficie de falla (el cono de arrancamiento).
Geometria y comprobaciones comparten estos datos (dibujo, 3D, anclajes).

Dos opciones (Conc.u_type):
  A  barra U       : patas rectas; bajo la punta del anclaje se desarrolla ld (ACI 25.4.2.3) y sobre la punta del anclaje el tramo horizontal actua
                     como gancho (ldh).
  B  barra OMEGA   : las patas terminan en un gancho estandar de 90° hacia AFUERA (cola de 12·db); bajo la punta del anclaje se
                     desarrolla ldh (ACI 25.4.3) y sobre la punta del anclaje tambien ldh."""
from __future__ import annotations
import math

from .model import Project, REBAR
from . import geometry as G

PHI_REINF = 0.75          # ACI 17.5.3: refuerzo de anclaje, condicion A


def ubar(prj: Project):
    """Datos de las barras U o None si no hay. Unidades: in, ksi."""
    c, b = prj.conc, prj.bolts
    if not getattr(c, "u_on", False) or c.u_n <= 0:
        return None
    omega = str(getattr(c, "u_type", "")).startswith("Opcion B")
    db, Ab = REBAR.get(c.u_size, REBAR["#4"])
    fy = max(float(c.u_fy), 1.0)
    sq = math.sqrt(max(c.fc, 1e-6) * 1000.0)
    lam = max(c.lam, 0.5)
    # ACI 25.4.2.3 (barra recta, psi) y 25.4.3 (gancho estandar); psi_t = psi_e = 1
    ld = max(12.0, fy * 1000.0 / ((25.0 if db <= 0.75 + 1e-9 else 20.0) * lam * sq) * db)
    ldh = max(8.0 * db, 6.0, fy * 1000.0 / (50.0 * lam * sq) * db)
    hef = max(b.hef, 1.0)
    pos = G.bolt_positions(prj) or [(0.0, 0.0)]
    xs = [x for x, _ in pos]
    ys = [y for _, y in pos]
    off = min(0.5 * hef, max(0.3 * hef, 3.0))            # distancia de la pata al eje del perno (<= 0.5·hef)
    lim = max(c.B2 / 2.0 - 1.5, 1.0)                      # recubrimiento lateral de 1.5 in
    xl, xr = max(min(xs) - off, -lim), min(max(xs) + off, lim)
    depth = max(float(c.u_depth), db)                     # profundidad del tramo horizontal bajo la superficie
    z_cross = max(depth, hef)                             # seccion critica: la punta del anclaje (como en el esquema: ldh/ld se miden de ahi hacia abajo)
    above = z_cross - depth                               # longitud de pata sobre la superficie de falla (gancho)
    dev_req = ldh if omega else ld                        # longitud a desarrollar bajo la punta del anclaje (A: ld recta, B: ldh con gancho)
    leg_req = above + dev_req                             # pata total para desarrollarla bajo la punta del anclaje
    leg = float(c.u_leg) if c.u_leg > 0 else math.ceil(leg_req)
    below = depth + leg - z_cross                         # longitud desarrollada bajo la punta del anclaje
    n_legs = 2 * int(c.u_n)
    # las U van FUERA del grupo de anclajes, a 5 cm (1.97 in) de la fila extrema, mitad a cada lado (si son impares, una mas en el
    # lado -Y); asi el tramo horizontal no choca con los pernos.  Separacion entre barras del mismo lado: max(4·db, 2 in).
    ya, yb = min(ys), max(ys)
    dist = 50.0 / 25.4
    sep = max(4.0 * db, 2.0)
    n = int(c.u_n)
    n_lo, n_hi = (n + 1) // 2, n // 2
    lim_y = max(c.N2 / 2.0 - 1.5, 1.0)
    yu = [max(ya - dist - k * sep, -lim_y) for k in range(n_lo)] + [min(yb + dist + k * sep, lim_y) for k in range(n_hi)]
    yu.sort()
    rb = 3.5 * db                                         # radio al eje del doblez (diametro interior 6·db)
    tail = max(12.0 * db, 4.0 * db) if omega else 0.0      # cola del gancho estandar de 90° (ACI 25.3.1)
    tail_end = min(abs(xl), abs(xr)) + tail               # distancia del extremo de la cola al eje del pedestal
    cover = c.B2 / 2.0 - (max(abs(xl), abs(xr)) + tail)   # recubrimiento lateral que queda tras la cola
    return dict(size=c.u_size, db=db, Ab=Ab, fy=fy, n=int(c.u_n), n_legs=n_legs, ld=ld, ldh=ldh, off=off,
                kind="OMEGA" if omega else "U", dev=dev_req, rb=rb, tail=tail, cover=cover,
                xl=xl, xr=xr, depth=depth, z_cross=z_cross, above=above, leg=leg, leg_req=leg_req,
                below=below, yu=yu, Nrs=n_legs * Ab * fy, phi=PHI_REINF,
                max_leg=c.ha - depth)
