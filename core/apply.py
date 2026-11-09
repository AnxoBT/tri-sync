"""Ejecuta un plan (acciones elegidas en la web).

- Serializd y Dixmax: se aplican directamente con tu sesión.
- Letterboxd: se generan CSV para su importador oficial (logs/notas y watchlist).
- dry=True: simulación, no cambia nada.
Cada ejecución real queda registrada en logs/.
"""
import json
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


PENDIENTES = LOGS / "fechas_pendientes.json"


class Cancelado(Exception):
    pass


def _guardar_pendientes(lst):
    LOGS.mkdir(exist_ok=True)
    if lst:
        PENDIENTES.write_text(json.dumps(lst), encoding="utf-8")
    elif PENDIENTES.exists():
        PENDIENTES.unlink()


def restaurar_pendientes(dx, out=print):
    """Si una aplicación se cortó (ventana cerrada, apagón…) entre marcar favorita y restaurar la fecha,
    aquí se restauran las fechas que quedaron anotadas."""
    if not PENDIENTES.exists():
        return 0
    lst = json.loads(PENDIENTES.read_text(encoding="utf-8"))
    for i in range(0, len(lst), 50):
        dx.set_dates(lst[i:i + 50])
    _guardar_pendientes([])
    out(f"[Dixmax] restauradas {len(lst)} fechas que quedaron pendientes de una aplicación interrumpida")
    return len(lst)


def execute(acciones, dry=True, ctl=None):
    """ctl (opcional): dict compartido con la web -> {total, hechos, actual, cancelar}."""
    log, archivos = [], []
    por = defaultdict(list)
    for a in acciones:
        por[a["accion"]].append(a)
    ctl = ctl if ctl is not None else {}
    hechas = []  # ids de las diferencias aplicadas sin error (la web las quita de la lista)
    ctl.update(total=len(acciones), hechos=0, actual="Conectando…", log=log, hechas=hechas)
    cur = {"a": None, "err": 0}
    errores = [0]

    def out(msg):
        log.append(msg)
        if "ERROR" in msg:
            errores[0] += 1

    def cerrar():  # la acción anterior terminó: si no dio error, cuenta como aplicada
        if cur["a"] is not None and not dry and errores[0] == cur["err"] and cur["a"].get("id"):
            hechas.append(cur["a"]["id"])
        cur["a"] = None

    def tick(a):
        cerrar()
        if ctl.get("cancelar"):
            raise Cancelado()
        ctl["actual"] = a.get("titulo", "")
        ctl["hechos"] += 1
        cur.update(a=a, err=errores[0])

    try:
        _execute(por, dry, out, tick, archivos, ctl)
        cerrar()
    except Cancelado:
        out(f"⛔ CANCELADO: se hicieron {ctl['hechos']} de {ctl['total']}; el resto no se ha tocado. "
            f"Haz una revisión rápida para ver lo que falta.")
    if not dry:
        LOGS.mkdir(exist_ok=True)
        (LOGS / f"ejecucion_{datetime.now():%Y%m%d_%H%M%S}.log").write_text("\n".join(log), encoding="utf-8")
    return {"log": log, "archivos": archivos, "hechas": hechas}


AL_ACTIVIDAD = LOGS / "anilist_actividad.json"


def restaurar_actividad_anilist(out=print):
    """Si una subida a AniList se cortó con la actividad apagada, la deja como estaba."""
    if not AL_ACTIVIDAD.exists():
        return
    from . import anilist
    anilist.poner_actividad_listas(json.loads(AL_ACTIVIDAD.read_text(encoding="utf-8")))
    AL_ACTIVIDAD.unlink()
    out("[AniList] actividad de listas restaurada como estaba")


def _al_subir(acciones, dry, out, tick, ctl, anilist):
    lote = []
    for a in acciones + [None]:  # varias series por petición (límite de 30/min)
        if a is not None:
            lote.append(a)
        if lote and (a is None or sum(len(x["datos"]["entradas"]) for x in lote) >= 12):
            err = None
            if not dry:
                if ctl.get("cancelar"):
                    raise Cancelado()
                try:
                    anilist.guardar([e for x in lote for e in x["datos"]["entradas"]])
                except Exception as ex:
                    err = str(ex)
            cancel = ctl.pop("cancelar", False)  # lo ya enviado se cuenta entero
            for x in lote:
                tick(x)
                out(f"[AniList] {x['titulo']}: {len(x['datos']['entradas'])} entradas")
                if err:
                    out(f"   ERROR: {err[:150]}")
            if cancel:
                ctl["cancelar"] = True
            lote = []
    favs = [e for a in acciones for e in a["datos"]["entradas"] if e.get("favorito")]
    if favs and not dry:
        ya = anilist.favoritos()
        for e in favs:
            if e["mediaId"] not in ya:
                try:
                    anilist.marcar_favorito(e["mediaId"])
                    out(f"[AniList] ♥ favorito: {e['mediaId']}")
                except Exception as ex:
                    out(f"[AniList] ♥ favorito {e['mediaId']}: no se pudo ({str(ex)[:120]})")
        try:  # en tu perfil, los favoritos quedan ordenados por tu nota
            anilist.ordenar_favoritos()
            out("[AniList] favoritos ordenados por tu nota")
        except Exception as ex:
            out(f"[AniList] no se pudieron ordenar los favoritos ({str(ex)[:120]})")


def _execute(por, dry, out, tick, archivos, ctl):

    sz = dx = None
    sz_acc = {"sz_subir_eps", "sz_estado", "sz_terminar", "sz_nota", "sz_like"}
    dx_acc = {"dx_vista", "nota_lb_a_dx", "dx_nota", "dx_favorita"}
    # también en simulación: se comprueba que las conexiones funcionan antes de dar el visto bueno
    if sz_acc & set(por):
        from .serializd import Serializd
        sz = Serializd()
        out(f"[Comprobación] Serializd conectado como {sz.check()}")
        if not dry:
            Serializd.invalidar_diario()  # la próxima revisión rápida rehace el diario
    if dx_acc & set(por):
        from .dixmax_api import Dixmax
        dx = Dixmax()
        out(f"[Comprobación] Dixmax (API oficial) conectado como {dx.check()}")
        if not dry:
            restaurar_pendientes(dx, out)
        if dry and por["dx_favorita"]:
            a = por["dx_favorita"][0]
            d = a["datos"].get("dx") or a["datos"].get("show")
            info = dx.dates(d["id"])
            out(f"[Comprobación] lectura de fechas OK ({a['titulo']}: {info.get('marked')}, "
                f"{(info.get('markedDate') or {}).get('text')})")
            n = len(por["dx_favorita"])
            out(f"[Comprobación] tiempo estimado: ~{max(1, round(n / 1.8 / 60))} min para {n} favoritas (límite de la API)")

    # ---------------- Serializd ----------------
    for a in por["sz_subir_eps"]:
        tick(a)
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

        tick(a)
        st = a["datos"]["estado"]
        out(f"[Serializd] {a['titulo']}: poner como {st}")
        if not dry:
            s, r = sz.set_status(a["datos"]["tmdb"], st)
            if s != 200:
                out(f"   ERROR {s}: {str(r)[:80]}")

    for a in por["sz_terminar"]:

        tick(a)
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

        tick(a)
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

        tick(a)
        sh = a["datos"]["show"]
        logs = [x for x in sh.get("sz_reviews", []) if x.get("isLog")]
        out(f"[Serializd] {a['titulo']}: ♥ en el registro de serie")
        if not dry and logs:
            s, r = sz.update_review(logs[0], like=True)
            if s not in (200, 201):
                out(f"   ERROR {s}: {str(r)[:80]}")

    # ---------------- Dixmax ----------------
    if por["dx_favorita"]:
        fechas, comprobar, pend = [], [], []

        def volcar():
            if pend:
                dx.set_dates(pend)
                pend.clear()
                _guardar_pendientes([])

        try:
            for a in por["dx_favorita"]:
                tick(a)
                d = a["datos"].get("dx") or a["datos"].get("show")
                prev = d.get("mark_unix") if d.get("mark") == "viewed" else None
                out(f"[Dixmax] {a['titulo']}: marcar como favorita"
                    + (f" conservando la fecha {datetime.fromtimestamp(prev):%d/%m/%Y %H:%M}" if prev else " (fecha leída de Dixmax)"))
                if dry:
                    continue
                try:
                    if prev is None:  # sin dato fiable del export: se lee la fecha actual de la marca
                        prev = (dx.dates(d["id"]).get("markedDate") or {}).get("unix")
                    if prev:  # se anota ANTES de marcar: si se corta, la fecha se puede restaurar
                        pend.append({"fichaId": d["id"], "type": "mark", "unix": prev})
                        _guardar_pendientes(pend)
                    dx.set_mark(d["id"], "favorite", keep_date=False)
                    if prev:
                        fechas.append(pend[-1])
                        comprobar.append((a["titulo"], d["id"], prev))
                except Exception as ex:
                    out(f"   ERROR: {ex}")
                if len(pend) >= 10:
                    volcar()
        finally:
            if not dry:
                volcar()  # también si se cancela: las ya marcadas recuperan su fecha
        if comprobar:  # comprobación de una muestra
            import random
            ctl["actual"] = "Comprobando una muestra…"
            for t_, fid, prev in random.sample(comprobar, min(3, len(comprobar))):
                info = dx.dates(fid)
                ok = info.get("marked") == "favorite" and (info.get("markedDate") or {}).get("unix") == prev
                out(f"   Comprobación {t_}: {'OK' if ok else 'REVISAR'} ({info.get('marked')}, "
                    f"{(info.get('markedDate') or {}).get('text')})")
            out(f"   {len(fechas)} favoritas marcadas con su fecha original")
    for a in por["dx_vista"]:
        tick(a)
        m, f = a["datos"]["dx"], a["datos"]["lb"]
        out(f"[Dixmax] {m['title']}: marcar como vista")
        if not dry:
            out(f"   {dx.set_mark(m['id'], 'viewed')}")
    for a in por["nota_lb_a_dx"]:
        tick(a)
        m, f = a["datos"]["dx"], a["datos"]["lb"]
        v = f["rating"] * 2
        out(f"[Dixmax] {m['title']}: nota {m['rating10']} -> {v:g}")
        if not dry:
            out(f"   {dx.rate(m['id'], int(v) if v == int(v) else v)}")
    for a in por["dx_nota"]:
        tick(a)
        sh = a["datos"]["show"]
        notas = [x["rating"] for x in sh.get("sz_reviews", []) if x.get("rating")]
        if not notas:
            continue
        out(f"[Dixmax] {a['titulo']}: nota {sh['rating10']} -> {notas[0]}")
        if not dry:
            out(f"   {dx.rate(sh['id'], notas[0])}")

    # ---------------- AniList ----------------
    if por["al_subir"]:
        from . import anilist
        out(f"[Comprobación] AniList conectado como {anilist.check() or 'NADIE: Configuración → Conectar con AniList'}")
        out("[AniList] la actividad de listas se apaga mientras se sube (para no llenar tu feed) y luego se deja como estaba")
        if not dry:
            antes = anilist.actividad_listas()
            AL_ACTIVIDAD.write_text(json.dumps(antes), encoding="utf-8")  # por si se corta: se restaura al revisar
            anilist.poner_actividad_listas([{**x, "disabled": True} for x in antes])
        try:
            _al_subir(por["al_subir"], dry, out, tick, ctl, anilist)
        finally:
            if not dry:
                restaurar_actividad_anilist(out)

    # ---------------- Letterboxd (CSV) ----------------
    logs_rows, wl_rows = [], []
    for a in por["lb_log"] + por["nota_dx_a_lb"]:
        tick(a)
        m = a["datos"]["dx"]
        f = a["datos"].get("lb") or {}
        row = {"tmdbID": m.get("tmdb") or "", "Title": f.get("name") or m["title"], "Year": f.get("year") or m["year"],
               "Rating": _stars(m.get("rating10"))}
        if a["accion"] == "lb_log":
            row["WatchedDate"] = (m.get("date") or "")[:10]
        logs_rows.append(row)
    for a in por["lb_watchlist"]:
        tick(a)
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
