# -*- coding: utf-8 -*-
"""Modelo 3D de una conexion: piezas, pernos, soldaduras, apoyos y cargas.

Cada tipologia arma un `Model3D` (conn/fem/builders.py) que sirve para tres cosas: la vista 3D, la malla de Gmsh y el .inp de
CalculiX.  Unidades in, kip, ksi.  Sistema global: x a lo largo de la viga (desde el soporte), y transversal en el plano
horizontal, z hacia arriba.

Una pieza es la UNION de prismas (poligono extruido); asi un cope, un recorte RBS o un perfil I son simples listas de cajas
y no hace falta restar volumenes.  Los agujeros de los pernos se restan solos al mallar.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

import numpy as np

COLORS = {"beam": "#9dc3e6", "column": "#bdd7ee", "support": "#c9c9c9", "plate": "#f4b183", "angle": "#f8cbad",
          "stiff": "#a9d18e", "gusset": "#ffd966", "brace": "#8faadc", "hss": "#9dc3e6", "weld": "#c00000",
          "bolt": "#1f3864", "other": "#d9d9d9"}
KIND_NAMES = {"beam": "Viga", "column": "Columna", "support": "Soporte", "plate": "Placas", "angle": "Angulos", "stiff": "Rigidizadores",
              "gusset": "Cartela", "brace": "Arriostramiento", "hss": "Perfiles HSS", "weld": "Soldaduras", "other": "Otras"}


# ---------------------------------------------------------------------------------------------- geometria basica
def unit(v):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


@dataclass
class Prism:
    """Poligono (u, v) extruido de w0 a w1 en el sistema local (o; U, V, W = U×V).  `circle=(ro, ri)`: cilindro o tubo de eje W."""
    poly: list = field(default_factory=list)
    o: tuple = (0.0, 0.0, 0.0)
    U: tuple = (1.0, 0.0, 0.0)
    V: tuple = (0.0, 1.0, 0.0)
    w0: float = 0.0
    w1: float = 1.0
    circle: tuple = None
    holes: list = field(default_factory=list)         # solo para tubos poligonales (mismo numero de vertices que el exterior)

    @property
    def W(self):
        return tuple(np.cross(self.U, self.V))

    def to_global(self, u, v, w):
        o, U, V, W = (np.asarray(x, float) for x in (self.o, self.U, self.V, self.W))
        return o + u * U + v * V + w * W

    def corners(self):
        """Vertices globales de las dos tapas (para el encuadre y la caja)."""
        pts = []
        if self.circle is not None:
            ro = self.circle[0]
            for w in (self.w0, self.w1):
                for a in range(0, 360, 30):
                    pts.append(self.to_global(ro * math.cos(math.radians(a)), ro * math.sin(math.radians(a)), w))
        else:
            for w in (self.w0, self.w1):
                for (u, v) in self.poly:
                    pts.append(self.to_global(u, v, w))
        return np.array(pts)

    def faces(self, nseg: int = 36):
        """Caras (poligonos 3D) para dibujar."""
        out = []
        if self.circle is not None:
            ro, ri = self.circle
            ang = [2 * math.pi * k / nseg for k in range(nseg)]
            ring = lambda r, w: [self.to_global(r * math.cos(a), r * math.sin(a), w) for a in ang]
            outs = [ring(ro, self.w0), ring(ro, self.w1)]
            for k in range(nseg):
                k2 = (k + 1) % nseg
                out.append([outs[0][k], outs[0][k2], outs[1][k2], outs[1][k]])
            if ri > 0:
                ins = [ring(ri, self.w0), ring(ri, self.w1)]
                for k in range(nseg):
                    k2 = (k + 1) % nseg
                    out.append([ins[0][k], ins[0][k2], ins[1][k2], ins[1][k]])
                for w, o_, i_ in ((0, outs[0], ins[0]), (1, outs[1], ins[1])):
                    for k in range(nseg):
                        k2 = (k + 1) % nseg
                        out.append([o_[k], o_[k2], i_[k2], i_[k]])
            else:
                out.append(outs[0])
                out.append(outs[1])
            return out
        P0 = [self.to_global(u, v, self.w0) for (u, v) in self.poly]
        P1 = [self.to_global(u, v, self.w1) for (u, v) in self.poly]
        n = len(P0)
        for k in range(n):
            k2 = (k + 1) % n
            out.append([P0[k], P0[k2], P1[k2], P1[k]])
        if self.holes and len(self.holes[0]) == n:
            H0 = [self.to_global(u, v, self.w0) for (u, v) in self.holes[0]]
            H1 = [self.to_global(u, v, self.w1) for (u, v) in self.holes[0]]
            for k in range(n):
                k2 = (k + 1) % n
                out.append([H0[k], H0[k2], H1[k2], H1[k]])
            for P, H in ((P0, H0), (P1, H1)):
                for k in range(n):
                    k2 = (k + 1) % n
                    out.append([P[k], P[k2], H[k2], H[k]])
        else:
            out.append(P0)
            out.append(P1)
        return out


def box_prism(c, size, axes=((1, 0, 0), (0, 1, 0), (0, 0, 1))):
    """Caja centrada en c con dimensiones `size` a lo largo de los ejes (e1, e2, e3) (derecha: e1×e2 = e3)."""
    e1, e2 = unit(axes[0]), unit(axes[1])
    e3 = np.cross(e1, e2)
    a, b, h = size
    return Prism(poly=[(-a / 2, -b / 2), (a / 2, -b / 2), (a / 2, b / 2), (-a / 2, b / 2)],
                 o=tuple(np.asarray(c, float) - e3 * h / 2), U=tuple(e1), V=tuple(e2), w0=0.0, w1=h)


def rect_prism(x0, x1, y0, y1, z0, z1):
    """Caja alineada con los ejes globales."""
    return Prism(poly=[(y0, z0), (y1, z0), (y1, z1), (y0, z1)], o=(0.0, 0.0, 0.0), U=(0.0, 1.0, 0.0), V=(0.0, 0.0, 1.0), w0=x0, w1=x1)


def poly_prism(poly, o, U, V, w0, w1):
    U, V = unit(U), unit(V)
    return Prism(poly=[tuple(map(float, q)) for q in poly], o=tuple(map(float, o)), U=tuple(U), V=tuple(V), w0=float(w0), w1=float(w1))


def cyl_prism(c, axis, ro, length, ri=0.0):
    """Cilindro/tubo centrado en c, de eje `axis` y largo `length`."""
    ax = unit(axis)
    ref = np.array([0.0, 0.0, 1.0]) if abs(ax[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    U = unit(np.cross(ref, ax))
    V = np.cross(ax, U)
    return Prism(o=tuple(np.asarray(c, float)), U=tuple(U), V=tuple(V), w0=-length / 2, w1=length / 2, circle=(ro, ri))


def i_section(shape):
    """Contorno de un perfil I en (u = ancho, v = peralte), centrado, sin acuerdos."""
    d, bf, tf, tw = shape.d, shape.bf, shape.tf, shape.tw
    return [(-bf / 2, -d / 2), (bf / 2, -d / 2), (bf / 2, -d / 2 + tf), (tw / 2, -d / 2 + tf), (tw / 2, d / 2 - tf), (bf / 2, d / 2 - tf),
            (bf / 2, d / 2), (-bf / 2, d / 2), (-bf / 2, d / 2 - tf), (-tw / 2, d / 2 - tf), (-tw / 2, -d / 2 + tf), (-bf / 2, -d / 2 + tf)]


def rect_tube(shape):
    """(exterior, interior) de un HSS rectangular en (u = B, v = H)."""
    H, B, t = shape.d, shape.bf, shape.tw
    return ([(-B / 2, -H / 2), (B / 2, -H / 2), (B / 2, H / 2), (-B / 2, H / 2)],
            [(-B / 2 + t, -H / 2 + t), (B / 2 - t, -H / 2 + t), (B / 2 - t, H / 2 - t), (-B / 2 + t, H / 2 - t)])


def angle_poly(leg_a, leg_b, t):
    """Angulo L en (u, v): pierna `leg_a` a lo largo de v y `leg_b` a lo largo de u, con el vertice en el origen."""
    return [(0.0, 0.0), (leg_b, 0.0), (leg_b, t), (t, t), (t, leg_a), (0.0, leg_a)]


# ---------------------------------------------------------------------------------------------- piezas y elementos
@dataclass
class Part:
    name: str
    kind: str
    label: str
    Fy: float
    Fu: float
    prisms: list
    t: float = 0.0                      # espesor de pared o de placa (0 = el menor lado de su caja)
    stub: bool = False                  # pieza larga (viga, columna, soporte): malla fina solo en la zona de la conexion
    hard: tuple = None                  # (Fy efectivo, Fu efectivo, deformacion en Fu): acero con endurecimiento en lugar de φ·Fy perfectamente plastico (RBS)
    no_peeq: bool = False               # pieza donde la plastificacion es el comportamiento buscado: no se verifica su deformacion plastica
    cuts: list = field(default_factory=list)        # prismas solidos que se restan de la pieza (p. ej. el cordon al recortar una diagonal HSS)

    def bbox(self):
        P = np.vstack([p.corners() for p in self.prisms])
        return P.min(axis=0), P.max(axis=0)

    @property
    def thickness(self):
        if self.t > 0:
            return self.t
        a, b = self.bbox()
        return float(np.min(b - a))


@dataclass
class Bolt:
    """Perno de eje paralelo a un eje global.  `grip`: [(pieza, s0, s1)] de la cabeza a la tuerca; s es la coordenada a lo largo de `axis`
    medida desde `p`.  Cabeza apoyada en la cara s = head_s de la primera pieza; tuerca en s = nut_s de la ultima."""
    tag: str
    p: tuple
    axis: tuple
    db: float
    dh: float
    rw: float
    grip: list
    head_s: float
    nut_s: float
    grade: str = "A325-N"
    planes: int = 1                     # planos de corte (1 o 2)


@dataclass
class Weld:
    """Filete entre dos piezas a lo largo del segmento p0-p1.  nA y nB: normales de las superficies de A y B apuntando hacia el rincon
    que rellena el filete (hacia el lado del cordon).  `w` = cateto (in)."""
    name: str
    A: str
    B: str
    p0: tuple
    p1: tuple
    nA: tuple
    nB: tuple
    w: float
    fexx: float = 70.0
    group: str = ""
    shift: tuple = (0.0, 0.0, 0.0)


@dataclass
class FaceSel:
    """Caras de una pieza: triangulos de la piel de la pieza cuyo centroide esta en la caja y que miran hacia `normal`."""
    part: str
    box: tuple                          # (x0, x1, y0, y1, z0, z1)
    normal: tuple = None


@dataclass
class Contact:
    name: str
    slave: FaceSel
    master: FaceSel


@dataclass
class Support:
    name: str
    sel: FaceSel
    dofs: tuple = (1, 2, 3)


@dataclass
class LoadApp:
    """Carga sobre una o varias caras rigidizadas juntas (cuerpo rigido): fuerza F y momento M en el punto `ref`. `sel` puede ser una
    lista de FaceSel (p. ej. los extremos de dos placas de un arriostramiento)."""
    name: str
    sel: object
    ref: tuple
    F: tuple = (0.0, 0.0, 0.0)
    M: tuple = (0.0, 0.0, 0.0)
    fix_ref: tuple = ()                  # grados de libertad (1-3) de la traslacion del cuerpo rigido que quedan fijos
    fix_rot: tuple = ()                  # ... y de su giro
    show: tuple = None                   # punto donde se dibujan las flechas (por defecto `ref`)


@dataclass
class Model3D:
    name: str
    parts: list = field(default_factory=list)
    bolts: list = field(default_factory=list)
    welds: list = field(default_factory=list)
    contacts: list = field(default_factory=list)
    supports: list = field(default_factory=list)
    loads: list = field(default_factory=list)
    zone: tuple = None                  # caja de la zona de la conexion (refinada): (x0, x1, y0, y1, z0, z1)
    bonded: list = field(default_factory=list)       # pares (pieza A, pieza B) soldados con penetracion completa o continuos: nodos compartidos
    notes: list = field(default_factory=list)
    dims: list = field(default_factory=list)      # cotas para el visor: (a, b, desplazamiento, texto, vistas)

    def part(self, name):
        return next((p for p in self.parts if p.name == name), None)

    def bounds(self):
        mn, mx = [], []
        for p in self.parts:
            a, b = p.bbox()
            mn.append(a)
            mx.append(b)
        return np.min(mn, axis=0), np.max(mx, axis=0)

    def bolt_hole_prisms(self, part_name):
        """[(centro, eje, diametro del agujero, largo)] de los agujeros de pernos de una pieza."""
        out = []
        for b in self.bolts:
            for (pn, s0, s1) in b.grip:
                if pn == part_name:
                    ax = unit(b.axis)
                    c = np.asarray(b.p, float) + ax * 0.5 * (s0 + s1)
                    out.append((tuple(c), tuple(ax), b.dh, (s1 - s0) + 0.0))
        return out


def weld_prism(w: Weld) -> Prism:
    """Prisma triangular del filete: vertice en el rincon, un cateto sobre cada superficie.  nA y nB deben ser perpendiculares."""
    p0, p1 = np.asarray(w.p0, float), np.asarray(w.p1, float)
    axis = unit(p1 - p0)
    U, V = unit(w.nA), unit(w.nB)                     # cateto sobre B: a lo largo de nA; cateto sobre A: a lo largo de nB
    sgn = 1.0 if float(np.dot(np.cross(U, V), axis)) > 0 else -1.0
    return Prism(poly=[(0.0, 0.0), (w.w, 0.0), (0.0, w.w)], o=tuple(p0 if sgn > 0 else p1), U=tuple(U), V=tuple(V), w0=0.0,
                 w1=float(np.linalg.norm(p1 - p0)))


# ---------------------------------------------------------------------------------------------- serializacion (proceso hijo del mallador)
def model_to_dict(m: Model3D) -> dict:
    from dataclasses import asdict

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        return o
    return clean(asdict(m))


def model_from_dict(d: dict) -> Model3D:
    def prism(x):
        x = dict(x)
        x["poly"] = [tuple(q) for q in x.get("poly", [])]
        x["holes"] = [[tuple(q) for q in h] for h in x.get("holes", [])]
        for k in ("o", "U", "V"):
            x[k] = tuple(x[k])
        if x.get("circle") is not None:
            x["circle"] = tuple(x["circle"])
        return Prism(**x)

    def sel(x):
        return FaceSel(x["part"], tuple(x["box"]), tuple(x["normal"]) if x.get("normal") is not None else None)
    m = Model3D(d["name"])
    for p in d["parts"]:
        m.parts.append(Part(p["name"], p["kind"], p["label"], p["Fy"], p["Fu"], [prism(q) for q in p["prisms"]], p.get("t", 0.0), p.get("stub", False), tuple(p["hard"]) if p.get("hard") else None, p.get("no_peeq", False), [prism(q) for q in p.get("cuts", [])]))
    for b in d["bolts"]:
        b = dict(b)
        b["p"], b["axis"] = tuple(b["p"]), tuple(b["axis"])
        b["grip"] = [tuple(g) for g in b["grip"]]
        m.bolts.append(Bolt(**b))
    for w in d["welds"]:
        w = dict(w)
        for k in ("p0", "p1", "nA", "nB", "shift"):
            w[k] = tuple(w[k])
        m.welds.append(Weld(**w))
    for c in d["contacts"]:
        m.contacts.append(Contact(c["name"], sel(c["slave"]), sel(c["master"])))
    for s_ in d["supports"]:
        m.supports.append(Support(s_["name"], sel(s_["sel"]), tuple(s_["dofs"])))
    for l_ in d["loads"]:
        sl = [sel(x) for x in l_["sel"]] if isinstance(l_["sel"], list) else sel(l_["sel"])
        m.loads.append(LoadApp(l_["name"], sl, tuple(l_["ref"]), tuple(l_["F"]), tuple(l_["M"]), tuple(l_.get("fix_ref", ())), tuple(l_.get("fix_rot", ())), tuple(l_["show"]) if l_.get("show") else None))
    m.bonded = [tuple(b) for b in d.get("bonded", [])]
    m.zone = tuple(d["zone"]) if d.get("zone") else None
    m.notes = list(d.get("notes", []))
    m.dims = list(d.get("dims", []))
    return m
