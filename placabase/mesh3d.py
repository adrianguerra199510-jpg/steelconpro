# -*- coding: utf-8 -*-
"""
Modelo SOLIDO 3D del conjunto, para Gmsh + CalculiX.

A diferencia del modelo integrado (placa de Mindlin, rapido, para iterar), aqui
se construye la geometria real en tres dimensiones:

  - placa base con los AGUJEROS de los pernos taladrados de verdad,
  - perfil extruido como solido con el espesor de sus paredes/alas,
  - cordones de soldadura como prismas triangulares a lo largo del contacto
    perfil-placa (filete) o como fusion directa (CJP),
  - pletinas rigidizadoras con su forma real (rectangular, triangular o con la
    esquina recortada),
  - llave de corte por debajo de la placa,
  - apoyo del concreto como resortes a tierra en la cara inferior,
  - pernos como resortes verticales repartidos en el anillo de apoyo de la
    tuerca, alrededor de cada agujero.

Se escribe un archivo .geo con el kernel OpenCASCADE.  Gmsh lo malla en
tetraedros de segundo orden y lo exporta en formato Abaqus (.inp), que
CalculiX lee directamente.  El script Python que se genera junto al .geo
encadena todo el proceso y escribe el .inp final con materiales, apoyos,
cargas y peticiones de salida.
"""
from __future__ import annotations
from pathlib import Path
import math
import os
import re
import subprocess
import sys

from .model import Project
from . import geometry as G
from .units import ES_KSI, NU_STEEL, Ec_ksi
from .params3d import washer_radius, washer_thickness, washer_elements
from .shapes import W_SHAPE, HSS_RECT


# ------------------------------------------------------------------ utilidades
def wspec_txt(prj: Project) -> str:
    s = prj.section.shape()
    w = prj.welds.perimeter if s.is_hollow else prj.welds.flange
    return f"{w.wtype} {w.size:g} in, {w.electrode}"



def _poly(name, pts, tag0):
    """Lineas de .geo para un poligono cerrado en z=0 -> (texto, tag_curveloop)."""
    L = []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        L.append(f"Point({tag0 + i}) = {{{x:.6f}, {y:.6f}, 0, lc}};")
    for i in range(n):
        a = tag0 + i
        b = tag0 + (i + 1) % n
        L.append(f"Line({tag0 + n + i}) = {{{a}, {b}}};")
    loop = tag0 + 2 * n
    L.append(f"Curve Loop({loop}) = {{" +
             ", ".join(str(tag0 + n + i) for i in range(n)) + "};")
    return L, loop, tag0 + 2 * n + 1


def _poly_auto(pts, var):
    """Poligono plano con numeracion automatica de Gmsh (evita choques de tags
    con las entidades que crean las extrusiones).  Deja la superficie en `var`."""
    n = len(pts)
    L = ["_pp = newp;"]
    for i, (x, y) in enumerate(pts):
        L.append(f"Point(_pp+{i}) = {{{x:.6f}, {y:.6f}, 0, lc}};")
    L.append("_ll = newl;")
    for i in range(n):
        L.append(f"Line(_ll+{i}) = {{_pp+{i}, _pp+{(i + 1) % n}}};")
    L.append("_cl = newll; Curve Loop(_cl) = {" +
             ", ".join(f"_ll+{i}" for i in range(n)) + "};")
    L.append(f"{var} = news; Plane Surface({var}) = {{_cl}};")
    return L


def profile_solid_polys(prj: Project):
    """Poligonos (exterior, interiores) que definen la SECCION del perfil."""
    def _clean(pts, tol=1e-7):
        out = []
        for q in pts:
            if not out or math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > tol:
                out.append(q)
        if len(out) > 2 and math.hypot(out[0][0] - out[-1][0],
                                       out[0][1] - out[-1][1]) <= tol:
            out.pop()
        return out

    ext, inn = G.profile_outline(prj)
    return _clean(ext), (_clean(inn) if inn else None)


# ================================================================== .geo
def write_geo(prj: Project, path: str, mesh_size: float = 0.0,
              prof_height: float = 0.0) -> str:
    p, b, st, lug = prj.plate, prj.bolts, prj.stiff, prj.lug
    s = prj.section.shape()
    g = b.geom()
    circ = (p.shape == "Circular")
    H = prof_height if prof_height > 0 else max(3.0 * s.d, 12.0)
    lc = mesh_size if mesh_size > 0 else max(p.tp / 2.0, min(p.Nc, p.Bc) / 26.0)

    L: list[str] = []
    L.append('SetFactory("OpenCASCADE");')
    L.append(f"// PlacaBasePro - modelo solido 3D - {prj.name} / {prj.element}")
    L.append("// Unidades: pulgada")
    L.append(f"lc = {lc:.6f};")
    L.append("")

    vol = 1000
    plate_v, prof_v, weld_v, stif_v, lug_v = [], [], [], [], []

    # ---------------------------------------------------------------- placa
    L.append("// ---------------- PLACA BASE")
    if circ:
        L.append(f"Cylinder({vol}) = {{0,0,0, 0,0,{p.tp:.6f}, {p.Dp/2:.6f}}};")
    else:
        L.append(f"Box({vol}) = {{{-p.B/2:.6f}, {-p.N/2:.6f}, 0, "
                 f"{p.B:.6f}, {p.N:.6f}, {p.tp:.6f}}};")
    plate_v.append(vol); vol += 1

    # ------------------------------------------------- agujeros de los pernos
    holes = []
    L.append("// ---------------- AGUJEROS DE PERNO")
    for (bx, by) in G.bolt_positions(prj):
        L.append(f"Cylinder({vol}) = {{{bx:.6f}, {by:.6f}, {-p.tp:.6f}, "
                 f"0,0,{3*p.tp:.6f}, {g.dh/2:.6f}}};")
        holes.append(vol); vol += 1
    if holes:
        L.append(f"BooleanDifference{{ Volume{{{plate_v[0]}}}; Delete; }}"
                 f"{{ Volume{{{','.join(map(str, holes))}}}; Delete; }}")

    # ------------------------------------------------ arandelas (apoyo de la tuerca)
    #   La tuerca no actua en el borde del agujero sino sobre la corona de la arandela; un disco anular
    #   unido a la placa rigidiza esa zona y reparte la carga del perno en una superficie pequena.
    tw = washer_thickness(prj)
    rw = washer_radius(prj)
    if tw > 0:
        L.append("// ---------------- ARANDELAS")
        vol_w = 3000
        for (bx, by) in G.bolt_positions(prj):
            L.append(f"Cylinder({vol_w}) = {{{bx:.6f}, {by:.6f}, {p.tp:.6f}, 0,0,{tw:.6f}, {rw:.6f}}};")
            L.append(f"Cylinder({vol_w + 1}) = {{{bx:.6f}, {by:.6f}, {p.tp - 0.5:.6f}, 0,0,{tw + 1.0:.6f}, "
                     f"{g.dh/2:.6f}}};")
            L.append(f"BooleanDifference{{ Volume{{{vol_w}}}; Delete; }}{{ Volume{{{vol_w + 1}}}; Delete; }}")
            vol_w += 2

    # --------------------------------------------------------------- perfil
    L.append("// ---------------- PERFIL")
    tag = 10000
    if prj.section.generic:
        # seccion generica o doble: cada rectangulo se extruye por separado y la
        # fusion final (BooleanFragments) los une
        for i, poly in enumerate(G.section_rects(prj)):
            L += _poly_auto(poly[:-1], f"sr{i}")
            L.append(f"pr{i}[] = Extrude {{0,0,{H:.6f}}} {{ Surface{{sr{i}}}; }};")
            L.append(f"Translate {{0,0,{p.tp:.6f}}} {{ Volume{{pr{i}[1]}}; }}")
    else:
        ext, inn = profile_solid_polys(prj)
        txt, loop_ext, tag = _poly("ext", ext, tag)
        L += txt
        loops = [loop_ext]
        if inn:
            txt, loop_inn, tag = _poly("inn", inn, tag)
            L += txt
            loops.append(loop_inn)
        surf = tag
        L.append(f"Plane Surface({surf}) = {{" + ", ".join(map(str, loops)) + "};")
        L.append(f"prof[] = Extrude {{0,0,{H:.6f}}} {{ Surface{{{surf}}}; }};")
        L.append(f"Translate {{0,0,{p.tp:.6f}}} {{ Volume{{prof[1]}}; }}")
        L.append("profV = prof[1];")
    tag += 1

    # ------------------------------------------------------------ soldadura
    #   El cordon NO se modela como un solido aparte: al fusionar el perfil con
    #   la placa (BooleanFragments) la union queda de resistencia total, que es
    #   exactamente lo que representa una soldadura CJP y el idealizado habitual
    #   para un modelo global.  La soldadura de filete se verifica en forma
    #   cerrada segun AISC J2 y, ademas, el modelo entrega la fuerza por unidad
    #   de longitud que circula por la interfaz.
    L.append("// ---------------- UNION PERFIL-PLACA: fusion (equivale a CJP)")
    L.append(f"// Soldadura declarada: {wspec_txt(prj)}")

    # --------------------------------------------------------- rigidizadores
    if st.enabled and st.count > 0:
        L.append("// ---------------- RIGIDIZADORES")
        prof2d = st.outline()[:-1]
        for (x1, y1, x2, y2) in G.stiffener_lines(prj):
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            tag2 = tag + 1000
            pts = [(u, v) for (u, v) in prof2d]
            L.append("sp = newp;")
            for i, (u, v) in enumerate(pts):
                L.append(f"Point(sp+{i}) = {{{u:.6f}, 0, {v:.6f}, lc}};")
            L.append("sl = newl;")
            for i in range(len(pts)):
                L.append(f"Line(sl+{i}) = {{sp+{i}, sp+{(i+1) % len(pts)}}};")
            L.append("sc = newll; Curve Loop(sc) = {" +
                     ", ".join(f"sl+{i}" for i in range(len(pts))) + "};")
            L.append("ss = news; Plane Surface(ss) = {sc};")
            L.append(f"sv[] = Extrude {{0,{st.t:.6f},0}} {{ Surface{{ss}}; }};")
            L.append(f"Translate {{0,{-st.t/2:.6f},0}} {{ Volume{{sv[1]}}; }}")
            L.append(f"Rotate {{{{0,0,1}}, {{0,0,0}}, {math.radians(ang):.6f}}} "
                     f"{{ Volume{{sv[1]}}; }}")
            L.append(f"Translate {{{x1:.6f}, {y1:.6f}, {p.tp:.6f}}} "
                     f"{{ Volume{{sv[1]}}; }}")

    # ------------------------------------------------------- llave de corte
    if lug.enabled and lug.is_section:
        L.append(f"// ---------------- LLAVE DE CORTE: perfil {lug.label}")
        rs, rnd, ro, tr = G.lug_rects(prj)
        if rnd:
            L.append(f"Cylinder(5000) = {{0,0,{-lug.H:.6f}, 0,0,{lug.H:.6f}, {ro:.6f}}};")
            L.append(f"Cylinder(5001) = {{0,0,{-lug.H:.6f}, 0,0,{lug.H:.6f}, {ro-tr:.6f}}};")
            L.append("BooleanDifference{ Volume{5000}; Delete; }{ Volume{5001}; Delete; }")
        else:
            for i, poly in enumerate(rs):
                L += _poly_auto(poly[:-1], f"sk{i}")
                L.append(f"lk{i}[] = Extrude {{0,0,{-lug.H:.6f}}} {{ Surface{{sk{i}}}; }};")
    elif lug.enabled:
        L.append("// ---------------- LLAVE DE CORTE")
        vol = 5000
        if "X" in lug.direction or "Ambos" in lug.direction:
            L.append(f"Box({vol}) = {{{-lug.W/2:.6f}, {-lug.t/2:.6f}, {-lug.H:.6f}, "
                     f"{lug.W:.6f}, {lug.t:.6f}, {lug.H:.6f}}};")
            lug_v.append(vol); vol += 1
        if "Y" in lug.direction or "Ambos" in lug.direction:
            L.append(f"Box({vol}) = {{{-lug.t/2:.6f}, {-lug.W/2:.6f}, {-lug.H:.6f}, "
                     f"{lug.t:.6f}, {lug.W:.6f}, {lug.H:.6f}}};")
            lug_v.append(vol); vol += 1

    # ---------------------------------------------------- fusion y etiquetas
    L.append("")
    L.append("// ---------------- UNION DE TODOS LOS SOLIDOS")
    L.append("todos[] = Volume{:};")
    L.append("BooleanFragments{ Volume{todos[]}; Delete; }{}")
    L.append("finalV[] = Volume{:};")
    L.append('Physical Volume("ACERO") = {finalV[]};')
    L.append("")
    L.append("// cara inferior de la placa: apoyo sobre el concreto")
    L.append("bot[] = Surface In BoundingBox{"
             f"{-p.Bc:.3f},{-p.Nc:.3f},-0.001,{p.Bc:.3f},{p.Nc:.3f},0.001}};")
    L.append('Physical Surface("APOYO_CONCRETO") = {bot[]};')
    L.append("// cara superior del perfil: aplicacion de las cargas")
    L.append("top[] = Surface In BoundingBox{"
             f"{-p.Bc:.3f},{-p.Nc:.3f},{p.tp+H-0.001:.3f},"
             f"{p.Bc:.3f},{p.Nc:.3f},{p.tp+H+0.001:.3f}}};")
    L.append('Physical Surface("TOPE_PERFIL") = {top[]};')
    L.append("")
    # refinamiento local en el pie del perfil: ahi se leen las fuerzas de la
    # soldadura, asi que conviene tener al menos 2-3 elementos en el espesor
    tmin = min(x for x in (s.tf, s.tw) if x > 0) if (s.tf or s.tw) else p.tp
    hw = float(getattr(prj.fea, "weld_mesh", 0.0) or 0.0)       # tamano manual del elemento sobre el cordon (0 = automatico)
    hmin = max(0.9 * tmin, hw if hw > 0 else min(lc / 2.2, 1.1))   # automatico: ~28 mm, sin importar lc      # en el cordon el elemento no pasa de ~28 mm (Ghimire et al. 2023)
    bw, bh = G.profile_bbox(prj)
    ext_r = 0.5 * max(bw, bh) + 0.5
    ccx_, ccy_ = G.col_shift(prj)
    L.append("// refinamiento en la union perfil-placa (lectura de la soldadura)")
    L.append("wc[] = Curve In BoundingBox{"
             f"{ccx_ - ext_r:.3f},{ccy_ - ext_r:.3f},{p.tp-0.001:.4f},"
             f"{ccx_ + ext_r:.3f},{ccy_ + ext_r:.3f},{p.tp+0.001:.4f}}};")
    L.append("Field[1] = Distance; Field[1].CurvesList = {wc[]}; Field[1].Sampling = 60;")
    L.append("Field[2] = Threshold; Field[2].InField = 1;")
    L.append(f"Field[2].SizeMin = {hmin:.4f}; Field[2].SizeMax = lc;")
    L.append(f"Field[2].DistMin = {1.2*tmin:.4f}; Field[2].DistMax = {4*tmin+1.5:.4f};")
    # refinamiento alrededor de cada agujero y arandela: la corona de apoyo debe tener varios elementos
    rh_ = g.dh / 2.0
    # tamano en la corona: ~3 elementos en su ancho y ~1.2 en el espesor de la arandela, sin pasar de lc/8
    hh = max(0.06, (rw - rh_) / 3.0, (tw / 1.2 if tw > 0 else 0.0), lc / 8.0)
    L.append("hc[] = {};")
    for (bx, by) in G.bolt_positions(prj):
        L.append(f"hc[] += Curve In BoundingBox{{{bx - rw - 0.02:.4f},{by - rw - 0.02:.4f},{p.tp - 0.001:.4f},"
                 f"{bx + rw + 0.02:.4f},{by + rw + 0.02:.4f},{p.tp + max(tw, 0.0) + 0.001:.4f}}};")
    L.append("Field[3] = Distance; Field[3].CurvesList = {hc[]}; Field[3].Sampling = 40;")
    L.append("Field[4] = Threshold; Field[4].InField = 3;")
    L.append(f"Field[4].SizeMin = {hh:.4f}; Field[4].SizeMax = {lc:.4f};")
    L.append(f"Field[4].DistMin = {0.15:.4f}; Field[4].DistMax = {0.15 + 4 * hh:.4f};")
    L.append("Field[5] = Min; Field[5].FieldsList = {2, 4};")
    hmin = min(hmin, 0.8 * hh)
    L.append("Background Field = 5;")
    L.append("Mesh.MeshSizeExtendFromBoundary = 0;")
    L.append("Mesh.CharacteristicLengthMax = lc;")
    L.append(f"Mesh.CharacteristicLengthMin = {hmin*0.8:.4f};")
    L.append("Mesh.MeshSizeFromCurvature = 12;")
    L.append("Geometry.OCCSewFaces = 1;")
    L.append("Geometry.Tolerance = 1e-6;")
    L.append("Mesh.ElementOrder = 2;")
    L.append("Mesh.SecondOrderIncomplete = 1;")
    L.append("Mesh.SecondOrderLinear = 1;   // nodos medios en el punto medio de la arista recta: evita jacobianos negativos en tetraedros delgados junto a superficies curvas")
    L.append("Mesh.Algorithm3D = 1;    // Delaunay: mas tolerante con geometrias fusionadas")
    L.append("Mesh.Optimize = 1;")

    out = Path(path)
    out.write_text("\n".join(L), encoding="utf-8")
    return str(out)


def _weld_path(prj: Project):
    """Segmentos del cordon de soldadura en la huella del perfil."""
    s = prj.section.shape()
    ext, _ = G.profile_outline(prj)
    segs = []
    for i in range(len(ext) - 1):
        x1, y1 = ext[i]
        x2, y2 = ext[i + 1]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy)
        if n < 1e-9:
            continue
        segs.append((x1, y1, x2, y2, -dy / n, dx / n))
    return segs


# ============================================================ driver Python
DRIVER = '''# -*- coding: utf-8 -*-
"""Malla el .geo con Gmsh, escribe el .inp de CalculiX y lo resuelve.

    python correr_3d.py            # malla + resuelve
    python correr_3d.py --solo-malla
"""
import os, re, subprocess, sys, math

AQUI   = os.path.dirname(os.path.abspath(__file__))
GEO    = os.path.join(AQUI, "{stem}.geo")
MSH    = os.path.join(AQUI, "{stem}_malla.inp")
INP    = os.path.join(AQUI, "{stem}.inp")
GMSH   = r"{gmsh}"
CCX    = r"{ccx}"

E, NU  = {E:.1f}, {NU}
KS     = {ks:.6f}          # modulo de balasto, kip/in3
KB     = {kb:.4f}          # rigidez axial de un perno, kip/in
PU, MUX, MUY = {Pu:.5f}, {Mux:.5f}, {Muy:.5f}
VUX, VUY     = {Vux:.5f}, {Vuy:.5f}
ZTOP   = {ztop:.6f}
CX, CY = {colx:.6f}, {coly:.6f}      # centro de la columna respecto al centro de la placa
TP     = {tp:.6f}
RHOLE  = {rhole:.6f}
RWASH  = {rwash:.6f}
PERNOS = {bolts}

def malla():
    print("[1/3] Gmsh ...")
    r = subprocess.run([GMSH, GEO, "-3", "-format", "inp", "-o", MSH],
                       capture_output=True, text=True)
    print(r.stdout[-2500:] or r.stderr[-2500:])
    if not os.path.exists(MSH):
        raise SystemExit("Gmsh no genero la malla. Revise la ruta de gmsh y el .geo")

def leer_malla():
    nodos, elems, nsets = {{}}, [], {{}}
    modo, actual = None, None
    for ln in open(MSH, encoding="utf-8", errors="ignore"):
        t = ln.strip()
        if not t: continue
        if t.upper().startswith("*NODE"):
            modo = "N"; continue
        if t.upper().startswith("*ELEMENT"):
            modo = "E"
            actual = "C3D10" if "C3D10" in t.upper() else ("C3D4" if "C3D4" in t.upper() else None)
            continue
        if t.upper().startswith("*NSET"):
            modo = "S"
            m = re.search(r"NSET\\s*=\\s*([^,]+)", t, re.I)
            actual = m.group(1).strip() if m else "X"
            nsets.setdefault(actual, [])
            continue
        if t.startswith("*"):
            modo = None; continue
        v = [x.strip() for x in t.rstrip(",").split(",") if x.strip()]
        if modo == "N" and len(v) >= 4:
            nodos[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]))
        elif modo == "E" and actual and len(v) >= 5:
            elems.append((actual, int(v[0]), [int(x) for x in v[1:]]))
        elif modo == "S":
            nsets[actual] += [int(x) for x in v]
    return nodos, elems, nsets

def escribir_inp():
    print("[2/3] Escribiendo el .inp de CalculiX ...")
    nodos, elems, nsets = leer_malla()
    print(f"      {{len(nodos)}} nodos, {{len(elems)}} elementos solidos")
    tipo = elems[0][0] if elems else "C3D10"

    base  = [n for n,(x,y,z) in nodos.items() if abs(z) < 1e-4]
    tope  = [n for n,(x,y,z) in nodos.items() if abs(z-ZTOP) < 1e-4]
    # anillo de apoyo de cada tuerca: nodos de la cara superior de la placa
    # dentro de la corona  RHOLE <= r <= RWASH  alrededor del perno
    anillos = {{}}
    sup = [(n, x, y) for n, (x, y, z) in nodos.items() if abs(z - TP) < 1e-4]
    for k, (bx, by) in enumerate(PERNOS, start=1):
        ring = [n for n, x, y in sup
                if RHOLE - 1e-6 <= math.hypot(x - bx, y - by) <= RWASH + 1e-6]
        if ring:
            anillos["PERNO_%d" % k] = sorted(ring)
    print(f"      {{len(base)}} nodos en el apoyo, {{len(tope)}} en el tope, "
          f"{{len(anillos)}} anillos de perno")

    ref = max(nodos) + 1
    eid = max(e[1] for e in elems) + 1
    out = []
    out.append("** PlacaBasePro - modelo solido 3D")
    out.append("*INCLUDE, INPUT=" + os.path.basename(MSH))
    out.append(f"*NODE\\n{{ref}}, {{CX}}, {{CY}}, {{ZTOP}}")
    out.append("*NSET, NSET=NREF\\n" + str(ref))
    out.append("*NSET, NSET=NTOPE\\n" + wrap(tope))
    out.append("*MATERIAL, NAME=ACERO\\n*ELASTIC\\n%.1f, %.3f" % (E, NU))
    out.append("*SOLID SECTION, ELSET=EALL, MATERIAL=ACERO")

    # resortes del concreto: area tributaria aproximada por nodo
    A = float(len(base))
    kn = KS * ({A1:.4f} / max(A, 1.0))
    out.append("*ELEMENT, TYPE=SPRING1, ELSET=ECONC")
    for n in base:
        out.append(f"{{eid}}, {{n}}"); eid += 1
    out.append("*SPRING, ELSET=ECONC\\n3\\n%.6f" % kn)

    for k, ring in anillos.items():
        if not ring: continue
        out.append(f"*ELEMENT, TYPE=SPRING1, ELSET=E{{k}}")
        for n in ring:
            out.append(f"{{eid}}, {{n}}"); eid += 1
        out.append(f"*SPRING, ELSET=E{{k}}\\n3\\n%.6f" % (KB / len(ring)))

    out.append("*RIGID BODY, NSET=NTOPE, REF NODE=" + str(ref))
    out.append("*BOUNDARY\\n%d, 6, 6" % ref)
    out.append("*STEP\\n*STATIC")
    out.append("*CLOAD")
    out.append(f"{{ref}}, 3, {{-PU:.5f}}")
    if abs(VUX) > 0: out.append(f"{{ref}}, 1, {{VUX:.5f}}")
    if abs(VUY) > 0: out.append(f"{{ref}}, 2, {{VUY:.5f}}")
    if abs(MUX) > 0: out.append(f"{{ref}}, 4, {{MUX:.5f}}")
    if abs(MUY) > 0: out.append(f"{{ref}}, 5, {{MUY:.5f}}")
    out.append("*NODE FILE\\nU, RF")
    out.append("*EL FILE\\nS, E")
    out.append("*END STEP")
    open(INP, "w", encoding="utf-8").write("\\n".join(out))
    print("      ->", INP)

def wrap(lst, per=8):
    return "\\n".join(", ".join(str(x) for x in lst[i:i+per]) for i in range(0, len(lst), per))

def resolver():
    print("[3/3] CalculiX ...")
    stem = INP[:-4]
    r = subprocess.run([CCX, "-i", stem], capture_output=True, text=True, cwd=AQUI)
    print((r.stdout or "")[-3000:])
    frd = stem + ".frd"
    print("Resultados:", frd if os.path.exists(frd) else "NO se genero el .frd")
    print("Abralo en PrePoMax o CalculiX GraphiX (cgx -v archivo.frd)")

if __name__ == "__main__":
    malla()
    escribir_inp()
    if "--solo-malla" not in sys.argv:
        resolver()
'''


def write_driver(prj: Project, folder: str, stem: str) -> str:
    p, b = prj.plate, prj.bolts
    g = b.geom()
    ks = (prj.fea.ks_manual if prj.fea.ks_mode == "manual"
          else Ec_ksi(prj.conc.fc) / max(6.0, prj.conc.ha))
    kb = ES_KSI * g.Ase / max(b.hef + p.tp + p.grout, 1.0)
    s = prj.section.shape()
    H = max(3.0 * s.d, 12.0)
    txt = DRIVER.format(
        stem=stem, gmsh=prj.fea.gmsh_path or "gmsh", ccx=prj.fea.ccx_path or "ccx",
        E=ES_KSI, NU=NU_STEEL, ks=ks, kb=kb,
        Pu=prj.cloads.Pu, Mux=prj.cloads.Mux, Muy=prj.cloads.Muy,
        Vux=prj.cloads.Vux, Vuy=prj.cloads.Vuy,
        ztop=p.tp + H, A1=p.Nc * p.Bc, tp=p.tp, colx=G.col_shift(prj)[0], coly=G.col_shift(prj)[1],
        rhole=g.dh / 2.0, rwash=max(g.Fhex, 2.2 * g.db) / 2.0,
        bolts=repr([(round(x, 6), round(y, 6)) for x, y in G.bolt_positions(prj)]))
    out = Path(folder) / "correr_3d.py"
    out.write_text(txt, encoding="utf-8")
    return str(out)


def auto_mesh_size(prj: Project) -> float:
    """Tamano de elemento AUTOMATICO (in), calculado del propio proyecto.

    Estudio de convergencia (placa 500×500×20 mm, 1000 kN de traccion, 5 mallas): el von Mises promediado
    converge (±2 %) cuando el radio de promedio r es al menos ~0.85 veces el tamano del elemento y la traccion
    en pernos converge con cualquier malla.  Por eso:
        malla por convergencia   lc = 1.2 · r          r = (factor de radio) · tp
        malla por costo          lc = √(area de la placa / 400)   (≈ 70-90 mil nodos en total)
    y se toma la MAYOR de las dos (con placas grandes manda el costo: el calculo no se queda iterando y el
    radio de promedio sube a lc, como hace full_3d), sin pasar de 1/4 del lado menor de la placa."""
    p = prj.plate
    area = (math.pi * p.Dp ** 2 / 4.0) if p.shape == "Circular" else p.Nc * p.Bc
    side = p.Dp if p.shape == "Circular" else min(p.Nc, p.Bc)
    lc_conv = 1.2 * max(prj.fea.vm_avg_factor, 0.1) * p.tp
    lc_cost = math.sqrt(max(area, 1.0) / 400.0)
    return max(0.25, min(max(lc_conv, lc_cost), side / 4.0))


def mesh_size_for(prj: Project) -> float:
    """Tamano de malla 3D: el valor manual si se fijo; si no, el automatico (x 0.65 en el modo "Fina").

    Con acero elasto-plastico (por defecto) el automatico se agranda 1.33 veces: en el estudio de malla de PB-01 (61 / 81 / 102 / 127 mm) la
    traccion en pernos, la presion de contacto, el desplazamiento y el D/C de la soldadura cambian < 2 % (la malla del cordon sigue en
    ~28 mm) y el tiempo total baja de 99 s a 56 s; solo el von Mises promediado de la placa (informativo con plasticidad) baja 8 %.  Sin
    plasticidad el von Mises promediado SI se verifica (≤ 0.9·Fy) y se conserva la malla de siempre."""
    if prj.fea.mesh3d and prj.fea.mesh3d > 0:
        return float(prj.fea.mesh3d)
    if str(getattr(prj.fea, "mesh3d_mode", "")).startswith("Fina"):
        return 0.65 * auto_mesh_size(prj)
    lc = auto_mesh_size(prj)
    if getattr(prj.fea, "plastic", False):
        p = prj.plate
        side = p.Dp if p.shape == "Circular" else min(p.Nc, p.Bc)
        lc = min(1.33 * lc, side / 4.0)
    return lc


def is_fast_mesh(prj: Project) -> bool:
    """True si el tamano es el automatico (ni manual ni 'Fina')."""
    return (not (prj.fea.mesh3d and prj.fea.mesh3d > 0)) and \
        not str(getattr(prj.fea, "mesh3d_mode", "")).startswith("Fina")


def export_3d(prj: Project, geo_path: str, mesh_size: float = 0.0):
    """Escribe el .geo y su driver.  Devuelve (geo, driver)."""
    geo = write_geo(prj, geo_path, mesh_size)
    folder = str(Path(geo_path).parent)
    stem = Path(geo_path).stem
    drv = write_driver(prj, folder, stem)
    return geo, drv


def app_dir() -> Path:
    """Carpeta del programa: junto al .exe si esta compilado, o la raiz del
    proyecto si corre desde el codigo fuente."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def ccx_exe(user: str = "") -> str:
    """CalculiX a usar: el que indique el usuario, si existe; si no el incluido
    en solvers/calculix; si no, el que este en el PATH."""
    if user and user.strip() and user.strip().lower() not in ("ccx", "ccx.exe") \
            and Path(user).exists():
        return user
    if os.name == "nt":
        for q in (app_dir() / "solvers" / "calculix" / "ccx.exe",
                  app_dir() / "solvers" / "calculix" / "ccx_2.14_MT.exe"):
            if q.exists():
                return str(q)
    return "ccx"


def _self_cmd():
    """Como invocar a este mismo programa en un proceso hijo."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(app_dir() / "run.py")]


class CancelToken:
    """Permite cancelar el analisis desde la interfaz: mata el proceso (Gmsh o CalculiX) en curso."""
    def __init__(self):
        self.cancelled = False
        self.proc = None

    def cancel(self):
        self.cancelled = True
        pr = self.proc
        if pr is not None and pr.poll() is None:
            try:
                pr.kill()
            except Exception:
                pass


def _run_proc(cmd, cancel=None, timeout=7200, cwd=None, env=None):
    """Ejecuta un proceso y espera su fin revisando la cancelacion.  -> (returncode, salida, estado)
    con estado 'ok' | 'cancelado' | 'tiempo'."""
    import tempfile
    import time
    flags = 0x08000000 if os.name == "nt" else 0          # sin ventana de consola
    tmp = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="ignore")
    pr = subprocess.Popen(cmd, stdout=tmp, stderr=subprocess.STDOUT, cwd=cwd, env=env, creationflags=flags)
    if cancel is not None:
        cancel.proc = pr
    t0, state = time.time(), "ok"
    while pr.poll() is None:
        if cancel is not None and cancel.cancelled:
            pr.kill(); state = "cancelado"; break
        if time.time() - t0 > timeout:
            pr.kill(); state = "tiempo"; break
        time.sleep(0.2)
    try:
        pr.wait(timeout=10)
    except Exception:
        pass
    if cancel is not None:
        cancel.proc = None
    tmp.seek(0)
    out = tmp.read()
    tmp.close()
    return pr.returncode, out, state


def run_gmsh(geo_path: str, gmsh_exe: str = "", timeout: int = 1800, cancel=None):
    """Malla el .geo con la libreria de Gmsh incluida (proceso hijo).
    Devuelve (ok, salida, ruta_inp)."""
    p = Path(geo_path)
    out = str(p.with_name(p.stem + "_malla.inp"))
    try:
        if Path(out).exists():
            Path(out).unlink()                              # una malla vieja no debe pasar por nueva
        rc, txt, state = _run_proc(_self_cmd() + ["--mesh", str(p), out], cancel, timeout)
        if state == "cancelado":
            return False, "Analisis cancelado por el usuario.", out
        if state == "tiempo":
            return False, "Gmsh excedio el tiempo limite.", out
        return Path(out).exists(), txt, out
    except Exception as e:
        return False, f"No se pudo lanzar el mallador: {e}", out


# ============================================ pipeline 3D desde la aplicacion
def bottom_weights(nodes: dict, elems: list, z0: float = 0.0, tol: float = 1e-4) -> dict:
    """Area tributaria de cada nodo de la cara libre inferior (z = z0).
    Es lo que hace falta para que el resorte de Winkler del concreto (ks·A) no dependa
    de que la malla sea mas fina en una zona que en otra.
      C3D10 : regla de los puntos medios (exacta para cuadraticas): A/3 en cada nodo
              de lado del triangulo, 0 en los vertices.
      C3D4  : A/3 en cada vertice.
    Solo cuenta las caras exteriores (las que pertenecen a un solo tetraedro)."""
    faces = {}
    for e in elems:
        c = e[:4]
        for f, opp in (((0, 1, 2), 3), ((0, 1, 3), 2), ((0, 2, 3), 1), ((1, 2, 3), 0)):
            key = tuple(sorted((c[f[0]], c[f[1]], c[f[2]])))
            faces.setdefault(key, []).append((e, f))
    w = {}
    for key, lst in faces.items():
        if len(lst) != 1:
            continue
        if not all(abs(nodes[n][2] - z0) < tol for n in key):
            continue
        e, f = lst[0]
        a, b, c = (nodes[e[f[0]]], nodes[e[f[1]]], nodes[e[f[2]]])
        ux, uy = b[0] - a[0], b[1] - a[1]
        vx, vy = c[0] - a[0], c[1] - a[1]
        area = 0.5 * abs(ux * vy - uy * vx)
        if len(e) >= 10:
            mids = e[4:10]
            for (i, j) in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                pi, pj = nodes[e[i]], nodes[e[j]]
                mx_, my_ = 0.5 * (pi[0] + pj[0]), 0.5 * (pi[1] + pj[1])
                best = min(mids, key=lambda n: (nodes[n][0] - mx_) ** 2 + (nodes[n][1] - my_) ** 2)
                w[best] = w.get(best, 0.0) + area / 3.0
        else:
            for n in key:
                w[n] = w.get(n, 0.0) + area / 3.0
    return w


def build_inp(prj: Project, mesh_inp: str, out_inp: str, height: float = 0.0) -> str:
    """Toma la malla que escribio Gmsh y arma el .inp de CalculiX: material,
    apoyo del concreto, resortes de perno, acople de carga y paso estatico."""
    from .view3d import read_mesh_inp
    import os

    p, b = prj.plate, prj.bolts
    g = b.geom()
    s = prj.section.shape()
    H = height if height > 0 else max(3.0 * s.d, 12.0)
    ztop = p.tp + H
    ks = (prj.fea.ks_manual if prj.fea.ks_mode == "manual"
          else Ec_ksi(prj.conc.fc) / max(6.0, prj.conc.ha))
    Lb = max(b.hef + p.tp + p.grout, 1.0)
    kb = ES_KSI * g.Ase / Lb                      # rigidez axial del perno
    Gs = ES_KSI / (2.0 * (1.0 + NU_STEEL))
    kbh = Gs * g.Ase / Lb

    # soldadura: con el modelo de conectores se separan el cuerpo superior (perfil, rigidizadores) y el
    # inferior (placa, llave) duplicando los nodos de la interfaz (ver weldfe)
    split = None
    if str(getattr(prj.fea, "weld_model", "")).startswith("Conectores"):
        from . import weldfe
        sp = str(Path(mesh_inp).with_name(Path(mesh_inp).stem + "_split.inp"))
        split = weldfe.split_interface(mesh_inp, sp, p.tp, prj)
        if split is not None:
            mesh_inp = sp

    nodes, elems = read_mesh_inp(mesh_inp)
    if not nodes or not elems:
        raise RuntimeError("La malla no contiene nodos o elementos solidos.")

    # Gmsh nombra los ELSET de volumen como VolumeNNN (y define ACERO como la
    # union de todos); se toman los reales del archivo en vez de inventar uno.
    vol_sets, cps = [], []
    for ln in Path(mesh_inp).read_text(encoding="utf-8",
                                       errors="ignore").splitlines():
        t = ln.strip()
        if not t.upper().startswith("*ELEMENT"):
            continue
        m = re.search(r"ELSET\s*=\s*([^,\s]+)", t, re.I)
        if not m:
            continue
        name = m.group(1)
        if re.search(r"TYPE\s*=\s*C3D", t, re.I):
            vol_sets.append(name)
        else:
            cps.append(name)          # cascaras 2D parasitas de Gmsh
    if not vol_sets:
        raise RuntimeError("La malla no declara ningun ELSET de volumen (C3D).")

    base = [n for n, (x, y, z) in nodes.items() if abs(z) < 1e-4]
    tope = [n for n, (x, y, z) in nodes.items() if abs(z - ztop) < 1e-4]
    if not base or not tope:
        raise RuntimeError("No se localizaron las caras de apoyo o de carga en la "
                           "malla.  Revise la altura del perfil en el .geo.")

    r_hole = g.dh / 2.0
    r_wash = washer_radius(prj)
    z_nut = p.tp + max(washer_thickness(prj), 0.0)             # cara superior donde apoya la tuerca
    sup = [(n, x, y) for n, (x, y, z) in nodes.items() if abs(z - z_nut) < 1e-4]    # cara de apoyo de la tuerca
    inf = [(n, x, y) for n, (x, y, z) in nodes.items() if abs(z) < 1e-4]            # cara inferior

    def ring_of(cands, bx, by, nmin=4):
        """Nodos del anillo de apoyo de un perno (entre el borde del agujero y el radio de la
        arandela); con malla gruesa toma los nmin mas cercanos al borde del agujero."""
        d = sorted((math.hypot(x - bx, y - by), n) for n, x, y in cands)
        d = [(r_, n) for r_, n in d if r_ >= r_hole - 1e-6]
        ring = [n for r_, n in d if r_ <= r_wash + 1e-6]
        if len(ring) < nmin:
            ring = [n for _, n in d[:nmin]]
        return sorted(ring)

    # Traccion/compresion del perno: la tuerca apoya en el anillo de la CARA SUPERIOR.
    # Cortante del perno: se devuelve en el plano de la CARA INFERIOR (interfaz con el mortero,
    # donde esta el centro de giro de la placa); si estuvieran arriba, el giro de la placa
    # (θ·tp) movería sus resortes horizontales y añadiría una rigidez de giro artificial que
    # crece con tp² y falsea la fuerza de los pernos en placas gruesas.
    rings, hrings = {}, {}
    for k, (bx, by) in enumerate(G.bolt_positions(prj), start=1):
        ring = ring_of(sup, bx, by)
        if ring:
            rings[k] = ring
            hrings[k] = ring_of(inf, bx, by)

    ref = max(nodes) + 1
    # el mayor numero de elemento de la malla (Gmsh numera tambien lineas y
    # triangulos), para que los resortes nuevos no choquen con ninguno
    emax, mode = 0, False
    for ln in Path(mesh_inp).read_text(encoding="utf-8", errors="ignore").splitlines():
        t = ln.strip().lstrip("*").strip() if ln.startswith("**") else ln.strip()
        if ln.startswith("**"):
            ln = ln[2:].strip()
        up = ln.strip().upper()
        if up.startswith("*ELEMENT"):
            mode = True; continue
        if up.startswith("*"):
            mode = False; continue
        if mode and ln.strip():
            try:
                emax = max(emax, int(ln.split(",")[0]))
            except ValueError:
                pass
    eid = max(emax, max(nodes)) + 1

    def wrap(lst, per=8):
        return "\n".join(", ".join(str(x) for x in lst[i:i + per])
                         for i in range(0, len(lst), per))

    from .params3d import shear_arm
    # con llave el cortante se devuelve a media altura de la llave (H/2 bajo la cara inferior)
    z_arm = shear_arm(prj) - (0.5 * prj.lug.H if prj.lug.enabled else 0.0)

    L = ["** PlacaBasePro - modelo solido 3D",
         f"** {prj.name} / {prj.element}",
         "*INCLUDE, INPUT=" + os.path.basename(mesh_inp),
         # nodo de referencia: el cortante actua a la altura e (el mismo brazo del 2D y del calculo
         # lineal, fea.shear_arm) sobre el plano donde los pernos lo devuelven (cara inferior de
         # la placa): el par V·e llega a la placa igual que en el 2D.  e = 0 -> en la cara inferior.
         "*NODE", f"{ref}, {G.col_shift(prj)[0]:.6f}, {G.col_shift(prj)[1]:.6f}, {z_arm:.6f}",
         f"{ref + 1}, {G.col_shift(prj)[0]:.6f}, {G.col_shift(prj)[1]:.6f}, {z_arm:.6f}",
         "*NSET, NSET=NREF", str(ref),
         "*NSET, NSET=NTOPE", wrap(tope),
         "*MATERIAL, NAME=ACERO", "*ELASTIC",
         f"{ES_KSI:.1f}, {NU_STEEL:.3f}",
         ]
    plastic = bool(getattr(prj.fea, "plastic", False))
    if plastic:
        # TODAS las piezas son de acero elasto-plastico perfecto con limite φ·Fy de su propio acero (acero perfectamente plastico).
        # Cada elemento se asigna a su pieza por su centroide (igual que classify_parts): asi funciona
        # tambien con la union fusionada, donde placa, perfil y rigidizadores son un solo volumen.
        from .view3d import _covered_by_profile
        zl = max(z for (_x, _y, z) in nodes.values())
        by_cls = {"PLACA": [], "COLUMNA": [], "RIGID": [], "LLAVE": [], "ARANDELA": []}
        cur_ok = False
        for ln in Path(mesh_inp).read_text(encoding="utf-8", errors="ignore").splitlines():
            t = ln.strip()
            if t.upper().startswith("*ELEMENT"):
                cur_ok = bool(re.search(r"TYPE\s*=\s*C3D", t, re.I))
                continue
            if t.startswith("*"):
                cur_ok = False
                continue
            if cur_ok and t:
                v_ = [x_.strip() for x_ in t.rstrip(",").split(",") if x_.strip()]
                c4 = [nodes[int(n_)] for n_ in v_[1:5]]
                xc = sum(q[0] for q in c4) / 4.0
                yc = sum(q[1] for q in c4) / 4.0
                zc = sum(q[2] for q in c4) / 4.0
                if zc < 0:
                    k_ = "LLAVE"
                elif zc < p.tp:
                    k_ = "PLACA"
                elif washer_elements(prj, xc, yc, zc):
                    k_ = "ARANDELA"
                elif _covered_by_profile(prj, xc, yc):
                    k_ = "COLUMNA"
                else:
                    k_ = "RIGID"
                by_cls[k_].append(int(v_[0]))
        fy_of = {"PLACA": p.mat().Fy, "ARANDELA": p.mat().Fy, "COLUMNA": prj.section.mat().Fy,
                 "RIGID": prj.stiff.mat().Fy, "LLAVE": prj.lug.mat().Fy}
        for nm, ids_ in by_cls.items():
            if not ids_:
                continue
            fy = 0.9 * fy_of[nm]
            L += [f"*MATERIAL, NAME=M{nm}", "*ELASTIC", f"{ES_KSI:.1f}, {NU_STEEL:.3f}",
                  "*PLASTIC", f"{fy:.4f}, 0.0", f"{fy * 1.0005:.4f}, 0.25",
                  f"*ELSET, ELSET=EL{nm}"]
            for i_ in range(0, len(ids_), 16):
                L.append(", ".join(str(x_) for x_ in ids_[i_:i_ + 16]))
            L.append(f"*SOLID SECTION, ELSET=EL{nm}, MATERIAL=M{nm}")
    else:
        for vs in vol_sets:
            L.append(f"*SOLID SECTION, ELSET={vs}, MATERIAL=ACERO")
    if cps:
        L.append("** ELSET de superficie que exporta Gmsh y CalculiX no usa: "
                 + ", ".join(sorted(set(cps))[:6]))

    # --- concreto: SOLO COMPRESION.  Curva fuerza-desplazamiento con rigidez
    #     ks·A_trib al bajar y practicamente cero al subir (la placa se despega).
    # rigidez por nodo = ks · area tributaria del nodo (no un valor uniforme: la malla es
    # mas fina cerca del perfil y un reparto por nodo cargaria de rigidez esa zona)
    wts = bottom_weights(nodes, elems)
    if not wts:                                   # respaldo: reparto uniforme
        wts = {n: (p.Nc * p.Bc) / max(len(base), 1) for n in base}
    kn = ks * sum(wts.values()) / max(len(wts), 1)          # valor medio (informativo)
    D = 50.0                                      # rango de la curva, in
    # Los resortes unilaterales se modelan como SPRINGA (entre dos nodos) contra
    # un nodo de tierra fijo situado 1 in por debajo: acortarse = compresion.
    gnodes, gid = [], max(nodes) + 20
    def ground(n):
        nonlocal gid
        x, y, z = nodes[n]
        gnodes.append((gid, x, y, z - 1.0))
        gid += 1
        return gid - 1
    conc_pairs = [(n, ground(n)) for n in base if n in wts]
    ring_pairs = {k: [(n, ground(n)) for n in ring] for k, ring in rings.items()}
    L.append("*NODE, NSET=NTIERRA")
    for (i, x, y, z) in gnodes:
        L.append(f"{i}, {x:.6f}, {y:.6f}, {z:.6f}")
    eid = max(eid, gid + 1)
    # los pesos se agrupan en clases de ~8 % (un ELSET de resorte por clase)
    classes = {}
    for (n, gn) in conc_pairs:
        classes.setdefault(int(round(math.log(max(wts[n], 1e-9)) / math.log(1.08))), []).append((n, gn))
    for ci, lst in sorted(classes.items()):
        kc = ks * sum(wts[n] for n, _ in lst) / len(lst)
        L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET=ECONC{ci + 200}")
        for (n, gn) in lst:
            L.append(f"{eid}, {n}, {gn}")
            eid += 1
        L += [f"*SPRING, ELSET=ECONC{ci + 200}, NONLINEAR",
              f"{-kc*D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kc*1e-5*D:.6e}, {D:.1f}"]

    # --- pernos: resorte vertical (traccion/compresion) y horizontales, que son
    #     los que equilibran el cortante e impiden el movimiento de cuerpo rigido
    for k, ring in rings.items():
        kr = kb / len(ring)
        L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET=EPERNO{k}")
        for (n, gn) in ring_pairs[k]:
            L.append(f"{eid}, {n}, {gn}")
            eid += 1
        # perno: SOLO TRACCION (la tuerca retiene a la placa cuando sube)
        L += [f"*SPRING, ELSET=EPERNO{k}, NONLINEAR",
              f"{-kr*1e-5*D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kr*D:.6e}, {D:.1f}"]
        hr = hrings.get(k) or ring
        for dof in (1, 2):
            L.append(f"*ELEMENT, TYPE=SPRING1, ELSET=EPERNO{k}H{dof}")
            for n in hr:
                L.append(f"{eid}, {n}")
                eid += 1
            L += [f"*SPRING, ELSET=EPERNO{k}H{dof}", str(dof),
                  f"{kbh / len(hr):.6f}"]

    # --- llave de corte: si existe, toma el cortante por aplastamiento contra
    #     el concreto.  Se modela como resortes horizontales en sus caras.
    if prj.lug.enabled:
        klug = 4.0 * Ec_ksi(prj.conc.fc)          # kip/in por nodo, orden de magnitud
        lug_nodes = [n for n, (x, y, z) in nodes.items() if z < -1e-4]
        if lug_nodes:
            for dof in (1, 2):
                L.append(f"*ELEMENT, TYPE=SPRING1, ELSET=ELLAVE{dof}")
                for n in lug_nodes:
                    L.append(f"{eid}, {n}")
                    eid += 1
                L += [f"*SPRING, ELSET=ELLAVE{dof}", str(dof),
                      f"{klug:.6f}"]

    # --- rigidez horizontal residual en el apoyo (friccion placa-mortero);
    #     evita la singularidad si no se localizo ningun anillo
    kfric = max(1e-3, 0.05 * kbh * max(len(rings), 1) / max(len(base), 1))
    for dof in (1, 2):
        L.append(f"*ELEMENT, TYPE=SPRING1, ELSET=EFRIC{dof}")
        for n in base:
            L.append(f"{eid}, {n}")
            eid += 1
        L += [f"*SPRING, ELSET=EFRIC{dof}", str(dof), f"{kfric:.8f}"]

    # --- soldadura perfil-placa como conectores entre los cuerpos separados
    wmeta = None
    if split is not None:
        from . import weldfe
        recs, _walls_, _ = weldfe.match_lines(prj, split, weldfe.boundary_edges(split))
        wcards, eid, wmeta = weldfe.write_cards(prj, split, recs, eid)
        L += wcards

    ld = prj.cloads        # las cargas actuan en el eje de la columna (el FEM ya incluye la excentricidad)
    # En CalculiX los giros de un cuerpo rigido viven en un nodo aparte
    # (ROT NODE): sus grados 1, 2, 3 son las rotaciones y ahi van los momentos.
    rot = ref + 1
    L += [f"*RIGID BODY, NSET=NTOPE, REF NODE={ref}, ROT NODE={rot}",
          "*BOUNDARY", "NTIERRA, 1, 3",
          "*STEP, NLGEOM, INC=300", "*STATIC", "0.25, 1.0, 1e-3, 1.0", "*CLOAD",
          f"{ref}, 3, {-ld.Pu:.5f}"]
    if abs(ld.Vux) > 0:
        L.append(f"{ref}, 1, {ld.Vux:.5f}")
    if abs(ld.Vuy) > 0:
        L.append(f"{ref}, 2, {ld.Vuy:.5f}")
    if abs(ld.Mux) > 0:
        L.append(f"{rot}, 1, {ld.Mux:.5f}")          # traccion en +Y
    if abs(ld.Muy) > 0:
        L.append(f"{rot}, 2, {ld.Muy:.5f}")
    L += ["*NODE FILE", "U, RF", "*EL FILE", "S, E" + (", PEEQ" if plastic else ""), "*END STEP"]

    Path(out_inp).write_text("\n".join(L), encoding="utf-8")
    import json
    meta = {"ks": ks, "kn": kn, "kb": kb, "tp": p.tp, "ztop": ztop,
            "rings": {str(k): v for k, v in rings.items()},
            "ring_ground": {str(k): [g for _, g in v] for k, v in ring_pairs.items()},
            "base": base, "base_ground": [g for _, g in conc_pairs],
            "n_bolts": len(G.bolt_positions(prj)), "mesh_used": os.path.basename(mesh_inp)}
    if wmeta is not None:
        meta["conn"] = wmeta
    Path(out_inp).with_suffix(".meta.json").write_text(json.dumps(meta),
                                                        encoding="utf-8")
    return out_inp


def run_ccx(inp_path: str, ccx_path: str = "", timeout: int = 7200, cancel=None):
    """Resuelve con CalculiX.  Devuelve (ok, salida, ruta_frd)."""
    p = Path(inp_path)
    stem = str(p.with_suffix(""))
    frd = stem + ".frd"
    exe = ccx_exe(ccx_path)
    env = dict(os.environ)
    ncpu = str(max(1, os.cpu_count() or 1))
    env.setdefault("OMP_NUM_THREADS", ncpu)
    env.setdefault("CCX_NPROC_EQUATION_SOLVER", ncpu)
    env.setdefault("CCX_NPROC_STIFFNESS", ncpu)
    try:
        if Path(frd).exists():
            Path(frd).unlink()
        rc, out, state = _run_proc([exe, "-i", p.stem], cancel, timeout, cwd=str(p.parent), env=env)
        if state == "cancelado":
            return False, "Analisis cancelado por el usuario.", frd
        if state == "tiempo":
            return False, "CalculiX excedio el tiempo limite.", frd
        return Path(frd).exists(), out, frd
    except FileNotFoundError:
        return False, (f"No se encontro CalculiX ('{exe}').  Deberia estar en "
                       f"solvers\\calculix junto al programa."), frd


CANCELADO = "Analisis cancelado por el usuario."


def full_3d(prj: Project, folder: str, stem: str = "modelo3d", progress=None, cancel=None):
    """Geometria -> malla -> .inp -> CalculiX -> resultados, con cancelacion y reintentos.

    Si Gmsh o CalculiX fallan (tetraedros invalidos, sin convergencia, sin memoria) se reintenta hasta dos
    veces con una malla mas gruesa (x1.35 y x1.8), porque en placas grandes o con detalles pequenos la malla
    manda en la robustez.  `progress` recibe mensajes de avance; `cancel` es un CancelToken."""
    def say(m_):
        if progress:
            progress(m_)

    lc0 = mesh_size_for(prj)
    last = "No se pudo completar el analisis."
    import copy
    elastic = copy.deepcopy(prj)
    elastic.fea.plastic = False
    elastic.fea.weld_criterion = "Elastico (pico limitado y media)"
    plan = ([(prj, 1.0)] if getattr(prj.fea, "plastic", False) else [])
    if str(getattr(prj.fea, "weld_criterion", "")).startswith("Plastico") and getattr(prj.fea, "plastic", False):
        weld_el = copy.deepcopy(prj)                   # plasticidad en las piezas pero cordon elastico
        weld_el.fea.weld_criterion = "Elastico (pico limitado y media)"
        plan.append((weld_el, 1.0))
    plan += [(elastic if getattr(prj.fea, "plastic", False) else prj, f) for f in (1.0, 1.35, 1.8)]
    for k, (pj, f) in enumerate(plan):
        if cancel is not None and cancel.cancelled:
            return None, CANCELADO
        lc = lc0 * f
        fallback = pj is elastic
        weld_fb = (pj is not prj) and (not fallback) and pj.fea.plastic
        tag = "" if k == 0 else ("  (el cordon plastico no convergio: cordon elastico)" if weld_fb else
                                 "  (la plasticidad no convergio: criterio elastico)" if (fallback and k == 1)
                                 else f"  (reintento con malla mas gruesa x{f:g})")
        res, msg = _full_3d_once(pj, folder, stem, lc, say, cancel, tag)
        if res is not None or (cancel is not None and cancel.cancelled) or msg == CANCELADO:
            if res is not None and weld_fb:
                res.msg += "   (El cordon plastico no convergio en este caso: se uso el cordon elastico, con pico limitado.)"
            if res is not None and fallback:
                res.msg += "   (La plasticidad no convergio en este caso: se uso el criterio elastico de von Mises promediado.)"
            return res, (CANCELADO if (cancel is not None and cancel.cancelled) else (res.msg if res is not None else msg))
        last = msg
    return None, last + "\n\n(Se probaron tres tamanos de malla; revise la geometria o aumente el tamano manual.)"


def _full_3d_once(prj, folder, stem, lc, say, cancel, tag=""):
    Path(folder).mkdir(parents=True, exist_ok=True)
    geo = str(Path(folder) / f"{stem}.geo")
    say(f"1/4  Escribiendo la geometria solida ...{tag}")
    export_3d(prj, geo, lc)

    say(f"2/4  Mallando con Gmsh (elemento de {lc * 25.4:.0f} mm = {lc:.2f} in) ...{tag}")
    ok, out, mesh_inp = run_gmsh(geo, cancel=cancel)
    if cancel is not None and cancel.cancelled:
        return None, CANCELADO
    if not ok:
        return None, f"Gmsh no genero la malla.\n\n{out[-3000:]}"

    say("3/4  Armando el modelo de CalculiX ...")
    _strip_shells(mesh_inp)
    inp = str(Path(folder) / f"{stem}_ccx.inp")
    try:
        build_inp(prj, mesh_inp, inp)
    except Exception as e:
        return None, f"No se pudo armar el .inp: {e}"

    say(f"4/4  Resolviendo con CalculiX ...{tag}")
    ok, out, frd = run_ccx(inp, prj.fea.ccx_path, cancel=cancel)
    if cancel is not None and cancel.cancelled:
        return None, CANCELADO
    if not ok:
        return None, f"CalculiX no genero resultados.\n\n{out[-3000:]}"

    say("Leyendo resultados y revisando la soldadura ...")
    from .view3d import load_results
    from .weld3d import postprocess
    import json as _json
    try:                                            # con conectores la malla es la separada
        mu = _json.loads(Path(inp).with_suffix(".meta.json").read_text(encoding="utf-8")).get("mesh_used")
        if mu:
            mesh_inp = str(Path(mesh_inp).with_name(mu))
    except Exception:
        pass
    res = load_results(mesh_inp, frd)
    if getattr(prj.fea, "plastic", False):
        try:
            from .view3d import read_peeq
            res.peeq = read_peeq(frd)
        except Exception:
            res.peeq = {}
    if not res.ok:
        err = [ln for ln in out.splitlines() if "*ERROR" in ln][:3]
        return None, res.msg + ("\n" + "\n".join(err) if err else "")
    res.lc = lc
    try:
        from .view3d import classify_parts
        res.parts = classify_parts(res, prj)
    except Exception:
        res.parts = {}
    if getattr(res, "peeq", None):
        try:
            from .view3d import part_peeq, clip_vm_to_yield
            res.vm_clipped = clip_vm_to_yield(res, prj)
            res.peeq_parts = part_peeq(res, prj, max(prj.plate.tp, lc / 1.2))
        except Exception as e:
            res.peeq_parts = {}
            res.msg += f"   (PEEQ por pieza no disponible: {e})"
    try:                                            # caras de la interfaz: no son superficie visible
        dup = set(_json.loads(Path(inp).with_suffix(".meta.json").read_text(encoding="utf-8"))
                  .get("conn", {}).get("dup", {}).values())
        if dup:
            res.tris = [t for t in res.tris if not all(n in dup for n in t)]
    except Exception:
        pass
    try:
        res.post = postprocess(prj, res, str(Path(inp).with_suffix(".meta.json")))
    except Exception as e:
        res.post = None
        res.msg += f"   (postproceso de soldadura fallido: {e})"
    res.folder = folder
    try:
        from .view3d import smoothed_plate_vm
        p_ = prj.plate
        # el radio no baja de lc/1.2: en el estudio de convergencia el promedio es estable (±2 %) con
        # elementos de hasta 1.2 veces el radio; con menos radio por elemento no promedia
        r_avg = max(prj.fea.vm_avg_factor * p_.tp, lc / 1.2)
        res.vm_avg = smoothed_plate_vm(res, prj, r_avg)
        if res.vm_avg:
            res.msg += (f"   Von Mises PROMEDIADO en la placa (r = {res.vm_avg['radius']:.2f} in) = "
                        f"{res.vm_avg['vm']:.1f} ksi")
    except Exception as e:
        res.vm_avg = None
        res.msg += f"   (promedio de von Mises no disponible: {e})"
    try:                                            # columna y rigidizadores: promedio en la misma cara
        from .view3d import smoothed_part_vm
        res.part_avg = {k: v for k, v in
                        ((k, smoothed_part_vm(res, prj, k, r_avg)) for k in ("column", "stiff")) if v}
    except Exception as e:
        res.part_avg = {}
        res.msg += f"   (promedio en columna/rigidizadores no disponible: {e})"
    return res, res.msg


def _strip_shells(mesh_inp: str):
    """Gmsh exporta tambien los triangulos de las superficies fisicas.
    CalculiX aborta si un elemento no tiene seccion asignada, asi que esos
    bloques 2D se comentan antes de resolver."""
    p = Path(mesh_inp)
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    out, skipping = [], False
    for ln in lines:
        t = ln.strip()
        if t.upper().startswith("*ELEMENT"):
            skipping = not bool(re.search(r"TYPE\s*=\s*C3D", t, re.I))
            out.append(("** " + ln) if skipping else ln)
            continue
        if t.startswith("*"):
            skipping = False
            out.append(ln)
            continue
        out.append(("** " + ln) if skipping else ln)
    p.write_text("\n".join(out), encoding="utf-8")
