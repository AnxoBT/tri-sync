"""Fichas de cada peli, serie y anime para las estadísticas (sin claves nuevas):

- Pelis: Radarr (duración, géneros, estudio, saga, director, reparto, idioma) + Wikidata (países).
- Series: Serializd (país, géneros, cadena, duración del episodio).
- Anime: AniList (estudio, géneros, país, duración del episodio).
Todo en caché: solo se descarga lo que falta (la primera vez tarda unos minutos).
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import cache_json, save_cache
from .http import call

PELIS, PAISES, SERIES, ANIME = "meta_pelis.json", "meta_paises.json", "meta_series.json", "meta_anime.json"


def _peli(tmdb):
    s, d = call("GET", f"https://api.radarr.video/v1/movie/{tmdb}", delay=0, retries=2, timeout=30)
    if s != 200 or not isinstance(d, dict):
        return tmdb, None if s == 404 else "error"
    cr = d.get("Credits") or {}
    return tmdb, {"rt": d.get("Runtime") or None, "g": d.get("Genres") or [], "st": d.get("Studio") or None,
                  "col": (d.get("Collection") or {}).get("Name"), "lang": d.get("OriginalLanguage"),
                  "dir": [c["Name"] for c in cr.get("Crew") or [] if c.get("Job") == "Director"][:3],
                  "cast": [c["Name"] for c in sorted(cr.get("Cast") or [], key=lambda c: c.get("Order", 99))[:6]]}


def pelis(tmdbs, progress=print):
    c = cache_json(PELIS, {})
    faltan = [t for t in set(tmdbs) if t and (str(t) not in c or c[str(t)] == "error")]
    if faltan:
        progress(f"Estadísticas: fichas de {len(faltan)} películas (solo la primera vez)…")
        with ThreadPoolExecutor(8) as ex:
            for i, (t, d) in enumerate(ex.map(_peli, faltan), 1):
                c[str(t)] = d
                if i % 200 == 0:
                    progress(f"Estadísticas: películas {i}/{len(faltan)}")
                    save_cache(PELIS, c)
        save_cache(PELIS, c)
    return c


def paises_pelis(tmdbs, progress=print):
    """País(es) de producción de cada peli (Wikidata, por id de TMDB). {tmdb: ["US", …]}"""
    c = cache_json(PAISES, {})
    faltan = [str(t) for t in set(tmdbs) if t and str(t) not in c]
    if faltan:
        progress(f"Estadísticas: países de {len(faltan)} películas (Wikidata, solo la primera vez)…")

    def lote(ids):
        q = ("SELECT ?t ?pais WHERE { VALUES ?t {" + " ".join(f'"{t}"' for t in ids) + "} "
             "?f wdt:P4947 ?t; wdt:P495 ?p. ?p wdt:P297 ?pais }")
        try:  # por POST: con muchos ids la URL sería enorme
            req = urllib.request.Request("https://query.wikidata.org/sparql",
                                         data=urllib.parse.urlencode({"format": "json", "query": q}).encode(),
                                         headers={"User-Agent": "Tri-Sync (uso personal)",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                filas = json.load(r)["results"]["bindings"]
        except Exception:
            return {}  # se reintenta en la próxima
        res = {t: [] for t in ids}
        for b in filas:
            res[b["t"]["value"]].append(b["pais"]["value"])
        return res
    lotes = [faltan[i:i + 100] for i in range(0, len(faltan), 100)]
    with ThreadPoolExecutor(3) as ex:
        for n, res in enumerate(ex.map(lote, lotes), 1):
            c.update(res)
            save_cache(PAISES, c)
            progress(f"Estadísticas: países {min(n * 100, len(faltan))}/{len(faltan)}")
    return c


def _serie(sz, tmdb):
    s, d = sz._call("GET", f"/show/{tmdb}")
    if s != 200 or not isinstance(d, dict):
        return tmdb, None if s == 404 else "error"
    rt = [x for x in d.get("episodeRunTime") or [] if x]
    if not rt:  # muchas series no lo traen: se mira la duración de los episodios de la 1.ª temporada
        s2, t = sz._call("GET", f"/show/{tmdb}/season/1")
        if s2 == 200 and isinstance(t, dict):
            rt = [e["runtime"] for e in t.get("episodes") or [] if e.get("runtime")]
    return tmdb, {"pais": d.get("originCountry") or [], "g": [g["name"] for g in d.get("genres") or []],
                  "red": [n["name"] for n in d.get("networks") or []][:2],
                  "rt": round(sum(rt) / len(rt)) if rt else None, "eps": d.get("numEpisodes")}


def series(tmdbs, progress=print):
    from .serializd import Serializd
    c = cache_json(SERIES, {})
    faltan = [t for t in set(tmdbs) if t and (str(t) not in c or c[str(t)] == "error")]
    if faltan:
        progress(f"Estadísticas: fichas de {len(faltan)} series (solo la primera vez)…")
        sz = Serializd()
        with ThreadPoolExecutor(6) as ex:
            for i, (t, d) in enumerate(ex.map(lambda t: _serie(sz, t), faltan), 1):
                c[str(t)] = d
                if i % 100 == 0:
                    progress(f"Estadísticas: series {i}/{len(faltan)}")
                    save_cache(SERIES, c)
        save_cache(SERIES, c)
    return c


def anime(ids, progress=print):
    from . import anilist
    c = cache_json(ANIME, {})
    faltan = [i for i in set(ids) if str(i) not in c]
    if faltan:
        progress(f"Estadísticas: fichas de {len(faltan)} animes…")
    q = """query($ids:[Int]){ Page(perPage:50){ media(id_in:$ids, type:ANIME){ id genres countryOfOrigin duration
          studios(isMain:true){ nodes{ name } } } } }"""
    for i in range(0, len(faltan), 50):
        try:
            for m in anilist.gql(q, {"ids": faltan[i:i + 50]}, con_token=False)["Page"]["media"]:
                c[str(m["id"])] = {"g": m.get("genres") or [], "pais": m.get("countryOfOrigin"), "rt": m.get("duration"),
                                   "st": [n["name"] for n in (m.get("studios") or {}).get("nodes") or []][:2]}
        except Exception:
            break
    if faltan:
        save_cache(ANIME, c)
    return c
