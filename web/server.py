"""Servidor web local (solo librería estándar). Solo escucha en 127.0.0.1."""
import json
import os
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import config
from core.config import CACHE, LOGS

WEB = Path(__file__).resolve().parent
INDEX = (WEB / "index.html").read_bytes()  # se fija al arrancar: página y servidor siempre de la misma versión
ANILIST_HTML = """<!doctype html><meta charset="utf-8"><title>Tri-Sync · AniList</title>
<body style="font:16px system-ui;background:#0f1218;color:#e6e6e6;display:grid;place-items:center;height:90vh">
<div id="m">Guardando el permiso de AniList…</div>
<script>
const p = new URLSearchParams(location.hash.slice(1));
if (!p.get('access_token')) document.getElementById('m').textContent = 'AniList no ha dado permiso. Cierra esta pestaña y vuelve a probar.';
else fetch('/api/anilist_token', {method: 'POST', body: JSON.stringify({access_token: p.get('access_token'), expires_in: p.get('expires_in')})})
  .then(r => r.json()).then(r => {
    history.replaceState(null, '', '/anilist');
    document.getElementById('m').innerHTML = r.ok ? '✓ Conectado con AniList como <b>' + r.usuario + '</b>. Ya puedes cerrar esta pestaña.' : 'Error: ' + r.texto;
    if (r.ok) setTimeout(() => window.close(), 1500);
  });
</script>""".encode()

# estado de la revisión en segundo plano
JOB = {"activo": False, "mensajes": [], "error": None, "fin": None}


HIST = "historial.json"
RUN = {"activo": False, "simulacion": True, "total": 0, "hechos": 0, "actual": "", "cancelar": False,
       "resultado": None}


def _aplicar(acciones, simulacion):
    from core.apply import execute
    RUN.update(activo=True, simulacion=simulacion, total=len(acciones), hechos=0, actual="Empezando…",
               cancelar=False, resultado=None)
    try:
        RUN["resultado"] = {"ok": True, **execute(acciones, dry=simulacion, ctl=RUN)}
    except Exception as e:
        RUN["resultado"] = {"ok": False, "log": RUN.get("log", []) + [f"ERROR: {e}"], "archivos": [],
                            "hechas": list(RUN.get("hechas") or [])}
    finally:
        try:
            _quitar_aplicadas(acciones, RUN["resultado"] or {})
            if not simulacion:
                _historial_aplicacion(acciones, RUN["resultado"] or {})
        finally:
            RUN["activo"] = False


def _historial_aplicacion(acciones, res):
    """Cada aplicación real queda en el historial con lo que se cambió (y si salió bien)."""
    hechas = set(res.get("hechas") or [])
    hist = config.cache_json(HIST, [])
    hist.append({"fecha": datetime.now().strftime("%d/%m/%Y %H:%M"), "modo": "aplicación", "segundos": None,
                 "aplicadas": len(hechas), "total": len(acciones),
                 "acciones": [{"c": a.get("categoria"), "t": a.get("titulo"), "a": a.get("texto") or a.get("accion"),
                               "ok": a.get("id") in hechas} for a in acciones][:300]})
    config.save_cache(HIST, hist[-100:])


def _quitar_aplicadas(acciones, res):
    """Lo aplicado deja de salir en la lista sin tener que volver a revisar."""
    tit = {a.get("id"): a.get("titulo") for a in acciones}
    hechas = {i for i in res.get("hechas") or [] if i in tit}
    if not hechas:
        return
    p = CACHE / "diff.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        d["diferencias"] = [x for x in d.get("diferencias", []) if not (x["id"] in hechas and x["titulo"] == tit[x["id"]])]
        config.save_cache("diff.json", d)


def _revisar(solo, rapida=False):
    from core import diff
    from core.imports import estado_exports
    JOB.update(activo=True, mensajes=[], error=None, fin=None)
    try:
        if config.env("DIXMAX_API_KEY") and config.env("DIXMAX_AUTH_KEY"):
            from core.apply import restaurar_pendientes
            from core.dixmax_api import Dixmax
            restaurar_pendientes(Dixmax(), JOB["mensajes"].append)
        if config.env("ANILIST_TOKEN"):
            from core.apply import restaurar_actividad_anilist
            restaurar_actividad_anilist(JOB["mensajes"].append)
        ex = estado_exports()
        for k in ("dixmax", "letterboxd"):
            e = ex[k]
            JOB["mensajes"].append(f"{k}: {e['carpeta']} ({e['edad']})" if e["carpeta"] else f"{k}: sin export")
        t0 = datetime.now()
        res = diff.compute(progress=lambda m: JOB["mensajes"].append(m), solo=solo, rapida=rapida)
        res["calculado"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        novedades = res.pop("novedades", None)
        config.save_cache("diff.json", res)
        from collections import Counter
        hist = config.cache_json(HIST, [])
        hist.append({"fecha": res["calculado"], "modo": res["modo"], "segundos": round((datetime.now() - t0).total_seconds()),
                     "diferencias": len(res["diferencias"]),
                     "categorias": dict(Counter(d["categoria"] for d in res["diferencias"])),
                     "fuentes": res["fuentes"], "stats": res.get("stats", {}), "novedades": novedades,
                     "detalle": [{"c": d["categoria"], "t": d["titulo"], "d": (d.get("detalle") or "")[:160]}
                                 for d in res["diferencias"][:300]]})
        config.save_cache(HIST, hist[-100:])
        if solo is None:
            lanzar_estadisticas()
    except Exception as e:  # token caducado, export que falta…
        JOB["error"] = str(e)
    finally:
        JOB.update(activo=False, fin=datetime.now().strftime("%H:%M:%S"))


def _dias_permiso_anilist():
    """Días que le quedan al permiso de AniList (None si no hay)."""
    f = config.env("ANILIST_EXPIRA")
    if not (config.env("ANILIST_TOKEN") and f):
        return None
    try:
        return (datetime.strptime(f, "%d/%m/%Y") - datetime.now()).days
    except ValueError:
        return None


ESTAD = {"activo": False, "mensaje": "", "error": None}


def lanzar_estadisticas():
    """Calcula las estadísticas en segundo plano (la primera vez descarga fichas: tarda unos minutos)."""
    if ESTAD["activo"]:
        return
    ESTAD.update(activo=True, mensaje="Empezando…", error=None)

    def correr():
        from core import estadisticas
        try:
            estadisticas.calcular(progress=lambda m: ESTAD.update(mensaje=m))
        except Exception as e:
            ESTAD["error"] = str(e)
        finally:
            ESTAD["activo"] = False
    threading.Thread(target=correr, daemon=True).start()


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
    if config.env("ANILIST_USER"):
        try:
            from core import anilist
            u = anilist.check()
            out["anilist"] = ({"ok": True, "texto": f"Conectado como {u} (permiso hasta el {config.env('ANILIST_EXPIRA') or '?'})"}
                              if u else {"ok": False, "texto": "Falta el permiso: pulsa «Conectar con AniList»"})
        except Exception as e:
            out["anilist"] = {"ok": False, "texto": str(e)}
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
        self.path = self.path.split("?", 1)[0]  # ignora ?v=… (evita caché del navegador)
        LATIDO["t"] = time.time()  # cualquier petición de la página cuenta como actividad
        if self.path == "/anilist":  # vuelta de la autorización de AniList (el permiso viene tras el #)
            return self._send(200, ANILIST_HTML, "text/html; charset=utf-8")
        if self.path in ("/", "/index.html"):
            return self._send(200, INDEX, "text/html; charset=utf-8")
        if self.path == "/api/diff":
            p = CACHE / "diff.json"
            return self._send(200, json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"diferencias": []})
        if self.path == "/api/estado":
            from core.imports import estado_exports
            p = CACHE / "diff.json"
            calc = json.loads(p.read_text(encoding="utf-8")).get("calculado") if p.exists() else None
            return self._send(200, {"exports": estado_exports(), "calculado": calc,
                                    "letterboxd_user": config.env("LETTERBOXD_USER"),
                                    "anilist_user": config.env("ANILIST_USER"),
                                    "anilist_dias": _dias_permiso_anilist(), "trabajo": JOB})
        if self.path in ("/favicon.ico", "/logo.ico"):
            return self._send(200, (WEB / "logo.ico").read_bytes(), "image/x-icon")
        if self.path == "/logo.svg":
            return self._send(200, (WEB / "logo.svg").read_bytes(), "image/svg+xml")
        if self.path == "/api/estadisticas":
            return self._send(200, {"datos": config.cache_json("estadisticas.json", {}), "job": ESTAD})
        if self.path == "/mundo.json":
            return self._send(200, (WEB / "mundo.json").read_bytes(), "application/json; charset=utf-8")
        if self.path == "/api/historial":
            return self._send(200, list(reversed(config.cache_json(HIST, []))))
        if self.path == "/api/run":
            return self._send(200, {k: v for k, v in RUN.items() if k != "log"})
        if self.path == "/api/progreso":
            return self._send(200, JOB)
        if self.path == "/api/config":
            return self._send(200, config.config_publica())
        if self.path == "/api/version":
            from core.actualizar import comprobar
            return self._send(200, comprobar())
        if self.path == "/api/ping":
            return self._send(200, {"ok": True, "android": config.ANDROID})
        if self.path.startswith("/api/descargar/"):  # CSV de Letterboxd (en el móvil se baja a Descargas)
            p = (LOGS / self.path.rsplit("/", 1)[1]).resolve()
            if p.parent == LOGS.resolve() and p.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
                data = p.read_bytes()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
        self._send(404, {"error": "no existe"})

    def do_POST(self):
        LATIDO["t"] = time.time()
        if self.path == "/api/latido":  # la pestaña sigue abierta
            PESTANAS[str(self._body().get("id"))] = time.time()
            return self._send(200, {"ok": True})
        if self.path == "/api/cerrar":  # la pestaña se ha cerrado (o recargado)
            PESTANAS.pop(str(self._body().get("id")), None)
            return self._send(200, {"ok": True})
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
            body = self._body()
            if not RUN["activo"]:
                RUN.update(activo=True, resultado=None, hechos=0, total=len(body.get("acciones", [])))  # sin carreras con la web
                threading.Thread(target=_aplicar, args=(body.get("acciones", []), bool(body.get("simulacion", True))),
                                 daemon=True).start()
            return self._send(200, {"ok": True})
        if self.path == "/api/apagar":
            if JOB["activo"] or RUN["activo"]:
                return self._send(200, {"ok": False, "texto": "Hay una revisión o aplicación en marcha"})
            self._send(200, {"ok": True})
            return apagar()
        if self.path == "/api/version":
            from core.actualizar import comprobar
            return self._send(200, comprobar(forzar=True))
        if self.path == "/api/actualizar":
            if JOB["activo"] or RUN["activo"] or UPD["activo"]:
                return self._send(200, {"ok": False, "texto": "Espera a que termine la revisión o la aplicación en marcha"})
            UPD.update(activo=True, mensajes=[], error=None)
            threading.Thread(target=_actualizar, daemon=True).start()
            return self._send(200, {"ok": True})
        if self.path == "/api/actualizando":
            return self._send(200, UPD)
        if self.path == "/api/anilist_token":
            from core import anilist
            b = self._body()
            try:
                yo = anilist.viewer(token=b.get("access_token"))
            except Exception as e:
                return self._send(200, {"ok": False, "texto": str(e)})
            from datetime import timedelta
            caduca = datetime.now() + timedelta(seconds=int(b.get("expires_in") or 31536000))
            config.guardar_config({"ANILIST_TOKEN": b["access_token"], "ANILIST_USER": yo["name"],
                                   "ANILIST_EXPIRA": caduca.strftime("%d/%m/%Y")})
            return self._send(200, {"ok": True, "usuario": yo["name"]})
        if self.path == "/api/estadisticas":
            lanzar_estadisticas()
            return self._send(200, {"ok": True})
        if self.path == "/api/cancelar":
            RUN["cancelar"] = True
            return self._send(200, {"ok": True})
        if self.path == "/api/abrir":
            p = Path(self._body().get("archivo", ""))
            if p.exists() and LOGS in p.parents and not config.ANDROID:
                os.startfile(p.parent)
            return self._send(200, {"ok": True})
        if self.path == "/api/importar":  # zip de export de Dixmax o Letterboxd, elegido en la web
            from core import movil
            n = int(self.headers.get("Content-Length", 0))
            try:
                return self._send(200, {"ok": True, **movil.importar_export(urllib.parse.unquote(self.headers.get("X-Nombre", "")), self.rfile.read(n))})
            except Exception as e:
                return self._send(200, {"ok": False, "texto": str(e)})
        if self.path == "/api/sincro/recibir":  # el PC pasa al móvil tu configuración y caché (por USB)
            from core import movil
            n = int(self.headers.get("Content-Length", 0))
            try:
                return self._send(200, {"ok": True, **movil.recibir(self.rfile.read(n))})
            except Exception as e:
                return self._send(200, {"ok": False, "texto": str(e)})
        if self.path == "/api/movil":  # PC: instala/actualiza la app del móvil y le pasa los datos (adb)
            from core import movil
            if MOV["activo"]:
                return self._send(200, {"ok": False, "texto": "Ya se está pasando al móvil"})
            MOV.update(activo=True, mensajes=[], error=None, fin=False)
            threading.Thread(target=_movil, daemon=True).start()
            return self._send(200, {"ok": True})
        if self.path == "/api/movil/estado":
            return self._send(200, MOV)
        self._send(404, {"error": "no existe"})


UPD = {"activo": False, "mensajes": [], "error": None}
MOV = {"activo": False, "mensajes": [], "error": None, "fin": False}


def _movil():
    from core import movil
    try:
        movil.pasar_al_movil(MOV["mensajes"].append)
        MOV["fin"] = True
    except Exception as e:
        MOV["error"] = str(e)
    finally:
        MOV["activo"] = False


def _actualizar():
    from core.actualizar import instalar, reiniciar
    try:
        instalar(UPD["mensajes"].append)
        if config.ANDROID:  # la página abre el instalador de Android con el APK descargado
            UPD.update(activo=False, apk=True)
            return
        reiniciar(SRV["srv"].server_address[1])
        apagar()
    except Exception as e:
        UPD.update(activo=False, error=str(e))


LATIDO = {"t": time.time() + 50}  # al arrancar da tiempo a que el navegador abra la página
PESTANAS = {}  # id de pestaña -> último latido
GRACIA_S = 10  # tras cerrar la última pestaña espera esto (por si era una recarga) y se apaga
PERDIDA_S = 150  # pestaña sin latidos tanto tiempo (navegador cerrado de golpe, PC suspendido…) = cerrada
SRV = {}


def apagar():
    threading.Thread(target=SRV["srv"].shutdown, daemon=True).start()


def _vigilante():
    """Se apaga solo al cerrar la pestaña. Nunca a mitad de una revisión o aplicación: espera a que acabe."""
    while True:
        time.sleep(2)
        ahora = time.time()
        for k, t in list(PESTANAS.items()):
            if ahora - t > PERDIDA_S:
                PESTANAS.pop(k, None)
        ocupado = JOB["activo"] or RUN["activo"] or ESTAD["activo"]
        if not PESTANAS and not ocupado and ahora - LATIDO["t"] > GRACIA_S:
            print("Pestaña cerrada: apagando Tri-Sync")
            apagar()
            return


def serve(port=8765, auto_apagar=True):
    """auto_apagar: en el PC se apaga al cerrar la pestaña; en el móvil vive lo que viva la app."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    SRV["srv"] = srv
    if auto_apagar:
        threading.Thread(target=_vigilante, daemon=True).start()
    print(f"Web local en http://127.0.0.1:{port}")
    srv.serve_forever()
