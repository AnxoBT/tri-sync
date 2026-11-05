"""Escritura en Dixmax/PlayMax con tu sesión (API interna, no oficial).

Necesita en .env:
  DIXMAX_COOKIE   cabecera Cookie completa de playmax.mx (F12 > Network > cualquier petición > Request Headers > cookie)
  DIXMAX_API_KEY  el código que aparece en las URLs /api/json/.../v1/<CLAVE>/ de esas mismas peticiones
"""
import json
from urllib.parse import urlencode

from .config import env
from .http import call

BASE = "https://playmax.mx"
TIPO = {"following": 1, "pending": 2, "favorite": 3, "viewed": 4, "abandoned": 5}


class DixmaxError(Exception):
    pass


class Dixmax:
    def __init__(self):
        self.cookie = env("DIXMAX_COOKIE")
        self.key = env("DIXMAX_API_KEY")
        if not self.cookie or not self.key:
            raise DixmaxError("Faltan DIXMAX_COOKIE y/o DIXMAX_API_KEY en .env (ver README)")
        self.h = {"Cookie": self.cookie, "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/"}

    def _api(self, kind, name, version, params=None, post=None):
        url = f"{BASE}/api/json/{kind}/{name}/{version}/{self.key}/?&" + urlencode(params or {})
        if post is not None:
            h = {**self.h, "Content-Type": "application/x-www-form-urlencoded"}
            from urllib.request import Request, urlopen
            with urlopen(Request(url, data=urlencode(post).encode(), method="POST", headers=h), timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        return call("GET", url, headers=self.h)

    def dates(self, ficha_id=None, episode_id=None):
        p = {"fichaId": ficha_id} if ficha_id else {"episodeId": episode_id}
        s, d = self._api("get", "ficha_user_dates", "v1", p)
        if s != 200 or not isinstance(d, dict) or "result" not in d:
            raise DixmaxError(f"Sesión de Dixmax no válida o caducada ({s}). Renueva DIXMAX_COOKIE.")
        return d["result"]

    def check(self, ficha_prueba=180):
        self.dates(ficha_prueba)
        return True

    def set_mark(self, ficha_id, mark):
        """mark: viewed/pending/favorite/abandoned/following. No hace nada si ya la tiene
        (en Dixmax volver a pulsar la misma marca la QUITA)."""
        actual = self.dates(ficha_id).get("marked") or ""
        if actual == mark:
            return "ya estaba"
        s, _ = call("GET", f"{BASE}/data.php?mode=marcar_ficha&tipo={TIPO[mark]}&ficha={ficha_id}", headers=self.h)
        return "ok" if s == 200 else f"error {s}"

    def rate(self, ficha_id, value10):
        s, _ = call("GET", f"{BASE}/data.php?mode=valorar_ficha&value={value10}&ficha={ficha_id}", headers=self.h)
        return "ok" if s == 200 else f"error {s}"

    def set_dates(self, entries):
        """entries: [{fichaId|episodeId, type: mark|rating|viewed|all, unix}]"""
        s, d = self._api("set", "ficha_user_dates", "v1", {"debug": 1}, post={"dates": json.dumps(entries)})
        return "ok" if s == 200 else f"error {s}"

    def mark_episode(self, episode_id):
        s, _ = self._api("set", "mark_episode", "v1.1", {"episodeId": episode_id, "forceMark": 1})
        return "ok" if s == 200 else f"error {s}"
