"""AniList (API GraphQL oficial). Solo se toca tu lista de ANIME: la de manga (Mihon) nunca.

- Leer tu lista: público, con tu usuario.
- Escribir: permiso OAuth (Configuración → Conectar con AniList), dura 1 año.
Límite de la API: 30 peticiones/min -> se espera solo cuando hace falta.
"""
import json
import time
import urllib.error
import urllib.request

from .config import cache_json, env, save_cache

URL = "https://graphql.anilist.co"
CLIENT_ID = 56451  # cliente «Tri-Sync» (público: el permiso lo das tú en AniList)
AUTH_URL = f"https://anilist.co/api/v2/oauth/authorize?client_id={CLIENT_ID}&response_type=token"
MEDIA_CACHE = "anilist_media.json"
POR_MINUTO = 28
_T = []


def _esperar_turno():
    ahora = time.time()
    _T[:] = [t for t in _T if ahora - t < 60]
    if len(_T) >= POR_MINUTO:
        time.sleep(60 - (ahora - _T[0]) + 0.5)
    _T.append(time.time())


def gql(query, variables=None, token=None, con_token=True):
    h = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Tri-Sync"}
    tk = token or (env("ANILIST_TOKEN") if con_token else "")
    if tk:
        h["Authorization"] = f"Bearer {tk}"
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for _ in range(4):
        _esperar_turno()
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, data=body, headers=h), timeout=40) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="replace")
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After") or 60) + 1)
                continue
            if e.code in (400, 401) and "token" in txt.lower():
                raise RuntimeError("El permiso de AniList no vale o ha caducado: Configuración → Conectar con AniList")
            raise RuntimeError(f"AniList respondió {e.code}: {txt[:200]}")
        if d.get("errors"):
            raise RuntimeError("AniList: " + "; ".join(x.get("message", "") for x in d["errors"])[:300])
        return d["data"]
    raise RuntimeError("AniList: demasiadas peticiones seguidas, prueba en un rato")


def viewer(token=None):
    return gql("{ Viewer { id name } }", token=token)["Viewer"]


def check():
    if not env("ANILIST_TOKEN"):
        return None
    return viewer()["name"]


def lista(usuario):
    """Tu lista de anime: {mediaId: {status, progress, score (0-10), startedAt, completedAt}}"""
    q = """query($u:String){ MediaListCollection(userName:$u, type:ANIME){ lists{ entries{
          mediaId status progress score(format:POINT_10_DECIMAL)
          startedAt{year month day} completedAt{year month day} } } } }"""
    d = gql(q, {"u": usuario}, con_token=False)
    out = {}
    for l in d["MediaListCollection"]["lists"]:
        for e in l["entries"]:
            out[e["mediaId"]] = e
    return out


def medios(ids, progress=print):
    """Formato, episodios y fecha de estreno de cada anime (en caché; los que están en emisión se refrescan)."""
    c = cache_json(MEDIA_CACHE, {})
    ahora = time.time()
    faltan = [i for i in set(ids) if str(i) not in c or
              c[str(i)].get("estado") in ("RELEASING", "NOT_YET_RELEASED") and ahora - c[str(i)].get("t", 0) > 7 * 86400]
    if faltan:
        progress(f"AniList: leyendo {len(faltan)} animes (solo la primera vez)…")
    q = """query($ids:[Int]){ Page(perPage:50){ media(id_in:$ids, type:ANIME){
          id format episodes status startDate{year month day} title{romaji} } } }"""
    for i in range(0, len(faltan), 50):
        for m in gql(q, {"ids": faltan[i:i + 50]}, con_token=False)["Page"]["media"]:
            s = m["startDate"] or {}
            c[str(m["id"])] = {"formato": m["format"], "eps": m["episodes"], "estado": m["status"],
                               "inicio": [s.get("year") or 9999, s.get("month") or 12, s.get("day") or 31],
                               "titulo": m["title"]["romaji"], "t": int(ahora)}
        if i and i % 500 == 0:
            progress(f"AniList: {i}/{len(faltan)}")
    if faltan:
        save_cache(MEDIA_CACHE, c)
    return c


def _fecha(f):
    return "{" + ", ".join(f"{k}: {v}" for k, v in zip(("year", "month", "day"), f)) + "}" if f else None


def guardar(entradas):
    """Varias entradas en una sola petición. entradas: [{mediaId, status, progress, scoreRaw, startedAt, completedAt}]"""
    partes = []
    for i, e in enumerate(entradas):
        args = [f"mediaId: {int(e['mediaId'])}", f"status: {e['status']}", f"progress: {int(e.get('progress') or 0)}"]
        if e.get("scoreRaw"):
            args.append(f"scoreRaw: {int(e['scoreRaw'])}")
        for k in ("startedAt", "completedAt"):
            if e.get(k):
                args.append(f"{k}: {_fecha(e[k])}")
        partes.append(f"e{i}: SaveMediaListEntry({', '.join(args)}) {{ id }}")
    return gql("mutation { " + " ".join(partes) + " }")
