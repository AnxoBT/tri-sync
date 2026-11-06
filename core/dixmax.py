"""Lectura del export de Dixmax/PlayMax (carpeta playmax-userdata-*)."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import latest_export, rules

TZ = ZoneInfo("Europe/Madrid")
LISTA_PELIS_VISTAS = "Peliculas vistas"
LISTA_PELIS_PENDIENTES = "Peliculas pendientes"


def iso_utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    exp = latest_export("playmax-userdata-")
    r = rules().get("dixmax", {})
    ign = set(r.get("fichas_ignoradas", []))
    tmdb_ov = {int(k): v for k, v in r.get("tmdb_override", {}).items()}
    mark_ov = {int(k): v for k, v in r.get("mark_override", {}).items()}

    fichas = {}
    for f in json.loads(exp.read_text("fichas.json")):
        if f["id"] in ign:
            continue
        if f["id"] in tmdb_ov:
            f["idTheMovieDB"] = tmdb_ov[f["id"]]
        if f["id"] in mark_ov:
            f["mark"] = mark_ov[f["id"]]
        tm = f.get("idTheMovieDB") or ""
        f["kind"] = "tv" if tm.startswith("tv/") else "movie"
        f["tmdb"] = int(tm.split("/")[1]) if "/" in tm else None
        fichas[f["id"]] = f

    listas = {l["name"]: {x["fichaId"]: x["date"] for x in l["fichas"]}
              for l in json.loads(exp.read_text("lists.json"))}
    episodes = json.loads(exp.read_text("episodes.json"))

    # Películas: estado según tus listas (como las usas tú), con fallback a la marca de la ficha
    vistas = listas.get(LISTA_PELIS_VISTAS, {})
    pend = listas.get(LISTA_PELIS_PENDIENTES, {})
    movies = []
    for f in fichas.values():
        if f["kind"] != "movie":
            continue
        if f["id"] in vistas:
            status, ts = "watched", vistas[f["id"]]
        elif f["id"] in pend:
            status, ts = "watchlist", pend[f["id"]]
        elif f["mark"] in ("viewed", "favorite"):
            status, ts = "watched", f["markDateUnix"]
        elif f["mark"] == "pending":
            status, ts = "watchlist", f["markDateUnix"]
        else:
            continue
        movies.append({"id": f["id"], "title": f["title"], "year": f["year"], "tmdb": f["tmdb"],
                       "imdb": f.get("idImdb"), "status": status, "date": iso_utc(ts) if ts else None,
                       "rating10": f["rating"] or None, "favorite": f["mark"] == "favorite",
                       "mark": f["mark"], "mark_unix": f.get("markDateUnix") or None,
                       "url": f["url"]})

    # Series
    eps_by = {}
    for e in episodes:
        if e.get("viewed") and e["fichaId"] in fichas:
            eps_by.setdefault(e["fichaId"], []).append(
                {"season": e["season"], "episode": e["episode"], "title": e.get("name", ""),
                 "date": iso_utc(e["viewedDateUnix"])})
    for fid, cfg in r.get("episodios_manuales", {}).items():
        fid = int(fid)
        ts = int(datetime.fromisoformat(cfg["fecha_local"]).replace(tzinfo=TZ).timestamp())
        have = {(x["season"], x["episode"]) for x in eps_by.get(fid, [])}
        for s, n in cfg["temporadas"].items():
            for ep in range(1, n + 1):
                if (int(s), ep) not in have:
                    eps_by.setdefault(fid, []).append({"season": int(s), "episode": ep, "title": "",
                                                       "date": iso_utc(ts)})
    status_map = {"viewed": "finished", "favorite": "finished", "following": "watching",
                  "pending": "watchlist", "abandoned": "dropped"}
    shows = []
    for f in fichas.values():
        if f["kind"] != "tv" or not f["tmdb"]:
            continue
        shows.append({"id": f["id"], "title": f["title"], "year": f["year"], "tmdb": f["tmdb"],
                      "status": status_map.get(f["mark"]), "rating10": f["rating"] or None,
                      "favorite": f["mark"] == "favorite", "mark": f["mark"], "mark_unix": f.get("markDateUnix") or None,
                      "mark_date": iso_utc(f["markDateUnix"]) if f["markDateUnix"] else None,
                      "rating_date": iso_utc(f["ratingDateUnix"]) if f.get("ratingDateUnix") else None,
                      "episodes": sorted(eps_by.get(f["id"], []), key=lambda x: (x["season"], x["episode"])),
                      "url": f["url"]})
    return {"export": exp.name, "export_mtime": exp.mtime, "movies": movies, "shows": shows}


def fecha_real(api, ficha_id=None, episode_id=None):
    """Fecha exacta (ISO UTC) de tu marca de una ficha o de cuándo viste un episodio, por la API oficial."""
    try:
        if episode_id:
            d = api._api("get", "ficha_user_dates", "v1", {"episodeId": episode_id})
            u = (d.get("viewedDate") or {}).get("unix")
        else:
            u = (api.dates(ficha_id).get("markedDate") or {}).get("unix")
        return iso_utc(u) if u else None
    except Exception:
        return None


def episodios_api(api, s):
    """Añade a la serie los episodios vistos en Dixmax que no trae el export (fecha aproximada: hoy)."""
    if s.get("_api"):
        return 0
    s["_api"] = True
    try:
        fi = api.ficha(s["id"])
    except Exception:
        return 0
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    have = {(e["season"], e["episode"]) for e in s["episodes"]}
    n = 0
    for season in fi.get("episodes") or []:
        for e in season.get("episodesList", []):
            if (e.get("user") or {}).get("viewed") and (e["season"], e["episode"]) not in have:
                real = fecha_real(api, episode_id=e["id"])
                fecha, aprox = (real, False) if real else (hoy, True)
                s["episodes"].append({"season": e["season"], "episode": e["episode"], "title": e.get("name", ""),
                                      "date": fecha, "fecha_aproximada": aprox, "dx_episode_id": e["id"]})
                n += 1
    s["episodes"].sort(key=lambda x: (x["season"], x["episode"]))
    return n


def apply_live(data, progress=print, rapida=False):
    """Actualiza lo leído del export con el estado ACTUAL de Dixmax (API oficial):
    marcas, notas, fichas nuevas y episodios vistos nuevos de las series que sigues.
    Lo nuevo que no está en el export no tiene fecha real: se usa la fecha de hoy (fecha_aproximada)."""
    from .dixmax_api import Dixmax
    api = Dixmax()
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mf = api.my_fichas()
    secs = mf.get("sections", mf)
    r = rules().get("dixmax", {})
    ign = set(r.get("fichas_ignoradas", []))
    tmdb_ov = {int(k): v for k, v in r.get("tmdb_override", {}).items()}
    live = {}  # id -> (tipo, marca, nota, ficha_api)
    for tipo, grupos in secs.items():
        if tipo == "episode" or not isinstance(grupos, dict):
            continue
        for mark, lst in grupos.items():
            for f in lst:
                if f.get("isFolder"):
                    continue
                live[f["id"]] = (tipo, mark, (f.get("user") or {}).get("rating") or None, f)

    movies = {m["id"]: m for m in data["movies"]}
    shows = {s["id"]: s for s in data["shows"]}
    status_show = {"viewed": "finished", "favorite": "finished", "following": "watching",
                   "pending": "watchlist", "abandoned": "dropped"}
    nuevos = cambios = 0

    def tmdb_de(fid, info=None):
        if fid in tmdb_ov:
            return int(tmdb_ov[fid].split("/")[1])
        info = info or api.ficha(fid)["info"]
        for x in info.get("externalLinks", []):
            if x["name"] == "TheMovieDB" and str(x.get("externalId", "")).isdigit():
                return int(x["externalId"])
        return None

    for fid, (tipo, mark, nota, f) in live.items():
        if fid in ign:
            continue
        es_serie = f.get("isSerie") or tipo == "series"
        if not es_serie:
            st = "watched" if mark in ("viewed", "favorite") else "watchlist" if mark == "pending" else None
            if not st:
                continue
            m = movies.get(fid)
            if m is None:
                movies[fid] = {"id": fid, "title": f["title"], "year": f.get("year"), "tmdb": tmdb_de(fid), "imdb": None,
                               "status": st, "date": fecha_real(api, ficha_id=fid) or hoy, "rating10": nota,
                               "favorite": mark == "favorite", "url": f"https://playmax.mx/x-f{fid}"}
                movies[fid]["fecha_aproximada"] = movies[fid]["date"] == hoy
                nuevos += 1
            else:
                if m["status"] != st:
                    if st == "watched":  # vista desde el export: fecha real de la marca por la API
                        m["date"] = fecha_real(api, ficha_id=fid) or hoy
                        m["fecha_aproximada"] = m["date"] == hoy
                    m["status"], cambios = st, cambios + 1
                if nota != m["rating10"]:
                    m["rating10"], cambios = nota, cambios + 1
                if m.get("mark") != mark:
                    m["mark"], m["mark_unix"] = mark, None
                m["favorite"] = mark == "favorite"
        else:
            s = shows.get(fid)
            st = status_show.get(mark)
            if s is None:
                tm = tmdb_de(fid)
                if not tm:
                    continue
                s = shows[fid] = {"id": fid, "title": f["title"], "year": f.get("year"), "tmdb": tm, "status": st,
                                  "rating10": nota, "favorite": mark == "favorite",
                                  "mark_date": fecha_real(api, ficha_id=fid) or hoy, "rating_date": hoy,
                                  "episodes": [], "url": f"https://playmax.mx/x-f{fid}"}
                nuevos += 1
            else:
                if s["status"] != st or s["rating10"] != nota:
                    cambios += 1
                if s.get("mark") != mark:
                    s["mark"], s["mark_unix"] = mark, None
                s["status"], s["rating10"], s["favorite"] = st, nota, mark == "favorite"
    # Nota: las fichas del export que no salen en la API no se tocan (p. ej. películas que tienes en
    # tus listas sin marca). Para reflejar marcas QUITADAS, descarga un export nuevo.

    # episodios nuevos de las series que sigues (y de las nuevas)
    revisar = [s for s in shows.values() if s["status"] == "watching" or not s["episodes"] and s["status"] == "finished"]
    import time
    if rapida:
        progress("Dixmax: revisión rápida (por la API solo se miran las series que no cuadren)")
        revisar = [s for s in revisar if not s["episodes"]]
    elif time.time() - data.get("export_mtime", 0) < 3600:  # export de hace menos de 1 h: ya trae los episodios
        progress("Dixmax: export reciente, no hace falta revisar episodios por la API")
        revisar = [s for s in revisar if not s["episodes"]]
    for i, s in enumerate(revisar, 1):
        if i % 10 == 0:
            progress(f"Dixmax: episodios {i}/{len(revisar)}")
        nuevos += episodios_api(api, s)
    progress(f"Dixmax en directo: {nuevos} novedades y {cambios} cambios respecto al export")
    data["movies"], data["shows"] = list(movies.values()), list(shows.values())
    data["live"] = True
    data["api"] = api  # para comprobar por la API, al revisar, las series que no cuadren
    data["novedades"], data["cambios"] = nuevos, cambios
    return data
