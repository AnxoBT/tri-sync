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
DINERO, DIXMAX, TVMAZE = "meta_dinero4.json", "meta_dixmax.json", "meta_tvmaze.json"
V_DIXMAX = 2
V_TVMAZE = 2
V_PELI, V_ANIME = 2, 3  # al añadir campos se vuelven a pedir las fichas de esa versión


def _peli(tmdb):
    s, d = call("GET", f"https://api.radarr.video/v1/movie/{tmdb}", delay=0, retries=2, timeout=30)
    if s != 200 or not isinstance(d, dict):
        return tmdb, None if s == 404 else "error"
    cr = d.get("Credits") or {}
    rt_ = d.get("MovieRatings") or {}
    imdb, tm = rt_.get("Imdb") or {}, rt_.get("Tmdb") or {}
    return tmdb, {"v": V_PELI, "imdb_n": imdb.get("Count") or 0, "imdb_r": imdb.get("Value") or None,
                  "tmdb_n": tm.get("Count") or 0, "pop": d.get("Popularity"), "rt": d.get("Runtime") or None, "g": d.get("Genres") or [], "st": d.get("Studio") or None,
                  "col": (d.get("Collection") or {}).get("Name"), "lang": d.get("OriginalLanguage"),
                  "dir": [c["Name"] for c in cr.get("Crew") or [] if c.get("Job") == "Director"][:3],
                  "cast": [c["Name"] for c in sorted(cr.get("Cast") or [], key=lambda c: c.get("Order", 99))[:6]]}


def pelis(tmdbs, progress=print):
    c = cache_json(PELIS, {})
    faltan = [t for t in set(tmdbs) if t and (not isinstance(c.get(str(t)), dict) and c.get(str(t), "x") is not None
                                              or isinstance(c.get(str(t)), dict) and c[str(t)].get("v") != V_PELI)]
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
    faltan = [i for i in set(ids) if (c.get(str(i)) or {}).get("v") != V_ANIME]
    if faltan:
        progress(f"Estadísticas: fichas de {len(faltan)} animes…")
    q = """query($ids:[Int]){ Page(perPage:25){ media(id_in:$ids, type:ANIME){ id genres countryOfOrigin duration
          popularity meanScore studios(isMain:true){ nodes{ name } }
          characters(sort:[ROLE, RELEVANCE], perPage:6){ edges{ node{ id } voiceActors(language:JAPANESE){ name{ full } } } } } } }"""
    for i in range(0, len(faltan), 25):
        try:
            for m in anilist.gql(q, {"ids": faltan[i:i + 25]}, con_token=False)["Page"]["media"]:
                voces = []
                for e in (m.get("characters") or {}).get("edges") or []:
                    va = (e.get("voiceActors") or [None])[0]  # la voz principal del personaje
                    if va and va["name"]["full"] not in voces:
                        voces.append(va["name"]["full"])
                c[str(m["id"])] = {"v": V_ANIME, "g": m.get("genres") or [], "pais": m.get("countryOfOrigin"),
                                   "rt": m.get("duration"), "pop": m.get("popularity") or 0, "media": m.get("meanScore"),
                                   "st": [n["name"] for n in (m.get("studios") or {}).get("nodes") or []][:2],
                                   "voces": voces[:6]}
        except Exception:
            break
    if faltan:
        save_cache(ANIME, c)
    return c


def dinero(tmdbs, progress=print):
    """Presupuesto y taquilla mundial en dólares (Wikidata). {tmdb: [coste|None, taquilla|None]}"""
    c = cache_json(DINERO, {})
    faltan = [str(t) for t in set(tmdbs) if t and str(t) not in c]
    if faltan:
        progress(f"Estadísticas: presupuesto y taquilla de {len(faltan)} películas (Wikidata)…")
    usd = "http://www.wikidata.org/entity/Q4917"

    def lote(ids):
        q = ("SELECT ?t ?coste ?uc ?taq ?ut WHERE { VALUES ?t {" + " ".join(f'"{t}"' for t in ids) + "} ?f wdt:P4947 ?t. "
             "OPTIONAL { ?f p:P2130/psv:P2130 [wikibase:quantityAmount ?coste; wikibase:quantityUnit ?uc] } "
             "OPTIONAL { ?f p:P2142 ?st. ?st psv:P2142 [wikibase:quantityAmount ?taq; wikibase:quantityUnit ?ut]. "
             "OPTIONAL { ?st pq:P3005 ?zona } } }")
        try:
            req = urllib.request.Request("https://query.wikidata.org/sparql",
                                         data=urllib.parse.urlencode({"format": "json", "query": q}).encode(),
                                         headers={"User-Agent": "Tri-Sync (uso personal)",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                filas = json.load(r)["results"]["bindings"]
        except Exception:
            return {}
        res = {t: [None, None, False] for t in ids}  # coste, taquilla, ¿taquilla marcada como mundial?
        mundial = "http://www.wikidata.org/entity/Q13780930"
        taq = {t: {"mundo": 0, "usd": 0, "otra": False} for t in ids}
        for b in filas:
            t = b["t"]["value"]
            if "coste" in b and b.get("uc", {}).get("value") == usd:
                res[t][0] = max(res[t][0] or 0, float(b["coste"]["value"]))
            if "taq" in b:
                if b.get("ut", {}).get("value") != usd:
                    taq[t]["otra"] = True
                elif b.get("zona", {}).get("value") == mundial:
                    taq[t]["mundo"] = max(taq[t]["mundo"], float(b["taq"]["value"]))
                else:
                    taq[t]["usd"] = max(taq[t]["usd"], float(b["taq"]["value"]))
        for t, x in taq.items():
            # taquilla mundial; si solo hay cifras sueltas en dólares y además otras monedas, la de dólares suele ser
            # solo la de EE. UU. de una peli extranjera (Battle Royale…): mejor no dar nada que dar un dato engañoso
            res[t][1] = x["mundo"] or x["usd"] or None  # si no es mundial, estadisticas.py decide según el idioma
            res[t][2] = bool(x["mundo"])
        return res
    lotes = [faltan[i:i + 100] for i in range(0, len(faltan), 100)]
    with ThreadPoolExecutor(3) as ex:
        for res in ex.map(lote, lotes):
            c.update(res)
            save_cache(DINERO, c)
    return c


def fichas_dixmax(ids, progress=print):
    """Ficha de Dixmax de series y anime: reparto, dirección, géneros (en español), temas, nota y votos de la comunidad."""
    from .dixmax_api import Dixmax
    c = cache_json(DIXMAX, {})
    faltan = [i for i in dict.fromkeys(ids) if (c.get(str(i)) or {}).get("v") != V_DIXMAX]
    if not faltan:
        return c
    progress(f"Estadísticas: fichas de Dixmax de {len(faltan)} títulos (solo la primera vez, ~{max(1, round(len(faltan) / 110))} min)…")
    api = Dixmax()
    for n, fid in enumerate(faltan, 1):
        try:
            info = api.ficha(fid)["info"]
        except Exception:
            continue
        grupos = {g["groupName"]: [p["name"] for p in g.get("persons") or []] for g in info.get("crew") or []}
        c[str(fid)] = {"v": V_DIXMAX, "pais": info.get("country"), "reparto": grupos.get("Reparto", [])[:8], "dir": grupos.get("Dirección", [])[:3],
                       "g": [g["name"] for g in info.get("genres") or []], "temas": [x["name"] for x in info.get("topics") or []],
                       "r": info.get("rating"), "votos": info.get("votes") or 0, "dur": info.get("duration")}
        if n % 25 == 0:
            progress(f"Estadísticas: fichas de Dixmax {n}/{len(faltan)} (solo la primera vez)")
            save_cache(DIXMAX, c)
    save_cache(DIXMAX, c)
    return c


def tvmaze(tmdbs, progress=print):
    """Popularidad (weight 0-100), nota media de la gente y reparto principal en TVmaze, por IMDb (que da Wikidata).
    {tmdb: {v, w, r, cast}}"""
    c = cache_json(TVMAZE, {})
    faltan = [str(t) for t in set(tmdbs) if t and (c.get(str(t)) or {}).get("v") != V_TVMAZE]
    if not faltan:
        return c
    progress(f"Estadísticas: popularidad y reparto de {len(faltan)} series (TVmaze)…")
    imdb = {}
    for i in range(0, len(faltan), 100):
        q = ("SELECT ?t ?imdb WHERE { VALUES ?t {" + " ".join(f'"{t}"' for t in faltan[i:i + 100]) + "} "
             "?f wdt:P4983 ?t; wdt:P345 ?imdb }")
        try:
            req = urllib.request.Request("https://query.wikidata.org/sparql",
                                         data=urllib.parse.urlencode({"format": "json", "query": q}).encode(),
                                         headers={"User-Agent": "Tri-Sync (uso personal)",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                for b in json.load(r)["results"]["bindings"]:
                    imdb.setdefault(b["t"]["value"], b["imdb"]["value"])
        except Exception:
            return c

    def uno(t):
        if t not in imdb:
            return t, {"v": V_TVMAZE}
        time.sleep(1.2)  # TVmaze: 20 peticiones cada 10 s (aquí van 2 por serie)
        s, d = call("GET", f"https://api.tvmaze.com/lookup/shows?imdb={imdb[t]}", delay=0, retries=2, timeout=30)
        if s != 200 or not isinstance(d, dict):
            return t, ({"v": V_TVMAZE} if s == 404 else None)
        out = {"v": V_TVMAZE, "w": d.get("weight"), "r": (d.get("rating") or {}).get("average"), "cast": []}
        s2, cast = call("GET", f"https://api.tvmaze.com/shows/{d['id']}/cast", delay=0, retries=2, timeout=30)
        if s2 == 200 and isinstance(cast, list):
            vistos = []
            for x in cast:  # reparto principal, en orden; sin repetir (hay actores con varios personajes)
                n = (x.get("person") or {}).get("name")
                if n and n not in vistos:
                    vistos.append(n)
            out["cast"] = vistos
        return t, out
    with ThreadPoolExecutor(2) as ex:
        for t, d in ex.map(uno, faltan):
            if d is not None:
                c[t] = d
    save_cache(TVMAZE, c)
    return c
