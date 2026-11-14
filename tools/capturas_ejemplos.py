# -*- coding: utf-8 -*-
"""Tablero de capturas: abre cada ejemplo `ejemplos/*.scp` en la aplicación Electron y guarda una imagen del visor 3D por ejemplo,
más un tablero `tablero.png` con todas (para revisarlos de un vistazo).

    python3 tools/capturas_ejemplos.py [carpeta_salida] [--filtro CN-] [--dir otra_carpeta_de_ejemplos ...]      (por defecto: capturas_ejemplos/ en el directorio temporal)

Necesita Electron preparado (electron/node_modules) y xvfb-run en Linux.  Si Electron falla al arrancar (a veces el proceso de GPU de
swiftshader se cae) se reintenta.
"""
import glob
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def capturar(files, out, intentos=4, lote=6):
    """Abre los ejemplos en Electron por lotes (un arranque por lote; si la aplicación se cae se reintentan los que faltan)."""
    def falta(fs):
        return [f for f in fs if not os.path.exists(os.path.join(out, os.path.splitext(os.path.basename(f))[0] + ".png"))]
    files = list({os.path.basename(f): f for f in files}.values())
    for i in range(0, len(files), lote):
        grupo = files[i:i + lote]
        for _ in range(intentos):
            pend = falta(grupo)
            if not pend:
                break
            cmd = ["node", "tests/tablero.js", out] + pend
            if sys.platform.startswith("linux"):
                cmd = ["xvfb-run", "-a"] + cmd
            try:
                r = subprocess.run(cmd, cwd=os.path.join(ROOT, "electron"), capture_output=True, text=True, timeout=120 + 40 * len(pend))
                print(r.stdout.strip())
            except subprocess.TimeoutExpired:
                print("tiempo agotado; se reintenta")
    return falta(files)


def tablero(out, nombres, cols=4, w=520):
    from PIL import Image, ImageDraw
    ims = []
    for n in nombres:
        p = os.path.join(out, n + ".png")
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            h = int(im.height * w / im.width)
            ims.append((n, im.resize((w, h))))
    if not ims:
        return None
    hh = max(im.height for _, im in ims) + 26
    rows = (len(ims) + cols - 1) // cols
    T = Image.new("RGB", (cols * w, rows * hh), (255, 255, 255))
    d = ImageDraw.Draw(T)
    for k, (n, im) in enumerate(ims):
        x, y = (k % cols) * w, (k // cols) * hh
        T.paste(im, (x, y + 24))
        d.text((x + 8, y + 6), n, fill=(20, 20, 20))
    path = os.path.join(out, "tablero.png")
    T.save(path)
    return path


def main():
    args = [a for a in sys.argv[1:]]
    filtro = ""
    if "--filtro" in args:
        i = args.index("--filtro")
        filtro = args[i + 1]
        del args[i:i + 2]
    dirs = [os.path.join(ROOT, "ejemplos")]
    while "--dir" in args:                                     # carpetas adicionales de ejemplos (p. ej. de otro worktree)
        i = args.index("--dir")
        dirs.append(args[i + 1])
        del args[i:i + 2]
    out = args[0] if args else os.path.join(tempfile.gettempdir(), "capturas_ejemplos")
    os.makedirs(out, exist_ok=True)
    files = sorted((f for d in dirs for f in glob.glob(os.path.join(d, "*.scp")) if filtro in os.path.basename(f)), key=os.path.basename)
    falta = capturar(files, out)
    nombres = [os.path.splitext(os.path.basename(f))[0] for f in files]
    print("tablero:", tablero(out, nombres))
    if falta:
        print("sin captura:", [os.path.basename(f) for f in falta])
        sys.exit(1)


if __name__ == "__main__":
    main()
