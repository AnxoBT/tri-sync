"""Lectura del export oficial de Letterboxd (carpeta letterboxd-*), y generación de CSV de importación."""
import csv
import io

from .config import latest_export


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
    return {"export": exp.name, "films": list(films.values())}


IMPORT_COLS = ["tmdbID", "Title", "Year", "WatchedDate", "Rating", "Rewatch", "Review"]


def write_import_csv(path, rows):
    """rows: dicts con claves de IMPORT_COLS (las que falten van vacías)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=IMPORT_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in IMPORT_COLS})
