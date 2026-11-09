"""Identificadores de una película en otras webs cuando Dixmax no da el de TMDB.

Wikidata cruza FilmAffinity / IMDb con TMDB y con la ficha de Letterboxd (sin cuentas ni claves).
Se guarda en caché: cada película se pregunta una sola vez.
"""
import json
import time
import urllib.parse
import urllib.request

from .config import cache_json, save_cache

CACHE = "ids_externos.json"
PROP = {"FilmAffinity": "P480", "IMDb": "P345"}


def buscar(externos):
    """externos: {"FilmAffinity": "154774", "IMDb": "tt…"} -> {"tmdb": int|None, "imdb": str|None, "lb": slug|None}"""
    clave = next((f"{k}:{v}" for k, v in externos.items() if k in PROP and v), None)
    if not clave:
        return {}
    c = cache_json(CACHE, {})
    hit = c.get(clave)
    if hit and (hit.get("lb") or time.time() - hit.get("t", 0) < 30 * 86400):  # sin resultado: reintenta al mes
        return hit
    nombre, valor = clave.split(":", 1)
    q = (f'SELECT ?lb ?tmdb ?imdb WHERE {{ ?f wdt:{PROP[nombre]} "{valor}". OPTIONAL{{?f wdt:P6127 ?lb}} '
         f'OPTIONAL{{?f wdt:P4947 ?tmdb}} OPTIONAL{{?f wdt:P345 ?imdb}} }} LIMIT 1')
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": q})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Tri-Sync (uso personal)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            filas = json.load(r)["results"]["bindings"]
    except Exception:
        return {}
    f = filas[0] if filas else {}
    v = lambda k: (f.get(k) or {}).get("value")  # noqa: E731
    res = {"tmdb": int(v("tmdb")) if (v("tmdb") or "").isdigit() else None, "imdb": v("imdb"), "lb": v("lb"),
           "t": int(time.time())}
    c[clave] = res
    save_cache(CACHE, c)
    return res


def tmdb_de_anilist(anilist_id):
    """TMDB (serie o peli) de un anime de AniList vía Wikidata, para lo que aún no está en la lista de equivalencias.
    -> {"tv": int|None, "movie": int|None}. En caché; si no hay dato se reintenta a la semana."""
    c = cache_json("anilist_tmdb.json", {})
    k = str(anilist_id)
    hit = c.get(k)
    if hit and (hit.get("tv") or hit.get("movie") or time.time() - hit.get("t", 0) < 7 * 86400):
        return hit
    q = (f'SELECT ?tv ?mv WHERE {{ ?f wdt:P8729 "{int(anilist_id)}". OPTIONAL{{?f wdt:P4983 ?tv}} '
         f'OPTIONAL{{?f wdt:P4947 ?mv}} }} LIMIT 1')
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": q})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Tri-Sync (uso personal)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            filas = json.load(r)["results"]["bindings"]
    except Exception:
        return {}
    f = filas[0] if filas else {}
    num = lambda k: int(f[k]["value"]) if f.get(k, {}).get("value", "").isdigit() else None  # noqa: E731
    c[k] = {"tv": num("tv"), "movie": num("mv"), "t": int(time.time())}
    save_cache("anilist_tmdb.json", c)
    return c[k]
