# -*- coding: utf-8 -*-
"""Galeria de perfiles libres (Section Designer) reducidos a placas y mallados.  Uso:  python3 tools/galeria_perfiles_libres.py <carpeta_de_imagenes>

Cada imagen muestra: (izquierda) la seccion con su linea media y espesor por placa; (derecha) la malla de cuadrilateros de un tramo del perfil."""
import json
import os
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
import numpy as np                                               # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from steelconpro import sections as SEC                          # noqa: E402
from steelconpro.shapes import make_general                      # noqa: E402
from steelconpro.conn.assembly import section_prisms             # noqa: E402
from steelconpro.conn.fem.model3d import Model3D, Part           # noqa: E402
from steelconpro.conn.fem import shellmesh as SM                 # noqa: E402

CASOS = [
    ("Perfil I armado (alas distintas)", SEC.build_template("Perfil I armado (alas distintas)", d=14, bf=9, tf=0.75, tw=0.4, bf2=6, tf2=0.5)),
    ("Cajón soldado", SEC.build_template("Cajón soldado")),
    ("Canal armado", SEC.build_template("Canal armado", d=10, bf=4, tf=0.4, tw=0.3)),
    ("Te armada", SEC.build_template("Te armada")),
    ("Doble ángulo espalda con espalda", SEC.build_template("Doble angulo espalda con espalda", a=5, b=5, t=0.5, gap=0.5)),
    ("Tubo circular", SEC.build_template("Tubo circular", d=8, t=0.375)),
    ("Cruz de dos placas", SEC.build_template("Cruz (dos placas)", L=9, t=0.5)),
    ("Cruz girada 45° (rectángulos con giro)", [{"t": "rect", "x": 0, "y": 0, "w": 10, "h": 0.5, "rot": 45}, {"t": "rect", "x": 0, "y": 0, "w": 10, "h": 0.5, "rot": -45}]),
    ("I con cubreplaca", SEC.build_template("Perfil I con cubreplacas")),
    ("Polígono libre: canal con alas cónicas", [{"t": "poly", "pts": [[0, 0], [9, 0], [9, 0.3], [0.5, 0.9], [0.5, 7.1], [9, 7.7], [9, 8], [0, 8]]}]),
    ("Polígono libre: Z", [{"t": "poly", "pts": [[0, 0], [5, 0], [5, 0.5], [0.5, 0.5], [0.5, 6], [6, 6], [6, 6.5], [0, 6.5]]}]),
    ("Barra maciza (tubo equivalente)", SEC.build_template("Barra circular maciza", d=4)),
]


def stub_model(comps, L):
    shp = make_general("libre", comps)
    A, sx, sy = (0, 0, 1.0), (1.0, 0, 0), (0, 1.0, 0)
    prs = section_prisms(shp, (0, 0, 0), sx, sy, A, 0.0, L)
    m = Model3D("perfil")
    m.parts.append(Part("Perfil", "beam", "Perfil", 50.0, 65.0, prs, t=shp.tw))
    return m, shp


def malla(plates, h):
    with tempfile.TemporaryDirectory() as td:
        jf, npz = os.path.join(td, "j.json"), os.path.join(td, "m.npz")
        SM.write_job(plates, {"h_near": h, "h_far": h, "h_hole": h / 2, "zone": None, "transition": 1.0}, jf)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), "--meshs", jf, npz], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])
        sm = SM.ShellMesh(npz)
        return sm, [sm.polygons(i) for i in range(len(sm.keys))]


def dibujar(nombre, comps, out):
    ext = max(float(make_general("x", comps).d), float(make_general("x", comps).bf))
    L = max(1.2 * ext, 5.0)
    mdl, shp = stub_model(comps, L)
    plates, notas = SM.build_plates(mdl)
    h = max(ext / 14.0, 0.25)
    sm, polys = malla(plates, h)
    fig = plt.figure(figsize=(13, 5.6))
    # ---- seccion con la linea media
    ax = fig.add_subplot(1, 2, 1)
    for pc in shp.pieces():
        if pc[0] == "circle":
            _, u, v, ro, ri = pc
            for r_, c_ in ((ro, "#cfd8e3"),) + (((ri, "white"),) if ri > 0 else ()):
                ax.add_patch(plt.Circle((u, v), r_, color=c_, zorder=1))
        else:
            ax.fill([q[0] for q in pc[1]], [q[1] for q in pc[1]], color="#cfd8e3", ec="#6b7b8c", lw=0.8, zorder=1)
    cols = plt.cm.tab10.colors
    for k, pl in enumerate(plates):
        P = pl.P
        if P[:, 2].max() - P[:, 2].min() < 1e-6:
            continue
        # placas extruidas a lo largo de z: su traza en la seccion (u, v) es un segmento
        zs = np.unique(np.round(P[:, 2], 6))
        base = P[np.abs(P[:, 2] - zs.min()) < 1e-6][:, :2]
        if len(base) >= 2:
            a_, b_ = base[0], base[-1]
            ax.plot([a_[0], b_[0]], [a_[1], b_[1]], color=cols[k % 10], lw=min(max(pl.t * 14, 2.0), 7.0), solid_capstyle="butt", alpha=0.9, zorder=3)
            ax.plot([a_[0], b_[0]], [a_[1], b_[1]], color="black", lw=0.6, zorder=4)
    ax.set_aspect("equal")
    ax.autoscale()
    ax.set_title(f"{nombre}\nsección y línea media de cada placa ({len(plates)} placas; el ancho de la línea ∝ espesor)", fontsize=9.5)
    ax.grid(alpha=0.25)
    # ---- malla 3D
    ax3 = fig.add_subplot(1, 2, 2, projection="3d")
    allp = []
    for k, pg in enumerate(polys):
        if not pg:
            continue
        pc3 = Poly3DCollection(pg, facecolor=cols[k % 10], edgecolor="#22303f", linewidths=0.35, alpha=0.95)
        ax3.add_collection3d(pc3)
        allp += [q for f in pg for q in f]
    P = np.array(allp)
    lo, hi = P.min(axis=0), P.max(axis=0)
    c, r = (lo + hi) / 2, float((hi - lo).max()) / 2
    ax3.set_xlim(c[0] - r, c[0] + r); ax3.set_ylim(c[1] - r, c[1] + r); ax3.set_zlim(c[2] - r, c[2] + r)
    ax3.set_box_aspect((1, 1, 1))
    ax3.view_init(elev=24, azim=-58)
    ax3.set_axis_off()
    ax3.set_title(f"malla de placas: {len(sm.node_ids):,} nodos · {sm.n_elems:,} elementos", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return notas


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "galeria"
    os.makedirs(out, exist_ok=True)
    for i, (nombre, comps) in enumerate(CASOS, 1):
        f = os.path.join(out, f"perfil_libre_{i:02d}.png")
        try:
            notas = dibujar(nombre, comps, f)
            print("OK  ", nombre, "->", f, notas or "")
        except Exception as e:                                           # noqa: BLE001
            print("FALLA", nombre, type(e).__name__, e)


if __name__ == "__main__":
    main()
