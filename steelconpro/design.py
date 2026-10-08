# -*- coding: utf-8 -*-
"""
Verificaciones de la placa segun AISC 360-22 y AISC Design Guide 1 (2a Ed.).
Unidades internas: in, kip, ksi.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from .model import Project
from . import materials as M
from . import geometry as G
from .explain import Recorder
from .shapes import W_SHAPE, HSS_RECT


# ==================================================================== Check
@dataclass
class Check:
    key: str
    title: str
    demand: float
    capacity: float
    unit: str
    ref: str = ""
    note: str = ""
    skip: bool = False
    steps: list = field(default_factory=list)

    KINDS = {"in": "L", "in²": "A", "kip": "F", "ksi": "S", "kip·in": "M",
             "kip/in": "LF", "-": "-", "": "-"}

    @property
    def kind(self) -> str:
        return self.KINDS.get(self.unit, "-")

    @property
    def ratio(self) -> float:
        if self.skip:
            return 0.0
        if self.capacity <= 1e-12:
            return 99.0 if self.demand > 1e-9 else 0.0
        return self.demand / self.capacity

    @property
    def ok(self) -> bool:
        return self.ratio <= 1.0 + 1e-9


@dataclass
class Bearing:
    A1: float = 0.0
    A2: float = 0.0
    sqrt_ratio: float = 1.0
    phiPp: float = 0.0
    fp_max: float = 0.0
    qmax: float = 0.0
    e: float = 0.0
    ecrit: float = 0.0
    case: str = ""
    Y: float = 0.0
    fp: float = 0.0
    Tu: float = 0.0
    f_arm: float = 0.0
    n_t: int = 0
    disc: float = 0.0
    feasible: bool = True


# ============================================================ A. APLASTAMIENTO
def bearing(prj: Project, rec: Recorder | None = None) -> Bearing:
    p, c, L = prj.plate, prj.conc, prj.eloads
    u = prj.units()
    r = Bearing()
    Nc, Bc = p.Nc, p.Bc
    r.A1 = Nc * Bc
    r.A2 = max(c.N2 * c.B2, r.A1)
    r.sqrt_ratio = min(2.0, math.sqrt(r.A2 / r.A1)) if r.A1 > 0 else 1.0
    r.phiPp = min(0.65 * 0.85 * c.fc * r.A1 * r.sqrt_ratio, 0.65 * 1.7 * c.fc * r.A1)
    r.fp_max = r.phiPp / r.A1 if r.A1 > 0 else 0.0
    r.qmax = r.fp_max * Bc

    _, n_t, f_arm, *_ = G.tension_group(prj)
    r.n_t, r.f_arm = n_t, f_arm

    if rec:
        rec.section("A.  APLASTAMIENTO DEL CONCRETO BAJO LA PLACA  (AISC J8)")
        if p.shape == "Circular":
            rec.text("Placa circular: se emplea el cuadrado equivalente de igual "
                     "area, Leq = Dp·√(π/4) = 0.8862·Dp.")
            rec.add("Leq", "Dp·√(π/4)", f"{rec.n('L', p.Dp)}·0.8862", Nc, "L")
        rec.add("A1", "N · B", f"{rec.n('L', Nc)} · {rec.n('L', Bc)}", r.A1, "A",
                "area de apoyo de la placa")
        rec.add("A2", "N2 · B2", f"{rec.n('L', c.N2)} · {rec.n('L', c.B2)}", r.A2, "A",
                "area del pedestal, geometricamente similar y concentrica")
        rec.add("√(A2/A1)", "min( √(A2/A1) ; 2 )",
                f"min( √({rec.n('A', r.A2)}/{rec.n('A', r.A1)}) ; 2 )",
                r.sqrt_ratio, "-", "AISC J8", "el confinamiento se limita a 2.0")
        rec.add("φc·Pp", "min( φc·0.85·f'c·A1·√(A2/A1) ; φc·1.7·f'c·A1 )",
                f"min( 0.65·0.85·{rec.n('S', c.fc)}·{rec.n('A', r.A1)}·"
                f"{r.sqrt_ratio:.3f} ; 0.65·1.7·{rec.n('S', c.fc)}·"
                f"{rec.n('A', r.A1)} )", r.phiPp, "F", "AISC Ec. J8-2")
        rec.add("fp,max", "φc·Pp / A1",
                f"{rec.n('F', r.phiPp)} / {rec.n('A', r.A1)}", r.fp_max, "S")
        rec.add("qmax", "fp,max · B",
                f"{rec.n('S', r.fp_max)} · {rec.n('L', Bc)}", r.qmax, "LF",
                "", "fuerza de aplastamiento por unidad de longitud en direccion N")
        rec.section("B.  EXCENTRICIDAD Y EQUILIBRIO  (DG1 §3.3 y §3.4)")
        rec.add("n_t", "pernos con y > 0",
                f"{n_t} de {len(G.bolt_positions(prj))} pernos", None, "-", "",
                "grupo traccionado")
        rec.add("f", "promedio de las ordenadas y del grupo traccionado", "",
                f_arm, "L", "", "brazo de la resultante de traccion al centro de la placa")

    Pu, Mu = L.Pu, abs(L.Mux)
    if rec and Pu > 1e-6:
        rec.add("e", "Mu / Pu", f"{rec.n('M', Mu)} / {rec.n('F', Pu)}",
                Mu / Pu, "L", "", "excentricidad equivalente de la carga axial")
        rec.add("ecrit", "N/2 − Pu / (2·qmax)",
                f"{rec.n('L', Nc)}/2 − {rec.n('F', Pu)} / (2·{rec.n('LF', r.qmax)})",
                Nc / 2.0 - Pu / (2 * r.qmax) if r.qmax > 0 else 0.0, "L",
                "DG1 Ec. 3.3.8", "frontera entre excentricidad pequena y grande")
    if Pu <= 1e-6:
        r.case = "TRACCION NETA"
        r.e = float("inf")
        r.Y = 0.0
        r.fp = 0.0
        r.Tu = abs(Pu) + (Mu / (2 * f_arm) if f_arm > 1e-6 else 0.0)
        if rec:
            rec.text("Pu <= 0: TRACCION NETA. No hay aplastamiento; toda la fuerza "
                     "la toman los pernos.")
            rec.add("Tu", "|Pu| + Mu/(2·f)",
                    f"{rec.n('F', abs(Pu))} + {rec.n('M', Mu)}/(2·{rec.n('L', f_arm)})",
                    r.Tu, "F")
        return r

    r.e = Mu / Pu
    r.ecrit = Nc / 2.0 - Pu / (2 * r.qmax) if r.qmax > 0 else 0.0

    if r.e <= r.ecrit:
        r.case = "CASO 1"
        r.Y = max(0.0, min(Nc, Nc - 2 * r.e))
        r.fp = Pu / (Bc * r.Y) if r.Y > 0 else 0.0
        r.Tu = 0.0
        if rec:
            rec.text(f"e = {rec.f('L', r.e)} <= ecrit = {rec.f('L', r.ecrit)}  "
                     "->  CASO 1: toda la resultante cabe dentro del nucleo "
                     "ampliado; los pernos NO trabajan a traccion.")
            rec.add("Y", "N − 2·e",
                    f"{rec.n('L', Nc)} − 2·{rec.n('L', r.e)}", r.Y, "L",
                    "DG1 Ec. 3.3.6", "longitud de aplastamiento")
            rec.add("fp", "Pu / (B·Y)",
                    f"{rec.n('F', Pu)} / ({rec.n('L', Bc)}·{rec.n('L', r.Y)})",
                    r.fp, "S")
            rec.add("Tu", "0", "", 0.0, "F", "", "sin traccion en los anclajes")
    else:
        r.case = "CASO 2"
        A = f_arm + Nc / 2.0
        r.disc = A ** 2 - 2 * Pu * (r.e + f_arm) / r.qmax
        if r.disc < 0:
            r.feasible = False
            r.Y = 0.0
            r.fp = r.fp_max
            r.Tu = 0.0
        else:
            r.Y = A - math.sqrt(r.disc)
            r.fp = r.fp_max
            r.Tu = max(0.0, r.qmax * r.Y - Pu)
        if rec:
            rec.text(f"e = {rec.f('L', r.e)} > ecrit = {rec.f('L', r.ecrit)}  "
                     "->  CASO 2: se requiere traccion en los pernos para el "
                     "equilibrio. La presion de borde se agota en fp,max y las "
                     "incognitas pasan a ser Y y Tu.")
            rec.add("Δ", "(f + N/2)² − 2·Pu·(e + f)/qmax",
                    f"({rec.n('L', f_arm)} + {rec.n('L', Nc)}/2)² − "
                    f"2·{rec.n('F', Pu)}·({rec.n('L', r.e)} + {rec.n('L', f_arm)})"
                    f"/{rec.n('LF', r.qmax)}", None, "-", "DG1 Ec. 3.4.4",
                    "Discriminante " + ("POSITIVO: existe solucion de equilibrio."
                                        if r.feasible else
                                        "NEGATIVO: la placa NO equilibra las acciones."))
            if r.feasible:
                rec.add("Y", "(f + N/2) − √Δ",
                        f"({rec.n('L', f_arm)} + {rec.n('L', Nc)}/2) − √Δ",
                        r.Y, "L", "DG1 Ec. 3.4.3")
                rec.add("fp", "fp,max", "", r.fp, "S", "",
                        "por definicion del metodo la presion de borde se agota")
                rec.add("Tu", "qmax·Y − Pu",
                        f"{rec.n('LF', r.qmax)}·{rec.n('L', r.Y)} − {rec.n('F', Pu)}",
                        r.Tu, "F", "DG1 Ec. 3.4.5",
                        "traccion TOTAL del grupo de pernos")
    return r


# ============================================================== B. ESPESOR
def plate_thickness(prj: Project, br: Bearing, rec: Recorder | None = None):
    """Devuelve (t_req, detalle dict)."""
    p = prj.plate
    u = prj.units()
    s = prj.section.shape()
    Fy = p.mat().Fy
    Nc, Bc = p.Nc, p.Bc
    bw, bh = G.profile_bbox(prj)
    cdx, cdy = G.col_shift(prj)
    Nm, Bm = Nc + 2 * abs(cdy), Bc + 2 * abs(cdx)     # columna descentrada: el voladizo del lado mas largo es (N/2 + |cy|) − media columna

    if s.is_round:
        my = (Nm - 0.80 * bh) / 2.0
        mx = (Bm - 0.80 * bw) / 2.0
        n_prime = bh / 4.0
    elif s.kind == W_SHAPE:
        my = (Nm - 0.95 * bh) / 2.0
        mx = (Bm - 0.80 * bw) / 2.0
        n_prime = math.sqrt(bw * bh) / 4.0
    else:
        my = (Nm - 0.95 * bh) / 2.0
        mx = (Bm - 0.95 * bw) / 2.0
        n_prime = math.sqrt(bw * bh) / 4.0

    # reduccion por rigidizadores
    mx_r, my_r = G.cantilever_reduction(prj)
    if prj.stiff.enabled:
        my = min(my, max(0.0, my_r))
        mx = min(mx, max(0.0, mx_r))

    X = 0.0
    if br.phiPp > 0 and prj.eloads.Pu > 0:
        X = min(1.0, (4 * bh * bw / (bh + bw) ** 2) * (prj.eloads.Pu / br.phiPp))
    lam = 1.0 if X <= 0 else min(1.0, 2 * math.sqrt(X) / (1 + math.sqrt(max(0.0, 1 - X))))
    ln = lam * n_prime

    fp = br.fp
    t_my = t_mx = t_ln = 0.0
    if fp > 0:
        if br.Y >= my:
            t_my = 1.49 * my * math.sqrt(fp / Fy)
        else:
            t_my = 2.11 * math.sqrt(max(0.0, fp * br.Y * (my - br.Y / 2)) / Fy)
        t_mx = 1.49 * mx * math.sqrt(fp / Fy)
        t_ln = 1.49 * ln * math.sqrt(fp / Fy)

    crit = (0.80 if s.is_round else 0.95) * bh / 2.0
    x_arm = max(0.0, br.f_arm - cdy - crit)       # la cara de la columna del lado traccionado esta en cy + media columna
    if prj.stiff.enabled and (prj.stiff.position.startswith("Alas") or
                              prj.stiff.position in ("Ambos",) or
                              prj.stiff.position.startswith("Perimetro")):
        x_arm = max(0.0, x_arm - prj.stiff.L)
    t_ten = 0.0
    if br.Tu > 1e-9 and x_arm > 0:
        t_ten = 2.11 * math.sqrt(br.Tu * x_arm / (Bc * Fy))

    if rec:
        rec.section("C.  ESPESOR REQUERIDO DE LA PLACA  (DG1 §3.1 y §3.3)")
        cd = "0.80·D" if s.is_round else "0.95·d"
        cb = ("0.80·D" if s.is_round else
              ("0.80·bf" if s.kind == W_SHAPE else "0.95·B"))
        rec.add("m", f"(N − {cd}) / 2",
                f"({rec.n('L', Nm)} − {0.80 if s.is_round else 0.95}·"
                f"{rec.n('L', bh)}) / 2", my, "L", "DG1 §3.1",
                "voladizo de la placa en direccion N"
                + (", reducido por los rigidizadores" if prj.stiff.enabled else ""))
        rec.add("n", f"(B − {cb}) / 2",
                f"({rec.n('L', Bm)} − "
                f"{0.80 if (s.is_round or s.kind == W_SHAPE) else 0.95}·"
                f"{rec.n('L', bw)}) / 2", mx, "L", "DG1 §3.1",
                "voladizo en direccion B")
        rec.add("X", "[4·d·bf/(d+bf)²] · (Pu/φcPp)",
                f"[4·{rec.n('L', bh)}·{rec.n('L', bw)}/"
                f"({rec.n('L', bh)}+{rec.n('L', bw)})²] · "
                f"({rec.n('F', prj.eloads.Pu)}/{rec.n('F', br.phiPp)})",
                X, "-", "DG1 Ec. 3.3.2")
        rec.add("λ", "min( 1 ; 2·√X / (1+√(1−X)) )",
                f"min( 1 ; 2·√{X:.3f} / (1+√(1−{X:.3f})) )", lam, "-",
                "DG1 Ec. 3.3.1")
        rec.add("n'", ("D/4" if s.is_round else "√(d·bf)/4"),
                f"√({rec.n('L', bh)}·{rec.n('L', bw)})/4" if not s.is_round
                else f"{rec.n('L', bh)}/4", n_prime, "L",
                "", "voladizo de la linea de fluencia interior")
        if fp > 0:
            if br.Y >= my:
                rec.add("t (dir. m)", "1.49·m·√(fp/Fy)",
                        f"1.49·{rec.n('L', my)}·√({rec.n('S', fp)}/{rec.n('S', Fy)})",
                        t_my, "L", "DG1 Ec. 3.3.14a",
                        "Y >= m: el voladizo esta cargado en toda su longitud")
            else:
                rec.add("t (dir. m)", "2.11·√[fp·Y·(m − Y/2)/Fy]",
                        f"2.11·√[{rec.n('S', fp)}·{rec.n('L', br.Y)}·"
                        f"({rec.n('L', my)} − {rec.n('L', br.Y)}/2)/{rec.n('S', Fy)}]",
                        t_my, "L", "DG1 Ec. 3.3.15a",
                        "Y < m: aplastamiento parcial del voladizo")
            rec.add("t (dir. n)", "1.49·n·√(fp/Fy)",
                    f"1.49·{rec.n('L', mx)}·√({rec.n('S', fp)}/{rec.n('S', Fy)})",
                    t_mx, "L", "DG1 Ec. 3.1.11")
            rec.add("t (λ·n')", "1.49·λ·n'·√(fp/Fy)",
                    f"1.49·{lam:.3f}·{rec.n('L', n_prime)}·"
                    f"√({rec.n('S', fp)}/{rec.n('S', Fy)})", t_ln, "L")
        if br.Tu > 1e-9:
            rec.add("x", "f − (0.95·d)/2"
                    + (" − L rigidizador" if prj.stiff.enabled else ""),
                    f"{rec.n('L', br.f_arm)} − {0.80 if s.is_round else 0.95}·"
                    f"{rec.n('L', bh)}/2"
                    + (f" − {rec.n('L', prj.stiff.L)}" if prj.stiff.enabled else ""),
                    x_arm, "L", "",
                    "brazo del voladizo del lado traccionado"
                    + (", reducido porque el rigidizador acorta el voladizo"
                       if prj.stiff.enabled else ""))
            rec.add("t (traccion)", "2.11·√[Tu·x/(B·Fy)]",
                    f"2.11·√[{rec.n('F', br.Tu)}·{rec.n('L', x_arm)}/"
                    f"({rec.n('L', Bc)}·{rec.n('S', Fy)})]", t_ten, "L",
                    "DG1 Ec. 3.3.16a")
        rec.add("t requerido", "max de los anteriores", "",
                max(t_my, t_mx, t_ln, t_ten), "L")

    treq = max(t_my, t_mx, t_ln, t_ten)
    det = dict(m_y=my, m_x=mx, n_prime=n_prime, X=X, lam=lam, lam_n=ln,
               t_my=t_my, t_mx=t_mx, t_ln=t_ln, t_ten=t_ten, x_arm=x_arm, Fy=Fy)
    return treq, det


# ============================================================== C. SOLDADURA
def _fillet_cap(w, L, FEXX, theta_deg, directional=True, both=True):
    """Resistencia de diseno de filete, kip.  theta = angulo entre la fuerza
    y el eje longitudinal de la soldadura (AISC 360 J2-5)."""
    n = 2 if both else 1
    Awe = 0.707 * w * L * n
    kd = (1.0 + 0.5 * math.sin(math.radians(theta_deg)) ** 1.5) if directional else 1.0
    return 0.75 * 0.60 * FEXX * Awe * kd


def _base_metal_cap(t, L, Fu, both=True):
    """Corte por rotura del metal base adyacente, kip (AISC J4.2)."""
    return 0.75 * 0.60 * Fu * t * L * (1 if not both else 1)


# ==================================================== grupo de soldadura generico
def weld_group(prj: Project, polys, spec, P=0.0, Mx=0.0, My=0.0, Vx=0.0, Vy=0.0,
               tmin=None, Fu=None):
    """Metodo elastico sobre el contorno exterior de la union de rectangulos.

        fz(x,y) = -P/Lw + Mx·(y-ȳ)/Ixw + My·(x-x̄)/Iyw     (+ traccion)
        fx = Vx/Lw ;  fy = Vy/Lw
        f  = raiz( max(fz,0)² + fx² + fy² )      (la compresion va por contacto)

    Devuelve dict con Lw, Ixw, Iyw, fmax, (x, y) del maximo, capacidad por
    unidad de longitud y texto del criterio."""
    pts = G.boundary_points(polys, ds=0.2)
    Lw = sum(q[2] for q in pts)
    if Lw <= 0:
        return None
    xc = sum(q[0] * q[2] for q in pts) / Lw
    yc = sum(q[1] * q[2] for q in pts) / Lw
    Ixw = sum(q[2] * (q[1] - yc) ** 2 for q in pts)
    Iyw = sum(q[2] * (q[0] - xc) ** 2 for q in pts)
    fx, fy = Vx / Lw, Vy / Lw
    best = (0.0, 0.0, 0.0, 0.0)
    for (x, y, dL, tx, ty) in pts:
        fz = -P / Lw + (Mx * (y - yc) / Ixw if Ixw > 0 else 0.0) \
            + (My * (x - xc) / Iyw if Iyw > 0 else 0.0)
        f = math.sqrt(max(fz, 0.0) ** 2 + fx ** 2 + fy ** 2)
        if f > best[0]:
            best = (f, x, y, fz)
    if spec.wtype.startswith("CJP"):
        t = tmin or 0.5
        cap = 0.90 * prj.section.mat().Fy * t
        crit = f"CJP: resistencia del metal base 0.90·Fy·t (t = {t:.3g} in)"
    else:
        thr = 0.707 * spec.size if spec.wtype == "Filete" else spec.size
        cap_w = 0.75 * 0.60 * spec.FEXX() * thr
        cap_b = 0.75 * 0.60 * (Fu or 58.0) * (tmin or 1e9)
        cap = min(cap_w, cap_b)
        crit = (f"{spec.wtype}: φ·0.60·FEXX·garganta por unidad de longitud"
                + (" (gobierna el metal base)" if cap_b < cap_w else ""))
    return dict(Lw=Lw, Ixw=Ixw, Iyw=Iyw, xc=xc, yc=yc, fmax=best[0], x=best[1],
                y=best[2], fz=best[3], fx=fx, fy=fy, cap=cap, crit=crit)


def _welds_generic(prj: Project, rec: Recorder | None):
    """Soldadura perfil-placa para angulos, canales, tes, pletinas y secciones
    dobles: grupo de soldadura en todo el contorno (especificacion 'perimetral')."""
    L = prj.cloads      # carga en el eje de la columna (sin trasladar al centro de la placa)
    u = prj.units()
    W = prj.welds.perimeter
    out: list[Check] = []
    if W.wtype == "Sin soldadura":
        return [Check("weld_grp", "Soldadura perfil-placa — sin soldadura declarada",
                      1.0, 0.0, "-", "AISC J2", "Declare la soldadura perimetral.")]
    tmin = min(min(c - a, e - b) for a, b, c, e in prj.section.local_rects())
    Fu = min(prj.section.mat().Fu, prj.plate.mat().Fu)
    g = weld_group(prj, G.section_rects(prj), W, P=L.Pu, Mx=L.Mux, My=L.Muy,
                   Vx=L.Vux, Vy=L.Vuy, tmin=tmin, Fu=Fu)
    if g is None:
        return out
    out.append(Check("weld_grp",
                     f"Soldadura perfil-placa — grupo {W.wtype} "
                     f"{M.float_to_frac(W.size)}\" en todo el contorno",
                     g["fmax"], g["cap"], "kip/in", "AISC J2.4 (metodo elastico)",
                     f"Lw = {u.q('L', g['Lw'])}; maximo en ({u.fmt('L', g['x'])}, "
                     f"{u.fmt('L', g['y'])}); fz = {u.q('LF', g['fz'])}, "
                     f"fx = {u.q('LF', g['fx'])}, fy = {u.q('LF', g['fy'])}. "
                     f"{g['crit']}. La compresion se transmite por contacto."))
    if W.wtype == "Filete":
        wmin = M.min_fillet(min(tmin, prj.plate.tp))
        out.append(Check("weld_grp_min", "Tamano minimo de filete (perimetral)",
                         wmin, W.size, "in", "AISC Tabla J2.4",
                         f"Parte mas delgada unida: {u.q('L', min(tmin, prj.plate.tp))}"))
    if rec:
        rec.add("Lw", "longitud del contorno soldado", "", g["Lw"], "L")
        rec.add("Ixw / Iyw", "momentos de inercia de la linea de soldadura",
                f"{g['Ixw']:.4g} / {g['Iyw']:.4g} in³", None, "-")
        rec.add("fz", "−Pu/Lw + Mux·y/Ixw + Muy·x/Iyw  (punto mas traccionado)", "",
                g["fz"], "LF", "AISC J2.4")
        rec.add("f", "√(max(fz,0)² + fx² + fy²)", "", g["fmax"], "LF")
        rec.check("Grupo de soldadura perfil-placa", g["fmax"], g["cap"], "LF",
                  g["fmax"] / g["cap"] if g["cap"] > 0 else 0, g["fmax"] <= g["cap"],
                  "AISC J2.4")
    return out


def unwelded_zones(prj: Project) -> list:
    """Zonas del perfil declaradas 'Sin soldadura' (contorno no soldado por completo)."""
    W = prj.welds
    if prj.section.generic:
        return ["contorno"] if W.perimeter.wtype == "Sin soldadura" else []
    s = prj.section.shape()
    if s.kind == W_SHAPE:
        return (["alas"] if W.flange.wtype == "Sin soldadura" else []) + \
               (["alma"] if W.web.wtype == "Sin soldadura" else [])
    return ["contorno"] if W.perimeter.wtype == "Sin soldadura" else []


def _welds_partial_W(prj: Project, rec: Recorder | None):
    """Perfil W con alas y/o alma sin soldar: metodo elastico sobre las lineas
    realmente soldadas.  La compresion se transmite por contacto."""
    W = prj.welds
    zones = unwelded_zones(prj)
    if not zones:
        return []
    s = prj.section.shape()
    L = prj.cloads      # carga en el eje de la columna (sin trasladar al centro de la placa)
    u = prj.units()
    d, bf, tf, tw = s.d, s.bf, s.tf, s.tw
    rot = math.radians(prj.section.rotation)
    cr, sr = math.cos(rot), math.sin(rot)
    Fu_base = min(prj.section.mat().Fu, prj.plate.mat().Fu)
    Fy = prj.section.mat().Fy

    def cap_of(spec, t):
        if spec.wtype.startswith("CJP"):
            return 0.90 * Fy * t
        thr = 0.707 * spec.size if spec.wtype == "Filete" else spec.size
        return min(0.75 * 0.60 * spec.FEXX() * thr, 0.75 * 0.60 * Fu_base * min(t, prj.plate.tp))

    pts = []
    for (x, y, dL, tx, ty) in G.boundary_points(G.section_rects(prj), ds=0.2):
        xl, yl = x * cr + y * sr, -x * sr + y * cr           # coordenadas locales
        if abs(yl) < d / 2 - tf - 1e-4:                        # alma
            if W.web.wtype == "Sin soldadura" or (not W.web.both_sides and xl < 0):
                continue
            pts.append((x, y, dL, cap_of(W.web, tw), "alma"))
        elif abs(abs(yl) - d / 2) < 1e-3 or abs(abs(yl) - (d / 2 - tf)) < 1e-3:
            if W.flange.wtype == "Sin soldadura":
                continue
            if abs(abs(yl) - (d / 2 - tf)) < 1e-3 and not W.flange.both_sides:
                continue
            pts.append((x, y, dL, cap_of(W.flange, tf), "ala"))
    Lw = sum(p[2] for p in pts)
    if Lw <= 1e-6:
        return [Check("weld_part", "Soldadura perfil-placa — no hay zonas soldadas",
                      1.0, 0.0, "-", "AISC J2", "Declare al menos una zona soldada.")]
    xc = sum(p[0] * p[2] for p in pts) / Lw
    yc = sum(p[1] * p[2] for p in pts) / Lw
    Ixw = sum(p[2] * (p[1] - yc) ** 2 for p in pts)
    Iyw = sum(p[2] * (p[0] - xc) ** 2 for p in pts)
    Vx = 0.0 if prj.lug.enabled else abs(L.Vux)
    Vy = 0.0 if prj.lug.enabled else abs(L.Vuy)
    fx, fy = Vx / Lw, Vy / Lw
    best = (-1.0, 0.0, 0.0, 0.0, 0.0, "")
    for sgn in (1.0, -1.0):          # el momento puede traccionar cualquiera de los dos lados
        for (x, y, dL, cap, zn) in pts:
            fz = -L.Pu / Lw + sgn * (abs(L.Mux) * (y - yc) / Ixw if Ixw > 1e-9 else 0.0) \
                + sgn * (abs(L.Muy) * (x - xc) / Iyw if Iyw > 1e-9 else 0.0)
            f = math.sqrt(max(fz, 0.0) ** 2 + fx ** 2 + fy ** 2)
            if f / cap > best[0]:
                best = (f / cap, f, cap, x, y, zn)
    ratio, f, cap, bx, by, zn = best
    out = [Check("weld_part",
                 "Soldadura perfil-placa — contorno PARCIAL (sin soldar: " + ", ".join(zones) + ")",
                 f, cap, "kip/in", "AISC J2.4 (metodo elastico, solo lineas soldadas)",
                 f"Lw = {u.q('L', Lw)} soldado; maximo en zona {zn} ({u.fmt('L', bx)}, "
                 f"{u.fmt('L', by)}). La compresion se transmite por contacto; traccion, "
                 f"cortante y momento solo por las zonas soldadas.")]
    if rec:
        rec.add("Zonas sin soldar", ", ".join(zones), "", None, "-", "AISC J2",
                "contorno NO soldado por completo")
        rec.add("Lw (soldado)", "longitud de las lineas soldadas", "", Lw, "L")
        rec.check("Soldadura — contorno parcial", f, cap, "LF", ratio, ratio <= 1.0, "AISC J2.4")
    return out


def welds(prj: Project, br: Bearing, rec: Recorder | None = None) -> list[Check]:
    if prj.section.generic:
        if rec:
            rec.section("F.  SOLDADURA PERFIL-PLACA  (AISC 360 Cap. J2) — grupo de soldadura")
        return _welds_generic(prj, rec)
    s = prj.section.shape()
    W = prj.welds
    L = prj.cloads      # carga en el eje de la columna (sin trasladar al centro de la placa)
    u = prj.units()
    out: list[Check] = []
    if rec:
        rec.section("F.  SOLDADURA PERFIL-PLACA  (AISC 360 Cap. J2)")
    Fu_base = min(prj.section.mat().Fu, prj.plate.mat().Fu)

    # el cortante lo toma la llave si existe
    Vx = 0.0 if prj.lug.enabled else abs(L.Vux)
    Vy = 0.0 if prj.lug.enabled else abs(L.Vuy)

    if s.kind == W_SHAPE:
        d, bf, tf, tw, A = s.d, s.bf, s.tf, s.tw, s.A
        Sx = s.Sx if s.Sx > 0 else 1e-9
        Sy = s.Sy if s.Sy > 0 else 1e-9
        # esfuerzo normal en la fibra extrema del ala (traccion positiva)
        sig = abs(L.Mux) / Sx + abs(L.Muy) / Sy - L.Pu / A
        Ff = max(0.0, sig) * bf * tf                    # traccion por ala
        Lf = 2 * bf if W.flange.both_sides else bf
        Lw = 2 * (d - 2 * tf) if W.web.both_sides else (d - 2 * tf)
        Vf = Vx / 2.0                                    # cortante X -> alas
        Rf = math.hypot(Ff, Vf)
        th_f = math.degrees(math.atan2(Ff, max(Vf, 1e-9)))

        # --- alas
        if W.flange.wtype.startswith("CJP"):
            cap = 0.90 * prj.section.mat().Fy * bf * tf
            out.append(Check("weld_fl", "Soldadura de ALA — CJP (resistencia = metal base)",
                             Rf, cap, "kip", "AISC J2.4",
                             "CJP con metal de aporte compatible: no requiere calculo del deposito."))
        elif W.flange.wtype == "Sin soldadura":
            out.append(Check("weld_fl", "Soldadura de ALA — sin soldar", Rf, 0.0, "kip", "",
                             "Alas sin soldar: la traccion y el cortante se redistribuyen "
                             "en las zonas soldadas (ver grupo parcial).", skip=True))
        else:
            thr = 0.707 * W.flange.size if W.flange.wtype == "Filete" else W.flange.size
            kd = (1 + 0.5 * math.sin(math.radians(th_f)) ** 1.5) if W.directional else 1.0
            cap = 0.75 * 0.60 * W.flange.FEXX() * thr * Lf * kd
            capb = 0.75 * 0.60 * Fu_base * min(tf, prj.plate.tp) * Lf
            out.append(Check("weld_fl", f"Soldadura de ALA — {W.flange.wtype} {M.float_to_frac(W.flange.size)}\"",
                             Rf, min(cap, capb), "kip", "AISC J2.4 / Ec. J2-5",
                             f"L = {u.q('L', Lf)}, θ = {th_f:.0f}°, deposito "
                             f"{u.q('F', cap)}, metal base {u.q('F', capb)}"))
            if rec:
                rec.add("σ fibra extrema del ala", "Mx/Sx + My/Sy − Pu/A",
                        f"{rec.n('M', abs(L.Mux))}/{rec.n('A', Sx)}·L + ... ",
                        sig, "S", "", "traccion positiva")
                rec.add("Ff", "σ · bf · tf",
                        f"{rec.n('S', max(0.0, sig))} · {rec.n('L', bf)} · "
                        f"{rec.n('L', tf)}", Ff, "F", "", "traccion por ala")
                rec.add("Rf", "√(Ff² + Vf²)",
                        f"√({rec.n('F', Ff)}² + {rec.n('F', Vf)}²)", Rf, "F")
                rec.add("garganta", ("0.707·w" if W.flange.wtype == "Filete" else "w"),
                        f"0.707·{rec.n('L', W.flange.size)}", thr, "L")
                rec.add("φRn deposito", "0.75·0.60·FEXX·garganta·L·kd",
                        f"0.75·0.60·{rec.n('S', W.flange.FEXX())}·"
                        f"{rec.n('L', thr)}·{rec.n('L', Lf)}·{kd:.3f}", cap, "F",
                        "AISC Ec. J2-4 y J2-5",
                        f"kd = 1+0.5·sin^1.5(θ) = {kd:.3f} (incremento direccional)"
                        if W.directional else "sin incremento direccional")
                rec.add("φRn metal base", "0.75·0.60·Fu·t·L",
                        f"0.75·0.60·{rec.n('S', Fu_base)}·"
                        f"{rec.n('L', min(tf, prj.plate.tp))}·{rec.n('L', Lf)}",
                        capb, "F", "AISC J4.2")
                rec.check("Soldadura de ala", Rf, min(cap, capb), "F",
                          Rf / max(min(cap, capb), 1e-9),
                          Rf <= min(cap, capb), "AISC J2.4")
            wmin = M.min_fillet(min(tf, prj.plate.tp))
            if W.flange.wtype == "Filete":
                out.append(Check("weld_fl_min", "Tamano minimo de filete en ALA",
                                 wmin, W.flange.size, "in", "AISC Tabla J2.4",
                                 f"t mas delgado = {rec.n('L', min(tf, prj.plate.tp))} "
                                 + rec.us.L))
        # --- alma
        Rw = math.hypot(Vy, max(0.0, -L.Pu) * (d - 2 * tf) * tw / A)
        if W.web.wtype.startswith("CJP"):
            out.append(Check("weld_web", "Soldadura de ALMA — CJP", Rw,
                             0.90 * prj.section.mat().Fy * (d - 2 * tf) * tw, "kip",
                             "AISC J2.4", "Resistencia = metal base."))
        elif W.web.wtype == "Sin soldadura":
            out.append(Check("weld_web", "Soldadura de ALMA — sin soldar", Rw, 0.0, "kip", "",
                             "Alma sin soldar: la demanda se redistribuye en las zonas "
                             "soldadas (ver grupo parcial).", skip=True))
        else:
            thr = 0.707 * W.web.size if W.web.wtype == "Filete" else W.web.size
            cap = 0.75 * 0.60 * W.web.FEXX() * thr * Lw
            capb = 0.75 * 0.60 * Fu_base * min(tw, prj.plate.tp) * Lw
            out.append(Check("weld_web", f"Soldadura de ALMA — {W.web.wtype} {M.float_to_frac(W.web.size)}\"",
                             Rw, min(cap, capb), "kip", "AISC J2.4",
                             f"L = {u.q('L', Lw)} (θ=0°), deposito {u.q('F', cap)}, "
                             f"metal base {u.q('F', capb)}"))
            if rec:
                rec.check("Soldadura de alma", Rw, min(cap, capb), "F",
                          Rw / max(min(cap, capb), 1e-9),
                          Rw <= min(cap, capb), "AISC J2.4")
            wmin = M.min_fillet(min(tw, prj.plate.tp))
            if W.web.wtype == "Filete":
                out.append(Check("weld_web_min", "Tamano minimo de filete en ALMA",
                                 wmin, W.web.size, "in", "AISC Tabla J2.4"))
        out += _welds_partial_W(prj, rec)
    else:
        # HSS / Pipe: soldadura perimetral
        Lp = s.perimeter_weld_len()
        Sx = s.Sx if s.Sx > 0 else 1e-9
        sig = abs(L.Mux) / Sx + abs(L.Muy) / max(s.Sy, 1e-9) - L.Pu / s.A
        Ften = max(0.0, sig) * s.A / 2.0
        Vres = math.hypot(Vx, Vy)
        R = math.hypot(Ften, Vres)
        th = math.degrees(math.atan2(Ften, max(Vres, 1e-9)))
        if W.perimeter.wtype.startswith("CJP"):
            out.append(Check("weld_per", "Soldadura PERIMETRAL — CJP", R,
                             0.90 * prj.section.mat().Fy * s.A, "kip", "AISC J2.4",
                             "Resistencia = metal base."))
        elif W.perimeter.wtype == "Sin soldadura":
            out.append(Check("weld_per", "Soldadura PERIMETRAL", R, 0.0, "kip", "",
                             "No definida", skip=(R <= 1e-9)))
        else:
            thr = 0.707 * W.perimeter.size if W.perimeter.wtype == "Filete" else W.perimeter.size
            kd = (1 + 0.5 * math.sin(math.radians(th)) ** 1.5) if W.directional else 1.0
            cap = 0.75 * 0.60 * W.perimeter.FEXX() * thr * Lp * kd
            capb = 0.75 * 0.60 * Fu_base * min(s.tw, prj.plate.tp) * Lp
            out.append(Check("weld_per",
                             f"Soldadura PERIMETRAL — {W.perimeter.wtype} {M.float_to_frac(W.perimeter.size)}\"",
                             R, min(cap, capb), "kip", "AISC J2.4 / Ec. J2-5",
                             f"L = {u.q('L', Lp)}, θ = {th:.0f}°"))
            if rec:
                rec.add("Ften", "σ·A/2",
                        f"{rec.n('S', max(0.0, sig))}·{rec.n('A', s.A)}/2", Ften, "F")
                rec.add("R", "√(Ften² + V²)", "", R, "F")
                rec.add("φRn", "0.75·0.60·FEXX·garganta·L·kd",
                        f"0.75·0.60·{rec.n('S', W.perimeter.FEXX())}·"
                        f"{rec.n('L', thr)}·{rec.n('L', Lp)}·{kd:.3f}", cap, "F",
                        "AISC Ec. J2-4")
                rec.check("Soldadura perimetral", R, min(cap, capb), "F",
                          R / max(min(cap, capb), 1e-9), R <= min(cap, capb),
                          "AISC J2.4")
            wmin = M.min_fillet(min(s.tw, prj.plate.tp))
            if W.perimeter.wtype == "Filete":
                out.append(Check("weld_per_min", "Tamano minimo de filete perimetral",
                                 wmin, W.perimeter.size, "in", "AISC Tabla J2.4"))
    return out


# ========================================================== D. LLAVE DE CORTE
def _lug_section(prj: Project, rec: Recorder | None) -> list[Check]:
    """Llave de corte hecha con un perfil (W, canal, angulo, HSS, tubo...).
    Se verifica en cada direccion de cortante con la proyeccion del perfil."""
    from .model import WeldSpec
    from .shapes import rect_props
    L, c, p, ld = prj.lug, prj.conc, prj.plate, prj.eloads
    u = prj.units()
    out: list[Check] = []
    sh = L.shape()
    Fy, Fu = L.mat().Fy, L.mat().Fu
    polys, rnd, ro, tr = G.lug_rects(prj)
    h_emb = max(0.0, L.H - p.grout)
    arm = p.grout + h_emb / 2.0
    rot90 = (int(round(L.rotation / 90.0)) % 2 == 1)
    if rnd:
        ext = {"x": 2 * ro, "y": 2 * ro}
        Z = {"x": sh.Zx, "y": sh.Zx}
        Av = {"x": sh.A / 2, "y": sh.A / 2}
        tmin = sh.tw
    else:
        rl = sh.rects()
        pr = rect_props(rl)
        Zl = {"x": sh.Zx or pr["Zx"], "y": sh.Zy or pr["Zy"]}   # ejes locales
        xs = [q[0] for P in polys for q in P]
        ys = [q[1] for P in polys for q in P]
        ext = {"x": max(xs) - min(xs), "y": max(ys) - min(ys)}
        # cortante en X global -> flexion alrededor de Y global
        Z = ({"x": Zl["x"], "y": Zl["y"]} if rot90 else {"x": Zl["y"], "y": Zl["x"]})
        if len(rl) == 1:
            Av = {"x": pr["A"], "y": pr["A"]}
        else:
            alongx = sum((c_ - a) * (e - b) for a, b, c_, e in rl if (c_ - a) >= (e - b))
            alongy = sum((c_ - a) * (e - b) for a, b, c_, e in rl if (c_ - a) < (e - b))
            Av = {"x": alongy if rot90 else alongx, "y": alongx if rot90 else alongy}
        tmin = min(min(c_ - a, e - b) for a, b, c_, e in rl)
    spec = WeldSpec(wtype="Filete", size=L.weld_size, electrode=L.electrode)
    FEXX = spec.FEXX()
    phi_c = 0.75 if c.cond_A_eff else 0.70
    psi_c = 1.0 if c.cracked else 1.4
    if rec:
        rec.add("Llave", f"perfil {sh.label}" + (" girado 90°" if rot90 else ""),
                f"h embebida = {rec.n('L', h_emb)}; brazo = {rec.n('L', arm)}", None, "-")
    for dirn, V in (("x", abs(ld.Vux)), ("y", abs(ld.Vuy))):
        if V <= 1e-9:
            continue
        D = dirn.upper()
        wperp = ext["y" if dirn == "x" else "x"]
        along = ext[dirn]
        Abrg = wperp * h_emb
        phiVbrg = 0.65 * 1.7 * c.fc * Abrg
        out.append(Check(f"lug_brg_{dirn}", f"Llave ({sh.label}) — aplastamiento, V{D}",
                         V, phiVbrg, "kip", "ACI 318-19 17.11.2.1",
                         f"Abrg = {u.q('L', wperp)} × {u.q('L', h_emb)} = {u.q('A', Abrg)}"))
        Mu = V * arm
        phiMn = 0.90 * Fy * Z[dirn]
        out.append(Check(f"lug_flex_{dirn}", f"Llave ({sh.label}) — flexion, V{D}",
                         Mu, phiMn, "kip·in", "AISC F (φMp)",
                         f"Z = {u.q('A', Z[dirn]) if False else round(Z[dirn], 3)} in³, "
                         f"Mu = V·(mortero + h/2)"))
        phiVn = 1.00 * 0.60 * Fy * max(Av[dirn], 1e-9)
        out.append(Check(f"lug_shear_{dirn}", f"Llave ({sh.label}) — cortante, V{D}",
                         V, phiVn, "kip", "AISC G",
                         f"Av = {u.q('A', Av[dirn])} (elementos paralelos al cortante)"))
        if rnd:
            Lw = 2 * math.pi * ro
            fv = V / Lw
            fb = Mu / (math.pi * ro ** 2)
            f = math.hypot(fv, fb)
            cap = 0.75 * 0.60 * FEXX * 0.707 * L.weld_size
            out.append(Check(f"lug_weld_{dirn}", f"Llave ({sh.label}) — soldadura, V{D}",
                             f, cap, "kip/in", "AISC J2.4",
                             "Filete perimetral; f = √(fv² + fb²)"))
        else:
            worst = None
            for sg in (1, -1):
                g = weld_group(prj, polys, spec,
                               Mx=(sg * Mu if dirn == "y" else 0.0),
                               My=(sg * Mu if dirn == "x" else 0.0),
                               Vx=(V if dirn == "x" else 0.0),
                               Vy=(V if dirn == "y" else 0.0), tmin=tmin, Fu=Fu)
                if g and (worst is None or g["fmax"] > worst["fmax"]):
                    worst = g
            if worst:
                out.append(Check(f"lug_weld_{dirn}",
                                 f"Llave ({sh.label}) — soldadura (grupo), V{D}",
                                 worst["fmax"], worst["cap"], "kip/in",
                                 "AISC J2.4 (metodo elastico)",
                                 f"Filete {M.float_to_frac(L.weld_size)}\" en todo el contorno, "
                                 f"Lw = {u.q('L', worst['Lw'])}"))
        ca1 = max(1.0, (c.B2 if dirn == "x" else c.N2) / 2.0 - along / 2.0)
        Avc = (wperp + 2 * 1.5 * ca1) * min(1.5 * ca1, c.ha)
        Avco = 4.5 * ca1 ** 2
        Vb = 9.0 * c.lam * math.sqrt(c.fc * 1000.0) * ca1 ** 1.5 / 1000.0
        Vcb = (Avc / Avco) * psi_c * Vb
        out.append(Check(f"lug_brkout_{dirn}",
                         f"Llave ({sh.label}) — desprendimiento del concreto, V{D}",
                         V, phi_c * Vcb, "kip", "ACI 318-19 17.11.2.2 / 17.7.2",
                         f"ca1 = {u.q('L', ca1)}, Avc/Avco = {Avc/Avco:.2f}"))
        if rec:
            rec.add(f"V{D}", "cortante en esa direccion", "", V, "F")
            rec.add("Abrg", "ancho perpendicular · h embebida",
                    f"{rec.n('L', wperp)} · {rec.n('L', h_emb)}", Abrg, "A")
            rec.add("φVbrg", "0.65·1.7·f'c·Abrg", "", phiVbrg, "F", "ACI 17.11.2.1")
            rec.add("Mu", "V·(mortero + h/2)", "", Mu, "M")
            rec.add("φMn", "0.90·Fy·Z", f"0.90·{rec.n('S', Fy)}·{Z[dirn]:.3g} in³",
                    phiMn, "M")
    if not out:
        out.append(Check("lug_none", "Llave — sin cortante que transmitir", 0.0, 1.0,
                         "-", "", "No hay Vux ni Vuy."))
    return out


def shear_lug(prj: Project, rec: Recorder | None = None) -> list[Check]:
    L, c, p = prj.lug, prj.conc, prj.plate
    u = prj.units()
    out: list[Check] = []
    if not L.enabled:
        return out
    if L.is_section:
        if rec:
            rec.section("G.  LLAVE DE CORTE — PERFIL  (ACI 318-19 17.11 / AISC)")
        return _lug_section(prj, rec)
    if rec:
        rec.section("G.  LLAVE DE CORTE  (ACI 318-19 §17.11 / AISC DG1 §3.5)")
    V = prj.eloads.Vu
    n_lug = 2 if L.direction.startswith("Ambos") else 1
    Vlug = V / n_lug

    h_emb = max(0.0, L.H - p.grout)
    Abrg = L.W * h_emb
    # ACI 318-19 Ec. 17.11.2.1a  (Psi_brg,sl = 1.0, conservador)
    phiVbrg = 0.65 * 1.7 * c.fc * Abrg
    out.append(Check("lug_brg", "Llave — aplastamiento del concreto",
                     Vlug, phiVbrg, "kip", "ACI 318-19 17.11.2.1",
                     f"Abrg = {u.q('L', L.W)} × {u.q('L', h_emb)} = {u.q('A', Abrg)} "
                     "(descontado el espesor del mortero)"))
    if rec:
        rec.add("h emb", "H − mortero",
                f"{rec.n('L', L.H)} − {rec.n('L', p.grout)}", h_emb, "L")
        rec.add("Abrg,sl", "W · h emb",
                f"{rec.n('L', L.W)} · {rec.n('L', h_emb)}", Abrg, "A")
        rec.add("φVbrg", "φ·1.7·f'c·Abrg,sl",
                f"0.65·1.7·{rec.n('S', c.fc)}·{rec.n('A', Abrg)}", phiVbrg, "F",
                "ACI Ec. 17.11.2.1a", "Ψbrg,sl = 1.0 (conservador)")
        rec.check("Aplastamiento del concreto contra la llave", Vlug, phiVbrg, "F",
                  Vlug / max(phiVbrg, 1e-9), Vlug <= phiVbrg, "ACI 17.11.2.1")

    # flexion de la llave en la cara inferior de la placa
    arm = p.grout + h_emb / 2.0
    Mu = Vlug * arm
    Z = L.W * L.t ** 2 / 4.0
    phiMn = 0.90 * L.mat().Fy * Z
    out.append(Check("lug_flex", "Llave — flexion de la pletina", Mu, phiMn, "kip·in",
                     "AISC F11", f"brazo = {u.q('L', arm)}"))
    if rec:
        rec.add("brazo", "mortero + h emb/2",
                f"{rec.n('L', p.grout)} + {rec.n('L', h_emb)}/2", arm, "L")
        rec.add("Mu", "Vlug · brazo",
                f"{rec.n('F', Vlug)} · {rec.n('L', arm)}", Mu, "M")
        rec.add("φMn", "0.90·Fy·W·t²/4",
                f"0.90·{rec.n('S', L.mat().Fy)}·{rec.n('L', L.W)}·"
                f"{rec.n('L', L.t)}²/4", phiMn, "M", "AISC F11")
        rec.check("Flexion de la pletina de la llave", Mu, phiMn, "M",
                  Mu / max(phiMn, 1e-9), Mu <= phiMn, "AISC F11")

    # cortante de la llave
    phiVn = 1.00 * 0.60 * L.mat().Fy * L.W * L.t
    out.append(Check("lug_shear", "Llave — cortante de la pletina", Vlug, phiVn, "kip", "AISC J4.2"))

    # soldadura de la llave a la placa (doble filete)
    thr = 0.707 * L.weld_size
    fv = Vlug / (2 * thr * L.W)                              # ksi
    Sw = 2 * thr * L.W ** 2 / 6.0
    fb = Mu / Sw if Sw > 0 else 0.0
    fr = math.hypot(fv, fb)
    FEXX = M.find(M.ELECTRODES, L.electrode, 1).FEXX
    out.append(Check("lug_weld", "Llave — soldadura a la placa (doble filete)",
                     fr, 0.75 * 0.60 * FEXX, "ksi", "AISC J2.4",
                     f"filete {M.float_to_frac(L.weld_size)} in a cada lado, "
                     f"garganta {u.q('L', thr)}"))

    # desprendimiento del concreto delante de la llave (ACI 17.11.2.2 -> 17.7.2)
    ca1 = max(1.0, min(c.N2, c.B2) / 2.0 - L.t / 2.0)
    Avc = (L.W + 2 * 1.5 * ca1) * min(1.5 * ca1, c.ha)
    Avco = 4.5 * ca1 ** 2
    fc_psi = c.fc * 1000.0
    Vb_lb = 9.0 * c.lam * math.sqrt(fc_psi) * ca1 ** 1.5
    psi_c = 1.0 if c.cracked else 1.4
    Vcb = (Avc / Avco) * psi_c * Vb_lb / 1000.0
    phi_c = 0.75 if c.cond_A_eff else 0.70
    out.append(Check("lug_brkout", "Llave — desprendimiento del concreto en cortante",
                     Vlug, phi_c * Vcb, "kip", "ACI 318-19 17.11.2.2 / 17.7.2",
                     f"ca1 = {u.q('L', ca1)}.  Se descuenta el area de la llave "
                     "del area proyectada."))
    if rec:
        rec.check("Desprendimiento del concreto delante de la llave", Vlug,
                  phi_c * Vcb, "F", Vlug / max(phi_c * Vcb, 1e-9),
                  Vlug <= phi_c * Vcb, "ACI 17.11.2.2")
    return out


# ========================================================== E. RIGIDIZADORES
def stiffeners(prj: Project, br: Bearing, rec: Recorder | None = None) -> list[Check]:
    """Pletinas rigidizadoras trabajando como mensula entre la cara del perfil
    y el borde de la placa.

    Trayectoria de carga adoptada:
      - la presion de contacto tributaria entra a la pletina por la soldadura
        HORIZONTAL pletina-placa (flujo de cortante);
      - el momento resultante en la cara del perfil lo toma la soldadura
        VERTICAL pletina-columna y la propia seccion de la pletina.

    En mensulas triangulares o con la esquina recortada la seccion critica no
    esta necesariamente en la cara del perfil, asi que se barre toda la
    proyeccion buscando la relacion M(x)/Z(x) maxima.
    """
    st = prj.stiff
    u = prj.units()
    out: list[Check] = []
    if not st.enabled or st.count <= 0:
        return out
    if rec:
        rec.section("H.  RIGIDIZADORES")
    Fy = st.mat().Fy
    E = 29000.0
    bw, bh = G.profile_bbox(prj)

    s_ = prj.section.shape()
    if s_.is_round:                      # radiales: proyeccion medida desde el cilindro
        avail = max(0.0, min(prj.plate.Nc, prj.plate.Bc) / 2.0 - s_.d / 2.0)
        width = math.pi * (s_.d + 2 * min(st.L, avail))   # perimetro exterior
        axis = "x"
    elif st.position.startswith("Alma"):
        avail = max(0.0, (prj.plate.Bc - bw) / 2.0)
        width = prj.plate.Nc
        axis = "y"
    else:
        avail = max(0.0, (prj.plate.Nc - bh) / 2.0)
        width = prj.plate.Bc
        axis = "x"
    Le = min(st.L, avail)

    out.append(Check("stf_fit", "Rigidizador — la proyeccion cabe en la placa",
                     st.L, max(avail, 1e-9), "in", "Geometria",
                     f"Voladizo disponible desde la cara del perfil = {u.q('L', avail)}"))

    lam_r = 0.56 * math.sqrt(E / Fy)
    out.append(Check("stf_slend", "Rigidizador — esbeltez del borde libre",
                     st.free_edge / st.t, lam_r, "-", "AISC Tabla B4.1a",
                     f"forma {st.shape.lower()}; borde libre = {u.q('L', st.free_edge)}, "
                     f"λr = 0.56·√(E/Fy) = {lam_r:.1f}"))

    # ------- ubicacion real de las pletinas -> ancho tributario verdadero
    offs = sorted(G._face_offsets(prj, bw if axis == "x" else bh, axis))
    if s_.is_round:
        trib = 2 * math.pi * (s_.d / 2.0 + Le / 2.0) / max(1, st.count)
        offs = []
    elif len(offs) > 1:
        gaps = [offs[i + 1] - offs[i] for i in range(len(offs) - 1)]
        trib = max(gaps)
    else:
        trib = width / 2.0
    trib = min(trib, width)

    Lload = Le if br.case == "CASO 1" else min(Le, max(br.Y, 0.0))
    q = br.fp * trib                                   # kip/in
    V = q * Lload

    # ------- seccion critica barriendo la proyeccion
    worst_x, worst_r, Mw, Zw = 0.0, 0.0, 0.0, 1e-9
    for i in range(41):
        x = Le * i / 40.0
        dep = st.depth_at(x)
        if dep <= 1e-6:
            continue
        lrem = max(0.0, min(Lload, Le - x))
        Mx = q * lrem * (Le - x - lrem / 2.0)
        Zx = st.t * dep ** 2 / 4.0
        r = Mx / (0.90 * Fy * Zx)
        if r > worst_r:
            worst_x, worst_r, Mw, Zw = x, r, Mx, Zx
    out.append(Check("stf_flex", "Rigidizador — flexion en la seccion critica", Mw,
                     0.90 * Fy * Zw, "kip·in", "AISC F11",
                     f"p = {u.q('S', br.fp)}, ancho tributario = {u.q('L', trib)}, "
                     f"proyeccion efectiva = {u.q('L', Le)}, seccion critica a "
                     f"{u.q('L', worst_x)} de la cara (peralte "
                     f"{u.q('L', st.depth_at(worst_x))})"))
    if rec:
        rec.add("L efectiva", "min( L ; voladizo disponible )",
                f"min( {rec.n('L', st.L)} ; {rec.n('L', avail)} )", Le, "L")
        rec.add("ancho tributario", "separacion entre pletinas", "", trib, "L")
        rec.add("q", "fp · ancho tributario",
                f"{rec.n('S', br.fp)} · {rec.n('L', trib)}", q, "LF")
        rec.add("V", "q · L cargada",
                f"{rec.n('LF', q)} · {rec.n('L', Lload)}", V, "F")
        rec.add("Mu (seccion critica)", "q·Lc·(Le − x − Lc/2)",
                f"seccion critica a {rec.n('L', worst_x)} de la cara, "
                f"peralte {rec.n('L', st.depth_at(worst_x))}", Mw, "M",
                "", "en mensulas triangulares o recortadas se barre toda la "
                    "proyeccion buscando el maximo de M(x)/Z(x)")
        rec.add("φMn", "0.90·Fy·t·h²/4",
                f"0.90·{rec.n('S', Fy)}·{rec.n('A', Zw)}", 0.90 * Fy * Zw, "M")
        rec.check("Flexion del rigidizador", Mw, 0.90 * Fy * Zw, "M",
                  Mw / max(0.90 * Fy * Zw, 1e-9), Mw <= 0.90 * Fy * Zw, "AISC F11")
    out.append(Check("stf_shear", "Rigidizador — cortante", V,
                     1.00 * 0.60 * Fy * st.h * st.t, "kip", "AISC J4.2"))

    thr = 0.707 * st.weld_size
    FEXX = M.find(M.ELECTRODES, st.electrode, 1).FEXX
    cap_w = 0.75 * 0.60 * FEXX
    Lwp = min(st.weld_len_plate, max(Le - st.clip_root, 0.0))
    if Lwp > 1e-6:
        out.append(Check("stf_weld_pl", "Rigidizador — soldadura a la PLACA (doble filete)",
                         V / (2 * thr * Lwp), cap_w, "ksi", "AISC J2.4",
                         f"flujo de cortante sobre {rec.n('L', Lwp)} {rec.us.L} "
                         f"(descontado el destaje de "
                         + M.float_to_frac(st.clip_root) + " in), filete "
                         + M.float_to_frac(st.weld_size) + " in"))
    Lwc = st.weld_len_col
    Mcol = q * Lload * max(Le - Lload / 2.0, 0.0)
    fv_c = V / (2 * thr * Lwc) if Lwc > 1e-6 else 0.0
    Sw = 2 * thr * Lwc ** 2 / 6.0
    fb_c = Mcol / Sw if Sw > 0 else 0.0
    out.append(Check("stf_weld_col", "Rigidizador — soldadura a la COLUMNA (doble filete)",
                     math.hypot(fv_c, fb_c), cap_w, "ksi", "AISC J2.4",
                     f"V y M sobre la altura soldada = {u.q('L', Lwc)}"))
    if rec:
        rec.check("Soldadura rigidizador-columna", math.hypot(fv_c, fb_c), cap_w,
                  "S", math.hypot(fv_c, fb_c) / cap_w,
                  math.hypot(fv_c, fb_c) <= cap_w, "AISC J2.4")
    return out


# ============================================================== F. PERFIL
def column_base(prj: Project) -> list[Check]:
    """Esfuerzos en la seccion del perfil inmediatamente sobre la placa."""
    s = prj.section.eff()
    L = prj.cloads      # carga en el eje de la columna (sin trasladar al centro de la placa)
    Fy = prj.section.mat().Fy
    out = []
    sig = L.Pu / s.A + abs(L.Mux) / max(s.Sx, 1e-9) + abs(L.Muy) / max(s.Sy, 1e-9)
    out.append(Check("col_norm", "Perfil — esfuerzo normal combinado en la base",
                     sig, 0.90 * Fy, "ksi", "AISC H1 (referencia)",
                     "P/A + Mx/Sx + My/Sy en la fibra mas solicitada."))
    tau = L.Vu / max(s.Aw, 1e-9)
    out.append(Check("col_shear", "Perfil — cortante en el alma", tau,
                     1.00 * 0.60 * Fy, "ksi", "AISC G2.1"))
    return out
