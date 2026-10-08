# -*- coding: utf-8 -*-
"""Autopruebas del motor de calculo (sin interfaz grafica)."""
import sys, math, traceback
sys.path.insert(0, ".")
for _st in (sys.stdout, sys.stderr):          # consolas de Windows (cp1252/cp850) no codifican φ, ° ni —
    try:
        _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from placabase.model import Project
from placabase.solver import solve
from placabase import geometry as G
from placabase.shapes import CATALOG, W_SHAPE, HSS_RECT, HSS_ROUND, PIPE

FAIL = []


def case(name, **mut):
    prj = Project()
    for path, val in mut.items():
        obj = prj
        parts = path.split(".")
        for q in parts[:-1]:
            obj = getattr(obj, q)
        setattr(obj, parts[-1], val)
    try:
        r = solve(prj)
    except Exception as e:
        FAIL.append(f"{name}: EXCEPCION {e}")
        traceback.print_exc()
        return None, None
    pos = G.bolt_positions(prj)
    feamsg = ""
    gov = r.governing.title[:38] if r.governing else "-"
    print(f"{name:34} n={len(pos):3d}  caso={r.br.case:13} Tu={r.br.Tu:7.1f}  "
          f"treq={r.treq:5.2f}  D/C={r.max_ratio:6.3f}  gob={gov:40}{feamsg}")
    for w in r.warnings:
        if w.startswith("**"):
            print(f"    AVISO CRITICO: {w}")
    return prj, r


print("=" * 150)
print("CASOS BASE")
print("=" * 150)
case("W14X90 base")
case("W14X90 rot 90", **{"section.rotation": 90.0})
case("W14X90 rot 30", **{"section.rotation": 30.0})
case("W14X90 M alto", **{"loads.Mux": 5200.0})
case("W14X90 traccion neta", **{"loads.Pu": -60.0, "loads.Mux": 900.0})
case("W14X90 sin momento", **{"loads.Mux": 0.0})

print()
print("PERFILES")
case("W36 grande", **{"section.label": "W24X162", "plate.N": 34.0, "plate.B": 30.0,
                      "plate.tp": 2.5, "loads.Pu": 900.0, "loads.Mux": 6000.0})
case("HSS12X12X1/2", **{"section.label": "HSS12X12X1/2", "section.steel": "ASTM A500 Gr.B (HSS rect.)"})
case("HSS8X4X1/2 rot90", **{"section.label": "HSS8X4X1/2", "section.rotation": 90.0,
                            "section.steel": "ASTM A500 Gr.B (HSS rect.)"})
case("HSS10.75X0.5 redondo", **{"section.label": "HSS10.75X0.5",
                                "section.steel": "ASTM A500 Gr.B (HSS red.)"})
case("Pipe 8 XS", **{"section.label": "Pipe 8 XS", "section.steel": "ASTM A53 Gr.B (Pipe)"})

print()
print("DISPOSICION DE PERNOS")
case("2 lados eje mayor", **{"bolts.pattern": "2 lados (eje mayor)"})
case("2 lados eje menor", **{"bolts.pattern": "2 lados (eje menor)"})
case("perim 4x2", **{"bolts.n_major": 4, "bolts.n_minor": 2})
case("perim 2x5", **{"bolts.n_major": 2, "bolts.n_minor": 5})
case("perim 5x5", **{"bolts.n_major": 5, "bolts.n_minor": 5})
case("placa circular 12 pernos", **{"plate.shape": "Circular", "plate.Dp": 30.0,
                                    "bolts.pattern": "Circular", "bolts.n_circ": 12,
                                    "section.label": "HSS10.75X0.5"})

print()
print("TIPOS DE PERNO")
for at in ["Con cabeza (hex pesada)", "Gancho en L", "Gancho en J", "Recto (sin cabeza)"]:
    case(f"anclaje {at[:22]}", **{"bolts.atype": at, "loads.Mux": 5200.0})

print()
print("DIAMETROS Y MATERIALES")
for sz in ["3/4", "1", "1-1/2", "2", "3"]:
    case(f"perno {sz}\"", **{"bolts.size": sz, "bolts.ex": 3.5, "bolts.ey": 3.5})
for st in ["ASTM F1554 Gr.36", "ASTM F1554 Gr.105", "ASTM F3125 Gr.A490"]:
    case(f"{st[5:]}", **{"bolts.steel": st, "loads.Mux": 5200.0})

print()
print("LLAVE DE CORTE Y RIGIDIZADORES")
case("llave X", **{"lug.enabled": True, "loads.Vux": 90.0})
case("llave ambos ejes", **{"lug.enabled": True, "lug.direction": "Ambos ejes",
                            "loads.Vux": 70.0, "loads.Vuy": 70.0})
case("rigidizadores alas", **{"stiff.enabled": True, "stiff.position": "Alas (paralelo a Y)"})
case("rigidizadores ambos", **{"stiff.enabled": True, "stiff.position": "Ambos", "stiff.count": 8})
case("rigid HSS perimetro", **{"section.label": "HSS12X12X1/2", "stiff.enabled": True,
                               "stiff.position": "Perimetro HSS (4 caras)", "stiff.count": 8,
                               "section.steel": "ASTM A500 Gr.B (HSS rect.)"})
case("llave + rigidizadores", **{"lug.enabled": True, "stiff.enabled": True,
                                 "loads.Vux": 90.0, "loads.Mux": 4200.0})

print()
print("SOLDADURA")
case("CJP alas", **{"welds.flange": __import__("placabase.model", fromlist=["WeldSpec"]).WeldSpec(
    "CJP (penetracion completa)", 0.0, "E70XX", True)})
case("filete chico", **{"welds.flange": __import__("placabase.model", fromlist=["WeldSpec"]).WeldSpec(
    "Filete", 0.1875, "E70XX", True), "loads.Mux": 5200.0})

print()
print("CONCRETO / SISMO")
case("no fisurado", **{"conc.cracked": False, "loads.Mux": 5200.0})
case("condicion A", **{"conc.cond_A": True, "loads.Mux": 5200.0})
case("sismico", **{"conc.seismic": True, "loads.Mux": 5200.0})
case("pedestal chico", **{"conc.N2": 26.0, "conc.B2": 26.0, "loads.Mux": 5200.0})
case("f'c 6 ksi", **{"conc.fc": 6.0, "loads.Mux": 5200.0})

print()
print("FAMILIAS AISC, SECCIONES DOBLES, PERSONALIZADAS Y LLAVES DE PERFIL")
case("L6X6X1/2", **{"section.label": "L6X6X1/2", "section.steel": "ASTM A36"})
case("2L6X6X1/2 espalda con espalda", **{"section.label": "L6X6X1/2", "section.double": True,
                                        "section.gap": 0.75})
case("2C10X15.3 rot 90", **{"section.label": "C10X15.3", "section.double": True,
                            "section.rotation": 90.0})
case("WT9X25", **{"section.label": "WT9X25"})
case("MC12X31", **{"section.label": "MC12X31"})
case("HP12X53", **{"section.label": "HP12X53"})
case("S12X35", **{"section.label": "S12X35"})
case("llave W8X31", **{"lug.enabled": True, "lug.ltype": "Perfil (cualquier seccion)",
                       "lug.label": "W8X31", "loads.Vux": 40.0})
case("llave HSS6X6X1/2 girada", **{"lug.enabled": True, "lug.ltype": "Perfil (cualquier seccion)",
                                   "lug.label": "HSS6X6X1/2", "lug.rotation": 90.0,
                                   "loads.Vuy": 30.0})
case("llave Pipe6STD", **{"lug.enabled": True, "lug.ltype": "Perfil (cualquier seccion)",
                          "lug.label": "Pipe6STD", "loads.Vux": 25.0})
case("adhesivo + coord. manuales", **{"bolts.atype": "Recto (sin cabeza)",
                                      "bolts.install": "Postinstalado adhesivo (epoxico)",
                                      "bolts.pattern": "Coordenadas manuales",
                                      "bolts.coords": [[-8.5, -8.5], [8.5, -8.5], [8.5, 8.5],
                                                       [-8.5, 8.5], [0.0, 8.5]]})

# grupo de soldadura contra calculo a mano
from placabase.shapes import CATALOG, make_custom, PLATE
from placabase.model import WeldSpec
from placabase import design as _D
CATALOG.shapes["_PLT"] = make_custom("_PLT", PLATE, 12.0, 1.0, 1.0)
_p = Project(); _p.section.label = "_PLT"
_g = _D.weld_group(_p, G.section_rects(_p), WeldSpec(size=0.5), P=-100.0)
_g2 = _D.weld_group(_p, G.section_rects(_p), WeldSpec(size=0.5), Mx=360.0)
print(f"{'grupo de soldadura (a mano)':34} traccion f={_g['fmax']:.3f} (3.846)  "
      f"momento f={_g2['fmax']:.3f} (6.000)")
if abs(_g["fmax"] - 100 / 26) > 0.01 or abs(_g2["fmax"] - 6.0) > 0.02:
    FAIL.append("grupo de soldadura: no coincide con el calculo a mano")
# seccion doble contra la tabla AISC (2L4X4X1/2, s = 3/8: Iy = 25.1 in4)
_q = Project(); _q.section.label = "L4X4X1/2"; _q.section.double = True; _q.section.gap = 0.375
_e = _q.section.eff()
print(f"{'2L4X4X1/2 s=3/8 contra AISC':34} Iy={_e.Iy:.2f} (25.1)  Ix={_e.Ix:.2f} (11.0)")
if abs(_e.Iy - 25.1) > 0.5:
    FAIL.append("seccion doble: Iy no coincide con AISC")

# columna inclinada: la proyeccion conserva la magnitud de fuerza y momento
_t = Project(); _t.loads.tilt_x = 15.0; _t.loads.tilt_y = 20.0
_e = _t.eloads
_f0 = math.hypot(_t.loads.Pu, _t.loads.Vux, _t.loads.Vuy)
_f1 = math.hypot(_e.Pu, _e.Vux, _e.Vuy)
_m1 = math.hypot(_e.Mux, _e.Muy, _e.Tz)
print(f"{'columna inclinada (15°, 20°)':34} |F| {_f0:.3f} -> {_f1:.3f}   |M| 1800 -> {_m1:.3f}")
if abs(_f0 - _f1) > 1e-6 or abs(_m1 - 1800.0) > 1e-6:
    FAIL.append("columna inclinada: la rotacion de cargas no conserva la magnitud")
_t = Project(); _t.loads.tilt_x = 30.0; _t.loads.Vux = 0.0
if abs(_t.eloads.Pu - 400 * math.cos(math.radians(30))) > 1e-6 or abs(_t.eloads.Vuy - 400 * 0.5) > 1e-6:
    FAIL.append("columna inclinada: componentes normal/tangencial incorrectas")
case("columna inclinada 20°", **{"loads.tilt_y": 20.0})

# perfil W soldado solo en el alma: la soldadura parcial debe tomar el momento
_w = Project(); _w.welds.flange.wtype = "Sin soldadura"
_rw = solve(_w)
_cp = [c for c in _rw.checks if c.key == "weld_part"]
print(f"{'W soldado solo en el alma':34} weld_part D/C = {_cp[0].ratio if _cp else float('nan'):.2f}")
if not _cp or not any("NO esta soldada" in w for w in _rw.warnings):
    FAIL.append("soldadura parcial: falta la verificacion o el aviso")

# ---- el veredicto final lo da el analisis 3D
import types
from placabase.fem_checks import Fem3D
_m = Project(); _m.loads.Mux = 4200.0
_rm = solve(_m)
if not (_rm.pending and _rm.verdict == "PENDIENTE"):
    FAIL.append("sin 3D: el veredicto debe ser PENDIENTE (realizar analisis 3D)")
if not any("REALIZAR ANALISIS 3D" in w for w in _rm.warnings):
    FAIL.append("sin 3D: falta el aviso de realizar el analisis 3D")


def _mock_fem(prj, Ts, umax=0.1):
    """Paquete 3D simulado con la traccion `Ts` de cada perno."""
    pos = G.bolt_positions(prj)
    post = types.SimpleNamespace(
        bolts=[(k + 1, x, y, T) for k, ((x, y), T) in enumerate(zip(pos, Ts))],
        p_max=1.0, R_conc=sum(Ts) + prj.eloads.Pu, T_bolts=sum(Ts), zones=[], msg="simulado")
    return Fem3D(post=post, vm_avg=dict(vm=20.0, radius=1.0, x=0, y=0, z=0), rep={}, fast=True,
                 n_nodes=1000, n_elems=500, umax=umax, vmmax=90.0, sig=prj.sig3d())


_n = len(G.bolt_positions(_m))
_Ts = [0.0] * _n; _Ts[1] = 30.0; _Ts[3] = 20.0
_r3 = solve(_m, fem=_mock_fem(_m, _Ts))
_bt = [c for c in _r3.checks if c.key == "blt_t"][0]
print(f"{'con 3D simulado':34} veredicto = {_r3.verdict}  blt_t demanda = {_bt.demand:.1f} (esperado 30.0)  "
      f"filas fem_ = {[c.key for c in _r3.checks if c.key.startswith('fem_')]}")
if _r3.pending or abs(_bt.demand - 30.0) > 1e-6:
    FAIL.append("con 3D: la fuerza del perno de diseno debe salir del 3D y el veredicto dejar de ser PENDIENTE")
if not {"fem_bolt", "fem_press", "fem_vm"} <= {c.key for c in _r3.checks}:
    FAIL.append("con 3D: faltan las filas de verificacion FEM")
if any(c.key.startswith("lin_") for c in _r3.checks) or any("lineal" in w.lower() for w in _r3.warnings):
    FAIL.append("no debe quedar nada del reparto lineal en el veredicto")
# un 3D con un perno sobrecargado debe dar NO CUMPLE
_Ts2 = [0.0] * _n; _Ts2[0] = 500.0
if solve(_m, fem=_mock_fem(_m, _Ts2)).verdict != "NO CUMPLE":
    FAIL.append("con 3D sobrecargado el veredicto debe ser NO CUMPLE")
# la firma del 3D ignora datos cosmeticos y cambia con la geometria
_q1, _q2 = Project(), Project(); _q2.name = "otro"; _q2.author = "x"
_q3 = Project(); _q3.plate.tp = 2.5
if not (_q1.sig3d() == _q2.sig3d() and _q1.sig3d() != _q3.sig3d()):
    FAIL.append("firma del 3D: debe ignorar nombre/autor y detectar cambios de geometria")
print(f"{'firma del modelo 3D':34} ok")

# vista 3D: el modelo cabe completo (sin tocar los bordes) en ventanas anchas, altas y chicas
import matplotlib
matplotlib.use("Agg")
import numpy as np
from matplotlib.figure import Figure
from PIL import Image
import io
from placabase import view3d
_vp = Project()
_ok_view = True
for _w, _h in ((10.2, 5.0), (7, 6), (4, 8), (3, 2.5)):
    _fig = Figure(figsize=(_w, _h), dpi=100)
    _ax = _fig.add_axes([0, 0, 1, 1], projection="3d")
    view3d.plot_geometry(_ax, _vp)
    _ax.set_title("", loc="left")
    _ax.view_init(elev=24, azim=-58)
    view3d.fit_to_axes(_ax)
    _buf = io.BytesIO(); _fig.savefig(_buf, format="png"); _buf.seek(0)
    _im = np.array(Image.open(_buf).convert("L"))
    _ys, _xs = np.where(_im < 245)
    _ok = _xs.min() > 1 and _ys.min() > 1 and _xs.max() < _im.shape[1] - 2 and _ys.max() < _im.shape[0] - 2
    _fill = max((_xs.max() - _xs.min()) / _im.shape[1], (_ys.max() - _ys.min()) / _im.shape[0])
    _ok_view &= _ok and _fill > 0.7
    print(f"{'vista 3D ' + str((_w, _h)):34} cabe = {_ok}   ocupa {100 * _fill:.0f} % del lado limitante")
if not _ok_view:
    FAIL.append("vista 3D: el modelo debe caber completo y ocupar ~90 % del lado limitante")

# tamano de malla 3D automatico: sube con el area de la placa (costo acotado) y respeta el manual
from placabase import mesh3d
_a = Project(); _b = Project(); _b.plate.N = _b.plate.B = 80.0
_c = Project(); _c.fea.mesh3d = 1.5
_la, _lb, _lc = mesh3d.mesh_size_for(_a), mesh3d.mesh_size_for(_b), mesh3d.mesh_size_for(_c)
print(f"{'malla 3D automatica':34} placa 22 in: {_la:.2f} in   placa 80 in: {_lb:.2f} in   manual 1.5: {_lc:.2f} in")
if not (_lb > _la and abs(_lc - 1.5) < 1e-9):
    FAIL.append("malla 3D: el tamano automatico debe crecer con la placa y el manual tener prioridad")
_tok = mesh3d.CancelToken(); _tok.cancel()
if mesh3d.full_3d(Project(), __import__("tempfile").mkdtemp(), cancel=_tok)[1] != mesh3d.CANCELADO:
    FAIL.append("cancelar antes de empezar debe devolver 'cancelado'")

print()
print("CASOS LIMITE")
case("placa insuficiente", **{"loads.Mux": 26000.0})
case("perfil mas grande que placa", **{"section.label": "W14X730", "plate.N": 14.0, "plate.B": 14.0})

# ---------------------------------------------------- combinaciones de carga y flexion del perno
from placabase.model import LoadCombo
_cb = Project()
_cb.combos = [LoadCombo("A", 400, 1800, 0, 30, 0), LoadCombo("B", -100, 0, 0, 10, 0)]
_q0, _q1 = _cb.with_combo(0), _cb.with_combo(1)
if not (_q0.loads.Pu == 400 and _q1.loads.Pu == -100 and _cb.loads.Pu == 400 and _q0.sig3d() != _q1.sig3d()):
    FAIL.append("combinaciones: with_combo no aplica las cargas de la combinacion")
_rt = Project.from_json(_cb.to_json())
if [c.name for c in _rt.combos] != ["A", "B"]:
    FAIL.append("combinaciones: no sobreviven al guardar/abrir")
_so = Project(); _so.bolts.standoff = 2.0
_Rso = solve(_so)
_k = {c.key: c for c in _Rso.checks}
if "blt_m" not in _k or "blt_tm" not in _k or _k["blt_m"].ratio <= 0:
    FAIL.append("flexion del perno: faltan las verificaciones con stand-off")
_cant = Project(); _cant.bolts.standoff = 2.0; _cant.bolts.fixity = "Voladizo (placa libre de girar)"
_kc = {c.key: c for c in solve(_cant).checks}
if abs(_kc["blt_m"].demand / _k["blt_m"].demand - 2.0) > 1e-6:
    FAIL.append("flexion del perno: voladizo debe duplicar el momento del doble empotramiento")
_ng = Project(); _ng.plate.grout = 0.0
if "blt_m" in {c.key for c in solve(_ng).checks}:
    FAIL.append("flexion del perno: sin stand-off ni mortero no debe verificarse")
if "blt_m" not in {c.key for c in solve(Project()).checks}:
    FAIL.append("flexion del perno: el mortero grueso debe verificarse")
print(f"{'flexion del perno (stand-off 2 in)':34} M/φMn = {_k['blt_m'].ratio:.3f}   voladizo = {_kc['blt_m'].ratio:.3f}")


# ---------------------------------------------------- barras U y visualizacion de cargas
from placabase.ubar import ubar
_u0 = Project(); _u0.combos = [LoadCombo("T", -300, 0, 0, 30, 0)]; _u0.apply_combo(0)
_u1 = Project.from_json(_u0.to_json()); _u1.conc.u_on = True; _u1.conc.u_n = 2; _u1.conc.u_size = "#5"
_k0 = {c.key: c for c in solve(_u0).checks}; _k1 = {c.key: c for c in solve(_u1).checks}
if not (ubar(_u0) is None and ubar(_u1) is not None):
    FAIL.append("barras U: ubar() debe existir solo si se activan")
if not (_k1["aci_ncb"].capacity > _k0["aci_ncb"].capacity and _k1["aci_vcb"].capacity > _k0["aci_vcb"].capacity):
    FAIL.append("barras U: el refuerzo debe aumentar la capacidad del arrancamiento")
if "aci_ubar_dev" not in _k1 or "aci_ubar_dev" in _k0:
    FAIL.append("barras U: fila de desarrollo de las patas")
_ub = ubar(_u1)
if abs(_ub["Nrs"] - 4 * 0.31 * 60.0) > 1e-6 or _ub["below"] < _ub["ld"] - 1e-6:
    FAIL.append("barras U: resistencia o desarrollo automatico incorrectos")
_u2 = Project.from_json(_u1.to_json()); _u2.conc.u_leg = 5.0
if _k1["aci_ubar_dev"].ratio > 1.0 or solve(_u2).checks[[c.key for c in solve(_u2).checks].index("aci_ubar_dev")].ratio <= 1.0:
    FAIL.append("barras U: una pata corta debe fallar el desarrollo")
print(f"{'barras U (2 U #5, Ncb tracc.)':34} capacidad {_k0['aci_ncb'].capacity:.1f} -> {_k1['aci_ncb'].capacity:.1f} kip   ld = {_ub['ld']:.1f} in")
_o2 = Project.from_json(_u1.to_json())
_o2.conc.u_type = "Opcion B — barras Omega (patas con gancho, ldh)"
_om = ubar(_o2)
_k2 = {c.key: c for c in solve(_o2).checks}
if _om["kind"] != "OMEGA" or _om["below"] < _om["ldh"] - 1e-6 or _om["tail"] < 12 * _om["db"] - 1e-9:
    FAIL.append("barras Omega: desarrollo o cola del gancho incorrectos")
for _k in ("aci_ubar_ten", "aci_ubar_dev", "aci_ubar_hook", "aci_ubar_fit", "aci_ubar_cover"):
    if _k not in _k2:
        FAIL.append(f"barras Omega: falta la revision {_k}")
if "aci_ubar_ten" not in {c.key for c in solve(_u1).checks} or "aci_ubar_cover" in {c.key for c in solve(_u1).checks}:
    FAIL.append("barras U: revisiones esperadas (tension, desarrollo, gancho, altura; sin recubrimiento de cola)")
print(f"{'barras Omega (2 Ω #5)':34} ldh = {_om['ldh']:.1f} in   pata = {_om['leg']:.0f} in   cola = {_om['tail']:.1f} in")
from placabase import view3d as _v3
_its, _pts = _v3.load_arrows(_u0, 1.0)
if len(_its) != 2 or not _pts:
    FAIL.append("cargas 3D: se esperaban flechas de Pu y Vux")


# ---------------------------------------------------- criterios del cordon (Ghimire et al. 2023)
try:
    from placabase import weldfe as _wf
    from placabase.model import WeldSpec as _WS
    _pw = Project()
    _sp = _WS("Filete", 0.5, _pw.welds.flange.electrode, True)
    _mk = lambda L: {"periodic": False, "spec": _sp, "p1": (0.0, 0.0), "p2": (L, 0.0)}
    _b = [_wf.long_beta(_pw, _mk(L)) for L in (40.0, 60.0, 100.0, 150.0, 200.0)]       # L/w = 80, 120, 200, 300, 400
    _exp = [1.0, 0.96, 0.8, 0.6, 0.45]
    if any(abs(a - b) > 1e-9 for a, b in zip(_b, _exp)):
        FAIL.append(f"β de cordon largo incorrecto: {_b} (esperado {_exp})")
    _pw.fea.weld_long_reduction = False
    if _wf.long_beta(_pw, _mk(200.0)) != 1.0:
        FAIL.append("β de cordon largo: la opcion desactivada debe dar 1.0")
    _f, _p = _wf.spring_force(0.001, 1000.0, 0.0005)
    if abs(_f - (0.5 + 0.0005)) > 1e-9 or abs(_p - 0.0005) > 1e-12 or _wf.spring_force(0.0003, 1000.0, 0.0005) != (0.3, 0.0):
        FAIL.append("conector elasto-plastico: fuerza o deformacion plastica incorrectas")
    _fl, _ft = _wf.yield_levels(_pw, _sp)
    if abs(_ft / _fl - 1.5) > 1e-9 or abs(_fl - 0.75 * 0.60 * _sp.FEXX() * 0.707 * 0.5) > 1e-9:
        FAIL.append("fluencia del cordon: debe ser φ·0.60·FEXX·garganta (x1.5 transversal)")
    print(f"{'cordon: β, conector plastico':34} β = {[round(v, 2) for v in _b]}   fluencia = {_fl:.2f} / {_ft:.2f} kip/in")
except Exception as _e:
    FAIL.append(f"criterios del cordon: {type(_e).__name__}: {_e}")

# ---------------------------------------------------- visor OpenGL: la escena se arma sin necesitar GPU
try:
    from placabase import gl3d as _gl
    import numpy as _np
    _conc = [(0, 0, 0), (4, 0, 0), (4, 1, 0), (1, 1, 0), (1, 4, 0), (0, 4, 0)]          # poligono concavo en L
    _tr = _gl.tri_poly(_conc)
    _ar = sum(abs(_np.cross(_np.subtract(_conc[b], _conc[a]), _np.subtract(_conc[c], _conc[a]))[2]) / 2 for a, b, c in _tr)
    if len(_tr) != 4 or abs(_ar - 7.0) > 1e-9:
        FAIL.append(f"visor GL: triangulacion de un poligono concavo incorrecta ({len(_tr)} tris, area {_ar})")
    _sc = _gl.scene_geometry(_u0, loads=True)
    _o, _t, _l = _sc.packed()
    if len(_o) < 100 or len(_t) == 0 or len(_l) == 0 or not _np.isfinite(_o).all() or not _sc.vlabels or len(_sc.dims) < 10:
        FAIL.append("visor GL: la escena de geometria quedo vacia o con valores no finitos")
    print(f"{'visor OpenGL (escena)':34} {len(_o) // 3} tris opacos, {len(_t) // 3} translucidos, {len(_l) // 2} aristas, {len(_sc.vlabels)} etiquetas, {len(_sc.dims)} cotas")
except Exception as _e:
    FAIL.append(f"visor GL: {type(_e).__name__}: {_e}")

# ---------------------------------------------------- interfaz (solo si hay Qt): que existan y corran los metodos clave
try:
    os_ = __import__("os"); os_.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication as _QA
    from placabase import ui as _ui
    _app = _QA.instance() or _QA([])
    _w = _ui.MainWindow()
    for _m in ("_bolt_loads", "_fem_now", "_raw_now", "draw_geom", "draw_3d", "_goto_calc", "export_target", "recalc"):
        if not hasattr(_w, _m):
            FAIL.append(f"interfaz: falta el metodo {_m}")
    _w.recalc(); _w.draw_geom(); _w.draw_3d()
    _q, _R = _w.export_target()
    print(f"{'interfaz (offscreen)':34} recalc, dibujo y exportacion OK   metodos: {len(dir(_w))}")
except ImportError:
    print(f"{'interfaz':34} omitida (sin PySide6)")
except Exception as _e:
    FAIL.append(f"interfaz: {type(_e).__name__}: {_e}")


# ---------------------------------------------------------------- columna descentrada (cx, cy)
try:
    from placabase import geometry as _G
    _pc = Project()
    _pc.loads.Pu, _pc.loads.Mux, _pc.loads.Muy, _pc.loads.Vux, _pc.loads.Vuy = 400.0, 1800.0, 0.0, 30.0, 10.0
    _pc.section.cx, _pc.section.cy = 2.0, -3.0
    _xs = [q[0] for q in _G.profile_outline(_pc)[0]]; _ys = [q[1] for q in _G.profile_outline(_pc)[0]]
    _ok_geo = abs((max(_xs) + min(_xs)) / 2 - 2.0) < 1e-9 and abs((max(_ys) + min(_ys)) / 2 + 3.0) < 1e-9
    _e = _pc.eloads
    _ok_ld = (abs(_e.Mux - (1800.0 + 400.0 * 3.0)) < 1e-9 and abs(_e.Muy - 400.0 * 2.0) < 1e-9
              and abs(_e.Tz - (2.0 * 10.0 + 3.0 * 30.0)) < 1e-9 and abs(_pc.cloads.Mux - 1800.0) < 1e-9)
    _Rc = solve(_pc)
    _ok_run = _Rc is not None and len(_Rc.checks) > 5
    _mx0 = _D.plate_thickness(Project(), _D.bearing(Project()))[1]["m_y"]
    _mx1 = _D.plate_thickness(_pc, _D.bearing(_pc))[1]["m_y"]
    _ok_m = abs(_mx1 - (_mx0 + 3.0)) < 1e-9          # voladizo del lado mas largo: +|cy|
    print(f"{'columna descentrada':34} geometria {'OK' if _ok_geo else 'ERROR'}  cargas {'OK' if _ok_ld else 'ERROR'}  "
          f"voladizo {'OK' if _ok_m else 'ERROR'}  calculo {'OK' if _ok_run else 'ERROR'}")
    for _n, _o in (("geometria", _ok_geo), ("traslado de cargas", _ok_ld), ("voladizo", _ok_m), ("calculo", _ok_run)):
        if not _o:
            FAIL.append(f"columna descentrada: {_n}")
    from placabase import view3d as _V3
    _gf = _V3.geometry_faces(_pc)
    _cf = [q for g in _gf if g[5] == "column" for q in g[1]]
    _cxs = [p[0] for q in _cf for p in q]
    if abs((max(_cxs) + min(_cxs)) / 2 - 2.0) > 0.2:
        FAIL.append("columna descentrada: la columna 3D no esta en la posicion indicada")
except Exception as _e_:
    FAIL.append(f"columna descentrada: {type(_e_).__name__}: {_e_}")


if "--3d" in sys.argv:
    # prueba de extremo a extremo con Gmsh + CalculiX (~30 s con la malla rapida)
    import tempfile
    from placabase import mesh3d
    from placabase.rep3d import make_fem
    print()
    print("ANALISIS SOLIDO 3D (--3d)")
    _p3 = Project()
    _res, _msg = mesh3d.full_3d(_p3, tempfile.mkdtemp(prefix="pb3d_"))
    if _res is None:
        FAIL.append(f"3D: no corrio: {_msg[-300:]}")
    else:
        _fem = make_fem(_p3, _res)
        _R = solve(_p3, fem=_fem)
        _ks = [c.key for c in _R.checks if c.key.startswith("fem_")]
        _p3s = Project.from_json(_p3.to_json()); _p3s.fea.weld_peak_factor = 1.0
        _Rs1 = {c.key: c for c in solve(_p3s, fem=_fem).checks}
        for c in _R.checks:
            if c.key.startswith("fem_weld") and _Rs1[c.key].ratio + 1e-9 < c.ratio:
                FAIL.append("3D: un limite de pico mas holgado no puede aumentar el D/C de la soldadura")
        _post = _fem.post
        _eq = _post.R_conc - _post.T_bolts - _p3.eloads.Pu
        print(f"{'3D PB-01':34} nodos={_fem.n_nodes:,}  R−ΣT−Pu = {_eq:+.3f} kip  filas: {_ks}")
        if abs(_eq) > 0.02 * max(1.0, abs(_p3.eloads.Pu)):
            FAIL.append(f"3D: equilibrio fuera de tolerancia ({_eq:+.2f} kip)")
        if not {"fem_bolt", "fem_press", "fem_vm", "fem_peeq"} <= set(_ks):
            FAIL.append("3D: faltan filas de verificacion FEM (incluida la deformacion plastica)")
        _pk = _fem.peeq
        print(f"{'  deformacion plastica en la placa':34} {_pk[0]*100:.4f} %  (limite {_p3.fea.plastic_limit:g} %)")
        if _pk is None or _pk[0] * 100.0 >= _p3.fea.plastic_limit:
            FAIL.append("3D: la deformacion plastica de la placa debe quedar bajo el limite en PB-01")
        if any("pendientes" in w for w in _R.warnings):
            FAIL.append("3D: no debe quedar el aviso de pendiente")
        if not (_fem.rep or {}).get("plan", {}).get("top"):
            FAIL.append("3D: no se generaron las vistas en planta")
        # soldadura con conectores: equilibrio vertical (contacto − cordones = Pu) y de cortante
        _eqw = _post.F_bear - _post.Fz_weld - _p3.eloads.Pu
        print(f"{'  soldadura: contacto − cordones − Pu':34} {_eqw:+.3f} kip   (modelo {_post.weld_model}, "
              f"contacto {_post.F_bear:.1f}, cordones {_post.Fz_weld:.1f})")
        if _post.weld_model != "conectores" or abs(_eqw) > 0.02 * abs(_p3.eloads.Pu):
            FAIL.append("3D: equilibrio vertical del cordon con conectores")
        # traccion pura: todo el axial pasa por los cordones y por los pernos
        _pt = Project(); _pt.loads.Pu = -100.0; _pt.loads.Mux = 0.0; _pt.loads.Vux = 0.0
        _rt, _mt = mesh3d.full_3d(_pt, tempfile.mkdtemp(prefix="pb3d_"))
        if _rt is None:
            FAIL.append(f"3D traccion pura: no corrio: {_mt[-200:]}")
        else:
            _pp = _rt.post
            print(f"{'  traccion pura 100 kip':34} cordones {_pp.Fz_weld:.2f} kip  contacto {_pp.F_bear:.3f}  "
                  f"pernos {_pp.T_bolts:.2f}")
            if not (abs(_pp.Fz_weld - 100.0) < 2.0 and _pp.F_bear < 1.0 and abs(_pp.T_bolts - 100.0) < 2.0):
                FAIL.append("3D traccion pura: el axial debe pasar por cordones y pernos")
        # respaldo fusionado: corre y entrega zonas
        _pf = Project(); _pf.fea.weld_model = "Fusionado (union monolitica, equivale a CJP)"
        _rf, _mf = mesh3d.full_3d(_pf, tempfile.mkdtemp(prefix="pb3d_"))
        if _rf is None or not _rf.post or not _rf.post.zones or _rf.post.weld_model != "fusionado":
            FAIL.append("3D fusionado: no entrego zonas de soldadura")
        else:
            print(f"{'  modelo fusionado (respaldo)':34} zonas = {[z.name for z in _rf.post.zones]}")


# ====================================================================================================
# TIPOLOGIAS DE CONEXION (placabase/conn): placa simple de corte, viga secundaria -> viga maestra / columna
# Los valores esperados se calcularon a mano, aparte del programa (AISC 360-22, LRFD).
# ====================================================================================================
print()
print("=" * 150)
print("TIPOLOGIAS DE CONEXION")
print("=" * 150)
from placabase.conn.specs import CT_SHEAR_TAB, CT_BASEPLATE, SUP_KINDS
from placabase.conn import common as _cc
from placabase.model import save_book, load_book
import tempfile as _tf, os as _os


def _near(name, got, want, tol=0.005):
    ok = abs(got - want) <= tol * max(1.0, abs(want))
    if not ok:
        FAIL.append(f"conn {name}: {got:.4f} (esperado {want:.4f})")
    return ok


def _tab(**mut):
    q = Project()
    q.ctype = CT_SHEAR_TAB
    for k, v in mut.items():
        setattr(q.stab, k, v)
    return q


# ---- metodo del centro instantaneo: equilibrio y limites
def _grp(n, s):
    return [((n - 1) / 2 - i) * s for i in range(n)]


_prev = None
for _e in (0.5, 1.5, 3.0, 6.0, 12.0):                            # C decrece al crecer la excentricidad
    _ic = _cc.ic_vertical_line(_grp(4, 3.0), _e)
    _Mic = sum(math.hypot(_ic.x_ic, y) * math.hypot(fx, fy) for y, fx, fy in zip(_ic.ys, _ic.fx, _ic.fy))
    if abs(sum(_ic.fy) - _ic.C) > 1e-9 or abs(sum(_ic.fx)) > 1e-9 or abs(_Mic - _ic.C * (_ic.x_ic + _e)) > 1e-6 * _ic.C:
        FAIL.append(f"conn IC: equilibrio (e = {_e})")
    if _prev is not None and not _ic.C < _prev:
        FAIL.append("conn IC: C debe decrecer con la excentricidad")
    _prev = _ic.C
_ic0 = _cc.ic_vertical_line(_grp(4, 3.0), 0.0)
_ic1 = _cc.ic_vertical_line(_grp(3, 3.0), 3.0)
# raiz de la ecuacion del CI con un metodo independiente (brentq) para 3 pernos, s = 3, e = 3
from scipy.optimize import brentq as _brentq
def _g(x, ys=_grp(3, 3.0), e=3.0):
    ds = [math.hypot(x, y) for y in ys]; dm = max(ds)
    R = [(1 - math.exp(-10 * 0.34 * d / dm)) ** 0.55 for d in ds]
    return sum(r * d for r, d in zip(R, ds)) - (x + e) * sum(r * x / d for r, d in zip(R, ds))
_x = _brentq(_g, 1e-6, 1e3)
_ds = [math.hypot(_x, y) for y in _grp(3, 3.0)]; _dm = max(_ds)
_C_ref = sum((1 - math.exp(-10 * 0.34 * d / _dm)) ** 0.55 * _x / d for d in _ds)
print(f"{'IC: 3 pernos s=3 e=3':34} C = {_ic1.C:.4f}  (brentq {_C_ref:.4f})   elastico {_ic1.C_elastic:.3f}   "
      f"concentrico 4 pernos C = {_ic0.C:.3f} (≈ 4·0.9815)")
_near("IC vs brentq", _ic1.C, _C_ref, 1e-6)
_near("IC concentrico", _ic0.C, 4 * (1 - math.exp(-3.4)) ** 0.55, 1e-6)
if not _ic1.C > _ic1.C_elastic:
    FAIL.append("conn IC: con 3 pernos el CI debe dar mas que el elastico")

# ---- placa simple, caso base calculado a mano: W16X31 -> alma de W24X55, 3 pernos 3/4 A325-N, s = 3, a = 3,
#      placa 3/8 A36 (9 in de alto, bordes 1.5), filete 1/4 E70, Vu = 25 kip
_p = _tab(combos=[["Comb 1", 25.0]])
_r = solve(_p)
_k = {c.key: c for c in _r.checks}
print(f"{'placa simple base (Vu = 25)':34} D/C max = {_r.max_ratio:.3f}  gobierna: {_r.governing.title[:48]}")
_near("pernos: phi*rn", 0.75 * 54.0 * math.pi * 0.75 ** 2 / 4, 17.893, 0.001)
_near("pernos: capacidad del grupo", _k["bolt_shear"].capacity, 0.75 * 54.0 * math.pi * 0.75 ** 2 / 4 * _ic1.C, 1e-6)
_near("placa: fluencia por cortante", _k["plate_vy"].capacity, 0.6 * 36 * 0.375 * 9.0, 1e-9)               # 72.9 kip
_near("placa: rotura por cortante", _k["plate_vr"].capacity, 0.75 * 0.6 * 58 * 0.375 * (9 - 3 * 0.875), 1e-9)  # 62.4 kip
_Lgv, _Lnv, _Lnt = 7.5, 7.5 - 2.5 * 0.875, 1.5 - 0.4375
_bs = 0.75 * min(0.6 * 58 * 0.375 * _Lnv + 58 * 0.375 * _Lnt, 0.6 * 36 * 0.375 * _Lgv + 58 * 0.375 * _Lnt)
_near("placa: bloque de cortante", _k["plate_bs"].capacity, _bs, 1e-9)                                      # 62.89 kip
_near("placa: flexion", _k["plate_m"].capacity, 0.9 * 36 * 0.375 * 81 / 4, 1e-9)                          # 246.0 kip·in
_near("placa: demanda de momento", _k["plate_m"].demand, 25 * 3.0, 1e-9)
_fv, _fh = 25 / 18.0, 3 * 25 * 3 / 81.0
_th = math.atan2(_fh, _fv)
_near("soldadura: demanda", _k["weld"].demand, math.hypot(_fv, _fh), 1e-9)                                  # 3.106 kip/in
_near("soldadura: capacidad", _k["weld"].capacity,
      0.75 * 0.6 * 70 * (1 + 0.5 * math.sin(_th) ** 1.5) * 0.707 * 0.25, 1e-9)                              # 7.92 kip/in
_near("soldadura: metal base del soporte", _k["weld_base"].capacity, 0.75 * 0.6 * 65 * CATALOG.get("W24X55").tw, 1e-9)
if _r.pending or not _r.closed_form or _r.verdict not in ("CUMPLE", "NO CUMPLE"):
    FAIL.append("conn: una tipologia de calculo cerrado no debe quedar PENDIENTE de 3D")
if not _r.ok:
    FAIL.append(f"conn: el caso base debe cumplir (D/C = {_r.max_ratio:.3f}, {_r.governing.title})")
# la capacidad por pernos debe coincidir con el D/C esperado a mano
_near("pernos: D/C", _k["bolt_shear"].ratio, 25.0 / (17.893 * _ic1.C), 0.001)

# ---- monotonia: mas carga, mayor D/C; otro perno, menos D/C de los pernos
_r2 = solve(_tab(combos=[["Comb 1", 40.0]]))
if not _r2.max_ratio > _r.max_ratio or _r2.ok:
    FAIL.append("conn: con Vu = 40 kip la placa base de este caso debe fallar en pernos (D/C > 1)")
_r4 = solve(_tab(n=4, combos=[["Comb 1", 40.0]]))
_k4 = {c.key: c for c in _r4.checks}
if not _k4["bolt_shear"].ratio < {c.key: c for c in _r2.checks}["bolt_shear"].ratio:
    FAIL.append("conn: 4 pernos deben dar menos D/C de pernos que 3 con la misma carga")
print(f"{'  Vu = 40 kip, 3 vs 4 pernos':34} pernos D/C {({c.key: c for c in _r2.checks})['bolt_shear'].ratio:.3f} -> {_k4['bolt_shear'].ratio:.3f}")

# ---- viga secundaria -> viga maestra: cope superior de 2 in x 4.5 in
_pc = _tab(cope_top=2.0, cope_len=4.5, top_flush=True, combos=[["Comb 1", 25.0], ["Comb 2", 30.0]])
_rc = solve(_pc)
_kc = {c.key: c for c in _rc.checks}
_b = CATALOG.get("W16X31")
print(f"{'viga secundaria a maestra (cope)':34} D/C max = {_rc.max_ratio:.3f}  gobierna: {_rc.governing.title[:48]}")
if not {"web_bs", "cope_flex", "cope_lwb", "geo_lev_b"} <= set(_kc):
    FAIL.append(f"conn cope: faltan verificaciones ({sorted(_kc)})")
if "cope_lwb" in _kc and not _kc["cope_lwb"].skip:
    FAIL.append("conn cope: el pandeo local del alma no esta implementado y debe figurar como NO EVALUADO (skip)")
if not any("NO EVALUADO" in w for w in _rc.warnings):
    FAIL.append("conn cope: debe avisar que el pandeo local por cope no se evalua")
# seccion del cope: ala inferior + alma restante, por rectangulos independientes
_y0 = _b.d / 2 - 2.0
_rs = [(_b.bf, _b.tf, -_b.d / 2 + _b.tf / 2), (_b.tw, _y0 - (-_b.d / 2 + _b.tf), (_y0 + (-_b.d / 2 + _b.tf)) / 2)]
_A = sum(w * h for w, h, _ in _rs); _yc = sum(w * h * y for w, h, y in _rs) / _A
_I = sum(w * h ** 3 / 12 + w * h * (y - _yc) ** 2 for w, h, y in _rs)
_S = _I / max(_yc - (-_b.d / 2), _y0 - _yc)
_e = 0.5 + 4.5 - 3.0
_near("cope: modulo neto", _kc["cope_flex"].capacity, 0.9 * 50 * _S, 1e-6)
_near("cope: momento", _kc["cope_flex"].demand, 30.0 * _e, 1e-9)               # gobierna la combinacion de 30 kip
_near("cope: bloque de cortante del alma", _kc["web_bs"].capacity, 0.75 * min(
    0.6 * 65 * _b.tw * (3.95 + 6 - 2.5 * 0.875) + 65 * _b.tw * (2.5 - 0.4375),
    0.6 * 50 * _b.tw * (3.95 + 6) + 65 * _b.tw * (2.5 - 0.4375)), 1e-9)
if _rc.combo_gov != 1 or len(_rc.combo_rows) != 2:
    FAIL.append(f"conn: la combinacion de 30 kip debe gobernar (gob = {_rc.combo_gov})")
if _rc.rec is None or "COPE" not in _rc.rec.to_html():
    FAIL.append("conn: la memoria debe incluir la seccion de la viga con cope")

# ---- viga a columna (ala) y limites del alcance
_rf = solve(_tab(sup_kind=SUP_KINDS[2], sup_label="W14X90", combos=[["Comb 1", 25.0]]))
_kf = {c.key: c for c in _rf.checks}
_near("columna: metal base = ala", _kf["weld_base"].capacity, 0.75 * 0.6 * 65 * CATALOG.get("W14X90").tf, 1e-9)
for _nm, _mut, _txt in (("a > 3.5 in", dict(a=4.0), "EXTENDIDA"), ("1 perno", dict(n=1), "2 a 12"),
                        ("13 pernos", dict(n=13), "2 a 12"), ("perfil inexistente", dict(beam="W99X999"), "no encontrado"),
                        ("cope sin longitud", dict(cope_top=2.0), "longitud")):
    _rr = solve(_tab(**_mut))
    _fat = [w for w in _rr.warnings if w.startswith("**")]
    if _rr.ok or not any(_txt in w for w in _fat):
        FAIL.append(f"conn alcance ({_nm}): debe dar aviso critico y no cumplir")
print(f"{'viga a ala de columna':34} D/C max = {_rf.max_ratio:.3f}   avisos criticos de alcance: OK")

# ---- consistencia de unidades: el D/C no depende del sistema de presentacion y la memoria convierte los modulos de seccion
_pm = _tab(cope_top=2.0, cope_len=4.5, combos=[["Comb 1", 25.0]])                 # mm, kN, MPa por defecto
_pi = _tab(cope_top=2.0, cope_len=4.5, combos=[["Comb 1", 25.0]])
_pi.u_len, _pi.u_force, _pi.u_stress, _pi.u_moment = "in", "kip", "ksi", "kip·in"
_rm, _ri = solve(_pm), solve(_pi)
if abs(_rm.max_ratio - _ri.max_ratio) > 1e-12:
    FAIL.append("conn unidades: el D/C cambia con el sistema de unidades")
_zl = [t for k, t in _rm.rec.to_lines() if t.startswith("φMp")][0]
if f"{7.59375 * 25.4 ** 3:.4g}" not in _zl:                                        # Z = 0.375·9²/4 in³ en mm³
    FAIL.append(f"conn unidades: Z mal convertido en la memoria: {_zl}")
print(f"{'consistencia de unidades':34} D/C mm-kN = in-kip = {_rm.max_ratio:.4f};  Z en la memoria: {_zl.split('=')[-2].strip()}")

# ---- interfaz y reportes de la tipologia (offscreen, solo si hay Qt) y modo por lotes
_od = _tf.mkdtemp(prefix="pbconn_out_")
try:
    from PySide6.QtWidgets import QApplication as _QA2
    from placabase import ui as _ui2, report as _rep
    _app2 = _QA2.instance() or _QA2([])
    _w2 = _ui2.MainWindow()
    _w2.add_connection(CT_SHEAR_TAB)
    _w2.prj.stab.cope_top, _w2.prj.stab.cope_len = 2.0, 4.5
    _w2.load_ui(); _w2.recalc()
    _tin = [_w2.tabs_in.tabText(i) for i in range(_w2.tabs_in.count()) if _w2.tabs_in.isTabVisible(i)]
    _tout = [_w2.tabs_out.tabText(i) for i in range(_w2.tabs_out.count()) if _w2.tabs_out.isTabVisible(i)]
    if not _w2.is_conn or _tin != ["Proyecto", "Conexion de corte"] or "Esquema de la conexion" not in _tout \
            or "Analisis FEM" in _tout or "Modelo y vistas" in _tout:
        FAIL.append(f"conn UI: pestañas de la tipologia incorrectas: {_tin} / {_tout}")
    if _w2.tbl.rowCount() != len(_w2.res.checks) or "CUMPLE" not in _w2.lbl_verdict.text():
        FAIL.append(f"conn UI: tabla o veredicto incorrectos ({_w2.tbl.rowCount()} filas; '{_w2.lbl_verdict.text().strip()}')")
    _dc0 = _w2.res.max_ratio
    _w2.fnamed["Conexion de corte"].w("stab.n").setValue(5)
    _w2.recalc()
    if not abs(_w2.res.max_ratio - _dc0) > 1e-6 or _w2.prj.stab.n != 5:
        FAIL.append("conn UI: cambiar el numero de pernos en el formulario debe recalcular")
    _w2._ld_add(); _w2.recalc()
    if len(_w2.res.combo_rows) != 2 or _w2.tbl_cmb.rowCount() != 2:
        FAIL.append("conn UI: agregar una reaccion debe agregar una combinacion")
    _w2._goto_calc(0)                                                    # salto a la memoria: no debe fallar
    _qq, _RR = _w2.export_target()
    _figs = _rep.save_figures(_qq, _RR, _od)
    _pdf = _rep.export_pdf(_qq, _RR, _os.path.join(_od, "m.pdf"), _figs)
    _doc = _rep.export_docx(_qq, _RR, _os.path.join(_od, "m.docx"), _figs)
    if len(_figs) != 1 or any(_os.path.getsize(f) < 5000 for f in (_pdf, _doc, *_figs)):
        FAIL.append("conn reportes: PDF/Word/figuras no generados o vacios")
    _w2._switch(0); _w2.recalc()
    _tin0 = [_w2.tabs_in.tabText(i) for i in range(_w2.tabs_in.count()) if _w2.tabs_in.isTabVisible(i)]
    if _w2.is_conn or "Placa" not in _tin0 or "Conexion de corte" in _tin0:
        FAIL.append(f"conn UI: al volver a la placa base deben reaparecer sus pestañas ({_tin0})")
    print(f"{'UI y reportes de la tipologia':34} pestañas por tipologia, edicion, combinaciones, PDF {_os.path.getsize(_pdf)//1024} KB, "
          f"Word {_os.path.getsize(_doc)//1024} KB")
except ImportError:
    print(f"{'UI y reportes de la tipologia':34} omitida (sin PySide6)")
except Exception as _e:
    FAIL.append(f"conn UI/reportes: {type(_e).__name__}: {_e}")
    traceback.print_exc()

# UI + reportes para TODAS las tipologias registradas
try:
    from PySide6.QtWidgets import QApplication as _QA3
    from placabase import ui as _ui3, report as _rep3, conn as _cn3
    _app3 = _QA3.instance() or _QA3([])
    _w3 = _ui3.MainWindow()
    for _ct3, _m3 in _cn3.modules():
        _w3.add_connection(_ct3)
        _w3.recalc()
        _q3, _R3 = _w3.export_target()
        _tabs = [_w3.tabs_in.tabText(i) for i in range(_w3.tabs_in.count()) if _w3.tabs_in.isTabVisible(i)]
        if _tabs != ["Proyecto", _m3.TAB]:
            FAIL.append(f"UI {_m3.PREFIX}: pestañas visibles incorrectas {_tabs}")
        if _w3.tbl.rowCount() != len(_w3.res.checks) or not any(k in _w3.lbl_verdict.text() for k in ("CUMPLE", "NO CUMPLE")):
            FAIL.append(f"UI {_m3.PREFIX}: tabla o veredicto incorrectos")
        if _w3.tbl_ld[_m3.ATTR].rowCount() != len(getattr(_w3.prj, _m3.ATTR).loads()):
            FAIL.append(f"UI {_m3.PREFIX}: la tabla de cargas no refleja las combinaciones")
        _ff = _rep3.save_figures(_q3, _R3, _od)
        _p3 = _rep3.export_pdf(_q3, _R3, _os.path.join(_od, f"{_m3.PREFIX}.pdf"), _ff)
        _d3 = _rep3.export_docx(_q3, _R3, _os.path.join(_od, f"{_m3.PREFIX}.docx"), _ff)
        if any(_os.path.getsize(f) < 4000 for f in (_p3, _d3, *_ff)):
            FAIL.append(f"UI {_m3.PREFIX}: PDF/Word/figura vacios")
        _w3._goto_calc(0)
    print(f"{'UI y reportes de todas':34} {len(_cn3.modules())} tipologias: pestañas, tabla, dibujo, PDF y Word OK")
except ImportError:
    print(f"{'UI de todas las tipologias':34} omitida (sin PySide6)")
except Exception as _e:
    FAIL.append(f"UI todas las tipologias: {type(_e).__name__}: {_e}")
    traceback.print_exc()

# modo por lotes (run.py): lee el LIBRO (antes usaba Project.load y calculaba un proyecto por defecto) y procesa cada conexion
import importlib, io, contextlib
_run = importlib.import_module("run")
_b1 = Project(); _b1.element = "VS-A"; _b1.ctype = CT_SHEAR_TAB; _b1.stab.combos = [["C1", 25.0]]
_b2 = Project(); _b2.element = "VS-B"; _b2.ctype = CT_SHEAR_TAB; _b2.stab.combos = [["C1", 60.0]]
_fb = _os.path.join(_od, "lote.pbase"); save_book(_fb, [_b1, _b2])
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    _rc = _run.batch([_fb, "--pdf", _os.path.join(_od, "lote.pdf")])
_txt = _buf.getvalue()
if "VS-A: CUMPLE" not in _txt or "VS-B: NO CUMPLE" not in _txt or _rc != 2 \
        or not (_os.path.exists(_os.path.join(_od, "lote_VS-A.pdf")) and _os.path.exists(_os.path.join(_od, "lote_VS-B.pdf"))):
    FAIL.append(f"conn lote: no proceso las dos conexiones del libro (rc = {_rc}):\n{_txt}")
with contextlib.redirect_stdout(io.StringIO()) as _buf2:
    _run.batch(["ejemplos/PB-02_HSS12_rigidizada.pbase"])
if "PB-02:" not in _buf2.getvalue():
    FAIL.append("lote: debe calcular el proyecto del archivo (PB-02), no uno por defecto")
print(f"{'modo por lotes (run.py)':34} libro con 2 conexiones: CUMPLE / NO CUMPLE, codigo de salida {_rc}; ejemplo PB-02 leido del archivo")


# ====================================================================================================
# DOBLE ANGULO (2L4X4X3/8 x 9 in, 3 Ø3/4 A325-N por fila, s = 3, gw = a = 2, Vu = 40 kip), calculado a mano
# ====================================================================================================
from placabase.conn.specs import CT_DOUBLE_ANGLE, DA_ATTACH


def _da(**mut):
    q = Project(); q.ctype = CT_DOUBLE_ANGLE
    for k, v in mut.items():
        setattr(q.dang, k, v)
    return q


_pd = _da()
_rd = solve(_pd)
_kd = {c.key: c for c in _rd.checks}
print(f"{'doble angulo (atornillado)':34} D/C max = {_rd.max_ratio:.3f}  gobierna: {_rd.governing.title[:48]}")


def _C_ref(n, s_, e):                                    # centro instantaneo con un metodo independiente (brentq)
    ys = _grp(n, s_)
    def g(x):
        ds = [math.hypot(x, y) for y in ys]; dm = max(ds)
        R = [(1 - math.exp(-10 * 0.34 * d / dm)) ** 0.55 for d in ds]
        return sum(r * d for r, d in zip(R, ds)) - (x + e) * sum(r * x / d for r, d in zip(R, ds))
    x = _brentq(g, 1e-6, 1e3)
    ds = [math.hypot(x, y) for y in ys]; dm = max(ds)
    return sum((1 - math.exp(-10 * 0.34 * d / dm)) ** 0.55 * x / d for d in ds)


_rn = 54.0 * math.pi * 0.75 ** 2 / 4
_near("DA pernos del alma (doble corte)", _kd["bolt_a"].capacity, 0.75 * 2 * _rn * _C_ref(3, 3.0, 2.0), 1e-6)
_near("DA pernos del soporte", _kd["bolt_b"].demand, 40.0 / 6, 1e-9)
_near("DA pernos del soporte: capacidad", _kd["bolt_b"].capacity, 0.75 * _rn, 1e-9)                        # 17.89 kip
_near("DA angulo: fluencia", _kd["ang_vy"].capacity, 0.6 * 36 * 0.375 * 9.0, 1e-9)                         # 72.9 kip
_near("DA angulo: fluencia, demanda por angulo", _kd["ang_vy"].demand, 20.0, 1e-9)
_near("DA angulo: rotura", _kd["ang_vr_w"].capacity, 0.75 * 0.6 * 58 * 0.375 * (9 - 3 * 0.875), 1e-9)     # 62.4 kip
_Lg, _Lt = 1.5 + 6.0, 2.0 - 0.4375
_near("DA angulo: bloque de cortante", _kd["ang_bs_w"].capacity, 0.75 * min(
    0.6 * 58 * 0.375 * (_Lg - 2.5 * 0.875) + 58 * 0.375 * _Lt, 0.6 * 36 * 0.375 * _Lg + 58 * 0.375 * _Lt), 1e-9)
if not _rd.ok or _rd.pending:
    FAIL.append(f"DA: el caso base debe cumplir (D/C = {_rd.max_ratio:.3f})")
# soldado: lineas verticales con e = a
_rw = solve(_da(attach=DA_ATTACH[1], weld_lines=2))
_kw = {c.key: c for c in _rw.checks}
_fv, _fh = 40 / (4 * 9.0), 6 * 40 * 2.0 / (4 * 81.0)
_th = math.atan2(_fh, _fv)
_near("DA soldado: demanda", _kw["weld"].demand, math.hypot(_fv, _fh), 1e-9)
_near("DA soldado: capacidad", _kw["weld"].capacity, 0.75 * 0.6 * 70 * (1 + 0.5 * math.sin(_th) ** 1.5) * 0.707 * 0.25, 1e-9)
if "bolt_b" in _kw:
    FAIL.append("DA soldado: no debe haber pernos del soporte")
# mas largo -> menos D/C de los angulos; cope agrega verificaciones; alcance
if not solve(_da(L_ang=12.0)).checks[0] or not {c.key: c for c in solve(_da(L_ang=12.0)).checks}["ang_vy"].ratio < _kd["ang_vy"].ratio:
    FAIL.append("DA: angulos mas largos deben bajar el D/C de cortante")
_rc2 = solve(_da(cope_top=2.0, cope_len=4.5))
if not {"web_bs", "cope_flex", "cope_lwb", "geo_lev_b"} <= {c.key for c in _rc2.checks} or not any("NO EVALUADO" in w for w in _rc2.warnings):
    FAIL.append("DA cope: faltan verificaciones o el aviso de pandeo local")
for _nm, _mut, _txt in (("1 perno", dict(n=1), "2 a 12"), ("angulo corto", dict(L_ang=5.0), "no alcanza"),
                        ("angulo inexistente", dict(angle="L9X9X9"), "no encontrado")):
    _rr = solve(_da(**_mut))
    if _rr.ok or not any(w.startswith("**") and _txt in w for w in _rr.warnings):
        FAIL.append(f"DA alcance ({_nm}): debe dar aviso critico y no cumplir")
print(f"{'  doble angulo soldado / cope':34} soldadura {_kw['weld'].ratio:.3f}; con cope D/C = {_rc2.max_ratio:.3f}; avisos de alcance OK")


# ====================================================================================================
# ASIENTO (L6X6X3/4 x 8 in, W16X31 sobre ala de W14X90, N = 3.5, retranqueo 3/4, R = 25 kip), calculado a mano
# ====================================================================================================
from placabase.conn.specs import CT_SEATED, SEAT_TYPES, SEAT_ATTACH


def _se(**mut):
    q = Project(); q.ctype = CT_SEATED
    for k, v in mut.items():
        setattr(q.seat, k, v)
    return q


_rs = solve(_se())
_ks = {c.key: c for c in _rs.checks}
_bw = CATALOG.get("W16X31"); _an = CATALOG.get("L6X6X3/4")
print(f"{'asiento sin rigidizar':34} D/C max = {_rs.max_ratio:.3f}  gobierna: {_rs.governing.title[:48]}")
_near("asiento: fluencia del alma", _ks["web_yield"].capacity, 50.0 * _bw.tw * (2.5 * _bw.kdes + 3.5), 1e-9)
_Nd = 3.5 / _bw.d                                                             # 0.2201 > 0.2: ecuacion J10-5b
_cr = 0.75 * 0.40 * _bw.tw ** 2 * (1 + (4 * _Nd - 0.2) * (_bw.tw / _bw.tf) ** 1.5) * math.sqrt(29000 * 50 * _bw.tf / _bw.tw)
_near("asiento: aplastamiento del alma (J10-5b)", _ks["web_crip"].capacity, _cr, 1e-9)
_eR = 0.75 + 3.5 / 2
_near("asiento: momento en el pie del filete", _ks["seat_flex"].demand, 25.0 * (_eR - _an.kdes), 1e-9)
_near("asiento: φMp de la pierna horizontal", _ks["seat_flex"].capacity, 0.9 * 36 * 8.0 * 0.75 ** 2 / 4, 1e-9)
_ys = [1.25, 4.25]
_Tm = 25.0 * _eR * max(_ys) / sum(2 * y * y for y in _ys)
_near("asiento: traccion del perno superior", _ks["bolt_t"].demand, _Tm, 1e-9)
_frv = (25.0 / 4) / (math.pi * 0.75 ** 2 / 4)
_near("asiento: φF'nt·Ab (J3.7)", _ks["bolt_t"].capacity, 0.75 * (1.3 * 90 - 90 / (0.75 * 54) * _frv) * math.pi * 0.75 ** 2 / 4, 1e-9)
if not _rs.ok:
    FAIL.append(f"asiento: el caso base debe cumplir (D/C = {_rs.max_ratio:.3f}: {_rs.governing.title})")
_r2s = solve(_se(angle="L6X6X3/8"))
if _r2s.ok or {c.key: c for c in _r2s.checks}["seat_flex"].ratio <= _ks["seat_flex"].ratio:
    FAIL.append("asiento: un angulo mas delgado debe fallar a flexion")
# soldado en C y rigidizado
_rsw = solve(_se(attach=SEAT_ATTACH[1]))
_ksw = {c.key: c for c in _rsw.checks}
if "weld" not in _ksw or "bolt_t" in _ksw or _ksw["weld"].ratio <= 0:
    FAIL.append("asiento soldado: debe verificar la soldadura en C y no los pernos")
_rst = solve(_se(seat_type=SEAT_TYPES[1]))
_kst = {c.key: c for c in _rst.checks}
_near("rigidizador: φMp", _kst["st_flex"].capacity, 0.9 * 36 * 0.625 * 8.0 ** 2 / 4, 1e-9)
_near("rigidizador: momento", _kst["st_flex"].demand, 25.0 * _eR, 1e-9)
_fv, _fh = 25.0 / (2 * 8.0), 6 * 25.0 * _eR / (2 * 64.0)
_near("rigidizador: soldadura (demanda)", _kst["weld"].demand, math.hypot(_fv, _fh), 1e-9)
for _nm, _mut, _txt in (("N no cabe", dict(N=8.0), "no cabe"), ("perfil inexistente", dict(beam="W99X999"), "perfil I")):
    _rr = solve(_se(**_mut))
    if _rr.ok or not any(w.startswith("**") and _txt in w for w in _rr.warnings):
        FAIL.append(f"asiento alcance ({_nm}): debe dar aviso critico y no cumplir")
print(f"{'  asiento soldado / rigidizado':34} soldadura C {_ksw['weld'].ratio:.3f}; rigidizado D/C = {_rst.max_ratio:.3f}; avisos de alcance OK")

# ====================================================================================================
# EMPALMES: viga W16X50 (Mu = 1200 kip·in, Vu = 30) y columna W14X90 con contacto
# ====================================================================================================
from placabase.conn.specs import CT_BEAM_SPLICE, CT_COL_SPLICE, SPLICE_SHARE


def _bs(**mut):
    q = Project(); q.ctype = CT_BEAM_SPLICE
    for k, v in mut.items():
        setattr(q.bsp, k, v)
    return q


def _cs(**mut):
    q = Project(); q.ctype = CT_COL_SPLICE
    for k, v in mut.items():
        setattr(q.csp, k, v)
    return q


_sh = CATALOG.get("W16X50")
_hf = _sh.d - _sh.tf
_Ff = 1200.0 / _hf
_rb = solve(_bs())
_kb = {c.key: c for c in _rb.checks}
print(f"{'empalme de viga':34} D/C max = {_rb.max_ratio:.3f}  gobierna: {_rb.governing.title[:48]}")
_near("empalme viga: fuerza de ala (demanda de fluencia)", _kb["fl_pl_y"].demand, _Ff, 1e-9)
_near("empalme viga: fluencia de placas", _kb["fl_pl_y"].capacity, 0.9 * 36 * 7.0 * 0.625, 1e-9)                # 141.75 kip
_near("empalme viga: rotura de placas", _kb["fl_pl_r"].capacity, 0.75 * 58 * min(0.625 * (7.0 - 2 * 1.0), 0.85 * 7.0 * 0.625), 1e-9)
_rnb = 54.0 * math.pi * 0.875 ** 2 / 4
_near("empalme viga: pernos de ala", _kb["fl_bolt"].capacity, 0.75 * _rnb, 1e-9)
_near("empalme viga: fuerza por perno", _kb["fl_bolt"].demand, _Ff / 6, 1e-9)
_Fe = math.pi ** 2 * 29000 / (3.5 / (0.625 / math.sqrt(12))) ** 2
_near("empalme viga: pandeo de placas (E3)", _kb["fl_pl_b"].capacity, 0.9 * 0.658 ** (36 / _Fe) * 36 * 4.375, 1e-9)
_near("empalme viga: perno del alma (elastico)", _kb["w_bolt"].demand, math.hypot(30 / 3, 30 * 2.25 * 3 / 18), 1e-9)
_near("empalme viga: perno del alma, capacidad", _kb["w_bolt"].capacity, 0.75 * 2 * 54 * math.pi * 0.75 ** 2 / 4, 1e-9)
if not _rb.ok:
    FAIL.append(f"empalme viga: el caso base debe cumplir (D/C = {_rb.max_ratio:.3f}: {_rb.governing.title})")
# placas interiores: doble corte y mas area
_rbi = solve(_bs(fi_b=2.5, fi_t=0.5))
_kbi = {c.key: c for c in _rbi.checks}
if not _kbi["fl_bolt"].capacity > _kb["fl_bolt"].capacity * 1.99 or not _kbi["fl_pl_y"].ratio < _kb["fl_pl_y"].ratio:
    FAIL.append("empalme viga: las placas interiores deben duplicar la capacidad de los pernos (doble corte) y bajar la fluencia")
# reparto del momento segun la inercia: alma toma Mw
_rbm = solve(_bs(share=SPLICE_SHARE[1]))
_kbm = {c.key: c for c in _rbm.checks}
_Mw = 1200.0 * (_sh.tw * (_sh.d - 2 * _sh.tf) ** 3 / 12) / _sh.Ix
_near("empalme viga: fuerza de ala con reparto por inercia", _kbm["fl_pl_y"].demand, (1200.0 - _Mw) / _hf, 1e-9)
if "w_pl_m" not in _kbm or _kbm["w_pl_m"].demand <= 0:
    FAIL.append("empalme viga: con reparto por inercia debe verificar la flexion de las placas de alma")
# axial de traccion aumenta T; columna: contacto reduce la compresion de diseno
_rbn = solve(_bs(combos=[["c", 1200.0, 30.0, 50.0]]))
if not {c.key: c for c in _rbn.checks}["fl_pl_y"].demand > _Ff:
    FAIL.append("empalme viga: la traccion axial debe aumentar la fuerza del ala traccionada")
_rc = solve(_cs())
_kc2 = {c.key: c for c in _rc.checks}
_rcn = solve(_cs(contact=False))
_kcn = {c.key: c for c in _rcn.checks}
_sc = CATALOG.get("W14X90")
_Cc = 300.0 / (_sc.d - _sc.tf) + 400.0 * (_sc.bf * _sc.tf) / _sc.A
_near("empalme columna sin contacto: compresion del ala", _kcn["fl_pl_y"].demand, _Cc, 1e-9)
_near("empalme columna con contacto: 50 % de la compresion", _kc2["fl_pl_y"].demand, 0.5 * _Cc, 1e-9)
if "fl_pl_b" in _kc2 or "fl_pl_b" not in _kcn:
    FAIL.append("empalme columna: el pandeo de placas solo aplica sin contacto")
_Nw_c = 0.5 * 400.0 * (_sc.A - 2 * _sc.bf * _sc.tf) / _sc.A
_near("empalme columna: axial del alma con contacto (50 %)", _kc2["w_pl_n"].demand, _Nw_c, 1e-9)
if not _rc.ok:
    FAIL.append(f"empalme columna: el caso base debe cumplir (D/C = {_rc.max_ratio:.3f}: {_rc.governing.title})")
for _nm, _mut, _txt in (("placa mas ancha que el ala", dict(fo_b=12.0), "mas ancha"), ("columnas no validas", dict(f_cols=3), "2 o 4"),
                        ("perfil inexistente", dict(shape="W99X999"), "perfil I")):
    _rr = solve(_bs(**_mut))
    if _rr.ok or not any(w.startswith("**") and _txt in w for w in _rr.warnings):
        FAIL.append(f"empalme alcance ({_nm}): debe dar aviso critico y no cumplir")
print(f"{'  empalme de columna':34} con contacto D/C = {_rc.max_ratio:.3f}; sin contacto {_rcn.max_ratio:.3f}; interiores / reparto / axial OK")

# ====================================================================================================
# FUZZ GENERICO: todas las tipologias registradas con valores numericos aleatorios (incluidos invalidos):
# no debe haber excepciones ni valores no finitos, y cualquier geometria imposible debe dar aviso critico
# ====================================================================================================
import random as _rnd, dataclasses as _dc, copy as _cp
from placabase import conn as _connpkg
_rnd.seed(20261008)
for _ct, _mod in _connpkg.modules():
    _bad, _nfat, _nok = [], 0, 0
    for _k in range(400):
        _q = Project(); _q.ctype = _ct
        _sp = getattr(_q, _mod.ATTR)
        for _f in _dc.fields(_sp):
            _v = getattr(_sp, _f.name)
            if isinstance(_v, bool):
                if _rnd.random() < 0.3:
                    setattr(_sp, _f.name, not _v)
            elif isinstance(_v, int) and _f.name != "combo_idx":
                setattr(_sp, _f.name, _rnd.choice([0, 1, 2, 3, 4, 6, 8, 12, 14]))
            elif isinstance(_v, float):
                setattr(_sp, _f.name, _rnd.choice([0.0, 0.0625, 0.25, 1.0, 2.5, 3.0, 6.0, 12.0, _v * 0.5, _v * 2.0, _v, _v]))
        _sp.combos = [[f"c{i}"] + [_rnd.choice([0.0, 5.0, 25.0, 80.0, 400.0]) for _ in _mod.LOADS] for i in range(_rnd.randint(1, 3))]
        try:
            _r = solve(_q)
            for _c in _r.checks:
                for _x in (_c.demand, _c.capacity, _c.ratio):
                    if not math.isfinite(_x):
                        _bad.append(f"no finito: {_c.key}")
                        break
            _r.rec.to_lines()
            _nfat += any(w.startswith("**") for w in _r.warnings)
            _nok += bool(_r.ok)
            if _k % 40 == 0:
                from placabase.conn.base import new_figure as _nf
                _fg = _nf(8, 9.5, 60); _mod.draw(_fg, _q)
        except Exception as _e:
            _bad.append(f"{type(_e).__name__}: {_e}")
    if _bad:
        FAIL.append(f"fuzz {_mod.NAME[:40]}: {len(_bad)} fallas, p. ej. {_bad[0]}")
    print(f"{'fuzz ' + _mod.PREFIX:34} 400 casos aleatorios sin excepciones; con aviso critico {_nfat}, cumplen {_nok}")

# ---- archivos: ida y vuelta de un libro con las dos tipologias, y compatibilidad con los ejemplos viejos
_f = _os.path.join(_tf.mkdtemp(prefix="pbconn_"), "libro.pbase")
_bp = Project(); _bp.element = "PB-X"
_pc.element = "VS-1"
save_book(_f, [_bp, _pc])
_bk = load_book(_f)
if [x.ctype for x in _bk] != [CT_BASEPLATE, CT_SHEAR_TAB] or _bk[1].stab != _pc.stab:
    FAIL.append("conn: el libro no conserva la tipologia y los datos de la conexion de corte")
for _ex in ("PB-01_W14X90", "COMP-1_W14X90_traccion"):
    _old = load_book(f"ejemplos/{_ex}.pbase")
    if _old[0].ctype != CT_BASEPLATE:
        FAIL.append(f"conn: {_ex} debe abrir como placa base")
print(f"{'libro con dos tipologias':34} guardado y leido OK;  ejemplos antiguos abren como placa base")

print()
print("=" * 150)
if FAIL:
    print(f"FALLAS ({len(FAIL)}):")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DEL MOTOR PASARON")
