# -*- coding: utf-8 -*-
"""Pruebas del modulo de nudo (un nudo generico con miembro principal designable): flujo por operaciones, geometria 3D, verificaciones por codigo y reportes.

    python selftest_nodes.py        (tambien las corre selftest.py al final)
"""
import sys, math, copy, json, random, io, contextlib, importlib, tempfile, os, traceback
sys.path.insert(0, ".")

import numpy as np


def run():
    FAIL = []
    import matplotlib
    matplotlib.use("Agg")
    from steelconpro.model import Project, save_book, load_book
    import steelconpro.model as MD
    from steelconpro.shapes import CATALOG
    from steelconpro import materials as M
    from tools import node_presets as PRE
    from steelconpro.conn import presets as PROD, assembly as AS, module_for, modules, solve_conn
    from steelconpro.conn.specs import (CT_BASEPLATE, CT_NODE, CONN_TYPES, ATTR_OF, MODE_COL, MODE_BEAM, MODE_CHORD, LEGACY_NODES, LEGACY_END_LABELS,
                                        END_LABELS, OPERATIONS, CONNECTION_OPS, OP_TAB, OP_DANG, OP_SEAT, OP_EP_FLUSH, OP_EP_EXT, OP_WELD, OP_GUSSET,
                                        OP_GUSSET_W, OP_COPE, OP_CONT, OP_BASE, Nodo, Member, Operation, Load)
    from steelconpro.conn.fem import scene as SC
    from steelconpro.conn.checks import adapters

    print()
    print("=" * 150)
    print("MODULOS DE NUDO (flujo por operaciones, verificacion por codigo)")
    print("=" * 150)

    # ---------------------------------------------------------------- registro
    if CONN_TYPES != [CT_BASEPLATE, CT_NODE] or [c for c, _m in modules()] != [CT_NODE]:
        FAIL.append(f"nudos: registro de modulos inesperado {CONN_TYPES}")
    if any(module_for(c).VISUAL for c, _m in modules()):
        FAIL.append("nudos: los modulos ya verifican por codigo (VISUAL = False)")
    print(f"{'registro':34} un modulo de nudo (sin tipologias) + placa base; {len(OPERATIONS)} operaciones disponibles")

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
    nd.main_end = END_LABELS[1]
    cz = AS.build_nodo(nd).part("Columna").bbox()
    if abs(float(cz[1][2])) > 1e-9 or abs(float(cz[0][2]) + 60.0) > 1e-9:
        FAIL.append("nudos: columna de extremo superior debe ir de -60 a 0")
    nd.main_end = END_LABELS[2]
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

    # ---------------------------------------------------------------- designar el miembro principal (como el miembro de apoyo de IDEA): la geometria se conserva
    def box(model, name):
        b_ = model.part(name).bbox()
        return np.array(b_, float)
    nd0 = PRE.build(MODE_COL, "int2", "I", "tab")                          # Columna W14X90 vertical + V1 (+X) y V2 (−X) con placa simple
    mdl0 = AS.build_nodo(nd0)
    ndp = copy.deepcopy(nd0)
    ndp.loads = [Load("C", "V1", Vz=-10.0), Load("C", "V2", Vz=-12.0)]
    notes_ = AS.set_main(ndp, "V1")
    mdl1 = AS.build_nodo(ndp)
    exp_names = {"V1", "V2", "Columna+", "Columna−"}
    if set(ndp.names()) != exp_names or ndp.main_name != "V1" or ndp.main_shape != nd0.members[0].shape or abs(ndp.main_el) > 1e-9 or ndp.main_az % 360.0 > 1e-9:
        FAIL.append(f"principal: V1 debe quedar como principal horizontal y la columna como dos miembros: {ndp.names()} el {ndp.main_el} az {ndp.main_az}")
    if ndp.connection_of("V1") is not None or any(x.member == "V1" for x in ndp.loads) or ndp.connection_of("V2") is None or not any(x.member == "V2" for x in ndp.loads):
        FAIL.append("principal: se descartan las operaciones y cargas del miembro designado, y se conservan las de los demas")
    if not any("Se descartaron" in n_ for n_ in notes_) or mdl1.notes:
        FAIL.append(f"principal: avisos {notes_} / {mdl1.notes}")
    far0 = box(mdl0, "V1")[1][0]
    if abs(box(mdl1, "V1")[1][0] - far0) > 1e-6 or abs(box(mdl1, "V1")[0][0]) > 1e-6:
        FAIL.append(f"principal: el nuevo principal debe ir del nudo al extremo de la viga ({far0}): {box(mdl1, 'V1')[:, 0]}")
    if np.abs(box(mdl1, "V2") - box(mdl0, "V2")).max() > 1e-6:
        FAIL.append(f"principal: la otra viga no debe moverse: {box(mdl1, 'V2')} contra {box(mdl0, 'V2')}")
    cz0 = box(mdl0, "Columna")
    if abs(box(mdl1, "Columna+")[1][2] - cz0[1][2]) > 1e-6 or abs(box(mdl1, "Columna−")[0][2] - cz0[0][2]) > 1e-6:
        FAIL.append("principal: los dos tramos de la columna deben conservar sus extremos")
    sh1 = box(mdl1, "V1")
    if box(mdl1, "Columna+")[0][2] < sh1[1][2] - 1e-6 or box(mdl1, "Columna−")[1][2] > sh1[0][2] + 1e-6:
        FAIL.append("principal: los tramos de la columna deben apoyar en las alas del nuevo principal, sin entrar")
    # principal horizontal con una secundaria perpendicular: al designar la secundaria, la viga principal queda en dos miembros colineales
    nb0 = PRE.build(MODE_BEAM, "sec1", "I", "tab")
    mb0 = AS.build_nodo(nb0)
    nbp = copy.deepcopy(nb0)
    AS.set_main(nbp, "S1")
    mbp = AS.build_nodo(nbp)
    if set(nbp.names()) != {"S1", "Viga principal+", "Viga principal−"} or abs(nbp.main_az - 90.0) > 1e-6 or abs(nbp.main_el) > 1e-6:
        FAIL.append(f"principal: S1 (a 90°) debe dar un eje en +Y: {nbp.names()} az {nbp.main_az}")
    if abs(box(mbp, "Viga principal+")[1][0] - box(mb0, "Viga principal")[1][0]) > 1e-6 or abs(box(mbp, "Viga principal−")[0][0] - box(mb0, "Viga principal")[0][0]) > 1e-6:
        FAIL.append("principal: los tramos de la viga principal anterior deben conservar sus extremos")
    # un extremo: el principal termina en el nudo y solo queda un miembro
    nde = PRE.build(MODE_COL, "ext1", "I", "tab")
    AS.set_main(nde, "V1")
    if set(nde.names()) != {"V1", "Columna"} or nde.member_named("Columna").el != -90.0:
        FAIL.append(f"principal: la columna de extremo (cuerpo por debajo) pasa a ser un solo miembro hacia abajo: {nde.names()}")
    # designar uno por uno todos los miembros de cualquier nudo no pierde miembros ni nombres
    ndr = PRE.build(MODE_COL, "int4", "I", "tab")
    for k_ in range(6):
        AS.set_main(ndr, ndr.members[k_ % len(ndr.members)].name)
        if len(set(ndr.names())) != len(ndr.names()) or not AS.build_nodo(ndr).parts:
            FAIL.append(f"principal: designaciones sucesivas {ndr.names()}")
            break
    print(f"{'miembro principal designable':34} V1 pasa a principal sin mover nada (viga, columna en dos tramos, viga que sigue el eje), extremos, operaciones/cargas descartadas: OK")

    # ---------------------------------------------------------------- la placa base como operacion (sin modulo individual)
    from steelconpro.solver import solve as _solve_eng
    from steelconpro.conn import baseplate as BPm
    from steelconpro import geometry as _G
    for ex in ("PB-01_W14X90", "PB-02_HSS12_rigidizada", "PB-03_poste_circular", "COMP-1_W14X90_traccion"):
        raw_ = json.load(open(f"ejemplos/{ex}.scp", encoding="utf-8"))
        eng_ = Project.from_json(json.dumps(raw_["conexiones"][0] if "conexiones" in raw_ else raw_))               # el proyecto de placa base tal como era
        ref_ = max(_solve_eng(eng_.with_combo(i)).max_ratio for i in range(len(eng_.combo_list())))
        pj_ = load_book(f"ejemplos/{ex}.scp")[0]
        Rn_ = solve_conn(pj_)
        if abs(Rn_.max_ratio - ref_) > 1e-9 or Rn_.ok != all(_solve_eng(eng_.with_combo(i)).ok for i in range(len(eng_.combo_list()))):
            FAIL.append(f"placa base: {ex} como operacion del nudo da D/C {Rn_.max_ratio} y el motor {ref_}")
        mb_ = AS.build_model(pj_)
        pl_ = [f for t, fs, _c, _a in mb_.extra if t == "plate" for f in fs]
        zs_ = np.array([q[2] for f in pl_ for q in f])
        if not mb_.extra or any(t == "column" for t, _f, _c, _a in mb_.extra) or abs(zs_.max()) > 1e-6 or abs(zs_.min() + pj_.plate.tp) > 1e-6:
            FAIL.append(f"placa base: {ex}: la placa debe quedar bajo el extremo del principal (z de {-pj_.plate.tp:g} a 0): {zs_.min():.3f}..{zs_.max():.3f}")
    # orientacion: el perfil del nudo coincide con el que dibuja el motor de la placa base (giro del perfil respecto de la placa)
    n_or = 0
    for lab_ in ("W14X90", "W8X31", "HSS12X12X1/2", "HSS6X4X1/4", "C12X30", "L4X4X1/2", "WT6X20"):
        for rot_ in (0.0, 90.0, 30.0, -45.0):
            pe_ = Project(); pe_.section.label = lab_; pe_.section.rotation = rot_
            q_ = BPm.unify(Project.from_json(pe_.to_json()))
            nd_ = q_.node
            A_, sx_, sy_ = AS.main_frame(nd_)
            pr_ = AS.section_prisms(AS.shape_of(nd_.main_shape), (0, 0, 0), sx_, sy_, A_, 0.0, 10.0)
            E_, Ai_, bx_, by_ = BPm.end_of_member(nd_, nd_.base_op(), {}, {})
            O_, F_ = BPm.plate_transform(BPm.derive(q_), E_, Ai_, bx_, by_)
            pts_ = np.vstack([p_.corners() for p_ in pr_])
            loc_ = (F_.T @ (pts_ - O_).T).T
            base_ = loc_[np.abs((pts_ - E_) @ Ai_) < 1e-6][:, :2]
            rs_ = _G.section_rects(BPm.derive(q_))
            e_ = np.array([pt for poly in rs_ for pt in poly]) if rs_ else np.array(_G.profile_outline(BPm.derive(q_))[0])
            if not (np.allclose(e_.min(0), base_.min(0), atol=1e-5) and np.allclose(e_.max(0), base_.max(0), atol=1e-5)):
                FAIL.append(f"placa base: el perfil {lab_} con giro {rot_} no coincide con el del motor de la placa base")
            n_or += 1
    # una columna inclinada sobre placa horizontal (migracion de la inclinacion): el eje del miembro es el de la columna y el plano de la placa sigue horizontal
    pt_ = Project(); pt_.loads.tilt_x, pt_.loads.tilt_y = 10.0, 20.0
    qt_ = BPm.unify(Project.from_json(pt_.to_json()))
    Et_, Ait_, bxt_, byt_ = BPm.end_of_member(qt_.node, qt_.node.base_op(), {}, {})
    Ot_, Ft_ = BPm.plate_transform(BPm.derive(qt_), Et_, Ait_, bxt_, byt_)
    if np.abs(Ft_ - np.eye(3)).max() > 1e-9 or abs(qt_.node.main_el - 90.0) < 1.0:
        FAIL.append(f"placa base: la columna inclinada debe migrar con la placa horizontal (matriz {np.round(Ft_, 4).tolist()}) y el eje inclinado ({qt_.node.main_el})")
    def _pj(nd__):
        q__ = Project(); q__.ctype = CT_NODE; q__.element = "T-1"; q__.node = nd__
        return q__
    # la placa base en un miembro conectado (extremo libre) y en el lado + del principal; todo finito y verificable
    rb_ = random.Random(7)
    n_bp = 0
    for k_ in range(60):
        nb_ = PRE.build(MODE_COL, "int2", "I", "tab")
        who_ = rb_.choice(nb_.names())
        nb_.operations.append(Operation(kind=OP_BASE, member=who_, end=rb_.choice((-1, 1))))
        qb_ = _pj(nb_)
        qb_.plate.tp = rb_.choice((0.5, 1.0, 1.5))
        mb2_ = AS.build_model(qb_)
        if not mb2_.extra:
            FAIL.append(f"placa base: sin geometria en {who_} (end {nb_.base_op().end}): {mb2_.notes}")
            continue
        for t_, fs_, _c, _a in mb2_.extra:
            if not np.all(np.isfinite(np.array([q for f in fs_ for q in f]))):
                FAIL.append(f"placa base: coordenadas no finitas ({who_})")
        Rb2_ = solve_conn(qb_)
        if not any(c.title.startswith("[Placa base") for c in Rb2_.checks) or any(not math.isfinite(c.ratio) for c in Rb2_.checks):
            FAIL.append(f"placa base: verificaciones de la placa en {who_}")
        n_bp += 1
    # designar el miembro principal arrastra la placa base al mismo extremo libre
    ndb = PRE.build(MODE_COL, "int2", "I", "tab")
    ndb.members[0].pos = ndb.members[1].pos = 24.0
    ndb.operations.append(Operation(kind=OP_BASE, member=ndb.main_name, end=-1))
    ndb.main_end = END_LABELS[2]
    pbd = _pj(ndb)
    zmin0 = float(AS.build_model(pbd).bounds()[0][2])
    AS.set_main(ndb, "V1")
    mdb = AS.build_model(pbd)
    if ndb.base_op() is None or ndb.base_op().member not in ndb.names() or ndb.base_op().member == "V1" or abs(float(mdb.bounds()[0][2]) - (zmin0 - 24.0)) > 1e-6:
        FAIL.append(f"placa base: al designar otro principal la placa debe seguir en el extremo libre: {ndb.base_op()}, z {mdb.bounds()[0][2]} (antes {zmin0})")
    print(f"{'placa base como operacion':34} 4 archivos de placa base abren y dan el mismo D/C que el motor, perfil y giro coinciden ({n_or} casos), columna inclinada, "
          f"{n_bp} nudos con placa en miembros o en el lado +, al designar el principal la placa sigue: OK")

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
                            q = Project(); q.ctype = CT_NODE
                            q.node = nd_
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
        if not sc.dims or any(len(sc.dim_segments(v_, 5.0)[0]) == 0 for v_ in ("plan", "front", "side")):
            FAIL.append(f"nudos: el visor OpenGL debe recibir cotas en planta, frontal y lateral ({mode})")
        if float((im < 240).mean()) < 0.03 or len(sc.labels) != len(nd_.members):
            FAIL.append(f"nudos: imagen del modelo {mode} casi vacia o sin nombres de miembros")
    print(f"{'vista 3D (z-buffer propio)':34} escena e imagen de nudos con el principal vertical, horizontal e inclinado, con los nombres de los miembros: OK")

    # ---------------------------------------------------------------- verificaciones por codigo: comparacion con calculo a mano
    # (1) cartela atornillada en traccion, miembro HSS (2 planos de corte): cortante por perno = P / nb, capacidad = φ·Fnv·Ab·2
    def prj_of(ct, nd_):
        q = Project(); q.ctype = ct; q.element = "T-1"
        q.node = nd_
        return q

    def by_key(R, suffix):
        return [c for c in R.checks if c.key.endswith(suffix)]

    ng = PRE.build(MODE_CHORD, "D", "HSS", "gus_bolt")
    ng.members[0].shape = "HSS4X4X1/4"
    ng.operations[0].n_bolts, ng.operations[0].bolt_size, ng.operations[0].bolt_grade, ng.operations[0].bolt_s = 3, "3/4", "A325-N", 3.0
    ng.loads = [Load("T", "D1", N=60.0)]
    R = solve_conn(prj_of(CT_NODE, ng))
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
    R2 = solve_conn(prj_of(CT_NODE, ng))
    for k in ("g_bolt", "g_whit_y", "g_mem_y", "g_wp"):
        a, b = by_key(R, k)[0].ratio, by_key(R2, k)[0].ratio
        if abs(a - 2.0 * b) > 1e-6 * max(a, 1.0):
            FAIL.append(f"nudos: {k} debe ser proporcional a la carga: {a} contra 2 x {b}")
    # (2) alas soldadas (CJP): Pf = |My| / (d − tf) + N/2 contra 0.9·Fy·bf·tf
    nw = PRE.build(MODE_BEAM, "sec1", "I", "weld")
    nw.members[0].shape = "W16X31"
    nw.loads = [Load("M", nw.members[0].name, My=1200.0, N=10.0)]
    R = solve_conn(prj_of(CT_NODE, nw))
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
    for ex, ct in (("CN-01_columna_con_vigas", CT_NODE), ("CN-02_viga_con_secundarias", CT_NODE), ("CN-03_cordon_con_diagonales", CT_NODE), ("CN-04_columna_con_placa_base", CT_NODE)):
        bk = load_book(f"ejemplos/{ex}.scp")
        if len(bk) != 1 or bk[0].ctype != ct:
            FAIL.append(f"nudos: ejemplo {ex} no abre como {ct}")
            continue
        R = solve_conn(bk[0])
        if not R.checks or not R.ok or R.max_ratio <= 0.0:
            FAIL.append(f"nudos: ejemplo {ex}: {len(R.checks)} verificaciones, ok = {R.ok}, D/C max = {R.max_ratio}")
    print(f"{'ejemplos':34} CN-01 a CN-04 abren y cumplen")

    # ---------------------------------------------------------------- guardar y leer
    prj = []
    for mode in (MODE_COL, MODE_BEAM, MODE_CHORD):
        q = Project(); q.ctype = CT_NODE; q.element = module_for(CT_NODE).PREFIX + "-1"
        q.node = PRE.default_nodo(mode)
        nd_ = q.node
        nd_.members[0].az, nd_.members[0].shape = 33.0, "W21X44"
        nd_.operations.append(Operation(kind=OP_COPE, member=nd_.members[0].name, cope_top=1.5))
        nd_.loads.append(Load("C1", nd_.members[0].name, N=3.0, Vz=7.0, My=-25.0))
        nd_.main_end = END_LABELS[1]
        prj.append(q)
    f = os.path.join(tmp, "nudos.scp")
    save_book(f, [Project()] + prj)
    bk = load_book(f)
    if [p.ctype for p in bk] != [CT_NODE, CT_NODE, CT_NODE, CT_NODE] or bk[0].node.base_op() is None or any(a.node != b.node for a, b in zip(prj, bk[1:])):
        FAIL.append("nudos: el libro no conserva los datos de los modulos")
    n0 = bk[1].node
    if n0.members[0].az != 33.0 or not isinstance(n0.members[0], Member) or not all(isinstance(o, Operation) for o in n0.operations) \
            or not all(isinstance(x, Load) for x in n0.loads) or n0.loads[0].My != -25.0:
        FAIL.append("nudos: miembros, operaciones y cargas deben volver como sus clases")
    # archivo de la version anterior (la conexion era un campo del miembro): se migra a operaciones
    d_ = json.load(open(f, encoding="utf-8"))
    cx = d_["conexiones"][1]
    cx["ctype"] = "Nudo viga-columna"                                     # formato con tipologias: cada una con su propio campo y su «mode»
    cx["ncol"] = cx.pop("node")
    cx["ncol"].update({"mode": MODE_COL, "main_slope": 0.0, "main_end": LEGACY_END_LABELS[MODE_COL][1]})
    for k_ in ("main_az", "main_el", "main_name"):
        cx["ncol"].pop(k_, None)
    for m_ in cx["ncol"]["members"]:
        m_.pop("off2", None)
    cx["ncol"]["operations"] = []
    cx["ncol"]["loads"] = []
    cx["ncol"]["members"][0]["conn"] = "Corte — placa simple"
    f1 = os.path.join(tmp, "v_anterior.scp")
    json.dump(d_, open(f1, "w", encoding="utf-8"))
    leg1 = load_book(f1)[1]
    ops = leg1.node.operations
    if len(ops) != 1 or ops[0].kind != OP_TAB or ops[0].member != cx["ncol"]["members"][0]["name"]:
        FAIL.append(f"nudos: la conexion del miembro (version anterior) debe migrar a una operacion: {ops}")
    if leg1.ctype != CT_NODE or leg1.node.main_name != "Columna" or leg1.node.main_el != 90.0 or leg1.node.end_index != 1:
        FAIL.append(f"nudos: un nudo viga-columna de la version con tipologias debe abrir como nudo generico con el principal vertical: {leg1.ctype} {leg1.node.main_name} {leg1.node.main_el} {leg1.node.main_end}")
    # los tres tipos antiguos migran a un nudo con la misma geometria y el mismo resultado
    from dataclasses import asdict as _ad
    for _ct_old, (attr_, mode_) in LEGACY_NODES.items():
        nd_old = PRE.build(mode_, {MODE_COL: "int2", MODE_BEAM: "sec2", MODE_CHORD: "V"}[mode_], "I")
        nd_old.main_end = END_LABELS[2]
        dd_ = _ad(nd_old)
        dd_.pop("main_az"); dd_.pop("main_el"); dd_.pop("main_name")
        for m_ in dd_["members"]:
            m_.pop("off2")
        dd_.update({"mode": mode_, "main_slope": 0.0, "main_end": LEGACY_END_LABELS[mode_][2]})
        pj_ = _ad(Project())
        for k_ in ("node",):
            pj_.pop(k_)
        pj_["ctype"] = next(k for k, v in LEGACY_NODES.items() if v[1] == mode_)
        pj_[attr_] = dd_
        mig = Project.from_json(json.dumps(pj_))
        if mig.ctype != CT_NODE or mig.node != nd_old:
            FAIL.append(f"nudos: la migracion de {mode_} no reproduce el nudo: {mig.node.main_name} {mig.node.main_el} {mig.node.main_end}")
        elif mode_ != MODE_COL and mig.node.main_el != 0.0:
            FAIL.append("nudos: la viga y el cordon deben migrar con el eje horizontal")
    # libros con tipologias retiradas: se omiten y se avisa
    d_ = json.load(open(f, encoding="utf-8"))
    leg = copy.deepcopy(d_["conexiones"][1]); leg["ctype"] = "Conexion de corte — placa simple (viga a viga / viga a columna)"; leg["element"] = "VS-1"
    d_["conexiones"].append(leg)
    f2 = os.path.join(tmp, "viejo.scp")
    json.dump(d_, open(f2, "w", encoding="utf-8"))
    bk2 = load_book(f2)
    if len(bk2) != 4 or MD.LAST_SKIPPED != [("VS-1", leg["ctype"])]:
        FAIL.append(f"nudos: una conexion de tipologia retirada debe omitirse con aviso: {len(bk2)} conexiones, {MD.LAST_SKIPPED}")
    for ex in ("PB-01_W14X90", "PB-02_HSS12_rigidizada", "PB-03_poste_circular", "COMP-1_W14X90_traccion"):
        pb_ = load_book(f"ejemplos/{ex}.scp")[0]
        if pb_.ctype != CT_NODE or pb_.node.base_op() is None or pb_.node.members:
            FAIL.append(f"nudos: {ex} (placa base de la version anterior) debe abrir como conexion de nudo con la operacion de placa base")
    print(f"{'libros':34} ida y vuelta con operaciones y cargas; version anterior migra; tipologias retiradas se omiten; las placas base de la version anterior abren como nudo con la operacion de placa base")

    # ---------------------------------------------------------------- aleatorio: cualquier seccion del catalogo, angulos, posiciones y operaciones
    rnd = random.Random(20261009)
    labels = {fam: CATALOG.by_family(fam) for fam in CATALOG.families()}
    n = 0
    for k in range(300):
        nd_ = Nodo(main_name="P", main_shape=rnd.choice(labels[rnd.choice(list(labels))]), main_roll=rnd.choice((0.0, 45.0, 90.0, -30.0)),
                   main_az=rnd.uniform(0, 360), main_el=rnd.choice((90.0, 90.0, 0.0, 0.0, 15.0, -20.0, 60.0, rnd.uniform(-89, 89))), main_end=rnd.choice(END_LABELS))
        for i in range(rnd.randint(0, 6)):
            nd_.members.append(Member(name=f"M{i}", shape=rnd.choice(labels[rnd.choice(list(labels))]), az=rnd.uniform(-360, 360),
                                      el=rnd.choice((0.0, 0.0, 30.0, -45.0, 60.0, -90.0, 90.0, rnd.uniform(-89, 89))), pos=rnd.uniform(-60, 60),
                                      off=rnd.uniform(-10, 10), off2=rnd.uniform(-5, 5), L=rnd.uniform(6, 120), roll=rnd.choice((0.0, 90.0, 33.0)), gap=rnd.uniform(0, 3)))
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
            if k % 3 == 0 and nd_.members:                       # designar otro miembro como principal en cualquier nudo: no debe fallar ni dejar valores no finitos
                nd_ = copy.deepcopy(nd_)
                AS.set_main(nd_, rnd.choice(nd_.members).name)
                mm = AS.build_nodo(nd_)
                if len({x for x in nd_.names()}) != len(nd_.names()):
                    raise ValueError(f"nombres repetidos tras designar el principal: {nd_.names()}")
                for pt in mm.parts:
                    if not np.all(np.isfinite(np.vstack([p.corners() for p in pt.prisms]))):
                        raise ValueError(f"no finito tras designar el principal en {pt.name}")
            R = adapters.run(prj_of(CT_NODE, nd_), nd_)
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
    bk = load_book("ejemplos/CN-01_columna_con_vigas.scp")
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
                    Rr_ = solve_conn(prj_of(CT_NODE, nd_))
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
        q_ = Project(); q_.ctype = CT_NODE; q_.node = nf
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

    # ---------------------------------------------------------------- plantillas: llevan dentro las secciones libres que usan
    from steelconpro import templates as TPL0
    from pathlib import Path as _P
    SH.USER_DB = type(old_db)(os.path.join(tmp, "shapes_tpl.json"))
    try:
        sh_t = SH.make_general("TPL-SEC", SEC.t_box(8, 10, 0.5, 0.5))
        CATALOG.add_free(sh_t)
        nt_ = PRE.default_nodo(MODE_COL)
        nt_.main_shape = "TPL-SEC"
        qt_ = prj_of(CT_NODE, nt_)
        td_ = _P(tmp) / "tpl_engine"
        td_.mkdir(exist_ok=True)
        fp_ = TPL0.save_template(qt_, "Con seccion libre", "desc", True, td_)
        CATALOG.shapes.pop("TPL-SEC", None)
        CATALOG._reindex()
        q2_ = TPL0.load_template(fp_)
        if CATALOG.get("TPL-SEC") is None or CATALOG.get("TPL-SEC").kind != SH.GEN or q2_.node != nt_:
            FAIL.append("plantillas: deben llevar dentro la seccion libre que usan y volver igual")
        if len(TPL0.list_templates(CT_NODE, td_)) != 1 or TPL0.list_templates(CT_NODE, td_)[0]["desc"] != "desc":
            FAIL.append("plantillas: listado")
        TPL0.save_template(qt_, "Con seccion libre", "otra", True, td_)               # mismo nombre: reemplaza, no duplica
        if len(list(td_.glob("*.json"))) != 1 or TPL0.list_templates(CT_NODE, td_)[0]["desc"] != "otra":
            FAIL.append("plantillas: guardar con el mismo nombre debe reemplazar")
        try:
            TPL0.save_template(qt_, "  ", "", True, td_)
            FAIL.append("plantillas: el nombre vacio debe rechazarse")
        except ValueError:
            pass
        print(f"{'plantillas (motor)':34} guardar / listar / cargar / reemplazar, con la seccion libre dentro: OK")
    finally:
        CATALOG.shapes.pop("TPL-SEC", None)
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

    # ---------------------------------------------------------------- plantillas del usuario: guardar una conexion terminada, crear otra desde ella, renombrar y eliminar
    from steelconpro import templates as TPL
    from dataclasses import asdict as _asd
    tdir = __import__("pathlib").Path(tmp) / "plantillas"
    tdir.mkdir(exist_ok=True)
    src = prj[1]
    p_ = TPL.save_template(src, "Mi nudo tipo", "prueba", True, tdir)
    if [t["name"] for t in TPL.list_templates(src.ctype, tdir)] != ["Mi nudo tipo"]:
        FAIL.append("plantillas: no se guardo la plantilla")
    new = TPL.load_template(p_)
    if new.node != src.node:
        FAIL.append("plantillas: la conexion creada desde la plantilla debe tener los mismos miembros, operaciones y cargas")
    if TPL.list_templates(CT_BASEPLATE, tdir):
        FAIL.append("plantillas: cada modulo solo lista las suyas")
    TPL.rename_template(p_, "Mi nudo renombrado")
    if [t["name"] for t in TPL.list_templates(src.ctype, tdir)] != ["Mi nudo renombrado"]:
        FAIL.append("plantillas: renombrar")
    TPL.delete_template(p_)
    if TPL.list_templates(src.ctype, tdir):
        FAIL.append("plantillas: eliminar")
    # una placa base de la version anterior abre como nudo con la operacion de placa base, y la plantilla la devuelve identica
    pb_ = load_book("ejemplos/PB-01_W14X90.scp")[0]
    if pb_.ctype != CT_NODE or pb_.node.base_op() is None:
        FAIL.append("plantillas: una placa base antigua debe abrir como nudo con la operacion de placa base")
    pbp = TPL.save_template(pb_, "Placa tipo", "", True, tdir)
    pb2 = TPL.load_template(pbp)
    d1, d2 = _asd(pb_), _asd(pb2)
    d1["element"] = d2["element"] = ""
    if d1 != d2 or pb2.ctype != CT_NODE or pb2.node.base_op() is None:
        FAIL.append("plantillas: la placa base debe volver idéntica")
    qn = copy.deepcopy(src)
    tn = TPL.save_template(qn, "Sin cargas", "", False, tdir)
    if TPL.load_template(tn).node.loads or not qn.node.loads:
        FAIL.append("plantillas: «incluir cargas» desmarcado debe guardar sin cargas sin tocar la conexion original")
    Rb = solve_conn(pb_)
    if abs(Rb.max_ratio - 0.75) > 1e-3 or not any(c.title.startswith("[Placa base") for c in Rb.checks):
        FAIL.append(f"placa base como operacion: D/C {Rb.max_ratio:.3f} (esperado 0.750 como el modulo anterior)")
    print(f"{'plantillas y placa base':34} guardar, crear, renombrar, eliminar; placa base antigua abre como operacion con D/C = {Rb.max_ratio:.3f}")
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
