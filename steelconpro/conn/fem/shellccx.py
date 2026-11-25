# -*- coding: utf-8 -*-
"""Analisis del modelo de placas (cascarones) con CalculiX.

A partir de la malla de placas (`shellmesh.py`, superficie media de cada pieza) y del modelo 3D:

  · cada placa es un conjunto de elementos S3/S4 con su espesor (*SHELL SECTION) y el acero de su pieza
    (elastico, o elasto-plastico perfecto con limite φ·Fy en el paso plastico);
  · placas que se tocan por un borde comparten nodos (union continua: soldadura de penetracion o filete a ambos lados);
    un cordon entre piezas que NO comparten nodos (placa apoyada de plano, boca de pez) se modela atando los nodos de una pieza
    a los de la otra a lo largo del cordon;
  · pernos y anclajes: el borde del agujero de cada placa del paquete es un cuerpo rigido con un nodo de referencia en el eje; entre
    referencias consecutivas hay resortes de cortante y entre la primera y la ultima un resorte axial solo-traccion.  El extremo embebido
    de un anclaje es un punto fijo;
  · contacto solo-compresion entre placas paralelas de un mismo paquete atornillado, y apoyo elastico solo-compresion del concreto bajo
    la placa base (el concreto no se malla);
  · apoyos (nodos del extremo del miembro principal) y cargas del analisis nodal en el extremo libre de cada miembro (cuerpo rigido).

Los resortes unilaterales se resuelven con un conjunto activo: se resuelven problemas lineales actualizando los resortes activos hasta que
el conjunto no cambia; despues, si el acero pasa de φ·Fy en algun punto, un paso elasto-plastico con ese conjunto.
Unidades in, kip, ksi.
"""
from __future__ import annotations
import math
import os
from pathlib import Path

import numpy as np

from .model3d import unit

KC = 5.0e4          # rigidez de contacto por unidad de area (kip/in3)
KSHEAR = 3500.0     # rigidez de cortante del perno = KSHEAR · db² (kip/in)


def _wrap(lst, per=12):
    return "\n".join(", ".join(str(int(x)) for x in lst[i:i + per]) for i in range(0, len(lst), per))


def _in_poly(pt, poly):
    x, y = pt
    ins = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-300) + x0:
            ins = not ins
    return ins


def _seg_dist(X, a, b):
    """Distancia de los puntos X (n, 3) al segmento a-b, y parametro s (0..1) del punto mas cercano."""
    ab = b - a
    L2 = float(ab @ ab)
    s = np.clip(((X - a) @ ab) / L2, 0.0, 1.0) if L2 > 1e-18 else np.zeros(len(X))
    P = a + np.outer(s, ab)
    return np.linalg.norm(X - P, axis=1), s


class ShellCase:
    """Modelo de CalculiX del modelo de placas listo para resolver (ver el docstring del modulo)."""

    def __init__(self, mdl, sm, job: dict, opts: dict | None = None):
        from scipy.spatial import cKDTree
        self.mdl, self.sm, self.opts = mdl, sm, dict(opts or {})
        self.plates = job["plates"]
        self.E = float(self.opts.get("E", 29000.0))
        self.NU = 0.3
        self.phi = float(self.opts.get("phi_y", 0.9))
        self.h = float(job.get("params", {}).get("h_near", 0.8))
        self.notes = []
        # ---- elementos por placa y nodos usados
        self.elems = []                              # (id, nodos, placa)
        eid = 1
        self.plate_elems = []
        n_drop = 0
        amin = 1e-4 * self.h ** 2
        for i in range(len(sm.keys)):
            ids = []
            nrm = unit(self.plates[i]["n"])
            for row in list(sm.tri[i]) + list(sm.quad[i]):
                ns = [int(x) for x in row]
                P = sm.xyz[[sm.index[n] for n in ns]]
                A = np.cross(P[1] - P[0], P[2] - P[0]) + (np.cross(P[2] - P[0], P[3] - P[0]) if len(ns) == 4 else 0.0)
                if float(np.linalg.norm(A)) / 2.0 < amin:                          # astilla de area nula (borde casi tangente): se descarta
                    n_drop += 1
                    continue
                if float(A @ nrm) < 0:                                               # recorrido antihorario respecto de la normal de la placa (CalculiX
                    ns = [ns[0]] + ns[1:][::-1]                                      # expande el cascaron segun esa normal)
                self.elems.append((eid, ns, i))
                ids.append(eid)
                eid += 1
            self.plate_elems.append(ids)
        if n_drop:
            self.notes.append(f"Se omitieron {n_drop} elementos de área nula del modelo de placas.")
        used = sorted({n for _e, ns, _p in self.elems for n in ns})
        self.node_ids = np.array(used, np.int64)
        self.xyz = sm.xyz[[sm.index[n] for n in used]] if used else np.zeros((0, 3))
        self.index = {n: k for k, n in enumerate(used)}
        self.tree = cKDTree(self.xyz) if used else None
        self.next_node = (max(used) if used else 0) + 1
        self.next_elem = eid
        # nodos de cada placa y de cada pieza
        self.plate_nodes = [set() for _ in sm.keys]
        for _e, ns, p in self.elems:
            self.plate_nodes[p].update(ns)
        self.part_nodes = {}
        for p, nodes in enumerate(self.plate_nodes):
            self.part_nodes.setdefault(sm.parts[p], set()).update(nodes)
        self.node_plates = {}
        for p, nodes in enumerate(self.plate_nodes):
            for n in nodes:
                self.node_plates.setdefault(n, []).append(p)
        # area tributaria de cada nodo (para contacto y concreto)
        self.trib = {}
        for _e, ns, _p in self.elems:
            P = self.coords(ns)
            ar = 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
            if len(ns) == 4:
                ar += 0.5 * float(np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[0])))
            for n in ns:
                self.trib[n] = self.trib.get(n, 0.0) + ar / len(ns)
        self.dep = set()            # nodos dependientes de alguna ecuacion
        self.fixed = set()
        self.extra_nodes = []       # (id, x, y, z)
        self.extra_xyz = {}
        self.eqs = []               # lineas *EQUATION
        self.bc = []
        self.cl = []
        self.refs = []              # nodos de referencia (para imprimir sus desplazamientos)
        self.bolt_ax = []           # [(elem, n1, n2, k, bolt index)]: axial solo-traccion
        self.bolt_sh = []           # [(elem, n1, n2, dof, k, bolt index, plano)]
        self.gaps = []              # [(elem, n1, n2, k, kind)]: SPRINGA solo-compresion (n1 -> n2 se acerca = compresion)
        self.ties = 0
        self.meta = {"bolts": [], "welds": [], "loads": [], "supports": [], "grounds": []}
        self.blocks = self._blocks()
        self.grounded = set()       # placas apoyadas en concreto
        self.anchored = set()       # placas con anclajes al concreto
        self._build_bolts()
        self._build_welds()
        self._build_contacts()
        self._build_ground()
        # anclajes de una placa que NO apoya en el concreto (placa separada sobre tuercas de nivelacion): trabajan tambien a compresion,
        # y la placa anclada es el apoyo del miembro principal
        self.bolt_bidir = set()
        for mb in self.meta["bolts"]:
            if mb.get("anchor"):
                pls = [p for p in range(len(self.sm.keys)) if self.sm.parts[p] in mb["parts"][:-1]]
                if not any(p in self.grounded for p in pls):
                    self.bolt_bidir.add(mb["index"])
                self.anchored.update(pls)
        if self.bolt_bidir:
            self.notes.append("Placa separada del concreto: los anclajes trabajan a tracción y a compresión (tuercas de nivelación).")
        self._build_bc_loads()

    # ------------------------------------------------------------------ utilidades
    def coord(self, n):
        if n in self.index:
            return self.xyz[self.index[n]]
        return self.extra_xyz[n]

    def coords(self, ns):
        return self.xyz[[self.index[int(n)] for n in ns]]

    def new_node(self, x):
        n = self.next_node
        self.next_node += 1
        self.extra_nodes.append((n, float(x[0]), float(x[1]), float(x[2])))
        self.extra_xyz[n] = np.array([float(x[0]), float(x[1]), float(x[2])])
        return n

    def new_elem(self):
        e = self.next_elem
        self.next_elem += 1
        return e

    def plate_n(self, p):
        return unit(self.plates[p]["n"])

    def plate_c(self, p):
        return np.mean(np.asarray(self.plates[p]["P"], float), axis=0)

    def plates_of(self, part):
        return [i for i, q in enumerate(self.sm.parts) if q == part]

    def _rigid(self, ids, ref, rot, c):
        """Cuerpo rigido por ecuaciones lineales (giros pequenos): u_i = u_ref + θ × (x_i − c), θ = grados 1..3 del nodo `rot`."""
        ids = [int(n) for n in ids if int(n) not in self.dep and int(n) not in self.fixed]
        X = self.coords(ids) - np.asarray(c, float) if ids else np.zeros((0, 3))
        for n, d in zip(ids, X):
            tm = (((rot, 2, -d[2]), (rot, 3, d[1])), ((rot, 3, -d[0]), (rot, 1, d[2])), ((rot, 1, -d[1]), (rot, 2, d[0])))
            for k in range(3):
                terms = [(n, k + 1, 1.0), (ref, k + 1, -1.0)] + [t for t in tm[k] if abs(t[2]) > 1e-12]
                self.eqs += [str(len(terms)), ", ".join(f"{a}, {b}, {v:.10g}" for a, b, v in terms)]
            self.dep.add(n)
        return ids

    # ------------------------------------------------------------------ bloques de concreto (operacion «Bloque de concreto»)
    def _blocks(self):
        """[(nombre, caras [(centro, normal exterior, poligono)], f'c)] de los bloques de concreto del modelo (no se mallan)."""
        out = []
        for nm, e in (getattr(self.mdl, "elems", {}) or {}).items():
            if not isinstance(e, dict) or e.get("type") != "concreto":
                continue
            quads = [np.asarray(q, float) for q in (e.get("box") or {}).get("quads", [])]
            if len(quads) < 4:
                continue
            cen = np.mean(np.vstack(quads), axis=0)
            faces = []
            for q in quads:
                c = q.mean(axis=0)
                n = unit(np.cross(q[1] - q[0], q[2] - q[0]))
                if float((c - cen) @ n) < 0:
                    n = -n
                faces.append((c, n, q))
            out.append((nm, faces, 4.0))
        return out

    def _in_block(self, x, tol=1e-3):
        for nm, faces, _fc in self.blocks:
            if all(float((x - c) @ n) <= tol for c, n, _q in faces):
                return nm
        return None

    # ------------------------------------------------------------------ pernos y anclajes
    def _build_bolts(self):
        for ib, b in enumerate(self.mdl.bolts):
            ax = unit(b.axis)
            p0 = np.asarray(b.p, float)
            hits = []                                         # (s a lo largo del eje, placa)
            for (pn, s0, s1) in b.grip:
                for p in self.plates_of(pn):
                    nrm = self.plate_n(p)
                    dn = float(ax @ nrm)
                    if abs(dn) < 0.9:
                        continue
                    s = float((self.plate_c(p) - p0) @ nrm) / dn
                    if s < s0 - 0.6 * max(s1 - s0, 0.1) - 0.05 or s > s1 + 0.6 * max(s1 - s0, 0.1) + 0.05:
                        continue
                    x = p0 + s * ax
                    ns = np.array(sorted(self.plate_nodes[p]), np.int64)
                    if not len(ns):
                        continue
                    X = self.coords(ns) - x
                    r = np.linalg.norm(X - np.outer(X @ nrm, nrm), axis=1)
                    off = np.abs(X @ nrm)
                    rim = ns[(np.abs(r - b.dh / 2.0) < max(0.06, 0.15 * b.dh)) & (off < 1e-3)]
                    if len(rim) < 3:
                        rim = ns[(r < 1.2 * b.dh) & (off < 1e-3)]
                    if len(rim) < 3:
                        continue
                    hits.append((s, p, x, rim))
            hits.sort(key=lambda t: t[0])
            refs, planes = [], []
            for (s, p, x, rim) in hits:
                ref, rot = self.new_node(x), self.new_node(x)
                got = self._rigid(rim, ref, rot, x)
                if len(got) < 3:
                    continue
                refs.append(ref)
                planes.append(self.sm.parts[p])
                self.refs += [ref, rot]
            if refs and (getattr(b, "ground", 0) or self._in_block(p0 + ax * b.nut_s, 0.05)):     # anclaje: el extremo embebido es un punto fijo
                g = self.new_node(p0 + ax * b.nut_s)
                self.fixed.add(g)
                self.bc.append(f"{g}, 1, 3")
                refs.append(g)
                planes.append("Concreto")
            if len(refs) < 2:
                self.notes.append(f"Perno {b.tag}: no se encontraron los agujeros en las placas del paquete; se omite del análisis.")
                self.meta["bolts"].append({"tag": b.tag, "skip": True})
                continue
            Ab = math.pi * b.db ** 2 / 4.0
            Lgrip = max(abs(b.nut_s - b.head_s), 0.25) + 0.5 * b.db
            kax = self.E * Ab / Lgrip
            ks = KSHEAR * b.db ** 2
            tr = [i for i in range(3) if abs(ax[i]) < 0.5]
            self.bolt_ax.append((self.new_elem(), refs[0], refs[-1], kax, ib))
            sh = []
            for i in range(len(refs) - 1):
                for dof in tr:
                    e = self.new_elem()
                    self.bolt_sh.append((e, refs[i], refs[i + 1], dof + 1, ks, ib, i))
                    sh.append({"plane": i, "dof": dof + 1})
            self.meta["bolts"].append({"tag": b.tag, "index": ib, "refs": refs, "parts": planes, "kax": kax, "ks": ks, "axis": ax.tolist(),
                                       "p": p0.tolist(), "db": b.db, "dh": b.dh, "grade": b.grade, "planes": len(refs) - 1, "trans": [t + 1 for t in tr],
                                       "anchor": planes[-1] == "Concreto"})

    # ------------------------------------------------------------------ soldaduras
    def _build_welds(self):
        """Cordones: si las dos piezas ya comparten nodos a lo largo del cordon la union es continua; si no, se atan los nodos de A a los de B."""
        from scipy.spatial import cKDTree
        trees = {}

        def part_tree(part):
            if part not in trees:
                ns = np.array(sorted(self.part_nodes.get(part, ())), np.int64)
                trees[part] = (ns, cKDTree(self.coords(ns)) if len(ns) else None)
            return trees[part]

        tmax = {}
        for p in range(len(self.sm.keys)):
            tmax[self.sm.parts[p]] = max(tmax.get(self.sm.parts[p], 0.0), float(self.sm.thick[p]))
        for w in self.mdl.welds:
            a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
            if w.A not in self.part_nodes or w.B not in self.part_nodes:
                continue
            nA, tA = part_tree(w.A)
            nB, tB = part_tree(w.B)
            if tA is None or tB is None:
                continue
            L = float(np.linalg.norm(b - a))
            tol = 0.5 * max(tmax.get(w.A, 0.2), tmax.get(w.B, 0.2)) + w.w + 0.35 * self.h
            mid = 0.5 * (a + b)
            ia = tA.query_ball_point(mid, 0.5 * L + tol)
            ib = tB.query_ball_point(mid, 0.5 * L + tol)
            XA, XB = self.coords(nA[ia]) if ia else np.zeros((0, 3)), self.coords(nB[ib]) if ib else np.zeros((0, 3))
            dA = _seg_dist(XA, a, b)[0] if len(XA) else np.zeros(0)
            dB = _seg_dist(XB, a, b)[0] if len(XB) else np.zeros(0)
            SA = set(int(n) for n in nA[ia][dA < tol]) if len(dA) else set()
            SB = set(int(n) for n in nB[ib][dB < tol]) if len(dB) else set()
            shared = SA & SB
            info = {"name": w.name, "A": w.A, "B": w.B, "p0": a.tolist(), "p1": b.tolist(), "w": w.w, "fexx": w.fexx, "group": w.group, "tied": False}
            if not shared and SA and SB:
                cand = np.array(sorted(SB - self.dep), np.int64)
                if len(cand):
                    tb = cKDTree(self.coords(cand))
                    lim = 0.5 * (tmax.get(w.A, 0.2) + tmax.get(w.B, 0.2)) + w.w + 0.6 * self.h
                    kq = min(3, len(cand))
                    for n in sorted(SA - self.dep - self.fixed):
                        d, j = tb.query(self.coord(n), k=kq)
                        d, j = np.atleast_1d(d), np.atleast_1d(j)
                        if d[0] > lim:
                            continue
                        # el nodo de A sigue al promedio (inverso de la distancia) de los nodos de B mas cercanos: si varios nodos de A se ataran
                        # al mismo nodo de B, el elemento entre ellos quedaria aplastado (picos de esfuerzo falsos)
                        sel = [(float(dd), int(cand[jj])) for dd, jj in zip(d, j) if dd <= lim]
                        if sel[0][0] < 1e-6:
                            sel = sel[:1]
                        wts = np.array([1.0 / max(dd, 1e-6) for dd, _m in sel])
                        wts = wts / wts.sum()
                        for k in (1, 2, 3):
                            terms = [f"{n}, {k}, 1.0"] + [f"{m}, {k}, {-w_:.8f}" for (_dd, m), w_ in zip(sel, wts)]
                            self.eqs += [str(len(terms)), ", ".join(terms)]
                        self.dep.add(n)
                        self.ties += 1
                    info["tied"] = True
            self.meta["welds"].append(info)

    # ------------------------------------------------------------------ contacto entre placas atornilladas y concreto
    def _build_contacts(self):
        from scipy.spatial import cKDTree
        pairs = set()
        for mb in self.meta["bolts"]:
            if mb.get("skip"):
                continue
            ps = [p for p in mb["parts"] if p != "Concreto"]
            for i in range(len(ps) - 1):
                if ps[i] != ps[i + 1]:
                    pairs.add(tuple(sorted((ps[i], ps[i + 1]))))
        n_sp = 0
        for (A, B) in sorted(pairs):
            for pa in self.plates_of(A):
                na = self.plate_n(pa)
                for pb in self.plates_of(B):
                    nb = self.plate_n(pb)
                    if abs(float(na @ nb)) < 0.98:
                        continue
                    gap = abs(float((self.plate_c(pa) - self.plate_c(pb)) @ nb))
                    tsum = 0.5 * (float(self.sm.thick[pa]) + float(self.sm.thick[pb]))
                    if abs(gap - tsum) > 0.1 + 0.25 * tsum:
                        continue
                    # placa B en su plano: contorno y agujeros
                    cb = self.plate_c(pb)
                    e1 = unit(np.asarray(self.plates[pb]["P"][1], float) - np.asarray(self.plates[pb]["P"][0], float))
                    e1 = unit(e1 - nb * float(e1 @ nb))
                    e2 = np.cross(nb, e1)
                    polyB = [((np.asarray(q, float) - cb) @ e1, (np.asarray(q, float) - cb) @ e2) for q in self.plates[pb]["P"]]
                    holesB = [np.asarray(h, float) for h in self.plates[pb]["holes"]]
                    nsB = np.array(sorted(self.plate_nodes[pb] - self.dep), np.int64)
                    if not len(nsB):
                        continue
                    tb = cKDTree(self.coords(nsB))
                    for n in sorted(self.plate_nodes[pa] - self.dep - self.fixed):
                        x = self.coord(n)
                        d = float((x - cb) @ nb)
                        xp = x - d * nb
                        uv = ((xp - cb) @ e1, (xp - cb) @ e2)
                        if not _in_poly(uv, polyB):
                            continue
                        if any(float(np.linalg.norm(xp - h.mean(axis=0))) < 0.5 * float(np.max(np.linalg.norm(h - h.mean(axis=0), axis=1))) + 0.05 for h in holesB):
                            continue
                        dd, j = tb.query(xp, k=min(3, len(nsB)))
                        dd, j = np.atleast_1d(dd), np.atleast_1d(j)
                        if dd[0] > 0.75 * self.h + 0.05 or abs(d) < 1e-4:
                            continue
                        k = KC * self.trib.get(n, 0.0)
                        if k <= 0:
                            continue
                        # el resorte va del nodo de A a su proyección sobre B (nodo auxiliar que sigue al promedio de los nodos de B más cercanos):
                        # así actúa solo en la dirección normal; si uniera dos nodos desalineados quedaría inclinado y tomaría cortante
                        aux = self.new_node(xp)
                        sel = [(float(a_), int(nsB[b_])) for a_, b_ in zip(dd, j) if a_ <= 0.75 * self.h + 0.05]
                        wts = np.array([1.0 / max(a_, 1e-6) for a_, _m in sel])
                        if sel[0][0] < 1e-6:
                            sel, wts = sel[:1], np.array([1.0])
                        wts = wts / wts.sum()
                        for kk in (1, 2, 3):
                            terms = [f"{aux}, {kk}, 1.0"] + [f"{m_}, {kk}, {-w_:.8f}" for (_a, m_), w_ in zip(sel, wts)]
                            self.eqs += [str(len(terms)), ", ".join(terms)]
                        self.dep.add(aux)
                        self.gaps.append((self.new_elem(), n, aux, k, "contacto"))
                        n_sp += 1
        self.meta["contacts"] = n_sp

    def _build_ground(self):
        self._block_ground()
        for g in getattr(self.mdl, "grounds", []):
            nrm = unit(g["normal"])
            x0, x1, y0, y1, z0, z1 = g["box"]
            n_sp = 0
            for p in self.plates_of(g["part"]):
                if abs(float(self.plate_n(p) @ nrm)) < 0.95:
                    continue
                t = float(self.sm.thick[p])
                for n in sorted(self.plate_nodes[p] - self.dep - self.fixed):
                    x = self.coord(n)
                    if not (x0 - 0.05 <= x[0] <= x1 + 0.05 and y0 - 0.05 <= x[1] <= y1 + 0.05):
                        continue
                    k = float(g["kv"]) * self.trib.get(n, 0.0)
                    if k <= 0:
                        continue
                    gn = self.new_node(x + nrm * max(0.5 * t, 0.25))
                    self.fixed.add(gn)
                    self.bc.append(f"{gn}, 1, 3")
                    self.gaps.append((self.new_elem(), n, gn, k, "concreto"))
                    n_sp += 1
                self.grounded.add(p)
            self.meta["grounds"].append({"name": g["name"], "n_springs": n_sp, "kv": float(g["kv"])})

    def _block_ground(self):
        """Placas apoyadas de plano sobre una cara de un bloque de concreto: resortes solo-compresion (modulo de balasto Ec / ancho de la placa)."""
        for nm, faces, fc in self.blocks:
            Ec = 57.0 * math.sqrt(fc * 1000.0)
            for (c, n, q) in faces:
                e1 = unit(q[1] - q[0])
                e1 = unit(e1 - n * float(e1 @ n))
                e2 = np.cross(n, e1)
                poly = [((x - c) @ e1, (x - c) @ e2) for x in q]
                for p in range(len(self.sm.keys)):
                    if p in self.grounded or abs(float(self.plate_n(p) @ n)) < 0.98:
                        continue
                    t = float(self.sm.thick[p])
                    d = float((self.plate_c(p) - c) @ n)
                    if abs(d - 0.5 * t) > 0.1 + 0.25 * t:
                        continue
                    P = np.asarray(self.plates[p]["P"], float)
                    ext = [float(np.ptp(P @ e1)), float(np.ptp(P @ e2))]
                    kv = Ec / max(min(ext), 6.0)
                    holes = [np.asarray(h, float) for h in self.plates[p]["holes"]]
                    n_sp = 0
                    for node in sorted(self.plate_nodes[p] - self.dep - self.fixed):
                        x = self.coord(node)
                        xp = x - float((x - c) @ n) * n
                        if not _in_poly(((xp - c) @ e1, (xp - c) @ e2), poly):
                            continue
                        if any(float(np.linalg.norm(x - h.mean(axis=0))) < float(np.max(np.linalg.norm(h - h.mean(axis=0), axis=1))) + 0.02 for h in holes):
                            continue
                        k = kv * self.trib.get(node, 0.0)
                        if k <= 0:
                            continue
                        gn = self.new_node(x - n * max(0.5 * t, 0.25))
                        self.fixed.add(gn)
                        self.bc.append(f"{gn}, 1, 3")
                        self.gaps.append((self.new_elem(), node, gn, k, "concreto"))
                        n_sp += 1
                    if n_sp:
                        self.grounded.add(p)
                        self.meta["grounds"].append({"name": f"Concreto «{nm}» bajo «{self.sm.parts[p]}»", "n_springs": n_sp, "kv": kv})

    # ------------------------------------------------------------------ apoyos y cargas
    def _end_nodes(self, sels, normal):
        """Nodos de las piezas de `sels` dentro de sus cajas y en el extremo (el mas alejado segun la normal)."""
        out = []
        for sl in sels:
            x0, x1, y0, y1, z0, z1 = sl.box
            ns = np.array(sorted(self.part_nodes.get(sl.part, ())), np.int64)
            if not len(ns):
                continue
            X = self.coords(ns)
            m = (X[:, 0] >= x0 - 1e-3) & (X[:, 0] <= x1 + 1e-3) & (X[:, 1] >= y0 - 1e-3) & (X[:, 1] <= y1 + 1e-3) & (X[:, 2] >= z0 - 1e-3) & (X[:, 2] <= z1 + 1e-3)
            ns, X = ns[m], X[m]
            if not len(ns):
                continue
            nrm = unit(sl.normal if sl.normal is not None else normal)
            s = X @ nrm
            out += [int(n) for n in ns[s >= s.max() - 0.05]]
        return out

    def _build_bc_loads(self):
        sup_pl = self.grounded | self.anchored
        gparts = {self.sm.parts[p] for p in sup_pl}
        gnodes = set().union(*[self.plate_nodes[p] for p in sup_pl]) if sup_pl else set()
        for i, s in enumerate(self.mdl.supports):
            linked = bool(gnodes & self.part_nodes.get(s.sel.part, set())) or any({w.A, w.B} & gparts and s.sel.part in (w.A, w.B) for w in self.mdl.welds)
            if gparts and linked:                                      # el principal llega a una placa apoyada en el concreto: el apoyo es el concreto
                self.notes.append(f"«{s.sel.part}» se apoya en el concreto a través de {', '.join(sorted(gparts))}: no se empotra su extremo.")
                continue
            ns = [n for n in self._end_nodes([s.sel], s.sel.normal) if n not in self.dep]
            if not ns:
                self.notes.append(f"Apoyo «{s.name}»: no se encontraron nodos en el extremo del miembro.")
                continue
            self.fixed.update(ns)
            self.bc += [f"{n}, {min(s.dofs)}, {max(s.dofs)}" for n in ns]
            self.meta["supports"].append({"name": s.name, "nodes": ns})
        for i, ld in enumerate(self.mdl.loads):
            sels = ld.sel if isinstance(ld.sel, (list, tuple)) else [ld.sel]
            ns = [n for n in self._end_nodes(sels, sels[0].normal) if n not in self.dep and n not in self.fixed]
            if len(ns) < 3:
                self.notes.append(f"Carga «{ld.name}»: no se encontraron nodos en el extremo del miembro; no se aplica.")
                continue
            c = np.asarray(ld.ref, float)
            ref, rot = self.new_node(c), self.new_node(c)
            self._rigid(ns, ref, rot, c)
            self.refs += [ref, rot]
            for d in range(3):
                if abs(ld.F[d]) > 0:
                    self.cl.append((ref, d + 1, float(ld.F[d])))
                if abs(ld.M[d]) > 0:
                    self.cl.append((rot, d + 1, float(ld.M[d])))
            for d in ld.fix_ref:
                self.bc.append(f"{ref}, {d}, {d}")
            for d in ld.fix_rot:
                self.bc.append(f"{rot}, {d}, {d}")
            self.meta["loads"].append({"name": ld.name, "ref": ref, "rot": rot, "nodes": ns, "F": list(ld.F), "M": list(ld.M)})
        self.fref = max([abs(v) for _n, _d, v in self.cl] + [1.0])

    # ------------------------------------------------------------------ escritura
    def write(self, path, gap_on=None, bolt_on=None, plastic=False):
        sm, mdl = self.sm, self.mdl
        parts = {p.name: p for p in mdl.parts}
        L = ["** SteelConPro - analisis del modelo de placas", f"** {mdl.name}", "*NODE"]
        for n, (x, y, z) in zip(self.node_ids, self.xyz):
            L.append(f"{int(n)}, {x:.6f}, {y:.6f}, {z:.6f}")
        for (n, x, y, z) in self.extra_nodes:
            L.append(f"{n}, {x:.6f}, {y:.6f}, {z:.6f}")
        for p in range(len(sm.keys)):
            tri = [(e, ns) for e, ns, q in self.elems if q == p and len(ns) == 3]
            quad = [(e, ns) for e, ns, q in self.elems if q == p and len(ns) == 4]
            if tri:
                L.append(f"*ELEMENT, TYPE=S3, ELSET=P{p}")
                L += [f"{e}, " + ", ".join(map(str, ns)) for e, ns in tri]
            if quad:
                L.append(f"*ELEMENT, TYPE=S4, ELSET=P{p}")
                L += [f"{e}, " + ", ".join(map(str, ns)) for e, ns in quad]
        L.append("*NORMAL")                                                          # normal de cada placa en sus nodos: en las uniones de placas que no son
        for e, ns, p in self.elems:                                                  # coplanares CalculiX no promedia normales (evita jacobianos negativos)
            nx, ny, nz = unit(self.plates[p]["n"])
            L += [f"{e}, {n}, {nx:.7f}, {ny:.7f}, {nz:.7f}" for n in ns]
        L.append("*ELSET, ELSET=ESH")
        L += [f"P{p}" for p in range(len(sm.keys)) if self.plate_elems[p]]
        mats = {}
        for p in range(len(sm.keys)):
            if not self.plate_elems[p]:
                continue
            pt = parts.get(sm.parts[p])
            fy = float(pt.Fy) if pt is not None and pt.Fy else 50.0
            key = round(fy, 3)
            if key not in mats:
                mats[key] = f"A{len(mats)}"
                L += [f"*MATERIAL, NAME={mats[key]}", "*ELASTIC", f"{self.E:.1f}, {self.NU:.3f}"]
                if plastic:
                    fyd = self.phi * fy
                    L += ["*PLASTIC", f"{fyd:.4f}, 0.0", f"{fyd * 1.0005:.4f}, 0.25"]
            L += [f"*SHELL SECTION, ELSET=P{p}, MATERIAL={mats[key]}", f"{float(sm.thick[p]):.5f}"]
        if self.refs:
            L += ["*NSET, NSET=NREF", _wrap(sorted(set(self.refs)))]
        if self.eqs:
            L += ["*EQUATION"] + self.eqs
        # los resortes inactivos (perno comprimido, contacto separado) conservan una rigidez residual minima: sin ella una pieza unida por
        # una sola fila de pernos queda como mecanismo y el paso no lineal diverge
        for (e, n1, n2, k, ib) in self.bolt_ax:
            kk = k if (bolt_on is None or ib in bolt_on) else k * 1e-3
            L += [f"*ELEMENT, TYPE=SPRINGA, ELSET=BA{e}", f"{e}, {n1}, {n2}", f"*SPRING, ELSET=BA{e}", f"{kk:.6f}"]
        by = {}
        for (e, n1, n2, dof, k, _ib, _pl) in self.bolt_sh:
            by.setdefault((dof, round(k, 3)), []).append((e, n1, n2))
        for (dof, k), lst in by.items():
            nm = f"BS{dof}_{int(k * 10)}"
            L.append(f"*ELEMENT, TYPE=SPRING2, ELSET={nm}")
            L += [f"{e}, {a}, {b}" for e, a, b in lst]
            L += [f"*SPRING, ELSET={nm}", f"{dof}, {dof}", f"{k:.6f}"]
        byk = {}
        for i, (e, n1, n2, k, _kind) in enumerate(self.gaps):
            kk = k if (gap_on is None or i in gap_on) else k * 1e-4
            byk.setdefault(int(round(math.log(max(kk, 1e-12)) / math.log(1.15))), []).append((e, n1, n2, kk))
        for ci, lst in sorted(byk.items()):
            nm = f"GAP{ci + 400}"
            kk = sum(x[3] for x in lst) / len(lst)
            L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET={nm}")
            L += [f"{e}, {a}, {b}" for e, a, b, _k in lst]
            L += [f"*SPRING, ELSET={nm}", f"{kk:.6f}"]
        if self.bc:
            L += ["*BOUNDARY"] + self.bc
        L += ["*STEP, INC=120", "*STATIC", "0.1, 1.0, 1e-5, 0.25" if plastic else "1.0, 1.0", "*CLOAD"]
        L += [f"{n}, {d}, {v:.6f}" for n, d, v in self.cl]
        L += ["*NODE FILE, OUTPUT=2D", "U", "*EL PRINT, ELSET=ESH, FREQUENCY=10000", "S" + (", PEEQ" if plastic else "")]
        if self.refs:
            L += ["*NODE PRINT, NSET=NREF, FREQUENCY=10000", "U"]
        L += ["*END STEP"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
        return path


# ================================================================================================== lectura de resultados
def read_dat(path):
    """(esfuerzos {elem: (n_ip, 6)}, peeq {elem: max}, desplazamientos de las referencias {nodo: (3,)}) del ultimo incremento del .dat."""
    S, PE, U = {}, {}, {}
    mode = None
    cur_S, cur_PE, cur_U = {}, {}, {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            s = ln.strip()
            if not s:
                continue
            low = s.lower()
            if low.startswith("stresses"):
                mode = "S"
                cur_S = {}
                S = cur_S
                continue
            if low.startswith("equivalent plastic strain"):
                mode = "PE"
                cur_PE = {}
                PE = cur_PE
                continue
            if low.startswith("displacements"):
                mode = "U"
                cur_U = {}
                U = cur_U
                continue
            if low[0].isalpha():
                mode = None
                continue
            t = s.split()
            try:
                if mode == "S" and len(t) >= 8:
                    S.setdefault(int(t[0]), []).append([float(x) for x in t[2:8]])
                elif mode == "PE" and len(t) >= 3:
                    e = int(t[0])
                    PE[e] = max(PE.get(e, 0.0), float(t[2]))
                elif mode == "U" and len(t) >= 4:
                    U[int(t[0])] = np.array([float(x) for x in t[1:4]])
            except ValueError:
                continue
    return {e: np.asarray(v, float) for e, v in S.items()}, PE, U


def read_frd_u(path):
    from ...view3d import read_frd
    disp, _s, _f = read_frd(path)
    return {int(k): np.asarray(v, float) for k, v in disp.items()}


def _vm(s):
    sx, sy, sz, sxy, sxz, syz = s[..., 0], s[..., 1], s[..., 2], s[..., 3], s[..., 4], s[..., 5]
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (sxy ** 2 + sxz ** 2 + syz ** 2))


def surface_stresses(S):
    """De los esfuerzos en los puntos de integracion de un elemento de cascaron expandido (dos capas de puntos a ±t/(2·√3)) obtiene el
    tensor en la cara superior, la inferior y la superficie media (extrapolacion lineal en el espesor).  -> (sup, inf, medio) (6,)"""
    n = len(S)
    if n >= 2 and n % 2 == 0:
        h = n // 2
        a, b = S[:h].mean(axis=0), S[h:].mean(axis=0)
    else:
        a = b = S.mean(axis=0)
    m = 0.5 * (a + b)
    k = math.sqrt(3.0)
    return m + (a - m) * k, m + (b - m) * k, m


# ================================================================================================== resolucion
def _run(inp, ccx_path, cancel, timeout=3600):
    from ... import mesh3d
    return mesh3d.run_ccx(inp, ccx_path, timeout=timeout, cancel=cancel)


def solve(case: ShellCase, folder, stem="placas", ccx_path="", cancel=None, progress=None, max_it=12, plastic=True):
    """Conjunto activo (lineal) y, si algo pasa de φ·Fy, paso elasto-plastico.  -> (ok, mensaje, info)."""
    from ... import mesh3d
    say = progress or (lambda m: None)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    gap_on = set(range(len(case.gaps)))
    bolt_on = {ib for (_e, _a, _b, _k, ib) in case.bolt_ax}
    info = {"iters": 0, "plastic": False}
    seen = []
    tol_f = 2e-4 * case.fref

    def one(tag, plastic_):
        inp = folder / f"{stem}_{tag}.inp"
        case.write(str(inp), gap_on, bolt_on, plastic=plastic_)
        ok, out, frd = _run(str(inp), ccx_path, cancel, int(case.opts.get("plastic_timeout", 480)) if plastic_ else 3600)
        return ok, out, frd, str(inp.with_suffix(".dat"))

    res = None
    for it in range(max_it):
        if cancel is not None and cancel.cancelled:
            return False, mesh3d.CANCELADO, info
        say(f"CalculiX: análisis elástico, iteración {it + 1} (contactos y pernos activos)")
        ok, out, frd, dat = one(f"e{it % 2}", False)
        if not ok or "*ERROR" in out:
            return False, "CalculiX no pudo resolver el modelo de placas.\n\n" + out[-2500:], info
        U = read_frd_u(frd)
        _S, _P, UR = read_dat(dat)
        U.update(UR)
        res = (frd, dat, U)
        info["iters"] = it + 1
        new_gap = set()
        for i, (_e, n1, n2, k, _kind) in enumerate(case.gaps):
            d = unit(case.coord(n2) - case.coord(n1))
            sep = float((U.get(n2, np.zeros(3)) - U.get(n1, np.zeros(3))) @ d)        # > 0: se separan
            if i in gap_on:
                if -k * sep >= -tol_f:                                                  # sigue en compresion
                    new_gap.add(i)
            elif sep < -1e-5:
                new_gap.add(i)
        new_bolt = set()
        for (_e, n1, n2, _k, ib) in case.bolt_ax:
            ax = unit(case.mdl.bolts[ib].axis)
            el = float((U.get(n2, np.zeros(3)) - U.get(n1, np.zeros(3))) @ (ax if float((case.coord(n2) - case.coord(n1)) @ ax) >= 0 else -ax))
            if ib in case.bolt_bidir or ((el >= -1e-9) if ib in bolt_on else (el > 1e-9)):
                new_bolt.add(ib)
        key = (frozenset(new_gap), frozenset(new_bolt))
        info.setdefault("history", []).append((len(gap_on), len(new_gap ^ gap_on), len(bolt_on), len(new_bolt ^ bolt_on)))
        nchg = len(new_gap ^ gap_on)
        if new_bolt == bolt_on and nchg <= max(2, int(0.003 * max(len(gap_on), 1))):
            break
        h = info["history"]
        if len(h) >= 2 and new_bolt == bolt_on and h[-2][3] == 0 and nchg <= 0.04 * max(len(gap_on), 1) and h[-2][1] <= 0.04 * max(h[-2][0], 1):
            break                                    # el conjunto ya casi no cambia (unos pocos resortes de contacto de borde oscilan): se acepta
        if key in seen:
            gap_on, bolt_on = new_gap & gap_on, new_bolt & bolt_on
            continue
        seen.append(key)
        gap_on, bolt_on = new_gap, new_bolt
    info.update(gap_on=gap_on, bolt_on=bolt_on, frd=res[0], dat=res[1], converged=info["iters"] < max_it)
    if not plastic:
        return True, "", info
    S, _P, _U = read_dat(res[1])
    fy = _fy_by_elem(case)
    vm = {e: float(max(_vm(a), _vm(b))) for e, (a, b, _m) in ((e, surface_stresses(s)) for e, s in S.items())}
    avg = averaged_vm(case, vm)
    info["vm_ratio_elastic"] = max((vm[e] / (case.phi * fy.get(e, 50.0)) for e in vm), default=0.0)
    worst = max((avg[e] / (case.phi * fy.get(e, 50.0)) for e in avg), default=0.0)
    info["vm_ratio_avg"] = worst
    if worst <= 1.0:                        # solo picos puntuales (aristas vivas, anillos rigidos de los agujeros): el elastico es la solucion
        return True, "", info
    if cancel is not None and cancel.cancelled:
        return False, mesh3d.CANCELADO, info
    say("CalculiX: análisis elasto-plástico (límite φ·Fy)")
    ok, out, frd, dat = one("p", True)
    if not ok or "*ERROR" in out or not ("Job finished" in out or "CalculiX Time" in out):
        info["plastic_failed"] = True
        if "tiempo" in out:
            return True, "El análisis elasto-plástico excedió el tiempo límite; se muestran los resultados elásticos.", info
        return True, "El análisis elasto-plástico no convergió (la conexión no alcanza la carga de diseño); se muestran los resultados elásticos.", info
    info.update(frd=frd, dat=dat, plastic=True)
    return True, "", info


def elem_quality(P):
    """Calidad de un triangulo o cuadrilatero: 4·√3·area / Σ lado² (1 = equilatero; ~0 = astilla)."""
    n = len(P)
    ar = 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
    if n == 4:
        ar = 0.5 * ar + 0.25 * float(np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[0])))     # mitad del cuadrilatero ~ un triangulo
    L2 = sum(float(np.sum((P[(i + 1) % n] - P[i]) ** 2)) for i in range(n)) * (3.0 / n)
    return 4.0 * math.sqrt(3.0) * ar / max(L2, 1e-18)


QMIN = 0.05             # elementos peores que esto (astillas de la malla) no se usan para evaluar esfuerzos


def averaged_vm(case, vm, rmin=0.5):
    """von Mises de cada elemento promediado (por area) con los elementos de su misma pieza a menos de r = max(espesor, 0.5 in) de su centro:
    quita los picos puntuales que dependen de la malla (aristas vivas, anillos rigidos de pernos) sin ocultar una zona que de verdad fluye."""
    from scipy.spatial import cKDTree
    cen, area, part, ids, tt, good = [], [], [], [], [], []
    for e, ns, p in case.elems:
        if e not in vm:
            continue
        P = case.coords(ns)
        ar = 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
        if len(ns) == 4:
            ar += 0.5 * float(np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[0])))
        cen.append(P.mean(axis=0)); area.append(ar); part.append(case.sm.parts[p]); ids.append(e); tt.append(float(case.sm.thick[p]))
        good.append(elem_quality(P) >= QMIN)
    out = {}
    if not ids:
        return out
    cen, area, tt, good = np.array(cen), np.array(area), np.array(tt), np.array(good, bool)
    v = np.array([vm[e] for e in ids])
    part = np.array(part)
    for nm in set(part.tolist()):
        k = np.nonzero(part == nm)[0]
        kg = k[good[k]]                                                   # solo elementos de buena calidad
        if not len(kg):
            for i in k:
                out[ids[i]] = 0.0
            continue
        tr = cKDTree(cen[kg])
        r = max(float(np.median(tt[k])), rmin)
        vmax = float(v[kg].max())
        for i in k:
            if good[i] and v[i] <= 0.5 * vmax:                            # solo vale la pena promediar donde el esfuerzo es alto
                out[ids[i]] = float(v[i])
                continue
            nb = kg[tr.query_ball_point(cen[i], r)]
            if not len(nb):
                nb = kg[[tr.query(cen[i])[1]]]
            out[ids[i]] = float((v[nb] * area[nb]).sum() / max(area[nb].sum(), 1e-12))
    return out


def _fy_by_elem(case):
    parts = {p.name: p for p in case.mdl.parts}
    out = {}
    for e, _ns, p in case.elems:
        pt = parts.get(case.sm.parts[p])
        out[e] = float(pt.Fy) if pt is not None and pt.Fy else 50.0
    return out
