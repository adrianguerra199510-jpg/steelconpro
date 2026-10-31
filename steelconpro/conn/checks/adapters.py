# -*- coding: utf-8 -*-
"""Verificacion por codigo (AISC 360-22) de las operaciones de un nudo, al estilo de RAM Connection: cada operacion de conexion se traduce a los datos
de su motor de calculo, se corre con las cargas del miembro (por caso) y se recoge la tabla D/C.

    run(prj, nodo) -> solver.Results        verificaciones, avisos y memoria de calculo

Motores: placa simple, doble angulo, asiento y placa extrema (steelconpro/conn/checks/*.py: calculos cerrados, valores contrastados a mano);
cartela (Whitmore, pernos, bloque de cortante, soldadura) y alas soldadas (flujo de las alas): `generic.py`.  Lo que no se evalua aparece en la
tabla como «NO EVALUADO» para que no pase inadvertido.
"""
from __future__ import annotations
import math
from types import SimpleNamespace

from ... import materials as M
from ...design import Check
from ...explain import Recorder
from ...shapes import CATALOG, W_SHAPE
from ..assembly import attach_info, gap_eff, tab_extra
from ..specs import (WELD_TYPES, OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET, OP_GUSSET_W, OP_COPE, OP_CONT, Nodo, Operation, Member)
from .specs import ShearTab, DoubleAngle, Seated, EndPlate, SUP_KINDS, EP_FLANGE_WELD
from . import shear_tab, double_angle, seated, endplate, generic

TOL_OTHER = 0.02          # fraccion de la fuerza principal bajo la cual una componente no considerada no se avisa


def _fr(x: float) -> str:
    return f"{x:.3g}"


def support_kind(nd: Nodo, info: dict) -> str:
    """Tipo de soporte del motor segun la cara por la que llega el miembro."""
    if info["face"] == "ala":
        return SUP_KINDS[2]                                 # ala de columna
    if info["face"] == "alma":
        return SUP_KINDS[1] if nd.vertical else SUP_KINDS[0]
    return SUP_KINDS[1]                                      # perfil hueco: se usa el espesor de pared (tw)


def _cope_of(nd: Nodo, name: str):
    return next((o for o in nd.ops_of(name) if o.kind == OP_COPE), None)


def _load_cases(nd: Nodo):
    """[(caso, {miembro: Load})] en orden de aparicion."""
    cases = {}
    for x in nd.loads:
        cases.setdefault(x.case, {})[x.member] = x
    return list(cases.items())


def _angle_label(t: float) -> str:
    for lab, tt in (("L4X4X1/4", 0.25), ("L4X4X5/16", 0.3125), ("L4X4X3/8", 0.375), ("L4X4X7/16", 0.4375), ("L4X4X1/2", 0.5), ("L4X4X5/8", 0.625)):
        if abs(tt - t) < 0.02 and CATALOG.get(lab) is not None:
            return lab
    return "L4X4X3/8"


def _seat_angle_label(t: float) -> str:
    for lab, tt in (("L6X6X1/2", 0.5), ("L6X6X5/8", 0.625), ("L6X6X3/4", 0.75), ("L6X6X7/8", 0.875), ("L6X6X1", 1.0)):
        if abs(tt - t) < 0.02 and CATALOG.get(lab) is not None:
            return lab
    return "L6X6X3/4"


class Item:
    """Una operacion de conexion lista para verificar: motor, datos del motor, y como sacar sus valores de carga de un `Load`."""
    def __init__(self, op, m, kind, spec, vals, notes=None, engine=None):
        self.op, self.m, self.kind, self.spec, self.vals, self.notes, self.engine = op, m, kind, spec, vals, notes or [], engine

    @property
    def label(self):
        return f"{self.op.kind} — {self.m.name}"


def build_items(nd: Nodo):
    """Traduce las operaciones de conexion del nudo a elementos verificables.  -> (items, avisos)"""
    items, warns = [], []
    mshape = CATALOG.get(nd.main_shape)
    for op in nd.operations:
        if not op.is_connection:
            continue
        m = nd.member_named(op.member)
        if m is None:
            warns.append(f"{op.kind}: el miembro «{op.member}» no existe.")
            continue
        info = attach_info(nd, m)
        if not info["touches"]:
            warns.append(f"** {m.name}: su eje no toca al miembro principal; la operación «{op.kind}» no se puede verificar. **")
            continue
        beam = CATALOG.get(m.shape)
        sup_kind = support_kind(nd, info)
        cope = None if tab_extra(nd, m, op) > 0 else _cope_of(nd, m.name)             # con la placa hasta las alas la viga no se corta
        cp = dict(cope_top=cope.cope_top, cope_bot=cope.cope_bot, cope_len=cope.cope_len) if cope else {}
        if not cope:
            from ..assembly import auto_cope_for
            ac = auto_cope_for(nd, m, op)                                    # corte automatico de la viga secundaria
            if ac is not None:
                cp = dict(cope_top=ac[0], cope_bot=ac[1], cope_len=ac[2])
        if op.kind in (OP_TAB, OP_WELD):
            from ..assembly import tab_dims
            from ..common import bolt_db
            n_, s_, cols_, g_, H_, W_, a_ = tab_dims(op, m, beam, bolt_db(op.bolt_size), tab_extra(nd, m, op)) if beam is not None else (max(int(op.n_bolts), 2), op.bolt_s, 1, 3.0, 9.0, 5.0, gap_eff(m) + 2.5)
            n_ = max(n_, 2)
            spec = ShearTab(beam=m.shape, beam_steel=m.steel, sup_kind=sup_kind, sup_label=nd.main_shape, sup_steel=nd.main_steel,
                            bolt_size=op.bolt_size, bolt_grade=op.bolt_grade, n=n_, s=s_, a=a_, cols=cols_, gage=g_,
                            lev_p=max((H_ - (n_ - 1) * s_) / 2.0, 0.25), leh_p=max(W_ - a_ - (cols_ - 1) * g_, 0.25),
                            tp=op.plate_t, plate_steel=op.plate_steel, gap=gap_eff(m) + tab_extra(nd, m, op), weld_size=op.weld_size, **cp)
            items.append(Item(op, m, "shear", spec, None, engine=shear_tab))
            if op.kind == OP_WELD:                                  # alas soldadas: ademas de la placa del alma, la fuerza de las alas
                items.append(Item(op, m, "flange", None, None, engine=generic))
        elif op.kind == OP_DANG:
            spec = DoubleAngle(beam=m.shape, beam_steel=m.steel, sup_kind=sup_kind, sup_label=nd.main_shape, sup_steel=nd.main_steel,
                               angle=_angle_label(op.plate_t), angle_steel=op.plate_steel, bolt_size=op.bolt_size, bolt_grade=op.bolt_grade,
                               n=max(int(op.n_bolts), 2), s=op.bolt_s, L_ang=(op.dang_H if op.dang_H > 0 else (max(int(op.n_bolts), 2) - 1) * op.bolt_s + 3.0), gap=gap_eff(m), weld_size=op.weld_size, **cp)
            items.append(Item(op, m, "shear", spec, None, engine=double_angle))
        elif op.kind == OP_SEAT:
            spec = Seated(beam=m.shape, beam_steel=m.steel, sup_kind=sup_kind, sup_label=nd.main_shape, sup_steel=nd.main_steel,
                          angle=_seat_angle_label(op.plate_t), angle_steel=op.plate_steel, bolt_size=op.bolt_size, bolt_grade=op.bolt_grade,
                          setback=max(gap_eff(m), 0.5), L_seat=(op.seat_W if op.seat_W > 0 else min(max(beam.bf if beam is not None else 8.0, 4.0), 12.0)))
            items.append(Item(op, m, "seat", spec, None, engine=seated))
        elif op.kind in (OP_EP_FLUSH, OP_EP_EXT):
            if mshape is None or mshape.kind != W_SHAPE or info["face"] != "ala":
                items.append(Item(op, m, "na", None, None, ["La verificación de placa extrema exige una columna I a la que la viga llega por la cara del ala."]))
                continue
            ext = op.kind == OP_EP_EXT
            spec = EndPlate(beam=m.shape, beam_steel=m.steel, col=nd.main_shape, col_steel=nd.main_steel, cont_plates=any(o.kind == OP_CONT and o.member == m.name for o in nd.operations),
                            plate_steel=op.plate_steel, bp=(op.ep_w if op.ep_w > 0 else (beam.bf if beam is not None else 7.0) + 1.5), tp=op.plate_t,
                            **({'g': op.ep_g} if op.ep_g > 0 else {}), bolt_size=op.bolt_size, bolt_grade=op.bolt_grade,
                            pfo=1.75, pfi=1.75, e_ext=1.5, ext_t=ext, ext_c=ext, fw_size=op.weld_size, ww_size=op.weld_size,
                            fw_type=(EP_FLANGE_WELD[1] if (op.wf_top == WELD_TYPES[0] or op.wf_bot == WELD_TYPES[0]) else EP_FLANGE_WELD[0]))
            items.append(Item(op, m, "ep", spec, None, engine=endplate))
        elif op.kind in (OP_GUSSET, OP_GUSSET_W):
            items.append(Item(op, m, "gusset", None, None, engine=generic))
    for it in items:                                    # datos que el motor de la operacion no admite (por ejemplo una viga que no es I): no se evalua
        if it.engine is not None and it.spec is not None:
            try:
                fatal = [w.strip("* ").strip() for w in it.engine.check_input(it.spec) if str(w).startswith("**")]
            except Exception as e:
                fatal = [f"{type(e).__name__}: {e}"]
            if fatal:
                it.engine, it.notes = None, fatal
    return items, warns


def _vals(item: Item, x):
    """Valores de carga del motor a partir de los esfuerzos del miembro (kip, kip·in) + avisos de lo que el motor no considera."""
    N, Vy, Vz, T, My, Mz = (x.N, x.Vy, x.Vz, x.T, x.My, x.Mz) if x else (0.0,) * 6
    notes = []
    if item.kind in ("shear", "seat"):
        V = abs(Vz)
        main = max(V, 1e-9)
        for nm, v, lim in (("N", N, TOL_OTHER * main * 2), ("Vy", Vy, TOL_OTHER * main * 2), ("T", T / 12.0, TOL_OTHER * main * 2), ("My", My / 12.0, 0.5 * main)):
            if abs(v) > max(lim, 0.5):
                notes.append(f"{nm} = {_fr(v if nm not in ('T', 'My') else v * 12)} no se considera en la verificación de corte de {item.m.name}.")
        return (V,), notes
    if item.kind == "ep":
        return (abs(My), abs(Vz)), ([f"N = {_fr(N)} y Vy = {_fr(Vy)} no se consideran en la placa extrema de {item.m.name}."] if abs(N) > 0.5 or abs(Vy) > 0.5 else [])
    return (N, Vy, Vz, T, My, Mz), []


def _units_prj(prj):
    return SimpleNamespace(units=lambda: prj.units())


def _grp(nd, op, label) -> str:
    """Rotulo del grupo de resultados de una operacion: «n. operacion — miembro»."""
    try:
        return f"{next(i for i, x in enumerate(nd.operations) if x is op) + 1}. {label}"
    except StopIteration:
        return label


def run(prj, nd: Nodo, fem_map=None):
    """Verifica todas las operaciones de conexion con todos los casos de carga.  Devuelve un `solver.Results` (D/C por verificacion)."""
    from ...solver import Results
    R = Results()
    R.closed_form = True
    items, warns = build_items(nd)
    R.warnings = list(warns)
    cases = _load_cases(nd)
    if not items and nd.base_op() is None:
        R.warnings.append("El nudo no tiene operaciones de conexión: agregue una con «Agregar operación».")
    if items and not cases:
        R.warnings.append("** No hay cargas definidas: agregue los esfuerzos de los miembros en «Cargas». **")
    if not cases:
        cases = [("Sin cargas", {})]
    us = prj.units()
    best = {}                                    # (indice del item, clave) -> (ratio, caso, Check)
    rows = []
    for ci, (cname, loads) in enumerate(cases):
        worst, gov = 0.0, "-"
        for ii, it in enumerate(items):
            if it.engine is None:
                continue
            vals, extra = _vals(it, loads.get(it.m.name))
            cks = _solve(prj, nd, it, vals, None)
            for c in cks:
                key = (ii, c.key)
                if key not in best or c.ratio > best[key][0] or (c.skip and key not in best):
                    best[key] = (c.ratio, cname, c)
                if not c.skip and c.ratio > worst:
                    worst, gov = c.ratio, f"{it.m.name}: {c.title}"
        rows.append({"name": cname, "ratio": worst, "ok": worst <= 1.0 + 1e-9, "pending": False, "gov": gov})
    R.combo_rows = rows
    R.combo_gov = max(range(len(rows)), key=lambda k: rows[k]["ratio"]) if rows else 0
    multi = len(cases) > 1
    rec = Recorder(us)
    memo = {}
    for ii, it in enumerate(items):
        if it.engine is None:
            c3 = Check(f"na_{ii}", f"{it.label} — NO EVALUADO", 0.0, 1.0, "-", "", " ".join(it.notes), skip=True)
            c3.group = _grp(nd, it.op, it.label)
            R.checks.append(c3)
            continue
        keys = [k for k in best if k[0] == ii]
        gov_case = max((best[k] for k in keys if not best[k][2].skip), key=lambda t: t[0], default=None)
        cname = gov_case[1] if gov_case else cases[0][0]
        loads = dict(cases)[cname] if cname in dict(cases) else {}
        vals, extra = _vals(it, loads.get(it.m.name))
        for n in extra:
            R.warnings.append(f"[{cname}] {n}")
        for k in keys:
            ratio, cn, c = best[k]
            c2 = Check(f"op{ii}_{c.key}", f"[{ii + 1}. {it.m.name}] {c.title}" + (f"  ({cn})" if multi and not c.skip else ""), c.demand, c.capacity, c.unit,
                       c.ref, c.note, c.skip, c.steps)
            c2.group = _grp(nd, it.op, it.label)
            R.checks.append(c2)
        rec.section(f"OPERACION {ii + 1}: {it.op.kind.upper()} — {it.m.name}  (caso {cname})")
        _solve(prj, nd, it, vals, rec)
        for w in _solve_warnings(it):
            R.warnings.append(f"{it.m.name}: {w}")
    for oi, o in enumerate(nd.operations):
        if o.kind == OP_CONT:
            c4 = Check(f"cont_{o.member}", f"[Placas de continuidad — {o.member}] Verificación de la placa de continuidad — NO EVALUADO", 0.0, 1.0, "-",
                       "AISC 360-22 J10", "Flexión local del ala, fluencia y aplastamiento del alma de la columna: verifíquelo aparte.", skip=True)
            c4.group = f"{oi + 1}. {o.kind} — {o.member}"
            R.checks.append(c4)
        if o.kind == OP_COPE:
            c5 = Check(f"cope_{o.member}", f"[Corte (cope) — {o.member}] Pandeo local del alma por el corte — NO EVALUADO", 0.0, 1.0, "-", "AISC Manual Parte 9",
                       "Las verificaciones de la conexión sí consideran el corte (sección del alma, bloque de cortante).", skip=True)
            c5.group = f"{oi + 1}. {o.kind} — {o.member}"
            R.checks.append(c5)
    from .. import ops as GOPS
    from ..assembly import build_model
    GOPS.add_checks(prj, nd, R, rec, build_model(prj))
    from .. import baseplate
    baseplate.add_checks(prj, nd, R, rec, fem_map)
    R.rec = rec
    R.item_labels = [it.label for it in items]                 # «operacion — miembro» de cada elemento verificado (para agrupar la tabla de resultados)
    return R


def _solve(prj, nd, it: Item, vals, rec):
    p = SimpleNamespace(units=lambda: prj.units())
    if it.kind == "shear" and it.engine is shear_tab:
        p.stab = it.spec
    elif it.kind == "shear":
        p.dang = it.spec
    elif it.kind == "seat":
        p.seat = it.spec
    elif it.kind == "ep":
        p.epl = it.spec
    if it.engine is generic:
        return generic.solve_one(prj, nd, it.op, it.m, vals, rec)
    return it.engine.solve_one(p, "", vals, rec)


def _solve_warnings(it: Item):
    if it.engine is None or it.spec is None:
        return []
    try:
        return [w for w in it.engine.check_input(it.spec)]
    except Exception:
        return []
