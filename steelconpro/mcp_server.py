# -*- coding: utf-8 -*-
"""Servidor MCP de SteelConPro para Claude Desktop (transporte stdio): crear conexiones, analizarlas y obtener los resultados desde el chat.

    SteelConPro-engine.exe --mcp        (aplicación instalada)
    python run.py --mcp                 (desarrollo)

Las herramientas llaman a `chat.py`, que usa la misma API del motor que la interfaz (`api.py`), así que los resultados son los de la aplicación.
Los proyectos se guardan en el espacio de trabajo de la aplicación (Documentos/SteelConPro, o SCP_WORKSPACE).
"""
from __future__ import annotations
import functools
import json
import os
import sys

INSTRUCCIONES = """SteelConPro diseña conexiones de acero (AISC 360-22, ACI 318-19): un nudo con un miembro principal, miembros que llegan a él y
operaciones (placas simples, dobles ángulos, placas extremas, cartelas, placa base, placas, pernos y soldaduras generales).
Flujo típico: listar_proyectos / abrir_proyecto o nueva_conexion → definir_principal → agregar_miembro → operaciones_disponibles(tipo) →
agregar_operacion → revisar_geometria → definir_cargas → calcular → estado_analisis (repetir hasta «terminado») → resultados → imagen / generar_informe.
UNIDADES DE ENTRADA: in, kip, kip·in, ksi y grados (convierta si el usuario da mm, kN, MPa: 1 in = 25.4 mm, 1 kip = 4.448 kN, 1 ksi = 6.895 MPa).
Los resultados salen en las unidades de la conexión. Cargas: acción de cada miembro sobre el nudo en sus ejes locales (x a lo largo del miembro
desde el nudo, N > 0 tracción; z el peralte; y = z × x); la reacción del miembro principal sale del equilibrio.
Antes de calcular revise la geometría (errores = piezas sueltas o que se cruzan). Responda al usuario en español."""


def _err(fn):
    """Convierte los errores de validación en un mensaje para el chat (el modelo lo lee y corrige los datos)."""
    @functools.wraps(fn)
    def w(*a, **k):
        from .chat import ChatError
        from .api import ApiError
        try:
            return fn(*a, **k)
        except (ChatError, ApiError) as e:
            return {"error": str(e)}
    return w


def build_server(root: str | None = None):
    from mcp.server.fastmcp import FastMCP, Image
    from . import chat as C

    mcp = FastMCP("SteelConPro", instructions=INSTRUCCIONES, log_level="WARNING")
    S = C.Session(root)

    def tool(fn):
        return mcp.tool()(_err(fn))

    # ------------------------------------------------------------------ proyectos
    @tool
    def listar_proyectos() -> dict:
        """Proyectos (.scp) del espacio de trabajo de SteelConPro."""
        return C.listar_proyectos(S)

    @tool
    def abrir_proyecto(ruta: str) -> dict:
        """Abre un proyecto por su ruta relativa al espacio de trabajo (de listar_proyectos) o por parte de su nombre."""
        return C.abrir_proyecto(S, ruta)

    @tool
    def nuevo_proyecto(nombre: str, carpeta: str = "", unidades: str = "Imperial") -> dict:
        """Crea un proyecto nuevo (una conexión vacía) en el espacio de trabajo. unidades: «Imperial» (in, kip, ksi) o «SI» (mm, kN, MPa) para los resultados."""
        return C.nuevo_proyecto(S, nombre, carpeta, unidades)

    @tool
    def guardar_proyecto(ruta: str = "") -> dict:
        """Guarda el proyecto (cada cambio ya se guarda solo); con `ruta` lo guarda con otro nombre."""
        return C.guardar_proyecto(S, ruta)

    @tool
    def listar_conexiones() -> dict:
        """Conexiones del proyecto abierto y cuál está activa."""
        return C.listar_conexiones(S)

    @tool
    def seleccionar_conexion(conexion: str) -> dict:
        """Activa una conexión del proyecto por su número (1, 2, …), nombre o código de elemento."""
        return C.seleccionar_conexion(S, conexion)

    @tool
    def nueva_conexion(nombre: str, elemento: str = "", tipologia: str = "", parametros: dict | None = None, principal: dict | None = None,
                       unidades: str = "") -> dict:
        """Agrega una conexión al proyecto abierto (si no hay, crea el proyecto) y la activa. `tipologia` (opcional, ver tipologias) arma un nudo
        típico con sus `parametros`; `principal` = {perfil, acero, nombre, azimut, elevacion, extremo} define el miembro principal."""
        return C.nueva_conexion(S, nombre, elemento, tipologia, parametros, principal, unidades)

    # ------------------------------------------------------------------ catálogo
    @tool
    def buscar_perfil(texto: str, limite: int = 25) -> dict:
        """Busca perfiles del catálogo AISC (W, HSS, Pipe, L, C, WT…) por texto, p. ej. «W18X» o «HSS6X6»."""
        return C.buscar_perfil(S, texto, limite)

    @tool
    def tipologias() -> dict:
        """Tipologías de nudo predefinidas (columna con diagonales, nudo de vigas, placa base) y sus parámetros."""
        return C.tipologias(S)

    @tool
    def operaciones_disponibles(tipo: str = "") -> dict:
        """Sin `tipo`: lista de operaciones. Con `tipo` (nombre o parte, p. ej. «Placa simple»): sus parámetros, valores típicos y opciones válidas."""
        return C.operaciones_disponibles(S, tipo)

    # ------------------------------------------------------------------ modelado
    @tool
    def definir_principal(perfil: str = "", acero: str = "", nombre: str = "", azimut: float | None = None, elevacion: float | None = None,
                          giro: float | None = None, extremo: str | None = None) -> dict:
        """Define el miembro principal: perfil, acero, nombre, azimut y elevación de su eje (90 = columna vertical, 0 = viga horizontal), giro, y
        `extremo` («Continuo (pasa por el nudo)» o «Termina en el nudo (el cuerpo queda del lado −)» / «(… lado +)»)."""
        return C.definir_principal(S, perfil, acero, nombre, azimut, elevacion, giro, extremo)

    @tool
    def agregar_miembro(nombre: str, perfil: str, azimut: float = 0.0, elevacion: float = 0.0, posicion: float = 0.0, acero: str = "", se_une_a: str = "",
                        desplazamiento: float = 0.0, desplazamiento_lateral: float = 0.0, giro: float = 0.0, separacion: float = 0.0) -> dict:
        """Agrega un miembro que llega al nudo: azimut en planta (0 = +x, 90 = +y) y elevación (0 horizontal, ±45 diagonal) de su eje desde el nudo,
        `posicion` a lo largo del principal (in), desplazamientos del eje (in), giro del perfil (°), separación a la cara del principal (in) y
        `se_une_a` (otro miembro; vacío = el principal). Devuelve la revisión de geometría."""
        return C.agregar_miembro(S, nombre, perfil, azimut, elevacion, posicion, acero, se_une_a, desplazamiento, desplazamiento_lateral, giro, separacion)

    @tool
    def modificar_miembro(nombre: str, cambios: dict) -> dict:
        """Cambia campos de un miembro: name, shape, steel, az, el, pos, off, off2, roll, gap, attach_to (in y grados) y load_at (punto de aplicación
        de sus acciones en el análisis de placas: «Automático», «En el extremo del elemento» o «En los pernos»)."""
        return C.modificar_miembro(S, nombre, cambios)

    @tool
    def eliminar_miembro(nombre: str) -> dict:
        """Quita un miembro con sus operaciones y cargas."""
        return C.eliminar_miembro(S, nombre)

    @tool
    def agregar_operacion(tipo: str, parametros: dict | None = None) -> dict:
        """Agrega una operación (conexión de catálogo, placa, pernos, soldadura, recorte, placa base, bloque de concreto). Vea los parámetros con
        operaciones_disponibles(tipo); los omitidos toman su valor típico. Devuelve la operación y la revisión de geometría."""
        return C.agregar_operacion(S, tipo, parametros)

    @tool
    def modificar_operacion(indice: int, cambios: dict) -> dict:
        """Cambia parámetros de la operación número `indice` (1, 2, …; ver describir_conexion)."""
        return C.modificar_operacion(S, indice, cambios)

    @tool
    def eliminar_operacion(indice: int) -> dict:
        """Quita la operación `indice` (y las que dependen de la pieza que crea)."""
        return C.eliminar_operacion(S, indice)

    @tool
    def configurar_placa_base(cambios: dict) -> dict:
        """Datos de la placa base con rutas «grupo.campo»: plate.N, plate.B, plate.tp, plate.steel, plate.grout; bolts.size, bolts.steel,
        bolts.n_major, bolts.n_minor, bolts.ex, bolts.ey, bolts.hef; conc.fc, conc.N2, conc.B2, conc.ha; stiff.enabled, stiff.count, stiff.t… (in, ksi)."""
        return C.configurar_placa_base(S, cambios)

    @tool
    def definir_cargas(cargas: list[dict], reemplazar: bool = True) -> dict:
        """Cargas por caso: lista de {caso, miembro, N, Vy, Vz, T, My, Mz} (kip, kip·in) = acción del miembro sobre el nudo en sus ejes locales en
        el extremo junto al nudo (N > 0 tracción; en una viga horizontal Vz es el cortante vertical). miembro = «@nudo» para una carga externa en
        ejes globales. Devuelve la reacción del principal por equilibrio."""
        return C.definir_cargas(S, cargas, reemplazar)

    @tool
    def describir_conexion() -> dict:
        """Estado completo de la conexión activa: principal, miembros, operaciones (con su número), cargas y elementos con sus caras."""
        return C.describir_conexion(S)

    @tool
    def revisar_geometria() -> dict:
        """Revisor de geometría: piezas que se cruzan, piezas sueltas, cordones o pernos fuera de sitio."""
        return C.revisar_geometria(S)

    @tool
    def analisis_nodal() -> dict:
        """Equilibrio del nudo por caso de carga (acciones de los miembros y reacción del principal)."""
        return C.analisis_nodal(S)

    # ------------------------------------------------------------------ análisis y resultados
    @tool
    def calcular(analisis_placas: bool = True) -> dict:
        """Verifica la conexión (fórmulas cerradas, inmediato) y lanza el análisis del modelo de placas con CalculiX en segundo plano (1 a 8 min por
        caso). Después llame a estado_analisis hasta que diga «terminado» y luego a resultados."""
        return C.calcular(S, analisis_placas)

    @tool
    def estado_analisis(esperar_s: float = 40.0) -> dict:
        """Estado del análisis de placas (espera hasta `esperar_s` segundos, máx. 50, a que termine)."""
        return C.estado_analisis(S, esperar_s)

    @tool
    def resultados(categoria: str = "", componente: str = "", solo_no_cumple: bool = False) -> dict:
        """Resumen estándar: D/C máximo y verificación que gobierna por categoría (Miembros, Placas, Pernos, Soldaduras, Anclajes y concreto) y
        máximos del modelo de placas. Con `categoria`: sus componentes; con `componente` (o `solo_no_cumple`): las verificaciones con demanda,
        capacidad, D/C y referencia."""
        return C.resultados(S, categoria, componente, solo_no_cumple)

    @tool
    def generar_informe(formato: str = "pdf", ruta: str = "") -> dict:
        """Informe de cálculo PDF o Word (docx) junto al proyecto (o en `ruta`)."""
        return C.generar_informe(S, formato, ruta)

    @mcp.tool()
    def imagen(tipo: str = "modelo", caso: int = 1, azimut: float = 50.0, elevacion: float = 24.0):
        """Imagen de la conexión: tipo «modelo» (geometría 3D) o, tras el análisis, «esfuerzos» (von Mises), «plastica» (deformación plástica) o
        «desplazamiento», sobre la deformada; `caso` = número de caso de carga; azimut/elevación de la vista (°)."""
        from .chat import ChatError
        try:
            return Image(data=C.imagen(S, tipo, caso, azimut, elevacion), format="png")
        except ChatError as e:
            return {"error": str(e)}

    return mcp


def main(argv=None):
    """Arranca el servidor por stdio.  La salida estándar queda reservada al protocolo: cualquier `print` del motor (o de procesos hijos que
    hereden el descriptor 1) se manda a la salida de errores."""
    real = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = os.fdopen(real, "w", encoding="utf-8", buffering=1)
    os.environ.setdefault("MPLBACKEND", "Agg")
    root = None
    if argv and "--root" in argv:
        root = argv[argv.index("--root") + 1]
    srv = build_server(root)
    srv.run("stdio")
    return 0


def desktop_config(exe: str | None = None, root: str | None = None) -> dict:
    """Entrada de `claude_desktop_config.json` para este programa (con la carpeta de trabajo de la aplicación, si se da)."""
    args = ["--mcp"]
    if exe is None:
        if getattr(sys, "frozen", False):
            exe = sys.executable
        else:
            exe, args = sys.executable, [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py"), "--mcp"]
    if root:
        args += ["--root", str(root)]
    return {"command": exe, "args": args}


def desktop_config_path() -> str:
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Claude", "claude_desktop_config.json")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


def stable_engine_dir() -> str:
    """Carpeta fija para la copia del motor que usa Claude Desktop: la aplicación portable se descomprime en una carpeta temporal distinta en cada
    inicio, así que la configuración no puede apuntar ahí."""
    base = os.environ.get("LOCALAPPDATA") or (os.path.expanduser("~/Library/Application Support") if sys.platform == "darwin" else os.path.expanduser("~/.local/share"))
    return os.path.join(base, "SteelConPro", "claude-engine")


def _copy_engine() -> str:
    """Copia el motor compilado (carpeta del ejecutable, con CalculiX) a la carpeta fija y devuelve la ruta del ejecutable copiado."""
    import shutil
    from . import __version__
    src = os.path.dirname(os.path.abspath(sys.executable))
    dst = stable_engine_dir()
    if os.path.normcase(os.path.abspath(src)) != os.path.normcase(os.path.abspath(dst)):
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    with open(os.path.join(dst, "VERSION.txt"), "w", encoding="utf-8") as f:
        f.write(__version__)
    return os.path.join(dst, os.path.basename(sys.executable))


def install_desktop(path: str | None = None, exe: str | None = None, root: str | None = None) -> dict:
    """Agrega (o actualiza) «steelconpro» en la configuración de Claude Desktop sin tocar los otros servidores.  Con el motor compilado, primero lo
    copia a una carpeta fija (ver `stable_engine_dir`).  Devuelve la ruta y la entrada."""
    path = path or desktop_config_path()
    if exe is None and getattr(sys, "frozen", False):
        exe = _copy_engine()
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            txt = f.read().strip()
        if txt:
            data = json.loads(txt)
    data.setdefault("mcpServers", {})["steelconpro"] = desktop_config(exe, root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        import shutil
        shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"path": path, "entry": data["mcpServers"]["steelconpro"]}


def desktop_status(path: str | None = None) -> dict:
    path = path or desktop_config_path()
    entry = None
    try:
        with open(path, encoding="utf-8") as f:
            entry = (json.load(f).get("mcpServers") or {}).get("steelconpro")
    except (OSError, ValueError):
        pass
    from . import __version__
    stale = False
    if entry is not None and getattr(sys, "frozen", False):
        try:
            with open(os.path.join(os.path.dirname(entry["command"]), "VERSION.txt"), encoding="utf-8") as f:
                stale = f.read().strip() != __version__
        except OSError:
            stale = True
    return {"path": path, "installed": entry is not None, "entry": entry, "stale": stale, "version": __version__}
