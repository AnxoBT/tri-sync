"""Tri-Sync en el móvil: importar exports desde la web y sincronizar el PC con el móvil por USB (adb).

Nada pasa por internet: el PC habla con la app del móvil por el cable (adb forward), le pide sus datos, los junta con
los suyos y le devuelve el resultado (sincro.py: ajustes, reglas, caché e historial, y el export más nuevo de cada web).
"""
import io
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import config, sincro
from .config import IMPORTADOS, REQUIRED, ROOT

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


def importar_export(nombre, datos, fecha_ms=""):
    """Guarda el zip en la carpeta de importados (sustituye al anterior del mismo tipo). fecha_ms: la del archivo
    original (la da el navegador): así la edad del export es la de cuando lo descargaste, no la de importarlo."""
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
    if str(fecha_ms).isdigit() and 0 < int(fecha_ms) / 1000 <= time.time() + 60:
        os.utime(destino, (int(fecha_ms) / 1000, int(fecha_ms) / 1000))
    return {"tipo": "dixmax" if pre.startswith("playmax") else "letterboxd", "nombre": nombre}


# ---------------- PC: sincronizar con el móvil por USB ----------------

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


CLAVE_MOVIL = f"/sdcard/Android/data/{PAQUETE}/files/clave-sincro.txt"  # la escribe la app en cada arranque


def _clave():
    """Clave secreta del servidor del móvil (otras apps del móvil no pueden leerla; adb sí)."""
    code, txt = _adb("shell", "cat", CLAVE_MOVIL, timeout=10)
    return "" if code else txt.strip()


def _post(url, datos=b"", timeout=120, binario=False):
    req = urllib.request.Request(url, data=datos, method="POST",
                                 headers={"Content-Type": "application/zip", "X-TriSync-Clave": _clave()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read() if binario else json.loads(r.read())


def sincronizar_movil(out=print):
    """Instala o actualiza la app en el móvil (si hay APK más nuevo) y junta los datos de los dos (sincro.py)."""
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
        out("Leyendo los datos del móvil…")
        try:
            suyo = _post(base + "/api/sincro/datos", timeout=300, binario=True)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError("La app del móvil es antigua: compila el APK nuevo para que se actualice al sincronizar")
            raise
        aqui = sincro.recibir(suyo)
        out("Pasando los datos juntos al móvil…")
        r = _post(base + "/api/sincro/recibir", sincro.datos(), timeout=300)
        if not r.get("ok"):
            raise RuntimeError(r.get("texto") or "El móvil no aceptó los datos")
        alli = r.get("cambios", [])
        out("Listo · aquí: " + (", ".join(aqui) or "nada nuevo") + " · en el móvil: " + (", ".join(alli) or "nada nuevo"))
    finally:
        _adb("forward", "--remove", f"tcp:{PUERTO_PUENTE}")
    return {"aqui": aqui, "alli": alli}
