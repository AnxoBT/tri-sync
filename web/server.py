"""Servidor web local (solo librería estándar). Solo escucha en 127.0.0.1."""
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.config import CACHE, ROOT

WEB = Path(__file__).resolve().parent
PLANES = ROOT / "logs"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/diff":
            p = CACHE / "diff.json"
            return self._send(200, json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"diferencias": []})
        self._send(404, {"error": "no existe"})

    def do_POST(self):
        if self.path == "/api/plan":
            n = int(self.headers.get("Content-Length", 0))
            plan = json.loads(self.rfile.read(n) or b"{}")
            PLANES.mkdir(exist_ok=True)
            f = PLANES / f"plan_{datetime.now():%Y%m%d_%H%M%S}.json"
            f.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
            # Fase 1: solo se guarda el plan. Las fases 2 y 3 lo ejecutarán.
            return self._send(200, {"ok": True, "archivo": str(f), "acciones": len(plan.get("acciones", []))})
        self._send(404, {"error": "no existe"})


def serve(port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Web local en http://127.0.0.1:{port}  (Ctrl+C para salir)")
    srv.serve_forever()
