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


HIST = "historial.json"


def _revisar(solo, rapida=False):
    from core import diff
    from core.imports import estado_exports
    JOB.update(activo=True, mensajes=[], error=None, fin=None)
    try:
        ex = estado_exports()
        for k in ("dixmax", "letterboxd"):
            e = ex[k]
            JOB["mensajes"].append(f"{k}: {e['carpeta']} ({e['edad']})" if e["carpeta"] else f"{k}: sin export")
        t0 = datetime.now()
        res = diff.compute(progress=lambda m: JOB["mensajes"].append(m), solo=solo, rapida=rapida)
        res["calculado"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        config.save_cache("diff.json", res)
        from collections import Counter
        hist = config.cache_json(HIST, [])
        hist.append({"fecha": res["calculado"], "modo": res["modo"], "segundos": round((datetime.now() - t0).total_seconds()),
                     "diferencias": len(res["diferencias"]),
                     "categorias": dict(Counter(d["categoria"] for d in res["diferencias"])),
                     "fuentes": res["fuentes"], "stats": res.get("stats", {})})
        config.save_cache(HIST, hist[-100:])
    except Exception as e:  # token caducado, export que falta…
        JOB["error"] = str(e)
    finally:
        JOB.update(activo=False, fin=datetime.now().strftime("%H:%M:%S"))


def _probar():
    from core.imports import estado_exports
    out = {}
    ex = estado_exports()
    out["carpetas"] = {"ok": all("no existe" not in c for c in ex["carpetas"]), "texto": " · ".join(ex["carpetas"])}
    for k, nombre, max_h in (("dixmax", "export Dixmax", 24 * 30), ("letterboxd", "export Letterboxd", 24)):
        e = ex[k]
        if not e["carpeta"]:
            pre = "playmax-userdata-" if k == "dixmax" else "letterboxd-"
            out[nombre] = {"ok": False, "texto": f"No encontrado (zip o carpeta completa que empiece por '{pre}')"}
            continue
        txt = (f"{e['carpeta']} ({e['tipo']}) en {e['ubicacion']} · descargado {e['fecha']} ({e['edad']}) · "
               f"archivos OK: {', '.join(e['archivos'])}")
        if e["otros"]:
            txt += f" · hay {e['otros']} más antiguos (se ignoran)"
        aviso = e["horas"] > max_h
        if aviso:
            txt += " · ⚠ antiguo, descarga uno nuevo" if k == "letterboxd" else " · ⚠ fechas poco actualizadas"
        out[nombre] = {"ok": True, "aviso": aviso, "texto": txt}
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
        if self.path in ("/favicon.ico", "/logo.ico"):
            return self._send(200, (WEB / "logo.ico").read_bytes(), "image/x-icon")
        if self.path == "/logo.svg":
            return self._send(200, (WEB / "logo.svg").read_bytes(), "image/svg+xml")
        if self.path == "/api/historial":
            return self._send(200, list(reversed(config.cache_json(HIST, []))))
        if self.path == "/api/progreso":
            return self._send(200, JOB)
        if self.path == "/api/config":
            return self._send(200, config.config_publica())
        self._send(404, {"error": "no existe"})

    def do_POST(self):
        if self.path == "/api/revisar":
            if not JOB["activo"]:
                b = self._body()
                threading.Thread(target=_revisar, args=(b.get("solo"), b.get("modo") == "rapida"), daemon=True).start()
            return self._send(200, {"ok": True})
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
