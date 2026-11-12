"""Tri-Sync en el móvil: importar exports desde la web y pasar los datos del PC al móvil por USB (adb).

Nada pasa por internet: el PC habla con la app del móvil por el cable (adb forward) y le manda tu .env,
rules.json, la caché (fichas, estadísticas, historial…) y los últimos exports de Dixmax y Letterboxd.
"""
import io
import json
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

from . import config
from .config import CACHE, DATOS, IMPORTADOS, REQUIRED, ROOT, find_exports

PAQUETE = "com.anxobt.trisync"
PUERTO_MOVIL = 8765  # el servidor de la app en el móvil (el mismo que en el PC: así vale el permiso de AniList)
PUERTO_PUENTE = 8783  # en el PC, reenviado por adb al del móvil
OBSOLETOS = {"meta_dinero.json", "meta_dinero2.json", "meta_dinero3.json"}
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------- importar export (PC y móvil) ----------------

def _tipo_export(nombre, zf):
    """Prefijo del export ('playmax-userdata-' o 'letterboxd-') por el nombre o, si lo han renombrado, por lo que lleva."""
    for pre in REQUIRED:
        if Path(nombre).name.lower().startswith(pre):
            return pre
    dentro = {Path(n).name for n in zf.namelist()}
    for pre, archivos in REQUIRED.items():
        if all(a in dentro for a in archivos):
            return pre
    return None


def importar_export(nombre, datos):
    """Guarda el zip en la carpeta de importados (sustituye al anterior del mismo tipo)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile:
        raise ValueError("No es un zip: elige el zip tal cual lo descargas de Dixmax o Letterboxd")
    pre = _tipo_export(nombre, zf)
    if not pre:
        raise ValueError("No parece un export de Dixmax ni de Letterboxd")
    nombre = Path(nombre).name if Path(nombre).name.lower().startswith(pre) else f"{pre}{time.strftime('%Y-%m-%d-%H-%M')}.zip"
    if not nombre.lower().endswith(".zip"):
        nombre += ".zip"
    destino = IMPORTADOS / nombre
    tmp = IMPORTADOS / ("_subiendo_" + nombre)  # sin el prefijo: no se usa hasta comprobarlo
    tmp.write_bytes(datos)
    x = config.Export(tmp)
    falta = x.missing(pre)
    x._zf.close()
    if falta:
        tmp.unlink()
        raise ValueError(f"Al export le faltan archivos: {', '.join(falta)}")
    for viejo in IMPORTADOS.glob(pre + "*"):
        viejo.unlink()
    tmp.replace(destino)
    return {"tipo": "dixmax" if pre.startswith("playmax") else "letterboxd", "nombre": nombre}


# ---------------- móvil: recibir datos del PC ----------------

def recibir(datos):
    """Zip del PC con .env, rules.json, cache/ e importados/: se escribe en la carpeta de datos de la app."""
    zf = zipfile.ZipFile(io.BytesIO(datos))
    n = 0
    raiz = DATOS.resolve()
    for nombre in zf.namelist():
        if nombre.endswith("/"):
            continue
        destino = (DATOS / nombre).resolve()
        if raiz not in destino.parents:  # zip con rutas raras
            raise ValueError(f"Ruta no válida: {nombre}")
        partes = Path(nombre).parts
        permitido = nombre in (".env", "rules.json") or (len(partes) == 2 and (
            (partes[0] == "cache" and nombre.endswith(".json")) or (partes[0] == "importados" and nombre.endswith(".zip"))))
        if not permitido:  # nada de código ni de otros archivos: solo configuración, caché y exports
            raise ValueError(f"Archivo no permitido: {nombre}")
        if nombre.startswith("importados/"):  # el export nuevo sustituye al anterior del mismo tipo
            for pre in REQUIRED:
                if Path(nombre).name.startswith(pre):
                    for viejo in IMPORTADOS.glob(pre + "*"):
                        viejo.unlink()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(zf.read(nombre))
        t = time.mktime(zf.getinfo(nombre).date_time + (0, 0, -1))  # la fecha del PC: la edad de los exports cuenta
        os.utime(destino, (t, t))
        n += 1
    config.recargar_env()
    return {"archivos": n}


# ---------------- PC: pasar al móvil ----------------

def adb():
    for c in (config.env("ADB"), shutil.which("adb"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe")):
        if c and os.path.exists(c):
            return c
    raise RuntimeError("No encuentro adb (Android SDK platform-tools). Pon su ruta en ADB del .env")


SERIE = {"id": None}  # el móvil elegido (si hay varios, p. ej. un emulador abierto)


def _adb(*args, timeout=120):
    pre = ["-s", SERIE["id"]] if SERIE["id"] and args[0] != "devices" else []
    r = subprocess.run([adb(), *pre, *args], capture_output=True, text=True, timeout=timeout, creationflags=SIN_VENTANA)
    return r.returncode, (r.stdout + r.stderr).strip()


def _apk():
    """El APK compilado más reciente (release o debug)."""
    cands = [p for p in (ROOT / "android/app/build/outputs/apk").glob("*/*.apk")] if (ROOT / "android").exists() else []
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def _version_movil():
    _, txt = _adb("shell", "dumpsys", "package", PAQUETE)
    for linea in txt.splitlines():
        if "versionName=" in linea:
            return linea.split("versionName=", 1)[1].strip()
    return None


def _zip_datos():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in (".env", "rules.json"):
            if (DATOS / n).exists():
                zf.write(DATOS / n, n)
        for p in CACHE.glob("*.json"):
            if p.name not in OBSOLETOS:
                zf.write(p, f"cache/{p.name}")
        for pre in REQUIRED:  # el último export de cada web, esté en Descargas o importado
            x = next(iter(find_exports(pre)), None)
            if x and x.zip:
                zf.write(x.path, f"importados/{x.name}")
    return buf.getvalue()


CLAVE_MOVIL = f"/sdcard/Android/data/{PAQUETE}/files/clave-sincro.txt"  # la escribe la app en cada arranque


def _clave():
    """Clave secreta del servidor del móvil (otras apps del móvil no pueden leerla; adb sí)."""
    code, txt = _adb("shell", "cat", CLAVE_MOVIL, timeout=10)
    return "" if code else txt.strip()


def _post(url, datos, timeout=120):
    req = urllib.request.Request(url, data=datos, method="POST",
                                 headers={"Content-Type": "application/zip", "X-TriSync-Clave": _clave()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def pasar_al_movil(out=print):
    """Instala o actualiza la app en el móvil (si hay APK más nuevo) y le pasa la configuración y la caché."""
    code, txt = _adb("devices")
    moviles = [l.split()[0] for l in txt.splitlines()[1:] if l.strip().endswith("device")]
    moviles.sort(key=lambda m: m.startswith("emulator-"))  # mejor el móvil de verdad que un emulador abierto
    if not moviles:
        raise RuntimeError("No veo ningún móvil: conéctalo por USB con la depuración USB activada y acepta el aviso")
    SERIE["id"] = moviles[0]
    out(f"Móvil conectado ({moviles[0]})")
    actual = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    v = _version_movil()
    apk = _apk()
    if apk and v != actual:
        out(f"Instalando Tri-Sync {actual} en el móvil" + (f" (tenía la {v})" if v else "") + "…")
        code, txt = _adb("install", "-r", str(apk), timeout=300)
        if code:
            raise RuntimeError(f"No se pudo instalar el APK: {txt[-300:]}")
    elif not v:
        raise RuntimeError("Tri-Sync no está instalado en el móvil y no hay APK compilado en android/")
    out("Abriendo Tri-Sync en el móvil…")
    _adb("shell", "am", "start", "-n", f"{PAQUETE}/.MainActivity")
    _adb("forward", f"tcp:{PUERTO_PUENTE}", f"tcp:{PUERTO_MOVIL}")
    try:
        base = f"http://127.0.0.1:{PUERTO_PUENTE}"
        for _ in range(80):  # la primera vez la app tarda unos segundos en arrancar Python
            try:
                with urllib.request.urlopen(base + "/api/ping", timeout=2) as r:
                    if json.loads(r.read()).get("android"):
                        break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("La app del móvil no responde: ábrela a mano y vuelve a probar")
        datos = _zip_datos()
        out(f"Pasando configuración, caché y exports ({len(datos) / 1e6:.1f} MB)…")
        r = _post(base + "/api/sincro/recibir", datos)
        if not r.get("ok"):
            raise RuntimeError(r.get("texto") or "El móvil no aceptó los datos")
        out(f"Listo: {r['archivos']} archivos en el móvil")
    finally:
        _adb("forward", "--remove", f"tcp:{PUERTO_PUENTE}")
