# -*- coding: utf-8 -*-
"""Figuras y tablas del reporte de una conexión de nudo (PDF y Word), sin OpenGL ni Qt: el z-buffer propio (`fem/raster.py`) dibuja las vistas 3D y matplotlib
las secciones.

    sections_figure(prj, folder)                 imagen de las secciones de los perfiles usados (con sus medidas)
    section_rows(prj, us)                        propiedades de esas secciones
    model_views(prj, folder)                     isométrico frontal y posterior del modelo
    wire_views(prj, folder)                      isométrico alámbrico (ejes, nudo de análisis, cargas, reacción y resultante) por caso de carga
    fem_views(prj, shells, folder)               malla, von Mises con la malla y deformada con la malla (por caso analizado)
    fem_tables(prj, shells)                      tablas de resultados: placas y miembros (esfuerzos, deformación plástica, desplazamientos), pernos y cordones
"""
from __future__ import annotations
import math
import os
from pathlib import Path

import numpy as np

# ------------------------------------------------------------------------------------------------ tipografía y proyección
_FONTS = {}


def font_path(bold=False) -> str | None:
    try:
        import matplotlib
        p = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
        return str(p) if p.exists() else None
    except Exception:                                                  # noqa: BLE001
        return None


def pil_font(size: int, bold=False):
    from PIL import ImageFont
    k = (size, bold)
    if k not in _FONTS:
        fp = font_path(bold)
        try:
            _FONTS[k] = ImageFont.truetype(fp, size) if fp else ImageFont.load_default()
        except Exception:                                              # noqa: BLE001
            _FONTS[k] = ImageFont.load_default()
    return _FONTS[k]


def make_proj(bounds, elev, azim, size, margin=0.06):
    """Función 3D -> píxel de la imagen (misma cámara y encuadre que `raster.render`)."""
    from .fem.raster import camera
    d, right, up = camera(elev, azim)
    pts = np.asarray(bounds, float).reshape(-1, 3)
    sx_all, sy_all = pts @ right, pts @ up
    x0, x1, y0, y1 = sx_all.min(), sx_all.max(), sy_all.min(), sy_all.max()
    W, H = size
    sc = (1 - 2 * margin) * min(W / max(x1 - x0, 1e-9), H / max(y1 - y0, 1e-9))
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)

    def proj(Q):
        Q = np.asarray(Q, float)
        return ((Q @ right - cx) * sc + W / 2.0, H / 2.0 - (Q @ up - cy) * sc)
    return proj


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _draw_label(draw, xy, text, fg="#1f3864", bg="#ffffff", border="#1f3864", size=15, bold=True, anchor="mm"):
    f = pil_font(size, bold)
    l, t, r, b = draw.textbbox((0, 0), text, font=f)
    w, h = r - l + 10, b - t + 8
    x, y = xy
    if anchor == "mm":
        x0, y0 = x - w / 2, y - h / 2
    else:
        x0, y0 = x, y
    draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=4, fill=_hex(bg), outline=_hex(border), width=1)
    draw.text((x0 + 5 - l, y0 + 4 - t), text, font=f, fill=_hex(fg))
    return (x0, y0, x0 + w, y0 + h)


def _place_labels(draw, labels, size):
    """Dibuja etiquetas [(x, y, texto, fg, border)] desplazando las que se pisan (hacia abajo)."""
    placed = []
    for x, y, text, fg, border in labels:
        for _ in range(12):
            f = pil_font(15, True)
            l, t, r, b = draw.textbbox((0, 0), text, font=f)
            w, h = r - l + 10, b - t + 8
            box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if not any(not (box[2] < p[0] or box[0] > p[2] or box[3] < p[1] or box[1] > p[3]) for p in placed):
                break
            y += h + 2
        x = min(max(x, 70), size[0] - 70)
        y = min(max(y, 14), size[1] - 14)
        placed.append(_draw_label(draw, (x, y), text, fg=fg, border=border))
    return placed


def _colorbar(im, cbar, title, ticks=5):
    """Agrega a la derecha de la imagen una barra de colores con su escala."""
    from PIL import Image, ImageDraw
    W, H = im.size
    bw = 150
    out = Image.new("RGB", (W + bw, H), (255, 255, 255))
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    cols = np.asarray(cbar["colors"], float)
    x0, x1, y0, y1 = W + 18, W + 38, int(H * 0.16), int(H * 0.86)
    n = y1 - y0
    for k in range(n):
        c = cols[min(int((1 - k / max(n - 1, 1)) * (len(cols) - 1) + 0.5), len(cols) - 1)]
        d.line([(x0, y0 + k), (x1, y0 + k)], fill=tuple(int(v * 255) for v in c[:3]))
    d.rectangle([x0, y0, x1, y1], outline=(60, 60, 60))
    vmin, vmax = float(cbar["vmin"]), float(cbar["vmax"])
    f = pil_font(14)
    for t in range(ticks):
        fr = t / (ticks - 1)
        y = y1 - fr * (y1 - y0)
        d.line([(x1, y), (x1 + 5, y)], fill=(60, 60, 60))
        v = vmin + fr * (vmax - vmin)
        d.text((x1 + 8, y - 8), f"{v:.4g}", font=f, fill=(30, 30, 30))
    words, lines_, cur = title.split(), [], ""
    for wd in words:                                                   # el título se parte en líneas para que quepa junto a la barra
        if cur and len(cur) + 1 + len(wd) > 17:
            lines_.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines_.append(cur)
    ty = y0 - 20 - 18 * len(lines_)
    for ln_ in lines_:
        d.text((W + 12, ty), ln_, font=pil_font(14, True), fill=(30, 30, 30))
        ty += 18
    return out


def _caption(im, text, color="#7a1010", bg="#fff3e0"):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    _draw_label(d, (12, im.size[1] - 40), text, fg=color, bg=bg, border=color, size=14, bold=True, anchor="tl")
    return im


# ------------------------------------------------------------------------------------------------ secciones
def _shapes_used(prj):
    """[(etiqueta del perfil, [miembros que lo usan])] en orden de aparición."""
    nd = prj.node
    out = {}
    out.setdefault(nd.main_shape, []).append(f"{nd.main_name} (principal)")
    for m in nd.members:
        out.setdefault(m.shape, []).append(m.name)
    return list(out.items())


def sections_figure(prj, folder) -> str | None:
    """Imagen con la sección de cada perfil usado (formas reales, incluidas las secciones del Section Designer), con sus medidas principales."""
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle, Circle, Polygon, Wedge
    from . import assembly as AS
    us = prj.units()
    kl = us.fl
    used = _shapes_used(prj)
    if not used:
        return None
    n = len(used)
    cols = min(n, 3)
    rows = int(math.ceil(n / cols))
    fig = Figure(figsize=(3.3 * cols, 3.0 * rows), dpi=170)
    for k, (lab, owners) in enumerate(used):
        ax = fig.add_subplot(rows, cols, k + 1)
        shp = AS.shape_of(lab)
        fc, ec = "#9db4d0", "#2b3d57"
        xs, ys = [], []
        if shp.kind == "GEN":
            for pc in shp.pieces():
                if pc[0] == "circle":
                    _, u, v, ro, ri = pc
                    ax.add_patch(Wedge((u / kl, v / kl), ro / kl, 0, 360, width=(ro - ri) / kl if ri > 0 else None, fc=fc, ec=ec, lw=0.8))
                    xs += [(u - ro) / kl, (u + ro) / kl]
                    ys += [(v - ro) / kl, (v + ro) / kl]
                else:
                    P = [(a / kl, b / kl) for a, b in pc[1]]
                    ax.add_patch(Polygon(P, closed=True, fc=fc, ec=ec, lw=0.8))
                    xs += [p[0] for p in P]
                    ys += [p[1] for p in P]
        elif shp.is_round:
            ro, ri = shp.d / 2 / kl, max(shp.d / 2 - shp.tw, 0.0) / kl
            ax.add_patch(Wedge((0, 0), ro, 0, 360, width=(ro - ri) if ri > 0 else None, fc=fc, ec=ec, lw=0.8))
            xs, ys = [-ro, ro], [-ro, ro]
        else:
            for (x0, y0, x1, y1) in (shp.rects() or []):
                ax.add_patch(Rectangle((x0 / kl, y0 / kl), (x1 - x0) / kl, (y1 - y0) / kl, fc=fc, ec=ec, lw=0.8))
                xs += [x0 / kl, x1 / kl]
                ys += [y0 / kl, y1 / kl]
        if not xs:
            ax.set_axis_off()
            continue
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = x1 - x0, y1 - y0
        pad = 0.22 * max(w, h)
        ax.set_xlim(x0 - pad, x1 + pad)
        ax.set_ylim(y0 - pad, y1 + pad)
        ax.set_aspect("equal")
        ax.set_axis_off()
        arrow = dict(arrowstyle="<->", lw=0.7, color="#444")
        off = 0.1 * max(w, h)
        ax.annotate("", xy=(x0, y0 - off), xytext=(x1, y0 - off), arrowprops=arrow)
        ax.text((x0 + x1) / 2, y0 - off - 0.035 * max(w, h), f"{w:.4g}", ha="center", va="top", fontsize=7, color="#222")
        ax.annotate("", xy=(x1 + off, y0), xytext=(x1 + off, y1), arrowprops=arrow)
        ax.text(x1 + off + 0.03 * max(w, h), (y0 + y1) / 2, f"{h:.4g}", ha="left", va="center", fontsize=7, color="#222", rotation=90)
        dims = ""
        if shp.kind == "W":
            dims = f"tf = {shp.tf / kl:.4g}, tw = {shp.tw / kl:.4g} {us.L}"
        elif shp.kind in ("HSS", "HSS_RECT") or (shp.is_hollow and not shp.is_round):
            dims = f"t = {shp.tw / kl:.4g} {us.L}"
        elif shp.is_round:
            dims = f"t = {shp.tw / kl:.4g} {us.L}"
        ax.set_title(f"{lab}\n{dims}" if dims else lab, fontsize=8, fontweight="bold", color="#1f3864", pad=4)
        ax.text(0.5, -0.02, "Usado en: " + ", ".join(owners), transform=ax.transAxes, ha="center", va="top", fontsize=6.6, color="#555")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.9, bottom=0.08, wspace=0.08, hspace=0.3)
    p = str(Path(folder) / "secciones.png")
    fig.savefig(p)
    return p


def section_rows(prj, us):
    """[(perfil, A, Ix, Iy, Zx, Zy, peso)] en unidades del proyecto, para la tabla de propiedades."""
    from . import assembly as AS
    kl = us.fl
    rows = []
    for lab, _own in _shapes_used(prj):
        s = AS.shape_of(lab)
        rows.append((lab, s.A / kl ** 2, s.Ix / kl ** 4, s.Iy / kl ** 4, s.Zx / kl ** 3, s.Zy / kl ** 3))
    return rows


# ------------------------------------------------------------------------------------------------ vistas del modelo
VIEW_FRONT = (24.0, 50.0)
VIEW_REAR = (24.0, 230.0)


def _save(im, folder, name):
    p = str(Path(folder) / name)
    im.save(p)
    return p


def model_views(prj, folder, size=(1200, 820)) -> list:
    """[(título, ruta)] del isométrico frontal y del posterior del modelo (con los nombres de los miembros)."""
    from .assembly import build_model
    from .fem import scene as FS
    from PIL import ImageDraw
    mdl = build_model(prj)
    sc = FS.scene_model(mdl, loads=False, tags=True)
    out = []
    for nm, title, (el, az) in (("iso_frontal.png", "Isométrico frontal", VIEW_FRONT), ("iso_posterior.png", "Isométrico posterior", VIEW_REAR)):
        im = FS.render_scene_image(sc, el, az, size, ss=2, margin=0.07)
        proj = make_proj(sc.pts, el, az, size, 0.07)
        d = ImageDraw.Draw(im)
        labs = []
        for pos, text in getattr(mdl, "tags", []):
            x, y = proj(pos)
            labs.append((x, y, text, "#1f3864", "#1f3864"))
        _place_labels(d, labs, size)
        out.append((title, _save(im, folder, nm)))
    return out


# ------------------------------------------------------------------------------------------------ alámbrico con cargas
def _sphere(c, r, rgb, n=12, m=18):
    V, T = [], []
    for i in range(n + 1):
        th = math.pi * i / n
        for j in range(m):
            ph = 2 * math.pi * j / m
            V.append((c[0] + r * math.sin(th) * math.cos(ph), c[1] + r * math.sin(th) * math.sin(ph), c[2] + r * math.cos(th)))
    for i in range(n):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            T += [(a, b, a + m), (b, b + m, a + m)]
    col = np.tile(np.array([rgb[0], rgb[1], rgb[2], 1.0]), (len(V), 1))
    return np.array(V), np.array(T), col


def wire_scene(prj, case_index: int):
    """Escena del modo alámbrico de un caso: ejes de los miembros, nudo de análisis, acciones de los miembros, reacción y resultante.  -> (escena, etiquetas, nombre del caso)"""
    from .assembly import build_model
    from .fem.model3d import Prism
    from . import nodal as NOD
    from ..scene3d import Scene
    mdl = build_model(prj)
    wire = getattr(mdl, "wire", None) or {"node": [0, 0, 0], "lines": []}
    lines = wire.get("lines", [])
    lo, hi = mdl.bounds()
    span = float(np.max(np.asarray(hi) - np.asarray(lo)))
    r = 0.0065 * span
    sc = Scene()
    pts = [np.asarray(wire["node"], float)]
    sc.group = "wire"
    for ln in lines:
        a, b = np.asarray(ln["a"], float), np.asarray(ln["b"], float)
        d = b - a
        L = float(np.linalg.norm(d))
        if L < 1e-9:
            continue
        u = d / L
        ref = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        U = np.cross(u, ref)
        U /= np.linalg.norm(U)
        V = np.cross(u, U)
        col = (0.12, 0.22, 0.39) if ln["kind"] == "principal" else (0.18, 0.46, 0.71)
        pr = Prism(o=tuple(a), U=tuple(U), V=tuple(V), w0=0.0, w1=L, circle=(r, 0.0))
        sc.add_faces(pr.faces(16), col, 1.0, edges=False)
        pts += [a, b]
    sc.add_mesh(*_sphere(np.asarray(wire["node"], float), 0.026 * span, (0.91, 0.36, 0.05)))
    labels = []
    for ln in lines:
        b = np.asarray(ln["b"], float)
        labels.append((b + np.array([0, 0, 0.02 * span]), ln["name"], "#1f3864", "#1f3864"))
    labels.append((np.asarray(wire["node"], float) + np.array([0, 0, 0.05 * span]), "Nudo de análisis", "#c44a06", "#e85d0c"))
    us = prj.units()
    ana = NOD.analysis(prj, prj.node)
    cases = ana["cases"]
    cname = ""
    if cases:
        c = cases[min(case_index, len(cases) - 1)]
        cname = c["case"]
        node = np.asarray(wire["node"], float)
        nrm = lambda x: float(np.linalg.norm(x))                          # noqa: E731
        items = []
        for dr in c["draw"]:
            kind = dr["kind"]
            pos = node if kind == "reaction" else np.asarray(dr["pos"], float)
            items.append((dr["name"], pos, np.asarray(dr["F"], float), np.asarray(dr["M"], float), kind))
        if c.get("sum_F") is not None and (nrm(c["sum_F"]) > 1e-9 or nrm(c["sum_M"]) > 1e-9):
            items.append((f"Resultante de las cargas", node, np.asarray(c["sum_F"], float), np.asarray(c["sum_M"], float), "resultant"))
        cF = {"member": (0.85, 0.1, 0.1), "main": (0.85, 0.1, 0.1), "ext": (0.85, 0.1, 0.1), "reaction": (0.1, 0.5, 0.25), "resultant": (0.71, 0.33, 0.04)}
        tF = {"member": "#9c0006", "main": "#9c0006", "ext": "#9c0006", "reaction": "#14663a", "resultant": "#b45309"}
        cM = {"reaction": (0.56, 0.27, 0.68), "resultant": (0.71, 0.33, 0.04)}
        for name, pos, F, M, kind in items:
            LF = (0.15 if kind in ("reaction", "resultant") else 0.21) * span
            if nrm(F) > 1e-9:
                d = F / nrm(F)
                tail = pos - d * LF
                sc.add_arrow(tuple(tail), tuple(pos), cF.get(kind, (0.85, 0.1, 0.1)), 0.0042 * span)
                pts += [tail, pos]
                labels.append((tail, f"{name}: {us.q('F', nrm(F), 2)}", tF.get(kind, "#9c0006"), tF.get(kind, "#9c0006")))
            if nrm(M) > 1e-9:
                d = M / nrm(M)
                LM = (0.12 if kind in ("reaction", "resultant") else 0.16) * span
                col = cM.get(kind, (0.5, 0.1, 0.7))
                sc.add_arrow(tuple(pos - d * LM), tuple(pos + d * LM), col, 0.0036 * span)
                sc.add_arrow(tuple(pos), tuple(pos + d * LM * 1.15), col, 0.0036 * span)
                pts += [pos - d * LM, pos + d * LM * 1.15]
                labels.append((pos + d * LM * 1.25, f"{name}: {us.q('M', nrm(M), 1)}", "#5b2c83", "#5b2c83"))
    sc.pts = np.array(pts, float)
    return sc, labels, cname


def wire_views(prj, folder, size=(1200, 820), max_cases=6) -> list:
    """[(título, ruta)] del isométrico alámbrico con cargas, reacción y resultante de cada caso de carga."""
    from .fem import scene as FS
    from . import nodal as NOD
    from PIL import ImageDraw
    n = len(NOD.cases_of(prj.node))
    out = []
    for i in range(min(max(n, 1), max_cases)):
        sc, labels, cname = wire_scene(prj, i)
        el, az = VIEW_FRONT
        im = FS.render_scene_image(sc, el, az, size, ss=2, margin=0.1)
        proj = make_proj(sc.pts, el, az, size, 0.1)
        d = ImageDraw.Draw(im)
        labs = []
        for pos, text, fg, border in labels:
            x, y = proj(pos)
            labs.append((x, y, text, fg, border))
        _place_labels(d, labs, size)
        title = "Isométrico alámbrico — cargas, reacción y resultante" + (f" — {cname}" if cname else "")
        out.append((title, _save(im, folder, f"alambrico_{i + 1}.png")))
    return out


# ------------------------------------------------------------------------------------------------ malla y resultados del FEM
def _mesh_scene(R):
    """Escena de la malla sin resultados: cada elemento del color de su pieza, con las aristas de la malla."""
    from ..scene3d import Scene
    from .fem.model3d import COLORS
    sc = Scene()
    V, T, C, seg = [], [], [], []
    for _e, ns, p in R.elems:
        base = len(V)
        col = COLORS.get(R.plate_kind[p], COLORS.get("plate", "#c8956c")).lstrip("#")
        rgb = [int(col[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]
        for n in ns:
            V.append(R.xyz[n])
            C.append(rgb)
        T.append((base, base + 1, base + 2))
        if len(ns) == 4:
            T.append((base, base + 2, base + 3))
        for q in range(len(ns)):
            seg.append((R.xyz[ns[q]], R.xyz[ns[(q + 1) % len(ns)]]))
    sc.add_mesh(np.array(V), np.array(T), np.array(C))
    if seg:
        arr = np.zeros((2 * len(seg), 10), np.float32)
        A = np.array(seg)
        arr[0::2, 0:3], arr[1::2, 0:3] = A[:, 0], A[:, 1]
        arr[:, 6:10] = (0.1, 0.12, 0.16, 0.5)
        sc.lines.append(arr)
        sc.tagged.append(("other", "l", arr))
    sc.pts = np.array(V)
    return sc


def fem_views(prj, shells, folder, size=(1200, 820)) -> list:
    """[(título, ruta, pie)] de la malla del modelo de placas y, por caso analizado, el von Mises con la malla y la deformada con la malla.
    `shells` = [(nombre del caso, ShellResult, ShellCase)]."""
    from .fem import scene as FS
    from .fem import shellpost as SPo
    from PIL import ImageDraw
    us = prj.units()
    out = []
    if not shells:
        return out
    el, az = VIEW_FRONT
    R0 = shells[0][1]
    sc = _mesh_scene(R0)
    im = FS.render_scene_image(sc, el, az, size, ss=2, margin=0.07)
    out.append(("Malla del modelo de placas", _save(im, folder, "fem_malla.png"),
                f"{R0.n_nodes:,} nodos y {R0.n_elems:,} elementos de cascarón (S3/S4) sobre la superficie media de cada placa y de cada pieza de los miembros."))
    for k, (cname, R, _case) in enumerate(shells):
        for field, scale, nm, ttl in (("vm", 0.0, f"fem_vm_{k + 1}.png", "Esfuerzo de von Mises en las caras, con la malla"),
                                      ("u", None, f"fem_def_{k + 1}.png", "Deformada con la malla (color = desplazamiento)")):
            sc2 = SPo.scene(R, us, field=field, scale=(SPo.auto_scale(R) if scale is None else scale), edges=True)
            from .fem.raster import render
            tris, cols, segs = FS.scene_arrays(sc2)
            im = render(tris, cols, segs, el, az, size, bounds=np.asarray(sc2.pts, float), ss=2, margin=0.07, line_rgb=(70, 80, 95))
            if getattr(sc2, "cbar", None) is not None:
                im = _colorbar(im, sc2.cbar, sc2.title or ttl)
            hud = next((h[1] for h in getattr(sc2, "hud", [])), "")
            if hud:
                _caption(im, hud)
            out.append((f"{ttl} — {cname}", _save(im, folder, nm), ""))
    return out


# ------------------------------------------------------------------------------------------------ tablas de resultados
def _part_disp(R) -> dict:
    """Desplazamiento máximo |U| (in) de cada pieza del modelo de placas."""
    mag = np.linalg.norm(R.U, axis=1)
    out = {}
    for _e, ns, p in R.elems:
        part = R.plate_part[p]
        out[part] = max(out.get(part, 0.0), float(mag[ns].max()))
    return out


def fem_tables(prj, shells) -> list:
    """[{case, parts: (encabezado, filas), bolts: (...), bolt_groups: (...), welds: (...), summary: [...]}] por caso analizado, en unidades del proyecto."""
    from .common import FNV, PHI_BOLT, bolt_tension_shear
    us = prj.units()
    out = []
    for cname, R, _case in shells:
        disp = _part_disp(R)
        rows = []
        order = sorted(R.parts.items(), key=lambda kv: (kv[0] not in R.member_names, kv[0]))
        for part, d in order:
            vm = d["vm"]
            ratio = vm / (0.9 * d["Fy"]) if d["Fy"] > 0 else 0.0
            rows.append([part, "Miembro" if part in R.member_names else "Placa", us.fmt("L", d["t"], 3) if d["t"] else "-", us.fmt("S", d["Fy"], 0),
                         us.fmt("S", vm, 1), us.fmt("S", d["vm_peak"], 1), f"{ratio:.2f}", f"{d['peeq'] * 100:.3f}", us.fmt("L", disp.get(part, 0.0), 3)])
        hdr = ["Pieza", "Tipo", f"Espesor ({us.L})", f"Fy ({us.S})", f"von Mises zona ({us.S})", f"Pico ({us.S})", "σ/φFy", "PEEQ (%)", f"|U| máx ({us.L})"]
        res = {"case": cname, "parts": (hdr, rows)}
        # ---- pernos
        brow, groups = [], {}
        for b in R.bolts:
            if b["anchor"]:
                continue
            Ab = math.pi * b["db"] ** 2 / 4.0
            grade = b["grade"] if b["grade"] in FNV else "A325-N"
            phiV = PHI_BOLT * FNV[grade] * Ab
            phiT = bolt_tension_shear(b["db"], grade, b["V"] / Ab)
            rv, rt = b["V"] / phiV, max(b["T"], 0.0) / max(phiT, 1e-9)
            brow.append((max(rv, rt), [b["tag"], " – ".join(dict.fromkeys(b["parts"])), us.fmt("F", b["V"], 2), us.fmt("F", max(b["T"], 0.0), 2), us.fmt("F", phiV, 1), us.fmt("F", phiT, 1), f"{rv:.2f}", f"{rt:.2f}"]))
            g = groups.setdefault(b["group"], {"n": 0, "V": 0.0, "T": 0.0, "r": 0.0, "parts": " – ".join(dict.fromkeys(b["parts"]))})
            g["n"] += 1
            g["V"], g["T"], g["r"] = max(g["V"], b["V"]), max(g["T"], max(b["T"], 0.0)), max(g["r"], rv, rt)
        brow.sort(key=lambda x: -x[0])
        res["bolts"] = (["Perno", "Placas que une", f"V ({us.F})", f"T ({us.F})", f"φVn ({us.F})", f"φTn ({us.F})", "V/φVn", "T/φTn"], [r for _k, r in brow])
        res["bolt_groups"] = (["Grupo", "Placas que une", "Pernos", f"V máx ({us.F})", f"T máx ({us.F})", "D/C máx"],
                              [[k, v["parts"], str(v["n"]), us.fmt("F", v["V"], 2), us.fmt("F", v["T"], 2), f"{v['r']:.2f}"] for k, v in groups.items()])
        # ---- anclajes
        arow = [[b["tag"], us.fmt("F", b["V"], 2), us.fmt("F", max(b["T"], 0.0), 2)] for b in R.bolts if b["anchor"]]
        res["anchors"] = (["Anclaje", f"V ({us.F})", f"T ({us.F})"], arow)
        # ---- cordones
        wg = {}
        for w in R.welds:
            k = f"{w['A']} – {w['B']}"
            g = wg.setdefault(k, {"n": 0, "L": 0.0, "q": 0.0, "cap": w["cap"], "r": 0.0, "w": w["w"]})
            g["n"] += 1
            g["L"] += w["L"]
            g["q"] = max(g["q"], w["q"])
            g["r"] = max(g["r"], w["q"] / max(w["cap"], 1e-9))
        res["welds"] = ([f"Unión", "Tramos", f"Largo ({us.L})", f"Cateto ({us.L})", f"q máx ({us.F}/{us.L})", f"φRn ({us.F}/{us.L})", "D/C"],
                        [[k, str(v["n"]), us.fmt("L", v["L"], 0), us.fmt("L", v["w"], 1), f"{v['q'] * us.fl / us.ff:.4g}", f"{v['cap'] * us.fl / us.ff:.4g}", f"{v['r']:.2f}"] for k, v in wg.items()])
        res["summary"] = [("Nodos / elementos", f"{R.n_nodes:,} / {R.n_elems:,}"), ("Desplazamiento máximo", us.q("L", R.umax, 3)),
                          ("von Mises máximo (caras)", us.q("S", R.vmmax, 1)), ("Deformación plástica máxima", f"{R.peeqmax * 100:.3f} %"),
                          ("Tipo de análisis", "elasto-plástico" if R.plastic else "elástico")]
        out.append(res)
    return out
