# -*- coding: utf-8 -*-
"""Pruebas de los modulos de nudo (viga-columna, viga a viga, crucetas): solo geometria y vista 3D; no se corre ningun calculo ni analisis.

    python selftest_nodes.py        (tambien las corre selftest.py al final)
"""
import sys, math, copy, json, random, io, contextlib, importlib, tempfile, os, traceback
sys.path.insert(0, ".")

import numpy as np


def run():
    FAIL = []
    from steelconpro.model import Project, save_book, load_book, LegacyConnection
    import steelconpro.model as MD
    from steelconpro.shapes import CATALOG
    from steelconpro.conn import presets as PRE, assembly as AS, module_for, modules
    from steelconpro.conn.specs import (CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS, CONN_TYPES, MODE_OF, ATTR_OF, MODE_COL, MODE_BEAM, MODE_CHORD,
                                        END_LABELS, CONNECT_KINDS, CK_BLANK, CK_TAB, CK_DANG, CK_SEAT, CK_EP_FLUSH, CK_EP_EXT, CK_WELD, CK_GUSSET,
                                        CK_GUSSET_W, Nodo, Member)
    from steelconpro.conn.fem import scene as SC

    print()
    print("=" * 150)
    print("MODULOS DE NUDO (solo geometria)")
    print("=" * 150)

    # ---------------------------------------------------------------- registro
    if CONN_TYPES != [CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS] or [c for c, _m in modules()] != [CT_NODE, CT_B2B, CT_TRUSS]:
        FAIL.append(f"nudos: registro de modulos inesperado {CONN_TYPES}")
    if any(not module_for(c).VISUAL for c, _m in modules()):
        FAIL.append("nudos: los modulos deben ser solo geometria (VISUAL)")
    print(f"{'registro':34} {len(modules())} modulos de nudo + placa base; ninguno tiene analisis")

    # ---------------------------------------------------------------- salida de un rayo por la seccion (a mano)
    w = CATALOG.get("W14X90")
    ext = AS.outer_extent(w)
    d, bf, tf, tw = w.d, w.bf, w.tf, w.tw
    checks = [("alma (+x)", AS.ray_exit(ext, (0, 0), (1, 0)), tw / 2.0),
              ("ala (+y)", AS.ray_exit(ext, (0, 0), (0, 1)), d / 2.0),
              ("45°", AS.ray_exit(ext, (0, 0), (math.cos(math.radians(45)), math.sin(math.radians(45)))), (d / 2.0) / math.sin(math.radians(45))),
              ("tubo redondo", AS.ray_exit(AS.outer_extent(CATALOG.get("HSS12.750X0.500")), (0, 0), (0.3, 0.7)),
               CATALOG.get("HSS12.750X0.500").d / 2.0 / math.hypot(0.3, 0.7)),
              ("HSS rect.", AS.ray_exit(AS.outer_extent(CATALOG.get("HSS12X12X1/2")), (0, 0), (1, 0)), 6.0)]
    for nm, got, want in checks:
        if got is None or abs(got - want) > 1e-6:
            FAIL.append(f"nudos: salida del rayo ({nm}): {got} contra {want}")
    # tubo redondo: ray (0.3, 0.7) no unitario -> s = R/|d|
    print(f"{'rayo contra la seccion':34} alma {checks[0][1]:.3f} = tw/2, ala {checks[1][1]:.3f} = d/2, 45° {checks[2][1]:.3f}, tubos: OK")

    # ---------------------------------------------------------------- posiciones a mano: columna W14X90 y viga W16X31 por el ala (az = 0)
    nd = PRE.build(MODE_COL, "int1", "I", "tab")
    nd.members[0].gap = 0.5
    mdl = AS.build_nodo(nd)
    v = mdl.part("V1")
    x0 = float(v.bbox()[0][0])
    if abs(x0 - (d / 2.0 + 0.5)) > 1e-6:
        FAIL.append(f"nudos: la viga debe empezar en d/2 + retranqueo = {d / 2 + 0.5:.3f}; empieza en {x0:.4f}")
    col = mdl.part("Columna")
    zmin, zmax = float(col.bbox()[0][2]), float(col.bbox()[1][2])
    if abs(zmin + 60.0) > 1e-9 or abs(zmax - 60.0) > 1e-9:
        FAIL.append(f"nudos: columna intermedia debe ir de -60 a 60: {zmin}..{zmax}")
    n_tab_bolts = len([b for b in mdl.bolts if b.tag.startswith("V1")])
    if n_tab_bolts != 3 or mdl.part("Placa V1") is None:
        FAIL.append(f"nudos: placa simple con 3 pernos: {n_tab_bolts} pernos")
    nd.main_end = END_LABELS[MODE_COL][1]
    cz = AS.build_nodo(nd).part("Columna").bbox()
    if abs(float(cz[1][2])) > 1e-9 or abs(float(cz[0][2]) + 60.0) > 1e-9:
        FAIL.append("nudos: columna de extremo superior debe ir de -60 a 0")
    nd.main_end = END_LABELS[MODE_COL][2]
    cz = AS.build_nodo(nd).part("Columna").bbox()
    if abs(float(cz[0][2])) > 1e-9 or abs(float(cz[1][2]) - 60.0) > 1e-9:
        FAIL.append("nudos: columna de extremo inferior debe ir de 0 a 60")
    # placa extrema a ras: la viga empieza donde termina la placa (d/2 + tp)
    nd2 = PRE.build(MODE_COL, "int1", "I", "ep_flush")
    m2 = AS.build_nodo(nd2)
    tp = nd2.members[0].plate_t
    pe = m2.part("Placa extrema V1")
    tpl = max(tp, 0.5)
    if pe is None or abs(float(pe.bbox()[0][0]) - d / 2.0) > 1e-6 or abs(float(pe.bbox()[1][0]) - (d / 2.0 + tpl)) > 1e-6 \
            or abs(float(m2.part("V1").bbox()[0][0]) - (d / 2.0 + tpl)) > 1e-6:
        FAIL.append("nudos: placa extrema contra la cara de la columna y viga a continuacion")
    print(f"{'posiciones (columna W14X90)':34} viga en d/2 + retranqueo = {x0:.3f} in, columna intermedia / de extremo, placa extrema contra la cara: OK")

    # ---------------------------------------------------------------- viga a viga: la secundaria llega a la cara del alma de la principal
    nb = PRE.build(MODE_BEAM, "sec1", "I", "tab")
    mb = AS.build_nodo(nb)
    wm = CATALOG.get(nb.main_shape)
    y0 = float(mb.part("S1").bbox()[0][1])
    if abs(y0 - (wm.tw / 2.0 + nb.members[0].gap)) > 1e-6:
        FAIL.append(f"nudos: la secundaria debe empezar en tw/2 + retranqueo = {wm.tw / 2 + 0.5:.4f}: {y0:.4f}")
    nb.members[0].az = 0.0                     # paralela al miembro principal: no lo toca
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
    nt.members[1].az = 90.0                                      # fuera del plano: otra cartela
    if len([p for p in AS.build_nodo(nt).parts if p.kind == "gusset"]) != 2:
        FAIL.append("nudos: dos diagonales en planos distintos llevan dos cartelas")
    print(f"{'crucetas':34} V, N, X, D: una cartela por plano; atornillada con pernos, soldada sin pernos: OK")

    # ---------------------------------------------------------------- todos los presets, secciones y diseños arman un modelo valido
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
                        if ck == CK_BLANK and (mm.bolts or [p for p in mm.parts if p.kind in ("plate", "angle", "gusset", "stiff")]):
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: en blanco no debe llevar herrajes")
                        if ck != CK_BLANK and not mm.bolts and ck != CK_GUSSET_W and not any(m.conn == CK_WELD for m in nd_.members):
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: la conexion no genero pernos")
                        if any("no toca" in n for n in mm.notes):
                            FAIL.append(f"nudos: {mode}/{gk}/{sk}/{dk}: {mm.notes[0]}")
    print(f"{'presets':34} {n_models} combinaciones de geometria, seccion y diseño armadas sin errores ni miembros sueltos")

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

    # ---------------------------------------------------------------- guardar y leer
    prj = []
    for ct in (CT_NODE, CT_B2B, CT_TRUSS):
        q = Project(); q.ctype = ct; q.element = module_for(ct).PREFIX + "-1"
        a = ATTR_OF[ct]
        nd_ = getattr(q, a)
        nd_.members[0].az, nd_.members[0].shape, nd_.members[0].conn = 33.0, "W21X44", CK_DANG
        nd_.main_end = END_LABELS[nd_.mode][1]
        prj.append(q)
    f = os.path.join(tmp, "nudos.scp")
    save_book(f, [Project()] + prj)
    bk = load_book(f)
    if [p.ctype for p in bk] != [CT_BASEPLATE, CT_NODE, CT_B2B, CT_TRUSS] or any(getattr(a, ATTR_OF[a.ctype]) != getattr(b, ATTR_OF[a.ctype]) for a, b in zip(prj, bk[1:])):
        FAIL.append("nudos: el libro no conserva los datos de los modulos")
    if bk[1].ncol.members[0].az != 33.0 or not isinstance(bk[1].ncol.members[0], Member):
        FAIL.append("nudos: los miembros deben volver como Member")
    # libros con tipologias retiradas: se omiten y se avisa
    d = json.load(open(f, encoding="utf-8"))
    leg = copy.deepcopy(d["conexiones"][1]); leg["ctype"] = "Conexion de corte — placa simple (viga a viga / viga a columna)"; leg["element"] = "VS-1"
    d["conexiones"].append(leg)
    f2 = os.path.join(tmp, "viejo.scp")
    json.dump(d, open(f2, "w", encoding="utf-8"))
    bk2 = load_book(f2)
    if len(bk2) != 4 or MD.LAST_SKIPPED != [("VS-1", leg["ctype"])]:
        FAIL.append(f"nudos: una conexion de tipologia retirada debe omitirse con aviso: {len(bk2)} conexiones, {MD.LAST_SKIPPED}")
    for ex in ("PB-01_W14X90", "COMP-1_W14X90_traccion"):
        if load_book(f"ejemplos/{ex}.scp")[0].ctype != CT_BASEPLATE:
            FAIL.append(f"nudos: {ex} debe abrir como placa base")
    print(f"{'libros':34} ida y vuelta de los tres modulos; tipologias retiradas se omiten con aviso; ejemplos de placa base abren igual")

    # ---------------------------------------------------------------- aleatorio: cualquier seccion del catalogo, angulos y posiciones
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
                                      off=rnd.uniform(-10, 10), L=rnd.uniform(6, 120), roll=rnd.choice((0.0, 90.0, 33.0)), conn=rnd.choice(CONNECT_KINDS),
                                      gap=rnd.uniform(0, 3), n_bolts=rnd.randint(1, 8), bolt_s=rnd.choice((1.5, 3.0, 4.0)),
                                      plate_t=rnd.choice((0.125, 0.375, 1.0)), ep_ext=rnd.uniform(1, 6), cont=rnd.random() < 0.5))
        try:
            mm = AS.build_nodo(nd_)
            for pt in mm.parts:
                P = np.vstack([p.corners() for p in pt.prisms])
                if not np.all(np.isfinite(P)):
                    raise ValueError(f"no finito en {pt.name}")
            for b in mm.bolts:
                if not np.all(np.isfinite(b.p)):
                    raise ValueError("perno no finito")
            if k % 25 == 0:
                SC.scene_model(mm, loads=False, tags=True)
            n += 1
        except Exception as e:
            FAIL.append(f"nudos aleatorio {k}: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
    print(f"{'aleatorio':34} {n} nudos con secciones, angulos, posiciones y conexiones al azar: sin excepciones ni coordenadas no finitas")

    # ---------------------------------------------------------------- lote (run.py): imagenes del modelo, sin calculo
    _run = importlib.import_module("run")
    buf = io.StringIO()
    out = os.path.join(tmp, "imgs")
    with contextlib.redirect_stdout(buf):
        rc = _run.batch_node(prj[0], ["x", "--3d", out, "--pdf", "a.pdf"])
    if rc != 0 or not all(os.path.exists(os.path.join(out, nm)) for nm in ("modelo3d_iso.png", "modelo3d_planta.png", "esquema.png")) or "solo geometria" not in buf.getvalue():
        FAIL.append(f"nudos: modo por lotes: {buf.getvalue()}")
    print(f"{'modo por lotes (run.py)':34} imagenes del modelo y esquema; sin memoria de calculo (avisado)")

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
            if tabs_in != ["Proyecto", mod.TAB] or tabs_out.get("Analisis FEM") is not False or tabs_out.get("Resultados") is not False \
                    or tabs_out.get("Modelo 3D") is not True or win.btn3d.isEnabled():
                FAIL.append(f"nudos UI {ct}: pestañas {tabs_in} / {tabs_out}, CALCULAR habilitado = {win.btn3d.isEnabled()}")
            nd_ = getattr(win.prj, ATTR_OF[ct])
            if len(nd_.members) != len(PRE.build(MODE_OF[ct], pre[0], pre[1], pre[2]).members):
                FAIL.append(f"nudos UI {ct}: el asistente no aplico la geometria")
            form = win.fnamed[mod.TAB]
            m0 = nd_.members[0]
            form.mf.w("m.az").setValue(30.0)
            form.m_pick.set_label("W21X44"); form.m_pick.changed.emit()
            form.mf.w("m.conn").setCurrentText(CK_DANG)
            if win.prj and (m0.az != 30.0 or m0.shape != "W21X44" or m0.conn != CK_DANG):
                FAIL.append(f"nudos UI {ct}: la edicion del miembro no se guardo: {m0.az} {m0.shape} {m0.conn}")
            n0 = len(nd_.members)
            form._add(); form._dup(); form._del()
            if len(nd_.members) != n0 + 1:
                FAIL.append(f"nudos UI {ct}: agregar/duplicar/quitar: {n0} -> {len(nd_.members)}")
            form.cb_all.setCurrentText(CK_SEAT); form._apply_all()
            if {m.conn for m in nd_.members} != {CK_SEAT}:
                FAIL.append(f"nudos UI {ct}: aplicar la conexion a todos")
            form.w(f"{ATTR_OF[ct]}.main_end").setCurrentIndex(1)
            if nd_.end_index != 1:
                FAIL.append(f"nudos UI {ct}: extremo del miembro principal")
            win.recalc()
            app.processEvents()
            if win.statusBar() is None or "desactivado" not in win.statusBar().currentMessage():
                FAIL.append(f"nudos UI {ct}: debe avisar que el analisis esta desactivado: '{win.statusBar().currentMessage()}'")
            win.run_3d()                                    # no debe correr nada
            if win.worker is not None and win.worker.isRunning():
                FAIL.append(f"nudos UI {ct}: CALCULAR no debe lanzar ningun analisis")
        # volver a la placa base: reaparecen sus pestañas y se habilitan las de resultados
        win._switch(0)
        app.processEvents()
        if not (win.tabs_out.isTabEnabled(win.tabs_out.indexOf(win.tab_fem)) and win.btn3d.isEnabled()):
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
        print(f"{'interfaz (offscreen)':34} 3 modulos: pestañas Analisis FEM y Resultados desactivadas, CALCULAR desactivado, edicion de miembros, asistente con "
              f"{len(dlg._cache)} miniaturas; la placa base conserva sus pestañas")
    except ImportError:
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
