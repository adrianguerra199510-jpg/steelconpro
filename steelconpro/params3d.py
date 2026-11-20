# -*- coding: utf-8 -*-
"""Parametros comunes del modelo 3D: brazo del cortante, modulo de balasto y rigidez axial del perno."""
from __future__ import annotations
import math
import numpy as np

from .model import Project
from .units import ES_KSI, Ec_ksi


def shear_arm(prj: Project) -> float:
    """Brazo e (in) entre donde el cortante entra en la placa (cara superior) y donde lo
    devuelven los pernos o la llave.  Manual si fea.shear_arm >= 0; si no:
      sin llave : tp/2 + mortero + stand-off  (el perno apoya en el centro del espesor y, con mortero,
                  trabaja a esa altura sobre el concreto)
      con llave : tp + H/2        (la llave reacciona en el centro de su altura de apoyo)."""
    a = float(getattr(prj.fea, "shear_arm", -1.0))
    if a >= 0:
        return a
    p = prj.plate
    if prj.lug.enabled:
        return p.tp + 0.5 * prj.lug.H
    return 0.5 * p.tp + max(0.0, p.grout) + max(0.0, getattr(prj.bolts, 'standoff', 0.0))


def foundation_ks(prj: Project) -> float:
    if prj.fea.ks_mode == "manual":
        return max(1.0, prj.fea.ks_manual)
    return Ec_ksi(prj.conc.fc) / max(6.0, prj.conc.ha)


def bolt_kb(prj: Project) -> float:
    g = prj.bolts.geom()
    Lb = prj.bolts.hef + prj.plate.tp + prj.plate.grout + max(0.0, getattr(prj.bolts, "standoff", 0.0))
    return ES_KSI * g.Ase / max(Lb, 1.0)


def washer_radius(prj: Project) -> float:
    """Radio exterior de la arandela (zona de apoyo de la tuerca sobre la placa): el diametro indicado o, en
    automatico, el mayor entre el ancho de la tuerca hex pesada y 2.2 veces el diametro del perno."""
    g = prj.bolts.geom()
    d = prj.bolts.washer_d if prj.bolts.washer_d > 0 else max(g.Fhex, 2.2 * g.db)
    return max(d / 2.0, g.dh / 2.0 + 0.05)


def washer_thickness(prj: Project) -> float:
    """Espesor de la arandela, in.  < 0 en el proyecto = automatico (0.25·db); 0 = sin arandela."""
    t = prj.bolts.washer_t
    return 0.25 * prj.bolts.geom().db if t < 0 else float(t)


def washer_elements(prj: Project, x: float, y: float, z: float) -> bool:
    """True si el punto (x, y, z) esta dentro del volumen de una arandela (sobre la placa, junto a un perno)."""
    from . import geometry as G
    tw = washer_thickness(prj)
    if tw <= 0 or z < prj.plate.tp - 1e-6 or z > prj.plate.tp + tw + 1e-6:
        return False
    rw = washer_radius(prj)
    return any((x - bx) ** 2 + (y - by) ** 2 <= (rw + 1e-4) ** 2 for bx, by in G.bolt_positions(prj))


def hook_profile(kind: str, db: float, eh: float, steps: int = 14):
    """Eje del doblez del gancho en el plano (s, z): s = distancia radial hacia afuera desde el eje del perno, z = altura
    sobre el fondo del anclaje (eje de la barra en el punto mas bajo = 0).  El primer punto es donde termina el vastago
    recto (z = rc).  Radio de doblez al eje rc = 2·db (radio interior 1.5·db).
    L: 90° y pata recta de largo eh;  J: 180° y cola recta de 4·db (o eh/2 si es mayor).  -> (puntos, rc)."""
    rc = 2.0 * db
    pts = [(0.0, rc)]
    if kind == "gancho_L":
        for a in np.linspace(math.pi, 1.5 * math.pi, steps)[1:]:
            pts.append((rc + rc * math.cos(a), rc + rc * math.sin(a)))
        pts.append((max(eh, rc + 1.5 * db), 0.0))
    else:
        for a in np.linspace(math.pi, 2.0 * math.pi, 2 * steps)[1:]:
            pts.append((rc + rc * math.cos(a), rc + rc * math.sin(a)))
        pts.append((2.0 * rc, rc + max(4.0 * db, 0.5 * eh)))
    return pts, rc
