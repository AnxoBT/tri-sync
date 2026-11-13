"""Sincronizar dos Tri-Sync (PC ↔ móvil, o PC ↔ PC) en los dos sentidos, por USB (movil.py) o por Wi-Fi (wifi.py).

Cada lado empaqueta lo suyo (datos()) y fusiona lo del otro (recibir()):
  .env          por clave, gana el cambio más reciente (config.SELLOS). Sin fechas en los dos: se rellena lo que
                falte aquí. No viajan las que son de cada dispositivo (carpeta de exports, idioma, adb).
  rules.json    unión: claves nuevas y listas juntas; si una misma regla es distinta, se queda la de aquí.
  caché         fichas y búsquedas (diccionarios): unión. Resultados de la última revisión, estadísticas y diario
                de Serializd: el más reciente entero. historial.json: las revisiones de los dos, por fecha.
  exports       el más reciente de Dixmax y de Letterboxd (zip) pasa al que lo tenga más viejo.
"""
import io
import json
import os
import time
import zipfile
from pathlib import Path

from . import config
from .config import CACHE, IMPORTADOS, REQUIRED

MANIFIESTO = "sincro.json"
NO_VIAJAN = {"DATA_DIR", "IDIOMA", "ADB"}  # de cada dispositivo
ENTEROS = {"diff.json", "estadisticas.json", "base_stats.json", "instantanea.json", "sz_diary.json", "anime_mapa.json"}
HIST = "historial.json"
FUERA = {"meta_dinero.json", "meta_dinero2.json", "meta_dinero3.json", config.SELLOS}


def _claves_env():
    return [k for k in dict.fromkeys(config.EDITABLES + [*config.ENV, "APPS_OFF"]) if k not in NO_VIAJAN]


def datos():
    """Zip con lo de este dispositivo: sincro.json (ajustes, mtimes) + cache/*.json + rules.json + importados/."""
    sellos = config.cache_json(config.SELLOS)
    man = {"version": (config.ROOT / "VERSION").read_text(encoding="utf-8").strip(),
           "android": config.ANDROID, "ios": config.IOS,
           "env": {k: [config.ENV.get(k, ""), sellos.get(k, 0)] for k in _claves_env()}, "mtimes": {}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if (config.DATOS / "rules.json").exists():
            zf.write(config.DATOS / "rules.json", "rules.json")
        for p in CACHE.glob("*.json"):
            if p.name not in FUERA:
                zf.write(p, f"cache/{p.name}")
                man["mtimes"][f"cache/{p.name}"] = p.stat().st_mtime
        for pre in REQUIRED:  # el último export de cada web, esté en Descargas o importado
            x = next(iter(config.find_exports(pre)), None)
            if x and x.zip:
                zf.write(x.path, f"importados/{x.name}")
                man["mtimes"][f"importados/{x.name}"] = x.mtime
        zf.writestr(MANIFIESTO, json.dumps(man, ensure_ascii=False))
    return buf.getvalue()


def version_de(paquete):
    """Lo que dice el manifiesto del otro (versión, si es Android…) sin fusionar nada."""
    with zipfile.ZipFile(io.BytesIO(paquete)) as zf:
        m = json.loads(zf.read(MANIFIESTO))
    return {k: m.get(k) for k in ("version", "android", "ios")}


# ---------- fusión ----------

def fusionar_reglas(aqui, otro):
    if isinstance(aqui, dict) and isinstance(otro, dict):
        return {**otro, **{k: fusionar_reglas(v, otro[k]) if k in otro else v for k, v in aqui.items()}}
    if isinstance(aqui, list) and isinstance(otro, list):
        return aqui + [x for x in otro if x not in aqui]
    return aqui


def fusionar_cache(aqui, otro):
    """Unión de diccionarios: lo de aquí manda, salvo si aquí falló la búsqueda ("error") y allí no."""
    out = {**otro, **aqui}
    for k, v in aqui.items():
        if v == "error" and otro.get(k) not in (None, "error"):
            out[k] = otro[k]
    return out


def _fecha_hist(h):
    try:
        return time.mktime(time.strptime(h.get("fecha", ""), "%d/%m/%Y %H:%M"))
    except ValueError:
        return 0


def fusionar_historial(aqui, otro):
    vistos = {json.dumps(h, sort_keys=True) for h in aqui}
    todas = aqui + [h for h in otro if json.dumps(h, sort_keys=True) not in vistos]
    return sorted(todas, key=_fecha_hist)[-100:]


def _env(otro_env, cambios):
    sellos = config.cache_json(config.SELLOS)
    nuevos, tomar = {}, {}
    for k, par in (otro_env or {}).items():
        if k in NO_VIAJAN or not isinstance(par, list) or len(par) != 2:
            continue
        v, t = str(par[0] or ""), float(par[1] or 0)
        aqui, ta = config.ENV.get(k, ""), float(sellos.get(k) or 0)
        if v == aqui:
            continue
        if t > ta or (not t and not ta and not aqui):
            tomar[k] = v
            if t:
                nuevos[k] = t
    if tomar:
        config.ENV.update(tomar)
        config._escribir_env(nuevos)
        config.recargar_env()
        cambios.append("ajustes")


def _guardar(destino, contenido, mtime=None):
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name("_sincro_" + destino.name)
    tmp.write_bytes(contenido)
    tmp.replace(destino)
    if mtime:
        os.utime(destino, (mtime, mtime))


def recibir(paquete):
    """Fusiona el zip de datos() de otro dispositivo con lo de aquí. Devuelve la lista de lo que ha cambiado."""
    cambios = []
    with zipfile.ZipFile(io.BytesIO(paquete)) as zf:
        nombres = set(zf.namelist())
        if MANIFIESTO not in nombres:
            raise ValueError("Paquete de sincronización no válido")
        man = json.loads(zf.read(MANIFIESTO))
        mt = man.get("mtimes") or {}
        for n in nombres:  # solo lo esperado: nada de rutas raras ni código
            p = Path(n).parts
            if not (n in (MANIFIESTO, "rules.json") or (len(p) == 2 and (
                    (p[0] == "cache" and n.endswith(".json")) or (p[0] == "importados" and n.endswith(".zip"))))):
                raise ValueError(f"Archivo no permitido: {n}")

        _env(man.get("env"), cambios)

        if "rules.json" in nombres:
            r = config.rules()
            junto = fusionar_reglas(r, json.loads(zf.read("rules.json")))
            if junto != r:
                _guardar(config.DATOS / "rules.json", (json.dumps(junto, ensure_ascii=False, indent=2) + "\n").encode())
                cambios.append("reglas")

        cache = False
        for n in sorted(x for x in nombres if x.startswith("cache/")):
            nombre = Path(n).name
            if nombre in FUERA:
                continue
            local = CACHE / nombre
            suyo = json.loads(zf.read(n))
            if not local.exists():
                _guardar(local, zf.read(n), mt.get(n))
                cache = True
                continue
            mio = json.loads(local.read_text(encoding="utf-8"))
            if nombre == HIST and isinstance(mio, list) and isinstance(suyo, list):
                junto = fusionar_historial(mio, suyo)
                if junto != mio:
                    config.save_cache(nombre, junto)
                    cambios.append("historial")
            elif nombre in ENTEROS or not (isinstance(mio, dict) and isinstance(suyo, dict)):
                if (mt.get(n) or 0) > local.stat().st_mtime + 1 and suyo != mio:
                    _guardar(local, zf.read(n), mt.get(n))
                    cache = True
            else:
                junto = fusionar_cache(mio, suyo)
                if junto != mio:
                    config.save_cache(nombre, junto)
                    cache = True
        if cache:
            cambios.append("caché")

        for n in (x for x in nombres if x.startswith("importados/")):
            nombre = Path(n).name
            pre = next((p for p in REQUIRED if nombre.lower().startswith(p)), None)
            if not pre:
                continue
            mio = next(iter(config.find_exports(pre)), None)
            if mio and (mt.get(n) or 0) <= mio.mtime + 1:
                continue
            for viejo in IMPORTADOS.glob(pre + "*"):
                viejo.unlink()
            _guardar(IMPORTADOS / nombre, zf.read(n), mt.get(n))
            cambios.append("export de Dixmax" if pre.startswith("playmax") else "export de Letterboxd")
    return cambios
