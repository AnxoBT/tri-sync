"""Estadísticas y curiosidades de todo tu historial, y las novedades entre una revisión y la anterior.

Se calcula al revisar (con los datos que ya se han leído) y se guarda en cache/estadisticas.json.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import CACHE, cache_json, save_cache

TZ = ZoneInfo("Europe/Madrid")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _local(iso):
    try:
        return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    except (TypeError, ValueError):
        return None


def _fecha(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _n(x):
    return f"{x:,}".replace(",", ".")


def _episodios_reales(shows):
    """Episodios con fecha fiable: fuera los marcados en bloque (muchos en el mismo minuto) y las fechas aproximadas."""
    por_minuto = Counter()
    eps = []
    for s in shows:
        for e in s["episodes"]:
            d = _local(e.get("date"))
            if d and not e.get("fecha_aproximada") and e["season"] > 0:
                eps.append((s, e, d))
                por_minuto[(s["id"], d.strftime("%Y%m%d%H%M"))] += 1
    return [(s, e, d) for s, e, d in eps if por_minuto[(s["id"], d.strftime("%Y%m%d%H%M"))] <= 3]


def calcular(dx, lb=None, sz_stats=None, al_lista=None, anime_ids=None):
    movies, shows = dx["movies"], dx["shows"]
    vistas = [m for m in movies if m["status"] == "watched"]
    eps_todos = sum(1 for s in shows for e in s["episodes"] if e["season"] > 0)
    reales = _episodios_reales(shows)
    anime_ids = anime_ids or set()
    resumen, graficos, curiosidades = [], [], []

    # ---------- resumen ----------
    resumen.append({"t": "Películas vistas", "v": _n(len(vistas)), "s": f"{_n(sum(1 for m in movies if m['status'] == 'watchlist'))} pendientes", "c": "dx"})
    terminadas = sum(1 for s in shows if s["status"] == "finished")
    resumen.append({"t": "Series", "v": _n(terminadas), "s": f"terminadas · {sum(1 for s in shows if s['status'] == 'watching')} siguiendo", "c": "sz"})
    resumen.append({"t": "Episodios vistos", "v": _n(eps_todos), "s": "en Dixmax", "c": "dx"})
    if anime_ids:
        an = [s for s in shows if s["id"] in anime_ids]
        resumen.append({"t": "Anime", "v": _n(sum(1 for s in an if s["status"] == "finished")),
                        "s": f"series terminadas · {_n(sum(1 for s in an for e in s['episodes'] if e['season'] > 0))} episodios", "c": "al"})
    if lb:
        diario = [(f, x) for f in lb["films"] for x in f["diary"] if x.get("date")]
        resumen.append({"t": "Diario de Letterboxd", "v": _n(len(diario)), "s": f"{sum(1 for _, x in diario if x['rewatch'])} revisionados · {sum(1 for f in lb['films'] if f['like'])} me gusta", "c": "lb"})
    favs = sum(1 for m in movies if m.get("favorite")) + sum(1 for s in shows if s.get("favorite"))
    resumen.append({"t": "Favoritas", "v": _n(favs), "s": "pelis y series en Dixmax", "c": "dx"})

    # ---------- gráficos ----------
    if lb:
        por_anio = Counter(x["date"][:4] for f in lb["films"] for x in f["diary"] if x.get("date"))
        if por_anio:
            graficos.append({"titulo": "Películas vistas por año", "nota": "según el diario de Letterboxd",
                             "c": "lb", "datos": sorted(por_anio.items())})
    ep_anio = Counter(str(d.year) for _, _, d in reales)
    if ep_anio:
        graficos.append({"titulo": "Episodios vistos por año", "nota": "Dixmax, sin los marcados de golpe",
                         "c": "sz", "datos": sorted(ep_anio.items())})
    if reales:
        dia = Counter(d.weekday() for _, _, d in reales)
        graficos.append({"titulo": "¿Qué día ves más episodios?", "c": "sz",
                         "datos": [(DIAS[i][:3], dia.get(i, 0)) for i in range(7)]})
        hora = Counter(d.hour for _, _, d in reales)
        graficos.append({"titulo": "¿A qué hora?", "nota": "hora a la que marcaste el episodio", "c": "sz",
                         "datos": [(f"{h}h", hora.get(h, 0)) for h in range(24)]})
    decada = Counter(f"{int(m['year']) // 10 * 10}s" for m in vistas if str(m.get("year") or "").isdigit())
    if decada:
        graficos.append({"titulo": "Películas vistas por década de estreno", "c": "dx", "datos": sorted(decada.items())})
    if lb:
        notas = Counter(f["rating"] for f in lb["films"] if f.get("rating"))
        if notas:
            graficos.append({"titulo": "Tus notas en Letterboxd", "nota": "estrellas", "c": "lb",
                             "datos": [(f"{k:g}★", notas.get(k, 0)) for k in [x / 2 for x in range(1, 11)]]})
    top = sorted(shows, key=lambda s: -sum(1 for e in s["episodes"] if e["season"] > 0))[:10]
    if top:
        graficos.append({"titulo": "Series con más episodios vistos", "c": "sz", "horizontal": True,
                         "datos": [(s["title"], sum(1 for e in s["episodes"] if e["season"] > 0)) for s in top]})

    # ---------- curiosidades ----------
    if reales:
        por_dia = defaultdict(list)
        for s, e, d in reales:
            por_dia[d.date()].append(s["title"])
        dmax = max(por_dia, key=lambda k: len(por_dia[k]))
        serie = Counter(por_dia[dmax]).most_common(1)[0][0]
        curiosidades.append(f"🍿 Tu mayor maratón: **{len(por_dia[dmax])} episodios** el {_fecha(dmax)}, sobre todo de *{serie}*.")
        dias = sorted(por_dia)
        mejor = actual = 1
        fin_mejor = dias[0]
        for a, b in zip(dias, dias[1:]):
            actual = actual + 1 if b - a == timedelta(days=1) else 1
            if actual > mejor:
                mejor, fin_mejor = actual, b
        curiosidades.append(f"🔥 Racha más larga: **{mejor} días seguidos** viendo episodios (hasta el {_fecha(fin_mejor)}).")
        mes = Counter((d.year, d.month) for _, _, d in reales).most_common(1)[0]
        curiosidades.append(f"📅 Tu mes con más episodios: **{MESES[mes[0][1] - 1]} de {mes[0][0]}** ({mes[1]}).")
        dia = Counter(d.weekday() for _, _, d in reales).most_common(1)[0][0]
        noche = sum(1 for _, _, d in reales if d.hour < 6)
        curiosidades.append(f"🗓️ Tu día favorito para ver series es el **{DIAS[dia]}**; "
                            f"el {round(100 * noche / len(reales))}% de los episodios los marcas de madrugada (0-6 h).")
    largas = [s for s in shows if s["status"] == "finished"]
    if largas:
        s = max(largas, key=lambda s: sum(1 for e in s["episodes"] if e["season"] > 0))
        curiosidades.append(f"📺 La serie más larga que has terminado: *{s['title']}*, con {sum(1 for e in s['episodes'] if e['season'] > 0)} episodios.")
    con_anio = [m for m in vistas if str(m.get("year") or "").isdigit()]
    if con_anio:
        vieja = min(con_anio, key=lambda m: int(m["year"]))
        curiosidades.append(f"🎞️ La película más antigua que has visto: *{vieja['title']}* ({vieja['year']}).")
    if lb:
        diario = sorted((x["date"], f["name"]) for f in lb["films"] for x in f["diary"] if x.get("date"))
        if diario:
            d0 = datetime.strptime(diario[0][0], "%Y-%m-%d")
            curiosidades.append(f"📖 Tu diario de Letterboxd empieza el {_fecha(d0)} con *{diario[0][1]}*.")
        rew = Counter((f["name"], f["year"]) for f in lb["films"] for x in f["diary"] if x.get("date"))
        if rew and rew.most_common(1)[0][1] > 1:
            (t, y), n = rew.most_common(1)[0]
            curiosidades.append(f"🔁 La peli que más veces has registrado: *{t}* ({y}), {n} veces.")
        lb_notas = [f["rating"] for f in lb["films"] if f.get("rating")]
        if lb_notas:
            curiosidades.append(f"⭐ Nota media en Letterboxd: **{sum(lb_notas) / len(lb_notas):.2f}★** en {len(lb_notas)} pelis.")
    notas_dx = [m["rating10"] for m in vistas if m.get("rating10")]
    if notas_dx:
        diez = sum(1 for n in notas_dx if n >= 10)
        curiosidades.append(f"💯 En Dixmax has puesto un 10 a {diez} películas (nota media {sum(notas_dx) / len(notas_dx):.1f}).")
    if anime_ids and shows:
        pct = round(100 * sum(1 for s in shows if s["id"] in anime_ids) / len(shows))
        curiosidades.append(f"⛩️ El {pct}% de las series que tienes en Dixmax son anime.")
    if al_lista:
        sc = [e["score"] for e in al_lista.values() if e.get("score")]
        if sc:
            curiosidades.append(f"🎌 Nota media en AniList: **{sum(sc) / len(sc):.1f}** en {len(sc)} animes.")
    if sz_stats and sz_stats.get("sz_diario"):
        curiosidades.append(f"📝 Llevas {_n(sz_stats['sz_diario'])} registros en el diario de Serializd.")

    return {"resumen": resumen, "graficos": graficos, "curiosidades": curiosidades,
            "calculado": datetime.now().strftime("%d/%m/%Y %H:%M")}


# ---------- novedades entre revisiones ----------
SNAP = "instantanea.json"


def _instantanea(dx, al_lista=None):
    return {
        "pelis": {str(m["id"]): [m["title"], m["status"], m.get("rating10"), bool(m.get("favorite"))] for m in dx["movies"]},
        "series": {str(s["id"]): [s["title"], s["status"], s.get("rating10"), bool(s.get("favorite")),
                                  sorted(e["season"] * 10000 + e["episode"] for e in s["episodes"])] for s in dx["shows"]},
        "anilist": {str(k): [v["status"], v.get("progress")] for k, v in (al_lista or {}).items()},
    }


def _rango(nums):
    t = [f"T{n // 10000}E{n % 10000}" for n in sorted(nums)]
    return t[0] if len(t) == 1 else f"{t[0]}–{t[-1]}" if len(t) <= 30 else f"{t[0]}–{t[-1]} ({len(t)})"


def novedades(dx, al_lista=None):
    """Lo que ha cambiado en tus webs desde la revisión anterior (para el historial)."""
    nueva = _instantanea(dx, al_lista)
    vieja = cache_json(SNAP, None)
    save_cache(SNAP, nueva)
    if not vieja:
        return []
    out = []
    est = {"watched": "vista", "watchlist": "pendiente", "finished": "terminada", "watching": "siguiendo",
           "dropped": "abandonada"}
    for k, (t, st, nota, fav) in nueva["pelis"].items():
        a = vieja["pelis"].get(k)
        if not a:
            out.append(f"🎬 {t}: añadida como {est.get(st, st)}" + (f", nota {nota:g}" if nota else ""))
            continue
        if a[1] != st:
            out.append(f"🎬 {t}: {est.get(a[1], a[1])} → {est.get(st, st)}")
        if a[2] != nota and nota:
            out.append(f"🎬 {t}: nota {a[2] or '—'} → {nota:g}")
        if fav and not a[3]:
            out.append(f"🎬 {t}: ♥ favorita")
    for k, (t, st, nota, fav, eps) in nueva["series"].items():
        a = vieja["series"].get(k)
        if not a:
            out.append(f"📺 {t}: añadida como {est.get(st, st)}" + (f" ({len(eps)} episodios)" if eps else ""))
            continue
        mas = set(eps) - set(a[4])
        if mas:
            out.append(f"📺 {t}: +{len(mas)} episodio{'s' if len(mas) > 1 else ''} ({_rango(mas)})")
        if a[1] != st:
            out.append(f"📺 {t}: {est.get(a[1], a[1])} → {est.get(st, st)}")
        if a[2] != nota and nota:
            out.append(f"📺 {t}: nota {a[2] or '—'} → {nota:g}")
        if fav and not a[3]:
            out.append(f"📺 {t}: ♥ favorita")
    return out[:300]
