"""Estadísticas y curiosidades de todo tu historial, y las novedades entre una revisión y la anterior.

Al revisar se guarda una «foto» de tus datos (cache/base_stats.json). Las estadísticas se calculan en segundo plano
con esa foto y las fichas de cada título (core/metadatos.py) y se guardan en cache/estadisticas.json.

Qué se cuenta y de dónde (sin sumar dos veces lo mismo):
- Pelis vistas, pendientes, notas y favoritas: Dixmax. Fechas de cuándo viste cada peli: diario de Letterboxd.
- Series y episodios (con fecha y hora): Dixmax. Anime = series de Dixmax que también están en AniList.
- Las pelis de anime cuentan como pelis y también en «anime».
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import cache_json, save_cache

TZ = ZoneInfo("Europe/Madrid")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
IDIOMAS = {"en": "inglés", "es": "español", "ja": "japonés", "fr": "francés", "ko": "coreano", "it": "italiano",
           "de": "alemán", "zh": "chino", "cn": "chino", "pt": "portugués", "ru": "ruso", "hi": "hindi", "sv": "sueco",
           "da": "danés", "no": "noruego", "nl": "neerlandés", "pl": "polaco", "tr": "turco", "fa": "persa",
           "th": "tailandés", "ca": "catalán", "eu": "euskera", "gl": "gallego", "ar": "árabe", "he": "hebreo",
           "el": "griego", "fi": "finés", "is": "islandés", "hu": "húngaro", "cs": "checo", "ro": "rumano"}
GENEROS = {"Action": "Acción", "Adventure": "Aventura", "Animation": "Animación", "Comedy": "Comedia", "Crime": "Crimen",
           "Documentary": "Documental", "Drama": "Drama", "Family": "Familia", "Fantasy": "Fantasía", "History": "Historia",
           "Horror": "Terror", "Music": "Música", "Mystery": "Misterio", "Romance": "Romance", "Science Fiction": "Ciencia ficción",
           "TV Movie": "Telefilm", "Thriller": "Suspense", "War": "Bélica", "Western": "Western", "Sci-Fi & Fantasy": "Ciencia ficción y fantasía",
           "Action & Adventure": "Acción y aventura", "War & Politics": "Bélica y política", "Kids": "Infantil", "Reality": "Telerrealidad",
           "Soap": "Telenovela", "Talk": "Entrevistas", "News": "Noticias", "Sci-Fi": "Ciencia ficción", "Supernatural": "Sobrenatural",
           "Slice of Life": "Recuentos de la vida", "Psychological": "Psicológico", "Sports": "Deportes", "Mecha": "Mecha",
           "Ecchi": "Ecchi", "Mahou Shoujo": "Chicas mágicas", "Hentai": "Hentai"}
BASE, SALIDA = "base_stats.json", "estadisticas.json"
RT_SERIE, RT_ANIME = 42, 24  # minutos por episodio si no se sabe


def _local(iso):
    try:
        return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    except (TypeError, ValueError):
        return None


def _fecha(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _n(x):
    return f"{x:,}".replace(",", ".")


def _horas(minutos):
    return f"{_n(round(minutos / 60))} h"


# ---------------- foto de los datos (al revisar) ----------------
def guardar_base(dx, lb=None, sz_stats=None):
    base = {
        "pelis": [{"id": m["id"], "tmdb": m.get("tmdb"), "t": m["title"], "y": m.get("year"), "st": m["status"],
                   "d": m.get("date"), "r": m.get("rating10"), "fav": bool(m.get("favorite"))} for m in dx["movies"]],
        "series": [{"id": s["id"], "tmdb": s["tmdb"], "t": s["title"], "y": s.get("year"), "st": s["status"],
                    "r": s.get("rating10"), "fav": bool(s.get("favorite")),
                    "eps": [[e["season"], e["episode"], e.get("date"), bool(e.get("fecha_aproximada"))]
                            for e in s["episodes"] if e["season"] > 0]} for s in dx["shows"]],
        "lb": [{"t": f["name"], "y": f["year"], "w": f["watched"], "r": f.get("rating"), "like": f["like"],
                "diario": [[x["date"], bool(x.get("rewatch"))] for x in f["diary"] if x.get("date")]}
               for f in (lb or {}).get("films", [])],
        "al": {str(k): {"st": v["status"], "p": v.get("progress"), "r": v.get("score")}
               for k, v in (dx.get("al_lista") or {}).items()},
        "anime": {str(k): v for k, v in (dx.get("anime_al") or {}).items()},  # id de Dixmax -> id de AniList
        "sz": {k: v for k, v in (sz_stats or {}).items() if k.startswith("sz_")},
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    save_cache(BASE, base)


def _episodios_reales(series):
    """Episodios con fecha y hora fiables: fuera los marcados en bloque (muchos en el mismo minuto) y los aproximados."""
    por_minuto, eps = Counter(), []
    for s in series:
        for se, ep, f, aprox in s["eps"]:
            d = _local(f)
            if d and not aprox:
                eps.append((s, se, ep, d))
                por_minuto[(s["id"], d.strftime("%Y%m%d%H%M"))] += 1
    return [x for x in eps if por_minuto[(x[0]["id"], x[3].strftime("%Y%m%d%H%M"))] <= 3]


def _es(counter):
    out = Counter()
    for k, v in counter.items():
        out[GENEROS.get(k, k)] += v
    return out


def _top(counter, n=15, ejemplos=None):
    return [{"k": k, "n": v, "e": (ejemplos or {}).get(k, [])[:5]} for k, v in counter.most_common(n)]


# ---------------- cálculo ----------------
def calcular(progress=print):
    from . import metadatos
    b = cache_json(BASE, None)
    if not b:
        return None
    pelis, series, lbf = b["pelis"], b["series"], b["lb"]
    vistas = [m for m in pelis if m["st"] == "watched"]
    con_eps = [s for s in series if s["eps"]]
    anime_ids = set(b["anime"])
    es_anime = lambda s: str(s["id"]) in anime_ids  # noqa: E731

    mp = metadatos.pelis([m["tmdb"] for m in vistas], progress)
    pp = metadatos.paises_pelis([m["tmdb"] for m in vistas], progress)
    ms = metadatos.series([s["tmdb"] for s in con_eps if not es_anime(s)], progress)
    ma = metadatos.anime([b["anime"][str(s["id"])] for s in con_eps if es_anime(s)], progress)
    progress("Estadísticas: calculando…")
    meta_p = lambda m: mp.get(str(m["tmdb"])) if isinstance(mp.get(str(m["tmdb"])), dict) else {}  # noqa: E731
    meta_s = lambda s: (ma.get(str(b["anime"][str(s["id"])])) if es_anime(s) else ms.get(str(s["tmdb"]))) or {}  # noqa: E731
    meta_s2 = lambda s: meta_s(s) if isinstance(meta_s(s), dict) else {}  # noqa: E731

    # ---------- horas ----------
    min_pelis = sum(meta_p(m).get("rt") or 0 for m in vistas)
    sin_rt_p = sum(1 for m in vistas if not meta_p(m).get("rt"))
    min_series = min_anime = 0
    for s in con_eps:
        rt = meta_s2(s).get("rt") or (RT_ANIME if es_anime(s) else RT_SERIE)
        if es_anime(s):
            min_anime += rt * len(s["eps"])
        else:
            min_series += rt * len(s["eps"])
    eps_total = sum(len(s["eps"]) for s in series)
    eps_anime = sum(len(s["eps"]) for s in series if es_anime(s))

    # ---------- resumen ----------
    diario_todo = [(f, d, rw) for f in lbf for d, rw in f["diario"]]
    # días en que importaste tu historial a Letterboxd (muchas pelis con la misma fecha): no son fechas reales
    por_dia_lb = Counter(d for _, d, _ in diario_todo)
    importados = {d: n for d, n in por_dia_lb.items() if n > 8}
    diario = [x for x in diario_todo if x[1] not in importados]
    nota_imp = (" · sin las " + _n(sum(importados.values())) + " importadas de golpe") if importados else ""
    paises_todos = set()
    resumen = [
        {"t": "Películas vistas", "v": _n(len(vistas)), "s": f"{_horas(min_pelis)} · {_n(sum(1 for m in pelis if m['st'] == 'watchlist'))} pendientes", "c": "lb"},
        {"t": "Diario de Letterboxd", "v": _n(len(diario_todo)), "s": f"{sum(1 for _, _, rw in diario_todo if rw)} revisionados · {sum(1 for f in lbf if f['like'])} me gusta", "c": "lb"},
        {"t": "Episodios de series", "v": _n(eps_total - eps_anime), "s": f"{_horas(min_series)} · {sum(1 for s in series if s['st'] == 'finished' and not es_anime(s))} series terminadas", "c": "sz"},
        {"t": "Episodios de anime", "v": _n(eps_anime), "s": f"{_horas(min_anime)} · {sum(1 for s in series if s['st'] == 'finished' and es_anime(s))} animes terminados", "c": "al"},
        {"t": "Frente a la pantalla", "v": f"{_n(round((min_pelis + min_series + min_anime) / 60 / 24))} días",
         "s": f"{_horas(min_pelis + min_series + min_anime)} en total (aprox.)", "c": "dx"},
    ]

    # ---------- mapa ----------
    mapa = {k: defaultdict(lambda: {"n": 0, "top": Counter()}) for k in ("todo", "pelis", "series", "anime")}

    def poner(tipo, pais, titulo, peso=1):
        for k in (tipo, "todo"):
            mapa[k][pais]["n"] += 1
            mapa[k][pais]["top"][titulo] += peso
    for m in vistas:
        for p in set(pp.get(str(m["tmdb"])) or []):
            poner("pelis", p, m["t"], (m["r"] or 5))
            paises_todos.add(p)
    for s in con_eps:
        d = meta_s2(s)
        ps = [d["pais"]] if isinstance(d.get("pais"), str) else d.get("pais") or []
        for p in set(ps):
            poner("anime" if es_anime(s) else "series", p, s["t"], len(s["eps"]))
            paises_todos.add(p)
    mapa_out = {k: {p: {"n": v["n"], "top": [t for t, _ in v["top"].most_common(5)]} for p, v in d.items()}
                for k, d in mapa.items()}
    resumen.append({"t": "Países", "v": str(len(paises_todos)), "s": "de origen de lo que has visto", "c": "dx"})

    # ---------- personas, estudios, sagas, géneros ----------
    dirs, cast, estudios, sagas, ej = Counter(), Counter(), Counter(), defaultdict(list), defaultdict(list)
    for m in vistas:
        d = meta_p(m)
        for x in d.get("dir", []):
            dirs[x] += 1
            ej["d:" + x].append(m["t"])
        for x in d.get("cast", [])[:5]:
            cast[x] += 1
            ej["a:" + x].append(m["t"])
        if d.get("st"):
            estudios[d["st"]] += 1
            ej["e:" + d["st"]].append(m["t"])
        if d.get("col"):
            sagas[d["col"].replace(" Collection", "").replace(" - Colección", "")].append(m["t"])
    for s in con_eps:
        if es_anime(s):
            for x in meta_s2(s).get("st", []):
                estudios[x] += 1
                ej["e:" + x].append(s["t"])
    resumen.append({"t": "Directores", "v": _n(len(dirs)), "s": f"{_n(len(cast))} actores en los repartos", "c": "lb"})
    pref = lambda p: {k[2:]: v for k, v in ej.items() if k.startswith(p)}  # noqa: E731
    g_pelis = Counter(g for m in vistas for g in meta_p(m).get("g", []))
    g_series = Counter(g for s in con_eps if not es_anime(s) for g in meta_s2(s).get("g", []))
    g_anime = Counter(g for s in con_eps if es_anime(s) for g in meta_s2(s).get("g", []))
    redes = Counter(r for s in con_eps if not es_anime(s) for r in meta_s2(s).get("red", [])[:1])
    ej_red = defaultdict(list)
    for s in con_eps:
        if not es_anime(s):
            for r in meta_s2(s).get("red", [])[:1]:
                ej_red[r].append(s["t"])
    idiomas = Counter(IDIOMAS.get(meta_p(m).get("lang"), meta_p(m).get("lang")) for m in vistas if meta_p(m).get("lang"))
    sagas_top = sorted(sagas.items(), key=lambda kv: -len(kv[1]))[:15]
    tops = {
        "directores": _top(dirs, 15, pref("d:")), "actores": _top(cast, 15, pref("a:")),
        "estudios": _top(estudios, 15, pref("e:")),
        "sagas": [{"k": k, "n": len(v), "e": v[:6]} for k, v in sagas_top if len(v) > 1],
        "generos_pelis": _top(_es(g_pelis), 12), "generos_series": _top(_es(g_series), 12), "generos_anime": _top(_es(g_anime), 12),
        "cadenas": _top(redes, 12, ej_red), "idiomas": _top(idiomas, 10),
    }

    # ---------- actividad ----------
    reales = _episodios_reales(series)
    semana = [[0] * 24 for _ in range(7)]
    for _, _, _, d in reales:
        semana[d.weekday()][d.hour] += 1
    anio_mes = defaultdict(lambda: [0] * 12)  # películas (diario de Letterboxd) + episodios
    for _, d, _ in diario:
        anio_mes[d[:4]][int(d[5:7]) - 1] += 1
    for _, _, _, d in reales:
        anio_mes[str(d.year)][d.month - 1] += 1

    # ---------- tu año ----------
    anios = {}
    rt_de = {}
    for f in lbf:
        rt_de[(f["t"], f["y"])] = None
    pelis_anio = defaultdict(list)
    for f, d, rw in diario:
        pelis_anio[d[:4]].append((d, f["t"], f["y"], f.get("r"), rw))
    eps_anio = defaultdict(Counter)
    for s, _, _, d in reales:
        eps_anio[str(d.year)][s["t"]] += 1
    vistos_antes = set()
    for y in sorted(set(pelis_anio) | set(eps_anio)):
        pa = sorted(pelis_anio.get(y, []))
        ea = eps_anio.get(y, Counter())
        mejor = max((p for p in pa if p[3]), key=lambda p: p[3], default=None)
        nuevas = [t for t in ea if t not in vistos_antes]
        vistos_antes |= set(ea)
        anios[y] = {"pelis": len(pa), "revisionados": sum(1 for p in pa if p[4]), "episodios": sum(ea.values()),
                    "series": len(ea), "series_nuevas": len(nuevas),
                    "top_series": [{"k": k, "n": v} for k, v in ea.most_common(5)],
                    "mejor_peli": f"{mejor[1]} ({mejor[2]}) · {mejor[3]:g}★" if mejor else None,
                    "primera": f"{pa[0][1]} ({pa[0][0][8:10]}/{pa[0][0][5:7]})" if pa else None,
                    "ultima": f"{pa[-1][1]} ({pa[-1][0][8:10]}/{pa[-1][0][5:7]})" if pa else None,
                    "meses": anio_mes.get(y, [0] * 12)}

    # ---------- gráficos ----------
    graficos = []
    por_anio = Counter(d[:4] for _, d, _ in diario)
    if por_anio:
        graficos.append({"titulo": "Películas vistas por año", "nota": "según el diario de Letterboxd" + nota_imp, "c": "lb",
                         "datos": sorted(por_anio.items())})
    ep_anio = Counter(str(d.year) for _, _, _, d in reales)
    if ep_anio:
        graficos.append({"titulo": "Episodios vistos por año", "nota": "Dixmax, sin los marcados de golpe", "c": "sz",
                         "datos": sorted(ep_anio.items())})
    decada = Counter(f"{int(m['y']) // 10 * 10}s" for m in vistas if str(m.get("y") or "").isdigit())
    if decada:
        graficos.append({"titulo": "Películas por década de estreno", "c": "lb", "datos": sorted(decada.items())})
    durs = [meta_p(m).get("rt") for m in vistas if meta_p(m).get("rt")]
    if durs:
        tramos = [("<80", 0, 80), ("80-99", 80, 100), ("100-119", 100, 120), ("120-139", 120, 140), ("140-159", 140, 160),
                  ("160-179", 160, 180), ("180+", 180, 10 ** 4)]
        graficos.append({"titulo": "Duración de las películas", "nota": "minutos", "c": "lb",
                         "datos": [(k, sum(1 for x in durs if a <= x < z)) for k, a, z in tramos]})
    notas = Counter(f["r"] for f in lbf if f.get("r"))
    if notas:
        graficos.append({"titulo": "Tus notas en Letterboxd", "nota": "estrellas", "c": "lb",
                         "datos": [(f"{k:g}★", notas.get(k, 0)) for k in [x / 2 for x in range(1, 11)]]})
    nal = Counter(round(v["r"]) for v in b["al"].values() if v.get("r"))
    if nal:
        graficos.append({"titulo": "Tus notas en AniList", "c": "al", "datos": [(str(k), nal.get(k, 0)) for k in range(1, 11)]})
    top_series = sorted(con_eps, key=lambda s: -len(s["eps"]))[:10]
    graficos.append({"titulo": "Series con más episodios vistos", "c": "sz", "horizontal": True,
                     "datos": [(s["t"], len(s["eps"])) for s in top_series]})

    # ---------- curiosidades ----------
    cur = []
    if reales:
        por_dia = defaultdict(list)
        for s, _, _, d in reales:
            por_dia[d.date()].append(s["t"])
        dmax = max(por_dia, key=lambda k: len(por_dia[k]))
        cur.append(f"🍿 Tu mayor maratón: **{len(por_dia[dmax])} episodios** el {_fecha(dmax)}, sobre todo de *{Counter(por_dia[dmax]).most_common(1)[0][0]}*.")
        dias = sorted(por_dia)
        mejor = actual = 1
        fin_mejor = dias[0]
        for a, c in zip(dias, dias[1:]):
            actual = actual + 1 if c - a == timedelta(days=1) else 1
            if actual > mejor:
                mejor, fin_mejor = actual, c
        cur.append(f"🔥 Racha más larga: **{mejor} días seguidos** viendo episodios (hasta el {_fecha(fin_mejor)}).")
        dia = Counter(d.weekday() for _, _, _, d in reales).most_common(1)[0][0]
        noche = sum(1 for _, _, _, d in reales if d.hour < 6)
        cur.append(f"🗓️ Tu día favorito para ver series es el **{DIAS[dia]}**; el {round(100 * noche / len(reales))}% de los episodios los marcas de madrugada (0-6 h).")
    if diario:
        por_dia_p = Counter(d for _, d, _ in diario)
        dd, nn = por_dia_p.most_common(1)[0]
        if nn > 1:
            cur.append(f"🎬 Tu día más peliculero: **{nn} películas** el {_fecha(datetime.strptime(dd, '%Y-%m-%d'))}.")
        d0 = min(diario, key=lambda x: x[1])
        cur.append(f"📖 Tu diario de Letterboxd (fechas reales) empieza el {_fecha(datetime.strptime(d0[1], '%Y-%m-%d'))} con *{d0[0]['t']}*.")
    if importados:
        fs = [_fecha(datetime.strptime(d, '%Y-%m-%d')) for d in sorted(importados)]
        cur.append(f"📥 El {fs[0] if len(fs) == 1 else ', el '.join(fs[:-1]) + ' y el ' + fs[-1]} importaste {_n(sum(importados.values()))} pelis de golpe a Letterboxd: no cuentan para fechas y rachas.")
    con_rt = [(meta_p(m)["rt"], m) for m in vistas if meta_p(m).get("rt")]
    if con_rt:
        lg, cr = max(con_rt, key=lambda x: x[0]), min(con_rt, key=lambda x: x[0])
        cur.append(f"⏱️ La peli más larga que has visto: *{lg[1]['t']}* ({lg[0]} min); la más corta, *{cr[1]['t']}* ({cr[0]} min).")
    con_anio = [m for m in vistas if str(m.get("y") or "").isdigit()]
    if con_anio:
        vieja = min(con_anio, key=lambda m: int(m["y"]))
        cur.append(f"🎞️ La película más antigua que has visto: *{vieja['t']}* ({vieja['y']}).")
    if dirs:
        dk, dn = dirs.most_common(1)[0]
        cur.append(f"🎥 Tu director más visto: **{dk}**, con {dn} películas.")
    if cast:
        ak, an = cast.most_common(1)[0]
        cur.append(f"⭐ El actor que más te encuentras: **{ak}**, en {an} películas.")
    if sagas_top:
        cur.append(f"📚 La saga de la que más has visto: **{sagas_top[0][0]}** ({len(sagas_top[0][1])} películas).")
    finished = [s for s in series if s["st"] == "finished"]
    if finished:
        s = max(finished, key=lambda s: len(s["eps"]))
        cur.append(f"📺 La serie más larga que has terminado: *{s['t']}*, con {len(s['eps'])} episodios.")
    lb_notas = [f["r"] for f in lbf if f.get("r")]
    if lb_notas:
        cur.append(f"⭐ Nota media en Letterboxd: **{sum(lb_notas) / len(lb_notas):.2f}★** en {len(lb_notas)} pelis.")
    notas_dx = [m["r"] for m in vistas if m.get("r")]
    if notas_dx:
        cur.append(f"💯 En Dixmax has puesto un 10 a {sum(1 for n in notas_dx if n >= 10)} películas (nota media {sum(notas_dx) / len(notas_dx):.1f}).")
    sc = [v["r"] for v in b["al"].values() if v.get("r")]
    if sc:
        cur.append(f"🎌 Nota media en AniList: **{sum(sc) / len(sc):.1f}** en {len(sc)} animes.")
    if idiomas:
        no_en = sum(v for k, v in idiomas.items() if k != "inglés")
        cur.append(f"🌍 El {round(100 * no_en / sum(idiomas.values()))}% de tus pelis no son en inglés; tras el inglés, el idioma que más ves es el **{next((k for k, _ in idiomas.most_common() if k != 'inglés'), '—')}**.")
    if b["sz"].get("sz_diario"):
        cur.append(f"📝 Llevas {_n(b['sz']['sz_diario'])} registros en el diario de Serializd.")
    if sin_rt_p:
        cur.append(f"ℹ️ Las horas son aproximadas: {sin_rt_p} pelis no tienen duración conocida y los episodios sin dato cuentan como {RT_SERIE} min (anime {RT_ANIME}).")

    out = {"resumen": resumen, "mapa": mapa_out, "semana": semana, "anios": anios, "tops": tops, "graficos": graficos,
           "curiosidades": cur, "calculado": b["fecha"]}
    save_cache(SALIDA, out)
    return out


# ---------------- novedades entre revisiones ----------------
SNAP = "instantanea.json"


def _instantanea(dx):
    return {
        "pelis": {str(m["id"]): [m["title"], m["status"], m.get("rating10"), bool(m.get("favorite"))] for m in dx["movies"]},
        "series": {str(s["id"]): [s["title"], s["status"], s.get("rating10"), bool(s.get("favorite")),
                                  sorted(e["season"] * 10000 + e["episode"] for e in s["episodes"])] for s in dx["shows"]},
    }


def _rango(nums):
    t = [f"T{n // 10000}E{n % 10000}" for n in sorted(nums)]
    return t[0] if len(t) == 1 else f"{t[0]}–{t[-1]}" if len(t) <= 30 else f"{t[0]}–{t[-1]} ({len(t)})"


def novedades(dx):
    """Lo que ha cambiado en tus webs desde la revisión anterior (para el historial)."""
    nueva = _instantanea(dx)
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
