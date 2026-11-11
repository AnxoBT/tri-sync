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

from .config import ROOT, env

REPO = "AnxoBT/tri-sync"
NO_TOCAR = {".env", "cache", "logs", "data", "salida", ".git", ".venv"}
_CACHE = {"t": 0, "r": None}
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def actual():
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def _num(v):
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def _token():
    t = env("GITHUB_TOKEN")
    if t:
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


def _get(url):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "Tri-Sync", "X-GitHub-Api-Version": "2022-11-28"}
    t = _token()
    if t:
        h["Authorization"] = f"Bearer {t}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        return r.read()


def comprobar(forzar=False):
    """{actual, nueva, notas, url} o {actual, error}. Se guarda 6 h para no preguntar a GitHub a cada rato."""
    if not forzar and _CACHE["r"] and time.time() - _CACHE["t"] < 6 * 3600:
        return _CACHE["r"]
    r = {"actual": actual(), "git": (ROOT / ".git").exists()}
    try:
        rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        tag = rel["tag_name"].lstrip("v")
        if _num(tag) > _num(r["actual"]):
            r.update(nueva=tag, notas=rel.get("body") or "", url=rel.get("html_url"))
    except urllib.error.HTTPError as e:
        r["error"] = ("No puedo ver las versiones (repo privado): pon un token de GitHub en Configuración"
                      if e.code in (401, 403, 404) else f"GitHub respondió {e.code}")
    except Exception as e:
        r["error"] = f"Sin conexión con GitHub ({e.__class__.__name__})"
    _CACHE.update(t=time.time(), r=r)
    return r


def instalar(out=print):
    """Descarga la última release y reemplaza los archivos del programa (copia de seguridad en logs/)."""
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
