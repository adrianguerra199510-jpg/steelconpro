# -*- coding: utf-8 -*-
"""Punto de entrada de PlacaBasePro.

    PlacaBasePro.exe                       -> interfaz grafica
    PlacaBasePro.exe --selftest            -> autopruebas del motor (sin interfaz)
    PlacaBasePro.exe --mesh a.geo b.inp    -> (interno) malla con la API de Gmsh
    PlacaBasePro.exe proyecto.pbase --pdf mem.pdf --docx s.docx
                                     --3d carpeta --geo modelo3d.geo
                                           -> calculo por lotes sin interfaz
                                              (--3d corre Gmsh + CalculiX y verifica con sus resultados)
"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)
BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def resolve(p):
    """Busca el archivo tal cual y, si no esta, junto al ejecutable/bundle."""
    if os.path.exists(p):
        return p
    for base in (os.path.dirname(sys.executable) if FROZEN else "", BUNDLE):
        if base:
            q = os.path.join(base, p)
            if os.path.exists(q):
                return q
    return p


def batch(argv):
    """Calcula TODAS las conexiones del archivo (un .pbase es un libro, como lo guarda la interfaz).
    Con varias conexiones, los archivos de --pdf / --docx / --geo llevan el nombre de la conexion al final."""
    from placabase.model import load_book
    book = load_book(resolve(argv[0]))
    rc = 0
    for i, prj in enumerate(book):
        suf = "" if len(book) == 1 else "_" + "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in (prj.element or f"conexion{i + 1}"))
        rc = max(rc, batch_one(prj, argv, suf))
    return rc


def _out(argv, flag, suf):
    p = argv[argv.index(flag) + 1]
    if not suf:
        return p
    base, ext = os.path.splitext(p)
    return base + suf + ext


def batch_one(prj, argv, suf=""):
    import tempfile
    from placabase.solver import solve
    from placabase import report, mesh3d
    from placabase.conn.specs import CT_BASEPLATE

    fem = None
    if prj.ctype != CT_BASEPLATE and ("--3d" in argv or "--geo" in argv):
        print(f"  aviso: --3d/--geo solo aplican a la placa base; '{prj.ctype}' se calcula en forma cerrada.")
    if "--3d" in argv and prj.ctype == CT_BASEPLATE:
        from placabase.rep3d import make_fem
        r3, msg = mesh3d.full_3d(prj, _out(argv, "--3d", suf))
        print("  3D:", msg)
        fem = make_fem(prj, r3) if r3 is not None else None
    res = solve(prj, fem=fem)
    gov = res.governing
    print(f"{prj.element}: {'CUMPLE' if res.ok else 'NO CUMPLE'}   "
          f"D/C max = {res.max_ratio:.3f}" + (f"   gobierna: {gov.title}" if gov else ""))
    for w in res.warnings:
        print("  aviso:", w)

    figs = None
    if any(f in argv for f in ("--docx", "--pdf")):
        figs = report.save_figures(prj, res, tempfile.mkdtemp(prefix="pbase_"))
    if "--pdf" in argv:
        print("  ->", report.export_pdf(prj, res, _out(argv, "--pdf", suf), figs))
    if "--docx" in argv:
        print("  ->", report.export_docx(prj, res, _out(argv, "--docx", suf), figs))
    if "--geo" in argv and prj.ctype == CT_BASEPLATE:
        g, d = mesh3d.export_3d(prj, _out(argv, "--geo", suf), prj.fea.mesh3d)
        print("  ->", g)
        print("  ->", d)
    return 0 if res.ok else 2


def mesh_child(geo, out):
    """Proceso hijo: malla con la libreria de Gmsh incluida (sin gmsh.exe).
    Va aparte para que un fallo de Gmsh no cierre la ventana principal."""
    import gmsh
    gmsh.initialize(["gmsh", "-nopopup"], interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.option.setNumber("General.NumThreads", max(1, (os.cpu_count() or 2) - 1))
        gmsh.open(geo)
        gmsh.model.mesh.generate(3)
        gmsh.write(out)
    finally:
        gmsh.finalize()
    return 0 if os.path.exists(out) else 3


def main():
    args = sys.argv[1:]
    if args and args[0] == "--mesh":
        return mesh_child(args[1], args[2])
    if args and args[0] == "--selftest":
        import runpy
        st = os.path.join(BUNDLE, "selftest.py")
        os.chdir(BUNDLE)
        runpy.run_path(st, run_name="__main__")
        return 0
    if args and not args[0].startswith("-"):
        return batch(args)
    from placabase.ui import main as gui
    return gui()


if __name__ == "__main__":
    sys.exit(main())
