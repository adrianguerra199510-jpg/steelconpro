# -*- coding: utf-8 -*-
"""Orquesta todas las verificaciones y devuelve un resultado unico."""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from .model import Project
from . import design as D
from . import anchors as A
from . import geometry as G
from . import materials as M
from .design import Check, Bearing
from .explain import Recorder
from .fem_checks import fem_checks


@dataclass
class Results:
    br: Bearing = None
    treq: float = 0.0
    tdet: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    fem: object = None              # fem_checks.Fem3D vigente (o None)
    warnings: list = field(default_factory=list)
    rec: Recorder = None
    combo_rows: list = field(default_factory=list)   # resumen de todas las combinaciones (lo llena la UI)
    combo_gov: int = 0

    @property
    def max_ratio(self) -> float:
        rs = [c.ratio for c in self.checks if not c.skip]
        return max(rs) if rs else 0.0

    @property
    def governing(self) -> Check | None:
        act = [c for c in self.checks if not c.skip]
        return max(act, key=lambda c: c.ratio) if act else None

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if not c.skip) and not self.warnings_fatal

    @property
    def pending(self) -> bool:
        """True si falta el analisis 3D: el veredicto final lo da el 3D, no el calculo cerrado."""
        return self.fem is None

    @property
    def verdict(self) -> str:
        """'PENDIENTE' (realizar el analisis 3D), 'CUMPLE' o 'NO CUMPLE'."""
        if self.pending:
            return "PENDIENTE"
        return "CUMPLE" if self.ok else "NO CUMPLE"

    @property
    def warnings_fatal(self) -> bool:
        return any(w.startswith("**") for w in self.warnings)


def solve(prj: Project, detail: bool = True, fem=None) -> Results:
    """`fem`: paquete Fem3D del analisis 3D hecho con ESTE proyecto (o None si no hay uno vigente)."""
    R = Results()
    R.fem = fem
    notes = prj.normalize()
    R.rec = Recorder(prj.units()) if detail else None
    rec = R.rec
    u = prj.units()
    if rec:
        rec.section("DATOS DE PARTIDA")
        s_ = prj.section.shape()
        rec.add("Perfil", prj.section.label,
                f"{prj.section.steel}, rotacion {prj.section.rotation:g}°", None)
        rec.add("Placa", ("Ø" + rec.n('L', prj.plate.Dp)
                          if prj.plate.shape == "Circular"
                          else f"{rec.n('L', prj.plate.N)} × {rec.n('L', prj.plate.B)}")
                + f" × {rec.n('L', prj.plate.tp)} {u.L}", prj.plate.steel, None)
        if abs(prj.section.cx) > 1e-9 or abs(prj.section.cy) > 1e-9:
            rec.add("Columna descentrada",
                    f"cx = {rec.n('L', prj.section.cx)} , cy = {rec.n('L', prj.section.cy)} {u.L} respecto al centro de la placa",
                    "las cargas se ingresan en el eje de la columna; los momentos que siguen estan "
                    "trasladados al centro de la placa:  Mux' = Mux − Pu·cy ,  Muy' = Muy + Pu·cx", None)
        if prj.loads.tilted:
            l0 = prj.loads
            rec.add("Columna inclinada",
                    f"giro X = {l0.tilt_x:g}°, giro Y = {l0.tilt_y:g}° respecto a la normal de la placa",
                    "cargas ingresadas en el eje de la columna; a continuacion las "
                    "componentes proyectadas a los ejes de la placa", None)
            rec.add("Pu,col", "axial en el eje de la columna", "", l0.Pu, "F")
            rec.add("Vu,col", "cortante transversal a la columna",
                    f"√({rec.n('F', l0.Vux)}² + {rec.n('F', l0.Vuy)}²)", l0.Vu, "F")
        rec.add("Pu", "axial factorizado (compresion +)"
                + (" — normal a la placa" if prj.loads.tilted else ""), "", prj.eloads.Pu, "F")
        rec.add("Mux", "momento respecto al eje fuerte", "", prj.eloads.Mux, "M")
        rec.add("Muy", "momento respecto al eje debil", "", prj.eloads.Muy, "M")
        rec.add("Vu", "cortante resultante",
                f"√({rec.n('F', prj.eloads.Vux)}² + {rec.n('F', prj.eloads.Vuy)}²)",
                prj.eloads.Vu, "F")
        rec.add("f'c", "resistencia del concreto", "", prj.conc.fc, "S")
        rec.add("Fy placa", "", prj.plate.steel, prj.plate.mat().Fy, "S")
        rec.add("Anclajes", f"{prj.bolts.n_total} × Ø{prj.bolts.size} in",
                f"{prj.bolts.steel}, {prj.bolts.atype}, hef = "
                f"{rec.f('L', prj.bolts.hef)}", None)
    R.br = D.bearing(prj, rec)
    br = R.br
    p, b, c, L = prj.plate, prj.bolts, prj.conc, prj.eloads

    # ------------------------------------------------------------ avisos
    R.warnings += notes
    if prj.loads.tilted:
        if abs(prj.loads.tilt_x) > 60 or abs(prj.loads.tilt_y) > 60:
            R.warnings.append("Inclinacion de columna mayor a 60°: verifique que las formulas de "
                              "DG1 (columna cuasi-perpendicular a la placa) sigan siendo aplicables.")
        if abs(L.Tz) > 1e-6:
            R.warnings.append("La inclinacion genera un momento torsor alrededor de la normal de la "
                              f"placa (Tz = {L.Tz:.1f} kip·in) que NO se verifica en los pernos "
                              "ni en la soldadura.")
        if L.Pu < 0 and prj.loads.Pu > 0:
            R.warnings.append("La inclinacion convierte la compresion en traccion normal a la placa.")
    if not br.feasible:
        R.warnings.append("** El discriminante del equilibrio es negativo: la placa no puede "
                          "equilibrar Pu y Mu. Aumente N, B o f'c, o acerque los pernos al borde. **")
    if b.atype.startswith("Recto") and br.Tu > 1e-6:
        R.warnings.append("** Varilla recta sin cabeza ni gancho con traccion en los pernos: "
                          "ACI 318-19 no le reconoce resistencia a la extraccion. **")
    if abs(prj.section.rotation) > 1e-6 and abs(abs(prj.section.rotation) - 90) > 1e-6:
        R.warnings.append("Rotacion del perfil distinta de 0° o 90°: las formulas cerradas de "
                          "DG1 usan el rectangulo envolvente del perfil (conservador). "
                          "El modelo de elementos finitos 3D si usa la geometria real.")
    if p.shape == "Circular":
        R.warnings.append("Placa circular: las formulas cerradas usan el cuadrado equivalente de "
                          "igual area (Leq = 0.8862·Dp).")
    emin = M.min_edge_distance(b.size)
    if min(b.ex, b.ey) < emin - 1e-6:
        R.warnings.append(f"Distancia al borde menor que la minima recomendada "
                          f"({u.q('L', emin)} para perno de {b.size}\").")
    cl = G.bolt_clashes(prj)
    if cl:
        lst = ", ".join(f"#{k} ({x:.1f},{y:.1f})" for k, x, y, _ in cl[:6])
        R.warnings.append(f"** {len(cl)} perno(s) interfieren con el perfil o no dejan holgura "
                          f"para tuerca/llave: {lst}. Cambie la rotacion, ex/ey o la disposicion. **")
    bw, bh = G.profile_bbox(prj)
    cdx, cdy = G.col_shift(prj)
    if bw / 2 + abs(cdx) > p.Bc / 2 + 1e-6 or bh / 2 + abs(cdy) > p.Nc / 2 + 1e-6:
        R.warnings.append("** El perfil no cabe dentro de la placa. **")
    if abs(cdx) > 1e-9 or abs(cdy) > 1e-9:
        R.warnings.append("Columna descentrada respecto a la placa: el momento por la excentricidad de Pu se suma a "
                          "los momentos aplicados; los voladizos de la placa se toman del lado mas largo y la torsion "
                          f"(Tz = {prj.eloads.Tz:.1f} kip·in) no se verifica en pernos ni soldadura.")
    if c.seismic:
        R.warnings.append("Diseno sismico activo: se aplica el factor 0.75 a la resistencia del "
                          "concreto de los anclajes (ACI 17.10.5.2). Verifique ademas el requisito "
                          "de que el anclaje sea gobernado por la fluencia ductil del acero.")

    zs = D.unwelded_zones(prj)
    if zs:
        R.warnings.append(
            "La columna NO esta soldada en todo el contorno (sin soldar: " + ", ".join(zs) +
            "). La compresion solo se transmite por contacto; la traccion, el cortante y el "
            "momento los toman unicamente las zonas soldadas. Revise que el detalle sea "
            "el intencionado.")

    # ------------------------------------------------------------ chequeos
    ck: list[Check] = []

    ratio_brg = 0.0 if br.case == "TRACCION NETA" else (
        99.0 if not br.feasible else (br.fp / br.fp_max if br.fp_max > 0 else 99.0))
    ck.append(Check("brg", "Aplastamiento del concreto bajo la placa",
                    br.fp, br.fp_max, "ksi", "AISC J8 / DG1 §3.3",
                    {"CASO 1": "Presion uniforme sobre la longitud Y.",
                     "CASO 2": "La presion alcanza fp,max por definicion del metodo; "
                               "el equilibrio se logra con traccion en los pernos.",
                     "TRACCION NETA": "No hay aplastamiento: la placa esta en traccion neta."}
                    .get(br.case, "")))
    if not br.feasible:
        ck[-1].capacity = 0.0
        ck[-1].demand = 1.0

    if rec:
        rec.check("Aplastamiento del concreto", br.fp, br.fp_max, "S",
                  ratio_brg, ratio_brg <= 1.0, "AISC J8")
    R.treq, R.tdet = D.plate_thickness(prj, br, rec)
    ck.append(Check("tp", "Espesor de la placa  tp ≥ t requerido",
                    R.treq, p.tp, "in", "DG1 §3.1 y §3.3",
                    f"m={u.q('L', R.tdet['m_y'])}, n={u.q('L', R.tdet['m_x'])}, "
                    f"λn'={u.q('L', R.tdet['lam_n'])}"
                    + ("  (voladizos reducidos por los rigidizadores)" if prj.stiff.enabled else "")))

    if rec:
        rec.check("Espesor de la placa", R.treq, p.tp, "L",
                  R.treq / max(p.tp, 1e-9), R.treq <= p.tp, "DG1 §3.1")
    ck += A.anchor_checks(prj, br, rec, fem)
    ck += D.welds(prj, br, rec)
    ck += D.shear_lug(prj, rec)
    ck += D.stiffeners(prj, br, rec)
    ck += D.column_base(prj)
    R.checks = ck

    # ------------------------------------------------------------ FEM 3D
    if fem is not None:
        try:
            R.checks += fem_checks(prj, br, fem, rec)
        except Exception as e:                              # pragma: no cover
            R.warnings.append(f"No se pudieron evaluar los resultados del FEM 3D: {e}")
    else:
        R.warnings.append("REALIZAR ANALISIS 3D (F8): el veredicto final y la fuerza de los pernos salen del "
                          "analisis solido; hasta entonces solo se muestran las verificaciones de calculo cerrado.")
    return R
