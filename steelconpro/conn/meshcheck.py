# -*- coding: utf-8 -*-
"""Verificación de las MALLAS que ve el usuario (las caras de cada pieza), no del modelo de ingeniería (para eso está `geocheck`).

`check_faces(faces)` revisa una lista de polígonos 3D como superficie sólida:
    abierta        una arista que solo pertenece a una cara (tapa que falta, hueco en la superficie)
    en T           arista abierta cuyo vecino tiene un vértice a mitad de camino (cara no conforme: aparece como línea falsa y puede dejar rendijas)
    no-variedad    una arista compartida por más de dos caras
    orientación    dos caras vecinas recorren la arista en el mismo sentido (normales contradictorias)
    degenerada     cara sin área o con menos de tres vértices distintos
    duplicada      dos caras con los mismos vértices (caras dobles: parpadean en el visor)
    volumen        el volumen con signo es ≤ 0 (normales hacia adentro) o no coincide con el esperado
y `check_prism(pr)` además compara el sólido de la malla (número de arrollamiento) con el material que dice `geocheck.prism_mask` en puntos al azar.
"""
from __future__ import annotations
import math

import numpy as np

from .fem.model3d import Prism

TOL = 1e-6


def _weld(faces, tol=TOL):
    """Une los vértices a menos de `tol`: -> (puntos únicos (n,3), [lista de ids por cara])."""
    pts = np.array([q for f in faces for q in f], float).reshape(-1, 3)
    if len(pts) == 0:
        return np.zeros((0, 3)), []
    from scipy.spatial import cKDTree
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    tree = cKDTree(pts)
    pairs = tree.query_pairs(tol, output_type="ndarray")
    n = len(pts)
    if len(pairs):
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
        _nc, lab = connected_components(g, directed=False)
    else:
        lab = np.arange(n)
    uniq = {}
    rep = np.zeros((int(lab.max()) + 1, 3))
    cnt = np.zeros(int(lab.max()) + 1)
    np.add.at(rep, lab, pts)
    np.add.at(cnt, lab, 1)
    rep /= cnt[:, None]
    ids, k = [], 0
    for f in faces:
        m = len(f)
        loop = [int(lab[k + i]) for i in range(m)]
        k += m
        ids.append(loop)
    del uniq
    return rep, ids


def _poly_area_vec(P):
    nv = np.zeros(3)
    n = len(P)
    for i in range(n):
        nv += np.cross(P[i], P[(i + 1) % n])
    return 0.5 * nv


def check_faces(faces, tol=TOL, expect_volume=None, vol_rtol=0.02, name=""):
    """-> {ok, errors: [texto], vol, nf, open, tj, ...}"""
    err = []
    res = {"nf": len(faces), "open": 0, "tj": 0, "nonman": 0, "orient": 0, "degen": 0, "dup": 0, "vol": 0.0}
    if not faces:
        res.update(ok=True, errors=[], empty=True)
        return res
    P, ids = _weld(faces, tol)
    loops, keep = [], []
    for fi, loop in enumerate(ids):
        lp = [loop[i] for i in range(len(loop)) if loop[i] != loop[i - 1]]
        if len(lp) >= 2 and lp[0] == lp[-1]:
            lp = lp[:-1]
        if len(lp) < 3:
            res["degen"] += 1
            err.append(f"cara {fi}: menos de tres vértices distintos")
            continue
        area = np.linalg.norm(_poly_area_vec(P[lp]))
        if area < 1e-9:
            res["degen"] += 1
            err.append(f"cara {fi}: área nula ({area:.2e})")
            continue
        loops.append(lp)
        keep.append(fi)
    dseen = {}
    for lp, fi in zip(loops, keep):
        k = tuple(sorted(lp))
        if k in dseen:
            res["dup"] += 1
            err.append(f"cara {fi} duplicada de la {dseen[k]}")
        else:
            dseen[k] = fi
    de = {}
    for lp in loops:
        m = len(lp)
        for i in range(m):
            e = (lp[i], lp[(i + 1) % m])
            de[e] = de.get(e, 0) + 1
    und = {}
    for (a, b), c in de.items():
        k = (min(a, b), max(a, b))
        und.setdefault(k, [0, 0])
        und[k][0 if a < b else 1] += c
    opens = []
    for (a, b), (f_, r_) in und.items():
        tot = f_ + r_
        if tot == 1:
            opens.append((a, b))
        elif tot > 2:
            res["nonman"] += 1
            err.append(f"arista {a}-{b} compartida por {tot} caras")
        elif f_ != 1 or r_ != 1:
            res["orient"] += 1
            err.append(f"arista {a}-{b} recorrida dos veces en el mismo sentido (orientación incoherente)")
    if opens:
        from scipy.spatial import cKDTree
        tree = cKDTree(P)
        for (a, b) in opens:
            pa, pb = P[a], P[b]
            mid = 0.5 * (pa + pb)
            rad = 0.5 * float(np.linalg.norm(pb - pa)) + tol
            cand = [i for i in tree.query_ball_point(mid, rad) if i not in (a, b)]
            tj = False
            for i in cand:
                d = pb - pa
                t = float((P[i] - pa) @ d) / max(float(d @ d), 1e-30)
                if 0 < t < 1 and np.linalg.norm(pa + t * d - P[i]) < 10 * tol:
                    tj = True
                    break
            if tj:
                res["tj"] += 1
                err.append(f"arista {pa.round(4).tolist()} → {pb.round(4).tolist()} en T (vértice a mitad de camino)")
            else:
                res["open"] += 1
                err.append(f"arista abierta {pa.round(4).tolist()} → {pb.round(4).tolist()}")
    vol = 0.0
    c0 = P.mean(axis=0)
    for lp in loops:
        Q = P[lp] - c0
        for i in range(1, len(lp) - 1):
            vol += float(Q[0] @ np.cross(Q[i], Q[i + 1])) / 6.0
    res["vol"] = vol
    if vol <= 1e-12:
        err.append(f"volumen con signo {vol:.4g} ≤ 0 (normales hacia adentro o superficie sin cerrar)")
    if expect_volume is not None and expect_volume > 1e-9 and abs(vol - expect_volume) > vol_rtol * expect_volume + 1e-6:
        err.append(f"volumen de la malla {vol:.4f} ≠ esperado {expect_volume:.4f}")
    res["errors"] = err
    res["ok"] = not err
    return res


# ------------------------------------------------------------------------------------------- sólido: número de arrollamiento
def _tris_of(faces):
    out = []
    for f in faces:
        P = np.asarray(f, float)
        n = len(P)
        if n < 3:
            continue
        if n == 3:
            out.append(P)
            continue
        nv = _poly_area_vec(P)
        ok = True
        for i in range(n):
            if float(np.dot(np.cross(P[(i + 1) % n] - P[i], P[(i + 2) % n] - P[(i + 1) % n]), nv)) < -1e-12:
                ok = False
                break
        if ok:
            for i in range(1, n - 1):
                out.append(np.array([P[0], P[i], P[i + 1]]))
        else:
            from ...scene3d import tri_poly
            for (i, j, k) in tri_poly(P):
                out.append(np.array([P[i], P[j], P[k]]))
    return np.array(out).reshape(-1, 3, 3)


def winding(faces, X, chunk=400):
    """Número de arrollamiento (≈1 dentro, ≈0 fuera) de los puntos X (m,3) respecto de la superficie de `faces`."""
    T = _tris_of(faces)
    X = np.asarray(X, float)
    w = np.zeros(len(X))
    for s in range(0, len(X), chunk):
        x = X[s:s + chunk]
        a = T[None, :, 0, :] - x[:, None, :]
        b = T[None, :, 1, :] - x[:, None, :]
        c = T[None, :, 2, :] - x[:, None, :]
        la, lb, lc = (np.linalg.norm(v, axis=2) for v in (a, b, c))
        num = np.einsum("ijk,ijk->ij", a, np.cross(b, c))
        den = la * lb * lc + np.einsum("ijk,ijk->ij", a, b) * lc + np.einsum("ijk,ijk->ij", a, c) * lb + np.einsum("ijk,ijk->ij", b, c) * la
        w[s:s + chunk] = np.arctan2(num, den).sum(axis=1) * 2.0 / (4 * math.pi)
    return w


def check_prism(pr, n_pts=1500, seed=1, nseg=36, mismatch_max=0.012, faces=None):
    """Malla de un prisma contra el material de `geocheck.prism_mask`: cerrada, orientada y con el mismo sólido."""
    from . import geocheck as GC
    f = faces if faces is not None else pr.faces(nseg)
    res = check_faces(f)
    if not f:
        # sin caras: el material debe ser vacío
        C = pr.corners() if pr.circle is None else np.array([pr.to_global(0, 0, pr.w0), pr.to_global(0, 0, pr.w1)])
        rng = np.random.default_rng(seed)
        X = C.min(axis=0) + rng.random((n_pts, 3)) * (C.max(axis=0) - C.min(axis=0) + 1e-9)
        vac = float(GC.prism_mask(pr, X).mean())
        if vac > 0.01:
            res["errors"].append(f"sin caras pero el {vac:.1%} del volumen es material")
            res["ok"] = False
        return res
    P = np.array([q for fc in f for q in fc], float)
    lo, hi = P.min(axis=0), P.max(axis=0)
    pad = 0.02 * (hi - lo) + 1e-3
    lo, hi = lo - pad, hi + pad
    rng = np.random.default_rng(seed)
    X = lo + rng.random((n_pts, 3)) * (hi - lo)
    w = winding(f, X)
    ins = w > 0.5
    ref = pr
    if pr.circle is not None:                                   # la malla es un poliedro: se compara con el cilindro facetado, no con el círculo ideal
        from .fem.prismmesh import _ring_pts
        ro, ri = pr.circle
        ref = Prism(poly=_ring_pts(ro, nseg), o=pr.o, U=pr.U, V=pr.V, w0=pr.w0, w1=pr.w1, holes=[_ring_pts(ri, nseg)] if ri > 0 else [],
                    cut_planes=list(pr.cut_planes), holes_extra=list(pr.holes_extra))
    mk = GC.prism_mask(ref, X)
    mism = ins != mk
    # los puntos casi sobre la superficie (|w − 0.5| pequeño) no cuentan
    amb = np.abs(w - 0.5) < 0.2
    frac = float((mism & ~amb).sum()) / max(1, int((ins | mk).sum()))
    res["mismatch"] = frac
    if frac > mismatch_max:
        res["errors"].append(f"el sólido de la malla no coincide con el material ({frac:.1%} de los puntos del volumen difieren)")
        res["ok"] = False
    # volumen contra el muestreo del material
    vm = float(mk.mean()) * float(np.prod(hi - lo))
    res["vol_mask"] = vm
    return res
