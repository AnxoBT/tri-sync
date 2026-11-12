"""API oficial de Letterboxd (OAuth2, v0). Opcional: sin ella, lo de Letterboxd se aplica con su importador CSV.

La API se pide a Letterboxd (letterboxd.com/api-beta): te dan un client_id y un client_secret, y registras como
dirección de vuelta http://127.0.0.1:8765/letterboxd. Luego, en Configuración → «Conectar con Letterboxd»,
autorizas la app (flujo Authorization Code; nunca se pide tu contraseña).

Endpoints usados (https://api.letterboxd.com/api/v0, documentación en api-docs.letterboxd.com):
  GET  /films?filmId=tmdb:ID…        → LID de Letterboxd de cada película (hasta 100 por petición)
  POST /log-entries                  → entrada del diario con fecha, nota y like
  PATCH /me/rate/{lid}               → nota sin entrada de diario
  PATCH /me/watch/{lid}              → vista, sin fecha ni nota
  PATCH /me/watchlist/{lid}          → añadir o quitar de la watchlist
"""
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

API = "https://api.letterboxd.com/api/v0"
REDIRECT = "http://127.0.0.1:8765/letterboxd"  # la misma en el PC y en el móvil (mismo puerto)
SCOPES = "content:modify profile:private:view oauth:refresh"
_ESTADO = {"state": None}
_LID = {}  # tmdb -> LID (caché del proceso)


class LetterboxdError(Exception):
    pass


def configurada():
    """Hay client_id y client_secret (la app de la API)."""
    return bool(config.env("LETTERBOXD_CLIENT_ID") and config.env("LETTERBOXD_CLIENT_SECRET"))


def conectada():
    return configurada() and bool(config.env("LETTERBOXD_TOKEN"))


def url_autorizar():
    _ESTADO["state"] = secrets.token_urlsafe(24)
    q = urllib.parse.urlencode({"response_type": "code", "client_id": config.env("LETTERBOXD_CLIENT_ID"),
                                "redirect_uri": REDIRECT, "scope": SCOPES, "state": _ESTADO["state"]})
    return f"{API}/auth/authorize?{q}"


def _token_form(campos):
    datos = urllib.parse.urlencode({**campos, "client_id": config.env("LETTERBOXD_CLIENT_ID"),
                                    "client_secret": config.env("LETTERBOXD_CLIENT_SECRET")}).encode()
    req = urllib.request.Request(f"{API}/auth/token", data=datos, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise LetterboxdError(f"Letterboxd no dio el permiso ({e.code}): {e.read().decode('utf-8', 'replace')[:200]}")
    config.guardar_config({"LETTERBOXD_TOKEN": t["access_token"],
                           "LETTERBOXD_REFRESH": t.get("refresh_token") or config.env("LETTERBOXD_REFRESH"),
                           "LETTERBOXD_EXPIRA": str(int(time.time() + int(t.get("expires_in") or 3600)))})
    return t


def recibir_codigo(code, state):
    """Vuelta de la autorización (GET /letterboxd?code=…&state=…): cambia el código por el permiso."""
    if not state or state != _ESTADO["state"]:
        raise LetterboxdError("La respuesta de Letterboxd no coincide con la petición (vuelve a pulsar Conectar)")
    _ESTADO["state"] = None
    _token_form({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT})
    yo = _call("GET", "/me")
    nombre = ((yo or {}).get("member") or {}).get("username") or ""
    if nombre:
        config.guardar_config({"LETTERBOXD_USER": nombre})
    return nombre


def _token():
    if not conectada():
        raise LetterboxdError("Letterboxd no está conectado por API (Configuración → Conectar con Letterboxd)")
    if time.time() > float(config.env("LETTERBOXD_EXPIRA") or 0) - 60:  # renovar antes de que caduque
        if not config.env("LETTERBOXD_REFRESH"):
            raise LetterboxdError("El permiso de Letterboxd ha caducado: vuelve a conectar")
        _token_form({"grant_type": "refresh_token", "refresh_token": config.env("LETTERBOXD_REFRESH")})
    return config.env("LETTERBOXD_TOKEN")


def _call(method, path, body=None, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    h = {"Authorization": f"Bearer {_token()}", "Accept": "application/json", "User-Agent": "Tri-Sync"}
    datos = None
    if body is not None:
        datos = json.dumps(body).encode()
        h["Content-Type"] = "application/json; charset=UTF-8"
    for intento in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=datos, method=method, headers=h), timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 2:  # límite de peticiones: espera lo que diga
                time.sleep(int(e.headers.get("Retry-After") or 5))
                continue
            raise LetterboxdError(f"Letterboxd {method} {path}: {e.code} {e.read().decode('utf-8', 'replace')[:200]}")


def lids(tmdbs):
    """{tmdb: LID} de Letterboxd, de 100 en 100."""
    faltan = [str(t) for t in dict.fromkeys(tmdbs) if t and str(t) not in _LID]
    for i in range(0, len(faltan), 100):
        trozo = faltan[i:i + 100]
        d = _call("GET", "/films", params={"filmId": [f"tmdb:{t}" for t in trozo], "perPage": 100,
                                           "excludeMemberFilmRelationships": "true"})
        for f in (d or {}).get("items", []):
            tm = next((l.get("id") for l in f.get("links", []) if l.get("type") == "tmdb"), None)
            if tm:
                _LID[str(tm)] = f["id"]
    return {str(t): _LID.get(str(t)) for t in tmdbs if t}


def _lid(tmdb):
    lid = lids([tmdb]).get(str(tmdb))
    if not lid:
        raise LetterboxdError(f"Letterboxd no tiene la película con TMDB {tmdb}")
    return lid


def registrar(tmdb, fecha=None, estrellas=None, like=False, rewatch=False):
    """Entrada del diario (fecha AAAA-MM-DD). Sin fecha, solo la nota (y vista)."""
    lid = _lid(tmdb)
    if not fecha:
        if estrellas:
            return _call("PATCH", f"/me/rate/{lid}", {"rating": estrellas})
        return _call("PATCH", f"/me/watch/{lid}", {"watched": True})
    body = {"filmId": lid, "diaryDetails": {"diaryDate": fecha[:10], "rewatch": bool(rewatch)}, "like": bool(like)}
    if estrellas:
        body["rating"] = estrellas
    return _call("POST", "/log-entries", body)


def nota(tmdb, estrellas):
    return _call("PATCH", f"/me/rate/{_lid(tmdb)}", {"rating": estrellas or None})


def watchlist(tmdb, dentro=True):
    return _call("PATCH", f"/me/watchlist/{_lid(tmdb)}", {"inWatchlist": bool(dentro)})


def check():
    """Usuario conectado (o error)."""
    yo = _call("GET", "/me")
    return ((yo or {}).get("member") or {}).get("username")
