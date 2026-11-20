# -*- coding: utf-8 -*-
"""Rasterizador de triangulos con z-buffer (numpy + Pillow): imagenes PNG de las escenas para los reportes y las pruebas, sin OpenGL
ni Qt.  Proyeccion ortografica, sombreado plano o colores por vertice interpolados."""
from __future__ import annotations
import math

import numpy as np


def camera(elev, azim):
    az, el = math.radians(azim), math.radians(elev)
    d = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    right = np.cross([0.0, 0.0, 1.0], d)
    right /= max(np.linalg.norm(right), 1e-12)
    up = np.cross(d, right)
    return d, right, up


def render(tris, cols, lines=None, elev=24.0, azim=50.0, size=(1100, 800), bg=(255, 255, 255), ss=2, margin=0.06,
           shade=True, line_rgb=(25, 30, 40), bounds=None):
    """tris: (n, 3, 3) vertices; cols: (n, 3, 4) color RGBA por vertice (0-1).  lines: (m, 2, 3).  -> PIL.Image"""
    from PIL import Image
    W, H = size[0] * ss, size[1] * ss
    d, right, up = camera(elev, azim)
    P = tris.reshape(-1, 3)
    pts = P if bounds is None else bounds
    sx_all, sy_all = pts @ right, pts @ up
    x0, x1, y0, y1 = sx_all.min(), sx_all.max(), sy_all.min(), sy_all.max()
    sc = (1 - 2 * margin) * min(W / max(x1 - x0, 1e-9), H / max(y1 - y0, 1e-9))
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)

    def proj(Q):
        return np.stack([(Q @ right - cx) * sc + W / 2.0, H / 2.0 - (Q @ up - cy) * sc, Q @ d], axis=-1)
    S = proj(tris.reshape(-1, 3)).reshape(-1, 3, 3)
    img = np.empty((H, W, 3), np.float32)
    img[:] = np.array(bg, np.float32)
    zb = np.full((H, W), -1e30, np.float32)
    # sombreado: luz fija en la camara y un poco de lado
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    nrm = np.cross(e1, e2)
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.maximum(ln, 1e-20)
    light = d * 0.8 + right * 0.35 + up * 0.35
    light /= np.linalg.norm(light)
    k = 0.42 + 0.58 * np.abs(nrm @ light) if shade else np.ones(len(tris))
    area = 0.5 * ((S[:, 1, 0] - S[:, 0, 0]) * (S[:, 2, 1] - S[:, 0, 1]) - (S[:, 2, 0] - S[:, 0, 0]) * (S[:, 1, 1] - S[:, 0, 1]))
    for i in range(len(S)):
        a, b, c = S[i]
        ar = area[i]
        if abs(ar) < 1e-9:
            continue
        xa, xb = int(max(math.floor(min(a[0], b[0], c[0])), 0)), int(min(math.ceil(max(a[0], b[0], c[0])), W - 1))
        ya, yb = int(max(math.floor(min(a[1], b[1], c[1])), 0)), int(min(math.ceil(max(a[1], b[1], c[1])), H - 1))
        if xa > xb or ya > yb:
            continue
        gx, gy = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
        w0 = ((b[0] - gx) * (c[1] - gy) - (c[0] - gx) * (b[1] - gy)) / (2 * ar)
        w1 = ((c[0] - gx) * (a[1] - gy) - (a[0] - gx) * (c[1] - gy)) / (2 * ar)
        w2 = 1.0 - w0 - w1
        eps = -1e-4
        m = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if not m.any():
            continue
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        sub = zb[ya:yb + 1, xa:xb + 1]
        m &= z > sub
        if not m.any():
            continue
        cc = cols[i]
        rgb = (w0[..., None] * cc[0, :3] + w1[..., None] * cc[1, :3] + w2[..., None] * cc[2, :3]) * k[i]
        sub[m] = z[m]
        img[ya:yb + 1, xa:xb + 1][m] = np.clip(rgb[m], 0, 1) * 255.0
    if lines is not None and len(lines):
        L = proj(lines.reshape(-1, 3)).reshape(-1, 2, 3)
        for p, q in L:
            n = int(max(abs(q[0] - p[0]), abs(q[1] - p[1]))) + 1
            t = np.linspace(0, 1, n * 2)
            px = (p[0] + (q[0] - p[0]) * t).astype(int)
            py = (p[1] + (q[1] - p[1]) * t).astype(int)
            pz = p[2] + (q[2] - p[2]) * t
            ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
            px, py, pz = px[ok], py[ok], pz[ok]
            vis = pz >= zb[py, px] - 0.02 * max(1e-9, 1.0)
            img[py[vis], px[vis]] = np.array(line_rgb, np.float32)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if ss > 1:
        im = im.resize(size, Image.LANCZOS)
    return im
