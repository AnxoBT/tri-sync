"""Servidor web local (solo librería estándar). Solo escucha en 127.0.0.1."""
import hmac
import html
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
    if (r.ok) setTimeout(() => { window.close(); location.href = '/'; }, 1500);  // en la app (iPhone) no hay pestaña: vuelve
  });
</script>""".encode()

PAGINA_VUELTA = """<!doctype html><meta charset="utf-8"><title>Tri-Sync</title>
<body style="font:16px system-ui;background:#0f1218;color:#e6e6e6;display:grid;place-items:center;height:90vh;padding:20px;text-align:center">
<div>{txt}<p><a href="/" style="color:#3fb0ff">Volver a Tri-Sync</a></p></div>"""

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
        if config.dixmax_api():
            from core.apply import restaurar_pendientes
            from core.dixmax_api import Dixmax
            restaurar_pendientes(Dixmax(), JOB["mensajes"].append)
        if config.env("ANILIST_TOKEN"):
            from core.apply import restaurar_actividad_anilist
            restaurar_actividad_anilist(JOB["mensajes"].append)
        ex, ap = estado_exports(), config.apps()
        for k in (k for k in ("dixmax", "letterboxd") if ap[k]):
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
    ap, out = config.apps(), {}
    ex = estado_exports()
    if not config.MOVIL:
        out["carpetas"] = {"ok": all("no existe" not in c for c in ex["carpetas"]), "texto": " · ".join(ex["carpetas"])}
    for k, nombre, max_h, app in (("dixmax", "export Dixmax", 24 * 30, "dixmax"), ("letterboxd", "export Letterboxd", 24, "letterboxd")):
        if not ap[app]:
            continue
        e = ex[k]
        if not e["carpeta"]:
            pre = "playmax-userdata-" if k == "dixmax" else "letterboxd-"
            opcional = k == "dixmax" and config.dixmax_api()
            out[nombre] = {"ok": bool(opcional), "aviso": bool(opcional),
                           "texto": ("No hay (opcional: la API lo lee todo)" if opcional else
                                     f"No encontrado: descárgalo e impórtalo (zip que empiece por '{pre}')")}
            continue
        txt = (f"{e['carpeta']} ({e['tipo']}) · descargado {e['fecha']} ({e['edad']}) · archivos OK: {', '.join(e['archivos'])}")
        if e["otros"]:
            txt += f" · hay {e['otros']} más antiguos (se ignoran)"
        aviso = e["horas"] > max_h
        if aviso:
            txt += " · ⚠ antiguo, descarga uno nuevo" if k == "letterboxd" else " · ⚠ fechas poco actualizadas"
        out[nombre] = {"ok": True, "aviso": aviso, "texto": txt}
    if ap["serializd"]:
        try:
            from core.serializd import Serializd
            out["serializd"] = {"ok": True, "texto": f"Conectado como {Serializd().check()}"}
        except Exception as e:
            out["serializd"] = {"ok": False, "texto": str(e)}
    if ap["anilist"]:
        try:
            from core import anilist
            u = anilist.check()
            out["anilist"] = ({"ok": True, "texto": f"Conectado como {u} (permiso hasta el {config.env('ANILIST_EXPIRA') or '?'})"}
                              if u else {"ok": False, "texto": "Falta el permiso: pulsa «Conectar con AniList»"})
        except Exception as e:
            out["anilist"] = {"ok": False, "texto": str(e)}
    from core import letterboxd_api
    if letterboxd_api.conectada():
        try:
            out["letterboxd API"] = {"ok": True, "texto": f"Conectado como {letterboxd_api.check()} (los cambios se aplican directamente)"}
        except Exception as e:
            out["letterboxd API"] = {"ok": False, "texto": str(e)}
    if config.dixmax_api():
        try:
            from core.dixmax_api import Dixmax
            Dixmax().check()
            out["dixmax"] = {"ok": True, "texto": "API oficial conectada (se pueden aplicar cambios)"}
        except Exception as e:
            out["dixmax"] = {"ok": False, "texto": str(e)}
    return out


LOCALES = ("127.0.0.1", "localhost")
# Android: otras apps del móvil también llegan a 127.0.0.1 (y sin Origin) → clave secreta por arranque
# (TRISYNC_SECRETO, la pone MainActivity). La pantalla de la app la recibe en /?k= y la guarda en una cookie;
# el PC, al pasar datos por USB, la lee con adb. Sin clave solo: el ping, y las vueltas de Letterboxd (protegida
# por "state") y de AniList (solo vale 10 min tras pulsar «Conectar con AniList», y una vez), que llegan desde
# el navegador de fuera de la app.
SECRETO = os.environ.get("TRISYNC_SECRETO", "")
SIN_CLAVE = {"/api/ping", "/letterboxd", "/anilist", "/api/anilist_token"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ajena(self, escribe):
        """Petición que no viene de Tri-Sync: se rechaza.
        - Host distinto de 127.0.0.1/localhost: una web que se hace pasar por tu equipo (DNS rebinding).
        - Al cambiar algo (POST), un Origin de otra web: cualquier página abierta en el navegador puede mandar
          peticiones a 127.0.0.1 (CSRF). Sin Origin = no es un navegador (el PC al pasar datos al móvil por adb)."""
        if (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]") not in LOCALES:
            return True
        if SECRETO and self.path.split("?", 1)[0] not in SIN_CLAVE:
            galleta = next((c.split("=", 1)[1] for c in (self.headers.get("Cookie") or "").split("; ")
                            if c.startswith("trisync=")), "")
            if not hmac.compare_digest((galleta or self.headers.get("X-TriSync-Clave", "")).encode(), SECRETO.encode()):
                return True
        origen = self.headers.get("Origin")
        if escribe and origen is not None:
            u = urllib.parse.urlsplit(origen)
            return u.scheme != "http" or u.hostname not in LOCALES or u.port != self.server.server_address[1]
        return False

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        return json.loads(self._crudo or b"{}")

    def do_GET(self):
        if SECRETO and self.path.startswith("/?"):  # la app abre /?k=<clave>: se guarda en una cookie
            k = (urllib.parse.parse_qs(self.path[2:]).get("k") or [""])[0]
            if hmac.compare_digest(k.encode(), SECRETO.encode()):
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"trisync={SECRETO}; Path=/; HttpOnly; SameSite=Strict")
                self.send_header("Content-Length", "0")
                return self.end_headers()
        if self._ajena(False):
            return self._send(403, {"error": "petición ajena a Tri-Sync"})
        consulta = urllib.parse.parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        self.path = self.path.split("?", 1)[0]  # ignora ?v=… (evita caché del navegador)
        if self.path == "/letterboxd":  # vuelta de la autorización de la API de Letterboxd (?code=…&state=…)
            from core import letterboxd_api
            try:
                u = letterboxd_api.recibir_codigo((consulta.get("code") or [""])[0], (consulta.get("state") or [""])[0])
                txt = f"✓ Conectado con Letterboxd{' como <b>' + html.escape(u) + '</b>' if u else ''}. Ya puedes volver a Tri-Sync."
            except Exception as e:
                txt = f"No se pudo conectar con Letterboxd: {html.escape(str(e))}"
            if config.env("IDIOMA") == "en":
                txt = txt.replace("Conectado con Letterboxd", "Connected to Letterboxd").replace(" como ", " as ").replace(
                    "Ya puedes volver a Tri-Sync.", "You can go back to Tri-Sync now.").replace("No se pudo conectar con Letterboxd", "Couldn't connect to Letterboxd")
            return self._send(200, PAGINA_VUELTA.replace("{txt}", txt).replace("Volver a Tri-Sync", "Back to Tri-Sync" if config.env("IDIOMA") == "en" else "Volver a Tri-Sync").encode(), "text/html; charset=utf-8")
        LATIDO["t"] = time.time()  # cualquier petición de la página cuenta como actividad
        if self.path == "/anilist":  # vuelta de la autorización de AniList (el permiso viene tras el #)
            pagina = ANILIST_HTML
            if config.env("IDIOMA") == "en":
                for es_, en_ in (("Guardando el permiso de AniList…", "Saving the AniList permission…"),
                                 ("AniList no ha dado permiso. Cierra esta pestaña y vuelve a probar.", "AniList didn't give permission. Close this tab and try again."),
                                 ("✓ Conectado con AniList como ", "✓ Connected to AniList as "), (". Ya puedes cerrar esta pestaña.", ". You can close this tab now.")):
                    pagina = pagina.replace(es_.encode(), en_.encode())
            return self._send(200, pagina, "text/html; charset=utf-8")
        if self.path in ("/", "/index.html"):
            return self._send(200, INDEX, "text/html; charset=utf-8")
        if self.path == "/api/diff":
            p = CACHE / "diff.json"
            return self._send(200, json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"diferencias": []})
        if self.path == "/api/estado":
            from core import letterboxd_api
            from core.imports import estado_exports
            p = CACHE / "diff.json"
            calc = json.loads(p.read_text(encoding="utf-8")).get("calculado") if p.exists() else None
            return self._send(200, {"exports": estado_exports(), "calculado": calc, "apps": config.apps(),
                                    "dixmax_api": config.dixmax_api(), "letterboxd_api": letterboxd_api.conectada(),
                                    "letterboxd_user": config.env("LETTERBOXD_USER"),
                                    "anilist_user": config.env("ANILIST_USER"),
                                    "anilist_dias": _dias_permiso_anilist(), "trabajo": JOB})
        if self.path in ("/favicon.ico", "/logo.ico"):
            return self._send(200, (WEB / "logo.ico").read_bytes(), "image/x-icon")
        if self.path == "/logo.svg":
            return self._send(200, (WEB / "logo.svg").read_bytes(), "image/svg+xml")
        if self.path == "/api/estadisticas":
            return self._send(200, {"datos": config.cache_json("estadisticas.json", {}), "job": ESTAD})
        if self.path == "/i18n_en.json":  # traducciones al inglés (la web traduce al mostrar)
            return self._send(200, (WEB / "i18n_en.json").read_bytes(), "application/json; charset=utf-8")
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
            return self._send(200, {"ok": True, "android": config.ANDROID, "ios": config.IOS, "movil": config.MOVIL})
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
        # se lee siempre todo lo que manda, también si se va a rechazar: contestar sin leerlo hace que Windows corte
        # la conexión de golpe (el navegador vería un error en vez de la respuesta)
        self._crudo = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        if self._ajena(True):
            return self._send(403, {"error": "petición ajena a Tri-Sync"})
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
                JOB.update(activo=True, mensajes=[], error=None, fin=None)
                threading.Thread(target=_revisar, args=(b.get("solo"), b.get("modo") == "rapida"), daemon=True).start()
            return self._send(200, {"ok": True})
        if self.path == "/api/config":
            config.guardar_config(self._body())
            return self._send(200, {"ok": True, "config": config.config_publica()})
        if self.path == "/api/probar":
            return self._send(200, _probar())
        if self.path == "/api/app/quitar":
            config.quitar_app(self._body().get("app"))
            return self._send(200, {"ok": True, "apps": config.apps()})
        if self.path == "/api/letterboxd/conectar":
            from core import letterboxd_api
            if not letterboxd_api.configurada():
                return self._send(200, {"ok": False, "texto": "Pon antes el client_id y el client_secret de tu app de la API de Letterboxd"})
            return self._send(200, {"ok": True, "url": letterboxd_api.url_autorizar()})
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
        if self.path == "/api/anilist/conectar":  # el botón «Conectar con AniList»: se espera su vuelta 10 min
            ANILIST_PEDIDO["t"] = time.time()
            return self._send(200, {"ok": True})
        if self.path == "/api/anilist_token":
            # Una web cualquiera podría abrir /anilist#access_token=<el suyo> y quedarse con lo que subes a AniList:
            # solo vale si acabas de pulsar «Conectar con AniList» aquí
            if time.time() - ANILIST_PEDIDO["t"] > 600:
                return self._send(200, {"ok": False, "texto": "Pulsa «Conectar con AniList» en Tri-Sync y vuelve a autorizar"})
            ANILIST_PEDIDO["t"] = 0
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
            p = Path(str(self._body().get("archivo", ""))).resolve()
            if p.is_file() and p.parent == LOGS.resolve() and not config.MOVIL:
                os.startfile(LOGS)
            return self._send(200, {"ok": True})
        if self.path == "/api/abrir_url":  # iPhone: enlaces de fuera (Dixmax, Letterboxd…) en Safari
            url = str(self._body().get("url", ""))
            if url.startswith("https://") and config.GANCHOS["abrir_url"]:
                config.GANCHOS["abrir_url"](url)
            return self._send(200, {"ok": True})
        if self.path == "/api/compartir":  # iPhone: el CSV de Letterboxd, con el menú de compartir (Guardar en Archivos…)
            p = (LOGS / Path(str(self._body().get("archivo", ""))).name).resolve()
            if p.parent == LOGS.resolve() and p.is_file() and config.GANCHOS["compartir"]:
                config.GANCHOS["compartir"](str(p))
            return self._send(200, {"ok": True})
        if self.path == "/api/importar":  # zip de export de Dixmax o Letterboxd, elegido en la web
            from core import movil
            try:
                return self._send(200, {"ok": True, **movil.importar_export(urllib.parse.unquote(self.headers.get("X-Nombre", "")), self._crudo,
                                                                             self.headers.get("X-Fecha", ""))})
            except Exception as e:
                return self._send(200, {"ok": False, "texto": str(e)})
        if self.path == "/api/sincro/recibir":  # el PC pasa al móvil tu configuración y caché (por USB)
            if not config.MOVIL:
                return self._send(403, {"error": "solo en el móvil"})
            from core import movil
            try:
                return self._send(200, {"ok": True, **movil.recibir(self._crudo)})
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
ANILIST_PEDIDO = {"t": 0}
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
        ocupado = JOB["activo"] or RUN["activo"] or ESTAD["activo"] or MOV["activo"] or UPD["activo"]
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
