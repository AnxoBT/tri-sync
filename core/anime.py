"""Anime: lo que ves en Dixmax -> tu lista de anime de AniList.

AniList cuenta cada temporada (y cada parte de una temporada partida) como un anime distinto.
Para cruzarlo se usa la lista pública Fribb/anime-lists (AniList <-> TMDB + temporada) y se reparten
tus episodios de Dixmax entre las partes, en orden de estreno.
"""
import json
import time
import urllib.request
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from . import anilist
from .config import CACHE, env

MAPA_URL = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"
MAPA = CACHE / "anime_mapa.json"
FMT_SERIE = {"TV", "TV_SHORT", "ONA"}
TZ = ZoneInfo("Europe/Madrid")
IGNORAR = {"clave": "ignorar", "texto": "Ignorar", "fase": 1}
ESTADO_TXT = {"COMPLETED": "completado", "CURRENT": "viendo", "PLANNING": "pendiente", "DROPPED": "abandonado",
              "PAUSED": "en pausa", "REPEATING": "reviendo", None: "nada"}


def mapa(progress=print):
    """{"tv": {tmdb: [[anilist, temporada|None], …]}, "mv": {tmdb: [anilist, …]}} (se renueva cada semana)."""
    if MAPA.exists() and time.time() - MAPA.stat().st_mtime < 7 * 86400:
        return json.loads(MAPA.read_text(encoding="utf-8"))
    progress("AniList: actualizando la lista de equivalencias de anime…")
    try:
        with urllib.request.urlopen(urllib.request.Request(MAPA_URL, headers={"User-Agent": "Tri-Sync"}), timeout=60) as r:
            bruto = json.load(r)
    except Exception:
        if MAPA.exists():
            return json.loads(MAPA.read_text(encoding="utf-8"))
        raise
    tv, mv = defaultdict(list), defaultdict(list)
    lst = lambda v: v if isinstance(v, list) else [v]  # noqa: E731
    for x in bruto:
        al, t = x.get("anilist_id"), x.get("themoviedb_id") or {}
        if not al:
            continue
        for i in lst(t.get("tv")) if t.get("tv") else []:
            tv[str(i)].append([al, (x.get("season") or {}).get("tmdb")])
        for i in lst(t.get("movie")) if t.get("movie") else []:
            mv[str(i)].append(al)
    m = {"tv": tv, "mv": mv}
    MAPA.write_text(json.dumps(m), encoding="utf-8")
    return m


def _dia(iso):
    if not iso:
        return None
    d = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    return [d.year, d.month, d.day]


def _partes_serie(show, ents, med):
    """[(anilist_id, episodios_vistos_en_esa_parte [ep…], total|None)] repartiendo tus episodios de Dixmax."""
    partes = [(al, se) for al, se in ents if (med.get(str(al)) or {}).get("formato") in FMT_SERIE]
    if not partes:
        return []
    inicio = lambda p: med[str(p[0])]["inicio"]  # noqa: E731
    eps = sorted((e for e in show["episodes"] if e["season"] > 0), key=lambda e: (e["season"], e["episode"]))
    out = []
    if all(se for _, se in partes):  # cada parte sabe su temporada de TMDB: se reparte dentro de cada temporada
        por_temp = defaultdict(list)
        for p in partes:
            por_temp[p[1]].append(p)
        conocidos = {al for al, _ in partes}
        for se, ps in sorted(por_temp.items()):
            vistos = [e for e in eps if e["season"] == se]
            ps = sorted(ps, key=inicio)
            off = 0
            for al, _ in ps:
                n = med[str(al)]["eps"]
                out.append((al, [e for e in vistos if off < e["episode"] <= off + (n or 10 ** 6)], n))
                off += n or 10 ** 6
            # ¿has visto más episodios de esta temporada que los que cubren las partes conocidas? (p. ej. el final
            # de Shingeki en dos especiales y la lista de equivalencias solo trae el primero): se sigue la secuela
            ultimo = ps[-1][0]
            for _ in range(3):
                if not any(e["episode"] > off for e in vistos):
                    break
                sig = anilist.secuela(ultimo)
                if not sig or sig in conocidos:
                    break
                info = anilist.medios([sig], progress=lambda m: None).get(str(sig)) or {}
                med[str(sig)] = info
                if info.get("formato") not in FMT_SERIE | {"SPECIAL"} or not info.get("eps"):
                    break
                n = info["eps"]
                out.append((sig, [e for e in vistos if off < e["episode"] <= off + n], n))
                off += n
                conocidos.add(sig)
                ultimo = sig
    else:  # numeración seguida (p. ej. One Piece, Naruto): se reparten por orden
        off = 0
        for al, _ in sorted(partes, key=inicio):
            n = med[str(al)]["eps"]
            out.append((al, eps[off: off + n] if n else eps[off:], n))
            off += n or 10 ** 6
    return out


def _deseado_serie(show, partes):
    """Entradas que debería tener AniList para esta serie de Dixmax."""
    nota = round(show["rating10"] * 10) if show.get("rating10") else None
    out = []
    for i, (al, vistos, n) in enumerate(partes):
        prog = len(vistos)
        if prog and n and show["status"] == "finished":
            prog = n  # Dixmax la da por terminada: los recuentos de episodios a veces difieren en 1-2 (recaps, dobles)
        if prog and n and prog >= n:
            st = "COMPLETED"
        elif prog:
            st = "DROPPED" if show["status"] == "dropped" else "CURRENT"
        elif i == 0 and show["status"] == "watchlist":
            st = "PLANNING"
        else:
            continue  # partes que aún no has empezado: no se añaden
        out.append({"mediaId": al, "status": st, "progress": min(prog, n) if n else prog,
                    "scoreRaw": nota if prog else None,
                    "startedAt": _dia(vistos[0]["date"]) if vistos else None,
                    "completedAt": _dia(vistos[-1]["date"]) if st == "COMPLETED" else None})
    return out


def _deseado_peli(m, ids, med):
    pelis = [al for al in ids if (med.get(str(al)) or {}).get("formato") == "MOVIE"] or ids[:1]
    if not pelis:
        return []
    al = sorted(pelis, key=lambda a: (med.get(str(a)) or {}).get("inicio", [9999]))[0]
    if m["status"] == "watched":
        d = _dia(m.get("date"))
        n = (med.get(str(al)) or {}).get("eps") or 1  # algunas «pelis» son antologías de varios episodios
        return [{"mediaId": al, "status": "COMPLETED", "progress": n, "favorito": bool(m.get("favorite")),
                 "scoreRaw": round(m["rating10"] * 10) if m.get("rating10") else None, "startedAt": d, "completedAt": d}]
    if m["status"] == "watchlist":
        return [{"mediaId": al, "status": "PLANNING", "progress": 0}]
    return []


def _cambios(des, cur):
    """Qué cambia en una entrada: lista de textos (vacía si ya está bien)."""
    if not cur:
        return [f"añadir como {ESTADO_TXT[des['status']]}" + (f" ({des['progress']} ep.)" if des["progress"] else "")]
    c = []
    if cur["status"] != des["status"]:
        c.append(f"{ESTADO_TXT.get(cur['status'], cur['status'])} → {ESTADO_TXT[des['status']]}")
    if (cur.get("progress") or 0) != des["progress"]:
        c.append(f"episodios {cur.get('progress') or 0} → {des['progress']}")
    if des.get("scoreRaw") and round((cur.get("score") or 0) * 10) != des["scoreRaw"]:
        c.append(f"nota {cur.get('score') or '—'} → {des['scoreRaw'] / 10:g}")
    for k, t in (("startedAt", "inicio"), ("completedAt", "fin")):
        f = cur.get(k) or {}
        if des.get(k) and [f.get("year"), f.get("month"), f.get("day")] != des[k]:
            c.append(f"fecha de {t}")
    return c


def diferencias(dx, progress=print):
    usuario = env("ANILIST_USER")
    if not usuario:
        return [], {}
    mp = mapa(progress)
    shows = [s for s in dx["shows"] if str(s["tmdb"]) in mp["tv"]]
    pelis = [m for m in dx["movies"] if m.get("tmdb") and str(m["tmdb"]) in mp["mv"]]
    ids = {al for s in shows for al, _ in mp["tv"][str(s["tmdb"])]} | {al for m in pelis for al in mp["mv"][str(m["tmdb"])]}
    med = anilist.medios(ids, progress)
    progress("AniList: leyendo tu lista de anime…")
    cur = anilist.lista(usuario)
    favs = anilist.favoritos() if env("ANILIST_TOKEN") else set()
    out = []

    def add(item, des, enlaces, aviso=""):
        lineas, entradas = [], []
        for d in des:
            c = _cambios(d, cur.get(d["mediaId"]))
            if d.get("favorito") and d["mediaId"] not in favs:
                c.append("♥ favorito")
            if c:
                entradas.append(d)
                lineas.append(f"{med[str(d['mediaId'])]['titulo']}: {', '.join(c)}")
        if not entradas:
            return
        nuevo = all(d["mediaId"] not in cur for d in entradas)
        out.append({"id": f"a{len(out)}", "seccion": "Anime",
                    "categoria": "Falta en AniList" if nuevo else "Distinto en AniList",
                    "titulo": item["title"], "detalle": (aviso + " · " if aviso else "") + " · ".join(lineas[:4])
                    + (f" · y {len(lineas) - 4} más" if len(lineas) > 4 else ""),
                    "enlaces": {**enlaces, "AniList": f"https://anilist.co/anime/{entradas[0]['mediaId']}"},
                    "opciones": [{"clave": "al_subir", "texto": "Subir a AniList (estado, episodios, nota y fechas)",
                                  "fase": 2}, IGNORAR],
                    "datos": {"entradas": entradas}})

    for s in shows:
        partes = _partes_serie(s, mp["tv"][str(s["tmdb"])], med)
        if not partes:
            continue
        aviso = ""
        total = sum(n or 0 for _, _, n in partes)
        vistos = sum(1 for e in s["episodes"] if e["season"] > 0)
        if s["status"] == "finished" and all(n for _, _, n in partes) and vistos != total:
            aviso = f"⚠ revisa: en Dixmax hay {vistos} episodios y AniList cuenta {total}"
        des = _deseado_serie(s, partes)
        if s.get("favorite") or s["tmdb"] in dx.get("sz_favs", set()):
            # favorita en Dixmax o ♥ en Serializd: en AniList se marca la primera temporada
            primera = min(partes, key=lambda p: med[str(p[0])]["inicio"])[0]
            for d in des:
                if d["mediaId"] == primera:
                    d["favorito"] = True
        add(s, des, {"Dixmax": s.get("url")}, aviso)
    for m in pelis:
        add(m, _deseado_peli(m, mp["mv"][str(m["tmdb"])], med), {"Dixmax": m.get("url")})
    # lo que tienes en AniList y no en Dixmax (ni es parte, OVA o secuela de algo que sí está)
    conocidos = ids | {e["mediaId"] for x in out for e in x["datos"]["entradas"]}
    solo = [i for i in cur if i not in conocidos]
    info = anilist.medios(solo, progress)
    for i in solo:
        m = info.get(str(i)) or {}
        if m.get("estado") == "NOT_YET_RELEASED":
            continue  # aún no se ha estrenado: Dixmax no suele tener ficha; se ignora hasta el estreno
        if any(r in conocidos for r in anilist.relacionados(i)):
            continue  # temporada, OVA o especial de algo que ya tienes en Dixmax
        out.append({"id": f"a{len(out)}", "seccion": "Anime", "categoria": "Solo en AniList",
                    "titulo": m.get("titulo") or str(i),
                    "detalle": f"AniList: {ESTADO_TXT.get(cur[i]['status'], cur[i]['status'])}"
                               + (f", {cur[i]['progress']} ep." if cur[i].get("progress") else ""),
                    "enlaces": {"AniList": f"https://anilist.co/anime/{i}"},
                    "opciones": [{"clave": "dx_buscar", "texto": "Añadir en Dixmax (a mano, con el enlace)", "fase": 2},
                                 IGNORAR],
                    "datos": {"anilist": i}})
    stats = {"al_anime": len(cur), "al_series_cruzadas": len(shows), "al_pelis_cruzadas": len(pelis)}
    return out, stats
