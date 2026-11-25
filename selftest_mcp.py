# -*- coding: utf-8 -*-
"""Pruebas del servidor MCP (Claude Desktop): arranca `run.py --mcp` como proceso hijo por stdio, igual que Claude Desktop, y recorre con un
cliente MCP real el flujo completo: crear una conexión, agregar miembro y operación, cargas, geometría, calcular (fórmulas + modelo de placas),
esperar el análisis, resultados por categoría y componente, imagen, informe, y los errores de validación.  También la instalación en la
configuración de Claude Desktop.

    python3 selftest_mcp.py            (con el análisis de placas)
    python3 selftest_mcp.py --rapido   (sin esperar el análisis de placas)
"""
import asyncio
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
RAPIDO = "--rapido" in sys.argv
FAILS = []
DC = {}


def check(cond, msg):
    print(("OK    " if cond else "FALLA ") + msg)
    if not cond:
        FAILS.append(msg)


def data(res):
    """Contenido de una respuesta de herramienta como dict (o el tipo de contenido si es una imagen)."""
    for c in res.content:
        if c.type == "text":
            try:
                return json.loads(c.text)
            except json.JSONDecodeError:
                return {"_texto": c.text}
        if c.type == "image":
            return {"_imagen": c.mimeType, "_bytes": len(c.data)}
    return {}


async def flujo(ws):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=[os.path.join(ROOT, "run.py"), "--mcp", "--root", ws], env={**os.environ, "MPLBACKEND": "Agg"})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as cs:
            init = await cs.initialize()
            check(init.serverInfo.name == "SteelConPro" and "in, kip" in (init.instructions or ""), "el servidor se presenta con sus instrucciones (unidades y flujo)")
            tools = {t.name for t in (await cs.list_tools()).tools}
            need = {"nueva_conexion", "agregar_miembro", "agregar_operacion", "definir_cargas", "calcular", "estado_analisis", "resultados", "imagen", "generar_informe",
                    "operaciones_disponibles", "buscar_perfil", "revisar_geometria", "configurar_placa_base", "abrir_proyecto", "listar_proyectos"}
            check(need <= tools, f"herramientas expuestas ({len(tools)}): faltan {sorted(need - tools)}")
            call = lambda n, **a: cs.call_tool(n, a)                                   # noqa: E731
            d = data(await call("buscar_perfil", texto="W18X3"))
            check(any(p["label"] == "W18X35" for p in d["perfiles"]), "buscar_perfil encuentra W18X35")
            d = data(await call("operaciones_disponibles", tipo="Placa simple"))
            check(d.get("tipo") == "Placa simple (corte)" and "n_bolts" in d["parametros"] and "opciones" in d["parametros"]["bolt_size"], "operaciones_disponibles describe los parámetros y opciones")
            d = data(await call("nueva_conexion", nombre="Columna con viga", principal={"perfil": "W14X90"}))
            check("activa" in d and "W14X90" in d["activa"], "nueva_conexion crea el proyecto y la conexión con su principal")
            d = data(await call("agregar_miembro", nombre="V1", perfil="W18X35", azimut=0, elevacion=0))
            check(d["miembro"]["perfil"] == "W18X35", "agregar_miembro")
            d = data(await call("agregar_operacion", tipo="Placa simple", parametros={"member": "V1", "n_bolts": 4, "bolt_size": "3/4"}))
            check(d.get("operacion", {}).get("indice") == 1 and d["geometria"]["errores"] == 0, f"agregar_operacion con geometría sin errores ({d.get('geometria')})")
            d = data(await call("agregar_operacion", tipo="Placa simple", parametros={"member": "V1", "bolt_size": "2"}))
            check("error" in d and "3/4" in d["error"], "un valor inválido se rechaza con las opciones válidas")
            d = data(await call("agregar_operacion", tipo="Placa simple", parametros={"member": "V9"}))
            check("error" in d and "V1" in d["error"], "un miembro inexistente se rechaza con la lista de elementos")
            d = data(await call("definir_cargas", cargas=[{"caso": "Caso 1", "miembro": "V1", "Vz": -30.0}]))
            check(d["casos"] == ["Caso 1"] and abs(d["nudo"][0]["reaccion_principal_F"][2] - 30.0) < 1e-6, "definir_cargas devuelve la reacción del principal por equilibrio")
            d = data(await call("describir_conexion"))
            check(len(d["miembros"]) == 1 and len(d["operaciones"]) == 1 and d["elementos_y_caras"], "describir_conexion")
            d = data(await call("imagen", tipo="modelo"))
            check(d.get("_imagen") == "image/png" and d["_bytes"] > 5000, "imagen del modelo (PNG)")
            d = data(await call("calcular", analisis_placas=not RAPIDO))
            f = d["formulas"]
            DC["chat"] = f["dc_max"]
            check({"Miembros", "Placas", "Pernos", "Soldaduras"} <= {c["categoria"] for c in f["categorias"]}, "calcular devuelve el resumen por categorías")
            if not RAPIDO:
                t0 = time.time()
                st = {}
                while time.time() - t0 < 900:
                    st = data(await call("estado_analisis", esperar_s=30))
                    if st.get("estado") != "en curso":
                        break
                check(st.get("estado") == "terminado", f"el análisis de placas termina ({time.time() - t0:.0f} s): {st}")
                d = data(await call("resultados"))
                check(d.get("modelo_placas") and d["resumen"]["analisis_placas_vigente"], "resultados incluye el modelo de placas")
                check(any("FEM" in c["fuentes"] for c in d["resumen"]["categorias"]), "las categorías incluyen verificaciones del modelo (FEM)")
                d = data(await call("resultados", categoria="Pernos"))
                check(d.get("componentes"), "resultados por categoría: componentes con su D/C")
                comp = d["componentes"][0]["componente"]
                d = data(await call("resultados", componente=comp))
                check(d.get("verificaciones") and all("dc" in v for v in d["verificaciones"]), "resultados por componente: verificaciones con demanda, capacidad y D/C")
                d = data(await call("imagen", tipo="esfuerzos"))
                check(d.get("_imagen") == "image/png", "imagen de los esfuerzos sobre la deformada")
            d = data(await call("generar_informe", formato="pdf"))
            check(os.path.exists(d.get("archivo", "")), f"informe PDF ({d.get('archivo')})")
            d = data(await call("listar_proyectos"))
            check(any("Columna con viga" in p["ruta"] for p in d["proyectos"]), "el proyecto queda guardado en el espacio de trabajo (se abre en la aplicación)")


def main():
    with tempfile.TemporaryDirectory() as ws:
        asyncio.run(flujo(ws))
        from steelconpro.model import load_book
        f = [os.path.join(dp, x) for dp, _d, fs in os.walk(ws) for x in fs if x.endswith(".scp")]
        p = load_book(f[0])[0] if f else None
        check(p is not None and p.node.members and p.node.operations and p.node.loads, "el .scp guardado tiene el miembro, la operación y las cargas")
        if p is not None:
            from dataclasses import asdict
            from steelconpro import api
            v = api.verify({"connection": asdict(p)})
            fm = round(max([c["ratio"] for c in v["checks"] if not c["skip"] and c.get("src") != "fem"] + [0.0]), 3)
            check(abs(fm - DC.get("chat", -1)) < 1e-3, f"el D/C de fórmulas por chat coincide con el de la aplicación ({DC.get('chat')} = {fm})")
        from steelconpro import mcp_server
        cfg = os.path.join(ws, "Claude", "claude_desktop_config.json")
        os.makedirs(os.path.dirname(cfg))
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"mcpServers": {"otro": {"command": "x"}}, "theme": "dark"}, fh)
        r = mcp_server.install_desktop(cfg, exe=r"C:\SteelConPro\engine\SteelConPro-engine.exe")
        d = json.load(open(cfg, encoding="utf-8"))
        check(d["mcpServers"]["steelconpro"] == {"command": r"C:\SteelConPro\engine\SteelConPro-engine.exe", "args": ["--mcp"]} and "otro" in d["mcpServers"]
              and d.get("theme") == "dark" and os.path.exists(cfg + ".bak"), "la instalación en Claude Desktop agrega «steelconpro» sin tocar lo demás (y respalda el archivo)")
    print("\nTODO BIEN" if not FAILS else f"\n{len(FAILS)} FALLAS")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
