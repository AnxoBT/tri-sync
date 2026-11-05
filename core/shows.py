"""Equivalencia de episodios Dixmax -> Serializd (numeración TMDB actual).

Modos por serie:
  directo    todos los episodios existen tal cual
  temporada  misma estructura de temporadas: i-ésimo episodio de la temporada
  global     TMDB reorganizó/fusionó temporadas: numeración absoluta
  manual     rules.json > series > mapa_temporadas
Especiales (temporada 0): solo con reglas (especiales_s0 / episodios_a_s0).
"""
from concurrent.futures import ThreadPoolExecutor

from .config import rules

MAX_DIFF = 3


def map_show(sz, show):
    """Devuelve (lista de {dx..., sz_season, sz_season_id, sz_episode}, modo, sin_mapear)."""
    r = rules().get("series", {})
    tid = show["tmdb"]
    s0 = {int(k): v for k, v in r.get("especiales_s0", {}).get(str(tid), {}).items()}
    a_s0 = {tuple(int(x) for x in k.split("x")): v for k, v in r.get("episodios_a_s0", {}).get(str(tid), {}).items()}
    smap = {int(k): v for k, v in r.get("mapa_temporadas", {}).get(str(tid), {}).items()}
    saltar = set(r.get("saltar_episodios_serializd", {}).get(str(tid), []))

    info = sz.show(tid)
    if not info:
        return [], "no_encontrada", [f"S{e['season']:02d}E{e['episode']:02d}" for e in show["episodes"]]
    seasons = {int(k): v for k, v in info["seasons"].items()}
    with ThreadPoolExecutor(4) as ex:
        sdata = dict(zip(seasons, ex.map(lambda n: sz.season(tid, n), seasons)))
    eps_of = {n: sorted(int(e) for e in (d or {}).get("episodes", {})) for n, d in sdata.items()}

    eps = show["episodes"]
    regular = [e for e in eps if e["season"] >= 1]
    dix_len = {}
    for e in regular:
        dix_len[e["season"]] = max(dix_len.get(e["season"], 0), e["episode"])
    direct = all(e["episode"] in eps_of.get(e["season"], []) for e in regular)
    per_season = all(eps_of.get(s) and abs(len(eps_of[s]) - n) <= MAX_DIFF for s, n in dix_len.items())
    modo = "manual" if smap else "directo" if direct else "temporada" if per_season else "global"
    flat = [(s, e) for s in sorted(x for x in seasons if x >= 1) for e in eps_of[s] if e not in saltar]
    offsets, acc = {}, 0
    for s in sorted(dix_len):
        offsets[s] = acc
        acc += dix_len[s]

    out, sin = [], []
    for e in eps:
        tgt = None
        if (e["season"], e["episode"]) in a_s0:
            tgt = (0, a_s0[(e["season"], e["episode"])])
        elif e["season"] == 0:
            tgt = (0, s0[e["episode"]]) if s0.get(e["episode"]) else None
        elif modo == "manual":
            dst = smap.get(e["season"])
            lst = eps_of.get(dst, []) if dst else []
            tgt = (dst, lst[e["episode"] - 1]) if dst and e["episode"] <= len(lst) else None
        elif modo == "directo":
            tgt = (e["season"], e["episode"])
        elif modo == "temporada":
            lst = eps_of[e["season"]]
            tgt = (e["season"], lst[e["episode"] - 1]) if e["episode"] <= len(lst) else None
        else:
            k = offsets[e["season"]] + e["episode"] - 1
            tgt = flat[k] if k < len(flat) else None
        sid = (sdata.get(tgt[0]) or {}).get("id") if tgt else None
        if tgt and sid:
            out.append({**e, "sz_season": tgt[0], "sz_season_id": sid, "sz_episode": tgt[1]})
        else:
            sin.append(f"S{e['season']:02d}E{e['episode']:02d}")
    return out, modo, sin
