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
    for f in json.loads((exp / "fichas.json").read_text(encoding="utf-8")):
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
              for l in json.loads((exp / "lists.json").read_text(encoding="utf-8"))}
    episodes = json.loads((exp / "episodes.json").read_text(encoding="utf-8"))

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
                      "favorite": f["mark"] == "favorite", "mark_date": iso_utc(f["markDateUnix"]) if f["markDateUnix"] else None,
                      "rating_date": iso_utc(f["ratingDateUnix"]) if f.get("ratingDateUnix") else None,
                      "episodes": sorted(eps_by.get(f["id"], []), key=lambda x: (x["season"], x["episode"])),
                      "url": f["url"]})
    return {"export": exp.name, "movies": movies, "shows": shows}
