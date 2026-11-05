"""Dixmax/PlayMax mediante su API oficial v2 (https://playmax.mx/documentacion_api.php).

Necesita en Configuración / .env:
  DIXMAX_API_KEY   apiKey de tu app (playmax.mx/tusapps.php > Añadir App)
  DIXMAX_AUTH_KEY  authKey de tu usuario (Panel de Control > Aplicaciones autorizadas)
Límite de la API: 20 peticiones cada 10 s por IP (el cliente espera lo necesario).
"""
import time
from urllib.parse import urlencode

from .config import env
from .http import call

BASE = "https://playmax.mx/api/json"
MARK = {"following": 1, "pending": 2, "favorite": 3, "viewed": 4, "abandoned": 5}


class DixmaxError(Exception):
    pass


class Dixmax:
    def __init__(self):
        self.key = env("DIXMAX_API_KEY")
        self.auth = env("DIXMAX_AUTH_KEY")
        if not self.key or not self.auth:
            raise DixmaxError("Faltan DIXMAX_API_KEY y/o DIXMAX_AUTH_KEY (pestaña Configuración)")
        self._t = []

    def _api(self, kind, page, version, params=None, post=None):
        # respetar 20 peticiones / 10 s
        now = time.time()
        self._t = [t for t in self._t if now - t < 10]
        if len(self._t) >= 18:
            time.sleep(10 - (now - self._t[0]) + 0.2)
        self._t.append(time.time())
        url = f"{BASE}/{kind}/{page}/{version}/{self.key}/{self.auth}/"
        if params:
            url += "?" + urlencode(params, doseq=True)
        if post is not None:
            from urllib.request import Request, urlopen
            import json
            data = urlencode(post, doseq=True).encode()
            with urlopen(Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
        else:
            s, d = call("GET", url, delay=0)
            if not isinstance(d, dict):
                raise DixmaxError(f"Respuesta inesperada de Dixmax ({s})")
        err = d.get("error", {})
        if err.get("code"):
            raise DixmaxError(f"Dixmax: {err.get('message')} (código {err.get('code')})")
        return d.get("result")

    # ---------- lectura ----------
    def check(self):
        u = self._api("get", "user_data", "v1")
        return u.get("name") if isinstance(u, dict) else True

    def my_fichas(self):
        """{'movie': {'viewed': [...], 'pending': [...]...}, 'series': {...}, ...} con user.marked y user.rating."""
        return self._api("get", "my_fichas", "v1.1", {"disableFolders": "true"})

    def ficha(self, ficha_id):
        return self._api("get", "ficha", "v1.2", {"fichaId": ficha_id, "showEpisodeSynopsis": "false"})

    # ---------- escritura ----------
    def set_mark(self, ficha_id, mark):
        """mark: viewed/pending/favorite/abandoned/following. forceMark=1: nunca desmarca."""
        self._api("set", "mark_ficha", "v1", {"fichaId": ficha_id, "mark": MARK[mark], "forceMark": 1})
        return "ok"

    def rate(self, ficha_id, value10):
        self._api("set", "rating_ficha", "v1.1", {"fichaId": ficha_id, "rating": value10})
        return "ok"

    def mark_episodes(self, episode_ids):
        self._api("set", "mark_episodes", "v1", post={"episodesId[]": list(episode_ids), "forceMark": 1})
        return "ok"
