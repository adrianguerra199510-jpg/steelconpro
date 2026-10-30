# -*- coding: utf-8 -*-
"""Pruebas del motor de la aplicacion: operaciones generales (placa, pernos, soldadura, corte) con dependencias, resultados por operacion,
API JSON, espacio de trabajo de proyectos y servidor local.

    python selftest_ops.py        (tambien las corre selftest.py al final)
"""
import sys, os, json, copy, tempfile, threading, urllib.request, urllib.error, traceback
sys.path.insert(0, ".")


def run():
    FAIL = []
    from steelconpro import api
    from steelconpro.conn import specs as SP, ops as OPS
    from steelconpro.model import load_book

    print()
    print("=" * 150)
    print("OPERACIONES GENERALES, API Y SERVIDOR")
    print("=" * 150)

    def fail(msg):
        FAIL.append(msg)

    try:
        K = api.constants()["op"]
        book = api.book_new()
        con = book["connections"][0]
        nd = con["node"]
        if nd["members"] or nd["operations"]:
            fail("ops: una conexion nueva debe estar en blanco")

        # ---- placa sobre el principal, rigidizador sobre esa placa (dependencia) y soldadura entre ellas
        r = api.add_operation({"connection": con, "kind": K["PLATE"]})
        con = r["connection"]; p1 = con["node"]["operations"][r["index"]]
        if p1["name"] != "P1" or p1["parent"] != con["node"]["main_name"] or not p1["face"]:
            fail(f"ops: la placa nueva debe unirse al principal ({p1['name']}, {p1['parent']}, {p1['face']})")
        r = api.add_operation({"connection": con, "kind": K["PLATE"], "params": {"parent": "P1", "face": "Cara +", "role": "Rigidizador", "orient": SP.PLATE_ORIENTS[1]}})
        con = r["connection"]; p2 = con["node"]["operations"][r["index"]]
        if p2["parent"] != "P1" or p2["name"] != "P2":
            fail("ops: la placa debe poder apoyarse en otra placa")
        r = api.add_operation({"connection": con, "kind": K["FILLET"], "params": {"targets": ["P1"]}})
        con = r["connection"]
        r = api.add_operation({"connection": con, "kind": K["BOLTS"], "params": {"parent": "P1", "face": "Cara +", "pl_s": 6.0, "targets": [con["node"]["main_name"]]}})
        con = r["connection"]
        if any(o["member"] for o in con["node"]["operations"]):
            fail("ops: las operaciones generales no deben quedar ligadas a un miembro por defecto")
        el = api.element_info({"connection": con})["elements"]
        names = [e["name"] for e in el]
        if "P1" not in names or "P2" not in names or el[0]["main"] is not True:
            fail(f"ops: element_info no lista las placas ({names})")
        m = api.mesh({"connection": con})
        kinds = {p["name"] for p in m["parts"]}
        if "P1" not in kinds or "P2" not in kinds or not m["bounds"]:
            fail(f"ops: la malla 3D no trae las placas ({sorted(kinds)})")
        v = api.verify({"connection": con})
        groups = {c["group"] for c in v["checks"] if c["group"]}
        if not any(g.startswith("1.") for g in groups) or not any(g.startswith("2.") for g in groups):
            fail(f"ops: los resultados deben agruparse por operacion ({sorted(groups)})")
        print(f"{'operaciones generales':34} placa → rigidizador → soldadura → pernos: {len(m['parts'])} piezas, {len(v['checks'])} verificaciones en {len(groups)} operaciones   D/C max {v['max_ratio']:.3f}")

        # ---- el filete minimo depende de la parte mas delgada (AISC Tabla J2.4)
        if OPS.min_fillet(0.375) != 0.1875 or OPS.min_fillet(0.2) != 0.125 or OPS.min_fillet(0.9) != 0.3125:
            fail("ops: cateto minimo del filete (AISC J2.4)")

        # ---- dependencias: borrar P1 quita P2 (y lo que depende de P1)
        dep = api.dependents({"connection": con, "name": "P1"})["operations"]
        d = api.delete_operation({"connection": con, "index": 0})
        left = [o["name"] or o["kind"] for o in d["connection"]["node"]["operations"]]
        if len(dep) < 2 or any(o["name"] in ("P1", "P2") for o in d["connection"]["node"]["operations"]):
            fail(f"ops: el borrado en cascada no quito las placas dependientes ({left}, dependientes {dep})")
        print(f"{'dependencias':34} borrar P1 quita {len(d['removed'])} operaciones (P1, P2 y las que dependen de ellas); quedan {len(left)}")

        # ---- miembro conectado + corte de elementos
        nm = api.new_member({"connection": con})["member"]
        con["node"]["members"].append(nm)
        r = api.add_operation({"connection": con, "kind": K["CUT"], "params": {"targets": [nm["name"]], "cut_at": "Inicio"}})
        con = r["connection"]
        m2 = api.mesh({"connection": con})
        if not m2["parts"]:
            fail("ops: el corte deja el modelo vacio")
        # ---- placa base en la misma conexion
        r = api.add_operation({"connection": con, "kind": K["BASE"]})
        con = r["connection"]
        v2 = api.verify({"connection": con})
        if not any("Placa base" in (c["group"] or "") for c in v2["checks"]):
            fail("ops: los resultados de la placa base deben aparecer como una operacion mas")
        # ---- nombre repetido / renombrado desde la interfaz: designar principal
        dm = api.designate_main({"connection": con, "name": nm["name"]})
        if dm["connection"]["node"]["main_name"] != nm["name"]:
            fail("ops: designar el miembro principal")
        print(f"{'corte, placa base, principal':34} corte de {nm['name']}, placa base como operacion ({len(v2['checks'])} verificaciones), designar principal OK")

        # ---- analisis nodal: equilibrio del nudo y cargas de la placa base
        import numpy as np
        cn = copy.deepcopy(con)
        cn["section"]["rotation"] = 0.0
        ndn = cn["node"]
        ndn["main_name"], ndn["main_el"], ndn["main_az"], ndn["main_roll"] = "C1", 90.0, 0.0, 0.0
        ndn["members"] = [dict(nm, name="V1", az=0.0, el=0.0, pos=96.0, off=0.0, off2=0.0, roll=0.0)]
        ndn["operations"] = [o for o in ndn["operations"] if o["kind"] == K["BASE"]]
        ndn["operations"][0].update(member="C1", end=-1)
        ndn["loads"] = [{"case": "A", "member": "V1", "N": 5.0, "Vy": 0.0, "Vz": -10.0, "T": 0.0, "My": 0.0, "Mz": 0.0, "side": 0}]
        a = api.nodal({"connection": cn})
        c0 = a["cases"][0]
        tot = np.sum([r["F"] for r in c0["rows"]], axis=0)
        totm = np.sum([r["M"] for r in c0["rows"]], axis=0)
        if np.abs(tot).max() > 1e-9 or np.abs(totm).max() > 1e-9:
            fail(f"nodal: el nudo no queda en equilibrio (ΣF = {tot}, ΣM = {totm})")
        b = c0["base"]
        # viga a 96 in sobre el nudo con 5 kip de traccion horizontal y 10 kip hacia abajo; el principal termina en el nudo (base en el nudo si no tiene largo inferior)
        lneg = ndn["main_len_neg"] if ndn["main_end"].startswith("Continuo") else 0.0
        if abs(b["Pu"] - 10.0) > 1e-6 or abs(b["Vuy"] - 5.0) > 1e-6 or abs(abs(b["Mux"]) - 5.0 * (96.0 + lneg)) > 1e-6:
            fail(f"nodal: cargas de la placa base {b} (esperado Pu = 10, |Mux| = {5.0 * (96.0 + lneg)}, Vuy = 5)")
        ndn["loads"].append({"case": "B", "member": "@nudo", "N": 0.0, "Vy": 0.0, "Vz": -7.0, "T": 0.0, "My": 0.0, "Mz": 0.0, "side": 0})
        a2 = api.nodal({"connection": cn})
        if abs(a2["cases"][1]["base"]["Pu"] - 7.0) > 1e-6:
            fail(f"nodal: carga externa en el nudo ({a2['cases'][1]['base']})")
        v3 = api.verify({"connection": cn})
        if not any("Placa base" in (c["group"] or "") for c in v3["checks"]) or len(v3["combos"]) < 2:
            fail("nodal: la placa base debe verificar los casos del nudo")
        print(f"{'analisis nodal':34} equilibrio ΣF = ΣM = 0, carga externa, y cargas de la placa base desde el nudo (Pu {b['Pu']:.1f}, Mux {b['Mux']:.0f}, Vuy {b['Vuy']:.1f}): OK")

        # ---- placa simple: filas × columnas, tamaño de la placa y corte automatico de la secundaria
        from steelconpro.conn import assembly as AS_
        ex = api.book_load({"path": os.path.join("ejemplos", "CN-02_viga_con_secundarias.scp")})["connections"][0]
        o_tab = next(o for o in ex["node"]["operations"] if o["kind"] == K["TAB"])
        o_tab.update(n_cols=2, n_bolts=3, tab_H=10.0, tab_W=7.0)
        mt = api.mesh({"connection": ex})
        nb = len([1 for p_ in mt["parts"] if p_["name"] == "Pernos"])
        vt = api.verify({"connection": ex})
        grp = [c for c in vt["checks"] if c["group"].startswith("1.")]
        if not any("grupo elastico" in c["title"] for c in grp) or not nb:
            fail("placa simple: con dos columnas de pernos debe verificar el grupo elastico")
        from steelconpro.api import _prj
        pe = _prj(ex)
        mem = next(m for m in pe.node.members if m.name == o_tab["member"])
        pl_ = [p_ for p_ in AS_.build_model(pe).parts if p_.name.startswith("Placa S")]
        mdl_ = AS_.build_model(pe)
        if len(mdl_.bolts) < 6 or not any(w.A.startswith("Placa S2") or w.A.startswith("Placa " + mem.name) for w in mdl_.welds):
            fail("placa simple: faltan los pernos (3×2) o las soldaduras sobre la cara del soporte")
        ac = AS_.auto_cope_for(pe.node, next(m for m in pe.node.members if m.name == "S3"))
        if ac is None or ac[0] <= 0 or ac[2] <= 0:
            fail(f"corte automatico: la viga S3 entra en la viga principal y debe cortarse ({ac})")
        print(f"{'placa simple y corte automatico':34} 3×2 pernos, placa 10×7 in con filetes en la cara del soporte, grupo elastico verificado, corte automatico de S3 {tuple(round(x, 2) for x in ac)}: OK")

        # ---- nucleo geometrico general: formas de placa, aberturas, angulo, huecos, recorte y soldadura de contorno
        c2 = api.book_new()["connections"][0]
        mm = api.new_member({"connection": c2})["member"]; c2["node"]["members"].append(mm)
        def add2(kind, params):
            nonlocal c2
            r = api.add_operation({"connection": c2, "kind": K[kind], "params": params}); c2 = r["connection"]; return c2["node"]["operations"][r["index"]]
        for shp in SP.PLATE_SHAPES:
            add2("PLATE", {"shape": shp})
        add2("ANGLE", {})
        add2("HOLE", {"parent": "P1", "rows": 2, "cols": 2})
        add2("HOLE", {"parent": "P2", "hole_shape": SP.HOLE_SHAPES[1]})
        add2("PLATE", {"parent": mm["name"], "face": SP.FACES_END[1], "pl_L": 8, "pl_W": 8, "shape": SP.PLATE_SHAPES[3], "opening": SP.OPENINGS[3], "op_member": mm["name"]})
        pn = c2["node"]["operations"][-1]["name"]
        add2("FILLET", {"weld_mode": SP.WELD_MODES[1], "targets": [mm["name"]], "parent": pn, "face": "Cara −"})
        add2("TRIM", {"targets": [mm["name"]], "parent": c2["node"]["main_name"], "face": SP.FACES_I[0], "trim_gap": 0.5})
        m2 = api.mesh({"connection": c2})
        names2 = {p["name"] for p in m2["parts"]}
        if m2.get("notes") or not {"P1", "P7", "A1", pn}.issubset(names2) or not any(n.startswith(mm["name"] + "-S") for n in names2):
            fail(f"nucleo: modelo con formas/angulo/huecos/recorte/contorno ({m2.get('notes')}, {sorted(names2)[:12]})")
        if not api.plate_edges({"connection": c2, "index": 0})["edges"] or len(api.verify({"connection": c2})["checks"]) < 20:
            fail("nucleo: bordes de placa o verificaciones")
        print(f"{'nucleo geometrico':34} 7 formas de placa, abertura que rodea al miembro, ángulo, huecos/ranuras, recorte y soldadura de contorno: {len(m2['parts'])} piezas: OK")

        # ---- conexion editable: la placa extrema se convierte en piezas con los mismos pernos; malla del FEM del nudo
        ex1 = api._dump(__import__("steelconpro.model", fromlist=["load_book"]).load_book("ejemplos/CN-01_columna_con_vigas.scp")[0])
        from steelconpro.conn import assembly as AS0
        before = OPS._bolt_positions(AS0.build_model(api._prj(ex1)), "V1-B")
        cv = api.convert_connection({"connection": ex1, "member": "V1"})
        after = OPS._bolt_positions(AS0.build_model(api._prj(cv["connection"])), "B")
        if before != after or not before or any(o["kind"] == SP.OP_EP_EXT for o in cv["connection"]["node"]["operations"] if o["member"] == "V1"):
            fail(f"editable: la conversion de la placa extrema no conserva los pernos ({len(before)} vs {len(after)})")
        import time
        mj = api.fem_mesh_start({"connection": ex1, "case": 0})["job"]
        t0 = time.time()
        while not api.job_status({"job": mj})["done"] and time.time() - t0 < 300:
            time.sleep(1)
        js = api.job_status({"job": mj})
        ms = api.fem_mesh_scene({"connection": ex1, "case": 0}) if js["state"] == "done" else None
        if ms is None or ms["mesh"]["elements"] < 1000:
            fail(f"fem: no se genero la malla ({js.get('state')}, {js.get('error', '')[:200]})")
        print(f"{'conexion editable y malla FEM':34} placa extrema -> piezas con los mismos {len(before)} pernos; malla {ms['mesh']['elements'] if ms else 0:,} elementos: OK")

        # ---- archivos
        tmp = tempfile.mkdtemp(prefix="scp_ops_")
        f = os.path.join(tmp, "p.scp")
        api.book_save({"path": f, "connections": [con]})
        back = api.book_load({"path": f})["connections"][0]
        if [o["kind"] for o in back["node"]["operations"]] != [o["kind"] for o in con["node"]["operations"]]:
            fail("ops: el archivo no conserva las operaciones")
        for ex in ("CN-01_columna_con_vigas", "CN-04_columna_con_placa_base", "CN-05_viga_con_placas_trapezoidales", "CN-06_diagonal_con_recorte_y_angulo", "PB-01_W14X90"):
            b = load_book(os.path.join("ejemplos", ex + ".scp"))
            vv = api.verify({"connection": api.book_load({"path": os.path.join("ejemplos", ex + ".scp")})["connections"][0]})
            if not vv["checks"]:
                fail(f"ops: el ejemplo {ex} no produce verificaciones")
        th = api.thumbnail({"connection": con, "w": 200, "h": 140})
        if not th["png"]:
            fail("ops: miniatura vacia")

        # ---- espacio de trabajo
        root = os.path.join(tmp, "ws")
        os.makedirs(root)
        c1 = api.ws_create_project({"root": root, "name": "Nave 1", "folder": ""})
        api.ws_create_folder({"root": root, "name": "Naves"})
        mv = api.ws_move({"root": root, "path": c1["rel"], "folder": "Naves"})
        api.ws_favorite({"root": root, "path": mv["path"]})
        api.ws_touch({"root": root, "path": mv["path"]})
        lst = api.ws_list({"root": root, "thumbs": False})
        pj = lst["projects"][0]
        if len(lst["projects"]) != 1 or pj["folder"] != "Naves" or not pj["favorite"] or lst["recent"] != [mv["path"]] or not any(x["name"] == "Naves" for x in lst["folders"]):
            fail(f"workspace: listado inesperado {lst['projects']}")
        dup = api.ws_duplicate({"root": root, "path": mv["path"]})
        rn = api.ws_rename({"root": root, "path": dup["path"], "name": "Copia"})
        api.ws_delete({"root": root, "path": rn["path"]})
        try:
            api.ws_delete({"root": root, "path": "../fuera"})
            fail("workspace: debe rechazar rutas fuera de la carpeta de trabajo")
        except api.ApiError:
            pass
        imp = api.ws_import({"root": root, "source": os.path.join("ejemplos", "PB-01_W14X90.scp")})
        if not os.path.exists(os.path.join(root, imp["path"])):
            fail("workspace: importar un proyecto")
        print(f"{'espacio de trabajo':34} crear, carpeta, mover, favorito, reciente, duplicar, renombrar, eliminar, importar, ruta fuera rechazada: OK")

        # ---- servidor local
        from steelconpro import server
        srv, info = server.serve(0, "tok123", quiet=True)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        base = f"http://127.0.0.1:{info['port']}"

        def post(fn, body, token="tok123"):
            rq = urllib.request.Request(f"{base}/api/{fn}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-SCP-Token": token})
            with urllib.request.urlopen(rq, timeout=60) as rs:
                return json.loads(rs.read())
        if post("app_info", {})["name"] != "SteelConPro":
            fail("servidor: app_info")
        try:
            post("app_info", {}, token="malo")
            fail("servidor: debe rechazar un token invalido")
        except urllib.error.HTTPError as e:
            if e.code != 403:
                fail(f"servidor: codigo {e.code} con token invalido")
        try:
            post("section_info", {"label": "NO-EXISTE"})
            fail("servidor: un perfil desconocido debe dar error")
        except urllib.error.HTTPError as e:
            if e.code != 400 or "desconocido" not in json.loads(e.read())["error"]:
                fail("servidor: error de perfil desconocido")
        rv = post("verify", {"connection": con})
        if rv["max_ratio"] != v2["max_ratio"]:
            fail("servidor: verify por HTTP no coincide con la llamada directa")
        srv.shutdown()
        print(f"{'servidor local':34} token, errores y calculo por HTTP: OK")

        # ---- bibliotecas
        sec = api.section_build({"template": next(iter(__import__("steelconpro.sections", fromlist=["TEMPLATES"]).TEMPLATES))})
        if not sec["props"] or sec["props"]["A"] <= 0:
            fail("secciones: plantilla del Section Designer")
        mats = api.materials_get()
        if not mats["all"]["steel"]:
            fail("materiales: lista vacia")
    except Exception as e:                                  # noqa: BLE001
        fail(f"ops/api: {type(e).__name__}: {e}")
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
    print("TODAS LAS PRUEBAS DE OPERACIONES Y API PASARON")
