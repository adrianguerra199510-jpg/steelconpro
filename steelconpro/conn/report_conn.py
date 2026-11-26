# -*- coding: utf-8 -*-
"""Memoria de calculo (PDF y Word) de la conexion de nudo.

`report.py` delega aqui cuando `prj.ctype` no es la placa base.  Misma estructura que la memoria de la placa base:
datos, casos de carga, verificaciones por operacion, veredicto, avisos, anexo de ecuaciones y dibujos.
"""
from __future__ import annotations
import datetime

from ..units import UnitSet

def _us(prj) -> UnitSet:
    return UnitSet(prj.u_len, prj.u_force, prj.u_stress, prj.u_moment)


def _mod(prj):
    from . import module_for
    return module_for(prj.ctype)


def input_rows(prj, us: UnitSet) -> list:
    """Filas (concepto, descripcion) de los datos de entrada."""
    return _mod(prj).input_rows(prj, us)


def _checks_rows(us, res):
    from ..report import ck_vals
    out = []
    for ch in res.checks:
        dv, cv, ul = ck_vals(us, ch)
        out.append((ch, dv, cv, ul))
    return out


def _fem_tables(prj, res, us):
    """[(titulo, encabezado, filas)] de las tablas del analisis 3D; vacio mientras el analisis por elementos finitos del nudo no se haya corrido."""
    return list(getattr(res, "fem_tables", None) or [])


def _split_figs(figs):
    figs = figs or []
    return [f for f in figs if "fem_" not in f.replace("\\", "/").split("/")[-1]], [f for f in figs if "fem_" in f.replace("\\", "/").split("/")[-1]]


def _verdict(res):
    if res.pending:
        return "PENDIENTE", "#9C5700"
    return ("CUMPLE", "#006100") if res.ok else ("NO CUMPLE", "#9C0006")


# ======================================================================= contenido común (PDF y Word)
def _extra(prj, res, folder) -> dict:
    """Figuras y tablas del reporte: secciones, vistas del modelo, alámbrico con cargas, malla y resultados del análisis de placas (si hay)."""
    from . import report_figs as RF
    from . import nodal as NOD
    us = _us(prj)
    out = {"sections": None, "sec_rows": [], "model": [], "wire": [], "fem": [], "tables": [], "nodal": None, "errors": []}
    shells = list(getattr(res, "shells", None) or [])

    def guard(key, fn):
        try:
            return fn()
        except Exception as e:                                          # noqa: BLE001 — una figura que falla no debe impedir el reporte
            out["errors"].append(f"{key}: {type(e).__name__}: {e}")
            return None
    out["sections"] = guard("secciones", lambda: RF.sections_figure(prj, folder))
    out["sec_rows"] = guard("propiedades", lambda: RF.section_rows(prj, us)) or []
    out["model"] = guard("vistas", lambda: RF.model_views(prj, folder)) or []
    out["wire"] = guard("alámbrico", lambda: RF.wire_views(prj, folder)) or []
    out["nodal"] = guard("nodal", lambda: NOD.analysis(prj, prj.node))
    if shells:
        out["fem"] = guard("malla", lambda: RF.fem_views(prj, shells, folder)) or []
        out["tables"] = guard("tablas", lambda: RF.fem_tables(prj, shells)) or []
    return out


def _nodal_tables(prj, us, nodal):
    """[(título, encabezado, filas)] del equilibrio del nudo por caso de carga."""
    out = []
    if not nodal:
        return out
    hdr = ["Acción sobre el nudo"] + [f"{k} ({us.F})" for k in ("Fx", "Fy", "Fz")] + [f"{k} ({us.M})" for k in ("Mx", "My", "Mz")]
    for c in nodal.get("cases", []):
        rows = []
        for r in c.get("rows", []):
            rows.append([r["member"] + ("" if r.get("given") else "  (reacción)")] + [us.fmt("F", v, 2) for v in r["F"]] + [us.fmt("M", v, 1) for v in r["M"]])
        rows.append(["Σ con la reacción"] + ["0"] * 6)
        out.append((f"Caso de carga: {c['case']}", hdr, rows))
    return out


def _blocks(prj, res, us, ex, detail=True):
    """Lista de bloques del cuerpo del reporte: ("h1", texto) ("p", texto) ("small", texto) ("img", ruta, ancho_in, pie) ("table", encabezado, filas, anchos_in, opciones)
    ("verdict", texto, color, detalle) ("pb",)."""
    B = []
    rows = [[a, b] for a, b in input_rows(prj, us)]
    n = 0

    def h1(t):
        nonlocal n
        n += 1
        B.append(("h1", f"{n}. {t}"))
    h1("Datos de entrada")
    B.append(("table", ["Concepto", "Descripción"], rows, [1.5, 5.8], {"wrap": True}))
    if ex.get("sections"):
        h1("Secciones de los perfiles")
        B.append(("img", ex["sections"], 6.2, "Secciones usadas en el nudo, con sus medidas principales."))
        if ex.get("sec_rows"):
            L = us.L
            B.append(("table", ["Perfil", f"A ({L}²)", f"Ix ({L}⁴)", f"Iy ({L}⁴)", f"Zx ({L}³)", f"Zy ({L}³)"],
                      [[r[0]] + [f"{v:.4g}" for v in r[1:]] for r in ex["sec_rows"]], [1.6, 1.1, 1.2, 1.2, 1.1, 1.1], {}))
    if ex.get("model"):
        h1("Modelo del nudo")
        for title, fp in ex["model"]:
            B.append(("img", fp, 6.2, title))
    if ex.get("wire"):
        h1("Modo alámbrico: cargas, reacción y resultante")
        B.append(("small", "Cada miembro se representa por su eje; el nudo de análisis es la esfera. Las flechas rojas son las acciones de los miembros, la verde la reacción del miembro principal "
                           "y la naranja la resultante de las cargas; las violetas son momentos."))
        for title, fp in ex["wire"]:
            B.append(("img", fp, 6.2, title))
        for ttl, hdr, rws in _nodal_tables(prj, us, ex.get("nodal")):
            B.append(("p", f"<b>{ttl}</b> — equilibrio del nudo (ejes globales, momentos respecto del cruce de ejes)"))
            B.append(("table", hdr, rws, [1.9] + [0.9] * 6, {"right": True, "left": [0]}))
    tabs = ex.get("tables") or []
    if ex.get("fem"):
        h1("Análisis por elementos finitos (modelo de placas, CalculiX)")
        B.append(("small", "Modelo de cascarones sobre la superficie media de cada placa y pieza de los miembros; pernos como resortes de cortante y tracción (solo tracción), contacto solo a compresión "
                           "y cordones atados a las placas. Los esfuerzos son de von Mises en las caras de los cascarones."))
        for title, fp, cap in ex["fem"]:
            B.append(("img", fp, 6.5, title + (f". {cap}" if cap else "")))
    if tabs:
        h1("Resumen de resultados")
        for t in tabs:
            B.append(("p", f"<b>Caso de carga: {t['case']}</b>"))
            B.append(("table", ["Resultado", "Valor"], [[a, b] for a, b in t["summary"]], [2.4, 2.0], {}))
            B.append(("p", "<b>Placas y miembros</b> — esfuerzos, deformación plástica y desplazamientos (zona de la conexión; «Pico» incluye los máximos puntuales)"))
            B.append(("table", t["parts"][0], t["parts"][1], [1.35, 0.7, 0.7, 0.6, 0.85, 0.7, 0.55, 0.65, 0.8], {"right": True, "small": True, "left": [0, 1]}))
            if t["bolt_groups"][1]:
                B.append(("p", "<b>Pernos</b> — fuerzas por grupo"))
                B.append(("table", t["bolt_groups"][0], t["bolt_groups"][1], [1.5, 2.0, 0.7, 1.0, 1.0, 0.7], {"right": True, "left": [0, 1]}))
                if t["bolts"][1]:
                    lim = 40
                    B.append(("p", f"<b>Pernos</b> — fuerza en cada perno" + (f" (los {lim} más exigidos de {len(t['bolts'][1])})" if len(t["bolts"][1]) > lim else "")))
                    B.append(("table", t["bolts"][0], t["bolts"][1][:lim], [1.0, 1.9, 0.75, 0.75, 0.75, 0.75, 0.6, 0.6], {"right": True, "small": True, "left": [0, 1]}))
            if t["anchors"][1]:
                B.append(("p", "<b>Anclajes</b>"))
                B.append(("table", t["anchors"][0], t["anchors"][1], [2.0, 1.2, 1.2], {"right": True}))
            if t["welds"][1]:
                B.append(("p", "<b>Cordones de soldadura</b> — fuerza por unidad de largo transmitida por las placas"))
                B.append(("table", t["welds"][0], t["welds"][1], [1.9, 0.6, 0.8, 0.8, 1.0, 1.0, 0.6], {"right": True, "left": [0]}))
    elif not ex.get("fem"):
        B.append(("small", "Este informe no incluye la malla, los esfuerzos ni las deformaciones del análisis por elementos finitos porque no hay un análisis vigente: presione «Calcular» "
                           "en la aplicación y genere el informe de nuevo."))
    h1("Verificaciones")
    data = []
    for ch, dv, cv, ul in _checks_rows(us, res):
        data.append([ch.title, f"{dv:,.3f}", f"{cv:,.3f}", ul, "—" if ch.skip else f"{ch.ratio:.3f}", 0 if ch.skip else (1 if ch.ok else 2)])
    B.append(("checks", ["Verificación", "Demanda", "Capacidad", "Un.", "D/C"], data, [3.6, 0.9, 1.0, 0.5, 0.6]))
    gov = res.governing
    vtxt, vcol = _verdict(res)
    B.append(("verdict", vtxt, vcol, f"D/C máximo = {res.max_ratio:.3f}" + (f"  (gobierna: {gov.title})" if gov else "")))
    if len(res.combo_rows or []) > 1:
        B.append(("p", "<b>Casos de carga</b> (el detalle corresponde al que gobierna)"))
        B.append(("checks", ["Caso de carga", "D/C máx", "Gobierna", "Estado"],
                  [[cr["name"], f"{cr['ratio']:.3f}", cr["gov"], "CUMPLE" if cr["ok"] else "NO CUMPLE", 1 if cr["ok"] else 2] for cr in res.combo_rows], [1.5, 0.8, 3.7, 0.9]))
    if res.warnings:
        h1("Avisos")
        for w in res.warnings:
            B.append(("warn", w))
    if ex.get("errors"):
        B.append(("small", "No se pudieron generar algunas figuras: " + "; ".join(ex["errors"])))
    return B


def _fonts():
    """(normal, negrita): DejaVu Sans (con acentos y letras griegas) si matplotlib la trae; si no, Helvetica."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from . import report_figs as RF
        fn, fb = RF.font_path(False), RF.font_path(True)
        if fn and fb:
            pdfmetrics.registerFont(TTFont("DJ", fn))
            pdfmetrics.registerFont(TTFont("DJB", fb))
            pdfmetrics.registerFontFamily("DJ", normal="DJ", bold="DJB", italic="DJ", boldItalic="DJB")
            return "DJ", "DJB"
    except Exception:                                                    # noqa: BLE001
        pass
    return "Helvetica", "Helvetica-Bold"


# ======================================================================= PDF
def export_pdf(prj, res, path: str, figs: list | None = None, detail: bool = True) -> str:
    import tempfile
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, KeepTogether)
    from xml.sax.saxutils import escape as esc
    from PIL import Image as PILImage

    us = _us(prj)
    FN, FB = _fonts()
    ss = getSampleStyleSheet()
    H0 = ParagraphStyle("H0", parent=ss["Title"], fontName=FB, fontSize=15, spaceAfter=2)
    H1 = ParagraphStyle("H1", parent=ss["Heading2"], fontName=FB, fontSize=11, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1F3864"), keepWithNext=1)
    BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontName=FN, fontSize=8, leading=10.5)
    BODYK = ParagraphStyle("BODYK", parent=BODY, keepWithNext=1, spaceAfter=2)
    SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=6.8, leading=8.6, textColor=colors.HexColor("#444444"))
    CAP = ParagraphStyle("CAP", parent=SMALL, alignment=TA_CENTER, spaceAfter=6)
    CEN = ParagraphStyle("CEN", parent=BODY, alignment=TA_CENTER)
    CELL = ParagraphStyle("CELL", parent=BODY, fontSize=7, leading=8.6)
    CELLS = ParagraphStyle("CELLS", parent=CELL, fontSize=6.4, leading=7.8)
    CELLR = ParagraphStyle("CELLR", parent=CELL, alignment=TA_RIGHT)
    CELLRS = ParagraphStyle("CELLRS", parent=CELLS, alignment=TA_RIGHT)
    CELLB = ParagraphStyle("CELLB", parent=CELL, fontName=FB, textColor=colors.white)

    def tbl(hdr, rows, widths, right=False, small=False, extra=None, left=(0,)):
        cs, cr = (CELLS, CELLRS) if small else (CELL, CELLR)
        data = [[Paragraph(esc(str(h)), CELLB) for h in hdr]]
        for r in rows:
            data.append([Paragraph(esc(str(v)), (cr if (right and j not in left) else cs)) for j, v in enumerate(r)])
        t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
        st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6"))]
        t.setStyle(TableStyle(st + (extra or [])))
        return t

    story = []
    try:
        from .. import brand
        lw = 2.4 * inch
        story.append(RLImage(brand.LOGO(), width=lw, height=lw * brand.logo_ratio(), hAlign="LEFT"))
        story.append(Spacer(1, 4))
    except Exception:
        pass
    story.append(Paragraph(f"MEMORIA DE CÁLCULO — {_mod(prj).TITLE}", H0))
    story.append(Paragraph(f"<b>{esc(prj.name)}</b> &nbsp;|&nbsp; Elemento: {esc(prj.element)} &nbsp;|&nbsp; Cálculo: {esc(prj.author or '-')} &nbsp;|&nbsp; "
                           f"Fecha: {prj.date or datetime.date.today().isoformat()}", CEN))
    story.append(Paragraph(f"Normas: {_mod(prj).NORMS} &nbsp;|&nbsp; Unidades: {us.L}, {us.F}, {us.S}", CEN))
    story.append(Spacer(1, 8))

    folder = tempfile.mkdtemp(prefix="scp_rep_")
    ex = _extra(prj, res, folder)
    head = None                                                          # título pendiente: se pega a la figura que le sigue (para que no quede solo al pie de una página)
    for b in _blocks(prj, res, us, ex, detail):
        k = b[0]
        if k == "h1":
            head = Paragraph(esc(b[1]), H1)
            continue
        if k != "img" and head is not None:
            story.append(head)
            head = None
        if k == "p":
            story.append(Paragraph(b[1], BODYK))
        elif k == "small":
            story.append(Paragraph(esc(b[1]), SMALL))
            story.append(Spacer(1, 3))
        elif k == "img":
            try:
                iw, ih = PILImage.open(b[1]).size
                w = b[2] * inch
                story.append(KeepTogether(([head] if head is not None else []) + [RLImage(b[1], width=w, height=w * ih / iw), Paragraph(esc(b[3]), CAP)]))
                head = None
            except Exception:                                            # noqa: BLE001
                pass
        elif k == "table":
            opts = b[4]
            t_ = tbl(b[1], b[2], b[3], opts.get("right", False), opts.get("small", False), left=tuple(opts.get("left", [0])))
            story.append(KeepTogether([t_]) if len(b[2]) <= 14 else t_)                  # las tablas cortas no se parten entre páginas
            story.append(Spacer(1, 6))
        elif k == "checks":
            hdr, rows, wd = b[1], b[2], b[3]
            extra = []
            data = []
            ncol = len(hdr)
            for i, r in enumerate(rows, start=1):
                st_ = r[-1]
                data.append([str(v) for v in r[:-1]])
                extra.append(("BACKGROUND", (ncol - 1, i), (ncol - 1, i), colors.HexColor({0: "#EEEEEE", 1: "#C6EFCE", 2: "#FFC7CE"}[st_])))
            t = tbl(hdr, data, wd, right=False, extra=extra)
            story.append(t)
            story.append(Spacer(1, 5))
        elif k == "verdict":
            story.append(Paragraph(f'<b>VEREDICTO: <font color="{b[2]}">{esc(b[1])}</font></b> &nbsp;&nbsp; {esc(b[3])}', BODY))
            story.append(Spacer(1, 4))
        elif k == "warn":
            col = "9C0006" if b[1].startswith("**") else "7F6000"
            story.append(Paragraph(f'<font color="#{col}">• {esc(b[1])}</font>', BODY))
        elif k == "pb":
            story.append(PageBreak())

    if detail and res.rec is not None:
        story.append(PageBreak())
        story.append(Paragraph("Anexo A — Desarrollo de las ecuaciones", H1))
        story.append(Paragraph("Cada línea muestra el símbolo, la fórmula, la sustitución numérica y el resultado, en las unidades de trabajo del proyecto.", SMALL))
        EQ = ParagraphStyle("EQ", parent=BODY, fontSize=7.4, leading=9.6, leftIndent=8)
        SEC = ParagraphStyle("SEC", parent=BODY, fontName=FB, fontSize=8.4, leading=11, spaceBefore=7, spaceAfter=2, textColor=colors.white, backColor=colors.HexColor("#1F3864"),
                             leftIndent=2, rightIndent=2, borderPadding=3)
        NT = ParagraphStyle("NT", parent=EQ, textColor=colors.HexColor("#555555"), leftIndent=16)
        CH = ParagraphStyle("CH", parent=EQ, fontName=FB, textColor=colors.HexColor("#1F3864"))
        for kind, txt in res.rec.to_lines():
            story.append(Paragraph(esc(txt), {"sec": SEC, "txt": NT, "chk": CH}.get(kind, EQ)))

    draw_figs, _fem_figs = _split_figs(figs)
    draw_figs = [f for f in draw_figs if "modelo3d_iso" not in f.replace("\\", "/").split("/")[-1]]      # el isométrico ya está en el cuerpo del reporte
    if draw_figs:
        story.append(PageBreak())
        story.append(Paragraph("Anexo B — Dibujos", H1))
        for fp in draw_figs:
            try:
                iw, ih = PILImage.open(fp).size
                w = 6.1 * inch
                story.append(RLImage(fp, width=w, height=w * ih / iw))
                story.append(Spacer(1, 6))
            except Exception:
                pass

    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.55 * inch, bottomMargin=0.55 * inch,
                            title=f"Memoria {_mod(prj).TITLE.lower()} {prj.element}", author=prj.author or "SteelConPro")

    def _footer(canvas, docu):
        canvas.saveState()
        canvas.setFont(FN, 6.5)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(0.6 * inch, 0.32 * inch, f"{prj.name} — {prj.element} — SteelConPro {__import__('steelconpro').__version__}")
        canvas.drawRightString(letter[0] - 0.6 * inch, 0.32 * inch, f"Página {docu.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


# ====================================================================== Word
def export_docx(prj, res, path: str, figs: list | None = None, detail: bool = True) -> str:
    import re
    import tempfile
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    us = _us(prj)
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(9)
    try:
        from .. import brand
        doc.add_picture(brand.LOGO(), width=Inches(2.6))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.LEFT
    except Exception:
        pass
    doc.add_heading(f"MEMORIA DE CÁLCULO — {_mod(prj).TITLE}", level=0)
    p0 = doc.add_paragraph()
    p0.add_run(f"{prj.name}\n").bold = True
    p0.add_run(f"Elemento: {prj.element}     Cálculo: {prj.author}     Fecha: {prj.date or datetime.date.today().isoformat()}\n")
    p0.add_run(f"Normas: {_mod(prj).NORMS}.")
    strip = lambda t: re.sub(r"<[^>]+>", "", t)                          # noqa: E731
    folder = tempfile.mkdtemp(prefix="scp_rep_")
    ex = _extra(prj, res, folder)

    def table(hdr, rows, size=8):
        t = doc.add_table(rows=1, cols=len(hdr))
        t.style = "Light Grid Accent 1"
        for c, h in zip(t.rows[0].cells, hdr):
            c.text = str(h)
        for r in rows:
            cells = t.add_row().cells
            for c, v in zip(cells, r):
                c.text = str(v)
        for row in t.rows:
            for c in row.cells:
                for pp in c.paragraphs:
                    for run in pp.runs:
                        run.font.size = Pt(size)
        return t
    for b in _blocks(prj, res, us, ex, detail):
        k = b[0]
        if k == "h1":
            doc.add_heading(b[1], level=1)
        elif k in ("p", "small"):
            doc.add_paragraph(strip(b[1]))
        elif k == "img":
            try:
                doc.add_picture(b[1], width=Inches(min(b[2], 6.4)))
                cap = doc.add_paragraph(b[3])
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:                                            # noqa: BLE001
                pass
        elif k == "table":
            table(b[1], b[2], 7 if b[4].get("small") else 8)
        elif k == "checks":
            table(b[1], [r[:-1] for r in b[2]])
        elif k == "verdict":
            p = doc.add_paragraph()
            p.add_run("VEREDICTO: ").bold = True
            r = p.add_run(b[1])
            r.bold = True
            r.font.color.rgb = RGBColor.from_string(b[2].lstrip("#"))
            p.add_run(f"     {b[3]}")
        elif k == "warn":
            doc.add_paragraph(b[1], style="List Bullet")
    if detail and res.rec is not None:
        doc.add_heading("Anexo A — Desarrollo de las ecuaciones", level=1)
        for kind, txt in res.rec.to_lines():
            if kind == "sec":
                doc.add_heading(txt, level=2)
            else:
                para = doc.add_paragraph(txt)
                para.paragraph_format.space_after = Pt(1)
                if kind == "chk":
                    for run in para.runs:
                        run.bold = True
                elif kind == "txt":
                    for run in para.runs:
                        run.italic = True
    draw_figs, _fem_figs = _split_figs(figs)
    draw_figs = [f for f in draw_figs if "modelo3d_iso" not in f.replace("\\", "/").split("/")[-1]]
    if draw_figs:
        doc.add_heading("Anexo B — Dibujos", level=1)
        for fp in draw_figs:
            try:
                doc.add_picture(fp, width=Inches(6.0))
            except Exception:
                pass
    doc.save(path)
    return path
