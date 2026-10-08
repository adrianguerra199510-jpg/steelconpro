# -*- coding: utf-8 -*-
"""
Verificaciones basadas en el analisis de elementos finitos SOLIDO 3D (Gmsh + CalculiX).

El modelo 3D es el unico analisis de elementos finitos del programa.  Cuando existe un analisis vigente
(hecho con el proyecto tal como esta ahora) sus resultados alimentan el veredicto:

  · fem_bolt   traccion del perno mas cargado           AISC J3.6 (φ·0.75·Fu·Ab)
  · fem_press  presion de contacto maxima                AISC J8
  · fem_vm     von Mises PROMEDIADO en la placa          criterio del programa: ≤ 0.90·Fy
               (el valor puntual no converge con la malla; el promediado en un circulo de radio
               fijo sobre la misma cara si; ver view3d.smoothed_plate_vm)
  · fem_weld*  soldadura perfil-placa, una fila por zona AISC J2.4

Si no hay analisis 3D vigente, el programa solo avisa que las verificaciones FEM estan pendientes.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .model import Project
from .design import Check, Bearing


@dataclass
class Fem3D:
    """Paquete de resultados del analisis 3D que consume el veredicto y la memoria."""
    post: object = None              # weld3d.Post3D
    vm_avg: dict = None              # view3d.smoothed_plate_vm
    rep: dict = None                 # imagenes y resumen para el reporte
    fast: bool = False
    lc: float = 0.0                  # tamano de elemento usado, in
    n_nodes: int = 0
    n_elems: int = 0
    umax: float = 0.0
    vmmax: float = 0.0
    peeq_r: float = 0.0              # radio de promedio de la PEEQ, in
    peeq_parts: dict = None          # PEEQ por pieza (plate/column/stiff/lug/washer): {'raw': ..., 'avg': ...}
    peeq: tuple = None               # (PEEQ max en la placa [fraccion], x, y, z) si el analisis fue elasto-plastico
    folder: str = ""
    msg: str = ""
    sig: str = ""                    # firma (JSON) del proyecto con el que se corrio


def bolt_phiRnt(prj: Project) -> float:
    g, mat = prj.bolts.geom(), prj.bolts.mat()
    return 0.75 * 0.75 * mat.Fu * g.Ab                       # AISC J3-1: φ·Fnt·Ab, Fnt = 0.75·Fu


def fem_checks(prj: Project, br: Bearing, fem: Fem3D, rec=None) -> list:
    """Filas del veredicto que salen del analisis 3D vigente."""
    u = prj.units()
    out: list[Check] = []
    post = fem.post
    phi = bolt_phiRnt(prj)
    Fy = prj.plate.mat().Fy
    mesh_txt = (f"malla de {u.q('L', fem.lc)}" if fem.lc else "malla") + f", {fem.n_nodes:,} nodos"

    # ---- pernos
    bolts = list(getattr(post, "bolts", []))
    if bolts:
        k, bx, by, Tm = max(bolts, key=lambda b: b[3])
        out.append(Check("fem_bolt", "FEM 3D — traccion maxima en un perno", Tm, phi, "kip",
                         "AISC J3.6",
                         f"P{k} ({u.fmt('L', bx)}, {u.fmt('L', by)}); ΣT = {u.q('F', post.T_bolts)}; "
                         f"{mesh_txt}", skip=Tm <= 1e-6))
    # ---- concreto
    out.append(Check("fem_press", "FEM 3D — presion de contacto maxima", post.p_max, br.fp_max, "ksi",
                     "AISC J8", "Distribucion real de la presion sobre el concreto (resortes de Winkler)."))
    # ---- placa
    va = fem.vm_avg
    pk = getattr(fem, "peeq", None)
    lim = float(getattr(prj.fea, "plastic_limit", 5.0))
    if pk is not None:
        out.append(Check("fem_peeq", "FEM 3D — deformacion plastica equivalente en la placa", pk[0] * 100.0, lim, "%",
                         "deformacion plastica admisible",
                         f"acero elasto-plastico con limite φ·Fy = {u.q('S', 0.9 * Fy)}; maximo en "
                         f"({u.fmt('L', pk[1])}, {u.fmt('L', pk[2])}, z = {u.fmt('L', pk[3])}) {u.L}"))
    PN = {"column": "columna", "stiff": "rigidizadores", "lug": "llave de corte"}
    for part, nm in PN.items():
        d = (getattr(fem, "peeq_parts", None) or {}).get(part)
        if d is None or pk is None:
            continue
        a = d["avg"]
        out.append(Check(f"fem_peeq_{part}", f"FEM 3D — deformacion plastica equivalente en {nm}", a[0] * 100.0, lim, "%",
                         "deformacion plastica admisible",
                         f"promedio en r = {u.q('L', getattr(fem, 'peeq_r', 0.0) or 0.0)}; pico nodal {d['raw'][0] * 100:.3f} % "
                         f"(singularidad de malla en el cordon, no se verifica); maximo en "
                         f"({u.fmt('L', a[1])}, {u.fmt('L', a[2])}, z = {u.fmt('L', a[3])}) {u.L}"))
    if va:
        if pk is not None:        # con plasticidad el esfuerzo queda acotado por φ·Fy: se informa, no se verifica
            out.append(Check("fem_vm", "FEM 3D — von Mises promediado en la placa (informativo)", va["vm"], 0.90 * Fy,
                             "ksi", "informativo (placa elasto-plastica)",
                             f"promedio en r = {u.q('L', va['radius'])}; pico puntual {u.q('S', fem.vmmax)}",
                             skip=True))
        else:
            out.append(Check("fem_vm", "FEM 3D — von Mises promediado en la placa", va["vm"], 0.90 * Fy, "ksi",
                             "criterio del programa: ≤ 0.90·Fy",
                             f"promedio del tensor en r = {u.q('L', va['radius'])} sobre la cara de la placa; "
                             f"pico puntual {u.q('S', fem.vmmax)} (no converge con la malla)"))
    # ---- soldadura
    for i, z in enumerate(getattr(post, "zones", [])):
        if not (z.fmax > 1e-9 or z.cap > 0):
            continue
        cap = (z.fmax / z.ratio) if (z.ratio > 1e-12 and z.ratio != float("inf")) else z.cap
        if z.ratio == float("inf"):
            cap = 0.0
        # El pico elastico local (esquinas, donde el perfil llega a la placa) se admite hasta `weld_peak_factor` veces
        # la resistencia, por la redistribucion plastica de un filete ductil (AISC J2.4 lo permite);
        # la MEDIA de la cara se exige completa.  D/C de la fila = max(pico/F, media).
        F = max(1.0, float(getattr(prj.fea, "weld_peak_factor", 1.5)))
        if getattr(z, "plastic", False) and z.cap > 0:
            # criterio plastico (Ghimire et al. 2023): D/C = deformacion plastica de la garganta / limite; media <= 1.0
            lim_w = float(getattr(prj.fea, "weld_plastic_limit", 5.0))
            dem = max(z.ratio, z.ratio_avg) * z.cap
            out.append(Check(f"fem_weld{i}", f"FEM 3D — soldadura {z.name}", dem, z.cap, "kip/in",
                             "AISC J2.4 + plastico 5 %",
                             f"{z.spec}; deformacion plastica de la garganta {z.eps * 100:.2f} % (limite {lim_w:g} %); "
                             f"pico {u.q('LF', z.fmax)} (D/C pico {z.ratio:.3f}); media {u.q('LF', z.f_avg)} "
                             f"(D/C media {z.ratio_avg:.3f}); {z.note}"
                             + (f"; reduccion por cordon largo β = {z.beta:.2f}" if z.beta < 0.999 else "")))
            continue
        dem = max(z.fmax / F, z.f_avg) if cap > 0 else z.fmax
        out.append(Check(f"fem_weld{i}", f"FEM 3D — soldadura {z.name}", dem, cap, "kip/in",
                         "AISC J2.4", f"{z.spec}; pico {u.q('LF', z.fmax)} (D/C pico {z.ratio:.3f}, limite {F:g}); "
                         f"media {u.q('LF', z.f_avg)} (D/C media {z.ratio_avg:.3f}, limite 1.0); {z.note}"
                         + (f"; reduccion por cordon largo β = {z.beta:.2f}" if z.beta < 0.999 else "")))
    if rec:
        rec.section("I.  ELEMENTOS FINITOS SOLIDOS 3D  (Gmsh + CalculiX)")
        rec.text("Modelo solido de tetraedros cuadraticos: placa con los agujeros taladrados, perfil, "
                 "rigidizadores y llave; concreto como resortes de Winkler solo a compresion y pernos como "
                 "resortes solo a traccion (paso no lineal).")
        if getattr(post, "weld_model", "") == "conectores":
            rec.text("Soldadura: el perfil y la placa son cuerpos separados. La compresion pasa por contacto "
                     "(resortes solo-compresion) y cada linea de cordon es un conector de traccion y cortante "
                     "cuya fuerza se lee directo del resorte (F = k·Δ); un lado sin cordon no transmite. La "
                     "fuerza por unidad de longitud se suaviza en una ventana de 4 veces el cateto y se compara "
                     "con φ·0.60·FEXX·garganta·kd por linea (AISC J2.4) y con la rotura del metal base. "
                     + ("Los conectores son ELASTO-PLASTICOS (Ghimire et al. 2023): fluyen en esa "
                        "resistencia de diseno con una rama plastica corta (pendiente k/1000), lo que redistribuye los "
                        "picos; el D/C del cordon vale 1 cuando la deformacion plastica de la garganta llega al limite "
                        f"({getattr(prj.fea, 'weld_plastic_limit', 5.0):g} %) y la MEDIA de cada cara se exige hasta 1.0."
                        if str(getattr(prj.fea, "weld_criterion", "")).startswith("Plastico") else
                        "El D/C PICO (punto mas cargado, en regimen elastico) se admite hasta el limite del proyecto "
                        "(por defecto 1.5, por la redistribucion plastica del filete) y la MEDIA de cada cara hasta 1.0.")
                     + (" El FEM no captura la reduccion por cordon largo: se aplica β (AISC J2.2b(d)) cuando L > 100·w."
                        if getattr(prj.fea, "weld_long_reduction", True) else ""))
        else:
            rec.text("Soldadura: union perfil-placa monolitica (equivale a CJP); la fuerza del cordon se deduce "
                     "de los esfuerzos del perfil sobre el pie y se verifica con AISC J2.4.")
        rec.add("malla", mesh_txt, "", None, "-")
        if getattr(post, "weld_model", "") == "conectores":
            rec.add("Compresion por contacto", "Σ fuerza de los resortes de contacto perfil-placa", "",
                    post.F_bear, "F", "", "la compresion no pasa por el cordon (DG1)")
            rec.add("Traccion en cordones", "Σ fuerza normal de los conectores de cordon", "",
                    post.Fz_weld, "F", "", "equilibrio vertical: contacto − cordones = Pu")
        rec.add("Tmax perno", "reaccion en los resortes del anillo de la tuerca", "",
                max((b[3] for b in bolts), default=0.0), "F", "AISC J3.6")
        rec.add("pmax", "ks · hundimiento maximo", "", post.p_max, "S", "AISC J8")
        if pk is not None:
            rec.add("PEEQ placa", "deformacion plastica equivalente maxima (acero φ·Fy, perfectamente plastico)", "",
                    pk[0] * 100.0, "-", "", f"limite {lim:g} %  (se muestra en %)")
        if va:
            rec.add("σvM promediado", "promedio del tensor en un circulo de radio r",
                    f"r = {rec.n('L', va['radius'])}", va["vm"], "S", "",
                    "converge con la malla; el pico puntual no")
        rec.add("equilibrio", "R concreto − ΣT pernos − Pu",
                f"{rec.n('F', post.R_conc)} − {rec.n('F', post.T_bolts)} − {rec.n('F', prj.eloads.Pu)}",
                post.R_conc - post.T_bolts - prj.eloads.Pu, "F", "", "residuo de equilibrio del modelo")
    return out
