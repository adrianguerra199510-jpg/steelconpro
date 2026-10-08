# -*- coding: utf-8 -*-
"""Modelo de datos.  Unidades internas: in, kip, ksi."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json

from . import materials as M
from .shapes import CATALOG, Shape, W_SHAPE, GENERIC_KINDS, rect_props
import dataclasses

# --------------------------------------------------------------- catalogos
U_TYPES = ["Opcion A — barras U (patas rectas, ld)", "Opcion B — barras Omega (patas con gancho, ldh)"]
WELD_CRITERIA = ["Plastico 5 % (Ghimire et al. 2023)",
                 "Elastico (pico limitado y media)"]
WELD_MODELS = ["Conectores (cordon como resortes entre cuerpos separados)",
               "Fusionado (union monolitica, equivale a CJP)"]
FIXITY = ["Doble empotramiento (placa restringida)", "Voladizo (placa libre de girar)"]
# barras de refuerzo ASTM A615 (diametro in, area in2)
REBAR = {"#3": (0.375, 0.11), "#4": (0.500, 0.20), "#5": (0.625, 0.31), "#6": (0.750, 0.44),
         "#7": (0.875, 0.60), "#8": (1.000, 0.79), "#9": (1.128, 1.00), "#10": (1.270, 1.27)}
MESH3D_MODES = ["Automatica (recomendada)", "Fina (mas lenta)"]
PATTERNS = ["Perimetral (4 lados)", "2 lados (eje mayor)",
            "2 lados (eje menor)", "Circular", "Coordenadas manuales"]
INSTALL_TYPES = ["Preinstalado (vaciado en sitio)", "Postinstalado adhesivo (epoxico)"]
ADH_ENV = ["Interior, concreto seco (Tabla 17.6.5.2.5)",
           "Exterior, seco a saturado (Tabla 17.6.5.2.5)",
           "Datos del producto (ESR / ICC-ES)"]
ADH_CATEGORY = ["Categoria 1", "Categoria 2", "Categoria 3"]
ANCHOR_TYPES = ["Con cabeza (hex pesada)", "Gancho en L", "Gancho en J", "Recto (sin cabeza)"]
WELD_TYPES = ["Filete", "CJP (penetracion completa)", "PJP (penetracion parcial)", "Sin soldadura"]
PLATE_SHAPES = ["Rectangular", "Circular"]
LUG_DIRS = ["Eje X (paralelo a B)", "Eje Y (paralelo a N)", "Ambos ejes"]
LUG_TYPES = ["Placa", "Perfil (cualquier seccion)"]
STIFF_SHAPES = ["Rectangular", "Triangular", "Rectangular con esquina recortada"]
STIFF_SPACING = ["Automatico (repartido)", "Separacion fija", "Alineado con los pernos"]
STIFF_POSITIONS = ["Alas (paralelo a Y)", "Alma (paralelo a X)", "Ambos",
                   "Perimetro HSS (4 caras)"]


@dataclass
class Section:
    label: str = "W14X90"
    steel: str = "ASTM A992"
    rotation: float = 0.0        # grados; 0 = eje fuerte paralelo a N(Y)
    double: bool = False         # seccion doble espalda con espalda
    cx: float = 0.0              # desplazamiento del centro de la columna respecto al centro de la placa, direccion X
    cy: float = 0.0              # idem, direccion Y
    gap: float = 0.375           # separacion entre las dos piezas, in

    def shape(self) -> Shape:
        s = CATALOG.get(self.label)
        return s if s else CATALOG.get("W14X90")

    @property
    def can_double(self) -> bool:
        return not self.shape().is_round

    @property
    def is_double(self) -> bool:
        return self.double and self.can_double

    @property
    def generic(self) -> bool:
        """Se calcula como grupo de soldadura generico (sin la logica ala/alma)."""
        return self.shape().kind in GENERIC_KINDS or self.is_double

    def local_rects(self):
        """Rectangulos de la seccion sin rotar, ya con la pieza doble si aplica."""
        s = self.shape()
        r = s.rects()
        if r is None or not self.is_double:
            return r
        xmin = min(a for a, b, c, e in r)
        dx = self.gap / 2.0 - xmin
        right = [(a + dx, b, c + dx, e) for a, b, c, e in r]
        left = [(-c, b, -a, e) for a, b, c, e in right]
        return right + left

    def eff(self) -> Shape:
        """Propiedades de diseno de la seccion completa (doble si aplica)."""
        s = self.shape()
        if not self.is_double:
            return s
        pr = rect_props(self.local_rects())
        return dataclasses.replace(
            s, label=f"2{s.label}", A=2 * s.A, Ix=2 * s.Ix, Sx=2 * s.Sx, Zx=2 * s.Zx,
            Iy=pr["Iy"], Sy=pr["Sy"], Zy=pr["Zy"], bf=2 * s.bf + self.gap,
            aw=2 * s.Aw)

    def describe(self, u=None, short=False) -> str:
        if not self.is_double:
            return self.label
        g = u.q("L", self.gap) if u else f"{self.gap:g} in"
        if short:
            return f"2{self.label} (s = {g})"
        return f"2{self.label} espalda con espalda, separacion {g}"

    def mat(self) -> M.Steel:
        return M.find(M.SHAPE_STEELS, self.steel)


@dataclass
class Plate:
    shape: str = "Rectangular"
    N: float = 22.0              # largo, direccion Y (eje fuerte del perfil si rot=0)
    B: float = 22.0              # ancho, direccion X
    Dp: float = 26.0             # diametro si circular
    tp: float = 2.0
    steel: str = "ASTM A572 Gr.50"
    grout: float = 1.5           # espesor de mortero de nivelacion

    def mat(self) -> M.Steel:
        return M.find(M.PLATE_STEELS, self.steel, 1)

    @property
    def Nc(self) -> float:
        return self.Dp * 0.8862 if self.shape == "Circular" else self.N

    @property
    def Bc(self) -> float:
        return self.Dp * 0.8862 if self.shape == "Circular" else self.B

    @property
    def area(self) -> float:
        import math
        return math.pi * self.Dp ** 2 / 4 if self.shape == "Circular" else self.N * self.B


@dataclass
class BoltGroup:
    size: str = "1-1/4"
    steel: str = "ASTM F1554 Gr.55"
    atype: str = "Con cabeza (hex pesada)"
    pattern: str = "Perimetral (4 lados)"
    n_major: int = 3             # pernos por fila en el eje MAYOR (a lo largo de X)
    n_minor: int = 3             # pernos por fila en el eje MENOR (a lo largo de Y)
    n_circ: int = 8              # pernos en patron circular
    ex: float = 2.5              # distancia al borde en X
    ey: float = 2.5              # distancia al borde en Y
    hef: float = 24.0            # embebido efectivo
    eh: float = 0.0              # longitud del gancho (L/J); 0 = 3*db
    Abrg_user: float = 0.0       # 0 = calculado de la cabeza hex
    washer_d: float = 0.0        # diametro de la arandela / zona de apoyo de la tuerca, in (0 = automatico)
    washer_t: float = -1.0       # espesor de la arandela, in (-1 = automatico 0.25·db; 0 = sin arandela)
    hole_rule: str = "AISC Tabla 14-2 (maximo recomendado)"
    standoff: float = 0.0        # separacion libre placa-concreto (tuercas de nivelacion), in; 0 = sin flexion
    fixity: str = "Doble empotramiento (placa restringida)"   # ver FIXITY
    # --- instalacion (solo varilla recta)
    install: str = "Preinstalado (vaciado en sitio)"
    adh_env: str = "Interior, concreto seco (Tabla 17.6.5.2.5)"
    tau_cr: float = 0.300        # ksi, adherencia caracteristica en concreto fisurado
    tau_uncr: float = 1.000      # ksi, en concreto no fisurado
    adh_cat: str = "Categoria 1"
    sustained: float = 0.0       # fraccion de la traccion que es sostenida (0-1)
    # --- coordenadas manuales (x, y) en in, respecto al centro de la placa
    coords: list = field(default_factory=lambda: [
        [-8.5, -8.5], [8.5, -8.5], [8.5, 8.5], [-8.5, 8.5]])

    @property
    def adhesive(self) -> bool:
        return (self.atype.startswith("Recto")
                and self.install.startswith("Postinstalado"))

    def bond_stress(self):
        """(tau_cr, tau_uncr) en ksi, ya con los factores de la Tabla 17.6.5.2.5."""
        if self.adh_env.startswith("Interior"):
            return 0.300, 1.000
        if self.adh_env.startswith("Exterior"):
            return 0.200, 0.650
        return self.tau_cr, self.tau_uncr

    def geom(self) -> M.BoltGeom:
        return M.bolt_geom(self.size, self.hole_rule)

    def mat(self) -> M.AnchorSteel:
        return M.find(M.ANCHOR_STEELS, self.steel, 1)

    @property
    def n_total(self) -> int:
        if self.pattern.startswith("Coordenadas"):
            return max(1, len(self.coords))
        if self.pattern == "Circular":
            return max(3, self.n_circ)
        if self.pattern.startswith("Perimetral"):
            return 2 * self.n_major + 2 * self.n_minor - 4
        if "mayor" in self.pattern:
            return 2 * self.n_major
        return 2 * self.n_minor


@dataclass
class ShearLug:
    enabled: bool = False
    ltype: str = "Placa"          # "Placa" o "Perfil"
    label: str = "W8X31"          # perfil de la llave si ltype = "Perfil"
    rotation: float = 0.0         # giro del perfil de la llave, grados
    direction: str = "Eje X (paralelo a B)"
    W: float = 10.0              # ancho de la llave (perpendicular a V)
    H: float = 6.0               # altura total (desde la cara inferior de la placa)
    t: float = 1.25              # espesor
    steel: str = "ASTM A572 Gr.50"
    weld_size: float = 0.375     # filete a cada lado
    electrode: str = "E70XX"

    def mat(self) -> M.Steel:
        return M.find(M.PLATE_STEELS, self.steel, 1)

    @property
    def is_section(self) -> bool:
        return self.ltype.startswith("Perfil")

    def shape(self) -> Shape:
        return CATALOG.get(self.label) or CATALOG.get("W8X31")


@dataclass
class Stiffener:
    enabled: bool = False
    position: str = "Alas (paralelo a Y)"
    count: int = 4               # cantidad total de pletinas
    L: float = 3.5               # proyeccion horizontal desde la cara del perfil
    h: float = 8.0               # altura sobre la placa
    t: float = 0.625
    steel: str = "ASTM A572 Gr.50"
    weld_size: float = 0.500
    electrode: str = "E70XX"
    # --- ubicacion
    spacing_mode: str = "Automatico (repartido)"
    spacing: float = 6.0         # separacion centro a centro (modo fijo)
    offset: float = 0.0          # corrimiento del grupo a lo largo de la cara
    offset_angle: float = 0.0    # columna circular: angulo de la primera pletina radial, grados
    # --- forma
    shape: str = "Rectangular"
    clip_h: float = 1.5          # recorte horizontal de la esquina exterior
    clip_v: float = 1.5          # recorte vertical de la esquina exterior
    clip_root: float = 0.75      # destaje en el vertice placa-columna

    def mat(self) -> M.Steel:
        return M.find(M.PLATE_STEELS, self.steel, 1)

    def outline(self):
        """Perfil de la pletina en su plano local: x = proyeccion desde la
        cara del perfil, y = altura sobre la placa."""
        L, h = self.L, self.h
        c = max(0.0, min(self.clip_root, 0.45 * min(L, h)))
        if self.shape.startswith("Triangular"):
            pts = [(c, 0.0), (L, 0.0), (0.0, h), (0.0, c)]
        elif self.shape.startswith("Rectangular con"):
            ch = max(0.0, min(self.clip_h, 0.9 * L))
            cv = max(0.0, min(self.clip_v, 0.9 * h))
            pts = [(c, 0.0), (L, 0.0), (L, h - cv), (L - ch, h), (0.0, h), (0.0, c)]
        else:
            pts = [(c, 0.0), (L, 0.0), (L, h), (0.0, h), (0.0, c)]
        return pts + [pts[0]]

    def depth_at(self, x: float) -> float:
        """Peralte disponible de la pletina a una distancia x de la cara
        del perfil (para la seccion critica de las mensulas triangulares)."""
        L, h = max(self.L, 1e-9), self.h
        if self.shape.startswith("Triangular"):
            return max(0.0, h * (1.0 - x / L))
        if self.shape.startswith("Rectangular con"):
            ch = max(0.0, min(self.clip_h, 0.9 * L))
            cv = max(0.0, min(self.clip_v, 0.9 * h))
            if x > L - ch and ch > 0:
                return max(0.0, h - cv * (x - (L - ch)) / ch)
        return h

    @property
    def weld_len_plate(self) -> float:
        return max(0.0, self.L - self.clip_root)

    @property
    def weld_len_col(self) -> float:
        return max(0.0, self.h - self.clip_root)

    @property
    def free_edge(self) -> float:
        """Longitud del borde libre (para la esbeltez del elemento saliente)."""
        import math as _m
        if self.shape.startswith("Triangular"):
            return _m.hypot(self.L, self.h)
        return self.h


@dataclass
class WeldSpec:
    wtype: str = "Filete"
    size: float = 0.375          # cateto del filete o garganta del PJP
    electrode: str = "E70XX"
    both_sides: bool = True

    def FEXX(self) -> float:
        return M.find(M.ELECTRODES, self.electrode, 1).FEXX


@dataclass
class Welds:
    flange: WeldSpec = field(default_factory=lambda: WeldSpec("Filete", 0.500, "E70XX", True))
    web: WeldSpec = field(default_factory=lambda: WeldSpec("Filete", 0.3125, "E70XX", True))
    perimeter: WeldSpec = field(default_factory=lambda: WeldSpec("Filete", 0.375, "E70XX", False))
    directional: bool = True     # usar incremento direccional AISC J2-5


@dataclass
class Concrete:
    material: str = "(personalizado)"
    fc: float = 4.0              # ksi
    N2: float = 40.0             # pedestal, direccion Y
    B2: float = 40.0             # pedestal, direccion X
    ha: float = 48.0             # altura del elemento de concreto
    cracked: bool = True
    lam: float = 1.0             # lambda_a
    cond_A: bool = False         # refuerzo suplementario (ACI T.17.5.3)
    seismic: bool = False        # aplica 0.75 de ACI 17.10
    # barras U que refuerzan el arrancamiento (ACI 17.5.2): se usan en lugar del concreto si resisten mas
    u_on: bool = False
    u_type: str = "Opcion A — barras U (patas rectas, ld)"      # ver U_TYPES
    u_size: str = "#4"
    u_n: int = 2                 # numero de barras U (cada una aporta 2 patas)
    u_fy: float = 60.0           # ksi
    u_depth: float = 2.0         # profundidad del tramo horizontal bajo la superficie, in
    u_leg: float = 0.0           # longitud de la pata, in (0 = automatica: la que desarrolla ld (U) o ldh (Omega) bajo el cono)

    @property
    def cond_A_eff(self) -> bool:
        """Condicion A (ACI T.17.5.3): se activa sola cuando hay barras U de refuerzo del anclaje."""
        return bool(self.u_on)


@dataclass
class Loads:
    Pu: float = 400.0            # kip, compresion positiva
    Mux: float = 1800.0          # kip*in, flexion alrededor del eje fuerte -> traccion en +Y
    Muy: float = 0.0             # kip*in, alrededor del eje debil
    Vux: float = 30.0            # kip
    Vuy: float = 0.0             # kip
    friction: bool = False       # considerar friccion placa-mortero (mu=0.4/0.55)
    mu_fric: float = 0.40
    # Inclinacion de la columna respecto a la normal de la placa (0 = perpendicular).
    # Las cargas de arriba se ingresan en el eje de la columna (axial / transversal).
    tilt_x: float = 0.0          # grados, giro alrededor de X (inclina la columna hacia Y)
    tilt_y: float = 0.0          # grados, giro alrededor de Y (inclina la columna hacia X)
    Tz: float = 0.0              # kip*in, torsion resultante en ejes de la placa (informativo)

    @property
    def tilted(self) -> bool:
        return abs(self.tilt_x) > 1e-9 or abs(self.tilt_y) > 1e-9

    def eff(self) -> "Loads":
        """Cargas proyectadas a los ejes de la placa (X, Y en el plano; Z normal).
        Fuerza y momento se rotan como vectores: R = Ry(tilt_y)·Rx(tilt_x)."""
        if not self.tilted:
            return self
        import math
        cx, sx = math.cos(math.radians(self.tilt_x)), math.sin(math.radians(self.tilt_x))
        cy, sy = math.cos(math.radians(self.tilt_y)), math.sin(math.radians(self.tilt_y))
        R = [[cy, sy * sx, sy * cx],
             [0.0, cx, -sx],
             [-sy, cy * sx, cy * cx]]
        rot = lambda v: [sum(R[i][j] * v[j] for j in range(3)) for i in range(3)]
        F = rot([self.Vux, self.Vuy, -self.Pu])
        M = rot([self.Mux, self.Muy, 0.0])
        return dataclasses.replace(self, Pu=-F[2], Vux=F[0], Vuy=F[1],
                                   Mux=M[0], Muy=M[1], Tz=M[2],
                                   tilt_x=0.0, tilt_y=0.0)

    @property
    def Vu(self) -> float:
        return (self.Vux ** 2 + self.Vuy ** 2) ** 0.5


@dataclass
class LoadCombo:
    """Una combinacion de cargas factorizadas (en ejes de la columna si esta inclinada)."""
    name: str = "Comb 1"
    Pu: float = 400.0            # kip, compresion positiva
    Mux: float = 1800.0          # kip*in
    Muy: float = 0.0             # kip*in
    Vux: float = 30.0            # kip
    Vuy: float = 0.0             # kip


@dataclass
class FEAOpts:
    """Opciones del analisis de elementos finitos SOLIDO 3D (Gmsh + CalculiX) y de sus datos comunes
    con el calculo lineal (modulo de balasto, brazo del cortante)."""
    ks_mode: str = "Ec/hped"     # o "manual"
    ks_manual: float = 1000.0    # kip/in^3
    ccx_path: str = "ccx"
    gmsh_path: str = "gmsh"
    mesh3d: float = 0.0          # tamano de malla 3D (0 = automatico)
    mesh3d_mode: str = "Automatica (recomendada)"   # ver MESH3D_MODES
    shear_arm: float = -1.0      # brazo del cortante sobre la placa, in (-1 = automatico)
    vm_avg_factor: float = 1.0   # radio de promedio del von Mises 3D, en espesores de placa
    plastic: bool = True         # acero elasto-plastico en TODAS las piezas (limite φ·Fy): sin picos de esfuerzo; se verifica la deformacion plastica
    plastic_limit: float = 5.0   # deformacion plastica equivalente maxima admitida, % (EN 1993-1-5 C.8)
    weld_peak_factor: float = 1.5   # el D/C PICO local de la soldadura (FEM) se admite hasta este valor; la media, hasta 1.0
    weld_model: str = "Conectores (cordon como resortes entre cuerpos separados)"   # ver WELD_MODELS
    weld_criterion: str = "Plastico 5 % (Ghimire et al. 2023)"   # ver WELD_CRITERIA
    weld_plastic_limit: float = 5.0     # deformacion plastica de la garganta a la que el D/C del cordon vale 1, %
    weld_mesh: float = 0.0              # tamano del elemento sobre el cordon, in (0 = automatico, ~28 mm)
    weld_long_reduction: bool = True    # reduccion por cordon largo, AISC J2.2b(d): L > 100·w (el FEM no la captura)


@dataclass
class Project:
    name: str = "Proyecto"
    element: str = "PB-01"
    author: str = ""
    date: str = ""
    metric: bool = False
    u_len: str = "mm"
    u_force: str = "kN"
    u_stress: str = "MPa"
    u_moment: str = "kN·m"

    section: Section = field(default_factory=Section)
    plate: Plate = field(default_factory=Plate)
    bolts: BoltGroup = field(default_factory=BoltGroup)
    lug: ShearLug = field(default_factory=ShearLug)
    stiff: Stiffener = field(default_factory=Stiffener)
    welds: Welds = field(default_factory=Welds)
    conc: Concrete = field(default_factory=Concrete)
    loads: Loads = field(default_factory=Loads)
    fea: FEAOpts = field(default_factory=FEAOpts)
    # combinaciones de carga: `loads` guarda la combinacion ACTIVA (la que se dibuja) mas los datos comunes
    # (inclinacion, friccion); el calculo corre todas las combinaciones
    combos: list = field(default_factory=lambda: [LoadCombo()])
    combo_idx: int = 0

    def combo_list(self) -> list:
        """Lista de combinaciones (nunca vacia)."""
        if not self.combos:
            L = self.loads
            self.combos = [LoadCombo("Comb 1", L.Pu, L.Mux, L.Muy, L.Vux, L.Vuy)]
        self.combo_idx = max(0, min(self.combo_idx, len(self.combos) - 1))
        return self.combos

    def with_combo(self, i: int) -> "Project":
        """Copia del proyecto con las cargas de la combinacion i como combinacion activa."""
        import copy
        q = copy.deepcopy(self)
        cs = q.combo_list()
        i = max(0, min(i, len(cs) - 1))
        c = cs[i]
        q.combo_idx = i
        q.loads.Pu, q.loads.Mux, q.loads.Muy, q.loads.Vux, q.loads.Vuy = c.Pu, c.Mux, c.Muy, c.Vux, c.Vuy
        return q

    def apply_combo(self, i: int):
        """Hace activa la combinacion i (copia sus cargas a `loads`)."""
        cs = self.combo_list()
        self.combo_idx = max(0, min(i, len(cs) - 1))
        c = cs[self.combo_idx]
        self.loads.Pu, self.loads.Mux, self.loads.Muy = c.Pu, c.Mux, c.Muy
        self.loads.Vux, self.loads.Vuy = c.Vux, c.Vuy

    @property
    def cloads(self) -> Loads:
        """Cargas en ejes de la placa (proyectadas si la columna esta inclinada), aplicadas EN EL EJE DE LA COLUMNA."""
        return self.loads.eff()

    @property
    def eloads(self) -> Loads:
        """Cargas en ejes de la placa, trasladadas al CENTRO de la placa (referencia del calculo cerrado y de los pernos).

        Si la columna esta descentrada (cx, cy) la fuerza axial y el cortante generan momento respecto al centro:
            Mux' = Mux − Pu·cy        (la compresion del lado +Y descarga la traccion de ese lado)
            Muy' = Muy + Pu·cx        (Muy > 0 comprime el lado +X)
            Tz'  = Tz + cx·Vuy − cy·Vux   (torsion, informativa)
        """
        L = self.loads.eff()
        cx, cy = float(self.section.cx), float(self.section.cy)
        if abs(cx) < 1e-12 and abs(cy) < 1e-12:
            return L
        return dataclasses.replace(L, Mux=L.Mux - L.Pu * cy, Muy=L.Muy + L.Pu * cx,
                                   Tz=L.Tz + cx * L.Vuy - cy * L.Vux)

    def normalize(self) -> list:
        """Aplica las restricciones entre datos. Devuelve la lista de cambios hechos.
        Columna inclinada: no se permiten rigidizadores (su geometria y las formulas
        de DG1 suponen columna perpendicular a la placa)."""
        changes = []
        if str(self.fea.weld_criterion).startswith("Plastico"):      # archivos de versiones anteriores: texto antiguo del criterio
            self.fea.weld_criterion = WELD_CRITERIA[0]
        if self.loads.tilted and self.stiff.enabled:
            self.stiff.enabled = False
            changes.append("Rigidizadores desactivados: no se permiten con la columna inclinada.")
        return changes

    # --------------------------------------------------------- unidades
    def units(self):
        from .units import UnitSet
        return UnitSet(self.u_len, self.u_force, self.u_stress, self.u_moment)

    # ------------------------------------------------------------ io
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, ensure_ascii=False)

    def sig3d(self) -> str:
        """Firma de lo que define el modelo solido 3D: cambia si cambia la geometria, las cargas, los
        materiales, las soldaduras o las opciones de malla; NO si solo cambian el nombre, el autor,
        las unidades de presentacion o el metodo de reparto de fuerzas."""
        d = asdict(self)
        for k in ("name", "element", "author", "date", "metric", "u_len", "u_force", "u_stress", "u_moment",
                  "combos", "combo_idx"):
            d.pop(k, None)
        d.get("fea", {}).pop("ccx_path", None)
        d.get("fea", {}).pop("gmsh_path", None)
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def from_json(txt: str) -> "Project":
        def mk(cls, dd):
            """Crea el dataclass ignorando claves que ya no existen (archivos de otras versiones)."""
            ok = getattr(cls, "__dataclass_fields__", {})
            return cls(**{k: v for k, v in dd.items() if k in ok})
        d = json.loads(txt)
        p = Project()
        for k, v in d.items():
            if not hasattr(p, k):
                continue
            cur = getattr(p, k)
            if hasattr(cur, "__dataclass_fields__") and isinstance(v, dict):
                if k == "welds":
                    w = Welds()
                    for wk in ("flange", "web", "perimeter"):
                        if wk in v and isinstance(v[wk], dict):
                            setattr(w, wk, mk(WeldSpec, v[wk]))
                    w.directional = v.get("directional", True)
                    setattr(p, k, w)
                else:
                    setattr(p, k, mk(type(cur), v))
            elif k == "combos" and isinstance(v, list):
                p.combos = [mk(LoadCombo, c) for c in v if isinstance(c, dict)]
            else:
                setattr(p, k, v)
        if "combos" not in d:                    # archivo de una version anterior: una sola combinacion
            p.combos = []
        p.combo_list()
        if "combos" in d:
            p.apply_combo(p.combo_idx)
        return p

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @staticmethod
    def load(path: str) -> "Project":
        with open(path, encoding="utf-8") as f:
            return Project.from_json(f.read())


# ============================================ libro: varias conexiones por archivo
def _used_extras(projects):
    """Perfiles personalizados y materiales del usuario que usan las conexiones,
    para guardarlos dentro del archivo."""
    shapes, mats = {}, {"steel": {}, "anchor": {}, "concrete": {}}
    for p in projects:
        for lab in (p.section.label, p.lug.label):
            s = CATALOG.get(lab)
            if s and s.source not in ("AISC", "integrado"):
                shapes[s.label] = asdict(s)
        for name in (p.section.steel, p.plate.steel, p.lug.steel, p.stiff.steel):
            m = next((x for x in M.PLATE_STEELS + M.SHAPE_STEELS if x.name == name), None)
            if m and m.note in ("usuario", "proyecto"):
                mats["steel"][name] = {"name": m.name, "Fy": m.Fy, "Fu": m.Fu}
        m = next((x for x in M.ANCHOR_STEELS if x.name == p.bolts.steel), None)
        if m and m.note in ("usuario", "proyecto"):
            mats["anchor"][m.name] = {"name": m.name, "Fy": m.Fy, "Fu": m.Fu,
                                      "dmax": m.dmax, "ductile": m.ductile}
        m = next((x for x in M.CONCRETES if x.name == p.conc.material), None)
        if m and m.note in ("usuario", "proyecto"):
            mats["concrete"][m.name] = {"name": m.name, "fc": m.fc, "lam": m.lam}
    return list(shapes.values()), {k: list(v.values()) for k, v in mats.items()}


def save_book(path: str, projects: list):
    shapes, mats = _used_extras(projects)
    data = {"formato": "PlacaBasePro-libro", "version": 2,
            "conexiones": [asdict(p) for p in projects],
            "perfiles": shapes, "materiales": mats}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def load_book(path: str) -> list:
    """Lee un libro (varias conexiones) o un proyecto antiguo de una sola."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict) and d.get("formato") == "PlacaBasePro-libro":
        for sd in d.get("perfiles", []):
            if not CATALOG.get(sd["label"]):
                CATALOG.shapes[sd["label"]] = Shape(**sd)
        CATALOG._reindex()
        M.register_embedded(d.get("materiales", {}))
        return [Project.from_json(json.dumps(c)) for c in d.get("conexiones", [])] \
            or [Project()]
    return [Project.from_json(json.dumps(d))]
