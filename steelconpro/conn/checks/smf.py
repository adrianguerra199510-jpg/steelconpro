# -*- coding: utf-8 -*-
"""Verificaciones del NUDO de un pórtico especial a momento (SMF) con placas extremas precalificadas (AISC Design Guide 4) diseñadas para sismo:

  · Columna fuerte–viga débil, AISC 341-22 E3.4a:  ΣM*pc / ΣM*pb > 1.0
        M*pc = Σ Zc·(Fyc − Prc/Ag)   (columna arriba y abajo del nudo; una sola si la columna termina en el nudo)
        M*pb = Σ (Mpe + Muv),  Mpe = 1.1·Ry·Fy·Zx y Muv = Vu·(Lp + dc/2): el momento probable de cada viga llevado al eje de la columna
        Prc = la mayor compresión de la columna en los casos con sobrerresistencia (Ωo) del nudo, o en todos si no los hay.
  · Zona del panel, AISC 341-22 E3.6e:  Ru = Σ Mf/(d − tf) − Vc ≤ φv·Rv,  φv = 1.0
        Mf = Mpe + Vu·Lp en la cara de la columna (el Muc de cada placa); Vc = Σ(Mpe + Muv)/H (cortante de la columna, H = altura de piso);
        Rv con la deformación del panel, AISC 360-22 J10.6(b): 0.60·Fy·dc·tw·(1 + 3·bcf·tcf²/(db·dc·tw)) si Prc ≤ 0.75·Py, y
        ·(1.9 − 1.2·Prc/Py) si no.  Si no alcanza, el espesor de la placa adosada (doubler) que falta.
        Espesor individual del alma y de la placa adosada: t ≥ (dz + wz)/90 (E3.6e.2), dz = d − 2·tf de la viga, wz = dc − 2·tfc.
  · Placas de continuidad (operación «Placas de continuidad» de la viga):
        espesor ≥ 0.5·tbf con viga de un lado y ≥ tbf con vigas a los dos lados (AISC 341-22 E3.6f.2);
        ancho bs + twc/2 ≥ bbf/3 y espesor ≥ bs/16 (AISC 360-22 J10.8); esbeltez bs/t ≤ 0.56·√(E/Fy);
        soldadura al alma (filetes a ambos lados) para la fuerza Fsu de la Design Guide 4 (paso 19; su fluencia ≤ φ·Fy·As la verifica la placa DG4).
        En sismo, las soldaduras a las alas de la columna son CJP (E3.6f.3): se informa.
Con estos datos el programa no conoce la columna fuera del nudo: se supone la misma sección arriba y abajo.
"""
from __future__ import annotations
import math

from ... import materials as M
from ...design import Check
from ...shapes import CATALOG
from .. import nodal as NOD

E_ST = 29000.0


def _ck(out, key, title, dem, cap, unit, ref, note="", skip=False):
    c = Check(key, title, float(dem), float(cap), unit, ref, note, skip)
    c.group = "Nudo de pórtico especial (AISC 341)"
    out.append(c)
    return c


def _col_compression(nd) -> float:
    """Mayor compresión de la columna (kip) en el lado que equilibra: casos Ωo del nudo si los hay; si no, todos."""
    cases = NOD.cases_of(nd)
    kinds = dict(getattr(nd, "case_kind", None) or {})
    om = [c for c in cases if kinds.get(c[0]) == "Ωo"]
    worst = 0.0
    for _name, loads in (om or cases):
        b = NOD.balance(nd, loads)
        worst = max(worst, -float(b["main_local"]["N"]))
    return worst


def node_checks(prj, nd, items, H: float) -> list:
    """Verificaciones del nudo SMF.  `items` = elementos verificados (adapters.Item) con su DG4Spec; solo las placas DG4 sísmicas."""
    from .endplate_dg4 import design
    dg = [it for it in items if it.kind == "dg4" and it.engine is not None and it.spec is not None and it.spec.seismic]
    out = []
    if not dg:
        return out
    col = CATALOG.get(nd.main_shape)
    if col is None or col.kind != "W":
        return out
    cm = M.find(M.SHAPE_STEELS, nd.main_steel)
    dc, tfc, bfc, twc, Ag, Zc = col.d, col.tf, col.bf, col.tw, col.A, col.Zx
    # ---- datos de cada viga (Mpe, Vu, Lp, Mf) de su verificación DG4
    beams = []
    for it in dg:
        I = {}
        design(it.spec, 0.0, 0.0, None, None, I)
        b = CATALOG.get(it.spec.beam)
        beams.append({"name": it.m.name, "Mpe": I["Mpe"], "Vu": I["Vu"], "Lp": I["Lp"], "Muc": I["Muc"], "Ffu": I["Ffu"], "d": b.d, "tf": b.tf, "bf": b.bf, "it": it})
    two_sided = len(beams) >= 2                                       # vigas precalificadas a las dos alas de la columna
    Prc = _col_compression(nd)
    Py = cm.Fy * Ag
    from .adapters import _col_ends
    ncol = 1 if _col_ends(nd) else 2
    # ---- columna fuerte – viga débil (E3.4a)
    Mpc = ncol * Zc * max(cm.Fy - Prc / Ag, 0.0)
    Mpb = sum(b["Mpe"] + b["Vu"] * (b["Lp"] + dc / 2.0) for b in beams)
    _ck(out, "smf_scwb", "Columna fuerte–viga débil: ΣM*pb ≤ ΣM*pc", Mpb, Mpc, "kip·in", "AISC 341-22 E3.4a",
        f"ΣM*pc = {ncol}·Zc·(Fyc − Prc/Ag) con Zc = {Zc:g} in³, Prc = {Prc:.0f} kip ({'casos Ωo' if any(v == 'Ωo' for v in (getattr(nd, 'case_kind', {}) or {}).values()) else 'todos los casos'}); "
        f"ΣM*pb = Σ(Mpe + Vu·(Lp + dc/2)) de {len(beams)} viga(s)" + ("; la columna termina en el nudo: una sola columna (vea las excepciones de E3.4a)" if ncol == 1 else "; misma sección arriba y abajo"))
    # ---- zona del panel (E3.6e)
    sumF = sum(b["Muc"] / (b["d"] - b["tf"]) for b in beams)
    Vc = Mpb / H if H > 0 else 0.0
    Ru = max(sumF - Vc, 0.0)
    db_ = max(b["d"] for b in beams)
    base = 0.60 * cm.Fy * dc * twc
    amp = 1.0 + 3.0 * bfc * tfc ** 2 / (db_ * dc * twc)
    Rv = base * amp * (1.0 if Prc <= 0.75 * Py else max(1.9 - 1.2 * Prc / Py, 0.0))
    note = (f"Ru = ΣMf/(d − tf) − Vc = {sumF:.0f} − {Vc:.0f} kip (Vc = ΣM*pb/H, H = {H:.0f} in); Rv = 0.60·Fy·dc·tw·(1 + 3·bcf·tcf²/(db·dc·tw)) = {Rv:.0f} kip"
            + (" (Prc > 0.75·Py: reducido)" if Prc > 0.75 * Py else ""))
    if Ru > Rv:
        tdp = (Ru - Rv) / (0.60 * cm.Fy * dc * amp)
        note += f"; hace falta una placa adosada (doubler) de unos {tdp:.3f} in ({math.ceil(tdp * 16) / 16:g} in) además del alma"
    _ck(out, "smf_pz", "Zona del panel — cortante con la deformación del panel (φv = 1.0)", Ru, Rv, "kip", "AISC 341-22 E3.6e.1; AISC 360-22 J10.6(b)", note)
    dz = max(b["d"] - 2 * b["tf"] for b in beams)
    wz = dc - 2 * tfc
    _ck(out, "smf_pzt", "Zona del panel — espesor del alma t ≥ (dz + wz)/90", (dz + wz) / 90.0, twc, "in", "AISC 341-22 E3.6e.2",
        f"dz = {dz:.2f} in, wz = {wz:.2f} in; si se agrega una placa adosada, también ella debe cumplirlo (o soldarse al alma con tapones)")
    # ---- placas de continuidad (detalle)
    from ..specs import OP_CONT
    tbf = max(b["tf"] for b in beams)
    bbf = max(b["bf"] for b in beams)
    Fsu = 0.0
    for b in beams:
        I = {}
        design(b["it"].spec, 0.0, 0.0, None, None, I)
        Fsu = max(Fsu, I.get("Fsu", 0.0))
    conts = [o for o in nd.operations if o.kind == OP_CONT and o.member in {b["name"] for b in beams}]
    if not conts:
        if Fsu > 0:
            _ck(out, "smf_cp_req", "Placas de continuidad requeridas (Fsu > 0) y no modeladas", Fsu, 0.0, "kip", "DG4 pasos 15–19; AISC 341-22 E3.6f",
                "agregue la operación «Placas de continuidad» a la viga")
        return out
    t = max(o.cont_t for o in conts)
    w = max(o.weld_size for o in conts)
    Fyp = 36.0                                                        # las placas de continuidad se arman en ASTM A36
    bs = (bfc - twc) / 2.0
    treq = (1.0 if two_sided else 0.5) * tbf
    _ck(out, "smf_cp_t", f"Placas de continuidad — espesor ≥ {'tbf (vigas a los dos lados)' if two_sided else '0.5·tbf (viga de un lado)'}", treq, t, "in", "AISC 341-22 E3.6f.2")
    _ck(out, "smf_cp_b", "Placas de continuidad — ancho bs + twc/2 ≥ bbf/3", bbf / 3.0, bs + twc / 2.0, "in", "AISC 360-22 J10.8(1)", f"bs = (bfc − twc)/2 = {bs:.2f} in")
    _ck(out, "smf_cp_t16", "Placas de continuidad — espesor ≥ bs/16", bs / 16.0, t, "in", "AISC 360-22 J10.8(2)")
    _ck(out, "smf_cp_bt", "Placas de continuidad — esbeltez bs/t ≤ 0.56·√(E/Fy)", bs / t, 0.56 * math.sqrt(E_ST / Fyp), "-", "AISC 360-22 Tabla B4.1a (caso 1)")
    Lw = max(dc - 2 * tfc - 2 * 0.75, 1.0)                           # soldadura al alma, descontando recortes de 3/4 in en las esquinas
    _ck(out, "smf_cp_ww", "Placas de continuidad — soldadura al alma (filetes a ambos lados de cada placa)", Fsu, 2 * 2 * 1.392 * (w * 16.0) * Lw, "kip", "AISC 360-22 J2.4 (E70)",
        f"2 placas × 2 filetes de {w:g} in × {Lw:.2f} in (con recortes de 3/4 in)")
    _ck(out, "smf_cp_wf", "Placas de continuidad — soldadura a las alas de la columna", 0.0, 1.0, "-", "AISC 341-22 E3.6f.3",
        "en un pórtico especial van con soldadura de penetración completa (CJP) a las alas de la columna", skip=True)
    return out
