# -*- coding: utf-8 -*-
"""Arma el .inp de CalculiX a partir de la malla (mesher.py) y el modelo 3D:

  · piezas de acero elastico o elasto-plastico perfecto (limite φ·Fy), tetraedros C3D10;
  · pernos: el borde de cada agujero (y la corona de cabeza y de tuerca) es un cuerpo rigido unido a los de las otras piezas del paquete por
    resortes: uno axial solo-traccion y dos de cortante;  la fuerza del perno se lee de los desplazamientos de los nodos de referencia;
  · cordones de filete: prismas triangulares unidos (*TIE) a las dos piezas; el esfuerzo en su garganta da la fuerza del cordon;
  · contactos entre piezas (*CONTACT PAIR, penalizacion lineal), apoyos empotrados y cargas sobre caras rigidizadas.
"""
from __future__ import annotations
import json
import math

import numpy as np

from .model3d import unit, weld_prism

FACES = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]                  # S1..S4 de CalculiX (indices 0-based de los 4 vertices)
EDGE_MID = {(0, 1): 4, (1, 2): 5, (0, 2): 6, (0, 3): 7, (1, 3): 8, (2, 3): 9}


def _mid(a, b):
    return EDGE_MID[(min(a, b), max(a, b))]


class Mesh:
    """Malla del modelo: nodos y tetraedros por pieza, con las caras de la piel de cada pieza."""

    def __init__(self, npz_path):
        Z = np.load(npz_path, allow_pickle=False)
        self.names = json.loads(str(Z["names"]))
        ids, xyz = Z["node_id"], Z["xyz"]
        self.E = {k: Z["e_" + k] for k in self.names}
        used = np.unique(np.concatenate([e.ravel() for e in self.E.values() if len(e)]))
        pos = np.searchsorted(ids, used)
        self.node_ids = used
        self.xyz = xyz[pos]
        self.index = {int(n): i for i, n in enumerate(used)}
        self.eid0 = int(used.max()) + 1000                       # los elementos se numeran aparte de los nodos
        # numeracion global de elementos
        self.eid = {}
        n = 1
        for k in self.names:
            m = len(self.E[k])
            self.eid[k] = np.arange(n, n + m)
            n += m
        self.n_elem = n - 1
        self._skin = {}

    def coord(self, nid):
        return self.xyz[self.index[int(nid)]]

    def coords(self, nids):
        return self.xyz[np.fromiter((self.index[int(n)] for n in nids), int, len(nids))]

    def part_nodes(self, key):
        return np.unique(self.E[key].ravel())

    def skin(self, key):
        """Caras de la piel de una pieza: (elem global, cara 1-4, nodos de la cara [6], centroide, normal exterior)."""
        if key in self._skin:
            return self._skin[key]
        E = self.E[key]
        m = len(E)
        N = int(self.node_ids.max()) + 1
        keys, own, fid = [], [], []
        for fi, (a, b, c) in enumerate(FACES):
            tri = np.sort(E[:, [a, b, c]], axis=1).astype(np.int64)
            keys.append(tri[:, 0] * N * N + tri[:, 1] * N + tri[:, 2])
            own.append(np.arange(m))
            fid.append(np.full(m, fi))
        keys, own, fid = np.concatenate(keys), np.concatenate(own), np.concatenate(fid)
        _u, inv, cnt = np.unique(keys, return_inverse=True, return_counts=True)
        sel = cnt[inv] == 1
        own, fid = own[sel], fid[sel]
        out = []
        P = self.coords(E.ravel()).reshape(m, 10, 3)
        for e, f in zip(own, fid):
            a, b, c = FACES[f]
            d = ({0, 1, 2, 3} - {a, b, c}).pop()
            pa, pb, pc = P[e, a], P[e, b], P[e, c]
            n = np.cross(pb - pa, pc - pa)
            ln = np.linalg.norm(n)
            if ln < 1e-14:
                continue
            n = n / ln
            cen = (pa + pb + pc) / 3.0
            if np.dot(cen - P[e, d], n) < 0:
                n = -n
            nodes = [E[e, a], E[e, b], E[e, c], E[e, _mid(a, b)], E[e, _mid(b, c)], E[e, _mid(c, a)]]
            out.append((int(self.eid[key][e]), int(f) + 1, nodes, cen, n))
        self._skin[key] = out
        return out

    def select(self, key, box, normal=None, pt=None, ptol=0.02, cos_tol=0.9):
        """Caras de la piel de `key` con el centroide dentro de la caja, normal exterior ~ `normal` y (opcional) sobre el plano por `pt`."""
        x0, x1, y0, y1, z0, z1 = box
        nrm = unit(normal) if normal is not None else None
        res = []
        for (e, f, nodes, cen, n) in self.skin(key):
            if not (x0 <= cen[0] <= x1 and y0 <= cen[1] <= y1 and z0 <= cen[2] <= z1):
                continue
            if nrm is not None:
                if np.dot(n, nrm) < cos_tol:
                    continue
                if pt is not None and abs(np.dot(cen - np.asarray(pt, float), nrm)) > ptol:
                    continue
            res.append((e, f, nodes))
        return res

    # ------------------------------------------------------------------ separacion de nodos entre piezas que solo se apoyan
    def split(self, bonded):
        """La malla del mallador comparte nodos en las caras que se tocan.  Aqui cada pieza recibe sus propios nodos salvo donde las piezas
        estan unidas (`bonded`: pares de nombres, p. ej. cordon-pieza) y devuelve los pares de nodos gemelos por pareja de piezas:
        {(A, B): [(nodo de A, nodo de B)]}, donde actua el contacto."""
        keys = [k for k in self.names if len(self.E[k])]
        parts_of = {}
        for k in keys:
            for n in np.unique(self.E[k]):
                parts_of.setdefault(int(n), []).append(k)
        bset = {frozenset(b) for b in bonded}
        next_id = int(self.node_ids.max()) + 1
        remap = {k: {} for k in keys}
        pairs = {}
        new_nodes = []
        for n, S in parts_of.items():
            if len(S) < 2:
                continue
            comps = []
            for k in S:
                hit = [c for c in comps if any(frozenset((k, q)) in bset for q in c)]
                merged = [k]
                for c in hit:
                    merged += c
                    comps.remove(c)
                comps.append(merged)
            if len(comps) == 1:
                continue
            ids = [n]
            for c in comps[1:]:
                nid = next_id
                next_id += 1
                new_nodes.append((nid, n))
                ids.append(nid)
                for k in c:
                    remap[k][n] = nid
            for i in range(len(comps)):
                for j in range(i + 1, len(comps)):
                    for a in comps[i]:
                        for b in comps[j]:
                            pairs.setdefault(tuple(sorted((a, b))), set()).add((ids[i], ids[j]) if a < b else (ids[j], ids[i]))
        if new_nodes:
            old = np.array([o for _n, o in new_nodes])
            self.xyz = np.vstack([self.xyz, self.coords(old)])
            self.node_ids = np.concatenate([self.node_ids, np.array([n for n, _o in new_nodes])])
            self.index = {int(n): i for i, n in enumerate(self.node_ids)}
        for k in keys:
            if remap[k]:
                E = self.E[k]
                for o, nn in remap[k].items():
                    E[E == o] = nn
        self._skin = {}
        self.pairs = {k: sorted(v) for k, v in pairs.items()}
        return self.pairs

    def gap_springs(self, minw=1e-6):
        """Resortes de contacto (compresion) entre nodos gemelos: [(nodo1, nodo2, dof, area tributaria)].  El orden de los nodos hace que
        el desplazamiento relativo positivo sea la separacion."""
        out = {}
        for (A, B), prs in self.pairs.items():
            if A.startswith("W:") or B.startswith("W:"):
                pass
            mapAB = {}
            for a, b in prs:
                mapAB[a] = b
            # los ids pueden haberse guardado en el orden (A, B) alfabetico: se separa cada lado por la pieza que lo contiene
            nodesA = set(int(n) for n in np.unique(self.E[A]))
            nodesB = set(int(n) for n in np.unique(self.E[B]))
            ab = {}
            for a, b in prs:
                if a in nodesA and b in nodesB:
                    ab[a] = b
                elif b in nodesA and a in nodesB:
                    ab[b] = a
            if not ab:
                continue
            w, nsum = {}, np.zeros(3)
            for (e, f, nodes, cen, n) in self.skin(A):
                if all(int(q) in ab for q in nodes[:3]):
                    pa, pb, pc = (self.coord(q) for q in nodes[:3])
                    ar = 0.5 * np.linalg.norm(np.cross(pb - pa, pc - pa))
                    nsum += n * ar
                    for q in nodes[:3]:
                        w[int(q)] = w.get(int(q), 0.0) + ar / 12.0
                    for q in nodes[3:]:
                        w[int(q)] = w.get(int(q), 0.0) + ar / 4.0
            if np.linalg.norm(nsum) < 1e-12:
                continue
            e_ = nsum / np.linalg.norm(nsum)
            ax = int(np.argmax(np.abs(e_)))
            for na, wt in w.items():
                if wt < minw or na not in ab:
                    continue
                nb = ab[na]
                if e_[ax] > 0:
                    out[(na, nb, ax + 1)] = wt
                else:
                    out[(nb, na, ax + 1)] = wt
        return [(a, b, d, wt) for (a, b, d), wt in out.items()]


def _wrap(lst, per=10):
    return "\n".join(", ".join(str(int(x)) for x in lst[i:i + per]) for i in range(0, len(lst), per))


class CcxCase:
    """Modelo de CalculiX listo para resolver.  Los contactos (resortes solo-compresion entre nodos gemelos) y la traccion de los pernos son
    unilaterales: para no depender de las iteraciones de contacto de CalculiX (que no convergen bien con varias piezas apoyadas) se
    resuelve un problema LINEAL con un conjunto de resortes activos y se actualiza ese conjunto hasta que no cambia (metodo de conjunto
    activo).  `write(path, ...)` escribe el .inp con el conjunto actual."""

    def __init__(self, mdl, mesh: Mesh, opts: dict):
        self.mdl, self.mesh, self.opts = mdl, mesh, dict(opts)
        E_ST, NU = opts.get("E", 29000.0), opts.get("nu", 0.3)
        self.E_ST, self.NU = E_ST, NU
        self.phi = float(opts.get("phi_y", 0.9))
        self.kc = float(opts.get("kc", 5.0e4))
        self.kshear = float(opts.get("kshear", 3500.0))
        bonded = [("W:" + w.name, w.A) for w in mdl.welds] + [("W:" + w.name, w.B) for w in mdl.welds] + list(getattr(mdl, "bonded", []))
        mesh.split(bonded)
        self.keys = list(mesh.names)
        self.head = []                                           # lineas fijas: nodos, elementos, materiales, cuerpos rigidos
        self.meta = {"parts": {}, "bolts": [], "welds": [], "supports": [], "loads": [], "contacts": [], "phi_y": self.phi, "E": E_ST,
                     "n_nodes": int(len(mesh.node_ids)), "n_elem": int(mesh.n_elem)}
        self.next_node = int(mesh.node_ids.max()) + 1
        self.next_elem = mesh.n_elem + 1
        self.rigid_nodes = set()
        self.bolt_ax = []            # [(elem, ref0, ref1, k, bolt index)]
        self.bolt_sh = []            # [(elem, n1, n2, dof, k)]
        self.gaps = []               # [(elem, n1, n2, dof, k)]
        self._build_bolts()
        self._build_welds()
        self._build_gaps()
        self._build_bc_loads()
        self._write_head()

    def _rigid(self, ids, ref, rot, c):
        """Cuerpo rigido como ecuaciones lineales (pequenos giros): u_i = u_ref + θ x (x_i - c), con θ = grados 1..3 del nodo `rot`.
        No se usa *RIGID BODY de CalculiX porque sus ecuaciones no lineales hacen divergir el paso elasto-plastico en algunos modelos
        (el residuo salta tras la primera iteracion aunque nada plastifique)."""
        ids = [int(n) for n in ids if int(n) not in (ref, rot)]
        X = self.mesh.coords(np.asarray(ids)) - np.asarray(c, float)
        L = ["*EQUATION"]
        for n, d in zip(ids, X):
            tm = (((rot, 2, -d[2]), (rot, 3, d[1])), ((rot, 3, -d[0]), (rot, 1, d[2])), ((rot, 1, -d[1]), (rot, 2, d[0])))
            for k in range(3):
                terms = [(n, k + 1, 1.0), (ref, k + 1, -1.0)] + [t for t in tm[k] if abs(t[2]) > 1e-12]
                L += [str(len(terms)), ", ".join(f"{a}, {b}, {v:.10g}" for a, b, v in terms)]
        return L

    # -------------------------------------------------------------------------- pernos
    def _build_bolts(self):
        mdl, mesh = self.mdl, self.mesh
        H = []
        for ib, b in enumerate(mdl.bolts):
            ax = unit(b.axis)
            p0 = np.asarray(b.p, float)
            refs, rims = [], []
            for ip, (pn, s0, s1) in enumerate(b.grip):
                nodes = mesh.part_nodes(pn)
                X = mesh.coords(nodes) - p0
                s = X @ ax
                r = np.linalg.norm(X - np.outer(s, ax), axis=1)
                tol_r = max(0.04, 0.12 * b.dh)
                rim = (np.abs(r - b.dh / 2.0) < tol_r) & (s >= s0 - 0.02) & (s <= s1 + 0.02)
                if ip == 0:
                    rim |= (np.abs(s - s0) < 0.02) & (r <= b.rw + 0.02) & (r >= b.dh / 2.0 - tol_r)
                if ip == len(b.grip) - 1:
                    rim |= (np.abs(s - s1) < 0.02) & (r <= b.rw + 0.02) & (r >= b.dh / 2.0 - tol_r)
                rim_ids = [int(n) for n in nodes[rim] if int(n) not in self.rigid_nodes]
                if len(rim_ids) < 3:
                    raise RuntimeError(f"Perno {b.tag}: la malla no tiene nodos en el agujero de la pieza {pn}.")
                self.rigid_nodes.update(rim_ids)
                c = p0 + ax * 0.5 * (s0 + s1)
                ref, rot = self.next_node, self.next_node + 1
                self.next_node += 2
                H += ["*NODE", f"{ref}, {c[0]:.6f}, {c[1]:.6f}, {c[2]:.6f}", f"{rot}, {c[0]:.6f}, {c[1]:.6f}, {c[2]:.6f}",
                      f"*NSET, NSET=RIM_{_san(b.tag)}_{ip}", _wrap(rim_ids)] + self._rigid(rim_ids, ref, rot, c)
                refs.append(ref)
                rims.append(len(rim_ids))
            Ab = math.pi * b.db ** 2 / 4.0
            Lgrip = abs(b.nut_s - b.head_s) + 0.5 * b.db
            kax = self.E_ST * Ab / Lgrip
            ks = self.kshear * (b.db ** 2)
            tr = [i for i in range(3) if abs(ax[i]) < 0.5]
            sh = []
            if len(refs) >= 2:
                self.bolt_ax.append((self.next_elem, refs[0], refs[-1], kax, ib))
                self.next_elem += 1
            for i in range(len(refs) - 1):
                for dof in tr:
                    self.bolt_sh.append((self.next_elem, refs[i], refs[i + 1], dof + 1, ks))
                    sh.append({"plane": i, "dof": dof + 1, "elem": self.next_elem})
                    self.next_elem += 1
            self.meta["bolts"].append({"tag": b.tag, "refs": refs, "kax": kax, "ks": ks, "axis": list(map(float, ax)), "db": b.db, "grade": b.grade,
                                       "planes": b.planes, "p": list(map(float, p0)), "grip": [(g[0], g[1], g[2]) for g in b.grip], "shear": sh,
                                       "nrim": rims, "trans": [int(t) + 1 for t in tr]})
        self.head_bolts = H

    def _build_welds(self):
        for w in self.mdl.welds:
            p0, p1 = np.asarray(w.p0, float), np.asarray(w.p1, float)
            self.meta["welds"].append({"name": w.name, "key": "W:" + w.name, "A": w.A, "B": w.B, "p0": list(map(float, p0)), "p1": list(map(float, p1)),
                                       "nA": list(map(float, unit(w.nA))), "nB": list(map(float, unit(w.nB))), "w": w.w, "fexx": w.fexx,
                                       "group": w.group})

    def _build_gaps(self):
        if not self.opts.get("contacts", True):
            return
        for (n1, n2, dof, wt) in self.mesh.gap_springs():
            if n1 in self.rigid_nodes or n2 in self.rigid_nodes:
                continue
            self.gaps.append((self.next_elem, n1, n2, dof, self.kc * wt))
            self.next_elem += 1
        self.meta["contacts"] = [{"name": "contactos", "n_springs": len(self.gaps)}] if self.gaps else []

    def _build_bc_loads(self):
        mdl, mesh = self.mdl, self.mesh
        H, bc, cl = [], [], []
        for i, s in enumerate(mdl.supports):
            fs = mesh.select(s.sel.part, s.sel.box, s.sel.normal)
            if not fs:
                raise RuntimeError(f"Apoyo '{s.name}': no se encontro la cara en la malla.")
            ns = sorted({int(n) for _e, _f, nodes in fs for n in nodes} - self.rigid_nodes)
            H += [f"*NSET, NSET=SUP{i}", _wrap(ns)]
            bc.append(f"SUP{i}, {min(s.dofs)}, {max(s.dofs)}")
            self.meta["supports"].append({"name": s.name, "nodes": ns})
        for i, ld in enumerate(mdl.loads):
            fs = []
            for sl in (ld.sel if isinstance(ld.sel, (list, tuple)) else [ld.sel]):
                fs += mesh.select(sl.part, sl.box, sl.normal)
            if not fs:
                raise RuntimeError(f"Carga '{ld.name}': no se encontro la cara en la malla.")
            ns = sorted({int(n) for _e, _f, nodes in fs for n in nodes} - self.rigid_nodes)
            ref, rot = self.next_node, self.next_node + 1
            self.next_node += 2
            c = ld.ref
            H += ["*NODE", f"{ref}, {c[0]:.6f}, {c[1]:.6f}, {c[2]:.6f}", f"{rot}, {c[0]:.6f}, {c[1]:.6f}, {c[2]:.6f}",
                  f"*NSET, NSET=LD{i}", _wrap(ns)] + self._rigid(ns, ref, rot, c)
            for d in range(3):
                if abs(ld.F[d]) > 0:
                    cl.append(f"{ref}, {d + 1}, {ld.F[d]:.6f}")
                if abs(ld.M[d]) > 0:
                    cl.append(f"{rot}, {d + 1}, {ld.M[d]:.6f}")
            for d in ld.fix_ref:
                bc.append(f"{ref}, {d}, {d}")
            for d in ld.fix_rot:
                bc.append(f"{rot}, {d}, {d}")
            self.meta["loads"].append({"name": ld.name, "ref": ref, "rot": rot, "nodes": ns, "F": list(ld.F), "M": list(ld.M)})
        self.head_bc = H
        self.bc, self.cl = bc, cl
        fm = [max(abs(x) for x in ld.F) for ld in mdl.loads] + [max(abs(x) for x in ld.M) / 10.0 for ld in mdl.loads]
        self.fref = max(fm + [1.0])

    # -------------------------------------------------------------------------- escritura
    def _write_head(self):
        mesh, mdl = self.mesh, self.mdl
        L = ["** SteelConPro - analisis 3D de la conexion", f"** {mdl.name}", "*NODE"]
        for nid, (x, y, z) in zip(mesh.node_ids, mesh.xyz):
            L.append(f"{int(nid)}, {x:.6f}, {y:.6f}, {z:.6f}")
        for k in self.keys:
            E = mesh.E[k]
            if not len(E):
                continue
            L.append(f"*ELEMENT, TYPE=C3D10, ELSET=E_{_san(k)}")
            for eid, row in zip(mesh.eid[k], E):
                L.append(str(int(eid)) + ", " + ", ".join(str(int(v)) for v in row))
            self.meta["parts"][k] = {"elems": [int(mesh.eid[k][0]), int(mesh.eid[k][-1])]}
        self.head_nodes_elems = L
        self.part_mats = {p.name: p for p in mdl.parts}

    def write(self, path, gap_on=None, bolt_on=None, plastic=None, inc=None, load_factor=1.0):
        """Escribe el .inp con los resortes activos indicados (conjuntos de indices; None = todos)."""
        plastic = self.opts.get("plastic", True) if plastic is None else plastic
        L = list(self.head_nodes_elems)
        for k in self.keys:
            if not len(self.mesh.E[k]):
                continue
            L += [f"*MATERIAL, NAME=M_{_san(k)}", "*ELASTIC", f"{self.E_ST:.1f}, {self.NU:.3f}"]
            if plastic and not k.startswith("W:"):
                pm = self.part_mats[k]
                if pm.hard:
                    fy, fu, eu = pm.hard
                    L += ["*PLASTIC", f"{fy:.4f}, 0.0", f"{fu:.4f}, {eu:.4f}", f"{fu * 1.001:.4f}, 0.30"]
                else:
                    fy = self.phi * pm.Fy
                    L += ["*PLASTIC", f"{fy:.4f}, 0.0", f"{fy * 1.0005:.4f}, 0.25"]
            L.append(f"*SOLID SECTION, ELSET=E_{_san(k)}, MATERIAL=M_{_san(k)}")
        L += self.head_bolts + self.head_bc
        # resortes de los pernos
        for (e, n1, n2, k, ib) in self.bolt_ax:
            if bolt_on is None or ib in bolt_on:
                L += [f"*ELEMENT, TYPE=SPRINGA, ELSET=BA{e}", f"{e}, {n1}, {n2}", f"*SPRING, ELSET=BA{e}", f"{k:.6f}"]
        sh = {}
        for (e, n1, n2, dof, k) in self.bolt_sh:
            sh.setdefault((dof, round(k, 3)), []).append((e, n1, n2))
        for (dof, k), lst in sh.items():
            L.append(f"*ELEMENT, TYPE=SPRING2, ELSET=BS{dof}_{int(k * 10)}")
            L += [f"{e}, {a}, {b}" for e, a, b in lst]
            L += [f"*SPRING, ELSET=BS{dof}_{int(k * 10)}", f"{dof}, {dof}", f"{k:.6f}"]
        # contactos
        by = {}
        for i, (e, n1, n2, dof, k) in enumerate(self.gaps):
            if gap_on is None or i in gap_on:
                by.setdefault((dof, int(round(math.log(max(k, 1e-9)) / math.log(1.1)))), []).append((e, n1, n2, k))
        for (dof, ci), lst in sorted(by.items()):
            name = f"GAP{dof}_{ci + 400}"
            kk = sum(k for *_x, k in lst) / len(lst)
            L.append(f"*ELEMENT, TYPE=SPRING2, ELSET={name}")
            L += [f"{e}, {a}, {b}" for e, a, b, _k in lst]
            L += [f"*SPRING, ELSET={name}", f"{dof}, {dof}", f"{kk:.6f}"]
        L += ["*BOUNDARY"] + self.bc
        L += [self.opts.get("step_card", "*STEP, INC=200"), "*STATIC", inc or ("0.1, 1.0, 0.002, 0.25" if plastic else "1.0, 1.0"), "*CLOAD"]
        for line in self.cl:
            if load_factor != 1.0:
                n, d, v = line.split(",")
                line = f"{n}, {d}, {float(v) * load_factor:.6f}"
            L.append(line)
        L += ["*NODE FILE", "U, RF", "*EL FILE", "S" + (", PEEQ" if plastic else ""), "*END STEP"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
        return path


def build_inp(mdl, mesh: Mesh, out_inp: str, opts: dict) -> dict:
    """Atajo: un solo .inp con todos los resortes activos (pruebas)."""
    case = CcxCase(mdl, mesh, opts)
    case.write(out_inp)
    return case.meta


def _san(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s)
