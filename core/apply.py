"""Ejecuta un plan (acciones elegidas en la web).

- Serializd y Dixmax: se aplican directamente con tu sesión.
- Letterboxd: se generan CSV para su importador oficial (logs/notas y watchlist).
- dry=True: simulación, no cambia nada.
Cada ejecución real queda registrada en logs/.
"""
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, env
from .letterboxd import write_import_csv

LOGS = ROOT / "logs"


def _unix(iso):
    return int(datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def _stars(r10):
    return f"{r10 / 2:g}" if r10 else ""


def execute(acciones, dry=True):
    log, archivos = [], []
    out = log.append
    por = defaultdict(list)
    for a in acciones:
        por[a["accion"]].append(a)

    sz = dx = None
    sz_acc = {"sz_subir_eps", "sz_estado", "sz_terminar", "sz_nota", "sz_like"}
    dx_acc = {"dx_vista", "nota_lb_a_dx", "dx_nota", "dx_favorita"}
    if not dry and sz_acc & set(por):
        from .serializd import Serializd
        sz = Serializd()
        sz.check()
        Serializd.invalidar_diario()  # la próxima revisión rápida rehace el diario
    if not dry and dx_acc & set(por):
        from .dixmax_api import Dixmax
        dx = Dixmax()
        dx.check()

    # ---------------- Serializd ----------------
    for a in por["sz_subir_eps"]:
        eps = a["datos"]["episodios"]
        out(f"[Serializd] {a['titulo']}: subir {len(eps)} episodios con su fecha")
        if dry:
            continue
        groups = defaultdict(list)
        for e in sorted(eps, key=lambda e: e["date"]):
            s, r = sz.add_diary(a["datos"]["tmdb"], e["sz_season_id"], e["sz_episode"], e["date"])
            if s in (200, 201):
                groups[e["sz_season_id"]].append(e["sz_episode"])
            else:
                out(f"   ERROR {s} S{e['sz_season']}E{e['sz_episode']}: {str(r)[:80]}")
        for sid, lst in groups.items():
            sz.mark_episodes(a["datos"]["tmdb"], sid, sorted(lst))
        # que el último episodio visto sea el último marcado ("Continuar viendo")
        last = max(eps, key=lambda e: (e["sz_season"], e["sz_episode"]))
        sz._call("POST", "/episode_log/remove", {"show_id": a["datos"]["tmdb"], "season_id": last["sz_season_id"],
                                                 "episode_numbers": [last["sz_episode"]]})
        sz.mark_episodes(a["datos"]["tmdb"], last["sz_season_id"], [last["sz_episode"]])

    for a in por["sz_estado"]:
        st = a["datos"]["estado"]
        out(f"[Serializd] {a['titulo']}: poner como {st}")
        if not dry:
            s, r = sz.set_status(a["datos"]["tmdb"], st)
            if s != 200:
                out(f"   ERROR {s}: {str(r)[:80]}")

    for a in por["sz_terminar"]:
        sh = a["datos"]["show"]
        nota = math.floor(sh["rating10"]) if sh.get("rating10") else 0
        fecha = sh.get("last_date") or sh.get("mark_date")
        out(f"[Serializd] {a['titulo']}: temporadas vistas + registro de serie {fecha[:10] if fecha else '?'} nota {nota}")
        if not dry:
            sz.set_status(sh["tmdb"], "watched")
            s, r = sz.add_diary(sh["tmdb"], None, None, fecha, rating=nota, is_log=True, like=bool(sh.get("favorite")))
            if s not in (200, 201):
                out(f"   ERROR {s}: {str(r)[:80]}")

    for a in por["sz_nota"]:
        sh = a["datos"]["show"]
        nota = math.floor(sh["rating10"])
        prev = [x for x in sh.get("sz_reviews", []) if x.get("seasonId") is None and x.get("episodeNumber") is None]
        out(f"[Serializd] {a['titulo']}: nota {nota}" + (" (actualizar la existente)" if prev else " (nueva valoración)"))
        if dry:
            continue
        if prev:
            s, r = sz.update_review(prev[0], rating=nota)
        else:
            s, r = sz.add_diary(sh["tmdb"], None, None, sh.get("rating_date") or sh.get("mark_date"), rating=nota, is_log=False)
        if s not in (200, 201):
            out(f"   ERROR {s}: {str(r)[:80]}")

    for a in por["sz_like"]:
        sh = a["datos"]["show"]
        logs = [x for x in sh.get("sz_reviews", []) if x.get("isLog")]
        out(f"[Serializd] {a['titulo']}: ♥ en el registro de serie")
        if not dry and logs:
            s, r = sz.update_review(logs[0], like=True)
            if s not in (200, 201):
                out(f"   ERROR {s}: {str(r)[:80]}")

    # ---------------- Dixmax ----------------
    if por["dx_favorita"]:
        fechas, comprobar = [], []
        for a in por["dx_favorita"]:
            d = a["datos"].get("dx") or a["datos"].get("show")
            prev = d.get("mark_unix") if d.get("mark") == "viewed" else None
            out(f"[Dixmax] {a['titulo']}: marcar como favorita"
                + (f" conservando la fecha {datetime.fromtimestamp(prev):%d/%m/%Y %H:%M}" if prev else " (fecha leída de Dixmax)"))
            if dry:
                continue
            try:
                if prev is None:  # sin dato fiable del export: se lee la fecha actual de la marca
                    prev = (dx.dates(d["id"]).get("markedDate") or {}).get("unix")
                dx.set_mark(d["id"], "favorite", keep_date=False)
                if prev:
                    fechas.append({"fichaId": d["id"], "type": "mark", "unix": prev})
                    comprobar.append((a["titulo"], d["id"], prev))
            except Exception as e:
                out(f"   ERROR: {e}")
        for i in range(0, len(fechas), 50):  # restaurar fechas en bloques
            dx.set_dates(fechas[i:i + 50])
        if comprobar:  # comprobación de una muestra
            import random
            for t, fid, prev in random.sample(comprobar, min(3, len(comprobar))):
                info = dx.dates(fid)
                ok = info.get("marked") == "favorite" and (info.get("markedDate") or {}).get("unix") == prev
                out(f"   Comprobación {t}: {'OK' if ok else 'REVISAR'} ({info.get('marked')}, "
                    f"{(info.get('markedDate') or {}).get('text')})")
            out(f"   {len(fechas)} favoritas marcadas con su fecha original")
    for a in por["dx_vista"]:
        m, f = a["datos"]["dx"], a["datos"]["lb"]
        out(f"[Dixmax] {m['title']}: marcar como vista")
        if not dry:
            out(f"   {dx.set_mark(m['id'], 'viewed')}")
    for a in por["nota_lb_a_dx"]:
        m, f = a["datos"]["dx"], a["datos"]["lb"]
        v = f["rating"] * 2
        out(f"[Dixmax] {m['title']}: nota {m['rating10']} -> {v:g}")
        if not dry:
            out(f"   {dx.rate(m['id'], int(v) if v == int(v) else v)}")
    for a in por["dx_nota"]:
        sh = a["datos"]["show"]
        notas = [x["rating"] for x in sh.get("sz_reviews", []) if x.get("rating")]
        if not notas:
            continue
        out(f"[Dixmax] {a['titulo']}: nota {sh['rating10']} -> {notas[0]}")
        if not dry:
            out(f"   {dx.rate(sh['id'], notas[0])}")

    # ---------------- Letterboxd (CSV) ----------------
    logs_rows, wl_rows = [], []
    for a in por["lb_log"] + por["nota_dx_a_lb"]:
        m = a["datos"]["dx"]
        f = a["datos"].get("lb") or {}
        row = {"tmdbID": m.get("tmdb") or "", "Title": f.get("name") or m["title"], "Year": f.get("year") or m["year"],
               "Rating": _stars(m.get("rating10"))}
        if a["accion"] == "lb_log":
            row["WatchedDate"] = (m.get("date") or "")[:10]
        logs_rows.append(row)
    for a in por["lb_watchlist"]:
        m = a["datos"]["dx"]
        wl_rows.append({"tmdbID": m.get("tmdb") or "", "Title": m["title"], "Year": m["year"]})
    user = env("LETTERBOXD_USER", "")
    if dry:
        if logs_rows:
            out(f"[Letterboxd] se generaría un CSV con {len(logs_rows)} registros/notas para el importador")
        if wl_rows:
            out(f"[Letterboxd] se generaría un CSV de watchlist con {len(wl_rows)} películas")
    elif logs_rows or wl_rows:
        LOGS.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if logs_rows:
            p = LOGS / f"letterboxd_import_{stamp}.csv"
            write_import_csv(p, logs_rows)
            archivos.append({"archivo": str(p), "abrir": "https://letterboxd.com/import/",
                             "texto": f"{len(logs_rows)} registros/notas → importador de Letterboxd"})
            out(f"[Letterboxd] CSV con {len(logs_rows)} registros/notas: {p}")
        if wl_rows:
            p = LOGS / f"letterboxd_watchlist_{stamp}.csv"
            write_import_csv(p, wl_rows)
            archivos.append({"archivo": str(p), "abrir": f"https://letterboxd.com/{user}/watchlist/" if user else "https://letterboxd.com/",
                             "texto": f"{len(wl_rows)} películas → tu watchlist > Import"})
            out(f"[Letterboxd] CSV de watchlist con {len(wl_rows)}: {p}")

    for clave in ("dx_buscar", "dx_marcar_eps"):
        for a in por[clave]:
            out(f"[manual] {a['titulo']}: hazlo a mano (enlaces en la web)")

    if not dry:
        LOGS.mkdir(exist_ok=True)
        (LOGS / f"ejecucion_{datetime.now():%Y%m%d_%H%M%S}.log").write_text("\n".join(log), encoding="utf-8")
    return {"log": log, "archivos": archivos}
