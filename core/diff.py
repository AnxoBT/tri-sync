"""Cálculo de diferencias entre Dixmax, Letterboxd, Serializd y AniList.

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


def lb_url(m):
    """Enlace a la ficha de la peli en Letterboxd sin API: por TMDB o IMDb (Letterboxd redirige a la ficha),
    por la ficha que da Wikidata, o como último recurso una búsqueda."""
    if m.get("tmdb"):
        return f"https://letterboxd.com/tmdb/{m['tmdb']}/"
    if m.get("lb_slug"):
        return f"https://letterboxd.com/film/{m['lb_slug']}/"
    if str(m.get("imdb") or "").startswith("tt"):
        return f"https://letterboxd.com/imdb/{m['imdb']}/"
    from urllib.parse import quote
    q = f"{m['title']} {m.get('year') or ''}".strip()
    return f"https://letterboxd.com/search/films/{quote(q)}/"


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
        links = {"Dixmax": m["url"], "Letterboxd": f.get("uri") or lb_url(m)}
        name = f"{m['title']} ({m['year']}) = {_lbname(f)}"
        datos = {"dx": m, "lb": f}
        if m["status"] == "watched" and not f["watched"]:
            add("Vista en Dixmax, no en Letterboxd", name, f"Vista el {(m['date'] or '')[:10]}" + (" (fecha aproximada: Dixmax no la dio)" if m.get("fecha_aproximada") else ""), [log_lb], datos, links)
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
            if f["like"] and not m["favorite"]:
                add("Me gusta en Letterboxd, no favorita en Dixmax", name, "En Dixmax «Favorita» sustituye a «Vista» (sigue en tu lista de vistas)",
                    [{"clave": "dx_favorita", "texto": "Marcar como favorita en Dixmax", "fase": 2}], datos, links)
            elif m["favorite"] and not f["like"]:
                add("Favorita en Dixmax, sin me gusta en Letterboxd", name, "Letterboxd no permite importar «me gusta»: ponlo con el enlace",
                    [], datos, links)
            if not f["diary"]:
                add("Sin entrada en el diario de Letterboxd", name, f"Fecha Dixmax {(m['date'] or '')[:10]}",
                    [log_lb], datos, links)
    for m in solo_dx:
        name = f"{m['title']} ({m['year']})"
        if name in ign_dx:
            continue
        add("Solo en Dixmax", name, "vista" if m["status"] == "watched" else "pendiente",
            [log_lb if m["status"] == "watched" else wl_lb], {"dx": m}, {"Dixmax": m["url"], "Letterboxd": lb_url(m)})
    for f in solo_lb:
        if _lbname(f) in ign_lb:
            continue
        add("Solo en Letterboxd", _lbname(f), "vista" if f["watched"] else "watchlist",
            [{"clave": "dx_buscar", "texto": "Añadir en Dixmax (te doy el enlace de búsqueda)", "fase": 2}],
            {"lb": f}, {"Letterboxd": f.get("uri")})
    return out


def leer_serializd(sz, rapida=False):
    """Lanza en segundo plano la lectura de Serializd (diario, listas, notas). Devuelve los futuros."""
    from concurrent.futures import ThreadPoolExecutor
    ex = ThreadPoolExecutor(6)
    pre = {"diario": ex.submit(sz.diary, rapida), "notas": ex.submit(sz.ratings),
           "listas": {k: ex.submit(sz.list_items, k) for k in ("watched", "watchlist", "watching", "dropped")}}
    ex.shutdown(wait=False)
    return pre


def series(dx, sz, progress=print, rapida=False, pre=None):
    r = rules().get("series", {})
    excl = set(r.get("excluir_tmdb", []))
    extra = defaultdict(set)
    for x in r.get("extra_serializd", []):
        for e in x["episodios"]:
            extra[x["tmdb"]].add((x["temporada"], e))
    progress("Serializd: leyendo diario, listas y notas a la vez…")
    pre = pre or leer_serializd(sz, rapida)
    diary = pre["diario"].result()
    lists = {k: f.result() for k, f in pre["listas"].items()}
    ratings = pre["notas"].result()
    show_reviews = defaultdict(dict)
    for x in ratings:
        show_reviews[x["showId"]][x["id"]] = x
    dx["sz_favs"] = {tid for tid, v in show_reviews.items() if any(x.get("like") for x in v.values())}
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
        resumen = {k: show.get(k) for k in ("id", "tmdb", "title", "status", "rating10", "rating_date", "favorite", "mark_date",
                                            "mark", "mark_unix")}
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
        have = sz_eps.get(tid, set())
        if have and dx.get("api") and not show.get("_api"):
            # ¿Serializd tiene episodios que el export de Dixmax no? Puede que el export sea antiguo:
            # se pregunta a la API de Dixmax solo por esta serie antes de dar la diferencia.
            want0 = {(e["sz_season_id"], e["sz_episode"]) for e in shows.map_show(sz, show)[0]} if show["episodes"] else set()
            if any((season_num.get(s), e) not in extra.get(tid, set()) for s, e in have - want0):
                progress(f"Dixmax: comprobando por la API {show['title']}…")
                dixmax.episodios_api(dx["api"], show)
        if show["episodes"]:
            mapped, modo, sin = shows.map_show(sz, show)
            falta = [e for e in mapped if (e["sz_season_id"], e["sz_episode"]) not in have]
            if falta:
                aprox = sum(1 for e in show["episodes"] if e.get("fecha_aproximada"))
                add("Episodios sin subir a Serializd", show,
                    f"{len(falta)} episodios (p. ej. {', '.join('S%02dE%02d' % (e['sz_season'], e['sz_episode']) for e in falta[:5])})"
                    + (f" · {aprox} con fecha aproximada (Dixmax no la dio)" if aprox else ""),
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
        # un solo estado en Serializd, el de Dixmax. Ojo: «watched» en Serializd son las TEMPORADAS terminadas y se pone
        # solo al marcar todos sus episodios; convive con viendo/abandonada y no se quita nunca (quitarla borra los ✓ de
        # los episodios y la serie desaparece de «Continúa viendo»).
        esperado = {"watching": "watching", "watchlist": "watchlist", "dropped": "dropped", "finished": "watched"}.get(st)
        quitar = {k: lists[k][tid].get("seasons") or [] for k in en if k not in (esperado, "watched")}
        NOM = {"watched": "vista", "watching": "viendo", "watchlist": "pendiente", "dropped": "abandonada"}
        if esperado and (esperado not in en and (st != "finished" or logs)):
            add("Estado distinto", show, f"Dixmax: {NOM[esperado]} · Serializd: {', '.join(NOM[k] for k in sorted(en)) or 'nada'}",
                [{"clave": "sz_estado", "texto": f"Dejarla solo como '{NOM[esperado]}' en Serializd", "fase": 2}],
                {"tmdb": tid, "estado": esperado, "quitar": quitar})
        elif esperado in en and quitar:
            add("Varios estados a la vez en Serializd", show,
                f"Dixmax: {NOM[esperado]} · Serializd: {', '.join(NOM[k] for k in sorted(en))}",
                [{"clave": "sz_estado", "texto": f"Dejarla solo como '{NOM[esperado]}' (quitar {', '.join(NOM[k] for k in quitar)})", "fase": 2}],
                {"tmdb": tid, "estado": esperado, "quitar": {**quitar, esperado: []}})
        if st == "finished" and logs:
            liked = any(x.get("like") for x in logs)
            if show.get("favorite") and not liked:
                add("Favorita en Dixmax, sin ♥ en Serializd", show, "",
                    [{"clave": "sz_like", "texto": "Poner ♥ al registro de serie en Serializd", "fase": 2}], {"tmdb": tid})
            elif liked and not show.get("favorite"):
                add("♥ en Serializd, no favorita en Dixmax", show, "En Dixmax «Favorita» sustituye a «Vista»",
                    [{"clave": "dx_favorita", "texto": "Marcar como favorita en Dixmax", "fase": 2}], {"tmdb": tid})
        if st == "finished" and not logs:
            add("Terminada en Dixmax sin registro de serie en Serializd", show, "",
                [{"clave": "sz_terminar", "texto": "Marcar terminada en Serializd (temporadas + registro + nota)", "fase": 2}],
                {"tmdb": tid, "quitar": {k: v for k, v in quitar.items() if k != "watched"}})
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
    dixmax.guardar_eps_api()
    STATS["sz_diario"] = len(diary)
    STATS["sz_vistas"] = len(lists["watched"])
    STATS["sz_favoritas"] = sum(1 for v in show_reviews.values() for x in v.values() if x.get("isLog") and x.get("like"))
    dx_ids = {s["tmdb"] for s in dx["shows"]} | excl
    dx["sz_en_listas"] = {tid for v in lists.values() for tid in v}  # para cruzar AniList con Serializd
    import time
    hoy = time.strftime("%Y-%m-%d")
    for k, v in lists.items():
        for tid, it in v.items():
            if tid not in dx_ids:
                est = sz.estreno(tid)
                if not est or est > hoy:  # aún no se ha estrenado: Dixmax no suele tener ficha; se ignora hasta entonces
                    continue
                out.append({"id": f"s{len(out)}", "seccion": "Series", "categoria": "Solo en Serializd",
                            "titulo": it["name"], "detalle": f"lista: {k}",
                            "enlaces": {"Serializd": f"https://www.serializd.com/show/{tid}"},
                            "opciones": [{"clave": "dx_buscar", "texto": "Añadir en Dixmax (enlace de búsqueda)", "fase": 2}, IGNORAR],
                            "datos": {"tmdb": tid, "lista": k}})
    return out


STATS = {}


def _stats_dx(dx):
    from collections import Counter
    pm = Counter(m["status"] for m in dx["movies"])
    ps = Counter(s["status"] for s in dx["shows"])
    return {"dx_pelis_vistas": pm["watched"], "dx_pelis_pendientes": pm["watchlist"],
            "dx_pelis_favoritas": sum(1 for m in dx["movies"] if m["favorite"]),
            "dx_series_terminadas": ps["finished"], "dx_series_siguiendo": ps["watching"],
            "dx_series_pendientes": ps["watchlist"], "dx_series_favoritas": sum(1 for s in dx["shows"] if s["favorite"]),
            "dx_episodios": sum(len(s["episodes"]) for s in dx["shows"])}


def compute(progress=print, solo=None, rapida=False):
    """Revisa solo las apps conectadas (Configuración). Dixmax es el centro: sin él no hay con qué comparar."""
    from .config import apps, dixmax_api as config_dixmax_api, find_exports
    ap = apps()
    if ap["letterboxd"] and solo in (None, "peliculas") and not find_exports("letterboxd-"):
        progress("Letterboxd: no hay export (descárgalo e impórtalo); de momento se revisa lo demás")
        ap["letterboxd"] = False
    if not ap["dixmax"]:
        raise RuntimeError("Conecta Dixmax en Configuración: todo se compara con lo que tienes en Dixmax")
    if solo is None and not (ap["letterboxd"] or ap["serializd"] or ap["anilist"]):
        raise RuntimeError("Conecta al menos una app más (Letterboxd, Serializd o AniList) en Configuración")
    hacer = lambda k, app: solo in (None, k) and ap[app]  # noqa: E731
    sz = pre = None
    if hacer("series", "serializd"):  # Serializd se va leyendo mientras se lee Dixmax
        sz = Serializd()
        sz.check()
        pre = leer_serializd(sz, rapida)
    progress("Leyendo export de Dixmax…")
    dx = dixmax.load()
    fuente_dx = dx["export"]
    from .config import env
    if config_dixmax_api():
        progress("Dixmax: leyendo estado actual por la API…")
        dx = dixmax.apply_live(dx, progress, rapida=rapida)
        fuente_dx += " + API en directo"
    STATS.clear()
    STATS.update(_stats_dx(dx))
    res = {"fuentes": {"dixmax": fuente_dx}, "diferencias": [], "modo": "rápida" if rapida else "completa"}
    lb = None
    if hacer("peliculas", "letterboxd"):
        progress("Leyendo export de Letterboxd…")
        lb = letterboxd.load()
        res["fuentes"]["letterboxd"] = lb["export"]
        progress("Cruzando películas…")
        res["diferencias"] += peliculas(dx, lb)
        STATS.update(lb_vistas=sum(1 for f in lb["films"] if f["watched"]), lb_watchlist=sum(1 for f in lb["films"] if f["watchlist"]),
                     lb_me_gusta=sum(1 for f in lb["films"] if f["like"]), lb_diario=sum(len(f["diary"]) for f in lb["films"]))
    if hacer("series", "serializd"):
        res["fuentes"]["serializd"] = sz.user
        res["diferencias"] += series(dx, sz, progress, rapida=rapida, pre=pre)
    if hacer("anime", "anilist"):
        from . import anime
        try:
            difs, st = anime.diferencias(dx, progress)
            res["diferencias"] += difs
            STATS.update(st)
            res["fuentes"]["anilist"] = env("ANILIST_USER")
        except Exception as e:  # AniList caído no debe estropear el resto de la revisión
            progress(f"AniList: no se pudo revisar ({e})")
            res["fuentes"]["anilist"] = f"error: {e}"
    res["stats"] = dict(STATS)
    if solo is None:  # estadísticas y novedades solo con la revisión entera
        from . import estadisticas
        try:
            estadisticas.guardar_base(dx, lb, STATS)  # las estadísticas se calculan luego, en segundo plano
            res["novedades"] = estadisticas.novedades(dx)
        except Exception as e:  # una curiosidad que falle no debe tumbar la revisión
            progress(f"Estadísticas: no se pudieron calcular ({e})")
    return res
