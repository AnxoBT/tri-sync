"""Emparejado de películas Dixmax <-> Letterboxd.

Dixmax trae TMDB id y títulos en español; Letterboxd trae título (normalmente inglés) + año.
Se usan los títulos de la API pública de Radarr (sin clave) y las reglas manuales de rules.json.
"""
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from .config import cache_json, rules, save_cache
from .http import call


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace("&", "and")
    s = re.sub(r"^(the|a|an|el|la|los|las)\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _radarr(tmdb):
    s, d = call("GET", f"https://api.radarr.video/v1/movie/{tmdb}", delay=0)
    if s == 200 and isinstance(d, dict):
        return tmdb, {"title": d.get("Title"), "orig": d.get("OriginalTitle"), "year": d.get("Year"),
                      "alt": [a.get("Title") for a in d.get("AlternativeTitles", [])]}
    return tmdb, None if s == 404 else "error"


def titles_cache(tmdb_ids):
    c = cache_json("radarr.json")
    todo = [t for t in tmdb_ids if t and (str(t) not in c or c[str(t)] == "error")]
    if todo:
        with ThreadPoolExecutor(8) as ex:
            for t, d in ex.map(_radarr, todo):
                c[str(t)] = d
        save_cache("radarr.json", c)
    return c


def match(dx_movies, lb_films):
    """Devuelve (pares [(dx, lb)], solo_dixmax [dx], solo_letterboxd [lb])."""
    manual = rules().get("peliculas", {}).get("titulo_manual", {})
    cache = titles_cache([m["tmdb"] for m in dx_movies])
    index = {}
    for f in lb_films:
        index.setdefault(norm(f["name"]), []).append(f)
    used, pairs, solo_dx = set(), [], []
    # primero las vistas, para que no "roben" pareja las pendientes
    for m in sorted(dx_movies, key=lambda m: m["status"] != "watched"):
        names, years = [m["title"], manual.get(m["title"])], {m["year"]}
        # Dixmax a veces añade una coletilla: "It's Such a Beautiful Day (Película)"
        sin_coletilla = re.sub(r"\s*\([^)]*\)\s*$", "", m["title"])
        if sin_coletilla and sin_coletilla != m["title"]:
            names.append(sin_coletilla)
        info = cache.get(str(m["tmdb"])) if m["tmdb"] else None
        if isinstance(info, dict):
            names += [info["title"], info["orig"]] + info["alt"]
            if info["year"]:
                years.add(info["year"])
        hit = None
        for n in filter(None, names):
            for f in index.get(norm(n), []):
                # sin año en Letterboxd (pasa en algunas fichas) basta con el título
                if id(f) not in used and (not f["year"] or any(abs(int(f["year"]) - int(y or 0)) <= 1 for y in years)):
                    hit = f
                    break
            if hit:
                break
        if hit:
            used.add(id(hit))
            pairs.append((m, hit))
        else:
            solo_dx.append(m)
    solo_lb = [f for f in lb_films if id(f) not in used and (f["watched"] or f["watchlist"])]
    return pairs, solo_dx, solo_lb
