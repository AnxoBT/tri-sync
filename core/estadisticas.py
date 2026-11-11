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

from .config import cache_json, rules, save_cache

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


def _dia(d):
    """Día de visionado: lo de madrugada (antes de las 6) cuenta para el día anterior."""
    return (d - timedelta(hours=6)).date()


def _racha(dias):
    """Días seguidos más largos de un conjunto de fechas: (n, último día)."""
    dias = sorted(dias)
    mejor = actual = 1
    fin = dias[0]
    for a, b in zip(dias, dias[1:]):
        actual = actual + 1 if b - a == timedelta(days=1) else 1
        if actual > mejor:
            mejor, fin = actual, b
    return mejor, fin


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


def _episodios_reales(series, dur=lambda s: RT_SERIE, reales=(), falsas=()):
    """Episodios con fecha fiable para maratones, rachas y horarios.

    Las marcas en tanda (más de 3 en el mismo minuto) son de dos tipos: importar de golpe lo que ya habías visto
    (Friends entera en un minuto) o marcar al final de una sesión lo que acabas de ver. Una tanda cuenta como vista ese
    día si es creíble: todo lo marcado en tanda ese día (de todas las series) cabe en 16 h. rules.json > estadisticas >
    tandas_reales / tandas_falsas lo fuerza por serie (p. ej. One Piece, aunque sean 100 capítulos en un día)."""
    eps, por_min = [], Counter()
    for s in series:
        for se, ep, f, aprox in s["eps"]:
            d = _local(f)
            if d and not aprox:
                eps.append((s, se, ep, d))
                por_min[(s["id"], d.strftime("%Y%m%d%H%M"))] += 1
    tanda = lambda x: por_min[(x[0]["id"], x[3].strftime("%Y%m%d%H%M"))] > 3  # noqa: E731
    carga = Counter()  # minutos marcados en tanda cada día (sin las series forzadas)
    for x in eps:
        if tanda(x) and x[0]["t"] not in reales and x[0]["t"] not in falsas:
            carga[_dia(x[3])] += dur(x[0])

    def vale(x):
        if not tanda(x):
            return True
        if x[0]["t"] in reales:  # forzada, salvo en días de importación masiva (lo demás de ese día ya pasa de 16 h)
            return carga[_dia(x[3])] <= 16 * 60
        return x[0]["t"] not in falsas and carga[_dia(x[3])] <= 16 * 60
    return [x for x in eps if vale(x)]


def _es(counter):
    out = Counter()
    for k, v in counter.items():
        out[GENEROS.get(k, k)] += v
    return out


def _norm(s):
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _paises_es():
    import json
    from .config import ROOT
    m = json.loads((ROOT / "web" / "mundo.json").read_text(encoding="utf-8"))
    d = {_norm(p["n"]): p["c"] for p in m["paises"]}
    # nombres que Dixmax escribe distinto
    d.update({_norm(k): v for k, v in {"Estados Unidos": "US", "Reino Unido": "GB", "Corea del Sur": "KR", "Rusia": "RU",
                                        "Irán": "IR", "Unión Soviética": "RU", "URSS": "RU", "Alemania del Oeste (RFA)": "DE",
                                        "Alemania del Este (RDA)": "DE", "Checoslovaquia": "CZ", "Yugoslavia": "RS",
                                        "Hong Kong": "HK", "Taiwán": "TW", "República Checa": "CZ", "Chequia": "CZ",
                                        "Unión Soviética (URSS)": "RU", "Paquistán": "PK", "Emiratos Árabes": "AE"}.items()})
    return d


def _top(counter, n=15, ejemplos=None):
    return [{"k": k, "n": v, "e": (ejemplos or {}).get(k, [])[:5]} for k, v in counter.most_common(n)]


# ---------------- cálculo ----------------
# Tipos: "pelis" (todas las películas, también las de anime), "series" (sin anime) y "anime" (series de anime).
# Cada tipo tiene su resumen y sus bloques; «todo» junta lo general (resumen, mapa, tu año, cuándo ves, curiosidades).

def _bloque(id_, titulo, forma, datos, nota="", c="dx", ancho=1, dest=False):
    """forma: barras (k, n, v, e) · columnas ([etiqueta, n]) · lista (k, v, d)"""
    return {"id": id_, "titulo": titulo, "forma": forma, "datos": datos, "nota": nota, "c": c, "ancho": ancho, "dest": dest}


def _barras(counter, n=12, ejemplos=None, fmt=None):
    return [{"k": k, "n": v, "v": fmt(v) if fmt else None, "e": (ejemplos or {}).get(k, [])[:5]} for k, v in counter.most_common(n)]


def _dinero(x):
    if x >= 1e9:
        return f"{x / 1e9:.2f} mil M$".replace(".", ",")
    if x >= 1e7:
        return f"{round(x / 1e6)} M$"
    if x >= 1e6:
        return f"{x / 1e6:.1f} M$".replace(".", ",")
    return f"{round(x / 1e3)} mil $"


def _votos(n):
    return f"{_n(n)} voto{'' if n == 1 else 's'}"


def _media(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def calcular(progress=print):
    from . import metadatos
    b = cache_json(BASE, None)
    if not b:
        return None
    pelis, series, lbf = b["pelis"], b["series"], b["lb"]
    vistas = [m for m in pelis if m["st"] == "watched"]
    # fichas de Dixmax de todo (país principal, géneros, reparto…): la primera vez tarda, luego va de caché
    md = metadatos.fichas_dixmax([m["id"] for m in pelis] + [s["id"] for s in series], progress)
    D = lambda s: md.get(str(s["id"])) or {}  # noqa: E731
    anime_ids = set(b["anime"])
    ASIA = {"Japón", "China", "Corea del Sur", "Taiwán", "Hong Kong"}

    def es_anime(s):
        """Anime = lo que cruza con AniList, lo que Dixmax etiqueta como Anime, o animación de Japón/China/Corea/Taiwán."""
        g = D(s).get("g") or []
        return str(s["id"]) in anime_ids or "Anime" in g or ("Animación" in g and D(s).get("pais") in ASIA)
    con_eps = [s for s in series if s["eps"]]
    ser = [s for s in con_eps if not es_anime(s)]
    ani = [s for s in con_eps if es_anime(s)]
    al_de = lambda s: b["anime"].get(str(s["id"]))  # noqa: E731

    mp = metadatos.pelis([m["tmdb"] for m in vistas], progress)
    pp = metadatos.paises_pelis([m["tmdb"] for m in pelis], progress)
    pd = metadatos.dinero([m["tmdb"] for m in vistas], progress)
    ms = metadatos.series([s["tmdb"] for s in series if not es_anime(s)], progress)
    ma = metadatos.anime([al_de(s) for s in ani if al_de(s)], progress)
    mt = metadatos.tvmaze([s["tmdb"] for s in ser], progress)
    progress("Estadísticas: calculando…")
    P = lambda m: mp.get(str(m["tmdb"])) if isinstance(mp.get(str(m["tmdb"])), dict) else {}  # noqa: E731
    S = lambda s: ms.get(str(s["tmdb"])) if isinstance(ms.get(str(s["tmdb"])), dict) else {}  # noqa: E731
    A = lambda s: (ma.get(str(al_de(s))) or {}) if al_de(s) else {}  # noqa: E731
    TV = lambda s: mt.get(str(s["tmdb"])) or {}  # noqa: E731
    neps = lambda s: len(s["eps"])  # noqa: E731
    tit = lambda m: f"{m['t']} ({m['y']})" if m.get("y") else m["t"]  # noqa: E731

    # ---------- horas ----------
    min_p = sum(P(m).get("rt") or 0 for m in vistas)
    min_s = sum((S(s).get("rt") or D(s).get("dur") or RT_SERIE) * neps(s) for s in ser)
    min_a = sum((A(s).get("rt") or D(s).get("dur") or RT_ANIME) * neps(s) for s in ani)
    eps_s, eps_a = sum(map(neps, ser)), sum(map(neps, ani))

    # ---------- mapa: país principal de producción ----------
    # pelis: Dixmax (criterio FilmAffinity/TMDB); si no lo da, Wikidata cuando hay uno solo.
    # anime: AniList (countryOfOrigin; Dixmax pone Japón a donghuas como To Be Hero X).
    # series: país de origen de TMDB (Dixmax a veces pone el de rodaje: See, El simpatizante → Canadá).
    nombres = _paises_es()

    def pais(x, peli):
        dx = nombres.get(_norm(D(x).get("pais") or ""))
        if peli:
            if dx:
                return dx
            w = pp.get(str(x["tmdb"])) or []
            return w[0] if len(set(w)) == 1 else None
        if es_anime(x):
            return A(x).get("pais") or dx
        w = S(x).get("pais") or []
        if len(w) == 1 or (w and dx not in w):
            return w[0]
        return dx
    ESTADOS = ("vistas", "terminadas", "siguiendo", "pendientes", "favoritas", "todas")
    mapa = {k: {e: defaultdict(lambda: {"n": 0, "top": Counter()}) for e in ESTADOS} for k in ("todo", "pelis", "series", "anime")}

    def poner(tipo, estados, iso, titulo, peso):
        for k in (tipo, "todo"):
            for e in estados:
                mapa[k][e][iso]["n"] += 1
                mapa[k][e][iso]["top"][titulo] += peso
    for m in pelis:
        iso = pais(m, True)
        if iso:
            est = {"watched": ["vistas", "terminadas"], "watchlist": ["pendientes"]}.get(m["st"], []) + ["todas"] + (["favoritas"] if m.get("fav") else [])
            poner("pelis", est, iso, m["t"], (m["r"] or 5) + (5 if m.get("fav") else 0))
    for s in series:
        iso = pais(s, False)
        if iso:
            est = (["vistas"] if s["eps"] else []) + {"finished": ["terminadas"], "watching": ["siguiendo"], "watchlist": ["pendientes"]}.get(s["st"], []) \
                + ["todas"] + (["favoritas"] if s.get("fav") else [])
            poner("anime" if es_anime(s) else "series", est, iso, s["t"], neps(s) + 1)
    mapa_out = {k: {e: {p: {"n": v["n"], "top": [t for t, _ in v["top"].most_common(5)]} for p, v in d.items()} for e, d in ee.items()}
                for k, ee in mapa.items()}

    # ---------- resumen general (una línea, sin subtítulos) ----------
    resumen = [
        {"t": "Películas", "v": _n(len(vistas)), "c": "lb"},
        {"t": "Series", "v": _n(len(ser)), "c": "sz"},
        {"t": "Animes", "v": _n(len(ani)), "c": "al"},
        {"t": "Episodios", "v": _n(eps_s + eps_a), "c": "sz"},
        {"t": "Horas", "v": _n(round((min_p + min_s + min_a) / 60)), "c": "dx"},
        {"t": "Países", "v": str(len(mapa_out["todo"]["vistas"])), "c": "dx"},
    ]

    # ================= PELÍCULAS =================
    ej = defaultdict(list)
    dirs, cast, est, sagas, notas_dir = Counter(), Counter(), Counter(), defaultdict(list), defaultdict(list)
    for m in vistas:
        d = P(m)
        for x in d.get("dir", []):
            dirs[x] += 1
            ej["d" + x].append(m["t"])
            if m.get("r"):
                notas_dir[x].append(m["r"])
        for x in d.get("cast", [])[:5]:
            cast[x] += 1
            ej["a" + x].append(m["t"])
        if d.get("st"):
            est[d["st"]] += 1
            ej["e" + d["st"]].append(m["t"])
        if d.get("col"):
            sagas[d["col"].replace(" Collection", "")].append(m["t"])
    sub = lambda p: {k[1:]: v for k, v in ej.items() if k[0] == p}  # noqa: E731
    gen_p = _es(Counter(g for m in vistas for g in P(m).get("g", [])))
    idi = Counter(IDIOMAS.get(P(m)["lang"], P(m)["lang"]) for m in vistas if P(m).get("lang"))
    con_votos = sorted([m for m in vistas if P(m).get("imdb_n")], key=lambda m: P(m)["imdb_n"])
    vs_gente = [(m["r"] - P(m)["imdb_r"], m) for m in vistas if m.get("r") and P(m).get("imdb_r") and P(m).get("imdb_n", 0) >= 5000]
    def _din(m):
        c_, t_, mundo = (pd.get(str(m["tmdb"])) or [None, None, False]) + [False] * 0
        if t_ and not mundo and P(m).get("lang") not in (None, "en"):
            t_ = None  # sin marca de «mundial» y no es en inglés: suele ser solo la taquilla de EE. UU.
        return m, c_, t_
    din = [_din(m) for m in vistas]
    caras = sorted([x for x in din if x[1]], key=lambda x: -x[1])
    taq = sorted([x for x in din if x[2]], key=lambda x: -x[2])
    # recaudó al menos un 5 % de lo que costó: si no, casi seguro fue un estreno de plataforma (El irlandés…)
    ratio = sorted([x for x in din if x[1] and x[2] and x[1] >= 1e6 and x[2] >= 0.05 * x[1]], key=lambda x: -x[2] / x[1])
    mejor_dir = sorted(((k, _media(v), len(v)) for k, v in notas_dir.items() if len(v) >= 3), key=lambda x: -x[1])[:10]
    diario_todo = [(f, d, rw) for f in lbf for d, rw in f["diario"]]
    importados = {d for d, n in Counter(d for _, d, _ in diario_todo).items() if n > 8}  # importaciones en bloque
    diario = [x for x in diario_todo if x[1] not in importados]
    durs = [P(m)["rt"] for m in vistas if P(m).get("rt")]
    tramos = [("<80", 0, 80), ("80-99", 80, 100), ("100-119", 100, 120), ("120-139", 120, 140), ("140-159", 140, 160),
              ("160-179", 160, 180), ("180+", 180, 10 ** 4)]
    nota_p = _media([m["r"] for m in vistas])
    favs_p = sorted([m for m in pelis if m.get("fav")], key=lambda m: -(m.get("r") or 0))
    gen_fav = _es(Counter(g for m in favs_p for g in P(m).get("g", [])))
    dir_fav = Counter(x for m in favs_p for x in P(m).get("dir", []))
    pel = {
        "resumen": [{"t": "Vistas", "v": _n(len(vistas))}, {"t": "Horas", "v": _n(round(min_p / 60))},
                    {"t": "Nota media", "v": f"{nota_p:.1f}" if nota_p else "—"}, {"t": "Favoritas", "v": _n(len(favs_p))},
                    {"t": "Pendientes", "v": _n(sum(1 for m in pelis if m["st"] == "watchlist"))}, {"t": "Países", "v": str(len(mapa_out["pelis"]["vistas"]))}],
        "bloques": [
            _bloque("dir", "Directores que más ves", "barras", _barras(dirs, 12, sub("d")), "películas", "lb", dest=True),
            _bloque("cast", "Actores que más te encuentras", "barras", _barras(cast, 12, sub("a")), "5 primeros del reparto", "lb"),
            _bloque("gen", "Géneros", "barras", _barras(gen_p, 10), "", "lb", dest=True),
            _bloque("favs", "Tus favoritas", "lista", [{"k": tit(m), "v": f"{m['r']:g}" if m.get("r") else "♥"} for m in favs_p[:10]],
                    f"{len(favs_p)} películas con ♥ en Dixmax · las de mejor nota", "lb"),
            _bloque("favgen", "Qué tienen tus favoritas", "barras", _barras(gen_fav, 8), "géneros de tus películas favoritas", "lb"),
            _bloque("favdir", "Directores de tus favoritas", "barras", _barras(dir_fav, 8), "", "lb"),
            _bloque("anio", "Películas por año", "columnas", sorted(Counter(d[:4] for _, d, _ in diario).items()),
                    "diario de Letterboxd" + (" (sin las importadas de golpe)" if importados else ""), "lb", 2),
            _bloque("nicho", "Joyas ocultas", "lista", [{"k": tit(m), "v": _votos(P(m)["imdb_n"])} for m in con_votos[:8]],
                    "las menos votadas en IMDb de las que has visto", "lb", dest=True),
            _bloque("masivas", "Las más populares", "lista", [{"k": tit(m), "v": _votos(P(m)["imdb_n"])} for m in con_votos[::-1][:8]],
                    "las más votadas en IMDb", "lb"),
            _bloque("mas", "Te gustaron más que a la gente", "lista",
                    [{"k": tit(m), "v": f"tú {m['r']:g} · IMDb {P(m)['imdb_r']:g}"} for x, m in sorted(vs_gente, key=lambda x: -x[0])[:8] if x > 0],
                    "tu nota frente a la de IMDb", "lb"),
            _bloque("menos", "Te gustaron menos que a la gente", "lista",
                    [{"k": tit(m), "v": f"tú {m['r']:g} · IMDb {P(m)['imdb_r']:g}"} for x, m in sorted(vs_gente, key=lambda x: x[0])[:8] if x < 0],
                    "", "lb"),
            _bloque("sagas", "Sagas y franquicias", "barras",
                    [{"k": k, "n": len(v), "e": v[:6]} for k, v in sorted(sagas.items(), key=lambda kv: -len(kv[1]))[:10] if len(v) > 1],
                    "películas vistas de cada colección", "lb"),
            _bloque("caras", "Las más caras", "lista", [{"k": tit(m), "v": _dinero(c)} for m, c, _ in caras[:8]], "presupuesto", "lb"),
            _bloque("taquilla", "Las más taquilleras", "lista", [{"k": tit(m), "v": _dinero(t)} for m, _, t in taq[:8]], "taquilla mundial", "lb"),
            _bloque("negocio", "Mejor negocio", "lista",
                    [{"k": tit(m), "v": f"×{t / c:.0f}", "d": f"costó {_dinero(c)}, recaudó {_dinero(t)}"} for m, c, t in ratio[:8]],
                    "veces que recaudó lo que costó", "lb"),
            _bloque("fracasos", "Fracasos en taquilla", "lista",
                    [{"k": tit(m), "v": f"×{t / c:.2f}".replace(".", ","), "d": f"costó {_dinero(c)}, recaudó {_dinero(t)}"}
                     for m, c, t in ratio[::-1][:8] if t < c], "recaudaron menos de lo que costaron", "lb"),
            _bloque("mejordir", "Directores con mejor nota", "barras",
                    [{"k": k, "n": round(v, 1), "v": f"{v:.1f} ({n} pelis)", "e": sub("d").get(k, [])[:5]} for k, v, n in mejor_dir],
                    "tu nota media, con 3 pelis o más", "lb"),
            _bloque("est", "Estudios", "barras", _barras(est, 10, sub("e")), "", "lb"),
            _bloque("idi", "Idiomas", "barras", _barras(idi, 8), "idioma original", "lb"),
            _bloque("dec", "Por década de estreno", "columnas",
                    sorted(Counter(f"{int(m['y']) // 10 * 10}s" for m in vistas if str(m.get("y") or "").isdigit()).items()), "", "lb", 2),
            _bloque("dur", "Duración", "columnas", [(k, sum(1 for x in durs if a <= x < z)) for k, a, z in tramos], "minutos", "lb"),
            _bloque("notas", "Tus notas", "columnas", [(str(k), sum(1 for m in vistas if m.get("r") and round(m["r"]) == k)) for k in range(1, 11)],
                    "Dixmax", "lb"),
        ],
    }

    # ================= SERIES y ANIME =================
    def tipo_series(lista, es_an):
        c = "al" if es_an else "sz"
        todas = [s for s in series if es_anime(s) == es_an]
        favs = sorted([s for s in todas if s.get("fav")], key=lambda s: -(s.get("r") or 0))
        rep, rep_eps, dire, gen, tem, red, ejs = Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), defaultdict(list)
        for s in lista:
            d, x = D(s), (A(s) if es_an else S(s))
            # anime: voces japonesas de los personajes principales y secundarios (AniList, sin los de fondo).
            # series: reparto oficial de TVmaze + invitados acreditados (cameos incluidos) de los episodios que has visto.
            # Si no hay datos, el reparto de la ficha de Dixmax.
            vistos = {f"{se}-{ep}" for se, ep, _, _ in s["eps"]}
            if es_an:
                personas = {p: neps(s) for p in (x.get("voces") or d.get("reparto", []))}
            elif TV(s).get("cast"):
                personas = {p: neps(s) for p in TV(s)["cast"]}
                for k, gs in (TV(s).get("inv") or {}).items():
                    if k in vistos:
                        for p in gs:
                            personas[p] = personas.get(p, 0) + 1
            else:
                personas = {p: neps(s) for p in d.get("reparto", [])}
            for p, n_ep in personas.items():
                rep[p] += 1
                rep_eps[p] += n_ep
                ejs["r" + p].append(s["t"])
            for p in d.get("dir", [])[:2]:
                dire[p] += 1
                ejs["d" + p].append(s["t"])
            for g in ((x.get("g") or d.get("g")) if es_an else (d.get("g") or x.get("g"))) or []:
                gen[GENEROS.get(g, g)] += 1
            for t in d.get("temas", []):
                tem[t] += 1
                ejs["t" + t].append(s["t"])
            for r in (x.get("st") if es_an else x.get("red", [])[:1]) or []:
                red[r] += 1
                ejs["c" + r].append(s["t"])
        sb = lambda p: {k[1:]: v for k, v in ejs.items() if k[0] == p}  # noqa: E731
        if es_an:
            pop = sorted([s for s in lista if A(s).get("pop")], key=lambda s: A(s)["pop"])
            fmt_pop = lambda s: f"{_n(A(s)['pop'])} en AniList"  # noqa: E731
            yo = [(s["r"] - A(s)["media"] / 10, s, A(s)["media"] / 10) for s in lista if s.get("r") and A(s).get("media")]
            gente = "AniList"
        else:
            # TVmaze: popularidad de 0 a 100 (a igualdad, desempatan los votos de Dixmax) y nota media de la gente
            pop = sorted([s for s in lista if TV(s).get("w") is not None], key=lambda s: (TV(s)["w"], D(s).get("votos") or 0))
            fmt_pop = lambda s: f"{TV(s)['w']}/100 en TVmaze"  # noqa: E731
            yo = [(s["r"] - TV(s)["r"], s, TV(s)["r"]) for s in lista if s.get("r") and TV(s).get("r")]
            gente = "TVmaze"
        nota = _media([s["r"] for s in lista])
        mins = (min_a if es_an else min_s)
        nombre = "animes" if es_an else "series"
        return {
            "resumen": [{"t": nombre.capitalize(), "v": _n(len(lista))}, {"t": "Episodios", "v": _n(sum(map(neps, lista)))},
                        {"t": "Horas", "v": _n(round(mins / 60))}, {"t": "Nota media", "v": f"{nota:.1f}" if nota else "—"},
                        {"t": "Favoritas", "v": _n(len(favs))}, {"t": "Pendientes", "v": _n(sum(1 for s in todas if s["st"] == "watchlist"))}],
            "bloques": [
                _bloque("rep", "Actores de doblaje que más oyes" if es_an else "Reparto que más ves", "barras",
                        [{"k": p, "n": rep[p], "v": f"{rep[p]} {nombre if rep[p] > 1 else nombre[:-1]} · {_n(rep_eps[p])} eps", "e": sb("r").get(p, [])[:5]}
                         for p in sorted(rep, key=lambda p: (-rep[p], -rep_eps[p]))[:12]],
                        (f"{nombre} y episodios: voz japonesa de personajes principales y secundarios (AniList)" if es_an
                         else f"{nombre} y episodios en los que sale: reparto oficial e invitados de lo que has visto (TVmaze)"), c, dest=True),
                _bloque("red", "Estudios" if es_an else "Cadenas y plataformas", "barras", _barras(red, 10, sb("c")), "", c, dest=True),
                _bloque("gen", "Géneros", "barras", _barras(gen, 10), "", c),
                _bloque("mas_eps", f"{nombre.capitalize()} con más episodios", "barras",
                        [{"k": s["t"], "n": neps(s)} for s in sorted(lista, key=lambda s: -neps(s))[:10]], "", c),
                _bloque("nicho", "Joyas ocultas", "lista", [{"k": s["t"], "v": fmt_pop(s)} for s in pop[:8]],
                        f"las menos populares en {gente} de las que has visto", c, dest=True),
                _bloque("masivas", "Las más populares", "lista", [{"k": s["t"], "v": fmt_pop(s)} for s in pop[::-1][:8]],
                        "en AniList" if es_an else "en TVmaze (0-100); a igualdad, las más votadas en Dixmax", c),
                _bloque("mas", "Te gustaron más que a la gente", "lista",
                        [{"k": s["t"], "v": f"tú {s['r']:g} · {gente} {g:.1f}"} for x, s, g in sorted(yo, key=lambda x: -x[0])[:8] if x > 0],
                        f"tu nota frente a la media de {gente}", c),
                _bloque("menos", "Te gustaron menos que a la gente", "lista",
                        [{"k": s["t"], "v": f"tú {s['r']:g} · {gente} {g:.1f}"} for x, s, g in sorted(yo, key=lambda x: x[0])[:8] if x < 0], "", c),
                _bloque("favs", "Tus favoritas", "lista", [{"k": s["t"], "v": f"{s['r']:g}" if s.get("r") else "♥"} for s in favs[:10]],
                        f"{len(favs)} con ♥ (favorita en Dixmax)", c),
                _bloque("estados", "En qué punto estás", "barras",
                        [{"k": k, "n": n} for k, n in (("Terminadas", sum(1 for s in todas if s["st"] == "finished")),
                                                       ("Siguiendo", sum(1 for s in todas if s["st"] == "watching")),
                                                       ("Pendientes", sum(1 for s in todas if s["st"] == "watchlist")),
                                                       ("Abandonadas", sum(1 for s in todas if s["st"] == "dropped"))) if n],
                        "según tu marca en Dixmax", c),
                _bloque("temas", "Temas y franquicias", "barras", _barras(tem, 10, sb("t")), "etiquetas de Dixmax", c),
                _bloque("dir", "Dirección", "barras", _barras(dire, 10, sb("d")), "Dixmax", c),
                _bloque("dec", "Por década de estreno", "columnas",
                        sorted(Counter(f"{int(s['y']) // 10 * 10}s" for s in lista if str(s.get("y") or "").isdigit()).items()), "", c, 2),
                _bloque("notas", "Tus notas", "columnas", [(str(k), sum(1 for s in lista if s.get("r") and round(s["r"]) == k)) for k in range(1, 11)],
                        "Dixmax", c),
            ],
        }
    tipos = {"pelis": pel, "series": tipo_series(ser, False), "anime": tipo_series(ani, True)}
    for t in tipos.values():  # fuera los bloques vacíos
        t["bloques"] = [x for x in t["bloques"] if x["datos"] and any((d[1] if isinstance(d, (list, tuple)) else 1) for d in x["datos"])]

    # ---------- actividad (todo) ----------
    reglas = (rules().get("estadisticas") or {})
    reales = _episodios_reales(series, lambda s: (A(s).get("rt") if es_anime(s) else S(s).get("rt")) or D(s).get("dur")
                               or (RT_ANIME if es_anime(s) else RT_SERIE),
                               set(reglas.get("tandas_reales") or []), set(reglas.get("tandas_falsas") or []))
    semana = [[0] * 24 for _ in range(7)]
    for _, _, _, d in reales:
        semana[d.weekday()][d.hour] += 1
    anio_mes = defaultdict(lambda: [0] * 12)
    for _, d, _ in diario:
        anio_mes[d[:4]][int(d[5:7]) - 1] += 1
    for _, _, _, d in reales:
        anio_mes[str(d.year)][d.month - 1] += 1
    pelis_anio = defaultdict(list)
    for f, d, rw in diario:
        pelis_anio[d[:4]].append((d, f["t"], f["y"], f.get("r"), rw))
    eps_anio = defaultdict(Counter)
    for s, _, _, d in reales:
        eps_anio[str(d.year)][s["t"]] += 1
    anios, vistos_antes = {}, set()
    for y in sorted(set(pelis_anio) | set(eps_anio)):
        pa, ea = sorted(pelis_anio.get(y, [])), eps_anio.get(y, Counter())
        mejor = max((p for p in pa if p[3]), key=lambda p: p[3], default=None)
        nuevas = [t for t in ea if t not in vistos_antes]
        vistos_antes |= set(ea)
        anios[y] = {"pelis": len(pa), "episodios": sum(ea.values()), "series": len(ea), "series_nuevas": len(nuevas),
                    "top_series": [{"k": k, "n": v} for k, v in ea.most_common(5)],
                    "mejor_peli": f"{mejor[1]} ({mejor[2]}) · {mejor[3]:g}★" if mejor else None,
                    "primera": f"{pa[0][1]} ({pa[0][0][8:10]}/{pa[0][0][5:7]})" if pa else None,
                    "ultima": f"{pa[-1][1]} ({pa[-1][0][8:10]}/{pa[-1][0][5:7]})" if pa else None,
                    "meses": anio_mes.get(y, [0] * 12)}

    # ---------- curiosidades (tarjetas: t = qué, v = dato, d = detalle, c = tipo) ----------
    cur = []

    def cu(t, v, d="", c="dx"):
        cur.append({"t": t, "v": v, "d": d, "c": c})
    if diario:
        dd, nn = Counter(d for _, d, _ in diario).most_common(1)[0]
        if nn > 1:
            cu("Tu día más peliculero", f"{nn} películas", _fecha(datetime.strptime(dd, "%Y-%m-%d")), "lb")
    if durs:
        lg = max(vistas, key=lambda m: P(m).get("rt") or 0)
        cu("La peli más larga", tit(lg), f"{P(lg)['rt']} minutos", "lb")
    if caras:
        cu("La más cara que has visto", tit(caras[0][0]), f"presupuesto de {_dinero(caras[0][1])}", "lb")
        baratas = [x for x in caras if x[1] >= 1e5]
        if baratas:
            cu("La más barata", tit(baratas[-1][0]), f"costó {_dinero(baratas[-1][1])}", "lb")
        cu("Dinero en pantalla", _dinero(sum(x[1] for x in caras)), f"lo que costaron juntas {len(caras)} de tus pelis", "lb")
    if ratio:
        m, c_, t_ = ratio[0]
        cu("El mejor negocio", tit(m), f"recaudó {t_ / c_:.0f} veces lo que costó", "lb")
    if con_votos:
        cu("Tu peli más de nicho", tit(con_votos[0]), f"solo {_n(P(con_votos[0])['imdb_n'])} votos en IMDb", "lb")
        cu("La más vista por el mundo", tit(con_votos[-1]), f"{_n(P(con_votos[-1])['imdb_n'])} votos en IMDb", "lb")
    if vs_gente:
        x, m = max(vs_gente, key=lambda x: x[0])
        if x > 0:
            cu("Tu defensa más firme", tit(m), f"le das un {m['r']:g}; IMDb, un {P(m)['imdb_r']:g}", "lb")
        x, m = min(vs_gente, key=lambda x: x[0])
        if x < 0:
            cu("Tu crítica más dura", tit(m), f"le das un {m['r']:g}; IMDb, un {P(m)['imdb_r']:g}", "lb")
    if dirs:
        k, n = dirs.most_common(1)[0]
        cu("Tu director", k, f"{n} películas vistas", "lb")
    if cast:
        k, n = cast.most_common(1)[0]
        cu("El actor que más te encuentras", k, f"en {n} películas", "lb")
    if mejor_dir:
        cu("El director que mejor te cae", mejor_dir[0][0], f"nota media {mejor_dir[0][1]:.1f} en {mejor_dir[0][2]} pelis", "lb")
    vieja = min((m for m in vistas if str(m.get("y") or "").isdigit()), key=lambda m: int(m["y"]), default=None)
    if vieja:
        cu("La más antigua", tit(vieja), f"hace {datetime.now().year - int(vieja['y'])} años", "lb")
    nueva = max((m for m in vistas if str(m.get("y") or "").isdigit()), key=lambda m: (int(m["y"]), m.get("r") or 0), default=None)
    if nueva:
        cu("La más reciente", tit(nueva), "la de estreno más nuevo que has visto", "lb")
    if idi:
        no_en = sum(v for k, v in idi.items() if k != "inglés")
        cu("Fuera del inglés", f"{round(100 * no_en / sum(idi.values()))} %", "de tus pelis; sobre todo en " + next((k for k, _ in idi.most_common() if k != "inglés"), "—"), "lb")
    def tarjetas_series(lista, es_an):
        """Las mismas 16 tarjetas para series y para anime, cada una con lo suyo (sin mezclar)."""
        c, nom, art = ("al", "anime", "un mismo anime") if es_an else ("sz", "serie", "una misma serie")
        if not lista:
            return
        ids = {s["id"] for s in lista}
        rr = [x for x in reales if x[0]["id"] in ids]
        if rr:
            por_dia = defaultdict(list)
            for s, _, _, d in rr:
                por_dia[_dia(d)].append(s["t"])
            dmax = max(por_dia, key=lambda k: len(por_dia[k]))
            cu("Tu mayor maratón", f"{len(por_dia[dmax])} episodios",
               f"{_fecha(dmax)} · sobre todo {Counter(por_dia[dmax]).most_common(1)[0][0]}", c)
            n, fin = _racha(por_dia)
            cu("Racha más larga", f"{n} días seguidos", f"viendo {'algún anime' if es_an else 'alguna serie'} cada día, hasta el {_fecha(fin)}", c)
            por_serie = defaultdict(set)
            for s, _, _, d in rr:
                por_serie[s["t"]].add(_dia(d))
            t, (n, fin) = max(((t, _racha(v)) for t, v in por_serie.items()), key=lambda x: x[1][0])
            cu(f"Racha con {art}", f"{n} días seguidos", f"con {t}, hasta el {_fecha(fin)}", c)
            noche = sum(1 for _, _, _, d in rr if d.hour < 6)
            cu("Noctámbulo", f"{round(100 * noche / len(rr))} %", f"de los episodios de {nom} los marcas entre las 0 y las 6", c)
        # mes más intenso: aquí sí cuentan las marcas en tanda (no dicen el día exacto, pero sí el mes)
        # (pero el mes tiene que tener marcas en 5 días distintos como mínimo: importar una serie entera de golpe no es un mes)
        mes, dias_mes = Counter(), defaultdict(set)
        for s in lista:
            for _, _, f, aprox in s["eps"]:
                d = _local(f)
                if d and not aprox:
                    mes[(s["t"], d.year, d.month)] += 1
                    dias_mes[(s["t"], d.year, d.month)].add(d.day)
        mes = [(k, n) for k, n in mes.most_common() if len(dias_mes[k]) >= 5]
        if mes:
            (t, y, m), n = mes[0]
            cu("Tu mes más intenso", f"{_n(n)} episodios", f"de {t} en {MESES[m - 1]} de {y}", c)
        s = max(lista, key=neps)
        cu(f"Tu {nom} más larg{'o' if es_an else 'a'}", s["t"], f"{_n(neps(s))} episodios vistos", c)
        bq = {x["id"]: x["datos"] for x in tipos["anime" if es_an else "series"]["bloques"]}
        if bq.get("nicho"):
            cu(f"Tu {nom} más de nicho", bq["nicho"][0]["k"], bq["nicho"][0]["v"], c)
        if bq.get("masivas"):
            cu(f"{'El anime' if es_an else 'La serie'} más popular que has visto", bq["masivas"][0]["k"], bq["masivas"][0]["v"], c)
        if bq.get("red"):
            cu("Tu estudio" if es_an else "Tu cadena", bq["red"][0]["k"], f"{bq['red'][0]['n']} {nom}s vist{'o' if es_an else 'a'}s", c)
        if bq.get("rep"):
            cu("La voz que más oyes" if es_an else "El actor que más ves", bq["rep"][0]["k"], f"en {bq['rep'][0]['n']} {nom}s", c)
        if bq.get("gen"):
            cu("Tu género", bq["gen"][0]["k"], f"en {bq['gen'][0]['n']} {nom}s", c)
        if bq.get("mas"):
            cu("Tu defensa más firme", bq["mas"][0]["k"], bq["mas"][0]["v"], c)
        if bq.get("menos"):
            cu("Tu crítica más dura", bq["menos"][0]["k"], bq["menos"][0]["v"], c)
        con_y = [s for s in lista if str(s.get("y") or "").isdigit()]
        if con_y:
            v = min(con_y, key=lambda s: int(s["y"]))
            cu(f"{'El' if es_an else 'La'} más antigu{'o' if es_an else 'a'}", f"{v['t']} ({v['y']})", f"se estrenó hace {datetime.now().year - int(v['y'])} años", c)
            v = max(con_y, key=lambda s: (int(s["y"]), neps(s)))
            cu(f"{'El' if es_an else 'La'} más recient{'e'}", f"{v['t']} ({v['y']})", "la de estreno más nuevo que has visto", c)
        h = round((min_a if es_an else min_s) / 60)
        cu(f"Horas de {nom}", f"{_n(h)} h", f"unos {_n(round(h / 24))} días seguidos", c)
    tarjetas_series(ser, False)
    tarjetas_series(ani, True)
    total_min = min_p + min_s + min_a
    cu("Frente a la pantalla", f"{_n(round(total_min / 60 / 24))} días", f"{_n(round(total_min / 60))} horas (aprox.)", "dx")
    if b["sz"].get("sz_diario"):
        cu("Diario de Serializd", _n(b["sz"]["sz_diario"]), "registros de episodios y series", "dx")

    notas_al = [v["r"] for v in b["al"].values() if v.get("r")]
    nota_al = (f"Notas de AniList: media {_media(notas_al):.1f} en {len(notas_al)} animes.") if notas_al else ""
    avisos = []
    if importados:
        fs = [_fecha(datetime.strptime(d, "%Y-%m-%d")) for d in sorted(importados)]
        avisos.append(f"El {' y el '.join(fs)} importaste {sum(1 for _, d, _ in diario_todo if d in importados)} pelis "
                      "de golpe a Letterboxd: no cuentan para fechas.")
    avisos.append(f"Las horas son aproximadas: si no se sabe la duración de un episodio, cuenta {RT_SERIE} min ({RT_ANIME} en anime).")
    if nota_al:
        avisos.append(nota_al)

    out = {"resumen": resumen, "mapa": mapa_out, "semana": semana, "anios": anios, "tipos": tipos,
           "curiosidades": cur, "avisos": avisos, "calculado": b["fecha"]}
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
