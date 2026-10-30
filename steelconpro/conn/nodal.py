# -*- coding: utf-8 -*-
"""Analisis nodal: equilibrio del nudo para cada caso de carga.

Los esfuerzos de cada miembro conectado se escriben en el extremo que llega al nudo, en sus ejes locales (x a lo largo del miembro, hacia afuera del nudo; N > 0 =
traccion; z el peralte; y = z × x) y son la ACCION DEL MIEMBRO SOBRE EL NUDO.  Opcionalmente hay una carga externa aplicada al nudo (miembro «@nudo», en ejes globales
X, Y, Z: N = Fx, Vy = Fy, Vz = Fz, T = Mx, My, Mz) y las cargas dadas del miembro principal en uno de sus lados.  La accion del miembro principal en el otro lado (el lado que
equilibra, `Nodo.balance_end`) sale del equilibrio de fuerzas y de momentos del nudo (momentos respecto del punto de cruce de los ejes, el origen):

    R_principal = −(Σ fuerzas de los demas + carga externa)       M_principal = −(Σ (M_i + r_i × F_i) + momento externo)

La placa base del extremo de un miembro (el lado que equilibra del principal, el lado dado del principal o un miembro conectado) recibe de ahi sus combinaciones de carga:
la carga que el miembro aplica a la placa es la opuesta a la reaccion del apoyo sobre el miembro, trasladada del nudo al centro de la placa.
"""
from __future__ import annotations
import math
import numpy as np

from . import assembly as AS
from .specs import Nodo, Load

NODE = "@nudo"                      # miembro de la carga externa aplicada al nudo (ejes globales)
KEYS = ("N", "Vy", "Vz", "T", "My", "Mz")


def cases_of(nd: Nodo):
    """[(caso, [Load])] en orden de aparicion."""
    out = {}
    for x in nd.loads:
        out.setdefault(x.case, []).append(x)
    return list(out.items())


def local_axes(nd: Nodo, name: str, out_sign: int = 1):
    """(x, y, z) del miembro `name`: x hacia afuera del nudo, z el peralte, y = z × x.  Para el principal, `out_sign` es el lado (+1 / −1)."""
    if name == nd.main_name:
        A, msx, msy = AS.main_frame(nd)
        x = A * (1.0 if out_sign >= 0 else -1.0)
        z = msy
        return x, np.cross(z, x), z
    m = nd.member_named(name)
    if m is None:
        return None
    A, sx, sy = AS.member_frame(m)
    return A, np.cross(sy, A), sy


def _vec(l: Load, axes):
    x, y, z = axes
    F = l.N * x + l.Vy * y + l.Vz * z
    M = l.T * x + l.My * y + l.Mz * z
    return F, M


def _node_point(nd: Nodo, name: str):
    if name == nd.main_name:
        return np.zeros(3)
    m = nd.member_named(name)
    return AS.attach_point(nd, m)[0]


def balance(nd: Nodo, loads: list) -> dict:
    """Equilibrio del nudo para un caso: `loads` = [Load] del caso.  Devuelve filas por miembro (fuerza y momento en ejes globales respecto del nudo), la resultante,
    la reaccion del miembro principal en el lado que equilibra y sus componentes en los ejes locales de ese lado."""
    bal = -1 if int(getattr(nd, "balance_end", -1)) < 0 else 1
    rows, F_tot, M_tot = [], np.zeros(3), np.zeros(3)
    for l in loads:
        if l.member == NODE:
            F = np.array([l.N, l.Vy, l.Vz], float)
            M = np.array([l.T, l.My, l.Mz], float)
            rows.append({"member": "Carga externa en el nudo", "F": F.tolist(), "M": M.tolist(), "given": True})
            F_tot += F
            M_tot += M
            continue
        if l.member == nd.main_name:
            side = int(getattr(l, "side", 0)) or -bal
            if side == bal:                                  # el lado que equilibra se calcula: se ignora lo escrito
                continue
            ax = local_axes(nd, nd.main_name, side)
            F, M = _vec(l, ax)
            rows.append({"member": f"{nd.main_name} (lado {'+' if side > 0 else '−'})", "F": F.tolist(), "M": M.tolist(), "given": True})
            F_tot += F
            M_tot += M
            continue
        ax = local_axes(nd, l.member)
        if ax is None:
            continue
        F, M = _vec(l, ax)
        P = _node_point(nd, l.member)
        Mo = M + np.cross(P, F)
        rows.append({"member": l.member, "F": F.tolist(), "M": Mo.tolist(), "given": True})
        F_tot += F
        M_tot += Mo
    R = -F_tot
    MR = -M_tot
    ax = local_axes(nd, nd.main_name, bal)
    loc_F = [float(np.dot(R, a)) for a in ax]
    loc_M = [float(np.dot(MR, a)) for a in ax]
    rows.append({"member": f"{nd.main_name} (lado {'+' if bal > 0 else '−'}) — por equilibrio", "F": R.tolist(), "M": MR.tolist(), "given": False})
    return {"rows": rows, "sum_F": F_tot.tolist(), "sum_M": M_tot.tolist(), "R": R.tolist(), "M": MR.tolist(), "side": bal,
            "main_local": dict(zip(("N", "Vy", "Vz", "T", "My", "Mz"), loc_F + loc_M))}


def base_combos(prj, nd: Nodo):
    """Combinaciones de carga de la placa base (LoadCombo) sacadas del analisis nodal, o None si no hay casos de carga o no se puede colocar la placa."""
    r = _base_cases(prj, nd)
    return [x[0] for x in r] if r else None


def _base_cases(prj, nd: Nodo):
    """[(LoadCombo, E, Fp, Mp)]: ademas de la combinacion, el centro de la placa y la fuerza y el momento globales que recibe."""
    from ..model import LoadCombo
    from . import baseplate as BP
    op = nd.base_op()
    cases = cases_of(nd)
    if op is None or not cases:
        return None
    name, m = BP.base_member(nd, op)
    if name is None:
        return None
    A_main, msx, msy = AS.main_frame(nd)
    # extremo libre y ejes de la placa (los de la seccion del miembro; la placa se gira con section.rotation respecto de ellos)
    if m is None:
        lneg, lpos = nd.lengths()
        if lneg + lpos < 1.0:
            lneg = lpos = 24.0
        side = 1 if op.end >= 0 else -1
        E = A_main * (lpos if side > 0 else -lneg)
        A_in, sx, sy = (-A_main, msx, -msy) if side > 0 else (A_main, msx, msy)
    else:
        side = 0
        A_in0, sx0, sy0 = AS.member_frame(m)
        P0, o2 = AS.attach_point(nd, m)
        ext = AS.outer_extent(AS.shape_of(nd.main_shape))
        d2 = (float(np.dot(A_in0, msx)), float(np.dot(A_in0, msy)))
        s_ex = AS.exit_dist(ext, o2, d2) or 0.0
        E = P0 + A_in0 * (s_ex + max(m.gap, 0.0) + max(m.L, 1.0))
        A_in, sx, sy = -A_in0, sx0, -sy0
    rot = math.radians(float(prj.section.rotation))
    c, s = math.cos(rot), math.sin(rot)
    Rz = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])          # Rz(−rotacion)
    Fm = np.column_stack([sx, sy, A_in]) @ Rz
    ex, ey, ez = Fm[:, 0], Fm[:, 1], Fm[:, 2]
    out = []
    for cname, loads in cases:
        bal = balance(nd, loads)
        if m is None:
            if side == bal["side"]:
                R, MR = np.array(bal["R"]), np.array(bal["M"])
            else:                                                    # lado dado del principal: lo escrito (o cero)
                R, MR = np.zeros(3), np.zeros(3)
                for l in loads:
                    if l.member == nd.main_name and (int(getattr(l, "side", 0)) or -bal["side"]) == side:
                        R, MR = _vec(l, local_axes(nd, nd.main_name, side))
        else:
            R, MR = np.zeros(3), np.zeros(3)
            for l in loads:
                if l.member == name:
                    F, M = _vec(l, local_axes(nd, name))
                    R, MR = F, M + np.cross(_node_point(nd, name), F)
        # accion del extremo del miembro sobre la placa = −(accion del apoyo sobre el miembro); el apoyo equilibra al tramo entre el nudo y la placa
        Fp = -R
        Mp = -MR - np.cross(-E, R)            # momento respecto del centro de la placa: −M_R − (O − E) × R
        out.append((LoadCombo(cname, float(np.dot(R, ez)), float(np.dot(Mp, ex)), float(-np.dot(Mp, ey)), float(np.dot(Fp, ex)), float(np.dot(Fp, ey))), E, Fp, Mp))
    return out


def _box(E, R):
    E = np.asarray(E, float)
    return (float(E[0] - R), float(E[0] + R), float(E[1] - R), float(E[1] + R), float(E[2] - R), float(E[2] + R))


def fem_conditions(nd: Nodo, loads: list, ends: dict, lneg: float, lpos: float, mshape):
    """Apoyo y cargas del modelo FEM de un caso de carga: el lado que equilibra del principal se empotra; en el otro lado del principal y en el extremo libre de cada
    miembro conectado se aplica la accion dada (fuerza y momento trasladados al extremo).  Devuelve (apoyos, cargas) del modelo 3D."""
    from .fem.model3d import FaceSel, LoadApp, Support
    A = AS.main_frame(nd)[0]
    bal = balance(nd, loads)
    sb = bal["side"]
    Rm = max(mshape.d, mshape.bf) / 2.0 + 1.0
    O = np.zeros(3)
    E_of = lambda side: A * side * (lpos if side > 0 else lneg)             # noqa: E731
    sups = [Support("Apoyo del principal", FaceSel(nd.main_name, _box(E_of(sb), Rm), tuple(float(x) for x in A * sb)), (1, 2, 3))]
    lds = []
    sg = -sb
    Fg, Mg = np.zeros(3), np.zeros(3)
    for l in loads:
        if l.member == nd.main_name and (int(getattr(l, "side", 0)) or -sb) == sg:
            F, M = _vec(l, local_axes(nd, nd.main_name, sg))
            Fg, Mg = Fg + F, Mg + M
        elif l.member == NODE:                                            # carga externa del nudo: se traslada al extremo del lado dado
            Fg, Mg = Fg + np.array([l.N, l.Vy, l.Vz], float), Mg + np.array([l.T, l.My, l.Mz], float)
    Eg = E_of(sg)
    if np.linalg.norm(Fg) > 1e-9 or np.linalg.norm(Mg) > 1e-9:
        lds.append(LoadApp(f"Carga de {nd.main_name}", FaceSel(nd.main_name, _box(Eg, Rm), tuple(float(x) for x in A * sg)), tuple(float(x) for x in Eg),
                           tuple(float(x) for x in Fg), tuple(float(x) for x in (Mg + np.cross(O - Eg, Fg)))))
    for l in loads:
        if l.member in (nd.main_name, NODE) or l.member not in ends:
            continue
        F, M = _vec(l, local_axes(nd, l.member))
        if np.linalg.norm(F) < 1e-9 and np.linalg.norm(M) < 1e-9:
            continue
        E, dirv, R = ends[l.member]
        E = np.asarray(E, float)
        lds.append(LoadApp(f"Carga de {l.member}", FaceSel(l.member, _box(E, R), tuple(float(x) for x in dirv)), tuple(float(x) for x in E),
                           tuple(float(x) for x in F), tuple(float(x) for x in (M + np.cross(_node_point(nd, l.member) - E, F)))))
    return sups, lds


def _draw_items(nd: Nodo, loads: list, bal: dict, ends: dict) -> list:
    """Cargas del caso para dibujarlas en el visor, cada una en el EXTREMO de su elemento (fuerza y momento globales, trasladados al extremo):
    [{pos, F, M, kind, name}].  `ends` = {miembro: punto del extremo libre}."""
    A = AS.main_frame(nd)[0]
    lneg, lpos = nd.lengths()
    if lneg + lpos < 1.0:
        lneg = lpos = 24.0
    Eside = lambda side: A * side * (lpos if side > 0 else lneg)                  # noqa: E731
    O = np.zeros(3)
    items = []
    for l in loads:
        if l.member == NODE:
            items.append({"pos": [0.0, 0.0, 0.0], "F": [l.N, l.Vy, l.Vz], "M": [l.T, l.My, l.Mz], "name": "Nudo", "kind": "ext"})
            continue
        if l.member == nd.main_name:
            side = int(getattr(l, "side", 0)) or -bal["side"]
            if side == bal["side"]:
                continue
            F, M = _vec(l, local_axes(nd, nd.main_name, side))
            E = Eside(side)
            items.append({"pos": E.tolist(), "F": F.tolist(), "M": (M + np.cross(O - E, F)).tolist(), "name": nd.main_name, "kind": "main"})
            continue
        ax = local_axes(nd, l.member)
        if ax is None or l.member not in ends:
            continue
        F, M = _vec(l, ax)
        E = np.asarray(ends[l.member], float)
        items.append({"pos": E.tolist(), "F": F.tolist(), "M": (M + np.cross(_node_point(nd, l.member) - E, F)).tolist(), "name": l.member, "kind": "member"})
    Eb = Eside(bal["side"])
    R, MR = np.array(bal["R"]), np.array(bal["M"])
    items.append({"pos": Eb.tolist(), "F": R.tolist(), "M": (MR + np.cross(O - Eb, R)).tolist(), "name": nd.main_name + " (reacción)", "kind": "reaction"})
    return items


def _base_at_balance(nd: Nodo) -> bool:
    op = nd.base_op()
    return op is not None and (op.member == nd.main_name or not op.member) and (1 if op.end >= 0 else -1) == (1 if int(getattr(nd, "balance_end", -1)) >= 0 else -1)


def analysis(prj, nd: Nodo) -> dict:
    """Resumen del analisis nodal para la interfaz: por caso, las filas del equilibrio, lo que se dibuja y las cargas que recibe la placa base."""
    cases = cases_of(nd)
    bc = _base_cases(prj, nd) if nd.base_op() is not None else None
    ends = {t[1]: t[0] for t in AS.build_model(prj).tags}                 # extremo libre de cada miembro conectado
    out = []
    for i, (cname, loads) in enumerate(cases):
        b = balance(nd, loads)
        b["case"] = cname
        b["draw"] = _draw_items(nd, loads, b, ends)
        if bc:
            cb, E, Fp, Mp = bc[i]
            b["base"] = {"Pu": cb.Pu, "Mux": cb.Mux, "Muy": cb.Muy, "Vux": cb.Vux, "Vuy": cb.Vuy}
            b["draw"] = [d for d in b["draw"] if d["kind"] != "reaction" or not _base_at_balance(nd)]      # la carga de la placa base ya es la reaccion
            # la carga de la placa base se calcula por dentro (se muestra en la pestaña Nudo), no se dibuja: las flechas van en los extremos de los miembros
        out.append(b)
    return {"cases": out, "balance_end": int(getattr(nd, "balance_end", -1)), "base": bool(bc)}
