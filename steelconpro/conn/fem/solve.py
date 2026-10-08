# -*- coding: utf-8 -*-
"""Resolucion del modelo con CalculiX: conjunto activo de contactos y traccion de pernos, y luego (opcional) el paso elasto-plastico."""
from __future__ import annotations
import os
import time
from pathlib import Path

import numpy as np

from ... import mesh3d
from ...view3d import read_frd, read_peeq
from .ccxgen import CcxCase


def run_ccx(inp: str, ccx_path: str = "", cancel=None, timeout=3600):
    """Ejecuta CalculiX sobre `inp`. -> (ok, salida, ruta .frd); ok = hay .frd (aunque el calculo no haya convergido: ver `finished`)."""
    return mesh3d.run_ccx(inp, ccx_path, timeout=timeout, cancel=cancel)


def finished(out: str) -> bool:
    """True si CalculiX termino el paso sin error (imprime 'Job finished')."""
    return "*ERROR" not in out and ("Job finished" in out or "Total CalculiX Time" in out or "CalculiX Time" in out)


def load_fraction(frd: str) -> float:
    """Fraccion de la carga alcanzada por el ultimo incremento convergido (del .sta que escribe CalculiX junto al .frd)."""
    sta = Path(frd).with_suffix(".sta")
    best = 0.0
    try:
        for ln in sta.read_text(errors="ignore").splitlines()[1:]:
            t = ln.split()
            if len(t) >= 6 and t[0].isdigit() and not t[2].endswith("U"):
                best = max(best, float(t[4]))
    except (OSError, ValueError):
        pass
    return best


def _gap_delta(case: CcxCase, disp):
    out = np.zeros(len(case.gaps))
    for i, (_e, n1, n2, dof, _k) in enumerate(case.gaps):
        out[i] = disp[n2][dof - 1] - disp[n1][dof - 1]
    return out


def _bolt_summary(case: CcxCase, disp):
    """(cortante maximo por plano, traccion maxima) de los pernos con los desplazamientos `disp` (para seguir la convergencia)."""
    vmax = 0.0
    for mb in case.meta["bolts"]:
        refs = mb["refs"]
        for i in range(len(refs) - 1):
            c = [mb["ks"] * (disp[refs[i + 1]][sh["dof"] - 1] - disp[refs[i]][sh["dof"] - 1]) for sh in mb["shear"] if sh["plane"] == i]
            vmax = max(vmax, float(np.sqrt(sum(x * x for x in c))))
    tmax = 0.0
    for (_e, n1, n2, k, ib) in case.bolt_ax:
        ax = np.asarray(case.mdl.bolts[ib].axis, float)
        tmax = max(tmax, k * float(np.dot(np.asarray(disp[n2]) - np.asarray(disp[n1]), ax / np.linalg.norm(ax))))
    return round(vmax, 3), round(tmax, 3)


def _stable(hist, nchg, nact) -> bool:
    """El conjunto activo sigue cambiando poco a poco pero las fuerzas de los pernos ya no varian (< 0.5 % dos iteraciones seguidas)."""
    if len(hist) < 4 or nchg > 0.05 * nact:
        return False
    (v1, t1), (v2, t2), (v3, t3) = hist[-3][2], hist[-2][2], hist[-1][2]
    def q(a, b, ab=0.03):
        return abs(a - b) <= max(0.005 * max(abs(a), abs(b)), ab)
    return q(v1, v2) and q(v2, v3) and q(t1, t2) and q(t2, t3)


def _new_sets(case, disp, gap_on, bolt_on, fol, tol_close=1e-5):
    """Conjunto activo siguiente: un contacto se abre si su traccion supera `fol` (kip) y se cierra si penetra mas de `tol_close`."""
    dg = _gap_delta(case, disp)
    kk = np.array([g[4] for g in case.gaps]) if case.gaps else np.zeros(0)
    on = np.zeros(len(case.gaps), bool)
    for i in gap_on:
        on[i] = True
    new_on = np.where(on, kk * dg <= fol, dg < -tol_close)
    el = _bolt_elong(case, disp)
    new_bolt = {ib for ib, v in el.items() if (v >= -1e-9 if ib in bolt_on else v > 1e-9)}
    return set(np.nonzero(new_on)[0].tolist()), new_bolt


def _bolt_elong(case: CcxCase, disp):
    out = {}
    for (_e, n1, n2, _k, ib) in case.bolt_ax:
        ax = np.asarray(case.mdl.bolts[ib].axis, float)
        ax = ax / np.linalg.norm(ax)
        out[ib] = float(np.dot(np.asarray(disp[n2]) - np.asarray(disp[n1]), ax))
    return out


def solve_case(case: CcxCase, folder: str, stem: str, ccx_path: str = "", cancel=None, progress=None, max_it: int = 14):
    """Devuelve (ok, mensaje, info) con info = {frd, gap_on, bolt_on, iters, plastic_frd}. Los archivos quedan en `folder`."""
    say = progress or (lambda m: None)
    folder = Path(folder)
    gap_on = set(range(len(case.gaps)))
    bolt_on = {ib for (_e, _a, _b, _k, ib) in case.bolt_ax}
    fol = 5e-4 * case.fref
    hist = []
    info = {"iters": 0}
    last_frd = None

    def one(plastic, tag):
        inp = folder / f"{stem}_{tag}.inp"
        case.write(str(inp), gap_on, bolt_on, plastic=plastic)
        ok, out, frd = run_ccx(str(inp), ccx_path, cancel=cancel)
        info["last_out"] = out
        return ok, out, frd

    # ---- paso 1: elastico con conjunto activo
    for it in range(max_it):
        if cancel is not None and cancel.cancelled:
            return False, mesh3d.CANCELADO, info
        say(f"CalculiX: elastico, iteracion {it + 1} de contactos ({len(gap_on)} contactos activos)")
        ok, out, frd = one(False, f"e{it % 2}")
        if not ok:
            return False, "CalculiX no genero resultados.\n\n" + out[-2500:], info
        disp, _s, _f = read_frd(frd)
        new_gap, new_bolt = _new_sets(case, disp, gap_on, bolt_on, fol)
        info["iters"] = it + 1
        info.setdefault("history", []).append((len(gap_on), len(new_gap ^ gap_on), _bolt_summary(case, disp)))
        last_frd = frd
        if new_bolt == bolt_on and len(new_gap ^ gap_on) <= max(2, int(0.004 * max(len(gap_on), 1))):
            break
        if _stable(info["history"], len(new_gap ^ gap_on), max(len(gap_on), 1)):
            gap_on, bolt_on = new_gap, new_bolt          # los resultados ya no cambian: se acepta
            break
        key = (frozenset(new_gap), frozenset(new_bolt))
        if key in hist:                          # ciclo: se queda con la interseccion de los dos ultimos estados
            gap_on, bolt_on = new_gap & gap_on, new_bolt & bolt_on
            hist.append(key)
            if len(hist) > max_it:
                break
            continue
        hist.append(key)
        gap_on, bolt_on = new_gap, new_bolt
    info.update(gap_on=gap_on, bolt_on=bolt_on, frd_elastic=last_frd)
    info["converged"] = (info["iters"] < max_it)
    if not case.opts.get("plastic", True):
        info["frd"] = last_frd
        return True, "", info
    # ---- paso 2: elasto-plastico con el conjunto activo del elastico (se repite si cambia)
    for it in range(2):
        if cancel is not None and cancel.cancelled:
            return False, mesh3d.CANCELADO, info
        say(f"CalculiX: elasto-plastico (φ·Fy), pasada {it + 1}")
        ok, out, frd = one(True, "p")
        if not ok or not finished(out):
            info["plastic_failed"] = out[-1500:]
            info["load_frac"] = load_fraction(frd) if ok else 0.0
            info["frd"] = last_frd
            return True, (f"La solucion elasto-plastica no convergio: la conexion no alcanza la carga de diseno "
                          f"(ultima carga convergida = {100 * info['load_frac']:.0f} %).  Se muestran los resultados elasticos."), info
        disp, _s, _f = read_frd(frd)
        new_gap, new_bolt = _new_sets(case, disp, gap_on, bolt_on, fol)
        info["frd"] = frd
        if new_bolt == bolt_on and len(new_gap ^ gap_on) <= max(2, int(0.004 * max(len(gap_on), 1))):
            break
        gap_on, bolt_on = new_gap, new_bolt
        info.update(gap_on=gap_on, bolt_on=bolt_on)
    return True, "", info
