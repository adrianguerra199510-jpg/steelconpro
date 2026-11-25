# -*- coding: utf-8 -*-
"""Verificaciones de los componentes con los resultados del analisis del modelo de placas (AISC 360-22 / ACI 318-19).

Cada verificacion lleva su categoria (`cat`: Miembros, Placas, Pernos, Soldaduras, Anclajes y concreto) y el componente al que pertenece (`comp`), para el
resumen estandar de resultados:

  · miembros y placas: esfuerzos locales del modelo (von Mises en las caras ≤ φ·Fy si todo queda elastico; si hay plastificacion,
    deformacion plastica equivalente ≤ 5 %), en la zona de la conexion (sin los extremos donde se aplican cargas y apoyos);
  · pernos: cortante por plano (J3.6), traccion con la interaccion J3.7 y aplastamiento / desgarramiento en cada placa (J3.10);
  · soldaduras: fuerza por unidad de largo del cordon ≤ φ·0.60·FEXX·0.707·w (J2.4, sin el aumento por la direccion de la carga);
  · anclajes: resistencia del acero a traccion y cortante (ACI 318-19 17.6.1, 17.7.1) y su interaccion (17.8).  Las resistencias del
    concreto (arrancamiento, extraccion, desprendimiento) las da la verificacion de la placa base.
"""
from __future__ import annotations
import math

import numpy as np

from ...design import Check
from ..common import FNV, FNT, PHI_BOLT, bolt_tension_shear
from .shellpost import PLASTIC_LIMIT

FUTA = {"A307": 60.0, "A325-N": 120.0, "A325-X": 120.0, "A490-N": 150.0, "A490-X": 150.0}


def _ck(key, title, dem, cap, unit, ref, note, cat, comp, skip=False):
    c = Check(key, title, float(dem), float(cap), unit, ref, note, skip)
    c.cat, c.comp = cat, comp
    return c


def _edge_dist(plate, x, d):
    """Distancia del punto x (sobre la placa) al borde del contorno de la placa en la direccion d (en el plano)."""
    P = np.asarray(plate["P"], float)
    best = 1e9
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        e = b - a
        M = np.array([d, -e]).T                                    # x + s d = a + u e
        try:
            sol, *_ = np.linalg.lstsq(M, a - x, rcond=None)
        except np.linalg.LinAlgError:
            continue
        s, u = sol
        if s > 1e-6 and -1e-6 <= u <= 1 + 1e-6 and np.linalg.norm(x + s * d - (a + u * e)) < 1e-3:
            best = min(best, float(s))
    return best


def checks(R, case, mdl, members, units) -> list:
    out = []
    u = units
    parts = {p.name: p for p in mdl.parts}
    members = set(members)
    # ---------------------------------------------------------------- miembros y placas: esfuerzos locales
    for part, d in R.parts.items():
        cat = "Miembros" if part in members else "Placas"
        Fy = d["Fy"]
        key = "".join(ch if ch.isalnum() else "_" for ch in part)
        if d["peeq"] > 1e-6:
            out.append(_ck(f"sh_pe_{key}", f"Deformación plástica equivalente — {part}", 100.0 * d["peeq"], 100.0 * PLASTIC_LIMIT, "%",
                           "Análisis elasto-plástico (φ·Fy); deformación plástica admisible 5 %",
                           f"von Mises en las caras {u.q('S', d['vm'], 1)}; espesor {u.q('L', d['t'], 3)}" + ("; zona de la conexión" if cat == "Miembros" else ""), cat, part))
        else:
            out.append(_ck(f"sh_vm_{key}", f"Esfuerzo de von Mises en las caras ≤ φ·Fy — {part}", d["vm"], 0.9 * Fy, "ksi", "AISC 360-22 (φ = 0.90), análisis elástico",
                           f"promedio en un radio del orden del espesor (pico puntual {u.q('S', d.get('vm_peak', d['vm']), 1)}); espesor {u.q('L', d['t'], 3)}"
                           + ("; esfuerzos locales en la zona de la conexión" if cat == "Miembros" else ""), cat, part))
    # ---------------------------------------------------------------- pernos y anclajes
    groups = {}
    for b in R.bolts:
        if b["anchor"]:
            comp = f"Anclajes de {b['parts'][0]}"
        else:
            comp = "Pernos " + " – ".join(dict.fromkeys(b["parts"]))
        groups.setdefault((b["anchor"], comp), []).append(b)
    for (anchor, comp), bl in groups.items():
        key = "".join(ch if ch.isalnum() else "_" for ch in comp)
        n = len(bl)
        if anchor:
            _anchor_checks(out, bl, comp, key, u)
            continue
        grade = bl[0]["grade"] if bl[0]["grade"] in FNV else "A325-N"
        db = bl[0]["db"]
        Ab = math.pi * db * db / 4.0
        phiV = PHI_BOLT * FNV[grade] * Ab
        bv = max(bl, key=lambda b: b["V"])
        out.append(_ck(f"sh_bv_{key}", f"Perno — cortante por plano ({n} pernos)", bv["V"], phiV, "kip", "AISC 360-22 J3.6",
                       f"perno más cargado {bv['tag']}; φ·Fnv·Ab = 0.75·{FNV[grade]:g}·{Ab:.3f}", "Pernos", comp))
        bt = max(bl, key=lambda b: b["T"] / max(bolt_tension_shear(db, grade, b["V"] / Ab), 1e-9))
        phiT = bolt_tension_shear(db, grade, bt["V"] / Ab)
        out.append(_ck(f"sh_bt_{key}", f"Perno — tracción con cortante concomitante ({n} pernos)", max(bt["T"], 0.0), phiT, "kip", "AISC 360-22 J3.6, J3.7",
                       f"perno {bt['tag']}; cortante concomitante {u.q('F', bt['V'])}", "Pernos", comp, skip=bt["T"] <= 1e-6))
        # aplastamiento y desgarramiento en cada placa del paquete
        worst = None
        for b in bl:
            for pi, pl_part in enumerate(b["parts"]):
                V = max([q["V"] for k_, q in enumerate(b["planes"]) if k_ in (pi - 1, pi)] + [0.0])
                if V <= 1e-9:
                    continue
                pt = parts.get(pl_part)
                Fu = float(getattr(pt, "Fu", 58.0) or 58.0)
                for p in [p for p in range(len(R.plate_part)) if R.plate_part[p] == pl_part]:
                    plate = case.plates[p]
                    nrm = np.asarray(plate["n"], float)
                    ax = np.asarray(b["axis"], float)
                    if abs(float(nrm @ ax)) < 0.9:
                        continue
                    x0 = np.asarray(b["pos"], float)
                    c = np.mean(np.asarray(plate["P"], float), axis=0)
                    s = float((c - x0) @ nrm) / float(ax @ nrm)
                    x = x0 + s * ax
                    dirs = [np.asarray(q["dir"], float) for k_, q in enumerate(b["planes"]) if k_ in (pi - 1, pi) and q["V"] > 1e-9]
                    if not dirs:
                        continue
                    dd = dirs[0] - nrm * float(dirs[0] @ nrm)
                    if np.linalg.norm(dd) < 1e-9:
                        continue
                    dd = dd / np.linalg.norm(dd)
                    le = min(_edge_dist(plate, x, dd), _edge_dist(plate, x, -dd))
                    if le > 1e8:
                        continue
                    t = R.plate_t[p]
                    lc = max(le - b["dh"] / 2.0, 0.0)
                    rn = min(1.2 * lc * t * Fu, 2.4 * db * t * Fu)
                    phi_rn = PHI_BOLT * rn
                    r = V / max(phi_rn, 1e-9)
                    if worst is None or r > worst[0]:
                        worst = (r, V, phi_rn, b["tag"], pl_part, t, lc)
                    break
        if worst:
            r, V, phi_rn, tag, pl_part, t, lc = worst
            out.append(_ck(f"sh_bb_{key}", "Aplastamiento / desgarramiento en el agujero", V, phi_rn, "kip", "AISC 360-22 J3.10 (deformación considerada)",
                           f"perno {tag} en «{pl_part}» (t = {u.q('L', t, 3)}, lc = {u.q('L', lc, 2)}); φ·min(1.2·lc·t·Fu, 2.4·d·t·Fu)", "Pernos", comp))
    # ---------------------------------------------------------------- soldaduras
    wg = {}
    for w in R.welds:
        comp = f"Soldadura {w['A']} – {w['B']}"
        wg.setdefault(comp, []).append(w)
    for comp, wl in wg.items():
        key = "".join(ch if ch.isalnum() else "_" for ch in comp)
        ww = max(wl, key=lambda w: w["q"] / max(w["cap"], 1e-9))
        Ltot = sum(w["L"] for w in wl)
        out.append(_ck(f"sh_w_{key}", f"Cordón — fuerza por unidad de largo ({len(wl)} tramo(s), {u.q('L', Ltot, 1)})", ww["q"], ww["cap"], "kip/in",
                       "AISC 360-22 J2.4: φ·0.60·FEXX·0.707·w",
                       f"tramo {ww['name']}; cateto {u.q('L', ww['w'], 3)}; {'un cordón a cada lado' if ww['sides'] == 2 else 'un cordón'}; fuerza que transmite «{ww['from'] or ww['A']}»",
                       "Soldaduras", comp))
    return out


def _anchor_checks(out, bl, comp, key, u):
    b0 = bl[0]
    db = b0["db"]
    futa = min(FUTA.get(b0["grade"], 58.0), 125.0)
    Ase = 0.7854 * (db - 0.9743 / max(_tpi(db), 1)) ** 2          # area efectiva de la rosca
    phiN = 0.75 * Ase * futa
    phiV = 0.65 * 0.6 * Ase * futa
    bt = max(bl, key=lambda b: b["T"])
    bv = max(bl, key=lambda b: b["V"])
    n = len(bl)
    out.append(_ck(f"sh_at_{key}", f"Anclaje — tracción, acero ({n} anclajes)", max(bt["T"], 0.0), phiN, "kip", "ACI 318-19 17.6.1: φ·Ase·futa (φ = 0.75)",
                   f"anclaje {bt['tag']}; Ase = {Ase:.3f} in²", "Anclajes y concreto", comp, skip=bt["T"] <= 1e-6))
    out.append(_ck(f"sh_av_{key}", f"Anclaje — cortante, acero ({n} anclajes)", bv["V"], phiV, "kip", "ACI 318-19 17.7.1: φ·0.6·Ase·futa (φ = 0.65)",
                   f"anclaje {bv['tag']}", "Anclajes y concreto", comp, skip=bv["V"] <= 1e-6))
    inter = max(((max(b["T"], 0.0) / phiN) ** (5 / 3) + (b["V"] / phiV) ** (5 / 3), b["tag"]) for b in bl)
    out.append(_ck(f"sh_ai_{key}", "Anclaje — interacción tracción-cortante", inter[0], 1.0, "-", "ACI 318-19 17.8: (N/φNn)^5/3 + (V/φVn)^5/3 ≤ 1",
                   f"anclaje {inter[1]}; resistencias del acero (las del concreto: verificación de la placa base)", "Anclajes y concreto", comp))
    cmin = [b for b in bl if b["T"] < -1e-6]
    if cmin:
        bc = min(cmin, key=lambda b: b["T"])
        out.append(_ck(f"sh_ac_{key}", "Anclaje — compresión (placa sobre tuercas de nivelación)", -bc["T"], phiN, "kip", "ACI 318-19 17.6.1 (acero); pandeo no evaluado",
                       f"anclaje {bc['tag']}", "Anclajes y concreto", comp))


def _tpi(db):
    return {0.5: 13, 0.625: 11, 0.75: 10, 0.875: 9, 1.0: 8, 1.125: 7, 1.25: 7, 1.5: 6}.get(round(db, 3), 8 if db >= 1.0 else 10)
