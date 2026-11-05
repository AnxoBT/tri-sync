"""Servidor web local (solo librería estándar). Solo escucha en 127.0.0.1."""
import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import config
from core.config import CACHE, ROOT

WEB = Path(__file__).resolve().parent
LOGS = ROOT / "logs"

# estado de la revisión en segundo plano
JOB = {"activo": False, "mensajes": [], "error": None, "fin": None}


def _revisar(solo):
    from core import diff
    JOB.update(activo=True, mensajes=[], error=None, fin=None)
    try:
        res = diff.compute(progress=lambda m: JOB["mensajes"].append(m), solo=solo)
        res["calculado"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        config.save_cache("diff.json", res)
    except Exception as e:  # token caducado, export que falta…
        JOB["error"] = str(e)
    finally:
        JOB.update(activo=False, fin=datetime.now().strftime("%H:%M:%S"))


def _probar():
    out = {}
    try:
        from core.serializd import Serializd
        out["serializd"] = {"ok": True, "texto": f"Conectado como {Serializd().check()}"}
    except Exception as e:
        out["serializd"] = {"ok": False, "texto": str(e)}
    try:
        from core.dixmax_api import Dixmax
        Dixmax().check()
        out["dixmax"] = {"ok": True, "texto": "API oficial conectada (se pueden aplicar cambios)"}
    except Exception as e:
        out["dixmax"] = {"ok": False, "texto": str(e)}
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/diff":
            p = CACHE / "diff.json"
            return self._send(200, json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"diferencias": []})
        if self.path == "/api/estado":
            from core.imports import estado_exports
            p = CACHE / "diff.json"
            calc = json.loads(p.read_text(encoding="utf-8")).get("calculado") if p.exists() else None
            return self._send(200, {"exports": estado_exports(), "calculado": calc,
                                    "letterboxd_user": config.env("LETTERBOXD_USER"), "trabajo": JOB})
        if self.path == "/api/progreso":
            return self._send(200, JOB)
        if self.path == "/api/config":
            return self._send(200, config.config_publica())
        self._send(404, {"error": "no existe"})

    def do_POST(self):
        if self.path == "/api/revisar":
            if not JOB["activo"]:
                threading.Thread(target=_revisar, args=(self._body().get("solo"),), daemon=True).start()
            return self._send(200, {"ok": True})
        if self.path == "/api/importar":
            from core.imports import importar_desde_descargas
            try:
                return self._send(200, {"ok": True, "log": importar_desde_descargas()})
            except Exception as e:
                return self._send(200, {"ok": False, "log": [str(e)]})
        if self.path == "/api/config":
            config.guardar_config(self._body())
            return self._send(200, {"ok": True, "config": config.config_publica()})
        if self.path == "/api/probar":
            return self._send(200, _probar())
        if self.path == "/api/plan":
            LOGS.mkdir(exist_ok=True)
            f = LOGS / f"plan_{datetime.now():%Y%m%d_%H%M%S}.json"
            f.write_text(json.dumps(self._body(), ensure_ascii=False, indent=1), encoding="utf-8")
            return self._send(200, {"ok": True, "archivo": str(f)})
        if self.path == "/api/run":
            from core.apply import execute
            body = self._body()
            try:
                return self._send(200, {"ok": True, **execute(body.get("acciones", []), dry=bool(body.get("simulacion", True)))})
            except Exception as e:
                return self._send(200, {"ok": False, "log": [f"ERROR: {e}"], "archivos": []})
        if self.path == "/api/abrir":
            p = Path(self._body().get("archivo", ""))
            if p.exists() and LOGS in p.parents:
                os.startfile(p.parent)
            return self._send(200, {"ok": True})
        self._send(404, {"error": "no existe"})


def serve(port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Web local en http://127.0.0.1:{port}  (Ctrl+C para salir)")
    srv.serve_forever()
