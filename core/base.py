"""Historial base cuando no tienes Dixmax: se monta con lo que tengas en las otras apps.

Dixmax es la única que lleva pelis, series y anime a la vez; sin ella, cada tipo sale de su app:
  pelis   Letterboxd (vistas, watchlist, notas, me gusta y fechas del diario). El export no trae el id de TMDB:
          se saca de la ficha de cada peli en letterboxd.com (una vez por peli, en caché).
  series  Serializd (diario de episodios con fecha, listas y notas de serie). Los ids ya son los de TMDB.
Tiene la misma forma que dixmax.load(), así el cruce con AniList y las estadísticas funcionan igual.
"""
import re
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .config import cache_json, save_cache

TMDB_LB = "lb_tmdb.json"


def _tmdb_de_ficha(uri):
    try:
        req = urllib.request.Request(uri, headers={"User-Agent": "Mozilla/5.0 (Tri-Sync)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        return uri, "error"
    m = re.search(r'data-tmdb-id="(\d+)"', html) or re.search(r"themoviedb\.org/movie/(\d+)", html)
    return uri, int(m.group(1)) if m else None


def tmdb_letterboxd(uris, progress=print):
    """{uri de Letterboxd: id de TMDB | None}. Los fallos de red se reintentan en la siguiente revisión."""
    c = cache_json(TMDB_LB, {})
    faltan = [u for u in dict.fromkeys(uris) if u and (u not in c or c[u] == "error")]
    if faltan:
        progress(f"Letterboxd: buscando el id de TMDB de {len(faltan)} pelis (solo la primera vez)…")
        with ThreadPoolExecutor(6) as ex:
            for n, (u, t) in enumerate(ex.map(_tmdb_de_ficha, faltan), 1):
                c[u] = t
                if n % 100 == 0:
                    progress(f"Letterboxd: ids de TMDB {n}/{len(faltan)}")
                    save_cache(TMDB_LB, c)
        save_cache(TMDB_LB, c)
    return {u: (c.get(u) if isinstance(c.get(u), int) else None) for u in uris}


def _iso(fecha):
    """'2024-05-06' -> '2024-05-06T12:00:00' (Letterboxd no da la hora: mediodía, para que no cambie de día)."""
    return f"{fecha[:10]}T12:00:00" if fecha else None


def pelis_letterboxd(lb, progress=print):
    ids = tmdb_letterboxd([f.get("uri") for f in lb["films"]], progress)
    out = []
    for f in lb["films"]:
        if not (f["watched"] or f["watchlist"]):
            continue
        fechas = sorted(x["date"] for x in f["diary"] if x.get("date"))
        out.append({"id": f"lb:{f.get('uri') or f['name']}", "tmdb": ids.get(f.get("uri")), "title": f["name"],
                    "year": int(f["year"]) if str(f["year"]).isdigit() else None,
                    "status": "watched" if f["watched"] else "watchlist", "date": _iso(fechas[-1]) if fechas else None,
                    "rating10": f["rating"] * 2 if f.get("rating") else None, "favorite": bool(f["like"]),
                    "url": f.get("uri")})
    return out


def series_serializd(diario, listas, notas):
    """diario, listas ({watched|watching|watchlist|dropped: {tmdb: …}}) y notas tal como los da serializd.Serializd."""
    eps, info, logs = defaultdict(dict), {}, defaultdict(list)
    for d in diario:
        tid = d["showId"]
        info.setdefault(tid, (d.get("showName"), (d.get("showPremiereDate") or "")[:4]))
        num = {s["id"]: s["seasonNumber"] for s in d.get("showSeasons") or []}
        if d.get("episodeNumber") is not None and num.get(d.get("seasonId")) is not None:
            k = (num[d["seasonId"]], d["episodeNumber"])
            f = (d.get("backdate") or d.get("dateAdded") or "")[:19] or None
            if k not in eps[tid] or (f and (eps[tid][k] or "9") > f):  # vista varias veces: la primera
                eps[tid][k] = f
        elif d.get("seasonId") is None:
            logs[tid].append(d)
    for x in notas:
        logs[x["showId"]].append(x)
    for k, v in listas.items():
        for tid, it in v.items():
            info.setdefault(tid, (it.get("name"), ""))
    out = []
    for tid, (nombre, anio) in info.items():
        en = {k for k, v in listas.items() if tid in v}
        st = ("dropped" if "dropped" in en else "watching" if "watching" in en else "watchlist" if "watchlist" in en
              and not eps[tid] else "finished" if "watched" in en else "watching" if eps[tid] else None)
        if not st:
            continue
        nota = max((x for x in logs[tid] if x.get("rating")), key=lambda x: x.get("dateAdded") or "", default=None)
        out.append({"id": f"sz:{tid}", "tmdb": tid, "title": nombre or str(tid), "year": int(anio) if anio.isdigit() else None,
                    "status": st, "rating10": nota["rating"] if nota else None, "nota_entera": True,
                    "favorite": any(x.get("like") for x in logs[tid]),
                    "episodes": [{"season": s, "episode": e, "date": f} for (s, e), f in sorted(eps[tid].items())],
                    "url": f"https://www.serializd.com/show/{tid}"})
    return out


def montar(lb=None, sz=None, progress=print):
    """dx sin Dixmax. sz: {"diario", "listas", "notas"} ya leídos."""
    dx = {"export": None, "export_mtime": None, "sin_dixmax": True, "movies": [], "shows": []}
    if lb:
        dx["movies"] = pelis_letterboxd(lb, progress)
    if sz:
        dx["shows"] = series_serializd(sz["diario"], sz["listas"], sz["notas"])
        dx["sz_favs"] = {s["tmdb"] for s in dx["shows"] if s["favorite"]}
        dx["sz_en_listas"] = {tid for v in sz["listas"].values() for tid in v}
    dx["fecha"] = time.strftime("%Y-%m-%d %H:%M")
    return dx


def _fecha_al(f):
    f = f or {}
    return f"{f['year']:04d}-{f.get('month') or 1:02d}-{f.get('day') or 1:02d}T12:00:00" if f.get("year") else None


def anime_anilist(dx, mp, progress=print):
    """Añade a dx el anime de tu lista de AniList que no está ya por Serializd o Letterboxd (con solo AniList, todo).
    AniList no da la fecha de cada episodio: solo cuántos llevas y cuándo empezaste y acabaste."""
    from . import anilist
    cur = dx.get("al_lista") or {}
    inv_tv = {al: (int(tm), temp) for tm, v in mp["tv"].items() for al, temp in v}
    inv_mv = {al: int(tm) for tm, v in mp["mv"].items() for al in v}
    ya_tv = {s["tmdb"] for s in dx["shows"]}
    ya_mv = {m["tmdb"] for m in dx["movies"] if m.get("tmdb")}
    med = anilist.medios(list(cur), progress)
    M = lambda i: med.get(str(i)) or {}  # noqa: E731
    series = defaultdict(list)
    for i, e in cur.items():
        if M(i).get("formato") == "MOVIE":
            if inv_mv.get(i) in ya_mv:
                continue
            st = {"COMPLETED": "watched", "PLANNING": "watchlist"}.get(e["status"])
            if st:
                dx["movies"].append({"id": f"al:{i}", "tmdb": inv_mv.get(i), "title": M(i).get("titulo") or str(i),
                                     "year": M(i).get("inicio", [None])[0] if M(i).get("inicio", [9999])[0] != 9999 else None,
                                     "status": st, "date": _fecha_al(e.get("completedAt")),
                                     "rating10": e.get("score") or None, "favorite": False})
            continue
        tm, temp = inv_tv.get(i, (None, None))
        if tm in ya_tv:
            continue
        series[tm or f"al{i}"].append((i, e, temp))
    for clave, partes in series.items():
        partes.sort(key=lambda p: M(p[0]).get("inicio", [9999]))
        eps, n_temp = [], defaultdict(int)
        for i, e, temp in partes:
            t = temp or 1
            fin = _fecha_al(e.get("completedAt"))
            for _ in range(e.get("progress") or 0):
                n_temp[t] += 1
                eps.append({"season": t, "episode": n_temp[t], "date": None, "fecha_aproximada": True})
            if eps and fin and e["status"] == "COMPLETED":
                eps[-1]["date"] = fin  # el último episodio: el día que la acabaste
        estados = {e["status"] for _, e, _ in partes}
        st = ("watching" if estados & {"CURRENT", "REPEATING", "PAUSED"} else "dropped" if "DROPPED" in estados
              else "finished" if estados == {"COMPLETED"} else "watchlist" if "PLANNING" in estados and not eps else "watching")
        i0, e0, _ = partes[0]
        notas = [e["score"] for _, e, _ in partes if e.get("score")]
        sid = f"al:{i0}"
        dx["shows"].append({"id": sid, "tmdb": clave if isinstance(clave, int) else None, "title": M(i0).get("titulo") or str(i0),
                            "year": M(i0).get("inicio", [None])[0] if M(i0).get("inicio", [9999])[0] != 9999 else None,
                            "status": st, "rating10": round(sum(notas) / len(notas), 1) if notas else None, "favorite": False,
                            "episodes": eps, "url": f"https://anilist.co/anime/{i0}"})
        dx.setdefault("anime_al", {})[sid] = i0
    return dx
