# -*- coding: utf-8 -*-
"""
Soldadura perfil-placa del modelo solido 3D: CORDON COMO CONECTORES entre cuerpos separados.

Problema del modelo fusionado.  Si el perfil y la placa comparten los nodos de la interfaz, la union es de
resistencia total (una CJP ideal) y la fuerza del cordon hay que deducirla de los esfuerzos del perfil en una
franja cercana; ademas, una zona SIN soldar transmite igual, la compresion pasa por la union y la
concentracion en las esquinas depende de la malla.

Modelo con conectores (este modulo).  Despues de mallar (malla conforme, con nodos compartidos) se separa el
cuerpo superior (perfil y rigidizadores) del inferior (placa y llave) duplicando los nodos de la interfaz.  Los
dos cuerpos solo se comunican por:

  · CONTACTO en compresion, sobre toda la huella: un resorte solo-compresion por nodo, con la rigidez de
    contacto por area (tributaria) del nodo.  El cordon no trabaja a compresion (DG1: la compresion pasa por
    aplastamiento).
  · CORDON: sobre cada linea de soldadura (borde de la huella del perfil o de la pletina, cara exterior o
    interior de la pared) un conector por nodo: normal solo-traccion + dos resortes de cortante.  La
    rigidez por unidad de longitud es la de una garganta de acero sobre una longitud igual al cateto:
        filete  k = 0.707·E (normal)  y  0.707·G (cortante)    [independiente del tamano]
        PJP     k = E y G      ·      CJP  k = 5·E y 5·G (practicamente monolitica)
    Al ser una junta con flexibilidad finita, la fuerza del cordon es convergente con la malla (no hay
    singularidad de esquina) y se lee DIRECTO del conector: F = k·Δ.  Un lado sin cordon (soldadura a un
    solo lado o "sin soldadura") no tiene conector: no transmite tracción ni cortante.

Nodo auxiliar.  Un resorte SPRINGA de CalculiX se orienta segun la posicion ACTUAL de sus dos nodos; si el
perfil se desliza lateralmente respecto de la placa (el cortante del cordon), el resorte se inclina y su
alargamiento vertical se contamina con Δ²/2δ.  Para que los resortes normales (contacto y cordon a traccion)
midan solo el movimiento vertical, cada nodo de la interfaz tiene un nodo auxiliar H cuyas componentes se
ligan con *EQUATION: H_z = z del nodo superior, H_x, H_y = x, y del nodo inferior.  El resorte va del nodo
inferior a H: es siempre vertical y su alargamiento es exactamente Δz.

Verificacion (AISC 360 J2.4): la fuerza por unidad de longitud de cada linea (normal, longitudinal y transversal
al cordon) se promedia en una ventana movil (por defecto 4 veces el cateto, nunca menos de 3 elementos), lo que
equivale a la redistribucion por ductilidad de un cordon real; el maximo de esa curva y el promedio de la
linea se comparan con φ·0.60·FEXX·garganta·kd por linea, y la fuerza total de la pared (suma de sus lineas)
con la rotura del metal base.
"""
from __future__ import annotations
import math
import re
from pathlib import Path

from .units import ES_KSI, NU_STEEL
from . import geometry as G
from .params3d import washer_elements

DELTA = 0.02                       # separacion inicial de los nodos duplicados, in (direccion del resorte)
AUX_BASE = 100000                  # los nodos auxiliares H se numeran desde max(nodo) + AUX_BASE
GS = ES_KSI / (2.0 * (1.0 + NU_STEEL))
KC_AREA = 5.0e5                    # rigidez de contacto por unidad de area, kip/in^3 (≈ 17·E/in)
MAXRANGE = 50.0                    # rango de la curva de los resortes no lineales, in
TOL_PAR = math.cos(math.radians(11.0))


# ===================================================================== lectura y separacion de la malla
def _parse_mesh(path):
    lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    nodes, el = {}, {}
    mode = None
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not t or t.startswith("**"):
            continue
        up = t.upper()
        if up.startswith("*NODE"):
            mode = "N"
            continue
        if up.startswith("*ELEMENT"):
            mode = "E" if re.search(r"TYPE\s*=\s*C3D", t, re.I) else None
            continue
        if t.startswith("*"):
            mode = None
            continue
        v = [x.strip() for x in t.rstrip(",").split(",") if x.strip()]
        if mode == "N" and len(v) >= 4:
            nodes[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]))
        elif mode == "E" and len(v) >= 5:
            el[i] = (int(v[0]), [int(x) for x in v[1:]])
    return lines, nodes, el


class Split:
    """Resultado de separar los cuerpos.  `nodes`/`up_elems` ya incluyen los nodos duplicados."""
    def __init__(self):
        self.nodes = {}
        self.dup = {}            # nodo de la placa (inferior) -> nodo duplicado del cuerpo superior
        self.up_elems = []       # elementos del cuerpo superior (con los nodos nuevos)
        self.tp = 0.0
        self.mesh_path = ""


def split_interface(mesh_in: str, mesh_out: str, tp: float, prj=None):
    """Duplica los nodos de la interfaz z = tp entre el cuerpo superior (centroide z > tp) y el inferior.
    Escribe `mesh_out` (malla con los elementos superiores reconectados) y devuelve un `Split`, o None si
    no hay interfaz."""
    lines, nodes, el = _parse_mesh(mesh_in)
    up_l, lo_nodes, up_nodes = [], set(), set()
    for i, (eid, nn) in el.items():
        zc = sum(nodes[n][2] for n in nn[:4]) / 4.0
        xc = sum(nodes[n][0] for n in nn[:4]) / 4.0
        yc = sum(nodes[n][1] for n in nn[:4]) / 4.0
        if zc > tp + 1e-6 and not (prj is not None and washer_elements(prj, xc, yc, zc)):
            up_l.append(i)
            up_nodes.update(nn)
        else:
            lo_nodes.update(nn)
    iface = sorted(n for n in (up_nodes & lo_nodes) if abs(nodes[n][2] - tp) < 1e-5)
    if not up_l or not iface:
        return None
    nid = max(nodes) + 1
    dup = {n: nid + k for k, n in enumerate(iface)}
    for i in up_l:
        eid, nn = el[i]
        new = [dup.get(n, n) for n in nn]
        el[i] = (eid, new)
        lines[i] = f"{eid}, " + ", ".join(str(x) for x in new)
    lines.append("*NODE")
    for n in iface:
        x, y, z = nodes[n]
        lines.append(f"{dup[n]}, {x:.6f}, {y:.6f}, {z + DELTA:.6f}")
    Path(mesh_out).write_text("\n".join(lines), encoding="utf-8")

    S = Split()
    S.tp = tp
    S.dup = dup
    S.nodes = dict(nodes)
    for n, m in dup.items():
        x, y, z = nodes[n]
        S.nodes[m] = (x, y, z + DELTA)
    S.up_elems = [el[i][1] for i in up_l]
    S.mesh_path = mesh_out
    return S


# ===================================================================== lineas de soldadura
def _walls(prj):
    """Paredes soldables: (zona, p1, p2, espesor, WeldSpec, clave, periodica)."""
    from .weld3d import _walls as _w
    from .model import WeldSpec
    W = prj.welds
    s = prj.section.shape()
    periodic = bool(s.is_round) and not prj.section.generic
    out = []
    for (name, p1, p2, t, spec) in _w(prj):
        key = "flange" if spec is W.flange else ("web" if spec is W.web else "perimeter")
        out.append(dict(zone=name, p1=p1, p2=p2, t=t, spec=spec, key=key, periodic=periodic))
    st = prj.stiff
    if st.enabled and st.count > 0 and not prj.section.generic:
        spec = WeldSpec("Filete", st.weld_size, st.electrode, True)
        c = max(0.0, min(st.clip_root, 0.45 * min(st.L, st.h)))
        for (x1, y1, x2, y2) in G.stiffener_lines(prj):
            Ls = math.hypot(x2 - x1, y2 - y1)
            if Ls < 1e-6:
                continue
            ux, uy = (x2 - x1) / Ls, (y2 - y1) / Ls
            out.append(dict(zone="Rigidizadores", p1=(x1 + ux * c, y1 + uy * c), p2=(x2, y2), t=st.t,
                            spec=spec, key="stiff", periodic=False))
    return out


def long_beta(prj, w):
    """Reduccion por cordon largo (AISC 360 J2.2b(d); EN 1993-1-8 4.11 es analoga): el FEM no la captura (Ghimire
    et al. 2023).  β = 1 si L <= 100·w;  1.2 − 0.002·L/w hasta 300·w;  longitud efectiva 180·w (β = 180·w/L) despues.
    No aplica a cordones continuos de tubos redondos, ni a penetracion parcial o completa."""
    if not getattr(prj.fea, "weld_long_reduction", True) or w["periodic"] or w["spec"].wtype != "Filete":
        return 1.0
    (ax, ay), (bx, by) = w["p1"], w["p2"]
    r = math.hypot(bx - ax, by - ay) / max(w["spec"].size, 1e-9)
    if r <= 100.0:
        return 1.0
    return max(0.6, 1.2 - 0.002 * r) if r <= 300.0 else 180.0 / r


def plastic_on(prj):
    return str(getattr(prj.fea, "weld_criterion", "")).startswith("Plastico")


SLOPE = 1.0e-3                     # pendiente plastica relativa del conector (E/1000, como en Ghimire et al. 2023)


def yield_levels(prj, spec, beta=1.0):
    """(fuerza de fluencia por unidad de longitud en cortante LONGITUDINAL, en cortante/normal TRANSVERSAL), kip/in.
    Es la resistencia de diseno AISC J2.4: φ·0.60·FEXX·garganta (φ = 0.75), x1.5 si el cordon trabaja transversal
    (J2-5).  Con CJP o sin soldadura no hay fluencia (0, 0)."""
    if spec.wtype.startswith("CJP") or spec.wtype == "Sin soldadura":
        return 0.0, 0.0
    thr = 0.707 * spec.size if spec.wtype == "Filete" else spec.size
    fl = 0.75 * 0.60 * spec.FEXX() * thr * beta
    kdT = 1.5 if (spec.wtype == "Filete" and prj.welds.directional) else 1.0
    return fl, fl * kdT


def shear_yields(fyl, fyt, ux, uy):
    """Fluencia de los resortes globales de cortante x e y segun la orientacion del cordon (ux, uy): el resorte
    alineado con la linea es longitudinal y el perpendicular, transversal.  |u| se cuantiza a 1/4."""
    qx, qy = round(abs(ux) * 4.0) / 4.0, round(abs(uy) * 4.0) / 4.0
    return fyt - (fyt - fyl) * qx, fyt - (fyt - fyl) * qy


def spring_force(d, k, dy, slope=SLOPE):
    """Fuerza por unidad de longitud y deformacion plastica de un resorte bilineal simetrico: (f, d_plastico)."""
    a = abs(d)
    if dy <= 0 or a <= dy:
        return k * d, 0.0
    f = k * dy + slope * k * (a - dy)
    return math.copysign(f, d), a - dy


def _weld_stiff(spec):
    """(k normal, k cortante) por unidad de longitud de cordon, kip/in^2."""
    if spec.wtype.startswith("CJP"):
        return 5.0 * ES_KSI, 5.0 * GS
    if spec.wtype.startswith("PJP"):
        return ES_KSI, GS
    return 0.707 * GS, 0.707 * GS          # filete: rigidez del throat a cortante, 0.272·E, en las tres direcciones 


def free_faces(S: Split):
    """Caras (a, b, c, elemento) del cuerpo superior que quedan sobre la interfaz."""
    z0 = S.tp + DELTA
    faces = []
    for e in S.up_elems:
        c = e[:4]
        for f in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)):
            ids = (c[f[0]], c[f[1]], c[f[2]])
            if all(abs(S.nodes[n][2] - z0) < 1e-4 for n in ids):
                faces.append((ids, e))
    return faces


def boundary_edges(S: Split):
    """Aristas del borde de la interfaz: [(n1, nmedio|None, n2)].  Una arista esta en el borde si pertenece
    a un solo triangulo de la cara inferior del cuerpo superior."""
    cnt, info = {}, {}
    for ids, e in free_faces(S):
        for (i, j) in ((0, 1), (1, 2), (2, 0)):
            key = tuple(sorted((ids[i], ids[j])))
            cnt[key] = cnt.get(key, 0) + 1
            info[key] = e
    out = []
    for key, k in cnt.items():
        if k != 1:
            continue
        e = info[key]
        mid = None
        if len(e) >= 10:
            a, b = S.nodes[key[0]], S.nodes[key[1]]
            m = tuple(0.5 * (a[q] + b[q]) for q in range(3))
            mid = min(e[4:10], key=lambda n: sum((S.nodes[n][q] - m[q]) ** 2 for q in range(3)))
        out.append((key[0], mid, key[1]))
    return out


def match_lines(prj, S: Split, edges):
    """Asigna cada arista del borde a una pared soldable.  -> lista de registros por nodo:
       dict(zone, group, side, up, dn, w, a, ux, uy, x, y, key, t, wall, kn, ks, on)"""
    walls = _walls(prj)
    beta_w = [long_beta(prj, w) for w in walls]
    recs = {}
    inv = {v: k for k, v in S.dup.items()}
    for (n1, nm, n2) in edges:
        p1, p2 = S.nodes[n1], S.nodes[n2]
        Le = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if Le < 1e-9:
            continue
        tx, ty = (p2[0] - p1[0]) / Le, (p2[1] - p1[1]) / Le
        mx, my = 0.5 * (p1[0] + p2[0]), 0.5 * (p1[1] + p2[1])
        best = None
        for wi, w in enumerate(walls):
            (ax, ay), (bx, by) = w["p1"], w["p2"]
            Lw = math.hypot(bx - ax, by - ay)
            if Lw < 1e-9:
                continue
            ux, uy = (bx - ax) / Lw, (by - ay) / Lw
            if abs(tx * ux + ty * uy) < TOL_PAR:
                continue
            nx, ny = -uy, ux
            d = (mx - ax) * nx + (my - ay) * ny
            a = (mx - ax) * ux + (my - ay) * uy
            t = w["t"]
            tolo = 0.2 * t + 0.03
            tola = 0.3 * t + 0.05
            err = abs(abs(d) - t / 2.0)
            if err > tolo or a < -tola or a > Lw + tola:
                continue
            if best is None or err < best[0]:
                best = (err, wi, d, a, ux, uy, nx, ny, Lw)
        if best is None:
            continue
        _, wi, d, a, ux, uy, nx, ny, Lw = best
        w = walls[wi]
        # cara exterior: la que mira alejandose del centroide del perfil
        cx = 0.5 * (w["p1"][0] + w["p2"][0]); cy = 0.5 * (w["p1"][1] + w["p2"][1])
        proj = cx * nx + cy * ny
        o = (1.0 if proj >= 0 else -1.0) if abs(proj) > 1e-6 else 1.0
        outer = (d * o) > 0
        side = "out" if outer else "in"
        spec = w["spec"]
        on = spec.wtype != "Sin soldadura" and (outer or spec.both_sides or w["key"] == "stiff")
        kn, ks = _weld_stiff(spec)
        # pesos de carga consistente de la arista: (1/6, 4/6, 1/6) con nodo medio; (1/2, 1/2) sin el
        wts = ([(n1, Le / 6.0), (nm, 4.0 * Le / 6.0), (n2, Le / 6.0)] if nm is not None
               else [(n1, Le / 2.0), (n2, Le / 2.0)])
        gid = ("ring" if w["periodic"] else wi, side)
        for (n, wt) in wts:
            if n not in inv:
                continue
            key = (gid, n)
            r = recs.get(key)
            x, y = S.nodes[n][0], S.nodes[n][1]
            if r is None:
                r = dict(zone=w["zone"], group=gid, side=side, up=n, dn=inv[n], w=0.0, ax=0.0, ay=0.0,
                         x=x, y=y, key=w["key"], t=w["t"], wall=wi, kn=kn, ks=ks, on=on, spec=spec,
                         periodic=w["periodic"], beta=beta_w[wi])
                recs[key] = r
            r["w"] += wt
            r["ax"] += wt * ux
            r["ay"] += wt * uy
    out = []
    for r in recs.values():
        nrm = math.hypot(r["ax"], r["ay"])
        r["ux"], r["uy"] = (r["ax"] / nrm, r["ay"] / nrm) if nrm > 1e-12 else (1.0, 0.0)
        del r["ax"], r["ay"]
        out.append(r)
    # parametro a lo largo de la linea (arco para tubos redondos)
    rmid = {}
    for r in out:
        if r["periodic"]:
            rr = math.hypot(r["x"] - G.col_shift(prj)[0], r["y"] - G.col_shift(prj)[1])
            r["a"] = rr * math.atan2(r["y"] - G.col_shift(prj)[1], r["x"] - G.col_shift(prj)[0])
            rmid[r["group"]] = rr
        else:
            (ax, ay), (bx, by) = walls[r["wall"]]["p1"], walls[r["wall"]]["p2"]
            r["a"] = (r["x"] - ax) * r["ux"] + (r["y"] - ay) * r["uy"]
    return out, walls, rmid


# ===================================================================== tarjetas de CalculiX
def _classes(vals, ratio=1.08):
    """Agrupa valores positivos en clases de ~8 %."""
    cl = {}
    for key, v in vals:
        cl.setdefault(int(round(math.log(max(v, 1e-12)) / math.log(ratio))), []).append((key, v))
    return cl


def bearing_weights(S: Split):
    """Area tributaria de cada nodo de la interfaz (cara inferior del cuerpo superior)."""
    from .mesh3d import bottom_weights
    w = bottom_weights(S.nodes, S.up_elems, z0=S.tp + DELTA)
    inv = {v: k for k, v in S.dup.items()}
    return {inv[n]: a for n, a in w.items() if n in inv}


def _weld_cards_plastic(prj, on, H, eid_box, D):
    """Conectores del cordon ELASTO-PLASTICOS (Ghimire et al. 2023, CBFEM): rigidez elastica k, fluencia en la
    resistencia de diseno AISC J2.4 (ver yield_levels) y rama plastica corta de pendiente k/1000.  El D/C del
    cordon vale 1 cuando la deformacion plastica de la garganta llega al limite (5 %)."""
    L = []
    eid = eid_box[0]
    # normal (solo traccion) : clase por (k·w, fluencia)
    cls = {}
    for i, r in enumerate(on):
        fyl, fyt = yield_levels(prj, r["spec"], r.get("beta", 1.0))
        dyn = fyt / r["kn"] if fyt > 0 else 0.0
        cls.setdefault((int(round(math.log(max(r["kn"] * r["w"], 1e-12)) / math.log(1.08))), round(dyn * 1e7)),
                       []).append((i, r["kn"] * r["w"], dyn))
    for n, ((ci, qd), lst) in enumerate(sorted(cls.items())):
        kk = sum(v for _, v, _ in lst) / len(lst)
        dy = lst[0][2]
        name = f"EWELDN{n + 200}"
        L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET={name}")
        for (i, _, _) in lst:
            r = on[i]
            L.append(f"{eid}, {r['dn']}, {H[r['dn']]}")
            eid += 1
        if dy > 0:
            fy_, fm = kk * dy, kk * dy + SLOPE * kk * (D - dy)
            L += [f"*SPRING, ELSET={name}, NONLINEAR",
                  f"{-fm:.6e}, {-D:.1f}", f"{-fy_:.6e}, {-dy:.8f}", "0.0, 0.0",
                  f"{fy_:.6e}, {dy:.8f}", f"{fm:.6e}, {D:.1f}"]
        else:
            L += [f"*SPRING, ELSET={name}, NONLINEAR",
                  f"{-kk * D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kk * D:.6e}, {D:.1f}"]
    # cortante x e y : clase por (k·w, fluencia del resorte)
    for dof in (1, 2):
        cls = {}
        for i, r in enumerate(on):
            fyl, fyt = yield_levels(prj, r["spec"], r.get("beta", 1.0))
            fy = shear_yields(fyl, fyt, r["ux"], r["uy"])[dof - 1]
            dy = fy / r["ks"] if fy > 0 else 0.0
            cls.setdefault((int(round(math.log(max(r["ks"] * r["w"], 1e-12)) / math.log(1.08))), round(dy * 1e7)),
                           []).append((i, r["ks"] * r["w"], dy))
        for n, ((ci, qd), lst) in enumerate(sorted(cls.items())):
            kk = sum(v for _, v, _ in lst) / len(lst)
            dy = lst[0][2]
            name = f"EWELDS{dof}_{n + 200}"
            L.append(f"*ELEMENT, TYPE=SPRING2, ELSET={name}")
            for (i, _, _) in lst:
                r = on[i]
                L.append(f"{eid}, {r['dn']}, {r['up']}")
                eid += 1
            if dy > 0:
                fy_, fm = kk * dy, kk * dy + SLOPE * kk * (D - dy)
                L += [f"*SPRING, ELSET={name}, NONLINEAR", f"{dof},{dof}",
                      f"{-fm:.6e}, {-D:.1f}", f"{-fy_:.6e}, {-dy:.8f}", "0.0, 0.0",
                      f"{fy_:.6e}, {dy:.8f}", f"{fm:.6e}, {D:.1f}"]
            else:
                L += [f"*SPRING, ELSET={name}", f"{dof},{dof}", f"{kk:.6f}"]
    eid_box[0] = eid
    return L


def write_cards(prj, S: Split, recs, eid: int):
    """Tarjetas *ELEMENT/*SPRING del contacto y del cordon.  -> (lineas, siguiente eid, meta)."""
    L = []
    D = MAXRANGE
    bw = bearing_weights(S)
    on = [r for r in recs if r["on"]]
    # ---- nodos auxiliares H (uno por nodo de la interfaz con resorte normal) y sus ecuaciones
    need = sorted(set(n for n, a in bw.items() if a > 0) | set(r["dn"] for r in on))
    hbase = max(S.nodes) + AUX_BASE
    H = {n: hbase + k for k, n in enumerate(need)}
    L.append("*NODE")
    for n, h in H.items():
        x, y, z = S.nodes[n]
        L.append(f"{h}, {x:.6f}, {y:.6f}, {z + DELTA:.6f}")
    L.append("*EQUATION")
    for n, h in H.items():
        up = S.dup[n]
        L += ["2", f"{h},3,1.0,{up},3,-1.0",
              "2", f"{h},1,1.0,{n},1,-1.0",
              "2", f"{h},2,1.0,{n},2,-1.0"]
    # ---- contacto solo-compresion en toda la huella
    cl = _classes([(n, a) for n, a in bw.items() if a > 0])
    for ci, lst in sorted(cl.items()):
        kc = KC_AREA * sum(a for _, a in lst) / len(lst)
        L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET=ECONT{ci + 200}")
        for (n, _) in lst:
            L.append(f"{eid}, {n}, {H[n]}")
            eid += 1
        L += [f"*SPRING, ELSET=ECONT{ci + 200}, NONLINEAR",
              f"{-kc * D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kc * 1e-6 * D:.6e}, {D:.1f}"]
    # ---- cordon: normal solo-traccion + cortante x, y
    plas = plastic_on(prj)
    if plas:
        L += _weld_cards_plastic(prj, on, H, eid_box := [eid], D)
        eid = eid_box[0]
    else:
        cl_n = _classes([(i, r["kn"] * r["w"]) for i, r in enumerate(on)])
        for ci, lst in sorted(cl_n.items()):
            kk = sum(v for _, v in lst) / len(lst)
            L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET=EWELDN{ci + 200}")
            for (i, _) in lst:
                r = on[i]
                L.append(f"{eid}, {r['dn']}, {H[r['dn']]}")
                eid += 1
            L += [f"*SPRING, ELSET=EWELDN{ci + 200}, NONLINEAR",
                  f"{-kk * D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kk * D:.6e}, {D:.1f}"]    # el elemento transmite tambien compresion
        cl_s = _classes([(i, r["ks"] * r["w"]) for i, r in enumerate(on)])
        for ci, lst in sorted(cl_s.items()):
            kk = sum(v for _, v in lst) / len(lst)
            for dof in (1, 2):
                L.append(f"*ELEMENT, TYPE=SPRING2, ELSET=EWELDS{dof}_{ci + 200}")
                for (i, _) in lst:
                    r = on[i]
                    L.append(f"{eid}, {r['dn']}, {r['up']}")
                    eid += 1
                L += [f"*SPRING, ELSET=EWELDS{dof}_{ci + 200}", f"{dof},{dof}", f"{kk:.6f}"]
    # ---- sin ningun cordon: rigidez tangencial minima para no dejar el cuerpo superior libre en el plano
    if not on:
        kf = 1e-3 * KC_AREA
        for dof in (1, 2):
            L.append(f"*ELEMENT, TYPE=SPRING2, ELSET=EFRICT{dof}")
            for n in bw:
                L.append(f"{eid}, {n}, {S.dup[n]}")
                eid += 1
            L += [f"*SPRING, ELSET=EFRICT{dof}", f"{dof},{dof}", f"{kf / max(len(bw), 1):.6f}"]
    meta = dict(
        delta=DELTA, kc_area=KC_AREA,
        bearing=[[n, S.dup[n], a] for n, a in bw.items()],
        lines=[dict(zone=r["zone"], group=[str(r["group"][0]), r["group"][1]], side=r["side"], up=r["up"],
                    dn=r["dn"], w=r["w"], a=r["a"], ux=r["ux"], uy=r["uy"], x=r["x"], y=r["y"],
                    key=r["key"], t=r["t"], wall=r["wall"], kn=r["kn"], ks=r["ks"], on=bool(r["on"]), beta=float(r.get("beta", 1.0)),
                    periodic=bool(r["periodic"])) for r in recs],
        dup={str(k): v for k, v in S.dup.items()})
    return L, eid, meta


def prepare_and_cards(prj, mesh_in, mesh_split, eid_start):
    """Separacion de cuerpos + tarjetas.  -> (Split, lineas, eid, meta) o None si no hay interfaz."""
    S = split_interface(mesh_in, mesh_split, prj.plate.tp, prj)
    if S is None:
        return None
    edges = boundary_edges(S)
    recs, walls, _ = match_lines(prj, S, edges)
    return S, recs, walls


# ===================================================================== postproceso
def _cap_line(prj, spec, fn, fl, ft, beta=1.0):
    """Capacidad por unidad de longitud de UNA linea de cordon (AISC J2.4) y su D/C.
    -> (cap, ratio, kd).  Filete/PJP: φ·0.60·FEXX·garganta·kd.  CJP: no se verifica por linea."""
    f = math.sqrt(fn * fn + fl * fl + ft * ft)             # el elemento toma tambien compresion: cuenta su modulo (Ec. 23 del paper)
    if spec.wtype.startswith("CJP") or spec.wtype == "Sin soldadura" or f < 1e-12:
        return 0.0, 0.0, 1.0
    thr = 0.707 * spec.size if spec.wtype == "Filete" else spec.size
    kd = 1.0
    if spec.wtype == "Filete" and prj.welds.directional:
        sin_th = min(1.0, math.sqrt(fn * fn + ft * ft) / f)
        kd = 1.0 + 0.5 * sin_th ** 1.5                                   # AISC Ec. J2-5
    cap = 0.75 * 0.60 * spec.FEXX() * thr * kd * beta
    return cap, f / cap, kd


def matching_electrode(fexx, fu):
    """Electrodo compatible ("matching") con el metal base segun AISC 360 Tabla 3-1: E70 para aceros con Fu <= 70 ksi
    (A36, A500, A572 Gr.50, A992...), E80 hasta 80 ksi, etc.  Un electrodo menor tambien es compatible (rige el cordon).
    Solo un electrodo SUPERIOR al compatible (sobrecompatible) obliga a verificar el metal base (J2.4, Ec. 26 del paper)."""
    need = max(70.0, 10.0 * math.ceil(fu / 10.0 - 1e-9))
    return fexx <= need + 1e-6


def _wall_ratio(prj, spec, key, t, fn, fl, ft):
    """D/C del metal base de la pared con la fuerza TOTAL por unidad de longitud de todas sus lineas.
    CJP: 0.90·Fy·t (normal) y 0.60·Fy·t (cortante).  Filete/PJP: rotura 0.75·0.60·Fu·t, solo con electrodo
    sobrecompatible (con electrodo compatible el cordon gobierna y no se verifica el metal base)."""
    if key == "stiff":
        base = prj.stiff.mat()
    else:
        base = prj.section.mat()
    plate = prj.plate.mat()
    fs = math.hypot(fl, ft)
    if spec.wtype.startswith("CJP"):
        return math.hypot(max(fn, 0.0) / (0.90 * base.Fy * t), fs / (0.60 * base.Fy * t))
    Fu = min(base.Fu, plate.Fu)
    if matching_electrode(spec.FEXX(), Fu):
        return 0.0                    # AISC J2.4: con electrodo compatible no se verifica el metal base (paper, Ec. 23)
    cap_b = 0.75 * 0.60 * Fu * t
    return math.sqrt(fn * fn + fs * fs) / cap_b


def _smooth(a, w, comps, win, period=None):
    """Media movil ponderada por longitud de las componentes (lista de listas) en una ventana `win`."""
    import numpy as np
    a = np.asarray(a, float); w = np.asarray(w, float)
    C = np.asarray(comps, float)                    # (n_comp, n)
    out = np.zeros_like(C)
    for i in range(len(a)):
        d = np.abs(a - a[i])
        if period:
            d = np.minimum(d, period - d)
        m = d <= win / 2.0
        ww = w[m]
        out[:, i] = (C[:, m] * ww).sum(axis=1) / max(ww.sum(), 1e-12)
    return out


def postprocess_conn(prj, res, conn, WeldZone, spec_txt):
    """Fuerzas del cordon leidas de los conectores.  -> (zonas, dict(totales))."""
    import numpy as np
    disp = res.disp
    lines = conn["lines"]
    kc = conn["kc_area"]

    def elong(up, dn):
        """Alargamiento del resorte normal = desplazamiento vertical relativo (nodo auxiliar, ver arriba)."""
        if up not in disp or dn not in disp:
            return 0.0
        return disp[up][2] - disp[dn][2]

    # ---- contacto perfil-placa
    F_bear, p_bear = 0.0, 0.0
    for (dn, up, a) in conn["bearing"]:
        if dn in disp and up in disp:
            e = elong(up, dn)
            if e < 0:
                F_bear += kc * a * (-e)
                p_bear = max(p_bear, kc * (-e))

    plas = plastic_on(prj)
    eps_lim = max(float(getattr(prj.fea, "weld_plastic_limit", 5.0)), 0.1) / 100.0
    walls_all = _walls(prj)
    recs = []
    for r in lines:
        rr = dict(r)
        e = (0.0, 0.0, 0.0)
        if r["dn"] in disp and r["up"] in disp:
            e = tuple(disp[r["up"]][q] - disp[r["dn"]][q] for q in range(3))
        epl = 0.0
        if r["on"]:
            if plas:
                # conector elasto-plastico: fuerza y deformacion plastica (en cateto) desde el alargamiento
                wl = walls_all[r["wall"]]
                spec_r = wl["spec"]
                fyl, fyt = yield_levels(prj, spec_r, r.get("beta", 1.0))
                dn_ = elong(r["up"], r["dn"])
                fn, pn = spring_force(dn_, r["kn"], (fyt / r["kn"]) if fyt > 0 else 0.0)
                fyx, fyy = shear_yields(fyl, fyt, r["ux"], r["uy"])
                fx, px = spring_force(e[0], r["ks"], (fyx / r["ks"]) if fyx > 0 else 0.0)
                fy, py = spring_force(e[1], r["ks"], (fyy / r["ks"]) if fyy > 0 else 0.0)
                leg = max(spec_r.size, 1e-6)
                epl = math.sqrt(pn * pn + px * px + py * py) / leg
            else:
                fn = r["kn"] * elong(r["up"], r["dn"])
                fx, fy = r["ks"] * e[0], r["ks"] * e[1]
        else:
            fn = fx = fy = 0.0
        rr["fn"] = fn
        rr["fl"] = fx * r["ux"] + fy * r["uy"]
        rr["ft"] = -fx * r["uy"] + fy * r["ux"]
        rr["epl"] = epl
        recs.append(rr)

    walls = {w["wall"]: w for w in recs}
    groups = {}
    for r in recs:
        groups.setdefault((tuple(r["group"]), ), []).append(r)

    spec_of = {}
    # WeldSpec de cada pared por indice (se reconstruye igual que en match_lines)
    for wi, w in enumerate(_walls(prj)):
        spec_of[wi] = w

    smoothed = {}
    for gk, lst in groups.items():
        lst.sort(key=lambda r: r["a"])
        a = [r["a"] for r in lst]; w = [r["w"] for r in lst]
        spec = spec_of[lst[0]["wall"]]["spec"]
        period = None
        if lst[0]["periodic"]:
            rr = float(np.mean([math.hypot(r["x"], r["y"]) for r in lst]))
            period = 2.0 * math.pi * rr
        mean_w = float(np.mean(w)) if w else 0.1
        win = max(4.0 * spec.size, 6.0 * mean_w, 0.5)
        if plas:
            win = 1e-9      # cordon plastico (Ghimire et al. 2023): valor por elemento, sin suavizar; la fluencia redistribuye
        S = _smooth(a, w, [[r["fn"] for r in lst], [r["fl"] for r in lst], [r["ft"] for r in lst],
                           [r["epl"] for r in lst]], win, period)
        smoothed[gk] = (lst, S, period, win)

    # fuerza total de la pared en cada nodo: suma de las lineas de la misma pared (o del anillo)
    def wallkey(r):
        return "ring" if r["periodic"] else r["wall"]

    by_wall = {}
    for gk, (lst, S, period, win) in smoothed.items():
        by_wall.setdefault(wallkey(lst[0]), []).append(gk)

    def nearest(gk, ai):
        lst, S, period, win = smoothed[gk]
        a = np.array([r["a"] for r in lst])
        d = np.abs(a - ai)
        if period:
            d = np.minimum(d, period - d)
        j = int(np.argmin(d))
        return S[:3, j] if d[j] <= win else np.zeros(3)

    zones = {}
    Fn_tot = 0.0

    def zone_of(name, spec, t):
        Z = zones.get(name)
        if Z is None:
            Z = WeldZone(name, spec_txt(spec), t)
            zones[name] = Z
        return Z

    for gk, (lst, S, period, win) in smoothed.items():
        others = [g for g in by_wall[wallkey(lst[0])] if g != gk]
        wl = spec_of[lst[0]["wall"]]
        spec, t, key = wl["spec"], wl["t"], wl["key"]
        # ---- pico (curva suavizada); solo en las lineas con cordon (la fuerza de la pared es la de todas)
        for i, r in enumerate(lst):
            Z = zone_of(r["zone"], spec, t)
            if not r["on"]:
                continue
            fn, fl, ft, eps_s = S[:, i]
            tot = np.array([fn, fl, ft])
            for og in others:
                tot = tot + nearest(og, r["a"])
            beta_r = r.get("beta", 1.0)
            cap, rw, kd = _cap_line(prj, spec, fn, fl, ft, beta_r)
            if plas and cap > 0:
                # criterio plastico: D/C = deformacion plastica / limite si el cordon fluyo en el punto; si no, D/C elastico
                rw = eps_s / eps_lim if eps_s > 1e-9 else min(rw, 1.0)
                Z.plastic = True
                Z.eps = max(Z.eps, float(eps_s))
            Z.beta = min(Z.beta, beta_r)
            rb = _wall_ratio(prj, spec, key, t, tot[0], tot[1], tot[2])
            # plastico: el pico se juzga por la deformacion plastica del cordon (la redistribucion ya esta en el modelo);
            # la rotura del metal base se exige con la fuerza MEDIA de la pared (ver ra mas abajo)
            rat = rw if (plas and cap > 0) else max(rw, rb)
            f = math.sqrt(fn * fn + fl * fl + ft * ft)
            Z.samples.append((r["x"], r["y"], f, rat))
            if rat >= Z.ratio and (f > 1e-9 or rat > 0):
                Z.fmax, Z.fn, Z.fl, Z.ft = f, fn, fl, ft
                Z.x, Z.y, Z.ratio = r["x"], r["y"], rat
                Z.cap = cap if plas else ((f / rat) if rat > 1e-12 else cap)
                Z.note = (f"{spec.wtype}: φ·0.60·FEXX·garganta" + (f"·kd, kd = {kd:.2f}" if kd > 1.0 else "")
                          + (f"·β, β = {beta_r:.2f} (cordon largo)" if beta_r < 0.999 else "")
                          if (rw >= rb or (plas and cap > 0)) else "gobierna la rotura del metal base de la pared")
        # ---- resultantes y medias por zona dentro de la linea
        byz = {}
        for r in lst:
            byz.setdefault(r["zone"], []).append(r)
        for zname, rl in byz.items():
            Z = zone_of(zname, spec, t)
            wsum = sum(r["w"] for r in rl)
            Fn = sum(r["fn"] * r["w"] for r in rl)
            Fl = sum(r["fl"] * r["w"] for r in rl)
            Ft = sum(r["ft"] * r["w"] for r in rl)
            Z.Fn += Fn; Z.Fl += Fl; Z.Ft += Ft
            Z.L += sum(r["w"] for r in rl if r["on"])
            Fn_tot += Fn
            if wsum <= 0 or not any(r["on"] for r in rl):
                continue
            fnm, flm, ftm = Fn / wsum, Fl / wsum, Ft / wsum
            capm, rwm, _ = _cap_line(prj, spec, fnm, flm, ftm, rl[0].get("beta", 1.0))
            fm = math.sqrt(max(fnm, 0.0) ** 2 + flm * flm + ftm * ftm)
            # metal base con la media de todas las lineas de la pared
            tots = np.array([fnm, flm, ftm])
            for og in others:
                lo = [q for q in smoothed[og][0] if q["zone"] == zname] or smoothed[og][0]
                w2 = sum(q["w"] for q in lo)
                if w2 > 0:
                    tots = tots + np.array([sum(q["fn"] * q["w"] for q in lo) / w2,
                                            sum(q["fl"] * q["w"] for q in lo) / w2,
                                            sum(q["ft"] * q["w"] for q in lo) / w2])
            rbm = _wall_ratio(prj, spec, key, t, tots[0], tots[1], tots[2])
            ra = max(rwm, rbm)
            if ra >= Z.ratio_avg:
                Z.ratio_avg, Z.f_avg = ra, fm
    for Z in zones.values():
        if Z.fmax <= 1e-12 and not Z.note:
            Z.note = "sin cordon en esta zona: la compresion pasa por contacto"
    A_b = sum(a for (_, _, a) in conn["bearing"])
    return list(zones.values()), dict(F_bear=F_bear, p_bear=(F_bear / A_b if A_b > 0 else 0.0), F_weld_n=Fn_tot)
