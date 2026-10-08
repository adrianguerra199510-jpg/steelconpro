# -*- coding: utf-8 -*-
"""Piezas comunes de las tipologias: recorrido de combinaciones, formato de resultados y dibujo."""
from __future__ import annotations

from ..design import Check
from ..explain import Recorder
from .specs import loads_of  # noqa: F401  (reexportada)


def run_combos(prj, spec, check_input, solve_one, detail: bool = True):
    """Calcula todas las combinaciones de `spec.loads()` y devuelve el `Results` de la que gobierna.

    `check_input(spec) -> [avisos]` (los que empiezan con '**' invalidan el veredicto);
    `solve_one(prj, nombre, valores, rec) -> [Check]`."""
    from ..solver import Results
    warns = list(check_input(spec))
    best, rows = None, []
    for idx, (name, vals) in enumerate(spec.loads()):
        rec = Recorder(prj.units()) if detail else None
        ck = solve_one(prj, name, vals, rec)
        act = [c for c in ck if not c.skip]
        mx = max((c.ratio for c in act), default=0.0)
        gov = max(act, key=lambda c: c.ratio) if act else None
        rows.append({"name": name, "ratio": mx, "ok": all(c.ok for c in act), "pending": False,
                     "gov": gov.title if gov else "-"})
        if best is None or mx > best[0]:
            best = (mx, idx, ck, rec)
    R = Results()
    R.closed_form = True
    R.checks = best[2] if best else []
    R.rec = best[3] if best else None
    R.warnings = warns
    R.combo_rows = rows
    R.combo_gov = best[1] if best else 0
    return R


def add_check(ck: list, rec, key, title, dem, cap, unit, ref, note="", skip=False):
    """Agrega un Check y, si hay memoria, su renglon de verificacion."""
    c = Check(key, title, dem, cap, unit, ref, note, skip)
    ck.append(c)
    if rec and not skip:
        rec.check(title, dem, cap, c.kind, c.ratio, c.ok, ref)
    return c


def not_evaluated(ck: list, key: str, title: str, ref: str, note: str = "No implementado: verifiquelo aparte."):
    """Verificacion que el programa NO realiza: aparece en la tabla (sin D/C) para que no pase inadvertida."""
    ck.append(Check(key, title + " — NO EVALUADO", 0.0, 1.0, "-", ref, note, skip=True))


def new_figure(width=8.0, height=6.5, dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    return Figure(figsize=(width, height), dpi=dpi)
