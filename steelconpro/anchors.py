# -*- coding: utf-8 -*-
"""
Anclajes: acero (AISC 360 J3) y concreto (ACI 318-19 Cap. 17).
Unidades internas: in, kip, ksi.  Las ecuaciones de ACI se evaluan en
lb/psi/in y el resultado se convierte a kip de forma explicita.
"""
from __future__ import annotations
import math

from .model import Project
from . import geometry as G
from . import materials as MAT
from .explain import Recorder
from .design import Check, Bearing
from .ubar import ubar


def _sqrt_fc_psi(fc_ksi: float) -> float:
    return math.sqrt(max(fc_ksi, 1e-6) * 1000.0)


def anchor_checks(prj: Project, br: Bearing,
                  rec: Recorder | None = None, fem=None) -> list[Check]:
    b, c, L = prj.bolts, prj.conc, prj.eloads
    g = b.geom()
    mat = b.mat()
    u = prj.units()
    out: list[Check] = []

    pos = G.bolt_positions(prj)
    n_tot = max(1, len(pos))
    grp, n_t, f_arm, xtmin, xtmax, ytmin, ytmax = G.tension_group(prj, pos)
    n_t = max(1, n_t)

    Nua = br.Tu                      # traccion total del grupo, kip
    Nua_b = Nua / n_t
    elastic = False
    if br.case == "TRACCION NETA" and pos:
        # la placa no apoya: reparto elastico entre TODOS los pernos,
        # T_i = |Pu|/n + Mux·y_i/Σy²  (solo los que quedan traccionados)
        n_all = len(pos)
        ym = sum(q[1] for q in pos) / n_all
        Iy = sum((q[1] - ym) ** 2 for q in pos)
        T = [abs(L.Pu) / n_all + (abs(L.Mux) * (q[1] - ym) / Iy if Iy > 1e-9 else 0.0)
             for q in pos]
        grp = [q for q, t in zip(pos, T) if t > 1e-9] or [pos[0]]
        Tpos = [t for t in T if t > 1e-9] or [0.0]
        n_t = len(grp)
        Nua = sum(Tpos)
        Nua_b = max(Tpos)
        xs_ = [q[0] for q in grp]; ys_ = [q[1] for q in grp]
        xtmin, xtmax, ytmin, ytmax = min(xs_), max(xs_), min(ys_), max(ys_)
        elastic = True
    linear_mode = False
    if fem is not None and getattr(fem.post, "bolts", None):
        # fuerza de cada perno del analisis solido 3D: el grupo traccionado son los pernos con T > 0
        tb = {k - 1: T for (k, x, y, T) in fem.post.bolts}
        Ts = [tb.get(i, 0.0) for i in range(len(pos))]
        if max(Ts, default=0.0) > 1e-9:
            grp = [q for q, t in zip(pos, Ts) if t > 1e-9]
            n_t = len(grp)
            Nua, Nua_b = sum(Ts), max(Ts)
            xs_ = [q[0] for q in grp]; ys_ = [q[1] for q in grp]
            xtmin, xtmax, ytmin, ytmax = min(xs_), max(xs_), min(ys_), max(ys_)
            elastic = True
            linear_mode = True
    Vua = 0.0 if prj.lug.enabled else prj.eloads.Vu
    if prj.eloads.friction and not prj.lug.enabled and L.Pu > 0:
        Vfric = prj.eloads.mu_fric * L.Pu
        Vua = max(0.0, Vua - Vfric)
    Vua_b = Vua / n_tot

    futa = min(mat.Fu, 1.9 * mat.Fy, 125.0)      # ACI 17.6.1.2 / 17.7.1.2
    phi_s_t = 0.75 if mat.ductile else 0.65
    phi_s_v = 0.65 if mat.ductile else 0.60
    phi_c = 0.75 if c.cond_A_eff else 0.70
    k_seis = 0.75 if c.seismic else 1.0

    # ---- anclaje postinstalado con adhesivo (ACI 318-19 17.6.5)
    adh = b.adhesive
    if adh:
        cat = {"Categoria 1": 0, "Categoria 2": 1, "Categoria 3": 2}.get(b.adh_cat, 0)
        phi_ct = ((0.75, 0.65), (0.65, 0.55), (0.55, 0.45))[cat][0 if c.cond_A_eff else 1]
        lam_brk = 0.8 * c.lam if c.lam < 1.0 else 1.0      # ACI Tabla 17.2.4.1
        lam_bond = 0.6 * c.lam if c.lam < 1.0 else 1.0
    else:
        phi_ct = phi_c
        lam_brk = c.lam

    # ---------------------------------------- distancia al borde disponible
    ca_x1 = max(0.0, c.B2 / 2.0 - xtmax)
    ca_x2 = max(0.0, c.B2 / 2.0 + xtmin)
    ca_y1 = max(0.0, c.N2 / 2.0 - ytmax)
    ca_min = max(0.5, min(ca_x1, ca_x2, ca_y1)
                 if not elastic else min(ca_x1, ca_x2, ca_y1, c.N2 / 2.0 + ytmin))
    sx = xtmax - xtmin
    sy = ytmax - ytmin

    if rec:
        rec.section("D.  PERNOS DE ANCLAJE — ACERO  (AISC 360 Cap. J3)")
        rec.add("Nua", "Tu (del equilibrio)", "", Nua, "F", "",
                "traccion total del grupo")
        if linear_mode:
            rec.add("Nua,perno", "Tmax del analisis solido 3D",
                    "ver seccion I: reaccion en los resortes de los pernos",
                    Nua_b, "F", "", "el grupo traccionado son los pernos con T > 0")
        elif elastic:
            rec.add("Nua,perno", "max( |Pu|/n + Mux·yi/Σy² )",
                    "traccion neta: reparto elastico entre todos los pernos",
                    Nua_b, "F")
        else:
            rec.add("Nua,perno", "Nua / n_t",
                    f"{rec.n('F', Nua)} / {n_t}", Nua_b, "F")
        rec.add("Vua", "Vu" + (" − μ·Pu (friccion)" if prj.eloads.friction
                               and not prj.lug.enabled else ""),
                ("cortante tomado por la llave de corte" if prj.lug.enabled else ""),
                Vua, "F")
        rec.add("Vua,perno", "Vua / n", f"{rec.n('F', Vua)} / {n_tot}", Vua_b, "F")

    # =============================================== AISC J3 — acero del perno
    Fnt = 0.75 * mat.Fu
    Fnv = 0.45 * mat.Fu                          # rosca incluida en el plano de corte
    phiRnt = 0.75 * Fnt * g.Ab
    phiRnv = 0.75 * Fnv * g.Ab
    out.append(Check("blt_t", "Perno — traccion (AISC J3)", Nua_b, phiRnt, "kip",
                     "AISC Tabla J3.2",
                     f"Fnt = 0.75·Fu = {u.q('S', Fnt)}, Ab = {u.q('A', g.Ab)}"))
    out.append(Check("blt_v", "Perno — cortante (AISC J3)", Vua_b, phiRnv, "kip",
                     "AISC Tabla J3.2",
                     ("Cortante tomado por la llave de corte." if prj.lug.enabled else
                      f"Fnv = 0.45·Fu = {u.q('S', Fnv)}, reparto uniforme entre {n_tot} pernos")))
    if rec:
        rec.add("Fnt", "0.75·futa", f"0.75·{rec.n('S', mat.Fu)}", Fnt, "S",
                "AISC Tabla J3.2")
        rec.add("φRnt", "φ·Fnt·Ab",
                f"0.75·{rec.n('S', Fnt)}·{rec.n('A', g.Ab)}", phiRnt, "F",
                "AISC Ec. J3-1", "resistencia a traccion de un perno")
        rec.add("Fnv", "0.45·futa", f"0.45·{rec.n('S', mat.Fu)}", Fnv, "S",
                "AISC Tabla J3.2", "rosca incluida en el plano de corte")
        rec.add("φRnv", "φ·Fnv·Ab",
                f"0.75·{rec.n('S', Fnv)}·{rec.n('A', g.Ab)}", phiRnv, "F")
        rec.check("Perno en traccion", Nua_b, phiRnt, "F",
                  Nua_b / phiRnt if phiRnt > 0 else 0, Nua_b <= phiRnt, "AISC J3.6")
        rec.check("Perno en cortante", Vua_b, phiRnv, "F",
                  Vua_b / phiRnv if phiRnv > 0 else 0, Vua_b <= phiRnv, "AISC J3.6")

    frv = Vua_b / g.Ab if g.Ab > 0 else 0.0
    rt = Nua_b / phiRnt if phiRnt > 0 else 0.0
    rv = Vua_b / phiRnv if phiRnv > 0 else 0.0
    if rt <= 0.30 or rv <= 0.30:
        out.append(Check("blt_tv", "Perno — interaccion traccion-cortante",
                         max(rt, rv), 1.0, "-", "AISC J3.7",
                         "No se requiere interaccion: una solicitacion <= 30% de su capacidad."))
    else:
        Fnt_p = max(0.0, min(1.3 * Fnt - (Fnt / (0.75 * Fnv)) * frv, Fnt))
        out.append(Check("blt_tv", "Perno — interaccion traccion-cortante",
                         Nua_b, 0.75 * Fnt_p * g.Ab, "kip", "AISC Ec. J3-3a",
                         f"F'nt = {u.q('S', Fnt_p)} con frv = {u.q('S', frv)}"))

    # ===================== flexion del perno por separacion libre (stand-off, tuercas de nivelacion)
    # El cortante que baja por el perno a traves de la separacion libre lo flexiona: voladizo desde la
    # superficie del concreto hasta el centro del espesor de la placa (la placa queda sujeta por las dos
    # tuercas).  Con doble empotramiento (placa que no gira) M = V·l/2; en voladizo M = V·l.
    so = max(0.0, float(getattr(b, "standoff", 0.0)))
    gr_t = max(0.0, float(getattr(prj.plate, "grout", 0.0)))
    l_gap = so + gr_t                     # tramo del perno sin apoyo lateral del concreto: separacion + mortero
    if l_gap > 0.5 * g.db and Vua_b > 1e-9:
        # un mortero delgado (<= medio diametro) queda cubierto por el factor 0.80 de ACI 17.7.1.2.1;
        # con mortero grueso o placa elevada se verifica la flexion del perno
        l_b = l_gap + 0.5 * prj.plate.tp
        k_fix = 0.5 if str(getattr(b, "fixity", "")).startswith("Doble") else 1.0
        Mu_b = Vua_b * l_b * k_fix
        d_e = (4.0 * g.Ase / 3.141592653589793) ** 0.5          # diametro de la seccion roscada
        Zb = d_e ** 3 / 6.0
        phiMn = 0.90 * mat.Fy * Zb                               # AISC F11 (seccion redonda, plastico)
        out.append(Check("blt_m", "Perno — flexion por separacion libre (stand-off)", Mu_b, phiMn, "kip·in",
                         "AISC F11 / DG1 §3.5",
                         f"l = stand-off {u.q('L', so)} + mortero {u.q('L', gr_t)} + tp/2 = {u.q('L', l_b)}; "
                         f"M = V·l·{k_fix:g}; Z = {Zb:.4g} in³, Fy = {u.q('S', mat.Fy)}"))
        # interaccion traccion + flexion (+ cortante como tension combinada)
        rt_m = Nua_b / phiRnt if phiRnt > 0 else 0.0
        rm = Mu_b / phiMn if phiMn > 0 else 0.0
        out.append(Check("blt_tm", "Perno — interaccion traccion-flexion", rt_m + rm, 1.0, "-",
                         "AISC H1-1a",
                         f"T/φTn = {rt_m:.3f} + M/φMn = {rm:.3f};  cortante Vb = {u.q('F', Vua_b)}"))
        if rec:
            rec.section("D2. FLEXION DEL PERNO (stand-off)")
            rec.add("l", "stand-off + mortero + tp/2",
                    f"{rec.n('L', so)} + {rec.n('L', gr_t)} + {rec.n('L', prj.plate.tp)}/2", l_b, "L",
                    "", "brazo libre entre el concreto y el centro de la placa")
            rec.add("Mu,perno", f"Vua,perno · l · {k_fix:g}", f"{rec.n('F', Vua_b)} · {rec.n('L', l_b)} · {k_fix:g}",
                    Mu_b, "M", "", str(b.fixity))
            rec.add("Z", "de³/6", f"({d_e:.4g})³/6", Zb, "-", "", "modulo plastico de la seccion roscada")
            rec.add("φMn", "0.90·Fy·Z", f"0.90·{rec.n('S', mat.Fy)}·{Zb:.4g}", phiMn, "M", "AISC F11")
            rec.check("Flexion del perno", Mu_b, phiMn, "M", rm, Mu_b <= phiMn, "AISC F11")
            rec.check("Interaccion traccion-flexion", rt_m + rm, 1.0, "-", rt_m + rm, rt_m + rm <= 1.0,
                      "AISC H1-1a")

    if rec:
        rec.section("E.  ANCLAJES AL CONCRETO  (ACI 318-19 Cap. 17)")
        rec.add("futa", "min( Fu ; 1.9·Fy ; 125 ksi )",
                f"min( {rec.n('S', mat.Fu)} ; 1.9·{rec.n('S', mat.Fy)} ; "
                f"{rec.n('S', 125.0)} )", futa, "S", "ACI 17.6.1.2")
        rec.add("Ase", "area efectiva a traccion", "", g.Ase, "A")
        rec.add("φ acero", "traccion / cortante",
                f"{phi_s_t:.2f} / {phi_s_v:.2f}", None, "-", "ACI Tabla 17.5.3(a)",
                "elemento " + ("ductil" if mat.ductile else "fragil"))
        rec.add("φ concreto", "condicion " + ("A" if c.cond_A_eff else "B"),
                f"{phi_c:.2f}", None, "-", "ACI Tabla 17.5.3(c)")
        if c.seismic:
            rec.add("factor sismico", "0.75 sobre la resistencia del concreto",
                    "", None, "-", "ACI 17.10.5.2")

    # ================================================ ACI 17.6.1 acero traccion
    Nsa = g.Ase * futa
    out.append(Check("aci_nsa", "Anclaje — acero en traccion (ACI 17.6.1)",
                     n_t * Nua_b, n_t * phi_s_t * Nsa, "kip", "ACI 318-19 Ec. 17.6.1.2",
                     f"Ase = {u.q('A', g.Ase)}, futa = {u.q('S', futa)}, n_t = {n_t}"))

    if rec:
        rec.add("Nsa", "Ase · futa",
                f"{rec.n('A', g.Ase)} · {rec.n('S', futa)}", Nsa, "F",
                "ACI Ec. 17.6.1.2")
        rec.check("Acero del anclaje en traccion (perno mas cargado)", Nua_b,
                  phi_s_t * Nsa, "F",
                  Nua_b / (phi_s_t * Nsa) if Nsa > 0 else 0,
                  Nua_b <= phi_s_t * Nsa, "ACI 17.6.1")

    # ============================= ACI 17.6.2 arrancamiento del concreto (traccion)
    hef = b.hef
    ANco = 9.0 * hef ** 2
    ca_y2 = max(0.0, c.N2 / 2.0 + ytmin)
    ANc = min(n_t * ANco,
              (min(1.5 * hef, ca_x1) + sx + min(1.5 * hef, ca_x2)) *
              (min(1.5 * hef, ca_y1) + sy + (min(1.5 * hef, ca_y2) if elastic
                                             else 1.5 * hef)))
    psi_ed = 1.0 if ca_min >= 1.5 * hef else 0.7 + 0.3 * ca_min / (1.5 * hef)
    psi_ec = 1.0
    fcp = _sqrt_fc_psi(c.fc)
    cac = 2.0 * hef                                   # ACI 17.9.3, adhesivo
    if adh:
        kc = 17.0                                     # ACI 17.6.2.2.1 postinstalado
        psi_c = 1.0 if c.cracked else 1.4             # ACI 17.6.2.5.1
        if c.cracked or ca_min >= cac:
            psi_cp = 1.0
        else:
            psi_cp = max(ca_min / cac, 1.5 * hef / cac)   # ACI 17.6.2.6.1
        Nb = kc * lam_brk * fcp * hef ** 1.5 / 1000.0
    else:
        kc = 24.0
        psi_c = 1.0 if c.cracked else 1.25
        psi_cp = 1.0
        if hef <= 11.0:
            Nb = 24.0 * c.lam * fcp * hef ** 1.5 / 1000.0
        else:
            Nb = 16.0 * c.lam * fcp * hef ** (5.0 / 3.0) / 1000.0
    Ncbg = (ANc / ANco) * psi_ed * psi_c * psi_cp * Nb
    if rec:
        rec.add("ANco", "9·hef²", f"9·{rec.n('L', hef)}²", ANco, "A",
                "ACI Ec. 17.6.2.1.4")
        rec.add("ANc", "(min(1.5hef,ca_x1)+sx+min(1.5hef,ca_x2)) · "
                       "(min(1.5hef,ca_y1)+sy+1.5hef)",
                f"({rec.n('L', min(1.5*hef, ca_x1))}+{rec.n('L', sx)}+"
                f"{rec.n('L', min(1.5*hef, ca_x2))}) · "
                f"({rec.n('L', min(1.5*hef, ca_y1))}+{rec.n('L', sy)}+"
                f"{rec.n('L', 1.5*hef)})", ANc, "A", "ACI 17.6.2.1",
                "area proyectada del grupo traccionado, limitada a n_t·ANco")
        rec.add("ψed,N", "1 si ca_min>=1.5hef ; si no 0.7+0.3·ca_min/(1.5hef)",
                f"ca_min = {rec.n('L', ca_min)}", psi_ed, "-", "ACI Ec. 17.6.2.4")
        rec.add("ψc,N", ("1.00 fisurado / 1.40 no fisurado (postinstalado)" if adh
                         else "1.00 fisurado / 1.25 no fisurado"), "", psi_c, "-",
                "ACI 17.6.2.5")
        if adh:
            rec.add("ψcp,N", "1 si fisurado o ca,min>=cac ; si no max(ca,min/cac ; 1.5hef/cac)",
                    f"cac = 2·hef = {rec.n('L', cac)} ; ca,min = {rec.n('L', ca_min)}",
                    psi_cp, "-", "ACI 17.6.2.6 / 17.9.3")
            rec.add("Nb", "kc·λa·√f'c·hef^1.5  (kc = 17, postinstalado)",
                    f"17·{lam_brk:.2f}·√{c.fc*1000:.0f}·{hef:.1f}^1.5 lb",
                    Nb, "F", "ACI Ec. 17.6.2.2.1",
                    "evaluada en unidades inglesas (psi, in) y convertida")
            rec.add("φ concreto (traccion)", f"{b.adh_cat}, condicion "
                    + ("A" if c.cond_A_eff else "B"), f"{phi_ct:.2f}", None, "-",
                    "ACI Tabla 17.5.3(c)")
        else:
            rec.add("Nb", ("kc·λa·√f'c·hef^1.5" if hef <= 11 else
                           "16·λa·√f'c·hef^(5/3)"),
                    f"{'24' if hef <= 11 else '16'}·{c.lam:.2f}·√{c.fc*1000:.0f}·"
                    f"{hef:.1f}^{'1.5' if hef <= 11 else '5/3'} lb",
                    Nb, "F", "ACI Ec. 17.6.2.2",
                    "evaluada en unidades inglesas (psi, in) y convertida")
        rec.add("Ncbg", "(ANc/ANco)·ψec·ψed·ψc·ψcp·Nb",
                f"({ANc/ANco:.3f})·{psi_ec:.2f}·{psi_ed:.3f}·{psi_c:.2f}·"
                f"{psi_cp:.2f}·{rec.n('F', Nb)}", Ncbg, "F")
        rec.check("Arrancamiento del concreto en traccion", Nua,
                  phi_ct * k_seis * Ncbg, "F",
                  Nua / (phi_ct * k_seis * Ncbg) if Ncbg > 0 else 0,
                  Nua <= phi_ct * k_seis * Ncbg, "ACI 17.6.2")
        _ub = ubar(prj)
        if _ub is not None:
            rec.section("E2. REFUERZO DEL ARRANCAMIENTO CON BARRAS "
                        + ("OMEGA (PATAS CON GANCHO)" if _ub["kind"] == "OMEGA" else "U (PATAS RECTAS)") + "  (ACI 318-19 17.5.2)")
            rec.add("barras " + _ub["kind"], f"{_ub['n']} {_ub['kind']} de {_ub['size']} (db = {_ub['db']:.3f} in, Ab = {_ub['Ab']:.2f} in²)",
                    f"{_ub['n_legs']} patas, fy = {rec.n('S', _ub['fy'])}", None, "-")
            rec.add("Nrs", "n_patas · Ab · fy", f"{_ub['n_legs']}·{_ub['Ab']:.2f}·{rec.n('S', _ub['fy'])}",
                    _ub["Nrs"], "F", "ACI 17.5.2.1")
            rec.check("Refuerzo U en traccion (φ = 0.75)", Nua, _ub["phi"] * _ub["Nrs"], "F",
                      Nua / (_ub["phi"] * _ub["Nrs"]), Nua <= _ub["phi"] * _ub["Nrs"], "ACI 17.5.2.1")
            rec.add("ld (pata recta)", "fy·ψt·ψe/(25 λ √f'c)·db  (20 si db > #6; min 12 in)", "", _ub["ld"], "L",
                    "ACI 25.4.2.3")
            rec.add("ldh (gancho)", "fy/(50 λ √f'c)·db  (min 8db, 6 in)", "", _ub["ldh"], "L", "ACI 25.4.3")
            rec.add("pata", f"sobre la punta del anclaje {rec.n('L', _ub['above'])} / bajo la punta del anclaje {rec.n('L', _ub['below'])}",
                    f"long. total = {rec.n('L', _ub['leg'])}", _ub["leg"], "L", "",
                    "seccion critica en la punta del anclaje (z = hef bajo la superficie); ld / ldh se miden de ahi hacia abajo")
            if _ub["kind"] == "OMEGA":
                rec.add("gancho", f"cola de 12·db hacia afuera, radio de doblez al eje {rec.n('L', _ub['rb'])}",
                        f"cola = {rec.n('L', _ub['tail'])}", _ub["tail"], "L", "ACI 25.3.1 / 25.4.3",
                        "bajo la punta del anclaje se desarrolla ldh (gancho estandar de 90°)")
    ub = ubar(prj)
    cap_ncb = phi_ct * k_seis * Ncbg
    if ub is not None:
        cap_ncb = max(cap_ncb, ub["phi"] * ub["Nrs"])          # ACI 17.5.2.1: el refuerzo sustituye al concreto
    out.append(Check("aci_ncb", "Anclaje — arrancamiento del concreto en traccion"
                     + (" (con refuerzo U)" if ub is not None else ""),
                     Nua, cap_ncb, "kip", "ACI 318-19 17.6.2" + (" / 17.5.2.1" if ub is not None else ""),
                     f"hef = {u.q('L', hef)}, ANc/ANco = {ANc/ANco:.2f}, ψed = {psi_ed:.2f}, "
                     f"ψc = {psi_c:.2f}, " + (f"ψcp = {psi_cp:.2f}, kc = 17, " if adh else "")
                     + f"Nb = {u.q('F', Nb)}"))

    # ============================= ACI 17.6.5 adherencia (anclaje adhesivo)
    Nag = None
    if adh:
        t_cr, t_uncr = b.bond_stress()
        table = not b.adh_env.startswith("Datos")
        f_red = ""
        t_cr_d, t_uncr_d = t_cr, t_uncr
        if table and b.sustained > 0:
            t_cr_d *= 0.4; t_uncr_d *= 0.4
            f_red = "×0.4 por traccion sostenida"
        if table and c.seismic:
            t_cr_d *= 0.8; t_uncr_d *= 0.4
            f_red += (" ; " if f_red else "") + "τcr×0.8, τuncr×0.4 por sismo (SDC C-F)"
        tau = t_cr_d if c.cracked else t_uncr_d
        da = g.db
        cNa = 10.0 * da * math.sqrt(t_uncr * 1000.0 / 1100.0)   # in (psi dentro de la raiz)
        ANao = (2.0 * cNa) ** 2
        ANa = min(n_t * ANao,
                  (min(cNa, ca_x1) + sx + min(cNa, ca_x2)) *
                  (min(cNa, ca_y1) + sy + (min(cNa, ca_y2) if elastic else cNa)))
        psi_edNa = 1.0 if ca_min >= cNa else 0.7 + 0.3 * ca_min / cNa
        if c.cracked or ca_min >= cac:
            psi_cpNa = 1.0
        else:
            psi_cpNa = max(ca_min / cac, cNa / cac)
        psi_ecNa = 1.0
        Nba = lam_bond * tau * math.pi * da * hef
        Nag = (ANa / ANao) * psi_ecNa * psi_edNa * psi_cpNa * Nba
        cap = phi_ct * k_seis * Nag
        out.append(Check("aci_na", "Anclaje adhesivo — resistencia de adherencia",
                         Nua, cap, "kip", "ACI 318-19 17.6.5",
                         f"τ{'cr' if c.cracked else 'uncr'} = {u.q('S', tau)}"
                         + (f" ({f_red})" if f_red else "")
                         + f", cNa = {u.q('L', cNa)}, ANa/ANao = {ANa/ANao:.2f}, "
                           f"ψed,Na = {psi_edNa:.2f}, ψcp,Na = {psi_cpNa:.2f}, "
                           f"Nba = {u.q('F', Nba)}, φ = {phi_ct:.2f} ({b.adh_cat})"))
        # traccion sostenida (17.5.2.2)
        if b.sustained > 0:
            Nuas = b.sustained * Nua_b
            out.append(Check("aci_nas", "Anclaje adhesivo — traccion sostenida",
                             Nuas, 0.55 * phi_ct * Nba, "kip", "ACI 318-19 17.5.2.2",
                             f"Nua,s = {b.sustained:.0%} de la traccion por perno; "
                             f"limite 0.55·φ·Nba"))
        # limites de embebido (17.3.4) y distancias minimas (17.9.2)
        out.append(Check("adh_hef", "Anclaje adhesivo — embebido minimo 4·da",
                         4.0 * da, hef, "in", "ACI 318-19 17.3.4",
                         f"4·da ≤ hef ≤ 20·da ; 20·da = {u.q('L', 20 * da)}"))
        if hef > 20.0 * da:
            out.append(Check("adh_hef2", "Anclaje adhesivo — embebido maximo 20·da",
                             hef, 20.0 * da, "in", "ACI 318-19 17.3.4",
                             "Fuera del rango calibrado de las ecuaciones de adherencia"))
        pos_all = pos
        s_min = min((math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                     for i, p1 in enumerate(pos_all) for p2 in pos_all[i + 1:]),
                    default=1e9)
        ca_all = min((min(c.B2 / 2.0 - abs(x), c.N2 / 2.0 - abs(y)) for x, y in pos_all),
                     default=1e9)
        out.append(Check("adh_min", "Anclaje adhesivo — separacion y borde minimos 6·da",
                         6.0 * da, min(s_min, ca_all), "in", "ACI 318-19 17.9.2",
                         f"s,min = {u.q('L', s_min)} ; borde al pedestal = {u.q('L', ca_all)} "
                         f"(salvo valores del producto segun ACI 355.4)"))
        if rec:
            rec.section("E2.  ANCLAJE POSTINSTALADO ADHESIVO — ADHERENCIA  (ACI 318-19 17.6.5)")
            rec.add("τcr / τuncr", ("Tabla 17.6.5.2.5, " + b.adh_env.split(",")[0].lower())
                    if table else "datos del producto (ESR)",
                    f"{rec.n('S', t_cr)} / {rec.n('S', t_uncr)}", None, "-",
                    "ACI 17.6.5.2.5", f_red or None)
            rec.add("τ", "τcr si fisurado ; τuncr si no fisurado", "", tau, "S")
            rec.add("cNa", "10·da·√(τuncr/1100)",
                    f"10·{rec.n('L', da)}·√({t_uncr*1000:.0f}/1100)", cNa, "L",
                    "ACI Ec. 17.6.5.1.2b", "τuncr en psi, cNa en in")
            rec.add("ANao", "(2·cNa)²", f"(2·{rec.n('L', cNa)})²", ANao, "A",
                    "ACI Ec. 17.6.5.1.2a")
            rec.add("ANa", "(min(cNa,ca_x1)+sx+min(cNa,ca_x2))·(min(cNa,ca_y1)+sy+cNa)",
                    "", ANa, "A", "ACI 17.6.5.1.1", "limitada a n_t·ANao")
            rec.add("ψed,Na", "1 si ca,min>=cNa ; si no 0.7+0.3·ca,min/cNa",
                    f"ca,min = {rec.n('L', ca_min)}", psi_edNa, "-", "ACI Ec. 17.6.5.4")
            rec.add("ψcp,Na", "1 si fisurado o ca,min>=cac ; si no max(ca,min/cac ; cNa/cac)",
                    f"cac = {rec.n('L', cac)}", psi_cpNa, "-", "ACI 17.6.5.5")
            rec.add("Nba", "λa·τ·π·da·hef",
                    f"{lam_bond:.2f}·{rec.n('S', tau)}·π·{rec.n('L', da)}·{rec.n('L', hef)}",
                    Nba, "F", "ACI Ec. 17.6.5.2.1")
            rec.add("Nag", "(ANa/ANao)·ψec,Na·ψed,Na·ψcp,Na·Nba",
                    f"({ANa/ANao:.3f})·1.00·{psi_edNa:.3f}·{psi_cpNa:.3f}·{rec.n('F', Nba)}",
                    Nag, "F", "ACI Ec. 17.6.5.1b")
            rec.check("Adherencia del anclaje adhesivo", Nua, cap, "F",
                      Nua / cap if cap > 0 else 0, Nua <= cap, "ACI 17.6.5")

    # ==================================== ACI 17.6.3 extraccion (pullout)
    Abrg = b.Abrg_user if b.Abrg_user > 0 else g.Abrg
    psi_cp_p = 1.0 if c.cracked else 1.4
    if b.atype.startswith("Con cabeza"):
        Np = 8.0 * Abrg * c.fc
        note = f"Cabeza hex pesada: Abrg = {u.q('A', Abrg)} (Ec. 17.6.3.2.2a)"
        skip = False
    elif "gancho" in b.atype.lower() or b.atype.startswith("Gancho"):
        eh = b.eh if b.eh > 0 else 3.0 * g.db
        eh = min(max(eh, 3.0 * g.db), 4.5 * g.db)
        Np = 0.9 * c.fc * eh * g.db
        note = (f"Gancho: eh = {u.q('L', eh)} (limitado a 3·db ≤ eh ≤ 4.5·db, Ec. 17.6.3.2.2b). "
                f"El gancho debe envolver una barra longitudinal o cumplir 17.6.3.2.2.")
        skip = False
    elif adh:
        Np = 0.0
        note = ("No aplica a anclajes adhesivos: la extraccion se sustituye por la "
                "resistencia de adherencia (ACI 17.6.5).")
        skip = True
    else:
        Np = 0.0
        note = ("VARILLA RECTA PREINSTALADA SIN CABEZA NI GANCHO: ACI 318-19 no reconoce "
                "resistencia a la extraccion. No es un anclaje valido a traccion; use "
                "cabeza, gancho, o instalacion postinstalada con adhesivo.")
        skip = (Nua <= 1e-9)
    if rec and not adh:
        rec.add("Np", ("8·Abrg·f'c" if b.atype.startswith("Con cabeza")
                       else ("0.9·f'c·eh·da" if b.atype.startswith("Gancho")
                             else "no aplica")),
                (f"8·{rec.n('A', Abrg)}·{rec.n('S', c.fc)}"
                 if b.atype.startswith("Con cabeza") else ""), Np, "F",
                "ACI 17.6.3.2.2", note)
        rec.add("ψc,P", "1.00 fisurado / 1.40 no fisurado", "", psi_cp_p, "-")
        rec.check("Extraccion (pullout)", Nua_b, phi_c * k_seis * psi_cp_p * Np, "F",
                  Nua_b / (phi_c * k_seis * psi_cp_p * Np) if Np > 0 else 0,
                  Np > 0 and Nua_b <= phi_c * k_seis * psi_cp_p * Np, "ACI 17.6.3")

    out.append(Check("aci_np", "Anclaje — extraccion por deslizamiento (pullout)",
                     Nua_b, phi_c * k_seis * psi_cp_p * Np, "kip",
                     "ACI 318-19 17.6.3", note, skip=skip))

    # ============================= ACI 17.6.4 desprendimiento lateral
    if b.atype.startswith("Con cabeza") and ca_min < 0.4 * hef:
        Nsb = 160.0 * ca_min * math.sqrt(Abrg) * c.lam * fcp / 1000.0
        if ca_x2 < 3.0 * ca_min:
            Nsb *= (1.0 + ca_x2 / ca_min) / 4.0
        out.append(Check("aci_nsb", "Anclaje — desprendimiento lateral (side-face blowout)",
                         Nua_b, phi_c * Nsb, "kip", "ACI 318-19 17.6.4",
                         f"Aplica porque ca_min = {u.q('L', ca_min)} < 0.4·hef = {u.q('L', 0.4*hef)}"))

    # ==================================== ACI 17.7.1 acero en cortante
    Vsa_1 = 0.6 * g.Ase * futa
    if b.atype.startswith("Gancho") or b.atype.startswith("Recto"):
        Vsa_1 = 0.6 * g.Ase * futa           # 17.7.1.2a (perno con gancho, sin cabeza)
    if prj.plate.grout > 0 and not prj.lug.enabled:
        Vsa_1 *= 0.80                        # ACI 17.7.1.2.1 mortero sin confinar
    out.append(Check("aci_vsa", "Anclaje — acero en cortante (ACI 17.7.1)",
                     Vua, n_tot * phi_s_v * Vsa_1, "kip", "ACI 318-19 17.7.1.2",
                     ("Cortante tomado por la llave de corte." if prj.lug.enabled else
                      "Incluye el factor 0.80 por mortero de nivelacion no confinado.")))

    if rec:
        rec.add("Vsa", "0.6·Ase·futa" + (" · 0.80 (mortero)"
                                         if prj.plate.grout > 0 and not prj.lug.enabled
                                         else ""),
                f"0.6·{rec.n('A', g.Ase)}·{rec.n('S', futa)}"
                + (" · 0.80" if prj.plate.grout > 0 and not prj.lug.enabled else ""),
                Vsa_1, "F", "ACI Ec. 17.7.1.2b")
        rec.check("Acero del anclaje en cortante", Vua, n_tot * phi_s_v * Vsa_1, "F",
                  Vua / (n_tot * phi_s_v * Vsa_1) if Vsa_1 > 0 else 0,
                  Vua <= n_tot * phi_s_v * Vsa_1, "ACI 17.7.1")

    # ============================ ACI 17.7.2 arrancamiento del concreto en cortante
    ca1 = ca_min
    le = min(hef, 8.0 * g.db)
    Vb1 = 7.0 * (le / g.db) ** 0.2 * math.sqrt(g.db) * c.lam * fcp * ca1 ** 1.5 / 1000.0
    Vb2 = 9.0 * c.lam * fcp * ca1 ** 1.5 / 1000.0
    Vb = min(Vb1, Vb2)
    Avco = 4.5 * ca1 ** 2
    Avc = (min(1.5 * ca1, ca_x1) + sx + min(1.5 * ca1, ca_x2)) * min(1.5 * ca1, c.ha)
    ca2min = min(ca_x1, ca_x2)
    psi_edV = 1.0 if ca2min >= 1.5 * ca1 else 0.7 + 0.3 * ca2min / (1.5 * ca1)
    psi_cV = 1.0 if c.cracked else 1.4
    psi_hV = math.sqrt(1.5 * ca1 / c.ha) if c.ha < 1.5 * ca1 else 1.0
    Vcbg = (Avc / Avco) * psi_edV * psi_cV * psi_hV * Vb
    if rec:
        rec.add("le", "min( hef ; 8·da )",
                f"min( {rec.n('L', hef)} ; 8·{rec.n('L', g.db)} )", le, "L")
        rec.add("Vb", "min[ 7·(le/da)^0.2·√da·λa·√f'c·ca1^1.5 ; "
                      "9·λa·√f'c·ca1^1.5 ]",
                f"min( {rec.n('F', Vb1)} ; {rec.n('F', Vb2)} )", Vb, "F",
                "ACI Ec. 17.7.2.2.1")
        rec.add("Avco", "4.5·ca1²", f"4.5·{rec.n('L', ca1)}²", Avco, "A")
        rec.add("Avc", "(min(1.5ca1,ca_x1)+sx+min(1.5ca1,ca_x2))·min(1.5ca1,ha)",
                "", Avc, "A")
        rec.add("ψed,V", "", f"ca2,min = {rec.n('L', ca2min)}", psi_edV, "-",
                "ACI 17.7.2.4")
        rec.add("Vcbg", "(Avc/Avco)·ψec·ψed·ψc·ψh·Vb",
                f"({Avc/Avco:.3f})·1.00·{psi_edV:.3f}·{psi_cV:.2f}·"
                f"{psi_hV:.3f}·{rec.n('F', Vb)}", Vcbg, "F")
        rec.check("Arrancamiento del concreto en cortante", Vua,
                  phi_c * k_seis * Vcbg, "F",
                  Vua / (phi_c * k_seis * Vcbg) if Vcbg > 0 else 0,
                  Vua <= phi_c * k_seis * Vcbg, "ACI 17.7.2")
    cap_vcb = phi_c * k_seis * Vcbg
    if ub is not None:
        cap_vcb = max(cap_vcb, ub["phi"] * ub["Nrs"])           # ACI 17.7.2.5: refuerzo de anclaje en cortante
    out.append(Check("aci_vcb", "Anclaje — arrancamiento del concreto en cortante"
                     + (" (con refuerzo U)" if ub is not None else ""),
                     Vua, cap_vcb, "kip", "ACI 318-19 17.7.2" + (" / 17.7.2.5" if ub is not None else ""),
                     ("Cortante tomado por la llave de corte." if prj.lug.enabled else
                      f"ca1 = {u.q('L', ca1)}, Avc/Avco = {Avc/Avco:.2f}, ψed,V = {psi_edV:.2f}")))

    # ============================================= ACI 17.7.3 pryout
    kcp = 1.0 if hef < 2.5 else 2.0
    Ncp = min(Ncbg, Nag) if adh and Nag is not None else Ncbg   # ACI 17.7.3.1.1
    Vcpg = kcp * Ncp
    out.append(Check("aci_vcp", "Anclaje — desprendimiento por cabeceo (pryout)",
                     Vua, phi_c * k_seis * Vcpg, "kip", "ACI 318-19 17.7.3",
                     f"kcp = {kcp:.0f}"))

    if rec:
        rec.add("kcp", "1.0 si hef<2.5 in ; 2.0 si hef>=2.5 in", "", kcp, "-")
        rec.add("Vcpg", "kcp · min(Ncbg ; Nag)" if adh else "kcp · Ncbg",
                f"{kcp:.0f} · {rec.n('F', Ncp)}", Vcpg, "F",
                "ACI Ec. 17.7.3.1")
        rec.check("Pryout", Vua, phi_c * k_seis * Vcpg, "F",
                  Vua / (phi_c * k_seis * Vcpg) if Vcpg > 0 else 0,
                  Vua <= phi_c * k_seis * Vcpg, "ACI 17.7.3")

    if ub is not None:
        nm = "Omega" if ub["kind"] == "OMEGA" else "U"
        dev = "ldh (gancho 90°)" if ub["kind"] == "OMEGA" else "ld (recta)"
        desc = (f"{ub['n']} {nm} {ub['size']} ({ub['n_legs']} patas, fy = {u.q('S', ub['fy'])}); pata {u.q('L', ub['leg'])} "
                f"(sobre la punta del anclaje {u.q('L', ub['above'])}, bajo la punta del anclaje {u.q('L', ub['below'])})")
        # 1) resistencia del refuerzo a traccion (ACI 17.5.2.1, condicion A, φ = 0.75)
        out.append(Check("aci_ubar_ten", f"Refuerzo {nm} — resistencia a traccion (φ·n·Ab·fy)", Nua, ub["phi"] * ub["Nrs"], "kip",
                         "ACI 318-19 17.5.2.1", desc + f"; Nrs = {u.q('F', ub['Nrs'])}, φ = {ub['phi']:g}"))
        # 2) desarrollo bajo la punta del anclaje (A: ld de barra recta, B: ldh del gancho)
        out.append(Check("aci_ubar_dev", f"Refuerzo {nm} — desarrollo bajo la punta del anclaje: {dev}",
                         ub["dev"], max(ub["below"], 0.0), "in",
                         "ACI 318-19 17.5.2.1 / " + ("25.4.3" if ub["kind"] == "OMEGA" else "25.4.2"),
                         desc + f"; se requiere {u.q('L', ub['dev'])}"
                         + ("; la pata no cabe en el pedestal" if ub["depth"] + ub["leg"] > prj.conc.ha + 1e-6 else "")))
        # 3) desarrollo sobre la punta del anclaje (el doblez superior / gancho)
        out.append(Check("aci_ubar_hook", f"Refuerzo {nm} — desarrollo sobre la punta del anclaje: ldh",
                         ub["ldh"], max(ub["above"], 0.0), "in", "ACI 318-19 25.4.3",
                         f"ldh = {u.q('L', ub['ldh'])}; tramo horizontal a {u.q('L', ub['depth'])} de la superficie"))
        # 4) cabe en el pedestal (profundidad + doblez) y la cola con su recubrimiento
        need_h = ub["depth"] + ub["leg"] + (ub["rb"] + ub["db"] if ub["kind"] == "OMEGA" else 0.0)
        out.append(Check("aci_ubar_fit", f"Refuerzo {nm} — cabe en la altura del pedestal", need_h, prj.conc.ha, "in",
                         "ACI 318-19 20.5.1 (recubrimiento)", f"profundidad {u.q('L', ub['depth'])} + pata {u.q('L', ub['leg'])}"
                         + (f" + doblez {u.q('L', ub['rb'] + ub['db'])}" if ub["kind"] == "OMEGA" else "")
                         + f"; altura disponible {u.q('L', prj.conc.ha)}"))
        if ub["kind"] == "OMEGA":
            out.append(Check("aci_ubar_cover", "Refuerzo Omega — recubrimiento lateral de la cola del gancho", 1.5,
                             max(ub["cover"], 0.0), "in", "ACI 318-19 20.5.1",
                             f"cola {u.q('L', ub['tail'])} hacia afuera; recubrimiento que queda {u.q('L', ub['cover'])}, minimo 1.5 in"))

    # ============================================= ACI 17.8 interaccion
    rN = max([ch.ratio for ch in out if ch.key in ("aci_nsa", "aci_ncb", "aci_np", "aci_nsb", "aci_na")] + [0.0])
    rV = max([ch.ratio for ch in out if ch.key in ("aci_vsa", "aci_vcb", "aci_vcp")] + [0.0])
    if rN <= 0.2 or rV <= 0.2:
        out.append(Check("aci_int", "Anclaje — interaccion traccion-cortante (ACI 17.8)",
                         max(rN, rV), 1.0, "-", "ACI 318-19 17.8.1/17.8.2",
                         "No se requiere interaccion: una solicitacion <= 20% de su capacidad."))
    else:
        out.append(Check("aci_int", "Anclaje — interaccion traccion-cortante (ACI 17.8)",
                         rN + rV, 1.2, "-", "ACI 318-19 Ec. 17.8.3",
                         f"N/φNn = {rN:.3f} ; V/φVn = {rV:.3f} ; limite 1.2"))

    # ==================================== detallado: distancia al borde en la placa
    emin = MAT.min_edge_distance(b.size, b.hole_rule)
    e_real = min(G.bolt_edge_distances(prj) or [0.0])
    out.append(Check("blt_edge", "Detallado — distancia del perno al borde de la placa",
                     emin, e_real, "in", "AISC Tabla 14-2 / J3.4",
                     f"Agujero dh = {u.q('L', g.dh)}; se requiere material suficiente para la arandela"))
    return out
