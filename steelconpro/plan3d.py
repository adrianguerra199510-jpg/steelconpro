# -*- coding: utf-8 -*-
"""
Vistas EN PLANTA de la placa aislada con los resultados del modelo solido 3D (para la memoria).

Se muestra solo la placa base (sin el perfil ni el concreto), con el contorno de la placa, los agujeros, la
huella del perfil, los rigidizadores y la llave, y sobre ella:

  · von Mises PROMEDIADO en la cara superior   (el promedio del tensor en un circulo de radio fijo,
                                                 que si converge con la malla; ver view3d.smoothed_plate_vm)
  · von Mises PROMEDIADO en la cara inferior
  · presion de contacto sobre el concreto, con la traccion de cada perno
  · deflexion vertical de la placa

Todas llevan una etiqueta en el punto del maximo y la escala en las unidades del usuario.
"""
from __future__ import annotations
import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon
from matplotlib.tri import Triangulation

from . import geometry as G
from .params3d import foundation_ks


def _outline_patch(ax, prj, k):
    out = G.plate_outline(prj)
    ax.plot([q[0] / k for q in out] + [out[0][0] / k], [q[1] / k for q in out] + [out[0][1] / k],
            color="#1f3864", lw=1.6, zorder=6)
    for i, poly in enumerate(G.section_polys(prj)):
        ax.plot([q[0] / k for q in poly] + [poly[0][0] / k], [q[1] / k for q in poly] + [poly[0][1] / k],
                color="#555555", lw=1.0, ls="--", zorder=6, label="Perfil" if i == 0 else None)
    for (x1, y1, x2, y2) in G.stiffener_lines(prj):
        ax.plot([x1 / k, x2 / k], [y1 / k, y2 / k], color="#b26b00", lw=2.2, solid_capstyle="butt", zorder=6)
    for poly in G.lug_outline(prj):
        ax.add_patch(Polygon([(a / k, b / k) for a, b in poly], closed=True, fill=False,
                             edgecolor="#00843d", lw=1.4, ls=":", zorder=6))


def _holes(ax, prj, k, number=True):
    g = prj.bolts.geom()
    for i, (x, y) in enumerate(G.bolt_positions(prj), start=1):
        ax.add_patch(Circle((x / k, y / k), g.dh / 2 / k, facecolor="white", edgecolor="#333333",
                            lw=0.8, zorder=7))
        if number:
            ax.text(x / k, y / k, str(i), ha="center", va="center", fontsize=6, color="#333333", zorder=8)


def _mask_tri(tri, xy, prj, r_max):
    """Enmascara triangulos que cruzan agujeros, salen de la placa o atraviesan vacios."""
    g = prj.bolts.geom()
    bolts = np.array(G.bolt_positions(prj), dtype=float).reshape(-1, 2)
    t = tri.triangles
    cen = xy[t].mean(axis=1)
    mask = np.zeros(len(t), dtype=bool)
    for (bx, by) in bolts:
        mask |= np.hypot(cen[:, 0] - bx, cen[:, 1] - by) < g.dh / 2 - 1e-6
    e = np.stack([np.hypot(*(xy[t[:, i]] - xy[t[:, (i + 1) % 3]]).T) for i in range(3)], axis=1)
    mask |= e.max(axis=1) > r_max
    plate = G.plate_outline(prj)
    for i in np.where(~mask)[0]:
        if not G._inside(float(cen[i, 0]), float(cen[i, 1]), plate):
            mask[i] = True
    return mask


def _field_ax(fig, prj, u, xy, val, title, cmap, label, mark=None, cover=False, levels=18,
              vmax=None, extra=None, fy_line=None, bolts_T=None):
    ax = fig.add_axes([0.10, 0.12, 0.69, 0.77])
    k = u.fl
    tri0 = Triangulation(xy[:, 0], xy[:, 1])
    h = 6.0 * math.sqrt(prj.plate.Nc * prj.plate.Bc / max(len(xy), 1))
    tri = Triangulation(xy[:, 0] / k, xy[:, 1] / k, triangles=tri0.triangles,
                        mask=_mask_tri(tri0, xy, prj, h))
    v = np.asarray(val, dtype=float)
    hi = float(vmax if vmax is not None else max(v.max(), 1e-9))
    hi = hi if hi > 1e-12 else 1.0
    lv = np.linspace(0.0 if v.min() >= 0 else float(v.min()), hi, levels)
    cs = ax.tricontourf(tri, np.clip(v, lv[0], hi), levels=lv, cmap=cmap, extend="neither", zorder=2)
    if fy_line is not None and v.max() >= fy_line:
        ax.tricontour(tri, v, levels=[fy_line], colors="k", linewidths=1.0, linestyles="--", zorder=5)
    cb = fig.colorbar(cs, cax=fig.add_axes([0.83, 0.18, 0.025, 0.62]))
    cb.set_label(label, fontsize=8)
    cb.ax.tick_params(labelsize=7)
    _outline_patch(ax, prj, k)
    if cover:
        # zona cubierta por el perfil: en la cara superior no se lee esfuerzo (esta soldada)
        for poly in G.section_polys(prj):
            ax.add_patch(Polygon([(a / k, b / k) for a, b in poly], closed=True, facecolor="#dddddd",
                                 edgecolor="none", alpha=0.85, zorder=3, hatch="////"))
    _holes(ax, prj, k, number=bolts_T is None)
    if extra:
        extra(ax)
    if mark is not None:
        x, y, txt = mark
        ax.plot([x / k], [y / k], marker="*", ms=13, mfc="yellow", mec="k", mew=0.9, zorder=10)
        ax.annotate(txt, (x / k, y / k), textcoords="offset points", xytext=(12, 12), fontsize=8,
                    fontweight="bold", color="#7a0000", zorder=11,
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#7a0000", alpha=0.92),
                    arrowprops=dict(arrowstyle="-", color="#7a0000", lw=0.8))
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_title(title, fontsize=9, loc="left")
    ax.set_xlabel(f"X ({u.L})", fontsize=8)
    ax.set_ylabel(f"Y ({u.L})", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.margins(0.03)
    return ax


def render_plan_vm(prj, res, path, face, fields=None, dpi=160, size=(7.0, 5.6)):
    """von Mises promediado en la cara 'top' o 'bot' de la placa.  -> ruta o None."""
    from .view3d import smoothed_face_fields
    u = prj.units()
    if fields is None:
        r = max(prj.fea.vm_avg_factor * prj.plate.tp, 0.0)
        fields = smoothed_face_fields(res, prj, r)
    f = fields.get(face)
    if f is None:
        return None
    vm = f["vm"] / u.fs
    i = int(np.argmax(vm))
    Fy = prj.plate.mat().Fy / u.fs
    rad = fields["radius"]
    name = "superior" if face == "top" else "inferior (apoyada en el mortero)"
    fig = Figure(figsize=size, dpi=dpi)
    _field_ax(fig, prj, u, f["xy"], vm,
              f"von Mises promediado — cara {name}  (r = {u.q('L', rad)})", "inferno",
              f"σvM promediado ({u.S})",
              mark=(f["xy"][i][0], f["xy"][i][1], f"σvM = {vm[i]:.1f} {u.S}"),
              cover=(face == "top"), fy_line=0.90 * Fy)
    fig.text(0.10, 0.015, f"Linea discontinua: 0.90·Fy = {0.9 * Fy:.1f} {u.S}.  "
             + ("Rayado: huella del perfil (soldada, sin lectura de esfuerzo)." if face == "top" else ""),
             fontsize=7, color="#555555")
    fig.savefig(path)
    return path


def bolt_and_pressure(prj, res, post):
    """Presion de contacto en los nodos de la cara inferior: p = ks · hundimiento (ksi)."""
    ks = foundation_ks(prj)
    xs, ps = [], []
    for n, (x, y, z) in res.nodes.items():
        if abs(z) < 1e-4 and n in res.disp:
            xs.append((x, y))
            ps.append(ks * max(0.0, -res.disp[n][2]))
    return np.array(xs, dtype=float).reshape(-1, 2), np.array(ps, dtype=float)


def render_plan_pressure(prj, res, post, path, dpi=160, size=(7.0, 5.6)):
    """Presion de contacto sobre el concreto y traccion de cada perno."""
    xy, p = bolt_and_pressure(prj, res, post)
    if len(p) < 4:
        return None
    u = prj.units()
    pv = p / u.fs
    i = int(np.argmax(pv))
    fp_max = None
    bolts = {k: T for (k, x, y, T) in post.bolts}

    def extra(ax):
        k = u.fl
        pos = G.bolt_positions(prj)
        for j, (x, y) in enumerate(pos, start=1):
            T = bolts.get(j, 0.0)
            lab = f"P{j}" + (f"\nT={T / u.ff:.1f}" if T > 1e-3 else "")
            ax.annotate(lab, (x / k, y / k), textcoords="offset points", xytext=(0, 9), ha="center",
                        fontsize=6.5, fontweight="bold", color="#00407a" if T > 1e-3 else "#666666",
                        bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.85), zorder=9)

    fig = Figure(figsize=size, dpi=dpi)
    _field_ax(fig, prj, u, xy, pv, "Presion de contacto sobre el concreto y traccion en pernos",
              "YlOrRd", f"p ({u.S})",
              mark=(xy[i][0], xy[i][1], f"p max = {pv[i]:.3f} {u.S}"), bolts_T=bolts, extra=extra)
    fig.text(0.10, 0.015, f"Etiquetas: perno y traccion T ({u.F}) del modelo 3D.  Zona sin color = placa "
             "despegada del concreto (p = 0).", fontsize=7, color="#555555")
    fig.savefig(path)
    return path


def render_plan_uz(prj, res, path, dpi=160, size=(7.0, 5.6)):
    """Deflexion vertical de la cara superior de la placa (fuera de la huella del perfil)."""
    from .view3d import _covered_by_profile
    tp = prj.plate.tp
    u = prj.units()
    xy, w = [], []
    for n, (x, y, z) in res.nodes.items():
        if abs(z - tp) < 1e-4 and n in res.disp and not _covered_by_profile(prj, x, y):
            xy.append((x, y)); w.append(res.disp[n][2])
    if len(w) < 4:
        return None
    xy = np.array(xy); w = np.array(w) / u.fl
    i = int(np.argmax(np.abs(w)))
    fig = Figure(figsize=size, dpi=dpi)
    # w positivo = sube (se despega); negativo = baja (comprime el concreto)
    _field_ax(fig, prj, u, xy, w, "Desplazamiento vertical de la cara superior (+ sube)", "coolwarm",
              f"Uz ({u.L})", cover=True, mark=(xy[i][0], xy[i][1], f"Uz = {w[i]:.4f} {u.L}"),
              vmax=float(w.max()))
    fig.savefig(path)
    return path


def render_all(prj, res, folder) -> dict:
    """Genera las vistas en planta.  -> dict(top, bot, press, uz) con rutas (o None)."""
    from pathlib import Path
    from .view3d import smoothed_face_fields
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    out = {}
    try:
        fields = smoothed_face_fields(res, prj, max(prj.fea.vm_avg_factor * prj.plate.tp, 0.0)
                                      if prj.fea.vm_avg_factor > 0 else 0.0)
        # el radio efectivo no baja del tamano de malla (igual que en full_3d)
        va = getattr(res, "vm_avg", None)
        if va and va.get("radius", 0) > fields.get("radius", 0):
            fields = smoothed_face_fields(res, prj, va["radius"])
    except Exception:
        fields = None
    for key, fn in (("top", lambda: render_plan_vm(prj, res, str(f / "planta_vm_sup.png"), "top", fields)),
                    ("bot", lambda: render_plan_vm(prj, res, str(f / "planta_vm_inf.png"), "bot", fields)),
                    ("press", lambda: render_plan_pressure(prj, res, getattr(res, "post", None),
                                                           str(f / "planta_presion.png"))),
                    ("uz", lambda: render_plan_uz(prj, res, str(f / "planta_uz.png")))):
        try:
            out[key] = fn() if (fields or key in ("press", "uz")) else None
        except Exception:
            import traceback
            traceback.print_exc()
            out[key] = None
    return out
