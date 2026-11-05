"""Cálculo de diferencias entre Dixmax, Letterboxd y Serializd.

Cada diferencia es un dict:
  id, seccion, categoria, titulo, detalle, enlaces, opciones [{clave, texto, fase}], datos
La web local las muestra y deja elegir una opción por diferencia.
"""
import math
from collections import defaultdict

from . import dixmax, letterboxd, movies, shows
from .config import rules
from .serializd import Serializd

IGNORAR = {"clave": "ignorar", "texto": "Ignorar", "fase": 1}
STARS = lambda r10: r10 / 2 if r10 else None  # noqa: E731


def _lbname(f):
    return f"{f['name']} ({f['year']})" if f["year"] else f["name"]


def peliculas(dx, lb):
    r = rules().get("peliculas", {})
    ign_lb = set(r.get("ignorar_solo_letterboxd", []))
    ign_dx = set(r.get("ignorar_solo_dixmax", []))
    revisionar = set(r.get("vistas_pero_pendientes_en_dixmax", []))
    pairs, solo_dx, solo_lb = movies.match(dx["movies"], lb["films"])
    out = []

    def add(cat, titulo, detalle, opciones, datos, enlaces=None):
        out.append({"id": f"p{len(out)}", "seccion": "Películas", "categoria": cat, "titulo": titulo,
                    "detalle": detalle, "enlaces": enlaces or {}, "opciones": opciones + [IGNORAR], "datos": datos})

    log_lb = {"clave": "lb_log", "texto": "Registrar en Letterboxd (diario con fecha y nota de Dixmax)", "fase": 3}
    wl_lb = {"clave": "lb_watchlist", "texto": "Añadir a la watchlist de Letterboxd", "fase": 3}
    for m, f in pairs:
        links = {"Dixmax": m["url"], "Letterboxd": f.get("uri")}
        name = f"{m['title']} ({m['year']}) = {_lbname(f)}"
        datos = {"dx": m, "lb": f}
        if m["status"] == "watched" and not f["watched"]:
            add("Vista en Dixmax, no en Letterboxd", name, f"Vista el {(m['date'] or '')[:10]}", [log_lb], datos, links)
        elif m["status"] == "watchlist" and f["watched"] and _lbname(f) not in revisionar:
            add("Vista en Letterboxd, pendiente en Dixmax", name, f"Letterboxd: {f['rating']}★" if f["rating"] else "",
                [{"clave": "dx_vista", "texto": "Marcar como vista en Dixmax", "fase": 2}], datos, links)
        elif m["status"] == "watchlist" and not f["watchlist"] and not f["watched"]:
            add("Pendiente en Dixmax, no en watchlist de Letterboxd", name, "", [wl_lb], datos, links)
        if m["status"] == "watched" and f["watched"]:
            if m["rating10"] and STARS(m["rating10"]) != f["rating"]:
                add("Nota distinta", name, f"Dixmax {m['rating10']} ({STARS(m['rating10'])}★) · Letterboxd {f['rating']}★",
                    [{"clave": "nota_dx_a_lb", "texto": "Poner la nota de Dixmax en Letterboxd", "fase": 3},
                     {"clave": "nota_lb_a_dx", "texto": "Poner la nota de Letterboxd en Dixmax", "fase": 2}], datos, links)
            elif not m["rating10"] and f["rating"]:
                add("Nota solo en Letterboxd", name, f"Letterboxd {f['rating']}★",
                    [{"clave": "nota_lb_a_dx", "texto": "Poner la nota de Letterboxd en Dixmax", "fase": 2}], datos, links)
            if not f["diary"]:
                add("Sin entrada en el diario de Letterboxd", name, f"Fecha Dixmax {(m['date'] or '')[:10]}",
                    [log_lb], datos, links)
    for m in solo_dx:
        name = f"{m['title']} ({m['year']})"
        if name in ign_dx:
            continue
        add("Solo en Dixmax", name, "vista" if m["status"] == "watched" else "pendiente",
            [log_lb if m["status"] == "watched" else wl_lb], {"dx": m}, {"Dixmax": m["url"]})
    for f in solo_lb:
        if _lbname(f) in ign_lb:
            continue
        add("Solo en Letterboxd", _lbname(f), "vista" if f["watched"] else "watchlist",
            [{"clave": "dx_buscar", "texto": "Añadir en Dixmax (te doy el enlace de búsqueda)", "fase": 2}],
            {"lb": f}, {"Letterboxd": f.get("uri")})
    return out


def series(dx, sz, progress=print):
    r = rules().get("series", {})
    excl = set(r.get("excluir_tmdb", []))
    extra = defaultdict(set)
    for x in r.get("extra_serializd", []):
        for e in x["episodios"]:
            extra[x["tmdb"]].add((x["temporada"], e))
    progress("Serializd: leyendo diario…")
    diary = sz.diary()
    progress("Serializd: leyendo listas y notas…")
    lists = {k: sz.list_items(k) for k in ("watched", "watchlist", "watching", "dropped")}
    show_reviews = defaultdict(dict)
    for x in sz.ratings():
        show_reviews[x["showId"]][x["id"]] = x
    sz_eps = defaultdict(set)
    season_num = {}
    for d in diary:
        if d.get("seasonId") is None and d.get("episodeNumber") is None:  # registro de serie
            show_reviews[d["showId"]][d["id"]] = d
        for s in d.get("showSeasons", []):
            season_num[s["id"]] = s["seasonNumber"]
        if d.get("episodeNumber") is not None:
            sz_eps[d["showId"]].add((d["seasonId"], d["episodeNumber"]))

    out = []

    def add(cat, show, detalle, opciones, datos):
        resumen = {k: show.get(k) for k in ("id", "tmdb", "title", "status", "rating10", "rating_date", "favorite", "mark_date")}
        resumen["last_date"] = max([e["date"] for e in show["episodes"]] or [show.get("mark_date") or ""]) or None
        resumen["sz_reviews"] = list(show_reviews.get(show["tmdb"], {}).values())
        out.append({"id": f"s{len(out)}", "seccion": "Series", "categoria": cat, "titulo": show["title"],
                    "detalle": detalle, "enlaces": {"Dixmax": show.get("url"),
                                                    "Serializd": f"https://www.serializd.com/show/{show['tmdb']}"},
                    "opciones": opciones + [IGNORAR], "datos": {**datos, "show": resumen}})

    dshows = [s for s in dx["shows"] if s["tmdb"] not in excl]
    for i, show in enumerate(dshows, 1):
        if i % 25 == 0:
            progress(f"Series: {i}/{len(dshows)}")
        tid = show["tmdb"]
        if show["episodes"]:
            mapped, modo, sin = shows.map_show(sz, show)
            have = sz_eps.get(tid, set())
            falta = [e for e in mapped if (e["sz_season_id"], e["sz_episode"]) not in have]
            if falta:
                add("Episodios sin subir a Serializd", show,
                    f"{len(falta)} episodios (p. ej. {', '.join('S%02dE%02d' % (e['sz_season'], e['sz_episode']) for e in falta[:5])})",
                    [{"clave": "sz_subir_eps", "texto": "Subir a Serializd con fecha de Dixmax", "fase": 2}],
                    {"tmdb": tid, "episodios": falta})
            want = {(e["sz_season_id"], e["sz_episode"]) for e in mapped}
            sobra = [(season_num.get(s, "?"), e) for s, e in have - want
                     if (season_num.get(s), e) not in extra.get(tid, set())]
            if sobra:
                add("Episodios en Serializd que no están en Dixmax", show,
                    f"{len(sobra)} (p. ej. {', '.join('S%sE%s' % x for x in sorted(sobra, key=str)[:5])})",
                    [{"clave": "dx_marcar_eps", "texto": "Marcarlos como vistos en Dixmax", "fase": 2}],
                    {"tmdb": tid, "episodios": sobra})
            sin = [x for x in sin if x not in set(r.get("sin_equivalencia_esperada", {}).get(str(tid), []))]
            if sin:
                add("Episodios sin equivalencia (revisar reglas)", show, f"{len(sin)}: {' '.join(sin[:8])}", [],
                    {"tmdb": tid, "modo": modo})
        # estado
        en = {k for k, v in lists.items() if tid in v}
        logs = [x for x in show_reviews.get(tid, {}).values() if x.get("isLog")]
        st = show["status"]
        esperado = {"watching": "watching", "watchlist": "watchlist", "dropped": "dropped"}.get(st)
        if esperado and esperado not in en:
            add("Estado distinto", show, f"Dixmax: {st} · Serializd: {', '.join(sorted(en)) or 'nada'}",
                [{"clave": "sz_estado", "texto": f"Poner en Serializd como '{st}'", "fase": 2}], {"tmdb": tid, "estado": st})
        if st == "finished" and not logs:
            add("Terminada en Dixmax sin registro de serie en Serializd", show, "",
                [{"clave": "sz_terminar", "texto": "Marcar terminada en Serializd (temporadas + registro + nota)", "fase": 2}],
                {"tmdb": tid})
        # nota (Serializd: entero 1-10, redondeo hacia abajo)
        if show["rating10"]:
            esperada = math.floor(show["rating10"])
            notas = {x["rating"] for x in show_reviews.get(tid, {}).values() if x.get("rating")}
            if notas and esperada not in notas:
                add("Nota de serie distinta", show, f"Dixmax {show['rating10']} → {esperada} · Serializd {sorted(notas)}",
                    [{"clave": "sz_nota", "texto": "Poner la nota de Dixmax en Serializd", "fase": 2},
                     {"clave": "dx_nota", "texto": "Poner la nota de Serializd en Dixmax", "fase": 2}], {"tmdb": tid})
            elif not notas:
                add("Nota de serie sin subir a Serializd", show, f"Dixmax {show['rating10']} → {esperada}",
                    [{"clave": "sz_nota", "texto": "Subir la nota a Serializd", "fase": 2}], {"tmdb": tid})
    sz.flush()
    dx_ids = {s["tmdb"] for s in dx["shows"]} | excl
    for k, v in lists.items():
        for tid, it in v.items():
            if tid not in dx_ids:
                out.append({"id": f"s{len(out)}", "seccion": "Series", "categoria": "Solo en Serializd",
                            "titulo": it["name"], "detalle": f"lista: {k}",
                            "enlaces": {"Serializd": f"https://www.serializd.com/show/{tid}"},
                            "opciones": [{"clave": "dx_buscar", "texto": "Añadir en Dixmax (enlace de búsqueda)", "fase": 2}, IGNORAR],
                            "datos": {"tmdb": tid, "lista": k}})
    return out


def compute(progress=print, solo=None):
    progress("Leyendo export de Dixmax…")
    dx = dixmax.load()
    res = {"fuentes": {"dixmax": dx["export"]}, "diferencias": []}
    if solo in (None, "peliculas"):
        progress("Leyendo export de Letterboxd…")
        lb = letterboxd.load()
        res["fuentes"]["letterboxd"] = lb["export"]
        progress("Cruzando películas…")
        res["diferencias"] += peliculas(dx, lb)
    if solo in (None, "series"):
        sz = Serializd()
        res["fuentes"]["serializd"] = sz.check()
        res["diferencias"] += series(dx, sz, progress)
    return res
