# -*- coding: utf-8 -*-
"""Servidor local del motor para la aplicacion Electron: HTTP en 127.0.0.1, POST /api/<funcion> con cuerpo JSON -> JSON (ver api.py).

    python run.py --serve [--port N] [--token T] [--ui carpeta]

Escribe en la salida estandar una linea `SCP_READY {"port": N, "token": "..."}` cuando esta listo.  Cada llamada exige la cabecera `X-SCP-Token`
(solo la conoce la aplicacion que lo lanzo).  Con `--ui` tambien sirve esa carpeta en /ui/ (para probar la interfaz en un navegador).
"""
from __future__ import annotations
import json
import mimetypes
import secrets
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import api


def make_handler(token: str, ui_dir: Path | None):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):                        # sin ruido en la consola
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SCP-Token")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send(204, b"")

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/health":
                return self._send(200, json.dumps({"ok": True, "version": api.__version__}).encode())
            if ui_dir is not None and u.path.startswith("/ui"):
                rel = u.path[3:].lstrip("/") or "index.html"
                f = (ui_dir / rel).resolve()
                if ui_dir.resolve() in f.parents and f.is_file():
                    ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                    if f.suffix == ".js" or f.suffix == ".mjs":
                        ctype = "text/javascript"
                    return self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
            return self._send(404, b'{"error": "no encontrado"}')

        def do_POST(self):
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._send(404, b'{"error": "no encontrado"}')
            if self.headers.get("X-SCP-Token") != token:
                return self._send(403, b'{"error": "token invalido"}')
            fn = api.EXPORTED.get(u.path[5:])
            if fn is None:
                return self._send(404, json.dumps({"error": f"funcion desconocida: {u.path[5:]}"}).encode())
            try:
                n = int(self.headers.get("Content-Length") or 0)
                args = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out = fn(args)
                body = json.dumps(out, ensure_ascii=False, default=_default).encode("utf-8")
                return self._send(200, body)
            except api.ApiError as e:
                return self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:                        # noqa: BLE001
                return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2500:]}, ensure_ascii=False).encode("utf-8"))
    return H


def _default(o):
    import numpy as np
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"no serializable: {type(o).__name__}")


def serve(port: int = 0, token: str | None = None, ui_dir: str | None = None, quiet: bool = False):
    token = token or secrets.token_hex(16)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, Path(ui_dir) if ui_dir else None))
    srv.daemon_threads = True
    info = {"port": srv.server_address[1], "token": token}
    if not quiet:
        print("SCP_READY " + json.dumps(info), flush=True)
    return srv, info


def main(argv):
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 0
    token = argv[argv.index("--token") + 1] if "--token" in argv else None
    ui = argv[argv.index("--ui") + 1] if "--ui" in argv else None
    srv, _info = serve(port, token, ui)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
