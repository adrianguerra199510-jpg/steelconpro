# -*- coding: utf-8 -*-
"""Pruebas de los modulos de nudo (viga-columna, viga a viga, crucetas): flujo por operaciones, geometria 3D, verificaciones por codigo y reportes.

    python selftest_nodes.py        (tambien las corre selftest.py al final)
"""
import sys, math, copy, json, random, io, contextlib, importlib, tempfile, os, traceback
sys.path.insert(0, ".")

import numpy as np


def run():
    FAIL = []
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:                                                   # la interfaz fija el backend de matplotlib: se importa antes de que otro codigo use pyplot
        from steelconpro import ui as _ui                  # noqa: F401
    except ImportError:
        pass
    from steelconpro.model import Project, save_book, load_book
    import steelconpro.model as MD
    from steelconpro.shapes import CATALOG
    from steelconpro import materials as M
    from steelconpro.conn import presets as PRE, assembly as AS, module_for, modules, solve_conn
    from steelconpro.conn.specs import (CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS, CONN_TYPES, MODE_OF, ATTR_OF, MODE_COL, MODE_BEAM, MODE_CHORD,
                                        END_LABELS, OPERATIONS, CONNECTION_OPS, OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET,
                                        OP_GUSSET_W, OP_COPE, OP_CONT, Nodo, Member, Operation, Load)
    from steelconpro.conn.fem import scene as SC
    from steelconpro.conn.checks import adapters

    print()
    print("=" * 150)
    print("MODULOS DE NUDO (flujo por operaciones, verificacion por codigo)")
    print("=" * 150)

    # ---------------------------------------------------------------- registro
    if CONN_TYPES != [CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS] or [c for c, _m in modules()] != [CT_NODE, CT_B2B, CT_TRUSS]:
        FAIL.append(f"nudos: registro de modulos inesperado {CONN_TYPES}")
    if any(module_for(c).VISUAL for c, _m in modules()):
        FAIL.append("nudos: los modulos ya verifican por codigo (VISUAL = False)")
    print(f"{'registro':34} {len(modules())} modulos de nudo + placa base; {len(OPERATIONS)} operaciones disponibles")

    # ---------------------------------------------------------------- salida de un rayo por la seccion (a mano)
    w = CATALOG.get("W14X90")
    ext = AS.outer_extent(w)
    d, bf, tf, tw = w.d, w.bf, w.tf, w.tw
    rr = CATALOG.get("HSS12.750X0.500")
    checks = [("alma (+x)", AS.ray_exit(ext, (0, 0), (1, 0)), tw / 2.0),
              ("ala (+y)", AS.ray_exit(ext, (0, 0), (0, 1)), d / 2.0),
              ("45°", AS.ray_exit(ext, (0, 0), (math.cos(math.radians(45)), math.sin(math.radians(45)))), (d / 2.0) / math.sin(math.radians(45))),
              ("tubo redondo", AS.ray_exit(AS.outer_extent(rr), (0, 0), (0.3, 0.7)), rr.d / 2.0 / math.hypot(0.3, 0.7)),
              ("HSS rect.", AS.ray_exit(AS.outer_extent(CATALOG.get("HSS12X12X1/2")), (0, 0), (1, 0)), 6.0)]
    for nm, got, want in checks:
        if got is None or abs(got - want) > 1e-6:
            FAIL.append(f"nudos: salida del rayo ({nm}): {got} contra {want}")
    print(f"{'rayo contra la seccion':34} alma {checks[0][1]:.3f} = tw/2, ala {checks[1][1]:.3f} = d/2, 45° {checks[2][1]:.3f}, tubos: OK")

    # ---------------------------------------------------------------- posiciones a mano: columna W14X90 y viga W16X31 por el ala (az = 0)
    nd = PRE.build(MODE_COL, "int1", "I", "tab")
    nd.members[0].gap = 0.5
    mdl = AS.build_nodo(nd)
    x0 = float(mdl.part("V1").bbox()[0][0])
    if abs(x0 - (d / 2.0 + 0.5)) > 1e-6:
        FAIL.append(f"nudos: la viga debe empezar en d/2 + retranqueo = {d / 2 + 0.5:.3f}; empieza en {x0:.4f}")
    zmin, zmax = float(mdl.part("Columna").bbox()[0][2]), float(mdl.part("Columna").bbox()[1][2])
    if abs(zmin + 60.0) > 1e-9 or abs(zmax - 60.0) > 1e-9:
        FAIL.append(f"nudos: columna intermedia debe ir de -60 a 60: {zmin}..{zmax}")
    if len([b for b in mdl.bolts if b.tag.startswith("V1")]) != 3 or mdl.part("Placa V1") is None:
        FAIL.append("nudos: placa simple con 3 pernos")
    nd.main_end = END_LABELS[MODE_COL][1]
    cz = AS.build_nodo(nd).part("Columna").bbox()
    if abs(float(cz[1][2])) > 1e-9 or abs(float(cz[0][2]) + 60.0) > 1e-9:
        FAIL.append("nudos: columna de extremo superior debe ir de -60 a 0")
    nd.main_end = END_LABELS[MODE_COL][2]
    cz = AS.build_nodo(nd).part("Columna").bbox()
    if abs(float(cz[0][2])) > 1e-9 or abs(float(cz[1][2]) - 60.0) > 1e-9:
        FAIL.append("nudos: columna de extremo inferior debe ir de 0 a 60")
    nd2 = PRE.build(MODE_COL, "int1", "I", "ep_flush")
    m2 = AS.build_nodo(nd2)
    pe = m2.part("Placa extrema V1")
    if pe is None or abs(float(pe.bbox()[0][0]) - d / 2.0) > 1e-6 or abs(float(m2.part("V1").bbox()[0][0]) - float(pe.bbox()[1][0])) > 1e-6:
        FAIL.append("nudos: placa extrema contra la cara de la columna y viga a continuacion")
    print(f"{'posiciones (columna W14X90)':34} viga en d/2 + retranqueo = {x0:.3f} in; columna intermedia / de extremo; placa extrema contra la cara: OK")

    # ---------------------------------------------------------------- operaciones: corte (cope) y placas de continuidad
    nc = PRE.build(MODE_COL, "int1", "I", "tab")
    def top_x0(model):                                                   # inicio (en x) de lo que queda del ala superior de la viga
        return min(float(p.corners()[:, 0].min()) for p in model.part("V1").prisms if float(p.corners()[:, 2].min()) > 0.0)
    x_full = top_x0(AS.build_nodo(nc))
    nc.operations.append(Operation(kind=OP_COPE, member="V1", cope_top=2.0, cope_len=4.5))
    x_cope = top_x0(AS.build_nodo(nc))
    if abs(x_cope - x_full - 4.5) > 1e-6:
        FAIL.append(f"nudos: el corte (cope) debe quitar 4.5 in de ala superior: {x_full} -> {x_cope}")
    nw = PRE.build(MODE_COL, "int1", "I", "weld")
    if not [p for p in AS.build_nodo(nw).parts if "ontinuidad" in p.name]:
        FAIL.append("nudos: la conexion soldada en una columna I lleva placas de continuidad")
    nw.operations = [o for o in nw.operations if o.kind != OP_CONT]
    if [p for p in AS.build_nodo(nw).parts if "ontinuidad" in p.name]:
        FAIL.append("nudos: sin la operacion de continuidad no debe haber placas")
    # una sola conexion por miembro: la operacion lo garantiza la interfaz; el modelo usa la primera
    print(f"{'operaciones (cope, continuidad)':34} el corte divide la viga; las placas de continuidad aparecen con la operacion: OK")

    # ---------------------------------------------------------------- viga a viga: la secundaria llega a la cara del alma de la principal
    nb = PRE.build(MODE_BEAM, "sec1", "I", "tab")
    mb = AS.build_nodo(nb)
    wm = CATALOG.get(nb.main_shape)
    y0 = float(mb.part("S1").bbox()[0][1])
    if abs(y0 - (wm.tw / 2.0 + nb.members[0].gap)) > 1e-6:
        FAIL.append(f"nudos: la secundaria debe empezar en tw/2 + retranqueo = {wm.tw / 2 + 0.5:.4f}: {y0:.4f}")
    nb.members[0].az = 0.0
    if not AS.build_nodo(nb).notes:
        FAIL.append("nudos: un miembro paralelo al principal debe dejar una advertencia")
    print(f"{'viga a viga':34} secundaria en tw/2 + retranqueo = {y0:.3f} in; miembro paralelo advertido: OK")

    # ---------------------------------------------------------------- cartelas: una por plano
    for geom, nmem, ngus in (("V", 2, 1), ("N", 2, 1), ("X", 4, 1), ("D", 1, 1)):
        nt = PRE.build(MODE_CHORD, geom, "I", "gus_bolt")
        mt = AS.build_nodo(nt)
        g = [p for p in mt.parts if p.kind == "gusset"]
        if len(nt.members) != nmem or len(g) != ngus or not mt.bolts:
            FAIL.append(f"nudos: crucetas {geom}: {len(nt.members)} miembros, {len(g)} cartelas, {len(mt.bolts)} pernos")
    nt = PRE.build(MODE_CHORD, "V", "I", "gus_weld")
    mt = AS.build_nodo(nt)
    if mt.bolts or not [p for p in mt.parts if p.kind == "gusset"]:
        FAIL.append("nudos: cartela con miembros soldados: sin pernos y con cartela")
    nt.members[1].az = 90.0
    if len([p for p in AS.build_nodo(nt).parts if p.kind == "gusset"]) != 2:
        FAIL.append("nudos: dos diagonales en planos distintos llevan dos cartelas")
    print(f"{'crucetas':34} V, N, X, D: una cartela por plano; atornillada con pernos, soldada sin pernos: OK")

    # ---------------------------------------------------------------- todos los presets arman un modelo valido y verificable
    n_models = 0
    for mode, geoms in PRE.GEOMS.items():
        for gk, gn, _f in geoms:
            for sk, _sn in PRE.SECTION_KEYS:
                for _grp, items in PRE.DESIGNS[mode]:
                    for dk, _dn, ck in items:
                        nd_ = PRE.build(mode, gk, sk, dk)
                        try:
                            mm = AS.build_nodo(nd_, name=gn)
                        except Exception as e:
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: {type(e).__name__}: {e}")
                            traceback.print_exc()
                            continue
                        n_models += 1
                        if not mm.parts:
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk} sin piezas")
                        for pt in mm.parts:
                            P = np.vstack([p.corners() for p in pt.prisms])
                            if not np.all(np.isfinite(P)):
                                FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: coordenadas no finitas en {pt.name}")
                        if ck is None and (nd_.operations or mm.bolts or [p for p in mm.parts if p.kind in ("plate", "angle", "gusset", "stiff")]):
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: en blanco no debe llevar herrajes")
                        if ck is not None and not nd_.operations:
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: el diseño no genero operaciones")
                        if any("no toca" in n for n in mm.notes):
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: {mm.notes[0]}")
                        if nd_.operations:                        # con cargas unitarias, las verificaciones corren sin excepcion
                            for m in nd_.members:
                                nd_.loads.append(Load("U", m.name, N=5.0, Vz=8.0, My=40.0))
                            q = Project(); q.ctype = {MODE_COL: CT_NODE, MODE_BEAM: CT_B2B, MODE_CHORD: CT_TRUSS}[mode]
                            setattr(q, ATTR_OF[q.ctype], nd_)
                            try:
                                R = solve_conn(q)
                                if not R.checks or any(not math.isfinite(c.ratio) for c in R.checks) or R.max_ratio > 50.0:
                                    FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: verificaciones vacias o no finitas")
                            except Exception as e:
                                FAIL.append(f"nudos: verificacion {mode}/{gk}/{sk}/{dk}: {type(e).__name__}: {e}")
                                traceback.print_exc()
    print(f"{'presets':34} {n_models} combinaciones de geometria, seccion y diseño: modelo 3D y verificacion sin errores")

    # ---------------------------------------------------------------- vista: escena y PNG con el z-buffer propio (sin OpenGL)
    tmp = tempfile.mkdtemp(prefix="scpnodes_")
    for mode in (MODE_COL, MODE_BEAM, MODE_CHORD):
        nd_ = PRE.default_nodo(mode)
        sc = SC.scene_model(AS.build_nodo(nd_, name=mode), loads=False, tags=True)
        p = os.path.join(tmp, f"{mode}.png")
        SC.render_scene_png(sc, p, 24.0, 50.0, size=(420, 320))
        from PIL import Image
        im = np.asarray(Image.open(p).convert("L"))
        if float((im < 240).mean()) < 0.03 or len(sc.labels) != len(nd_.members):
            FAIL.append(f"nudos: imagen del modelo {mode} casi vacia o sin nombres de miembros")
    print(f"{'vista 3D (z-buffer propio)':34} escena e imagen de los tres modulos, con los nombres de los miembros: OK")

    # ---------------------------------------------------------------- verificaciones por codigo: comparacion con calculo a mano
    # (1) cartela atornillada en traccion, miembro HSS (2 planos de corte): cortante por perno = P / nb, capacidad = φ·Fnv·Ab·2
    def prj_of(ct, nd_):
        q = Project(); q.ctype = ct; q.element = "T-1"
        setattr(q, ATTR_OF[ct], nd_)
        return q

    def by_key(R, suffix):
        return [c for c in R.checks if c.key.endswith(suffix)]

    ng = PRE.build(MODE_CHORD, "D", "HSS", "gus_bolt")
    ng.members[0].shape = "HSS4X4X1/4"
    ng.operations[0].n_bolts, ng.operations[0].bolt_size, ng.operations[0].bolt_grade, ng.operations[0].bolt_s = 3, "3/4", "A325-N", 3.0
    ng.loads = [Load("T", "D1", N=60.0)]
    R = solve_conn(prj_of(CT_TRUSS, ng))
    cb = by_key(R, "g_bolt")[0]
    Ab = math.pi * 0.75 ** 2 / 4.0
    want_cap = 0.75 * 54.0 * Ab * 2
    if abs(cb.demand - 60.0 / 6.0) > 1e-9 or abs(cb.capacity - want_cap) > 0.05:
        FAIL.append(f"nudos: cortante de los pernos de la cartela: demanda {cb.demand:.3f} (10), capacidad {cb.capacity:.3f} ({want_cap:.3f})")
    sh = CATALOG.get("HSS4X4X1/4")
    fy = M.find(M.SHAPE_STEELS, ng.members[0].steel).Fy
    cy = by_key(R, "g_mem_y")[0]
    if abs(cy.capacity - 0.90 * fy * sh.A) > 0.05:
        FAIL.append(f"nudos: fluencia del miembro: {cy.capacity:.2f} contra {0.90 * fy * sh.A:.2f}")
    # Whitmore: Lw = 2·Lb·tan30° + gauge, φ = 0.90 · Fy · t · Lw
    pl = M.find(M.PLATE_STEELS, ng.operations[0].plate_steel, 1)
    Lb = 2 * 3.0
    gauge = max(min(sh.d * 0.5, 6.0), 2.5)
    Lw = 2 * Lb * math.tan(math.radians(30)) + gauge
    cw = by_key(R, "g_whit_y")[0]
    if abs(cw.capacity - 0.90 * pl.Fy * ng.operations[0].plate_t * Lw) > 0.05:
        FAIL.append(f"nudos: Whitmore: {cw.capacity:.2f} contra {0.90 * pl.Fy * ng.operations[0].plate_t * Lw:.2f}")
    # el D/C crece con la carga (monotonia) y es proporcional en las verificaciones lineales
    ng.loads = [Load("T", "D1", N=30.0)]
    R2 = solve_conn(prj_of(CT_TRUSS, ng))
    for k in ("g_bolt", "g_whit_y", "g_mem_y", "g_wp"):
        a, b = by_key(R, k)[0].ratio, by_key(R2, k)[0].ratio
        if abs(a - 2.0 * b) > 1e-6 * max(a, 1.0):
            FAIL.append(f"nudos: {k} debe ser proporcional a la carga: {a} contra 2 x {b}")
    # (2) alas soldadas (CJP): Pf = |My| / (d − tf) + N/2 contra 0.9·Fy·bf·tf
    nw = PRE.build(MODE_BEAM, "sec1", "I", "weld")
    nw.members[0].shape = "W16X31"
    nw.loads = [Load("M", nw.members[0].name, My=1200.0, N=10.0)]
    R = solve_conn(prj_of(CT_B2B, nw))
    cf = by_key(R, "wf_flange")
    bm = CATALOG.get("W16X31")
    fyb = M.find(M.SHAPE_STEELS, nw.members[0].steel).Fy
    if not cf or abs(cf[0].demand - (1200.0 / (bm.d - bm.tf) + 5.0)) > 1e-6 or abs(cf[0].capacity - 0.9 * fyb * bm.bf * bm.tf) > 0.05:
        FAIL.append(f"nudos: alas soldadas: {[(c.demand, c.capacity) for c in cf]}")
    # (3) placa simple: sin cortante no hay demanda; con cortante crece de forma monotona
    nt = PRE.build(MODE_COL, "int1", "I", "tab")
    ratios = []
    for V in (0.0, 10.0, 20.0, 40.0):
        nt.loads = [Load("V", "V1", Vz=V)]
        Rv = solve_conn(prj_of(CT_NODE, nt))
        ratios.append(next(c.ratio for c in Rv.checks if "excentricidad" in c.title))         # cortante de los pernos con excentricidad (IC)
    if not (ratios[0] <= 1e-9 and ratios[1] > 0 and all(a < b for a, b in zip(ratios[1:], ratios[2:]))):
        FAIL.append(f"nudos: placa simple: D/C no monotono con el cortante {ratios}")
    # signo del cortante: la verificacion usa |V|
    nt.loads = [Load("V", "V1", Vz=-20.0)]
    r_neg = solve_conn(prj_of(CT_NODE, nt)).max_ratio
    nt.loads = [Load("V", "V1", Vz=20.0)]
    r_pos = solve_conn(prj_of(CT_NODE, nt)).max_ratio
    if abs(r_neg - r_pos) > 1e-9:
        FAIL.append(f"nudos: el signo del cortante no debe cambiar el D/C: {r_neg} / {r_pos}")
    print(f"{'verificaciones (a mano)':34} cortante de pernos {cb.demand:.2f}/{cb.capacity:.2f} kip, Whitmore Lw = {Lw:.2f} in, alas CJP, proporcionalidad y monotonia: OK")

    # ---------------------------------------------------------------- varios casos de carga: gobierna el peor y el resumen lo informa
    nt = PRE.build(MODE_COL, "int2", "I", "tab")
    nt.loads = [Load("D", "V1", Vz=10.0), Load("D", "V2", Vz=10.0), Load("L", "V1", Vz=30.0), Load("L", "V2", Vz=5.0)]
    R = solve_conn(prj_of(CT_NODE, nt))
    if [c["name"] for c in R.combo_rows] != ["D", "L"] or R.combo_rows[1]["ratio"] <= R.combo_rows[0]["ratio"] or R.combo_gov != 1:
        FAIL.append(f"nudos: casos de carga: {[(c['name'], c['ratio']) for c in R.combo_rows]}, gobierna {R.combo_gov}")
    # sin cargas: avisa
    nt.loads = []
    R = solve_conn(prj_of(CT_NODE, nt))
    if not any("cargas" in w.lower() for w in R.warnings):
        FAIL.append("nudos: sin cargas debe avisar")
    # sin operaciones: avisa
    nt.operations = []
    if not any("operaci" in w.lower() for w in solve_conn(prj_of(CT_NODE, nt)).warnings):
        FAIL.append("nudos: sin operaciones debe avisar")
    print(f"{'casos de carga y avisos':34} gobierna el peor caso; sin cargas o sin operaciones avisa: OK")

    # ---------------------------------------------------------------- ejemplos del proyecto
    for ex, ct in (("NC-01_nudo_viga_columna", CT_NODE), ("VV-01_viga_a_viga", CT_B2B), ("CR-01_crucetas", CT_TRUSS)):
        bk = load_book(f"ejemplos/{ex}.scp")
        if len(bk) != 1 or bk[0].ctype != ct:
            FAIL.append(f"nudos: ejemplo {ex} no abre como {ct}")
            continue
        R = solve_conn(bk[0])
        if not R.checks or not R.ok or R.max_ratio <= 0.0:
            FAIL.append(f"nudos: ejemplo {ex}: {len(R.checks)} verificaciones, ok = {R.ok}, D/C max = {R.max_ratio}")
    print(f"{'ejemplos':34} NC-01, VV-01 y CR-01 abren y cumplen")

    # ---------------------------------------------------------------- guardar y leer
    prj = []
    for ct in (CT_NODE, CT_B2B, CT_TRUSS):
        q = Project(); q.ctype = ct; q.element = module_for(ct).PREFIX + "-1"
        nd_ = getattr(q, ATTR_OF[ct])
        nd_.members[0].az, nd_.members[0].shape = 33.0, "W21X44"
        nd_.operations.append(Operation(kind=OP_COPE, member=nd_.members[0].name, cope_top=1.5))
        nd_.loads.append(Load("C1", nd_.members[0].name, N=3.0, Vz=7.0, My=-25.0))
        nd_.main_end = END_LABELS[nd_.mode][1]
        prj.append(q)
    f = os.path.join(tmp, "nudos.scp")
    save_book(f, [Project()] + prj)
    bk = load_book(f)
    if [p.ctype for p in bk] != [CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS] or any(getattr(a, ATTR_OF[a.ctype]) != getattr(b, ATTR_OF[a.ctype]) for a, b in zip(prj, bk[1:])):
        FAIL.append("nudos: el libro no conserva los datos de los modulos")
    n0 = bk[1].ncol
    if n0.members[0].az != 33.0 or not isinstance(n0.members[0], Member) or not all(isinstance(o, Operation) for o in n0.operations) \
            or not all(isinstance(x, Load) for x in n0.loads) or n0.loads[0].My != -25.0:
        FAIL.append("nudos: miembros, operaciones y cargas deben volver como sus clases")
    # archivo de la version anterior (la conexion era un campo del miembro): se migra a operaciones
    d_ = json.load(open(f, encoding="utf-8"))
    cx = d_["conexiones"][1]
    cx["ncol"]["operations"] = []
    cx["ncol"]["loads"] = []
    cx["ncol"]["members"][0]["conn"] = "Corte — placa simple"
    f1 = os.path.join(tmp, "v_anterior.scp")
    json.dump(d_, open(f1, "w", encoding="utf-8"))
    ops = load_book(f1)[1].ncol.operations
    if len(ops) != 1 or ops[0].kind != OP_TAB or ops[0].member != cx["ncol"]["members"][0]["name"]:
        FAIL.append(f"nudos: la conexion del miembro (version anterior) debe migrar a una operacion: {ops}")
    # libros con tipologias retiradas: se omiten y se avisa
    d_ = json.load(open(f, encoding="utf-8"))
    leg = copy.deepcopy(d_["conexiones"][1]); leg["ctype"] = "Conexion de corte — placa simple (viga a viga / viga a columna)"; leg["element"] = "VS-1"
    d_["conexiones"].append(leg)
    f2 = os.path.join(tmp, "viejo.scp")
    json.dump(d_, open(f2, "w", encoding="utf-8"))
    bk2 = load_book(f2)
    if len(bk2) != 4 or MD.LAST_SKIPPED != [("VS-1", leg["ctype"])]:
        FAIL.append(f"nudos: una conexion de tipologia retirada debe omitirse con aviso: {len(bk2)} conexiones, {MD.LAST_SKIPPED}")
    for ex in ("PB-01_W14X90", "COMP-1_W14X90_traccion"):
        if load_book(f"ejemplos/{ex}.scp")[0].ctype != CT_BASEPLATE:
            FAIL.append(f"nudos: {ex} debe abrir como placa base")
    print(f"{'libros':34} ida y vuelta con operaciones y cargas; version anterior migra; tipologias retiradas se omiten; placa base abre igual")

    # ---------------------------------------------------------------- aleatorio: cualquier seccion del catalogo, angulos, posiciones y operaciones
    rnd = random.Random(20261009)
    labels = {fam: CATALOG.by_family(fam) for fam in CATALOG.families()}
    n = 0
    for k in range(300):
        mode = rnd.choice((MODE_COL, MODE_BEAM, MODE_CHORD))
        nd_ = Nodo(mode=mode, main_shape=rnd.choice(labels[rnd.choice(list(labels))]), main_roll=rnd.choice((0.0, 45.0, 90.0, -30.0)),
                   main_slope=0.0 if mode == MODE_COL else rnd.choice((0.0, 15.0, -20.0)), main_end=rnd.choice(END_LABELS[mode]))
        for i in range(rnd.randint(0, 6)):
            nd_.members.append(Member(name=f"M{i}", shape=rnd.choice(labels[rnd.choice(list(labels))]), az=rnd.uniform(-360, 360),
                                      el=rnd.choice((0.0, 0.0, 30.0, -45.0, 60.0, -90.0, 90.0, rnd.uniform(-89, 89))), pos=rnd.uniform(-60, 60),
                                      off=rnd.uniform(-10, 10), L=rnd.uniform(6, 120), roll=rnd.choice((0.0, 90.0, 33.0)), gap=rnd.uniform(0, 3)))
            for _ in range(rnd.randint(0, 2)):
                kind = rnd.choice(OPERATIONS)
                nd_.operations.append(Operation(kind=kind, member=f"M{i}", n_bolts=rnd.randint(1, 8), bolt_s=rnd.choice((1.5, 3.0, 4.0)),
                                                plate_t=rnd.choice((0.125, 0.375, 1.0)), ep_ext=rnd.uniform(1, 6), cope_top=rnd.uniform(0, 4),
                                                cope_bot=rnd.uniform(0, 4), cope_len=rnd.uniform(1, 8), cont_t=rnd.choice((0.25, 0.5)),
                                                weld_size=rnd.choice((0.125, 0.25, 0.5))))
            nd_.loads.append(Load("R", f"M{i}", N=rnd.uniform(-50, 50), Vy=rnd.uniform(-20, 20), Vz=rnd.uniform(-40, 40), T=rnd.uniform(-30, 30),
                                  My=rnd.uniform(-500, 500), Mz=rnd.uniform(-300, 300)))
        try:
            mm = AS.build_nodo(nd_)
            for pt in mm.parts:
                P = np.vstack([p.corners() for p in pt.prisms])
                if not np.all(np.isfinite(P)):
                    raise ValueError(f"no finito en {pt.name}")
            for b in mm.bolts:
                if not np.all(np.isfinite(b.p)):
                    raise ValueError("perno no finito")
            R = adapters.run(prj_of({MODE_COL: CT_NODE, MODE_BEAM: CT_B2B, MODE_CHORD: CT_TRUSS}[mode], nd_), nd_)
            for c in R.checks:
                if not math.isfinite(c.ratio) or not math.isfinite(c.demand) or not math.isfinite(c.capacity):
                    raise ValueError(f"verificacion no finita: {c.title}")
            if k % 25 == 0:
                SC.scene_model(mm, loads=False, tags=True)
            n += 1
        except Exception as e:
            FAIL.append(f"nudos aleatorio {k}: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
    print(f"{'aleatorio':34} {n} nudos con secciones, angulos, posiciones, operaciones y cargas al azar: sin excepciones ni valores no finitos")

    # ---------------------------------------------------------------- memoria de calculo (PDF y Word) y modo por lotes
    from steelconpro import report
    from steelconpro.conn import save_figures
    bk = load_book("ejemplos/NC-01_nudo_viga_columna.scp")
    pj = bk[0]
    Rr = solve_conn(pj)
    figs = save_figures(pj, Rr, os.path.join(tmp, "fig"))
    fp, fd = os.path.join(tmp, "m.pdf"), os.path.join(tmp, "m.docx")
    report.export_pdf(pj, Rr, fp, figs, True)
    report.export_docx(pj, Rr, fd, figs, True)
    if os.path.getsize(fp) < 20000 or not open(fp, "rb").read(5).startswith(b"%PDF") or os.path.getsize(fd) < 20000 or Rr.rec is None:
        FAIL.append(f"nudos: memoria de calculo: pdf {os.path.getsize(fp)} bytes, docx {os.path.getsize(fd)} bytes")
    try:
        import fitz  # noqa
        txt = "".join(pg.get_text() for pg in fitz.open(fp))
        if "VEREDICTO" not in txt or "Placa simple" not in txt:
            FAIL.append("nudos: el PDF no contiene el veredicto o las operaciones")
    except ImportError:
        pass
    _run = importlib.import_module("run")
    buf = io.StringIO()
    out = os.path.join(tmp, "imgs")
    with contextlib.redirect_stdout(buf):
        rc = _run.batch_node(pj, ["x", "--3d", out, "--pdf", os.path.join(tmp, "b.pdf")])
    if rc != 0 or not all(os.path.exists(os.path.join(out, nm)) for nm in ("modelo3d_iso.png", "modelo3d_planta.png", "esquema.png")) \
            or "CUMPLE" not in buf.getvalue() or not os.path.exists(os.path.join(tmp, "b.pdf")):
        FAIL.append(f"nudos: modo por lotes: {buf.getvalue()}")
    print(f"{'memoria y lotes':34} PDF ({os.path.getsize(fp) // 1024} KB) y Word ({os.path.getsize(fd) // 1024} KB) con el desarrollo de las ecuaciones; run.py verifica y exporta")


    # ---------------------------------------------------------------- secciones de forma libre (Section Designer): propiedades contra formulas cerradas
    from steelconpro import sections as SEC, shapes as SH
    r = SEC.section_props([SEC._R(0, 0, 4, 10)])
    ok_ = abs(r["A"] - 40) < 1e-9 and abs(r["Ix"] - 4 * 1000 / 12) < 1e-6 and abs(r["Zx"] - 100) < 1e-6 and abs(r["Zy"] - 40) < 1e-6 and abs(r["Sx"] - 4 * 100 / 6) < 1e-6
    c_ = SEC.section_props([{"t": "circ", "x": 3, "y": -2, "d": 4}])
    ok_ &= abs(c_["A"] - 4 * math.pi) < 1e-9 and abs(c_["Zx"] - 4 ** 3 / 6) < 5e-3 and abs(c_["cx"] - 3) < 1e-9 and abs(c_["cy"] + 2) < 1e-9
    t_ = SEC.section_props(SEC.t_tube(8, 0.5))
    ok_ &= abs(t_["Zx"] - (8 ** 3 - 7 ** 3) / 6) < 0.01 and abs(t_["J"] - 2 * t_["Ix"]) < 1e-9
    tr = SEC.section_props([{"t": "poly", "pts": [[0, 0], [6, 0], [0, 3]]}])
    ok_ &= abs(tr["Ix"] - 6 * 27 / 36) < 1e-9 and abs(tr["cx"] - 2) < 1e-9 and abs(tr["cy"] - 1) < 1e-9
    rot = SEC.section_props([SEC._R(1, 2, 2, 2, 45)])
    ok_ &= abs(rot["Ix"] - 16 / 12) < 1e-9 and abs(rot["Ixy"]) < 1e-9
    w = CATALOG.get("W14X90")
    wi = SEC.section_props(SEC.t_i_shape(w.d, w.bf, w.tf, w.tw))
    ok_ &= abs(wi["Ix"] / w.Ix - 1) < 0.03 and abs(wi["Zx"] / w.Zx - 1) < 0.03 and abs(wi["A"] / w.A - 1) < 0.03          # sin los radios de laminacion
    ang = SEC.section_props(SEC.t_angle(6, 4, 0.5))
    ok_ &= abs(ang["Ixy"]) > 1.0 and abs(ang["I1"] + ang["I2"] - ang["Ix"] - ang["Iy"]) < 1e-9
    ok_ &= abs(SEC.overlap_area([SEC._R(0, 0, 4, 4), SEC._R(2, 0, 4, 4)]) - 8.0) < 0.2
    ok_ &= bool(SEC.valid_comp({"t": "poly", "pts": [[0, 0], [1, 1], [1, 0], [0, 1]]})) and bool(SEC.valid_comp({"t": "rect", "x": 0, "y": 0, "w": 0, "h": 1}))
    if not ok_:
        FAIL.append(f"secciones libres: propiedades contra formulas cerradas: rect {r['A']}, {r['Ix']}, {r['Zx']}; circulo {c_['Zx']}; tubo {t_['Zx']}; I {wi['Ix']} / {w.Ix}")
    for nm_, (spec_, _fn) in SEC.TEMPLATES.items():
        pr_ = SEC.section_props(SEC.build_template(nm_))
        if not pr_ or pr_["A"] <= 0 or pr_["Ix"] <= 0 or pr_["Iy"] <= 0 or SEC.overlap_area(SEC.build_template(nm_)) > 0.01 * pr_["A"]:
            FAIL.append(f"secciones libres: la plantilla «{nm_}» no es una seccion valida sin superposiciones")
    print(f"{'secciones libres (propiedades)':34} rectangulo, circulo, tubo, triangulo, giro 45°, perfil I contra el catalogo y {len(SEC.TEMPLATES)} plantillas: OK")

    # ---------------------------------------------------------------- secciones libres dentro del nudo: 3D, rayo, verificaciones y archivo
    old_db = SH.USER_DB
    SH.USER_DB = type(old_db)(os.path.join(tmp, "shapes_test.json"))
    free = {}
    try:
        free["LB-I"] = SH.make_general("LB-I", SEC.t_i_shape(14, 10, 0.75, 0.4, 6.0, 0.5))
        free["LB-BOX"] = SH.make_general("LB-BOX", SEC.t_box(10, 12, 0.5, 0.5) + [{"t": "ring", "x": 0, "y": 0, "d": 4, "ti": 0.5}])
        free["LB-L"] = SH.make_general("LB-L", SEC.t_angle(6, 4, 0.5))
        free["LB-POLY"] = SH.make_general("LB-POLY", SEC.t_polygon(6, 8.0))
        for sh_ in free.values():
            CATALOG.add_free(sh_)
        if "LB-I" in CATALOG.by_family("Personalizado") or SH.FREE_FAMILY in CATALOG.families() or SH.FREE_FAMILY not in CATALOG.families(free=True) \
                or "LB-I" not in CATALOG.by_family(SH.FREE_FAMILY):
            FAIL.append("secciones libres: la familia libre solo debe aparecer con free=True")
        if not all(CATALOG.get(k).kind == SH.GEN and CATALOG.get(k).pieces() for k in free):
            FAIL.append("secciones libres: no quedaron en el catalogo")
        n_free = 0
        for main_ in free:
            for mem_ in list(free) + ["W16X31", "HSS6X6X3/8"]:
                for mode_ in (MODE_COL, MODE_BEAM, MODE_CHORD):
                    nd_ = PRE.build(mode_, {MODE_COL: "int2", MODE_BEAM: "sec2", MODE_CHORD: "V"}[mode_], "I")
                    nd_.main_shape = main_
                    for m_ in nd_.members:
                        m_.shape = mem_
                        nd_.loads.append(Load("U", m_.name, N=4.0, Vz=6.0, My=30.0))
                    mm_ = AS.build_nodo(nd_)
                    for pt_ in mm_.parts:
                        if not np.all(np.isfinite(np.vstack([p_.corners() for p_ in pt_.prisms]))):
                            FAIL.append(f"secciones libres: coordenadas no finitas {main_}/{mem_}/{mode_}")
                    ct_ = {MODE_COL: CT_NODE, MODE_BEAM: CT_B2B, MODE_CHORD: CT_TRUSS}[mode_]
                    Rr_ = solve_conn(prj_of(ct_, nd_))
                    if any(not math.isfinite(c2_.ratio) for c2_ in Rr_.checks):
                        FAIL.append(f"secciones libres: verificacion no finita {main_}/{mem_}/{mode_}")
                    SC.scene_model(mm_, loads=False, tags=True)
                    n_free += 1
        e1 = AS.outer_extent(CATALOG.get("LB-I"))
        sx_ = AS.ray_exit(e1, (0, 0), (1, 0))
        if abs(sx_ - 0.2) > 1e-6:
            FAIL.append(f"secciones libres: el rayo por el alma de LB-I debe salir en tw/2 = 0.2: {sx_}")
        e2 = AS.outer_extent(CATALOG.get("LB-BOX"))
        if abs(AS.ray_exit(e2, (0, 0), (1, 0)) - 5.0) > 1e-6 or abs(AS.ray_exit(e2, (0, 0), (0, 1)) - 6.0) > 1e-6:
            FAIL.append("secciones libres: el rayo contra la caja debe salir en b/2 y h/2")
        nf = PRE.default_nodo(MODE_COL)
        nf.main_shape, nf.members[0].shape = "LB-BOX", "LB-I"
        q_ = Project(); q_.ctype = CT_NODE; q_.ncol = nf
        ff = os.path.join(tmp, "libre.scp")
        save_book(ff, [q_])
        for k in ("LB-I", "LB-BOX"):
            del CATALOG.shapes[k]
        CATALOG._reindex()
        load_book(ff)
        g_ = CATALOG.get("LB-BOX")
        if g_ is None or g_.kind != SH.GEN or len(g_.comps) != 5 or abs(g_.A - free["LB-BOX"].A) > 1e-9 or not CATALOG.get("LB-I"):
            FAIL.append("secciones libres: el proyecto debe llevar dentro las secciones libres que usa")
        print(f"{'secciones libres en el nudo':34} {n_free} nudos con 4 secciones libres como principal y como miembros: 3D, rayo, verificaciones (NO EVALUADO donde no aplica) y archivo: OK")
    finally:
        for k in list(free):
            CATALOG.shapes.pop(k, None)
        CATALOG._reindex()
        SH.USER_DB = old_db

    # ---------------------------------------------------------------- materiales: pernos y aceros propios llegan a los calculos y al archivo
    from steelconpro.conn import common as CM, specs as SPX
    old_mat = M._mat_file
    M._mat_file = lambda: type(old_db)(os.path.join(tmp, "materials_test.json"))
    try:
        M.save_user_materials({"steel": [{"name": "Acero T-70", "Fy": 70.0, "Fu": 90.0, "E": 29500.0, "nu": 0.29, "rho": 7850.0}],
                               "bolt": [{"name": "A354-BD-X", "Fnt": 113.0, "Fnv": 84.0}, {"name": "A325-N", "Fnt": 1.0, "Fnv": 1.0}],
                               "electrode": [{"name": "E75XX", "FEXX": 75.0}], "anchor": [], "concrete": []})
        st_ = M.find(M.SHAPE_STEELS, "Acero T-70")
        if st_.Fy != 70.0 or abs(st_.G - 29500.0 / (2 * 1.29)) > 1e-6 or not M.is_extra("steel", "Acero T-70") or M.is_extra("steel", "ASTM A36"):
            FAIL.append("materiales: acero propio con E y ν")
        if CM.FNV["A325-N"] != 54.0:
            FAIL.append("materiales: no se puede sobrescribir un grado de AISC")
        if "A354-BD-X" not in SPX.BOLT_GRADES or abs(CM.bolt_shear_rn(0.75, "A354-BD-X") - 84.0 * math.pi * 0.75 ** 2 / 4) > 1e-9:
            FAIL.append("materiales: perno propio en las verificaciones")
        if M.find(M.ELECTRODES, "E75XX", 0).FEXX != 75.0:
            FAIL.append("materiales: electrodo propio")
        nb_ = PRE.build(MODE_COL, "int1", "I", "tab")
        nb_.operations[0].bolt_grade, nb_.members[0].steel = "A354-BD-X", "Acero T-70"
        nb_.loads = [Load("U", "V1", Vz=40.0)]
        qb_ = prj_of(CT_NODE, nb_)
        cap_ = next(c2_.capacity for c2_ in solve_conn(qb_).checks if "excentricidad" in c2_.title)
        nb_.operations[0].bolt_grade = "A325-N"
        cap0_ = next(c2_.capacity for c2_ in solve_conn(qb_).checks if "excentricidad" in c2_.title)
        if cap_ <= cap0_ * 1.2:
            FAIL.append(f"materiales: el perno propio (Fnv 84) debe dar mas capacidad que A325-N (54): {cap_} / {cap0_}")
        nb_.operations[0].bolt_grade = "A354-BD-X"
        fm_ = os.path.join(tmp, "mats.scp")
        save_book(fm_, [qb_])
        emb = json.load(open(fm_, encoding="utf-8"))["materiales"]
        if [x["name"] for x in emb["bolt"]] != ["A354-BD-X"] or [x["name"] for x in emb["steel"]] != ["Acero T-70"] or emb["steel"][0]["E"] != 29500.0:
            FAIL.append(f"materiales: el proyecto debe llevar el perno y el acero propios que usa: {emb}")
        print(f"{'materiales propios':34} acero con E/ν/ρ, perno (Fnt, Fnv) que cambia la capacidad {cap0_:.1f} -> {cap_:.1f} kip, electrodo, y el proyecto los lleva dentro: OK")
    finally:
        M._mat_file = old_mat
        for k in M.USER_NAMES:
            M.USER_NAMES[k] = set()
        M.SHAPE_STEELS[:] = [x for x in M.SHAPE_STEELS if x.name != "Acero T-70"]
        M.PLATE_STEELS[:] = [x for x in M.PLATE_STEELS if x.name != "Acero T-70"]
        M.ELECTRODES[:] = [x for x in M.ELECTRODES if x.name != "E75XX"]
        CM.FNT.pop("A354-BD-X", None)
        CM.FNV.pop("A354-BD-X", None)
        if "A354-BD-X" in SPX.BOLT_GRADES:
            SPX.BOLT_GRADES.remove("A354-BD-X")

    # ---------------------------------------------------------------- exportacion de la geometria (STEP): Gmsh en un proceso aparte, sin malla ni analisis
    from steelconpro.conn.fem import driver as _drv
    sp = os.path.join(tmp, "nudo.step")
    _drv.export_step(prj[2], None, sp)
    if not os.path.exists(sp) or "ISO-10303" not in open(sp, errors="ignore").read(200):
        FAIL.append("nudos: no se escribio el STEP")
    print(f"{'exportacion STEP':34} geometria del nudo ({os.path.getsize(sp) // 1024} KB): OK")

    # ---------------------------------------------------------------- interfaz (offscreen, solo si hay Qt)
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from steelconpro import ui
        from steelconpro.ui_wizard import NewConnectionDialog
        app = QApplication.instance() or QApplication([])
        win = ui.MainWindow()
        for ct, pre in ((CT_NODE, ("int4", "I", "ep_flush")), (CT_B2B, ("sec2", "HSS", "tab")), (CT_TRUSS, ("V", "RND", "gus_bolt"))):
            win.add_connection(ct, pre)
            app.processEvents()
            tabs_in = [win.tabs_in.tabText(i) for i in range(win.tabs_in.count()) if win.tabs_in.isTabVisible(i)]
            tabs_out = {win.tabs_out.tabText(i): win.tabs_out.isTabEnabled(i) for i in range(win.tabs_out.count()) if win.tabs_out.isTabVisible(i)}
            mod = module_for(ct)
            if tabs_in != ["Proyecto", mod.TAB] or tabs_out.get("Analisis FEM") is not False or tabs_out.get("Resultados") is not True \
                    or tabs_out.get("Modelo 3D") is not True or not win.btn3d.isEnabled():
                FAIL.append(f"nudos UI {ct}: pestañas {tabs_in} / {tabs_out}, VERIFICAR habilitado = {win.btn3d.isEnabled()}")
            nd_ = getattr(win.prj, ATTR_OF[ct])
            ref = PRE.build(MODE_OF[ct], pre[0], pre[1], pre[2])
            if len(nd_.members) != len(ref.members) or len(nd_.operations) != len(ref.operations):
                FAIL.append(f"nudos UI {ct}: el asistente no aplico la geometria y las operaciones")
            form = win.fnamed[mod.TAB]
            mp, op, lp = form.members_pg, form.ops_pg, form.loads_pg
            m0 = nd_.members[0]
            mp.mf.w("m.az").setValue(30.0)
            mp.m_pick.set_label("W21X44"); mp.m_pick.changed.emit()
            if m0.az != 30.0 or m0.shape != "W21X44":
                FAIL.append(f"nudos UI {ct}: la edicion del miembro no se guardo: {m0.az} {m0.shape}")
            n0 = len(nd_.members)
            mp._add(); mp._dup(); mp._del()
            if len(nd_.members) != n0 + 1:
                FAIL.append(f"nudos UI {ct}: agregar/duplicar/quitar miembros: {n0} -> {len(nd_.members)}")
            # operaciones: una conexion por miembro (la nueva reemplaza), agregar corte, quitar, mover
            nops = len(nd_.operations)
            op.selected_member = m0.name
            op._add(OP_SEAT, m0.name)
            if len([o for o in nd_.operations if o.member == m0.name and o.is_connection]) != 1 or nd_.connection_of(m0.name).kind != OP_SEAT:
                FAIL.append(f"nudos UI {ct}: la nueva conexion debe reemplazar a la anterior del miembro")
            op._add(OP_COPE, m0.name)
            if nd_.operations[-1].kind != OP_COPE:
                FAIL.append(f"nudos UI {ct}: agregar el corte")
            op._dup()
            op._del()
            # cargas
            lp._add_case()
            if not nd_.loads or {x.case for x in nd_.loads} != {"Caso 1"}:
                FAIL.append(f"nudos UI {ct}: agregar caso de carga: {[x.case for x in nd_.loads]}")
            lp.tbl.item(0, 4).setText("12.5")                           # Vz del primer miembro
            lp.store(win.prj)
            if abs(nd_.loads[0].Vz - win.us.inn("F", 12.5)) > 1e-9:
                FAIL.append(f"nudos UI {ct}: la carga editada no se guardo: {nd_.loads[0]}")
            mp.w(f"{ATTR_OF[ct]}.main_end").setCurrentIndex(1)
            if nd_.end_index != 1:
                FAIL.append(f"nudos UI {ct}: extremo del miembro principal")
            # VERIFICAR: llena la tabla, el veredicto y la memoria; cualquier cambio la deja desactualizada
            win.recalc(); app.processEvents()
            if win._node_fresh() or "SIN VERIFICAR" not in win.lbl_verdict.text():
                FAIL.append(f"nudos UI {ct}: antes de verificar el veredicto debe decir SIN VERIFICAR: '{win.lbl_verdict.text()}'")
            win.run_3d(); app.processEvents()
            if not win._node_fresh() or win.tbl.rowCount() == 0 or ("CUMPLE" not in win.lbl_verdict.text()) or not win.node_res.checks \
                    or "OPERACION" not in win.txt_mem.toPlainText():
                FAIL.append(f"nudos UI {ct}: VERIFICAR no lleno la tabla / el veredicto / la memoria: '{win.lbl_verdict.text()}', {win.tbl.rowCount()} filas")
            if win.tabs_out.currentWidget() is not win.tab_res:
                FAIL.append(f"nudos UI {ct}: VERIFICAR debe mostrar la pestaña Resultados")
            lp.tbl.item(0, 4).setText("99")
            lp.store(win.prj)
            win.recalc(); app.processEvents()
            if win._node_fresh() or "DESACTUALIZADO" not in win.lbl_verdict.text():
                FAIL.append(f"nudos UI {ct}: tras editar, el resultado debe quedar DESACTUALIZADO: '{win.lbl_verdict.text()}'")
            q_, R_ = win.export_target()
            if R_ is None or not R_.checks:
                FAIL.append(f"nudos UI {ct}: export_target sin resultados")
            if win.worker is not None and win.worker.isRunning():
                FAIL.append(f"nudos UI {ct}: VERIFICAR no debe lanzar ningun analisis 3D")
        win._switch(0)
        app.processEvents()
        if not (win.tabs_out.isTabEnabled(win.tabs_out.indexOf(win.tab_fem)) and win.btn3d.isEnabled()) or "CALCULAR" not in win.btn3d.text():
            FAIL.append("nudos UI: la placa base debe conservar sus pestañas de analisis y resultados")
        dlg = NewConnectionDialog(None, CT_NODE)
        dlg.render_all()
        ch = dlg.choice()
        if ch["ctype"] != CT_NODE or not ch["geom"] or not ch["design"] or len(dlg._cache) < 20:
            FAIL.append(f"nudos UI: asistente de nueva conexion: {ch}, {len(dlg._cache)} miniaturas")
        dlg._pick_class(CT_TRUSS); dlg._pick_geom("X", "RND"); dlg._pick_design("gus_weld"); dlg.render_all()
        if dlg.choice() != {"ctype": CT_TRUSS, "geom": "X", "sec": "RND", "design": "gus_weld"}:
            FAIL.append(f"nudos UI: eleccion del asistente: {dlg.choice()}")
        dlg._pick_class(CT_BASEPLATE)
        if dlg.choice()["geom"] is not None:
            FAIL.append("nudos UI: la placa base no tiene geometria en el asistente")
        # ---- biblioteca de secciones, Section Designer y biblioteca de materiales (ventanas)
        from steelconpro.ui_sections import SectionLibrary, SectionDesigner
        from steelconpro.ui_materials import MaterialsLibrary
        from steelconpro import gl3d as _gl, shapes as _SH
        old_db2, old_mat2 = _SH.USER_DB, M._mat_file
        _SH.USER_DB = type(old_db2)(os.path.join(tmp, "shapes_ui.json"))
        M._mat_file = lambda: type(old_db2)(os.path.join(tmp, "materials_ui.json"))
        try:
            if _gl.gl_wanted() or win.use_gl:
                FAIL.append("visor: por omision debe usarse el visor clasico de matplotlib (el OpenGL es opcional)")
            lib = SectionLibrary(win.us, None, pick=True, current="W14X90")
            if lib.tbl.rowCount() > 500 or lib.cb_fam.currentData() != "W":
                FAIL.append("biblioteca de secciones: debe abrir en la familia de la seccion actual")
            lib.cb_fam.setCurrentIndex(0)
            lib.ed_find.setText("")
            lib._fill(select="W14X90")
            if lib.tbl.rowCount() < 1000 or lib._rows[lib.tbl.currentRow()] != "W14X90" or lib.canvas.props.get("A", 0) <= 0:
                FAIL.append(f"biblioteca de secciones: {lib.tbl.rowCount()} filas, seleccion {lib._rows[lib.tbl.currentRow()]}")
            lib.ed_find.setText("HSS6X6X3/8")
            if lib.tbl.rowCount() != 1:
                FAIL.append(f"biblioteca de secciones: la busqueda debe dejar una fila: {lib.tbl.rowCount()}")
            lib._use()
            if lib.selected_label != "HSS6X6X3/8":
                FAIL.append("biblioteca de secciones: Usar esta seccion")
            dsg = SectionDesigner(win.us, None, CATALOG.get("W14X90"))
            if len(dsg.comps) != 3 or abs(dsg.canvas.props["A"] - 26.1) > 0.5 or dsg.ed_name.text() != "W14X90-copia":
                FAIL.append(f"section designer: copia de un perfil estandar: {len(dsg.comps)} componentes, A = {dsg.canvas.props.get('A')}, nombre {dsg.ed_name.text()}")
            dsg.cb_tpl.setCurrentText("Cajón soldado"); dsg._apply_tpl()
            n0_ = len(dsg.comps)
            dsg._add("circ"); dsg._add("poly"); dsg._add("ring")
            dsg._dup(); dsg._mirror(0); dsg._center()
            if len(dsg.comps) != n0_ + 4 or not dsg.canvas.props:
                FAIL.append(f"section designer: agregar / duplicar / espejo: {len(dsg.comps)} componentes")
            dsg.tbl.selectRow(0)
            dsg.fields["w"][1].setValue(20.0 / dsg.fl)                # el cambio de un campo se guarda en el componente y recalcula
            if abs(dsg.comps[0]["w"] - 20.0) > 1e-9:
                FAIL.append("section designer: edicion de un campo")
            dsg.canvas.sel = 0
            x0_ = dsg.comps[0]["x"]
            dsg.canvas._drag = ("move", 0.0, 0.0, x0_, dsg.comps[0]["y"], copy.deepcopy(dsg.comps[0]))
            dsg.comps[0]["x"] = x0_ + 1.0
            dsg._canvas_moved()
            dsg.ed_name.setText("DES-TEST")
            dsg._ok()
            sh_ = dsg.result_shape
            if sh_ is None or sh_.kind != _SH.GEN or sh_.label != "DES-TEST" or sh_.A <= 0:
                FAIL.append("section designer: guardar")
            else:
                CATALOG.add_free(sh_)
                if CATALOG.get("DES-TEST") is None or "DES-TEST" not in CATALOG.by_family(_SH.FREE_FAMILY):
                    FAIL.append("section designer: la seccion guardada debe estar en la familia libre")
                from steelconpro.ui_nodes import SectionPicker
                pk = SectionPicker()
                if _SH.FREE_FAMILY not in [pk.fam.itemText(i) for i in range(pk.fam.count())]:
                    FAIL.append("selector de seccion: debe listar la familia libre")
                pk.set_label("DES-TEST")
                if pk.label() != "DES-TEST":
                    FAIL.append("selector de seccion: no encuentra la seccion libre")
                CATALOG.remove("DES-TEST")
            mlib = MaterialsLibrary(win.us)
            mlib._new("bolt"); mlib._new("steel")
            mlib.data["bolt"][0].update({"name": "UI-BOLT", "Fnt": 100.0, "Fnv": 60.0})
            mlib.data["steel"][0].update({"name": "UI-STEEL", "Fy": 55.0, "Fu": 70.0})
            mlib._save()
            if M.find(M.SHAPE_STEELS, "UI-STEEL").Fy != 55.0 or "UI-BOLT" not in {b.name for b in M.bolt_grades()}:
                FAIL.append("biblioteca de materiales: no registro los materiales nuevos")
            mlib2 = MaterialsLibrary(win.us)
            mlib2.data["bolt"] = []; mlib2.data["steel"] = []
            mlib2._save()
            if any(x.name == "UI-STEEL" for x in M.SHAPE_STEELS) or "UI-BOLT" in {b.name for b in M.bolt_grades()}:
                FAIL.append("biblioteca de materiales: no retiro los materiales eliminados")
        finally:
            _SH.USER_DB, M._mat_file = old_db2, old_mat2
            for k in M.USER_NAMES:
                M.USER_NAMES[k] = set()
        print(f"{'interfaz (offscreen)':34} 3 modulos: miembros / operaciones / cargas, VERIFICAR llena Resultados y la memoria, resultado desactualizado al editar, "
              f"Analisis FEM desactivado, asistente con {len(dlg._cache)} miniaturas; la placa base conserva sus pestañas")
    except ImportError as e:
        if "PySide6" not in str(e) and "shiboken" not in str(e):
            FAIL.append(f"nudos UI: {type(e).__name__}: {e}")
            traceback.print_exc()
        print(f"{'interfaz (offscreen)':34} omitida (sin PySide6)")
    except Exception as e:
        FAIL.append(f"nudos UI: {type(e).__name__}: {e}")
        traceback.print_exc()
    return FAIL


if __name__ == "__main__":
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    fails = run()
    print()
    if fails:
        print(f"FALLAS ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("TODAS LAS PRUEBAS DE LOS NUDOS PASARON")
    sys.stdout.flush()
    os._exit(0)         # evita el cierre normal del interprete: con ventanas Qt creadas por las pruebas puede terminar en una falla de segmentacion
