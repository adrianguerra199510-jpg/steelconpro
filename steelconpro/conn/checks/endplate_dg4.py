# -*- coding: utf-8 -*-
"""Placa extrema extendida precalificada según AISC Design Guide 4, 2.ª ed. (Murray y Sumner, 2003): «Extended End-Plate Moment
Connections — Seismic and Wind Applications».  Configuraciones 4E (4 pernos sin rigidizar), 4ES (4 pernos rigidizada) y 8ES (8 pernos
rigidizada), con el procedimiento de diseño del capítulo 3 (pasos 1 a 20) y las tablas 3.1 a 3.7:

  1. Momento de diseño: sísmico, Muc = Mpe + Vu·Lp con Mpe = 1.1·Ry·Fy·Zx (3.1, 3.2), Lp = min(d/2, 3·bf) (4E) o Lst + tp (4ES, 8ES);
     no sísmico (viento / gravedad), Muc = el momento factorizado de cada caso.
  3–4. Pernos sin palanca: φMnp = φ·2·Pt·Σh, φ = 0.75 (3.7, 3.8).
  5–6. Espesor de la placa por líneas de fluencia: tp,req = √(1.11·φ·Mnp / (φb·Fyp·Yp)) (3.10), Yp de las tablas 3.1–3.3.
  7–9. Fuerza del ala Ffu = Muc/(d − tf) (3.11); en la 4E, cortante en la extensión (3.12, 3.13).
  10. Rigidizador (4ES, 8ES): ts ≥ tw·Fyb/Fys (3.15), esbeltez hst/ts ≤ 0.56·√(E/Fys) (3.16), Lst = hst/tan 30°.
  11–12. Pernos del lado comprimido: cortante (3.17) y aplastamiento / desgarramiento en la placa y en el ala de la columna (3.18, 3.19).
  13. Soldaduras del alma (y del ala si es de filete).
  14–19. Columna: flexión del ala por líneas de fluencia (3.20, tablas 3.4 y 3.5, con o sin placas de continuidad), fluencia local del alma
      (3.24), pandeo del alma (3.26, 3.27), aplastamiento del alma (3.29–3.31) y fuerza de las placas de continuidad (3.32).
  20. Zona del panel: AISC 360-22 J10.6(a) (DG4 remite a la Design Guide 13 y a AISC 341).
Rango de parámetros ensayados: tabla 3.6 (cíclico, diseño sísmico) o 3.7 (monotónico).

Validado contra los ejemplos 4.2 (4E A y B), 4.3 (4ES) y 4.4 (8ES) de la guía (selftest_dg4.py).  Diferencia: el cortante de los pernos usa
Fnv de AISC 360-22 (A325-N 54 ksi, A490-N 68 ksi); los ejemplos usan las de AISC 1999 (48 y 60 ksi).
"""
from __future__ import annotations
import math
from dataclasses import dataclass

from ... import materials as M
from ...shapes import CATALOG
from ..common import FNT, FNV, bolt_db
from ...design import Check
from .base import add_check, not_evaluated

E_ST = 29000.0
TYPES = ("4E", "4ES", "8ES")
# geometría por omisión (la de los ejemplos de la guía): pfo, pfi, pb, de (in)
GEOM_DEFAULT = {"4E": (2.0, 2.0, 0.0, 1.625), "4ES": (2.0, 2.0, 0.0, 1.625), "8ES": (1.75, 1.75, 3.0, 1.25)}
# Tabla 3.6 (cíclico) y 3.7 (monotónico): (mín, máx) en in
RANGES = {
    True: {"4E": {"tp": (0.50, 2.25), "bp": (7.00, 10.625), "g": (4.00, 6.00), "pf": (1.50, 4.50), "d": (25.0, 55.0), "tf": (0.375, 0.75), "bf": (6.00, 9.25), "db": (0.875, 1.25)},
           "4ES": {"tp": (0.50, 1.375), "bp": (10.625, 10.625), "g": (3.25, 6.00), "pf": (1.625, 5.375), "d": (13.75, 24.0), "tf": (0.375, 0.75), "bf": (6.00, 9.00), "db": (1.00, 1.25)},
           "8ES": {"tp": (0.75, 2.50), "bp": (9.00, 15.0), "g": (5.00, 6.00), "pf": (1.625, 2.00), "pb": (3.50, 3.75), "d": (18.375, 36.0), "tf": (0.625, 1.00), "bf": (7.625, 12.25), "db": (1.125, 1.25)}},
    False: {"4E": {"tp": (0.375, 2.25), "bp": (5.00, 10.625), "g": (2.50, 7.00), "pf": (1.25, 4.50), "d": (10.0, 63.875), "tf": (0.25, 1.00), "bf": (4.00, 10.25), "db": (0.50, 1.25)},
            "4ES": {"tp": (0.375, 1.375), "bp": (8.00, 10.625), "g": (2.75, 6.00), "pf": (1.00, 5.375), "d": (13.75, 24.0), "tf": (0.375, 0.75), "bf": (6.00, 9.00), "db": (0.625, 1.25)},
            "8ES": {"tp": (0.75, 2.50), "bp": (9.00, 15.0), "g": (5.00, 6.00), "pf": (1.375, 2.00), "pb": (2.75, 3.75), "d": (18.375, 36.0), "tf": (0.625, 1.00), "bf": (7.625, 12.25), "db": (0.875, 1.25)}},
}


@dataclass
class DG4:
    typ: str = "4E"
    beam: str = "W21X55"
    beam_steel: str = "ASTM A992"
    col: str = "W14X109"
    col_steel: str = "ASTM A992"
    plate_steel: str = "ASTM A572 Gr.50"
    bolt_size: str = "1"
    bolt_grade: str = "A325-N"
    bp: float = 9.0
    g: float = 5.5
    tp: float = 0.875
    pfo: float = 0.0                  # 0 = por omisión del tipo
    pfi: float = 0.0
    pb: float = 0.0
    de: float = 0.0
    ts: float = 0.0                   # espesor del rigidizador de la placa (0 = el requerido, redondeado a 1/16)
    stiff_steel: str = "ASTM A572 Gr.50"
    flange_weld: str = "CJP"          # «CJP» o «Filete»
    flange_w: float = 0.0             # cateto del filete del ala (si es filete)
    web_w: float = 0.3125             # cateto del filete del alma (a ambos lados)
    cont_plates: bool = False
    cont_t: float = 0.5
    col_top: bool = False             # la columna termina en el nudo (ala de la viga a menos de d de su extremo)
    seismic: bool = True
    Ry: float = 1.1
    Lh: float = 0.0                   # distancia entre rótulas (in); 0 = no se da
    Vg: float = 0.0                   # cortante de gravedad en la rótula (kip)

    def geom(self):
        p = GEOM_DEFAULT[self.typ]
        return (self.pfo or p[0], self.pfi or p[1], (self.pb or p[2]) if self.typ == "8ES" else 0.0, self.de or p[3])


def rows_of(typ: str, d: float, tf: float, pfo: float, pfi: float, pb: float) -> list:
    """Posición de las filas de pernos respecto del centro de la viga (+ arriba), simétricas (diseño para inversión de carga)."""
    out = [d / 2 + pfo, d / 2 - tf - pfi]
    if typ == "8ES":
        out = [d / 2 + pfo + pb, d / 2 + pfo, d / 2 - tf - pfi, d / 2 - tf - pfi - pb]
    return out + [-y for y in out]


def stiffener_dims(typ, pfo, pb, de):
    """(hst, Lst) del rigidizador de la placa (4ES: pfo + de; 8ES: pfo + pb + de; Lst = hst / tan 30°)."""
    hst = pfo + de + (pb if typ == "8ES" else 0.0)
    return hst, hst / math.tan(math.radians(30.0))


def _yp(typ, bp, g, h, pfo, pfi, pb, de, s):
    if typ == "4E":
        h0, h1 = h
        return bp / 2 * (h1 * (1 / pfi + 1 / s) + h0 * (1 / pfo) - 0.5) + 2 / g * (h1 * (pfi + s))
    if typ == "4ES":
        h0, h1 = h
        if de <= s:
            return bp / 2 * (h1 * (1 / pfi + 1 / s) + h0 * (1 / pfo + 1 / (2 * s))) + 2 / g * (h1 * (pfi + s) + h0 * (de + pfo))
        return bp / 2 * (h1 * (1 / pfi + 1 / s) + h0 * (1 / s + 1 / pfo)) + 2 / g * (h1 * (pfi + s) + h0 * (s + pfo))
    h1, h2, h3, h4 = h
    if de <= s:
        a = h1 * (1 / (2 * de)) + h2 * (1 / pfo) + h3 * (1 / pfi) + h4 * (1 / s)
        b = h1 * (de + pb / 4) + h2 * (pfo + 3 * pb / 4) + h3 * (pfi + pb / 4) + h4 * (s + 3 * pb / 4) + pb ** 2
    else:
        a = h1 * (1 / s) + h2 * (1 / pfo) + h3 * (1 / pfi) + h4 * (1 / s)
        b = h1 * (s + pb / 4) + h2 * (pfo + 3 * pb / 4) + h3 * (pfi + pb / 4) + h4 * (s + 3 * pb / 4) + pb ** 2
    return bp / 2 * a + 2 / g * b + g


def _yc(typ, bfc, g, h, c, pb, s, stiff, pso=0.0, psi=0.0):
    if typ in ("4E", "4ES"):
        h0, h1 = h
        if not stiff:
            return bfc / 2 * (h1 / s + h0 / s) + 2 / g * (h1 * (s + 3 * c / 4) + h0 * (s + c / 4) + c ** 2 / 2) + g / 2
        return bfc / 2 * (h1 * (1 / s + 1 / psi) + h0 * (1 / s + 1 / pso)) + 2 / g * (h1 * (s + psi) + h0 * (s + pso))
    h1, h2, h3, h4 = h
    if not stiff:
        return bfc / 2 * (h1 / s + h4 / s) + 2 / g * (h1 * (pb + c / 2 + s) + h2 * (pb / 2 + c / 4) + h3 * (pb / 2 + c / 2) + h4 * s) + g / 2
    return (bfc / 2 * (h1 / s + h2 / pso + h3 / psi + h4 / s)
            + 2 / g * (h1 * (s + pb / 4) + h2 * (pso + 3 * pb / 4) + h3 * (psi + pb / 4) + h4 * (s + 3 * pb / 4) + pb ** 2) + g)


def check_input(st) -> list:
    beam, col = CATALOG.get(st.beam), CATALOG.get(st.col)
    if beam is None or beam.kind != "W":
        return [f"** La viga «{st.beam}» debe ser un perfil I (W) del catálogo. **"]
    if col is None or col.kind != "W":
        return [f"** La columna «{st.col}» debe ser un perfil I (W) del catálogo. **"]
    if st.typ not in TYPES:
        return [f"** Tipo de placa extrema «{st.typ}» desconocido (4E, 4ES, 8ES). **"]
    if st.bolt_grade[:4] not in ("A325", "A490"):
        return ["** DG4 precalifica pernos ASTM A325 o A490 pretensados. **"]
    return []


def design(st, Mu_case=0.0, Vu_case=0.0, rec=None, us=None, info=None) -> list:
    """Verificaciones DG4 para un caso de carga.  Sísmico: el momento de diseño no depende del caso (Mpe); el cortante en la rótula es
    2·Mpe/Lh + Vg (ficha de la viga) o, si no se dan, el del caso."""
    ck = []
    beam, col = CATALOG.get(st.beam), CATALOG.get(st.col)
    bm = M.find(M.SHAPE_STEELS, st.beam_steel)
    cm = M.find(M.SHAPE_STEELS, st.col_steel)
    pm = M.find(M.PLATE_STEELS, st.plate_steel, 1)
    sm = M.find(M.PLATE_STEELS, st.stiff_steel, 1)
    typ = st.typ
    d, tf, bf, tw, Zx = beam.d, beam.tf, beam.bf, beam.tw, beam.Zx
    dc, tfc, bfc, twc, kc = col.d, col.tf, col.bf, col.tw, (col.kdes if col.kdes > 0 else col.tf + 0.5)
    pfo, pfi, pb, de = st.geom()
    db = bolt_db(st.bolt_size)
    dh = db + 1.0 / 16.0
    Ab = math.pi * db ** 2 / 4.0
    Ft = FNT[st.bolt_grade]
    Fv = FNV[st.bolt_grade]
    tp, bp, g = st.tp, st.bp, st.g
    stiffened = typ in ("4ES", "8ES")
    hst, Lst = stiffener_dims(typ, pfo, pb, de) if stiffened else (0.0, 0.0)
    I = info if info is not None else {}

    # ---- 1. momento de diseño de la conexión
    if st.seismic:
        Mpe = 1.1 * st.Ry * bm.Fy * Zx
        Lp = min(d / 2.0, 3.0 * bf) if typ == "4E" else Lst + tp
        Vu = (2.0 * Mpe / st.Lh if st.Lh > 0 else 0.0) + abs(st.Vg)
        if Vu <= 0:
            Vu = abs(Vu_case)
        Muc = Mpe + Vu * Lp
        src = (f"Mpe = 1.1·Ry·Fy·Zx = 1.1·{st.Ry:g}·{bm.Fy:g}·{Zx:g} = {Mpe:.0f} kip·in; Lp = {Lp:.2f} in; Vu = {Vu:.1f} kip"
               + (" (2·Mpe/Lh + Vg)" if st.Lh > 0 else " (cortante de gravedad de la ficha)" if st.Vg else " (cortante del caso)"))
    else:
        Mpe, Lp, Vu = 0.0, 0.0, abs(Vu_case)
        Muc = abs(Mu_case)
        src = "momento factorizado del caso (diseño no sísmico)"
    I.update(Mpe=Mpe, Lp=Lp, Vu=Vu, Muc=Muc, hst=hst, Lst=Lst)
    if rec:
        rec.section(f"PLACA EXTREMA {typ} — AISC DESIGN GUIDE 4 (2.ª ed.)")
        rec.text(f"Viga {st.beam} ({st.beam_steel}), columna {st.col} ({st.col_steel}); placa {bp:g} × {tp:g} in {st.plate_steel}; pernos Ø{st.bolt_size} {st.bolt_grade}; "
                 f"g = {g:g}, pfo = {pfo:g}, pfi = {pfi:g}" + (f", pb = {pb:g}" if typ == "8ES" else "") + f", de = {de:g} in.")
        if st.seismic:
            rec.add("Mpe", "1.1·Ry·Fy·Zx", f"1.1·{st.Ry:g}·{bm.Fy:g}·{Zx:g}", Mpe, "M", "DG4 (3.2)")
            rec.add("Lp", "min(d/2, 3bf)" if typ == "4E" else "Lst + tp", "", Lp, "L", "DG4 (3.3), (3.4)")
            rec.add("Vu", "2·Mpe/Lh + Vg" if st.Lh > 0 else "cortante en la rótula", "", Vu, "F")
        rec.add("Muc", "Mpe + Vu·Lp" if st.seismic else "momento del caso", "", Muc, "M", "DG4 (3.1)")

    # ---- brazos de las filas traccionadas (desde el centroide del ala comprimida)
    if typ == "8ES":
        h = (d + pfo + pb - tf / 2, d + pfo - tf / 2, d - tf - pfi - tf / 2, d - tf - pfi - pb - tf / 2)
    else:
        h = (d + pfo - tf / 2, d - tf - pfi - tf / 2)
    # ---- 3–4. pernos sin palanca
    Pt = Ft * Ab
    Mnp = 2.0 * Pt * sum(h)
    dreq = math.sqrt(2.0 * Muc / (math.pi * 0.75 * Ft * sum(h)))
    I.update(h=h, Pt=Pt, Mnp=Mnp, phiMnp=0.75 * Mnp, db_req=dreq)
    add_check(ck, rec, "dg4_db", "Pernos sin palanca — φMnp = φ·2·Pt·Σh ≥ Muc", Muc, 0.75 * Mnp, "kip·in", "DG4 (3.7)/(3.8), φ = 0.75",
              f"{src}; Σh = {sum(h):.2f} in; db requerido = {dreq:.3f} in (3.5/3.6)")
    # ---- 5–6. espesor de la placa
    s = 0.5 * math.sqrt(bp * g)
    pfi_e = min(pfi, s)
    Yp = _yp(typ, bp, g, h, pfo, pfi_e, pb, de, s)
    tp_req = math.sqrt(1.11 * 0.75 * Mnp / (0.9 * pm.Fy * Yp))
    I.update(s=s, Yp=Yp, tp_req=tp_req)
    add_check(ck, rec, "dg4_tp", "Espesor de la placa por líneas de fluencia — tp,req ≤ tp", tp_req, tp, "in", "DG4 (3.10), tabla " + {"4E": "3.1", "4ES": "3.2", "8ES": "3.3"}[typ],
              f"Yp = {Yp:.1f} in; s = {s:.2f} in" + (f"; caso {'1 (de ≤ s)' if de <= s else '2 (de > s)'}" if stiffened else "") + "; placa gruesa: los pernos no tienen palanca")
    # ---- 7. fuerza del ala
    Ffu = Muc / (d - tf)
    I["Ffu"] = Ffu
    if rec:
        rec.add("Ffu", "Muc/(d − tf)", "", Ffu, "F", "DG4 (3.11)")
    # ---- 8–9. cortante en la extensión (4E)
    if typ == "4E":
        I.update(ext_y=0.9 * 0.6 * pm.Fy * bp * tp, ext_r=0.75 * 0.6 * pm.Fu * (bp - 2.0 * (db + 0.125)) * tp)
        add_check(ck, rec, "dg4_exty", "Extensión de la placa — fluencia por cortante (Ffu/2)", Ffu / 2, 0.9 * 0.6 * pm.Fy * bp * tp, "kip", "DG4 (3.12), φ = 0.90")
        An = (bp - 2.0 * (db + 0.125)) * tp
        add_check(ck, rec, "dg4_extr", "Extensión de la placa — rotura por cortante (Ffu/2)", Ffu / 2, 0.75 * 0.6 * pm.Fu * An, "kip", "DG4 (3.13), φ = 0.75",
                  f"An = {An:.2f} in²")
    # ---- 10. rigidizador de la placa
    if stiffened:
        ts_req = tw * bm.Fy / sm.Fy
        ts_bk = 1.79 * hst * math.sqrt(sm.Fy / E_ST)
        ts = st.ts if st.ts > 0 else math.ceil(max(ts_req, ts_bk) * 16.0 - 1e-9) / 16.0
        I.update(ts_req=ts_req, ts_bk=ts_bk, ts=ts, slender=hst / ts, slender_lim=0.56 * math.sqrt(E_ST / sm.Fy))
        add_check(ck, rec, "dg4_ts", "Rigidizador de la placa — espesor ts ≥ tw·Fyb/Fys", ts_req, ts, "in", "DG4 (3.15)", f"hst = {hst:.3f} in, Lst = hst/tan 30° = {Lst:.2f} in")
        add_check(ck, rec, "dg4_tsb", "Rigidizador de la placa — esbeltez hst/ts ≤ 0.56·√(E/Fys)", hst / ts, 0.56 * math.sqrt(E_ST / sm.Fy), "-", "DG4 (3.16)",
                  f"ts = {ts:g} in" + ("; con ts > 3/8 in las soldaduras del rigidizador deben ser CJP" if ts > 0.375 + 1e-9 else "; filetes que desarrollen el rigidizador"))
    # ---- 11. cortante de los pernos del lado comprimido
    nb = 8 if typ == "8ES" else 4
    I["bolt_shear"] = 0.75 * nb * Fv * Ab
    add_check(ck, rec, "dg4_bv", f"Pernos del lado comprimido — cortante ({nb} pernos)", Vu, 0.75 * nb * Fv * Ab, "kip", "DG4 (3.17); Fnv de AISC 360-22 Tabla J3.2",
              f"Fnv = {Fv:g} ksi")
    # ---- 12. aplastamiento / desgarramiento en la placa y en el ala de la columna
    brg = 2.4 * db * tp * pm.Fu
    if typ == "8ES":
        r_a = min(1.2 * (pb - dh) * tp * pm.Fu, brg)                       # filas con otra fila a pb en la dirección de la fuerza
        r_b = min(1.2 * (pfo + tf + pfi - dh) * tp * pm.Fu, brg)           # filas a cada lado del ala
        phiRn = 4 * 0.75 * r_a + 4 * 0.75 * r_b
        nt = f"Rn = {r_a:.1f} kip (4 pernos, Lc = pb − dh) y {r_b:.1f} kip (4 pernos)"
    else:
        r_o = min(1.2 * (pfo + tf + pfi - dh) * tp * pm.Fu, brg)
        phiRn = 2 * 0.75 * r_o + 2 * 0.75 * brg
        nt = f"Rn = {r_o:.1f} kip (exteriores) y {brg:.1f} kip (interiores)"
    I["bearing"] = phiRn
    add_check(ck, rec, "dg4_brp", "Pernos del lado comprimido — aplastamiento / desgarramiento en la placa", Vu, phiRn, "kip", "DG4 (3.18), (3.19)", nt)
    add_check(ck, rec, "dg4_brc", "Pernos del lado comprimido — aplastamiento en el ala de la columna", Vu, phiRn * (tfc / tp) * (cm.Fu / pm.Fu), "kip", "DG4 (3.18)",
              f"φRn de la placa × tfc/tp × Fuc/Fup")
    # ---- 13. soldaduras
    Dweb = max(0.6 * bm.Fy * tw / (2 * 1.392), Vu / (2 * 1.392 * (d / 2 - tf)))
    add_check(ck, rec, "dg4_ww", "Soldadura del alma a la placa (filetes a ambos lados)", Dweb / 16.0, st.web_w, "in", "DG4 paso 13; AISC J2.4 (E70)",
              "la mayor entre la que desarrolla la flexión del alma junto a los pernos (0.6·Fy·tw) y la que toma Vu en d/2 − tf")
    add_check(ck, rec, "dg4_wwmin", "Soldadura del alma — cateto mínimo", M.min_fillet(min(tw, tp)), st.web_w, "in", "AISC 360-22 Tabla J2.4")
    if str(st.flange_weld).startswith("CJP"):
        not_evaluated(ck, "dg4_wf", "Soldadura de las alas a la placa (CJP)", "DG4 paso 13 (figura 2.10)",
                      "CJP con metal de aporte compatible y el procedimiento de la figura 2.10 de la guía: desarrolla el ala.")
    else:
        Fw = max(Ffu, 0.6 * bm.Fy * bf * tf) if not st.seismic else Ffu
        Lw = bf + (bf - tw)
        add_check(ck, rec, "dg4_wf", "Soldadura de las alas a la placa (filetes)", Fw, 1.5 * 1.392 * st.flange_w * 16.0 * Lw, "kip", "DG4 paso 13; AISC J2.4 (carga transversal)",
                  f"L = bf + (bf − tw) = {Lw:.2f} in")
        if st.seismic:
            ck[-1].note += "; para diseño sísmico la guía usa soldaduras CJP en las alas"
    # ---- 14. flexión del ala de la columna
    sc = 0.5 * math.sqrt(bfc * g)
    c = pfo + tf + pfi
    Yc = _yc(typ, bfc, g, h, c, pb, sc, False)
    tfc_req = math.sqrt(1.11 * 0.75 * Mnp / (0.9 * cm.Fy * Yc))
    I.update(sc=sc, c=c, Yc=Yc, tfc_req=tfc_req)
    if st.cont_plates:
        pso = psi = min((c - st.cont_t) / 2.0, sc)
        Ycs = _yc(typ, bfc, g, h, c, pb, sc, True, pso, psi)
        tfc_s = math.sqrt(1.11 * 0.75 * Mnp / (0.9 * cm.Fy * Ycs))
        I.update(pso=pso, Ycs=Ycs, tfc_req_s=tfc_s)
        add_check(ck, rec, "dg4_cf", "Ala de la columna — flexión (líneas de fluencia, con placas de continuidad)", tfc_s, tfc, "in", "DG4 (3.20), tabla " + ("3.4" if typ != "8ES" else "3.5"),
                  f"Yc = {Ycs:.1f} in con pso = psi = {pso:.2f} in; sin rigidizar Yc = {Yc:.1f} in, tfc,req = {tfc_req:.3f} in")
    else:
        add_check(ck, rec, "dg4_cf", "Ala de la columna — flexión (líneas de fluencia, sin rigidizar)", tfc_req, tfc, "in", "DG4 (3.20), tabla " + ("3.4" if typ != "8ES" else "3.5"),
                  f"Yc = {Yc:.1f} in; si no cumple, agregue placas de continuidad")
    # ---- 15–18. demanda local en la columna (fuerza del ala vs ala y alma sin rigidizar)
    phiMcf = 0.9 * cm.Fy * Yc * tfc ** 2
    R15 = phiMcf / (d - tf)
    Ct = 0.5 if st.col_top else 1.0
    N = tf if str(st.flange_weld).startswith("CJP") else tf + 0.707 * st.flange_w
    R16 = 1.0 * Ct * (6 * kc + N + 2 * tp) * cm.Fy * twc
    hcl = dc - 2 * kc
    R17 = (0.9 * (12.0 if st.col_top else 24.0) * twc ** 3 * math.sqrt(E_ST * cm.Fy) / hcl)
    k_ = math.sqrt(E_ST * cm.Fy * tfc / twc)
    if not st.col_top:
        R18 = 0.75 * 0.80 * twc ** 2 * (1 + 3 * (N / dc) * (twc / tfc) ** 1.5) * k_
    elif N / dc <= 0.2:
        R18 = 0.75 * 0.40 * twc ** 2 * (1 + 3 * (N / dc) * (twc / tfc) ** 1.5) * k_
    else:
        R18 = 0.75 * 0.40 * twc ** 2 * (1 + (4 * N / dc - 0.2) * (twc / tfc) ** 1.5) * k_
    I.update(phiMcf=phiMcf, R15=R15, R16=R16, R17=R17, R18=R18)
    lims = [("Ala de la columna — resistencia equivalente φMcf/(d − tf)", "DG4 (3.21), (3.22)", R15, "dg4_c15"),
            ("Alma de la columna — fluencia local", "DG4 (3.24), φ = 1.0", R16, "dg4_c16"),
            ("Alma de la columna — pandeo por la fuerza de compresión", "DG4 (3.26)/(3.27), φ = 0.90", R17, "dg4_c17"),
            ("Alma de la columna — aplastamiento (crippling)", "DG4 (3.29)–(3.31), φ = 0.75", R18, "dg4_c18")]
    for title, ref, R, key in lims:
        if st.cont_plates:
            c_ = add_check(ck, rec, key, title + " (sin rigidizar)", Ffu, R, "kip", ref, "hay placas de continuidad: toman la diferencia (paso 19)")
            c_.skip = True
            c_.note = f"φRn = {R:.0f} kip vs Ffu = {Ffu:.0f} kip; " + ("las placas de continuidad toman la diferencia (paso 19)" if R < Ffu else "no hacen falta rigidizadores por este estado")
        else:
            add_check(ck, rec, key, title, Ffu, R, "kip", ref, "si no cumple, hacen falta placas de continuidad")
    Rmin = min(R15, R16, R17, R18)
    Fsu = max(Ffu - Rmin, 0.0)
    I["Fsu"] = Fsu
    if st.cont_plates:
        bs = (bfc - twc) / 2.0
        add_check(ck, rec, "dg4_cp", "Placas de continuidad — fuerza Fsu = Ffu − min φRn ≤ φ·Fy·As", Fsu, 0.9 * 36.0 * 2 * bs * st.cont_t, "kip", "DG4 (3.32); AISC J10.8",
                  f"min φRn = {Rmin:.0f} kip; As = 2·{bs:.2f}·{st.cont_t:g} in²; el detalle (DG13: soldaduras, esbeltez) se verifica aparte")
    elif Fsu > 0:
        ck[-1].note += f"; Fsu = Ffu − min φRn = {Fsu:.0f} kip"
    # ---- 20. zona del panel (AISC 360-22 J10.6(a), sin el cortante de la columna: conservador)
    if st.seismic:
        not_evaluated(ck, "dg4_pz", "Zona del panel (diseño sísmico)", "AISC 341-22 E3.6e",
                      "se verifica en el nudo (grupo «Nudo de pórtico especial»), con todas las vigas que llegan a la columna")
    else:
        add_check(ck, rec, "dg4_pz", "Zona del panel — cortante (Ffu, conexión a un lado)", Ffu, 0.9 * 0.6 * cm.Fy * dc * twc, "kip", "AISC 360-22 J10.6(a), φ = 0.90 (DG4 paso 20)",
                  "sin descontar el cortante de la columna (conservador); el diseño sísmico de la zona del panel de AISC 341 E3.6e se verifica aparte")
    # ---- rango ensayado (tabla 3.6 / 3.7)
    rg = RANGES[bool(st.seismic)][typ]
    vals = {"tp": tp, "bp": bp, "g": g, "pf": None, "pb": pb if typ == "8ES" else None, "d": d, "tf": tf, "bf": bf, "db": db}
    out = []
    for k, (lo, hi) in rg.items():
        if k == "pf":
            for nm, v in (("pfo", pfo), ("pfi", pfi)):
                if not (lo - 1e-6 <= v <= hi + 1e-6):
                    out.append(f"{nm} = {v:g} (ensayado {lo:g}–{hi:g})")
            continue
        v = vals.get(k)
        if v is not None and not (lo - 1e-6 <= v <= hi + 1e-6):
            out.append(f"{k} = {v:g} (ensayado {lo:g}–{hi:g})")
    I["out_of_range"] = out
    ck.append(Check("dg4_rng", f"Parámetros dentro del rango ensayado (tabla {'3.6, cíclico' if st.seismic else '3.7, monotónico'})", 0.0, 1.0, "-", "DG4 3.4",
                    ("FUERA DEL RANGO ENSAYADO: " + "; ".join(out) + ". La guía advierte que salirse del rango puede cambiar el mecanismo de falla.")
                    if out else "todos dentro del rango ensayado", skip=True))
    return ck


def solve_one(p, name, vals, rec):
    """Interfaz de motor de verificación (adapters): vals = (Mu, Vu) del caso."""
    st = p.dg4
    Mu, Vu = (vals + (0.0, 0.0))[:2]
    return design(st, Mu, Vu, rec, p.units() if hasattr(p, "units") else None)


def warnings(st) -> list:
    """Avisos fijos de la conexión (rango ensayado, alcance)."""
    I = {}
    try:
        design(st, 0.0, 0.0, None, None, I)
    except Exception:                                                  # noqa: BLE001
        return []
    w = []
    if I.get("out_of_range"):
        w.append(f"Placa extrema {st.typ} (DG4): fuera del rango ensayado de la tabla {'3.6' if st.seismic else '3.7'}: " + "; ".join(I["out_of_range"]) + ".")
    w.append(f"Placa extrema {st.typ} según AISC Design Guide 4 (2.ª ed.): " + ("diseño sísmico con Mpe = 1.1·Ry·Fy·Zx" if st.seismic else "diseño no sísmico con el momento de cada caso")
             + ("; zona del panel, columna fuerte–viga débil y placas de continuidad: AISC 341-22 en el nudo." if st.seismic else "; zona del panel con AISC 360-22 J10.6(a)."))
    return w
