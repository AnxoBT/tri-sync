"""Lectura del export oficial de Letterboxd (carpeta letterboxd-*), y generación de CSV de importación."""
import csv
import io
import time

from .config import cache_json, latest_export, save_cache

# Lo cambiado en Letterboxd por su API: el export no lo trae hasta que descargas uno nuevo, así que mientras tanto
# se aplica encima del export (si no, al revisar volvería a salir lo que acabas de arreglar).
APLICADO = "lb_aplicado.json"


def _read(exp, name):
    if not exp.exists(name):
        return []
    return list(csv.DictReader(io.StringIO(exp.read_text(name))))


def load():
    exp = latest_export("letterboxd-")
    films = {}

    def get(row):
        key = (row["Name"], row["Year"])
        return films.setdefault(key, {"name": row["Name"], "year": row["Year"], "uri": row.get("Letterboxd URI"),
                                      "watched": False, "watchlist": False, "rating": None, "like": False,
                                      "diary": []})

    for r in _read(exp, "watched.csv"):
        get(r)["watched"] = True
    for r in _read(exp, "watchlist.csv"):
        get(r)["watchlist"] = True
    for r in _read(exp, "ratings.csv"):
        get(r)["rating"] = float(r["Rating"])
    for r in _read(exp, "likes/films.csv"):
        get(r)["like"] = True
    for r in _read(exp, "diary.csv"):
        get(r)["diary"].append({"date": r["Watched Date"], "rating": r["Rating"], "rewatch": bool(r["Rewatch"])})
    _encima(films, exp.mtime)
    return {"export": exp.name, "films": list(films.values())}


def recordar(m, accion, fecha=None, estrellas=None, like=False):
    """Tras cambiar algo por la API. m: la peli (de Dixmax) con tmdb, title y year. accion: log | nota | watchlist."""
    c = cache_json(APLICADO)
    c[f"{m.get('tmdb')}:{accion}"] = {"t": time.time(), "tmdb": m.get("tmdb"), "name": m.get("title"),
                                      "year": str(m.get("year") or ""), "accion": accion, "fecha": fecha,
                                      "estrellas": estrellas, "like": bool(like)}
    save_cache(APLICADO, c)


def _encima(films, mtime_export):
    c = cache_json(APLICADO)
    vigentes = {k: v for k, v in c.items() if v.get("t", 0) > mtime_export}  # un export más nuevo ya lo trae
    if vigentes != c:
        save_cache(APLICADO, vigentes)
    if not vigentes:
        return
    tmdb_uri = {t: u for u, t in cache_json("lb_tmdb.json").items() if isinstance(t, int)}
    por_uri = {f["uri"]: f for f in films.values() if f.get("uri")}
    for v in sorted(vigentes.values(), key=lambda v: v["t"]):
        f = por_uri.get(tmdb_uri.get(v.get("tmdb")))
        if f is None:  # no estaba en el export: se añade con el título de Dixmax (así se empareja igual)
            f = films.setdefault((v["name"], v["year"]), {"name": v["name"], "year": v["year"], "uri": None,
                                                          "watched": False, "watchlist": False, "rating": None,
                                                          "like": False, "diary": []})
        if v["accion"] == "watchlist":
            f["watchlist"] = True
            continue
        if v.get("estrellas"):
            f["rating"] = float(v["estrellas"])
        if v["accion"] == "log":
            f["watched"] = True
            f["like"] = f["like"] or v.get("like", False)
            if v.get("fecha") and not any(d["date"] == v["fecha"] for d in f["diary"]):
                f["diary"].append({"date": v["fecha"], "rating": f"{v['estrellas']:g}" if v.get("estrellas") else "",
                                   "rewatch": False})


IMPORT_COLS = ["tmdbID", "Title", "Year", "WatchedDate", "Rating", "Rewatch", "Review"]


def write_import_csv(path, rows):
    """rows: dicts con claves de IMPORT_COLS (las que falten van vacías)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=IMPORT_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in IMPORT_COLS})
