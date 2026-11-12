"""Cliente de la API interna (no oficial) de Serializd."""
import threading
from concurrent.futures import ThreadPoolExecutor

from .config import CACHE, cache_json, env, save_cache
from .http import call

API = "https://serializddesktop.onrender.com/api"
DIARY_CACHE = "sz_diary.json"
LISTS = {"watched": "watchedpage_v2", "watchlist": "watchlistpage_v2",
         "watching": "currently_watching_page", "dropped": "dropped_shows_page"}


class TokenError(Exception):
    pass


class Serializd:
    def __init__(self, token=None, user=None):
        self.token = token or env("SERIALIZD_TOKEN")
        self.user = user or env("SERIALIZD_USER")
        self.headers = {"Origin": "https://www.serializd.com", "Referer": "https://www.serializd.com/",
                        "X-Requested-With": "serializd_vercel",
                        "Cookie": f"tvproject_credentials={self.token}"}

    def _call(self, method, path, body=None):
        return call(method, API + path, body, self.headers)

    def check(self):
        if not self.token:
            raise TokenError("Falta SERIALIZD_TOKEN en .env")
        s, d = self._call("POST", "/validateauthtoken", {"token": self.token})
        if s != 200 or not isinstance(d, dict) or not d.get("isValid"):
            raise TokenError("El token de Serializd ha caducado: copia de nuevo la cookie tvproject_credentials al .env")
        self.user = self.user or d.get("username")
        return self.user

    # ---------- lectura ----------
    def _diary_page(self, p):
        return self._call("GET", f"/user/{self.user}/diary?page={p}")[1]

    def diary(self, rapida=False):
        """Diario completo. rapida=True: solo baja las páginas nuevas y reutiliza la caché
        (no detecta entradas borradas ni con fecha antigua añadidas desde fuera de la herramienta)."""
        cache = cache_json(DIARY_CACHE)
        if rapida and cache.get("user") == self.user and cache.get("entries"):
            known = {e["id"]: e for e in cache["entries"]}
            p, pages, nuevas = 1, None, 0
            while True:
                d = self._diary_page(p)
                pages = d["totalPages"]
                fresh = [e for e in d["reviews"] if e["id"] not in known]
                for e in d["reviews"]:
                    known[e["id"]] = e
                nuevas += len(fresh)
                if (not fresh and p >= 2) or p >= pages:
                    break
                p += 1
            out = list(known.values())
        else:
            d = self._diary_page(1)
            pages = d["totalPages"]
            out = list(d["reviews"])
            with ThreadPoolExecutor(10) as ex:
                for dd in ex.map(self._diary_page, range(2, pages + 1)):
                    out += dd["reviews"]
        save_cache(DIARY_CACHE, {"user": self.user, "entries": out})
        return out

    @staticmethod
    def invalidar_diario():
        """Tras escribir en Serializd: la siguiente revisión rápida vuelve a bajar el diario entero."""
        p = CACHE / DIARY_CACHE
        if p.exists():
            p.unlink()

    def list_items(self, name):
        def pagina(p):
            s, d = self._call("GET", f"/user/{self.user}/{LISTS[name]}/{p}?sort_by=date_added_desc&filters=%7B%7D")
            if s != 200 or not isinstance(d, dict):
                raise RuntimeError(f"Serializd ({name}, página {p}): {s}")
            return d
        primera = pagina(1)
        paginas = [primera]
        total = primera.get("totalPages", 1)
        if total > 1:  # el resto de páginas a la vez
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(6) as ex:
                paginas += list(ex.map(pagina, range(2, total + 1)))
        items = {}
        for d in paginas:
            for it in d.get("items", []):
                items[it["showId"]] = {"name": it.get("showName"), "seasons": it.get("seasonIds") or [],
                                       "added": it.get("dateAdded")}
        return items

    def ratings(self):
        """Notas de serie (registros de serie y valoraciones sueltas).
        Se piden filtrando por cada nota (1-10): la paginación general de Serializd se salta entradas."""
        from urllib.parse import quote
        out = {}

        def bucket(rating):
            cur = cur2 = None
            for _ in range(200):
                q = (f"/user/{self.user}/reviewspage_v3?sort_by=date_added_desc&include_ratings=true"
                     f"&include_target=shows&rating={rating}")
                if cur:
                    q += f"&cursor={quote(str(cur))}"
                if cur2:
                    q += f"&secondary_cursor={quote(str(cur2))}"
                s, d = self._call("GET", q)
                items = d.get("items", []) if isinstance(d, dict) else []
                for x in items:
                    out[x["id"]] = x
                nxt = (d.get("nextCursor"), d.get("secondaryNextCursor")) if isinstance(d, dict) else (None, None)
                if not items or nxt == (None, None) or nxt == (cur, cur2):
                    break
                cur, cur2 = nxt

        with ThreadPoolExecutor(10) as ex:
            list(ex.map(bucket, range(1, 11)))
        return [x for x in out.values() if x.get("seasonId") is None and x.get("episodeNumber") is None]

    # Caché en memoria (thread-safe); se guarda en disco con flush()
    _lock = threading.Lock()
    _shows = None
    _seasons = None

    def _load_caches(self):
        with self._lock:
            if Serializd._shows is None:
                Serializd._shows = cache_json("sz_shows.json")
                Serializd._seasons = cache_json("sz_seasons.json")

    def flush(self):
        with self._lock:
            if Serializd._shows is not None:
                save_cache("sz_shows.json", Serializd._shows)
                save_cache("sz_seasons.json", Serializd._seasons)

    def show(self, tmdb):
        self._load_caches()
        k = str(tmdb)
        if k not in Serializd._shows:
            s, d = self._call("GET", f"/show/{tmdb}")
            Serializd._shows[k] = ({"name": d.get("name"), "seasons": {str(x["seasonNumber"]): x["id"] for x in d.get("seasons", [])}}
                                   if s == 200 and isinstance(d, dict) else None)
        return Serializd._shows[k]

    def estreno(self, tmdb):
        """Fecha de estreno (AAAA-MM-DD) o None si aún no tiene. En caché; lo no estrenado se vuelve a mirar cada día."""
        import time
        c = cache_json("sz_estrenos.json", {})
        k, hoy = str(tmdb), time.strftime("%Y-%m-%d")
        e = c.get(k)
        if not e or (not e.get("fecha") or e["fecha"] > hoy) and time.time() - e.get("t", 0) > 86400:
            s, d = self._call("GET", f"/show/{tmdb}")
            e = c[k] = {"fecha": d.get("premiereDate") if s == 200 and isinstance(d, dict) else None, "t": int(time.time())}
            save_cache("sz_estrenos.json", c)
        return e.get("fecha")

    def season(self, tmdb, number):
        self._load_caches()
        k = f"{tmdb}-{number}"
        if k not in Serializd._seasons:
            s, d = self._call("GET", f"/show/{tmdb}/season/{number}")
            Serializd._seasons[k] = ({"id": d.get("seasonId"), "episodes": {str(e["episodeNumber"]): e.get("name") for e in d.get("episodes", [])}}
                                     if s == 200 and isinstance(d, dict) else None)
        return Serializd._seasons[k]

    # ---------- escritura (fase 2) ----------
    def add_diary(self, show, season_id, episode, backdate, rating=0, is_log=True, like=False):
        body = {"show_id": show, "backdate": backdate, "review_text": "", "rating": rating,
                "contains_spoiler": False, "is_log": is_log, "is_rewatch": False, "tags": [],
                "allows_comments": True, "like": like}
        if season_id is not None:
            body["season_id"] = season_id
        if episode is not None:
            body["episode_number"] = episode
        return self._call("POST", "/show/reviews/add", body)

    def quitar(self, show, lista, seasons=None):
        """Saca la serie de una lista de Serializd (watched y watchlist van por temporadas)."""
        if lista == "watching":
            return self._call("POST", "/currently_watching/remove", {"show_id": show})
        if lista == "dropped":
            return self._call("POST", "/dropped_shows/remove", {"show_id": show})
        if lista == "watched":
            return self._call("POST", "/watched/remove_v2", {"show_id": show, "season_ids": seasons or []})
        if lista == "watchlist":
            return self._call("POST", "/watchlist/remove_v2", {"show_id": show, "season_ids": seasons or [], "async": False})
        raise ValueError(lista)

    def set_status(self, show, status, quitar=None):
        """status: watching / watchlist / dropped / watched (todas las temporadas).
        Serializd deja tener una serie en varias listas a la vez (vista y viendo, abandonada y vista…): con quitar
        ({lista: temporadas}) se saca de las demás para que tenga un solo estado, el de Dixmax."""
        for lista, seasons in (quitar or {}).items():
            if lista != status:
                s, r = self.quitar(show, lista, seasons)
                if s != 200:
                    return s, r
        if status in (quitar or {}):  # ya estaba en su lista: solo había que quitarla de las otras
            return 200, "ya estaba"
        return self._set_status(show, status)

    def _set_status(self, show, status):
        if status == "watching":
            return self._call("POST", "/currently_watching", {"show_id": show})
        if status == "dropped":
            return self._call("POST", "/dropped_shows", {"show_id": show})
        info = self.show(show) or {"seasons": {}}
        ids = [v for k, v in info["seasons"].items() if int(k) >= 1]
        if status == "watchlist":
            return self._call("POST", "/watchlist_v2", {"show_id": show, "season_ids": ids})
        if status == "watched":
            return self._call("POST", "/watched_v2", {"show_id": show, "season_ids": ids, "async": False})
        raise ValueError(status)

    def update_review(self, review, **changes):
        body = {"review_id": review["id"], "review_text": review.get("reviewText") or "",
                "rating": review.get("rating", 0), "contains_spoiler": review.get("containsSpoiler", False),
                "backdate": review.get("backdate"), "is_log": review.get("isLog", False),
                "is_rewatch": review.get("isRewatch", False), "episode_number": review.get("episodeNumber"),
                "tags": review.get("tags") or [], "allows_comments": review.get("allowsComments", True),
                "like": review.get("like", False)}
        body.update(changes)
        return self._call("POST", "/show/reviews/update", body)

    def mark_episodes(self, show, season_id, episodes):
        return self._call("POST", "/episode_log/add", {"show_id": show, "season_id": season_id,
                                                        "episode_numbers": episodes, "should_get_next_episode": False})
