# -*- coding: utf-8 -*-
"""Memoria de cálculo a capacidad del empalme soldado de la viga doble 2 × HN600×200×11×17 (ejemplo TP-V45): una placa de ala arriba y otra abajo, y una placa exterior por alma.

Calcula con las fórmulas de AISC 360-22 (los mismos motores del programa para el grupo de filetes) y genera un PDF con los datos, las capacidades de la viga,
las fuerzas de diseño, la verificación de las placas de ala y de alma, el resumen D/C y las observaciones; al final anexa el reporte del programa.

    python3 tools/memoria_empalme_viga_doble.py salida.pdf
"""
import glob
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from steelconpro.conn.common import weld_segments_elastic            # noqa: E402

MM, KN, KNM = 1 / 25.4, 1 / 4.448222, 8.850746                      # mm → in, kN → kip, kN·m → kip·in
# ------------------------------------------------------------------------------------------------ datos (mm, kN, MPa)
D, BF, TF, TW = 600.0, 200.0, 17.0, 11.0                            # HN600×200×11×17 (sin radio de acuerdo: conservador)
FY, FU, FEXX = 345.0, 450.0, 482.0                                  # A572 Gr. 50 (supuesto para las vigas y las placas), E70
TP, LP, BP, HW = 20.0, 500.0, 360.0, 400.0                          # placas de 20 mm: largo 500; ancho de la placa de ala (cubre las dos alas) 360; alto de la placa de alma 400
GAP = 2.0
WF, WW = 16.0, 12.0                                                 # filetes de las alas y del alma
E = 200000.0
PHI_W = 0.75
RES = []                                                            # (grupo, verificación, demanda, capacidad, unidad, referencia, nota)


def add(grp, name, dem, cap, unit, ref, note=""):
    RES.append((grp, name, dem, cap, unit, ref, note))
    return dem / cap


def web_vmax(web, L, H, w, capb, phiVn):
    """Cortante máximo (kN) que la placa transmite al alma con sus filetes en C, con el momento nulo (D/C = 1 del método elástico)."""
    f, cap, _t, _l = web(L, H, w, phiVn, 0.0)
    return phiVn / (f / min(cap, capb))


def calc():
    out = {}
    Af = BF * TF
    Zf = Af * (D - TF)                                              # módulo plástico de las alas (una viga)
    Zw = TW * (D - 2 * TF) ** 2 / 4.0                               # del alma
    ht = (D - 2 * TF) / TW
    lam_f, lam_w = BF / 2 / TF, ht
    out.update(Zf=Zf, Zw=Zw, ht=ht, lam_f=lam_f, lam_w=lam_w, lpf=0.38 * math.sqrt(E / FY), lpw=3.76 * math.sqrt(E / FY))
    phiMf, phiMw = 0.9 * FY * Zf / 1e6, 0.9 * FY * Zw / 1e6
    phiMn = phiMf + phiMw
    phiVn = 1.0 * 0.6 * FY * D * TW / 1e3
    out.update(phiMf=phiMf, phiMw=phiMw, phiMn=phiMn, phiVn=phiVn)
    arm = (D + TP) / 1000.0
    Ff = phiMf / arm
    out.update(arm=arm, Ff=Ff)
    q = lambda w: PHI_W * 0.6 * FEXX * 0.707 * w / 1e3             # kN/mm de filete de lado w (mm)   # noqa: E731
    lf = LP / 2 - GAP / 2
    # ---- placa de ala: una por nivel (PL 20 × 360 × 500), sobre las dos alas de las dos vigas
    G = f"Placas de ala (2 × PL {TP:g} × {BP:g} × {LP:g}: una arriba y otra abajo, sobre las dos alas)"
    Ft = 2 * Ff                                                      # fuerza de la placa: las alas de las dos vigas
    add(G, "Fluencia de la placa en tracción (sección bruta)", Ft, 0.9 * FY * BP * TP / 1e3, "kN", "J4.1(a), φ = 0.90", f"Ag = {BP:g}·{TP:g} = {BP * TP:g} mm²; fuerza = 2 × {Ff:.0f} kN (dos alas)")
    add(G, "Rotura de la placa en tracción (sección neta = bruta, sin agujeros)", Ft, 0.75 * FU * BP * TP / 1e3, "kN", "J4.1(b), φ = 0.75", "Ae = Ag (soldada; sin agujeros)")
    Rl, Rt = q(WF) * lf, q(WF) * BP / 2.0                            # cada ala de viga: su borde largo exterior y la mitad del extremo
    Rn = max(Rl + Rt, 0.85 * Rl + 1.5 * Rt)
    out.update(q_f=q(WF), Rl=Rl, Rt=Rt, Rn_f=Rn, lf=lf)
    add(G, f"Filetes de {WF:g} mm sobre cada ala de cada viga (1 longitudinal + mitad del transversal)", Ff, Rn, "kN", "J2.4, J2-10, φ = 0.75",
        f"Rwl = {q(WF):.3f}·{lf:g} = {Rl:.0f}; Rwt = {q(WF):.3f}·{BP / 2:g} = {Rt:.0f}; Rn = máx(Rwl + Rwt, 0.85·Rwl + 1.5·Rwt) = {Rn:.0f} kN. "
        "Los bordes interiores de la placa no se sueldan (la placa pasa sobre la unión de las puntas de las alas)")
    add(G, "Metal base del ala de la viga en los filetes (cortante y tracción)", Ff, 0.75 * (0.6 * FU * TF * lf + FU * TF * BP / 2.0) / 1e3, "kN", "J4.2(b), J4.3",
        f"cortante en {lf:g} mm y tracción en {BP / 2:g} mm, t = tf = {TF:g} mm")
    add(G, "Tamaño mínimo del filete", 6.0, WF, "mm", "Tabla J2.4", "parte más delgada tf = 17 mm (> 13 mm y ≤ 19 mm): 6 mm")
    add(G, "Tamaño máximo del filete en el borde de la placa", WF, TP - 2.0, "mm", "J2.2b", "t = 20 mm ≥ 6 mm: máx. t − 2 mm")
    KLr = 0.65 * GAP / (TP / math.sqrt(12.0))
    add(G, "Compresión de la placa (tramo libre = separación de 10 mm)", Ft, 0.9 * FY * BP * TP / 1e3, "kN", "J4.4, E3", f"KL/r = {KLr:.1f} ≤ 25: Fcr = Fy")
    # ---- alma: soldadura a tope CJP de las dos almas + una placa exterior por alma (PL 20 × 400 × 500), adicional
    G = f"Almas: soldadura a tope CJP + placa exterior (2 × PL {TP:g} × {HW:g} × {LP:g}, adicional)"
    hcl = D - 2 * TF                                                 # alto libre del alma (soldadura CJP entre las alas)
    Vcjp = 1.0 * 0.6 * FY * hcl * TW / 1e3                           # cortante que resiste la soldadura CJP (= el alma de 566 mm)
    Mcjp = 0.9 * FY * TW * hcl ** 2 / 4 / 1e6                        # flexión de la soldadura CJP (= φFy·Zw del alma)
    capb = PHI_W * 0.6 * FU * TW / 1e3
    lw = LP / 2 - GAP / 2

    def web(L, H, w, V, M):
        l_ = L / 2 - GAP / 2
        sg = [(0, H / 2 * MM, l_ * MM, H / 2 * MM), (0, -H / 2 * MM, l_ * MM, -H / 2 * MM), (l_ * MM, -H / 2 * MM, l_ * MM, H / 2 * MM)]
        r = weld_segments_elastic(sg, 0.0, V * KN, -GAP / 2 * MM, 0.0, w * MM, 70.0, M0=-M * KNM)
        return r["f"] / KN * MM, r["cap"] / KN * MM, r["theta"], r["L"] / MM
    Vplaca = max(phiVn - Vcjp, 0.0)                                  # cortante que excede a la CJP y toma la placa
    add(G, "CJP del alma — flexión (estado A: φMn,alma)", phiMw, Mcjp, "kN·m", "J2.6, Tabla J2.5, F2",
        f"CJP con electrodo compatible (E70 con A572 Gr. 50): resistencia = la del alma de {hcl:g} × {TW:g} mm, φFy·Zw = {Mcjp:.1f} kN·m; la desarrolla por definición")
    add(G, "CJP del alma — cortante (estado B: φVn)", phiVn, Vcjp + web_vmax(web, LP, HW, WW, capb, phiVn), "kN", "J2.6, G2.1",
        f"la CJP resiste φ·0.6·Fy·{hcl:g}·{TW:g} = {Vcjp:.0f} kN; el resto, {Vplaca:.0f} kN, lo toma la placa (capacidad de sus filetes a cortante puro ≈ {web_vmax(web, LP, HW, WW, capb, phiVn):.0f} kN)")
    Vp, Mp = Vplaca, 0.0                                             # la placa solo lleva el cortante que excede a la CJP
    add(G, "Placa — fluencia por cortante (Vplaca)", Vp, 1.0 * 0.6 * FY * HW * TP / 1e3, "kN", "J4.2(a), φ = 1.00", f"Agv = {HW:g}·{TP:g} mm²; Vplaca = φVn − φVn,CJP")
    add(G, "Placa — rotura por cortante (Vplaca)", Vp, 0.75 * 0.6 * FU * HW * TP / 1e3, "kN", "J4.2(b), φ = 0.75", "sin agujeros: Anv = Agv")
    res = {}
    f, cap, th, Lw_ = web(LP, HW, WW, Vp, 0.0)
    res["B"] = (f, cap, th, Lw_)
    add(G, f"Filetes en C de {WW:g} mm de la placa — cortante {Vp:.0f} kN", f, min(cap, capb), "kN/mm", "J2.4, J2-5, J4.2(b)",
        f"fuerza máxima por unidad de largo {f:.2f}; capacidad del filete {cap:.2f}; del metal base del alma {capb:.2f} kN/mm (θ = {th:.0f}°)")
    add(G, "Tamaño mínimo del filete", 5.0, WW, "mm", "Tabla J2.4", "parte más delgada tw = 11 mm (> 6 mm y ≤ 13 mm): 5 mm")
    add(G, "Tamaño máximo del filete en el borde de la placa", WW, TP - 2.0, "mm", "J2.2b", "")
    out.update(web=res, capb=capb, lw=lw, Vp=Vp, Mp=Mp)
    # ---- la placa SOLA (sin la CJP): lo que hizo falta soldar el alma
    fB = web(LP, HW, WW, phiVn, 0.0)[0] / min(web(LP, HW, WW, phiVn, 0.0)[1], capb)
    fA = web(LP, HW, WW, 0.3 * phiVn, phiMw)[0] / min(web(LP, HW, WW, 0.3 * phiVn, phiMw)[1], capb)
    out["sola_dc"] = max(fA, fB)
    out["sola_Vmax"] = phiVn / fB
    out.update(Vcjp=Vcjp, Mcjp=Mcjp, Vplaca=Vplaca)
    # ---- alas: ancho de 200 mm (una sola placa de 200 sobre las dos alas) y de 400 mm
    def ala(W_, w_):
        Rl_, Rt_ = q(w_) * lf, q(w_) * W_ / 2.0
        return max(Rl_ + Rt_, 0.85 * Rl_ + 1.5 * Rt_), 0.9 * FY * W_ * TP / 1e3
    out["ala200"] = (Ff / ala(200.0, WF)[0], 2 * Ff / ala(200.0, WF)[1], ala(200.0, WF)[1])
    out["ala400"] = (Ff / ala(400.0, WF)[0], 2 * Ff / ala(400.0, WF)[1])
    return out


# ------------------------------------------------------------------------------------------------ PDF
def build(path, programa=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, KeepTogether
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fd = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
    pdfmetrics.registerFont(TTFont("DJ", os.path.join(fd, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DJB", os.path.join(fd, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("DJ", normal="DJ", bold="DJB", italic="DJ", boldItalic="DJB")
    H0 = ParagraphStyle("H0", fontName="DJB", fontSize=15, leading=19, spaceAfter=3)
    H1 = ParagraphStyle("H1", fontName="DJB", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1F3864"), keepWithNext=1)
    B = ParagraphStyle("B", fontName="DJ", fontSize=8.2, leading=11)
    S = ParagraphStyle("S", fontName="DJ", fontSize=7, leading=9, textColor=colors.HexColor("#444444"))
    C = ParagraphStyle("C", fontName="DJ", fontSize=7.4, leading=9.4)
    CB = ParagraphStyle("CB", fontName="DJB", fontSize=7.4, leading=9.4)
    R = calc()
    tmp = tempfile.mkdtemp(prefix="memo_")
    # ---- figura: sección y elevación
    fig, ax = plt.subplots(1, 2, figsize=(9.6, 4.1), gridspec_kw={"width_ratios": [1, 1.5]})
    a = ax[0]
    a.set_aspect("equal")
    for x in (-100, 100):
        a.add_patch(Rectangle((x - 100, 292 - 8.5), 200, 17, fc="#9db4d0", ec="#345"))
        a.add_patch(Rectangle((x - 100, -292 - 8.5), 200, 17, fc="#9db4d0", ec="#345"))
        a.add_patch(Rectangle((x - 5.5, -283), 11, 566, fc="#9db4d0", ec="#345"))
    a.add_patch(Rectangle((-BP / 2, 300.5), BP, TP, fc="#e07b39", ec="#a33"))
    a.add_patch(Rectangle((-BP / 2, -300.5 - TP), BP, TP, fc="#e07b39", ec="#a33"))
    for x0 in (-125.5, 105.5):
        a.add_patch(Rectangle((x0, -HW / 2), 20, HW, fc="#e07b39", ec="#a33"))
    a.set_xlim(-230, 230)
    a.set_ylim(-340, 340)
    a.set_title("Sección en la junta (mm)", fontsize=9)
    a.tick_params(labelsize=7)
    b = ax[1]
    b.set_aspect("equal")
    b.add_patch(Rectangle((-700, 292 - 8.5 + 0), 1400, 17, fc="#9db4d0", ec="#345"))
    b.add_patch(Rectangle((-700, -300.5), 1400, 17, fc="#9db4d0", ec="#345"))
    b.add_patch(Rectangle((-700, -283), 1400, 566, fc="#dbe6f2", ec="#345"))
    b.add_patch(Rectangle((-5, -330), 10, 660, fc="white", ec="none"))
    b.add_patch(Rectangle((-245, 300.5), 500, 20, fc="#e07b39", ec="#a33"))
    b.add_patch(Rectangle((-245, -320.5), 500, 20, fc="#e07b39", ec="#a33"))
    b.add_patch(Rectangle((-245, -HW / 2), 500, HW, fc="#e07b39", ec="#a33", alpha=0.85))
    b.annotate("", xy=(255, 345), xytext=(-245, 345), arrowprops=dict(arrowstyle="<->", lw=0.7))
    b.text(5, 352, "500", ha="center", fontsize=7)
    b.annotate("", xy=(300, HW / 2), xytext=(300, -HW / 2), arrowprops=dict(arrowstyle="<->", lw=0.7))
    b.text(310, 0, f"{HW:g}", va="center", fontsize=7)
    b.set_xlim(-720, 720)
    b.set_ylim(-340, 370)
    b.set_title("Elevación lateral (mm): junta de 10 mm en x = 0", fontsize=9)
    b.tick_params(labelsize=7)
    fig.tight_layout()
    fig1 = os.path.join(tmp, "fig1.png")
    fig.savefig(fig1, dpi=170)
    plt.close(fig)

    story = [Paragraph("MEMORIA DE CÁLCULO — Empalme soldado de viga doble 2 × HN600×200×11×17", H0),
             Paragraph("Diseño a capacidad de la viga con placas de 20 mm (A572 Gr. 50) y electrodo E70 · AISC 360-22 · Unidades: mm, kN, MPa · Ejemplo TP-V45 de SteelConPro", S), Spacer(1, 6)]
    # ---- 1. datos
    story += [Paragraph("1. Datos", H1)]
    rows = [["Vigas", "Dos HN600×200×11×17 lado a lado (ejes a 200 mm; las puntas de las alas se tocan); modeladas como una sola sección personalizada de 2 miembros"],
            ["Sección de cada viga", f"d = {D:g}, bf = {BF:g}, tf = {TF:g}, tw = {TW:g} mm (sin radio de acuerdo)"],
            ["Acero", f"A572 Gr. 50 (supuesto para vigas y placas): Fy = {FY:g} MPa, Fu = {FU:g} MPa"],
            ["Soldadura", f"Filetes E70 (FEXX = {FEXX:g} MPa), φ = 0.75"],
            ["Junta", f"Abertura de raíz entre las vigas = {GAP:g} mm (soldadura a tope del alma); placas centradas en la junta (± {LP / 2:g} mm), {LP / 2 - GAP / 2:g} mm de placa sobre cada viga"],
            ["Placas de ala", f"2 × PL {TP:g} × {BP:g} × {LP:g} mm (una arriba y otra abajo, por fuera, sobre las dos alas), filete de {WF:g} mm"],
            ["Almas", f"Soldadura a tope de penetración completa (CJP) de cada alma contra la de la otra viga (sección de {D - 2 * TF:g} × {TW:g} mm) y, además, una placa exterior por alma 2 × PL {TP:g} × {HW:g} × {LP:g} mm con filete en C de {WW:g} mm"],
            ["Hipótesis", "Sin sismo ni fatiga; viga arriostrada lateralmente (φMn = φMp); N = 0; sin la soldadura entre las puntas de las alas de las dos vigas; CJP del alma con electrodo compatible (E70)"]]
    t = Table([[Paragraph(f"<b>{a_}</b>", C), Paragraph(b_, C)] for a_, b_ in rows], colWidths=[1.3 * inch, 5.9 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f8"))]))
    story += [t, Spacer(1, 6), RLImage(fig1, width=7.2 * inch, height=3.07 * inch)]
    if programa and os.path.exists(programa.get("png", "")):
        pass
    # ---- 2. capacidad de la viga
    story += [Paragraph("2. Capacidad de la viga (por viga)", H1)]
    story.append(Paragraph(f"Compacidad: bf/2tf = {R['lam_f']:.2f} ≤ 0.38√(E/Fy) = {R['lpf']:.2f} y h/tw = {R['ht']:.1f} ≤ 3.76√(E/Fy) = {R['lpw']:.1f}: sección compacta (F2). "
                           f"Con la viga arriostrada, Mn = Mp = Fy·Zx. Se reparte el módulo plástico entre alas y alma:", B))
    cap = [["Magnitud", "Expresión", "Valor"],
           ["Zf (alas)", f"bf·tf·(d − tf) = {BF:g}·{TF:g}·{D - TF:g}", f"{R['Zf'] / 1e3:.0f} cm³"],
           ["Zw (alma)", f"tw·(d − 2tf)²/4 = {TW:g}·{D - 2 * TF:g}²/4", f"{R['Zw'] / 1e3:.0f} cm³"],
           ["φMn,alas = 0.9·Fy·Zf", f"0.9·{FY:g}·{R['Zf'] / 1e6:.3f}·10⁶", f"{R['phiMf']:.1f} kN·m"],
           ["φMn,alma = 0.9·Fy·Zw", f"0.9·{FY:g}·{R['Zw'] / 1e6:.3f}·10⁶", f"{R['phiMw']:.1f} kN·m"],
           ["φMn = φMn,alas + φMn,alma", "", f"{R['phiMn']:.1f} kN·m (× 2 vigas = {2 * R['phiMn']:.0f})"],
           ["φVn = 1.0·0.6·Fy·d·tw", f"h/tw ≤ 2.24√(E/Fy) = {2.24 * math.sqrt(E / FY):.1f}: φv = 1.00 (G2.1)", f"{R['phiVn']:.0f} kN (× 2 = {2 * R['phiVn']:.0f})"]]
    t = Table([[Paragraph(str(x), C) for x in r] for r in cap], colWidths=[2.0 * inch, 3.4 * inch, 1.8 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe3f0"))]))
    story.append(t)
    # ---- 3. fuerzas de diseño
    story += [Paragraph("3. Fuerzas de diseño del empalme (a capacidad de la viga)", H1),
              Paragraph("El empalme se diseña para desarrollar la resistencia de cada viga, sin depender de las cargas de servicio: "
                        f"<b>Estado A</b> (momento): φMn = {R['phiMn']:.0f} kN·m por viga con 30 % de φVn concurrente; <b>Estado B</b> (cortante): φVn = {R['phiVn']:.0f} kN por viga con momento nulo en la junta. "
                        "Las alas transmiten el momento de las alas y el alma el del alma:", B),
              Paragraph(f"Fuerza en cada ala de cada viga: Ff = φMn,alas/(d + tp) = {R['phiMf']:.1f}/{R['arm']:.3f} = <b>{R['Ff']:.0f} kN</b> (brazo entre los centros de las placas de ala = {R['arm'] * 1000:.0f} mm); "
                        f"la placa de ala cubre las dos alas de un nivel y lleva 2 × {R['Ff']:.0f} = <b>{2 * R['Ff']:.0f} kN</b>. "
                        f"El alma de cada viga se une con la soldadura CJP, que desarrolla su momento (φFy·Zw = <b>{R['Mcjp']:.0f} kN·m</b>) y un cortante de φ·0.6·Fy·{D - 2 * TF:g}·{TW:g} = <b>{R['Vcjp']:.0f} kN</b>; "
                        f"la placa exterior toma el cortante que excede a la CJP: φVn − {R['Vcjp']:.0f} = <b>{R['Vplaca']:.0f} kN</b>.", B)]
    # ---- 4. verificaciones
    story += [Paragraph("4. Verificaciones", H1)]
    groups = {}
    for r_ in RES:
        groups.setdefault(r_[0], []).append(r_)
    for g, rows_g in groups.items():
        story.append(Paragraph(g, ParagraphStyle("G", parent=B, fontName="DJB", spaceBefore=5, spaceAfter=2)))
        data = [[Paragraph(h, CB) for h in ("Verificación", "Demanda", "Capacidad", "D/C", "Referencia / cálculo")]]
        for _g, nm, d_, c_, u_, rf_, nt_ in rows_g:
            dc = d_ / c_
            data.append([Paragraph(nm, C), Paragraph(f"{d_:.4g} {u_}", C), Paragraph(f"{c_:.4g} {u_}", C),
                         Paragraph(f"<font color='{'#1a7f37' if dc <= 1 else '#c0392b'}'><b>{dc:.2f}</b></font>", C), Paragraph(f"{rf_}. {nt_}", C)])
        t = Table(data, colWidths=[1.9 * inch, 0.9 * inch, 0.9 * inch, 0.5 * inch, 3.0 * inch], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe3f0")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
    # ---- 5. resumen
    worst = max(RES, key=lambda r: r[2] / r[3])
    dcs = [r[2] / r[3] for r in RES]
    story += [Paragraph("5. Resumen y conclusión", H1)]
    byg = {}
    for g, nm, d_, c_, *_ in RES:
        byg.setdefault(g, []).append((d_ / c_, nm))
    sm = [[Paragraph(h, CB) for h in ("Componente", "D/C máximo", "Gobierna")]]
    for g, v in byg.items():
        m = max(v)
        sm.append([Paragraph(g, C), Paragraph(f"<font color='{'#1a7f37' if m[0] <= 1 else '#c0392b'}'><b>{m[0]:.2f}</b></font>", C), Paragraph(m[1], C)])
    t = Table(sm, colWidths=[2.6 * inch, 0.9 * inch, 3.7 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe3f0"))]))
    story.append(t)
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Conclusión:</b> el empalme desarrolla la capacidad de las dos vigas (D/C máximo {max(dcs):.2f}): las alas con las placas PL {TP:g} × {BP:g} × {LP:g} y filete de {WF:g} mm "
                           f"(D/C {max(r[2] / r[3] for r in RES if r[0].startswith('Placas de ala')):.2f}); las almas con la soldadura a tope CJP, que las continúa, y la placa exterior PL {TP:g} × {HW:g} × {LP:g} con filete de {WW:g} mm como complemento. "
                           f"Con la placa sola, sin la CJP, el alma no alcanzaría: sus filetes darían D/C = {R['sola_dc']:.2f} (gobierna el metal base del alma de 11 mm) y el alma transmitiría como máximo V ≈ {R['sola_Vmax']:.0f} kN ({R['sola_Vmax'] / R['phiVn'] * 100:.0f} % de φVn).", B))
    story += [Paragraph("6. Observaciones", H1)]
    obs = [f"<b>Ancho de la placa de ala.</b> Una sola placa sobre las dos alas lleva {2 * R['Ff']:.0f} kN; con 200 mm de ancho solo resiste {R['ala200'][2]:.0f} kN por fluencia (D/C = {R['ala200'][1]:.2f}) y sus filetes darían D/C = {R['ala200'][0]:.2f}: "
           f"no alcanza. Con {BP:g} mm (borde a {(200 - BP / 2):.0f} mm del borde exterior del ala, para tener dónde apoyar el cateto) y filete de {WF:g} mm cumple; con 400 mm (a ras del ala) el filete sería de 14 a 16 mm y no habría dónde apoyarlo.",
           "<b>Soldadura a tope del alma (CJP).</b> Va entre los extremos de las dos almas (11 × 566 mm) con abertura de raíz de 2 mm y electrodo compatible (E70 para A572 Gr. 50, J2.6); la resistencia de una CJP es la del metal base, por eso desarrolla el alma. "
           "Interior de las dos almas: el espacio entre ellas queda cerrado por las alas, de modo que la soldadura se hace desde el exterior con respaldo (platina de respaldo colocada antes de cerrar la junta) y requiere control de calidad (ensayo no destructivo).",
           f"<b>Por qué la placa sola no alcanza.</b> Sus filetes están limitados por el metal base del alma de 11 mm (2.23 kN/mm por línea de filete, J4.2(b)), no por el cateto: aumentar el filete no mejora el resultado.",
           "<b>Reparto del momento.</b> Las alas se diseñan para la parte del momento de las alas (φFy·Zf) y la CJP del alma para la del alma (φFy·Zw).",
           "<b>No incluido.</b> La soldadura entre las puntas de las alas de las dos vigas, la torsión por la excentricidad entre las dos vigas, el pandeo lateral de la viga doble y el cortante entre las dos vigas. No se presenta el análisis por elementos finitos del modelo de placas a la carga de capacidad: a φMn y φVn las propias vigas plastifican y sus esfuerzos no sirven para juzgar el empalme."]
    for o in obs:
        story.append(Paragraph("• " + o, B))
        story.append(Spacer(1, 2))
    if programa and programa.get("png"):
        story += [PageBreak(), Paragraph("7. Modelo en SteelConPro (TP-V45)", H1), RLImage(programa["png"], width=6.8 * inch, height=4.42 * inch),
                  Paragraph("Las placas y filetes del modelo se refieren a las caras de cada componente de la sección personalizada (p. ej. «Comp. 6 (Rect.) — Cara +X» = cara exterior del alma derecha). "
                            "Las verificaciones del programa (resistencia de los filetes con reparto uniforme) se anexan a continuación; gobiernan las de esta memoria, que incluyen la excentricidad, el metal base y J2-10: el programa no ve la limitación del alma.", B)]
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title="Memoria de cálculo — empalme de viga doble", author="SteelConPro")

    def foot(c, d):
        c.saveState()
        c.setFont("DJ", 7)
        c.setFillColor(colors.grey)
        c.drawString(0.6 * inch, 0.35 * inch, "SteelConPro 1.1 — Memoria de cálculo del empalme de viga doble (TP-V45)")
        c.drawRightString(letter[0] - 0.6 * inch, 0.35 * inch, f"Página {d.page}")
        c.restoreState()
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
    return path


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "memoria_empalme_viga_doble.pdf"
    from steelconpro.model import load_book
    from steelconpro import api
    import base64
    f = glob.glob(os.path.join(ROOT, "ejemplos", "TP-V45_*.scp"))[0]
    p = load_book(f)[0]
    tmp = tempfile.mkdtemp(prefix="memo_")
    png = os.path.join(tmp, "modelo.png")
    open(png, "wb").write(base64.b64decode(api.thumbnail({"connection": api._dump(p), "w": 1000, "h": 650})["png"]))
    mem = os.path.join(tmp, "memoria.pdf")
    build(mem, {"png": png})
    prog = os.path.join(tmp, "programa.pdf")
    api.report({"connection": api._dump(p), "format": "pdf", "path": prog, "detail": True})
    from pypdf import PdfWriter
    w = PdfWriter()
    for src in (mem, prog):
        w.append(src)
    w.add_outline_item("Memoria de cálculo a capacidad", 0)
    n = len(__import__("pypdf").PdfReader(mem).pages)
    w.add_outline_item("Anexo: reporte de SteelConPro (verificaciones del modelo TP-V45)", n)
    with open(out, "wb") as fh:
        w.write(fh)
    print(out, n, "páginas de memoria +", len(__import__("pypdf").PdfReader(prog).pages), "del reporte del programa")


if __name__ == "__main__":
    main()
