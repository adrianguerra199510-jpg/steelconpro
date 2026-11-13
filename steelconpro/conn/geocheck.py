# -*- coding: utf-8 -*-
"""Revisión automática de la geometría de una conexión ya armada (Model3D): busca lo que un modelo «de cualquier geometría» puede traer mal.

    choque        dos piezas ocupan el mismo espacio (más allá del empotramiento de dibujo de las placas soldadas)
    soldadura     un cordón que no toca a alguna de las dos piezas que une, o de largo nulo
    perno         un perno que no atraviesa alguna pieza de su agarre, que atraviesa una pieza ajena, con el agujero cortando el borde,
                  con distancia al borde o separación menores que las mínimas (AISC J3.3 / J3.4), o con la cabeza o la tuerca dentro de otra pieza
    suelta        una pieza sin soldadura ni pernos, o sin camino de unión hasta el miembro principal
    degenerada    un prisma sin espesor o sin área, o un recorte que se lleva toda la pieza

Todo es geométrico (no depende de las cargas).  `check(mdl)` devuelve [{sev, code, text, parts, at}] con sev = «error» o «aviso».
"""
from __future__ import annotations
import math

import numpy as np

TOL_TOUCH = 0.1          # in: un cordón «toca» una pieza si queda a menos de esto de su material
TOL_CLASH = 0.05          # in: penetración admitida entre piezas que no están unidas entre sí
EMBED_OK = 0.42           # in: penetración admitida entre piezas unidas (las placas se empotran 0.35 in en el soporte para el dibujo)
MAX_PTS = 220000          # puntos de muestreo por par de piezas

_DIRS = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]] +
                 [[a, b, c] for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)], float)
_DIRS = _DIRS / np.linalg.norm(_DIRS, axis=1)[:, None]

# distancia mínima al borde (AISC 360-22 Tabla J3.4), por diámetro del perno
_EDGE_MIN = [(0.5, 0.75), (0.625, 0.875), (0.75, 1.0), (0.875, 1.125), (1.0, 1.25), (1.125, 1.5), (1.25, 1.625)]


def edge_min(db: float) -> float:
    for d, e in _EDGE_MIN:
        if db <= d + 1e-6:
            return e
    return 1.25 * db


# ---------------------------------------------------------------------------------------------- punto dentro del material
def _in_poly(U, V, poly):
    """Puntos (U, V) dentro del polígono (par-impar), vectorizado."""
    ins = np.zeros(U.shape, bool)
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if y0 == y1:
            continue
        c = (y0 > V) != (y1 > V)
        xi = (x1 - x0) * (V - y0) / (y1 - y0) + x0
        ins ^= c & (U < xi)
    return ins


def _local(pr, P):
    o, U, V = (np.asarray(x, float) for x in (pr.o, pr.U, pr.V))
    W = np.cross(U, V)
    Q = P - o
    return Q @ U, Q @ V, Q @ W


def prism_mask(pr, P, holes_extra=True):
    """Puntos P (n, 3) dentro del material del prisma (con sus agujeros y sus recortes planos)."""
    u, v, w = _local(pr, P)
    m = (w >= pr.w0 - 1e-9) & (w <= pr.w1 + 1e-9)
    if pr.circle is not None:
        ro, ri = pr.circle
        r = np.hypot(u, v)
        m &= (r <= ro + 1e-9) & (r >= ri - 1e-9)
    else:
        if len(pr.poly) < 3:
            return np.zeros(len(P), bool)
        m &= _in_poly(u, v, pr.poly)
        for h in pr.holes:
            if len(h) >= 3:
                m &= ~_in_poly(u, v, h)
        if holes_extra:
            for h in pr.holes_extra:
                if len(h) >= 3:
                    m &= ~_in_poly(u, v, h)
    for (pt, nrm) in pr.cut_planes:
        m &= ((P - np.asarray(pt, float)) @ np.asarray(nrm, float)) <= 1e-9
    return m


def part_mask(part, P, holes_extra=True):
    m = np.zeros(len(P), bool)
    for pr in part.prisms:
        m |= prism_mask(pr, P, holes_extra)
    for c in getattr(part, "cuts", None) or []:
        m &= ~prism_mask(c, P)
    return m


def deep_mask(part, P, d):
    """Puntos que están dentro de la pieza a una profundidad ≥ d (aprox.: el punto y 14 vecinos a distancia d están dentro)."""
    m = part_mask(part, P)
    for k in _DIRS:
        if not m.any():
            break
        idx = np.nonzero(m)[0]
        m[idx] = part_mask(part, P[idx] + k * d)
    return m


# ---------------------------------------------------------------------------------------------- distancia de un punto a una pieza
def _seg_dist(p, a, b):
    a, b, p = np.asarray(a, float), np.asarray(b, float), np.asarray(p, float)
    ab = b - a
    L2 = float(ab @ ab)
    t = 0.0 if L2 < 1e-18 else min(1.0, max(0.0, float((p - a) @ ab) / L2))
    return float(np.linalg.norm(p - (a + t * ab)))


def _poly_edge_dist(p, poly):
    n = len(poly)
    return min(_seg_dist(p, poly[k], poly[(k + 1) % n]) for k in range(n))


def prism_dist(pr, p):
    """Distancia (aprox.) del punto p al material del prisma: 0 si está dentro."""
    P = np.asarray(p, float)[None, :]
    u, v, w = (float(x[0]) for x in _local(pr, P))
    dw = max(pr.w0 - w, 0.0, w - pr.w1)
    if pr.circle is not None:
        ro, ri = pr.circle
        r = math.hypot(u, v)
        d2 = max(r - ro, 0.0, ri - r)
    elif len(pr.poly) < 3:
        return 1e9
    else:
        ins = bool(_in_poly(np.array([u]), np.array([v]), pr.poly)[0])
        hole = next((h for h in pr.holes if len(h) >= 3 and bool(_in_poly(np.array([u]), np.array([v]), h)[0])), None)
        if ins and hole is None:
            d2 = 0.0
        elif hole is not None:
            d2 = _poly_edge_dist((u, v), hole)
        else:
            d2 = _poly_edge_dist((u, v), pr.poly)
    d = math.hypot(dw, d2)
    for (pt, nrm) in pr.cut_planes:
        s = float((np.asarray(p, float) - np.asarray(pt, float)) @ np.asarray(nrm, float))
        if s > 0:
            d = max(d, s)
    return d


def part_dist(part, p):
    return min((prism_dist(pr, p) for pr in part.prisms), default=1e9)


# ---------------------------------------------------------------------------------------------- utilidades
def _bbox(part):
    P = np.vstack([pr.corners() for pr in part.prisms])
    return P.min(axis=0), P.max(axis=0)


def _thick(part):
    t = float(getattr(part, "t", 0.0) or 0.0)
    if t > 0:
        return t
    best = 1e9
    for pr in part.prisms:
        best = min(best, abs(pr.w1 - pr.w0))
        if pr.circle is not None:
            ro, ri = pr.circle
            best = min(best, (ro - ri) if ri > 0 else 2 * ro)
        elif pr.holes and len(pr.holes[0]) >= 3 and len(pr.poly) >= 3:
            best = min(best, _poly_edge_dist(pr.poly[0], pr.holes[0]))
    return best if best < 1e8 else 0.25


def _issue(out, sev, code, text, parts=(), at=None):
    out.append({"sev": sev, "code": code, "text": text, "parts": [p for p in parts if p],
                "at": [float(x) for x in at] if at is not None else None})


def _fmt(x):
    return f"{x:.2f} in ({x * 25.4:.0f} mm)"


# ---------------------------------------------------------------------------------------------- piezas degeneradas
def _degenerate(mdl, out):
    from .geom2d import area
    for p in mdl.parts:
        for pr in p.prisms:
            if abs(pr.w1 - pr.w0) < 1e-6:
                _issue(out, "error", "degenerada", f"«{p.name}» tiene un tramo sin espesor.", [p.name])
            elif pr.circle is None and (len(pr.poly) < 3 or abs(area(pr.poly)) < 1e-6):
                _issue(out, "error", "degenerada", f"«{p.name}» tiene un contorno sin área.", [p.name])
            elif pr.cut_planes:
                C = pr.corners()
                keep = np.ones(len(C), bool)
                for (pt, nrm) in pr.cut_planes:
                    keep &= ((C - np.asarray(pt, float)) @ np.asarray(nrm, float)) <= 1e-6
                if not keep.any():
                    _issue(out, "error", "degenerada", f"El recorte de «{p.name}» se lleva toda la pieza: revise el plano o el extremo que se recorta.", [p.name],
                           C.mean(axis=0))


# ---------------------------------------------------------------------------------------------- soldaduras
def _welds(mdl, parts, out):
    bad = {}
    virtual = set(getattr(mdl, "elems", None) or {}) | {str(e[0]) for e in (getattr(mdl, "extra", None) or [])}      # elementos sin prismas (placa base, planos)
    for w in mdl.welds:
        A, B = parts.get(w.A), parts.get(w.B)
        p0, p1 = np.asarray(w.p0, float), np.asarray(w.p1, float)
        L = float(np.linalg.norm(p1 - p0))
        if (A is None and w.A in virtual) or (B is None and w.B in virtual):
            continue                                                # soldadura a un elemento que no es una pieza de prismas (placa base): no se puede medir
        if A is None or B is None:
            _issue(out, "error", "soldadura", f"La soldadura «{w.name}» une una pieza que no existe ({w.A if A is None else w.B}).", [w.A, w.B], (p0 + p1) / 2)
            continue
        if L < 0.05:
            _issue(out, "aviso", "soldadura", f"La soldadura «{w.name}» ({w.A} — {w.B}) tiene largo nulo.", [w.A, w.B], p0)
            continue
        for part, nm, other in ((A, w.A, w.B), (B, w.B, w.A)):
            d = max(part_dist(part, q) for q in (p0, (p0 + p1) / 2.0, p1))
            if d > TOL_TOUCH:
                key = (w.group or w.name.rsplit("-", 1)[0], nm, other)
                e = bad.setdefault(key, {"d": 0.0, "n": 0, "L": 0.0, "at": (p0 + p1) / 2.0, "names": []})
                e["n"] += 1
                e["L"] += L
                e["names"].append(w.name)
                if d > e["d"]:
                    e["d"], e["at"] = d, (p0 + p1) / 2.0
    for (grp, nm, other), e in bad.items():
        which = e["names"][0] if e["n"] == 1 else f"{e['n']} cordones del grupo «{grp}»"
        _issue(out, "error", "soldadura", f"Soldadura {which} entre «{other}» y «{nm}»: el cordón no toca a «{nm}» (queda a {_fmt(e['d'])}).", [nm, other], e["at"])


# ---------------------------------------------------------------------------------------------- pernos
def _bolts(mdl, parts, boxes, out):
    lst = list(mdl.bolts)
    seen_edge = set()
    grp = {}                                                           # hallazgos repetidos de un mismo grupo de pernos se informan una sola vez

    def add(kind, sev, b, pn, at, val=None, parts_=()):
        e = grp.setdefault((kind, b.tag.rsplit("-", 1)[0], pn), {"sev": sev, "tags": [], "at": at, "val": val, "parts": list(parts_) or [pn], "db": b.db})
        e["tags"].append(b.tag)
        if val is not None and (e["val"] is None or val < e["val"]):
            e["val"], e["at"] = val, at
    for b in lst:
        ax = np.asarray(b.axis, float)
        n = float(np.linalg.norm(ax))
        if n < 1e-9:
            _issue(out, "error", "perno", f"El perno «{b.tag}» no tiene eje.", [], b.p)
            continue
        ax = ax / n
        p = np.asarray(b.p, float)
        names = [g[0] for g in b.grip]
        prev = None
        for (pn, s0, s1) in b.grip:
            part = parts.get(pn)
            mid = p + ax * 0.5 * (s0 + s1)
            if part is None:
                _issue(out, "error", "perno", f"El perno «{b.tag}» agarra una pieza que no existe ({pn}).", [pn], mid)
                continue
            if abs(s1 - s0) < 1e-6:
                continue
            if not bool(part_mask(part, mid[None, :], holes_extra=False)[0]):
                add("fuera", "error", b, pn, mid)
                prev = (pn, s0, s1)
                continue
            if prev is not None and min(s0, s1) - max(prev[1], prev[2]) > 0.07 and not any(parts[q].kind in ("brace", "column") for q in (prev[0], pn) if q in parts):      # el aire dentro de un tubo (cartela en ranura) es normal
                add("hueco", "aviso", b, f"{prev[0]}» y «{pn}", mid, -(min(s0, s1) - max(prev[1], prev[2])), [prev[0], pn])
            prev = (pn, s0, s1)
            # distancia del eje al borde de la pieza
            for pr in part.prisms:
                if pr.circle is not None or len(pr.poly) < 3:
                    continue
                W = np.cross(np.asarray(pr.U, float), np.asarray(pr.V, float))
                if abs(float(W @ ax)) < 0.9:
                    continue
                u, v, w = (float(x[0]) for x in _local(pr, mid[None, :]))
                if not (pr.w0 - 0.05 <= w <= pr.w1 + 0.05) or not bool(_in_poly(np.array([u]), np.array([v]), pr.poly)[0]):
                    continue
                de = _poly_edge_dist((u, v), pr.poly)
                for (pt, nrm) in pr.cut_planes:
                    nn = np.asarray(nrm, float)
                    lat = float(np.linalg.norm(nn - W * float(nn @ W)))
                    if lat > 1e-6:
                        de = min(de, -float((mid - np.asarray(pt, float)) @ nn) / lat)
                key = (b.tag, pn)
                if key in seen_edge:
                    continue
                if de < b.dh / 2.0 - 1e-6:
                    seen_edge.add(key)
                    add("borde_err", "error", b, pn, mid, max(de, 0.0))
                elif de < edge_min(b.db) - 0.02:
                    seen_edge.add(key)
                    add("borde_av", "aviso", b, pn, mid, de)
        # el vástago, la cabeza y la tuerca no deben meterse en piezas ajenas
        s_lo = min([b.head_s, b.nut_s] + [min(g[1], g[2]) for g in b.grip])
        s_hi = max([b.head_s, b.nut_s] + [max(g[1], g[2]) for g in b.grip])
        shank = np.array([p + ax * s for s in np.linspace(s_lo + 0.02, s_hi - 0.02, 9)])
        ref = np.array([1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = np.cross(ax, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(ax, e1)
        ring = [math.cos(a) * e1 + math.sin(a) * e2 for a in np.linspace(0, 2 * math.pi, 6, endpoint=False)]
        sgn = 1.0 if b.nut_s >= b.head_s else -1.0
        head = np.array([p + ax * (b.head_s - sgn * 0.3 * b.db) + r * 0.7 * b.db for r in ring])
        nut = np.array([p + ax * (b.nut_s + sgn * 0.4 * b.db) + r * 0.7 * b.db for r in ring])
        for nm, part in parts.items():
            lo, hi = boxes[nm]
            allp = np.vstack([shank, head, nut])
            if (allp.max(axis=0) < lo - 0.1).any() or (allp.min(axis=0) > hi + 0.1).any():
                continue
            if nm not in names and part_mask(part, shank).any():
                add("ajena", "error", b, nm, p + ax * 0.5 * (s_lo + s_hi), None, [nm] + names)
            elif part_mask(part, head).sum() >= 2 or part_mask(part, nut).sum() >= 2:
                wh = "cabeza" if part_mask(part, head).sum() >= 2 else "tuerca"
                add(wh, "aviso", b, nm, p + ax * (b.head_s if wh == "cabeza" else b.nut_s), None, [nm] + names)
    for (kind, g, pn), e in grp.items():
        n = len(e["tags"])
        short = [t.rsplit("-", 1)[-1] for t in e["tags"]]
        who = f"El perno «{e['tags'][0]}»" if n == 1 else f"{n} pernos del grupo «{g}» ({', '.join(short[:6])}{'…' if n > 6 else ''})"
        pl = n > 1
        if kind == "fuera":
            txt = f"{who} no atravies{'an' if pl else 'a'} «{pn}»: su eje cae fuera de la pieza (revise la posición del grupo de pernos)."
        elif kind == "ajena":
            txt = f"{who} atravies{'an' if pl else 'a'} «{pn}», que no está en su agarre."
        elif kind == "borde_err":
            txt = f"{who}: el agujero corta el borde de «{pn}» (el eje queda a {_fmt(e['val'])} del borde)."
        elif kind == "borde_av":
            txt = f"{who} en «{pn}»: distancia al borde {_fmt(e['val'])}, menor que la mínima {_fmt(edge_min(e['db']))} (AISC Tabla J3.4)."
        elif kind == "hueco":
            txt = f"{who}: hay {_fmt(-e['val'])} de separación entre «{pn}» dentro del agarre."
        else:
            txt = f"{who}: la {kind} queda dentro de «{pn}»; no hay espacio para colocarlo o apretarlo."
        _issue(out, e["sev"], "perno", txt, e["parts"], e["at"])
    # separación entre pernos que comparten pieza
    close = {}
    for i in range(len(lst)):
        a = lst[i]
        axa = np.asarray(a.axis, float)
        axa = axa / max(float(np.linalg.norm(axa)), 1e-12)
        na = {g[0] for g in a.grip}
        for j in range(i + 1, len(lst)):
            c = lst[j]
            if not (na & {g[0] for g in c.grip}):
                continue
            axc = np.asarray(c.axis, float)
            axc = axc / max(float(np.linalg.norm(axc)), 1e-12)
            if abs(float(axa @ axc)) < 0.99:
                continue
            dv = np.asarray(c.p, float) - np.asarray(a.p, float)
            lat = float(np.linalg.norm(dv - axa * float(dv @ axa)))
            db = max(a.db, c.db)
            if lat < 2.0 * db * 4.0 / 3.0 - 0.02:                              # 2⅔·d
                grp = (a.tag.rsplit("-", 1)[0], c.tag.rsplit("-", 1)[0])
                e = close.setdefault(grp, {"d": 1e9, "n": 0, "pair": None, "db": db, "dh": max(a.dh, c.dh), "parts": sorted(na & {g[0] for g in c.grip})})
                e["n"] += 1
                if lat < e["d"]:
                    e["d"], e["pair"] = lat, (a, c)
    for grp, e in close.items():
        a, c = e["pair"]
        at = (np.asarray(a.p, float) + np.asarray(c.p, float)) / 2.0
        if e["d"] < e["dh"] - 1e-6:
            _issue(out, "error", "perno", f"Pernos «{a.tag}» y «{c.tag}»: los agujeros se superponen (separación {_fmt(e['d'])}).", e["parts"], at)
        else:
            _issue(out, "aviso", "perno", f"Pernos «{a.tag}» y «{c.tag}»" + (f" (y {e['n'] - 1} pares más)" if e["n"] > 1 else "") +
                   f": separación {_fmt(e['d'])}, menor que la mínima 2⅔·d = {_fmt(e['db'] * 8.0 / 3.0)} (AISC J3.3).", e["parts"], at)


# ---------------------------------------------------------------------------------------------- choques entre piezas
def _sample_overlap(S, B, boxS, boxB, h):
    """Puntos de una rejilla (en el sistema local de cada prisma de S) que están dentro de S y dentro de B.  -> (puntos, paso)"""
    lo = np.maximum(boxS[0], boxB[0]) - 1e-6
    hi = np.minimum(boxS[1], boxB[1]) + 1e-6
    if (hi < lo).any():
        return np.zeros((0, 3)), h
    cor = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    pts = []
    for pr in S.prisms:
        u, v, w = _local(pr, cor)
        if pr.circle is not None:
            r = pr.circle[0]
            pu = pv = (-r, r)
        elif len(pr.poly) >= 3:
            xs, ys = [q[0] for q in pr.poly], [q[1] for q in pr.poly]
            pu, pv = (min(xs), max(xs)), (min(ys), max(ys))
        else:
            continue
        rng = [(max(pu[0], u.min()), min(pu[1], u.max())), (max(pv[0], v.min()), min(pv[1], v.max())), (max(pr.w0, w.min()), min(pr.w1, w.max()))]
        if any(b_ < a_ for a_, b_ in rng):
            continue
        hh = h
        while True:
            ns = [max(int(math.ceil((b_ - a_) / hh)) + 1, 2) for a_, b_ in rng]
            if ns[0] * ns[1] * ns[2] <= MAX_PTS:
                break
            hh *= 1.3
        gu, gv, gw = (np.linspace(a_ + 1e-4, b_ - 1e-4, n_) if b_ - a_ > 2e-4 else np.array([(a_ + b_) / 2.0]) for (a_, b_), n_ in zip(rng, ns))
        Ug, Vg, Wg = np.meshgrid(gu, gv, gw, indexing="ij")
        o, U, V = (np.asarray(x, float) for x in (pr.o, pr.U, pr.V))
        Wv = np.cross(U, V)
        P = o + Ug.reshape(-1, 1) * U + Vg.reshape(-1, 1) * V + Wg.reshape(-1, 1) * Wv
        P = P[prism_mask(pr, P)]
        if len(P):
            for c in getattr(S, "cuts", None) or []:
                P = P[~prism_mask(c, P)]
        if len(P):
            P = P[part_mask(B, P)]
        if len(P):
            pts.append(P)
    return (np.vstack(pts) if pts else np.zeros((0, 3))), h


def _clashes(mdl, parts, boxes, linked, out):
    names = list(parts)
    vol = {n: float(np.prod(np.maximum(boxes[n][1] - boxes[n][0], 1e-6))) for n in names}
    tk = {n: _thick(parts[n]) for n in names}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            la, ha = boxes[a]
            lb, hb = boxes[b]
            if (ha < lb).any() or (hb < la).any():
                continue
            S, B = (a, b) if vol[a] <= vol[b] else (b, a)
            h = min(max(min(tk[a], tk[b]) / 3.0, 0.04), 0.3)
            P, _h = _sample_overlap(parts[S], parts[B], boxes[S], boxes[B], h)
            if not len(P):
                continue
            allow = EMBED_OK if frozenset((a, b)) in linked else TOL_CLASH
            deep = deep_mask(parts[S], P, 0.03)
            if deep.any():
                idx = np.nonzero(deep)[0]
                deep[idx] = deep_mask(parts[B], P[idx], allow)
            if not deep.any():
                continue
            Q = P[deep]
            ext = Q.max(axis=0) - Q.min(axis=0)
            size = float(np.sort(ext)[-1])
            _issue(out, "error", "choque", f"«{a}» y «{b}» se cruzan: ocupan el mismo espacio en una zona de unos {_fmt(max(size, h))} de largo.", [a, b], Q.mean(axis=0))


# ---------------------------------------------------------------------------------------------- piezas sueltas
def _links(mdl, parts):
    linked = set()
    for w in mdl.welds:
        if w.A in parts and w.B in parts and w.A != w.B:
            linked.add(frozenset((w.A, w.B)))
    for b in mdl.bolts:
        ns = [g[0] for g in b.grip if g[0] in parts]
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                if ns[i] != ns[j]:
                    linked.add(frozenset((ns[i], ns[j])))
    for pair in getattr(mdl, "bonded", None) or []:
        if len(pair) >= 2 and pair[0] in parts and pair[1] in parts and pair[0] != pair[1]:
            linked.add(frozenset((pair[0], pair[1])))
    return linked


def _loose(mdl, parts, linked, out):
    adj = {n: set() for n in parts}
    for pr in linked:
        a, b = tuple(pr)
        adj[a].add(b)
        adj[b].add(a)
    main = next((p.name for p in mdl.parts if p.kind == "column"), None)
    reach = set()
    if main is not None:
        stack = [main]
        while stack:
            x = stack.pop()
            if x in reach:
                continue
            reach.add(x)
            stack.extend(adj[x] - reach)
    for p in mdl.parts:
        if p.name == main:
            continue
        member = p.kind == "brace"
        if not adj[p.name]:
            if member:
                _issue(out, "aviso", "suelta", f"El miembro «{p.name}» no está unido a nada: le falta una conexión (o la soldadura / los pernos de la que tiene).", [p.name])
            else:
                _issue(out, "error", "suelta", f"«{p.name}» está suelta: no tiene soldadura ni pernos que la unan a otra pieza.", [p.name])
        elif main is not None and p.name not in reach:
            _issue(out, "aviso", "suelta", f"«{p.name}» no tiene camino de unión hasta el miembro principal «{main}» (está unida solo a {', '.join(sorted(adj[p.name]))}).",
                   [p.name] + sorted(adj[p.name]))


# ---------------------------------------------------------------------------------------------- entrada
def check(mdl, clashes: bool = True) -> list:
    """Revisión geométrica completa del modelo armado.  -> [{sev, code, text, parts, at}], los errores primero."""
    out = []
    parts = {}
    for p in mdl.parts:
        if p.prisms:
            parts.setdefault(p.name, p)
    boxes = {n: _bbox(p) for n, p in parts.items()}
    _degenerate(mdl, out)
    _welds(mdl, parts, out)
    _bolts(mdl, parts, boxes, out)
    linked = _links(mdl, parts)
    if clashes:
        _clashes(mdl, parts, boxes, linked, out)
    _loose(mdl, parts, linked, out)
    order = {"error": 0, "aviso": 1}
    out.sort(key=lambda e: (order.get(e["sev"], 2), e["code"]))
    return out


def summary(issues: list) -> dict:
    ne = sum(1 for e in issues if e["sev"] == "error")
    na = sum(1 for e in issues if e["sev"] == "aviso")
    return {"errors": ne, "warnings": na, "ok": ne == 0}
