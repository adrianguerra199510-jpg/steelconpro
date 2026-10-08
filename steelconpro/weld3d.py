# -*- coding: utf-8 -*-
"""
Postproceso del modelo solido 3D.

1. SOLDADURA PERFIL-PLACA.  Dos modelos (opciones del proyecto, fea.weld_model):

   · CONECTORES (predeterminado, ver weldfe.py).  Perfil y placa son cuerpos separados unidos por contacto
     solo-compresion y por conectores de cordon (normal solo-traccion + cortante) en cada linea soldada; la
     fuerza del cordon se lee directo de los resortes, se suaviza en una ventana movil y se compara con AISC
     J2.4 por linea y con la rotura del metal base de la pared.

   · FUSIONADO (respaldo).  La union es monolitica (equivale a una CJP), asi que la fuerza que cruza el
     cordon se deduce de los esfuerzos del propio perfil justo por encima de la placa: para cada pared se
     promedian los esfuerzos nodales de una franja delgada por encima del pie de la soldadura y se integra
     en el espesor:

       f_n = t · σzz        (normal al plano del cordon; + traccion)
       f_l = t · τ(z,t)     (cortante longitudinal, a lo largo del cordon)
       f_t = t · τ(z,n)     (cortante transversal)

   En ambos, siguiendo la DG1, la compresion se transmite por contacto y el cordon se verifica a traccion y
   cortante:  f = raiz( max(f_n,0)² + f_l² + f_t² ), con el metodo vectorial elastico de AISC J2.4 y el limite
   del metal base (J4.2).

2. PERNOS.  Traccion de cada anclaje = reaccion en los resortes de su anillo.

3. CONCRETO.  Presion de contacto = ks · hundimiento, maxima sobre la cara
   inferior de la placa.

Unidades internas: in, kip, ksi.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import math
from pathlib import Path

from .model import Project
from .shapes import W_SHAPE, HSS_RECT
from . import geometry as G


# ============================================================== resultados
@dataclass
class WeldZone:
    name: str
    spec: str
    t: float                 # espesor de la pared
    fmax: float = 0.0        # demanda maxima, kip/in
    fn: float = 0.0          # componentes en el punto de maxima demanda
    fl: float = 0.0
    ft: float = 0.0
    x: float = 0.0
    y: float = 0.0
    cap: float = 0.0         # capacidad, kip/in
    ratio: float = 0.0
    Fn: float = 0.0          # resultantes integradas en toda la pared, kip
    Fl: float = 0.0
    Ft: float = 0.0
    samples: list = field(default_factory=list)   # (x, y, f, ratio)
    note: str = ""
    L: float = 0.0           # longitud de la pared
    f_avg: float = 0.0       # demanda media (resultante / longitud)
    ratio_avg: float = 0.0
    plastic: bool = False    # criterio plastico (conectores elasto-plasticos): el D/C pico es eps / limite
    eps: float = 0.0         # deformacion plastica maxima de la garganta (suavizada), fraccion
    beta: float = 1.0        # reduccion por cordon largo aplicada (AISC J2.2b(d))


@dataclass
class Post3D:
    zones: list = field(default_factory=list)
    bolts: list = field(default_factory=list)     # (k, x, y, T)
    p_max: float = 0.0
    R_conc: float = 0.0
    T_bolts: float = 0.0
    Fz_weld: float = 0.0     # resultante vertical en el pie del perfil
    weld_ratio: float = 0.0
    F_bear: float = 0.0          # compresion transmitida por contacto perfil-placa (modelo de conectores)
    p_bear: float = 0.0          # presion de contacto maxima perfil-placa, ksi
    weld_model: str = ""
    msg: str = ""


# ======================================================= paredes del perfil
def _walls(prj: Project):
    """Lista de (nombre, (x1,y1), (x2,y2), t, WeldSpec) en coordenadas de placa."""
    s = prj.section.shape()
    W = prj.welds
    rot = prj.section.rotation
    out = []

    def R(pts):
        return G._mv(G._rot(pts, rot), prj)

    if prj.section.generic:
        # cada rectangulo de la seccion es una pared: linea media a lo largo del
        # lado largo, espesor = lado corto.  Soldadura en todo el contorno, es
        # decir en las dos caras de cada pared.
        import copy
        spec = copy.copy(W.perimeter)
        spec.both_sides = True
        rl = prj.section.local_rects()
        n1 = len(rl) // (2 if prj.section.is_double else 1)
        for i, (a, b, c, e) in enumerate(rl):
            pieza = ("" if not prj.section.is_double else
                     (" (pieza der.)" if i < n1 else " (pieza izq.)"))
            if (c - a) >= (e - b):
                ym = (b + e) / 2
                p1, p2, t = (a, ym), (c, ym), e - b
            else:
                xm = (a + c) / 2
                p1, p2, t = (xm, b), (xm, e), c - a
            a_, b_ = R([p1, p2])
            out.append((f"Elemento {i % n1 + 1}{pieza}", a_, b_, t, spec))
        return out

    if s.kind == W_SHAPE:
        d, bf, tf, tw = s.d, s.bf, s.tf, s.tw
        yf = d / 2 - tf / 2
        for nm, sg in (("Ala +Y", 1), ("Ala −Y", -1)):
            a, b = R([(-bf / 2, sg * yf), (bf / 2, sg * yf)])
            out.append((nm, a, b, tf, W.flange))
        a, b = R([(0.0, -(d / 2 - tf)), (0.0, d / 2 - tf)])
        out.append(("Alma", a, b, tw, W.web))
        return out

    if s.kind == HSS_RECT:
        Ht, B, t = s.d, s.bf, s.tw
        xc, yc = B / 2 - t / 2, Ht / 2 - t / 2
        for nm, p1, p2 in (("Cara +Y", (-xc, yc), (xc, yc)),
                           ("Cara −Y", (-xc, -yc), (xc, -yc)),
                           ("Cara +X", (xc, -yc), (xc, yc)),
                           ("Cara −X", (-xc, -yc), (-xc, yc))):
            a, b = R([p1, p2])
            out.append((nm, a, b, t, W.perimeter))
        return out

    # redondo: 4 cuadrantes, cada uno dividido en cuerdas
    r = s.d / 2 - s.tw / 2
    n = 48
    names = ["Cuadrante +X", "Cuadrante +Y", "Cuadrante −X", "Cuadrante −Y"]
    for i in range(n):
        a0 = 2 * math.pi * i / n - math.pi / 4
        a1 = 2 * math.pi * (i + 1) / n - math.pi / 4
        q = int(((a0 + a1) / 2 + math.pi / 4) // (math.pi / 2)) % 4
        pa, pb = G._mv([(r * math.cos(a0), r * math.sin(a0)), (r * math.cos(a1), r * math.sin(a1))], prj)
        out.append((names[q], pa, pb, s.tw, W.perimeter))
    return out


def _capacity(prj: Project, spec, t: float, fn: float, fs: float, fl: float = None):
    """(capacidad por unidad de longitud, razon D/C, texto del criterio)."""
    col = prj.section.mat()
    f = math.hypot(max(fn, 0.0), fs)
    if fl is None:
        fl = fs
    if spec.wtype == "Sin soldadura":
        return 0.0, (math.inf if f > 1e-6 else 0.0), "sin soldadura declarada"
    if spec.wtype.startswith("CJP"):
        rn = max(fn, 0.0) / (0.90 * col.Fy * t)
        rv = fs / (1.00 * 0.60 * col.Fy * t)
        ratio = math.hypot(rn, rv)
        cap = f / ratio if ratio > 1e-12 else 0.90 * col.Fy * t
        return cap, ratio, "CJP: metal base, 0.90·Fy·t (normal) y 0.60·Fy·t (cortante)"
    nsides = 2 if spec.both_sides else 1
    thr = 0.707 * spec.size if spec.wtype == "Filete" else spec.size
    kd = 1.0
    if spec.wtype == "Filete" and prj.welds.directional and f > 1e-9:
        sin_th = min(1.0, math.sqrt(max(0.0, f * f - fl * fl)) / f)
        kd = 1.0 + 0.5 * sin_th ** 1.5                # AISC Ec. J2-5
    cap_w = nsides * 0.75 * 0.60 * spec.FEXX() * thr * kd
    cap_b = 0.75 * 0.60 * col.Fu * t              # rotura del metal base a traves de la pared
    cap = min(cap_w, cap_b)
    crit = (f"{spec.wtype} {nsides} lado{'s' if nsides > 1 else ''}: "
            f"φ·0.60·FEXX·garganta" + (f"·kd, kd = {kd:.2f}" if kd > 1.0 else "")
            + (" (gobierna el metal base)" if cap_b < cap_w else ""))
    return cap, (f / cap if cap > 0 else math.inf), crit


def _spec_txt(spec, u):
    if spec.wtype == "Sin soldadura":
        return "Sin soldadura"
    lado = "" if spec.wtype.startswith("CJP") else (" a 2 lados" if spec.both_sides else " a 1 lado")
    return f"{spec.wtype} {u.q('L', spec.size)}{lado}, {spec.electrode}"


# ================================================================ calculo
def _zones_fused(prj, res, meta, out, tp, u):
    """Modelo fusionado: la fuerza del cordon se deduce de los esfuerzos del perfil sobre el pie."""
    nodes, stress = res.nodes, res.stress
    # nodos del perfil cerca de la placa (una sola pasada)
    cand = [(n, x, y, z) for n, (x, y, z) in nodes.items()
            if tp + 1e-4 < z < tp + 4.0 and n in stress]
    zones = {}
    Fz_total = 0.0
    for (name, (x1, y1), (x2, y2), t, spec) in _walls(prj):
        Lw = math.hypot(x2 - x1, y2 - y1)
        if Lw < 1e-6:
            continue
        tx, ty = (x2 - x1) / Lw, (y2 - y1) / Lw
        nx, ny = -ty, tx
        wleg = spec.size if spec.wtype != "Sin soldadura" else 0.0
        z0 = tp + max(0.5 * t, 0.6 * wleg, 0.2)      # por encima del pie del cordon
        z1 = z0 + max(t, 0.45)
        band = t / 2 + 1e-3
        nbin = max(3, int(round(Lw / max(1.25 * t, 0.6))))
        ds = Lw / nbin
        sel = []
        for (n, x, y, z) in cand:
            if not (z0 <= z <= z1):
                continue
            dx, dy = x - x1, y - y1
            a = dx * tx + dy * ty
            if a < -1e-6 or a > Lw + 1e-6:
                continue
            if abs(dx * nx + dy * ny) > band:
                continue
            sel.append((min(nbin - 1, int(a / ds)), stress[n]))
        bins = [[] for _ in range(nbin)]
        for i, sv in sel:
            bins[i].append(sv)
        Z = zones.setdefault(name, WeldZone(name, _spec_txt(spec, u), t))
        for i, lst in enumerate(bins):
            if not lst:
                continue
            m = [sum(v[j] for v in lst) / len(lst) for j in range(6)]
            szz, syz, szx = m[2], m[4], m[5]
            fn = t * szz
            fl = t * (szx * tx + syz * ty)
            ft = t * (szx * nx + syz * ny)
            fs = math.hypot(fl, ft)
            f = math.hypot(max(fn, 0.0), fs)
            cap, ratio, crit = _capacity(prj, spec, t, fn, fs, fl)
            xm = x1 + (i + 0.5) * ds * tx
            ym = y1 + (i + 0.5) * ds * ty
            Z.samples.append((xm, ym, f, ratio))
            Z.Fn += fn * ds; Z.Fl += fl * ds; Z.Ft += ft * ds
            Fz_total += fn * ds
            if ratio >= Z.ratio:
                Z.fmax, Z.fn, Z.fl, Z.ft = f, fn, fl, ft
                Z.x, Z.y, Z.cap, Z.ratio = xm, ym, cap, ratio
                Z.note = crit
    # demanda media de cada zona: resultante integrada / longitud de la pared
    for (name, (x1, y1), (x2, y2), t, spec) in _walls(prj):
        if name in zones:
            zones[name].L += math.hypot(x2 - x1, y2 - y1)
            zones[name]._spec = spec
    for Z in zones.values():
        if Z.L > 0:
            fnm, flm, ftm = Z.Fn / Z.L, Z.Fl / Z.L, Z.Ft / Z.L
            Z.f_avg = math.hypot(max(fnm, 0.0), math.hypot(flm, ftm))
            _, Z.ratio_avg, _ = _capacity(prj, Z._spec, Z.t, fnm,
                                          math.hypot(flm, ftm), flm)
    out.zones = list(zones.values())
    out.Fz_weld = Fz_total
    out.weld_ratio = max((z.ratio for z in out.zones), default=0.0)



def postprocess(prj: Project, res, meta_path: str) -> Post3D:
    out = Post3D()
    u = prj.units()
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    tp = meta["tp"]
    z_wall = meta.get("z_wall", tp)           # cota donde arrancan las paredes (en el modelo de placas, tp/2)
    nodes, stress, disp, forc = res.nodes, res.stress, res.disp, res.forc

    # ------------------------------------------------------------- pernos
    pos = G.bolt_positions(prj)
    for k in range(1, len(pos) + 1):
        gs = meta.get("ring_ground", {}).get(str(k), [])
        T = -sum(forc.get(g, (0, 0, 0))[2] for g in gs)
        out.bolts.append((k, pos[k - 1][0], pos[k - 1][1], max(0.0, T)))
    out.T_bolts = sum(b[3] for b in out.bolts)

    # ----------------------------------------------------------- concreto
    out.R_conc = sum(forc.get(g, (0, 0, 0))[2] for g in meta.get("base_ground", []))
    uzmin = min((disp[n][2] for n in meta.get("base", []) if n in disp), default=0.0)
    out.p_max = meta["ks"] * max(0.0, -uzmin)

    # ----------------------------------------------------------- soldadura
    if meta.get("conn"):
        # modelo de conectores: la fuerza del cordon se lee directo de los resortes
        from . import weldfe
        out.zones, tot = weldfe.postprocess_conn(prj, res, meta["conn"], WeldZone, lambda sp: _spec_txt(sp, u))
        out.Fz_weld = tot["F_weld_n"]
        out.F_bear, out.p_bear = tot["F_bear"], tot["p_bear"]
        out.weld_model = "conectores"
        out.weld_ratio = max((z.ratio for z in out.zones), default=0.0)
    else:
        _zones_fused(prj, res, meta, out, z_wall, u)
        out.weld_model = "fusionado"

    L = prj.cloads
    out.msg = (f"Concreto {u.q('F', out.R_conc)}  −  pernos {u.q('F', out.T_bolts)}  =  "
               f"{u.q('F', out.R_conc - out.T_bolts)}  (Pu = {u.q('F', L.Pu)})")
    return out


def summary_rows(prj: Project, post: Post3D):
    """Filas de texto (ya en las unidades del usuario) para tablas y reportes."""
    u = prj.units()
    lf = f"{u.F}/{u.L}"
    welds = [["Zona", "Soldadura", f"f pico ({lf})", f"f media ({lf})",
              f"φRn ({lf})", "D/C pico", "D/C media"]]
    fr = lambda r: f"{r:.3f}" if math.isfinite(r) else "∞"
    for z in post.zones:
        welds.append([z.name, z.spec, u.fmt("LF", z.fmax), u.fmt("LF", z.f_avg),
                      (u.fmt("LF", z.cap) if z.cap > 0 else "—"),
                      fr(z.ratio), fr(z.ratio_avg)])
    bolts = [["Perno", f"x ({u.L})", f"y ({u.L})", f"T ({u.F})"]]
    for (k, x, y, T) in sorted(post.bolts, key=lambda b: -b[3]):
        bolts.append([f"P{k}", u.fmt("L", x), u.fmt("L", y), u.fmt("F", T)])
    return welds, bolts
