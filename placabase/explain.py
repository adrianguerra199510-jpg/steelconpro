# -*- coding: utf-8 -*-
"""
Memoria detallada al estilo CalcPad / MathCAD.

Mientras el motor calcula, va registrando cada paso en un `Recorder`:

    rec.add("fp,max", "φc·0.85·f'c·√(A2/A1)",
            f"0.65·0.85·{u.fmt('S', fc)}·{sq:.3f}", fp_max, "S", "AISC J8")

y despues se renderiza como

    fp,max = φc·0.85·f'c·√(A2/A1) = 0.65·0.85·27.58·1.818 = 27.70 MPa   [AISC J8]

Las tres partes (simbolo, formula, numeros) se guardan por separado, asi que
el mismo registro sirve para la pantalla (HTML), el PDF y el Word, y siempre
sale en las unidades que eligio el usuario, porque el formateo ocurre al
registrar, no al calcular.

El registro es opcional: si no se pasa un Recorder, el motor calcula igual y
no paga ningun costo.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import html

from .units import UnitSet


@dataclass
class Step:
    sym: str = ""
    formula: str = ""
    subst: str = ""
    value: float | None = None
    kind: str = "-"
    ref: str = ""
    note: str = ""
    unit_txt: str = ""
    kind_of: str = "eq"          # eq | text | check


@dataclass
class Section:
    title: str
    steps: list = field(default_factory=list)


class Recorder:
    """Acumula los pasos del calculo.  Todo se formatea en las unidades del
    usuario en el momento de registrar."""

    def __init__(self, us: UnitSet | None = None):
        self.us = us or UnitSet()
        self.sections: list[Section] = []

    # ------------------------------------------------------------ estructura
    def section(self, title: str):
        self.sections.append(Section(title))
        return self

    def _cur(self) -> Section:
        if not self.sections:
            self.section("Calculo")
        return self.sections[-1]

    # ---------------------------------------------------------------- pasos
    def add(self, sym, formula="", subst="", value=None, kind="-", ref="", note=""):
        u = self.us
        self._cur().steps.append(Step(
            sym=sym, formula=formula, subst=subst, value=value, kind=kind,
            ref=ref, note=note,
            unit_txt=(u.label(kind) if (kind and kind != "-") else "")))
        return self

    def text(self, txt):
        self._cur().steps.append(Step(note=txt, kind_of="text"))
        return self

    def check(self, title, dem, cap, kind, ratio, ok, ref=""):
        u = self.us
        self._cur().steps.append(Step(
            sym=title, formula="Demanda / Capacidad",
            subst=f"{u.fmt(kind, dem)} / {u.fmt(kind, cap)} {u.label(kind)}"
            if kind != "-" else f"{dem:.3f} / {cap:.3f}",
            value=ratio, kind="-", ref=ref,
            note=("CUMPLE" if ok else "NO CUMPLE"), kind_of="check"))
        return self

    # ---------------------------------------------------------- formateadores
    def f(self, kind, v, dec=None):
        """Numero con unidad, listo para meter en una sustitucion."""
        return self.us.q(kind, v, dec)

    def n(self, kind, v, dec=None):
        """Solo el numero, sin unidad."""
        return self.us.fmt(kind, v, dec)

    # ------------------------------------------------------------- renderers
    def to_html(self, base_font=10) -> str:
        out = [f"<style>"
               f"body{{font-family:Segoe UI,Arial;font-size:{base_font}pt}}"
               f".sec{{background:#1F3864;color:#fff;padding:4px 8px;"
               f"font-weight:bold;margin-top:14px}}"
               f".sym{{color:#1F3864;font-weight:bold}}"
               f".frm{{color:#333}}"
               f".sub{{color:#7f6000}}"
               f".val{{font-weight:bold}}"
               f".ref{{color:#888;font-size:8pt}}"
               f".ok{{color:#006100;font-weight:bold}}"
               f".no{{color:#9C0006;font-weight:bold}}"
               f".txt{{color:#444;font-style:italic}}"
               f"</style>"]
        for sec in self.sections:
            out.append(f"<div class='sec'>{html.escape(sec.title)}</div>")
            out.append("<table cellspacing='0' cellpadding='3' width='100%'>")
            for st in sec.steps:
                if st.kind_of == "text":
                    out.append(f"<tr><td colspan='2' class='txt'>"
                               f"{html.escape(st.note)}</td></tr>")
                    continue
                if st.kind_of == "check":
                    cls = "ok" if st.note == "CUMPLE" else "no"
                    out.append(
                        f"<tr><td width='42%'><span class='sym'>▸ "
                        f"{html.escape(st.sym)}</span></td>"
                        f"<td>{html.escape(st.subst)} &nbsp;&rarr;&nbsp; "
                        f"D/C = <span class='{cls}'>{st.value:.3f}</span> "
                        f"<span class='{cls}'>{st.note}</span>"
                        + (f" <span class='ref'>[{html.escape(st.ref)}]</span>"
                           if st.ref else "") + "</td></tr>")
                    continue
                parts = [f"<span class='sym'>{html.escape(st.sym)}</span>"]
                if st.formula:
                    parts.append(f"= <span class='frm'>{html.escape(st.formula)}</span>")
                if st.subst:
                    parts.append(f"= <span class='sub'>{html.escape(st.subst)}</span>")
                if st.value is not None:
                    parts.append(f"= <span class='val'>"
                                 f"{self.us.fmt(st.kind, st.value)} "
                                 f"{html.escape(st.unit_txt)}</span>")
                line = " ".join(parts)
                extra = ""
                if st.ref:
                    extra += f" <span class='ref'>[{html.escape(st.ref)}]</span>"
                if st.note:
                    extra += f"<br><span class='txt'>{html.escape(st.note)}</span>"
                out.append(f"<tr><td colspan='2'>{line}{extra}</td></tr>")
            out.append("</table>")
        return "".join(out)

    def to_lines(self):
        """Texto plano, una tupla (tipo, texto) por linea.  Para PDF y Word."""
        res = []
        for sec in self.sections:
            res.append(("sec", sec.title))
            for st in sec.steps:
                if st.kind_of == "text":
                    res.append(("txt", st.note))
                    continue
                if st.kind_of == "check":
                    res.append(("chk", f"{st.sym}:  {st.subst}  ->  D/C = "
                                       f"{st.value:.3f}  {st.note}"
                                       + (f"   [{st.ref}]" if st.ref else "")))
                    continue
                s = st.sym
                if st.formula:
                    s += f" = {st.formula}"
                if st.subst:
                    s += f" = {st.subst}"
                if st.value is not None:
                    s += f" = {self.us.fmt(st.kind, st.value)} {st.unit_txt}"
                if st.ref:
                    s += f"   [{st.ref}]"
                res.append(("eq", s.strip()))
                if st.note:
                    res.append(("txt", st.note))
        return res
