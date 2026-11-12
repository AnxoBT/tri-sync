"""Avisa de versiones nuevas en GitHub (releases) y se actualiza solo, sin tocar tu .env, cache ni logs."""
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

from .config import ANDROID, DATOS, IOS, ROOT, env

REPO = "AnxoBT/tri-sync"
NO_TOCAR = {".env", "rules.json", "cache", "logs", "data", "salida", ".git", ".venv"}
_CACHE = {"t": 0, "r": None}
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def actual():
    import os
    if os.environ.get("TRISYNC_VERSION"):  # el iPhone no lleva el archivo VERSION: se lo pasa la app
        return os.environ["TRISYNC_VERSION"]
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def _num(v):
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def _token():
    t = env("GITHUB_TOKEN")
    if t or ANDROID or IOS:  # en el móvil no hay gh ni git (y Android no deja lanzar programas)
        return t
    try:  # si tienes GitHub CLI (gh) con sesión iniciada, vale eso
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5, creationflags=SIN_VENTANA)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    try:  # o Git con tu cuenta de GitHub guardada (sin ventanas: si no hay credencial, no pregunta)
        r = subprocess.run(["git", "-c", "credential.interactive=false", "credential", "fill"],
                           input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True, timeout=10,
                           creationflags=SIN_VENTANA, env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0",
                                                          "GCM_INTERACTIVE": "never"})
        for linea in r.stdout.splitlines():
            if linea.startswith("password="):
                return linea.split("=", 1)[1]
    except Exception:
        pass
    return ""


def _get(url, binario=False):
    h = {"Accept": "application/octet-stream" if binario else "application/vnd.github+json", "User-Agent": "Tri-Sync",
         "X-GitHub-Api-Version": "2022-11-28"}
    req = urllib.request.Request(url, headers=h)
    t = _token()
    if t:
        req.add_unredirected_header("Authorization", f"Bearer {t}")  # no se reenvía al servidor de descargas
    with urllib.request.urlopen(req, timeout=300 if binario else 60) as r:
        return r.read()


def _apk(rel):
    return next((a["url"] for a in rel.get("assets", []) if a.get("name", "").endswith(".apk")), None)


def comprobar(forzar=False):
    """{actual, nueva, notas, url} o {actual, error}. Se guarda 6 h para no preguntar a GitHub a cada rato."""
    if not forzar and _CACHE["r"] and time.time() - _CACHE["t"] < 6 * 3600:
        return _CACHE["r"]
    r = {"actual": actual(), "git": (ROOT / ".git").exists(), "android": ANDROID, "ios": IOS}
    try:
        rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        tag = rel["tag_name"].lstrip("v")
        if _num(tag) > _num(r["actual"]) and (not ANDROID or _apk(rel)):
            r.update(nueva=tag, notas=rel.get("body") or "", url=rel.get("html_url"))
    except urllib.error.HTTPError as e:
        r["error"] = ("No puedo ver las versiones (repo privado): pon un token de GitHub en Configuración"
                      if e.code in (401, 403, 404) else f"GitHub respondió {e.code}")
    except Exception as e:
        r["error"] = f"Sin conexión con GitHub ({e.__class__.__name__})"
    _CACHE.update(t=time.time(), r=r)
    return r


def instalar(out=print):
    """Descarga la última release y reemplaza los archivos del programa (copia de seguridad en logs/).
    En el móvil descarga el APK de la release; la app abre el instalador de Android (/android/instalar)."""
    if IOS:
        raise RuntimeError("En el iPhone, descarga el IPA nuevo de la release e instálalo con Sideloadly o AltStore")
    if ANDROID:
        rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        tag = rel["tag_name"].lstrip("v")
        if not _apk(rel):
            raise RuntimeError("La release no trae APK")
        out(f"Descargando Tri-Sync {tag} para Android…")
        (DATOS / "Tri-Sync.apk").write_bytes(_get(_apk(rel), binario=True))
        _CACHE.update(t=0, r=None)
        out("Descargado: ahora se abre el instalador de Android")
        return tag
    if (ROOT / ".git").exists():
        raise RuntimeError("Esta carpeta es un clon de git: actualiza con «git pull»")
    rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
    tag = rel["tag_name"].lstrip("v")
    out(f"Descargando la versión {tag}…")
    zf = zipfile.ZipFile(io.BytesIO(_get(rel["zipball_url"])))
    raiz = zf.namelist()[0].split("/")[0] + "/"
    nuevos = [n for n in zf.namelist() if n.startswith(raiz) and not n.endswith("/")]
    if raiz + "sync.py" not in nuevos:
        raise RuntimeError("La descarga no parece de Tri-Sync")
    copia = ROOT / "logs" / f"copia_v{actual()}"
    out("Guardando una copia de la versión actual…")
    shutil.rmtree(copia, ignore_errors=True)
    for p in ROOT.rglob("*"):
        rel_p = p.relative_to(ROOT)
        if p.is_file() and rel_p.parts[0] not in NO_TOCAR and "__pycache__" not in rel_p.parts:
            (copia / rel_p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, copia / rel_p)
    out("Instalando…")
    for n in nuevos:
        rel_p = n[len(raiz):]
        if rel_p.split("/")[0] in NO_TOCAR:
            continue
        dest = ROOT / rel_p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(n))
    out("Comprobando librerías…")
    py = sys.executable.replace("pythonw.exe", "python.exe")
    try:  # por si la versión nueva necesita alguna librería más
        subprocess.run([py, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], timeout=300,
                       creationflags=SIN_VENTANA, capture_output=True)
    except Exception:
        pass
    out(f"Versión {tag} instalada. Reiniciando…")
    return tag


def reiniciar(puerto):
    """Arranca la versión nueva (espera a que esta suelte el puerto) sin abrir otra pestaña."""
    py = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([py, str(ROOT / "sync.py"), "--puerto", str(puerto), "--no-navegador", "--esperar"],
                     cwd=str(ROOT), creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | SIN_VENTANA,
                     close_fds=True)
