"""Configuración: .env, rutas y reglas (casos especiales)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # código (en Android va dentro del APK: de solo lectura)
# Datos que la app modifica (.env, rules.json, caché, logs, exports importados). En el PC = la carpeta del
# programa, como siempre; en Android, la carpeta privada de la app (TRISYNC_DATOS la pone el lanzador).
DATOS = Path(os.environ.get("TRISYNC_DATOS") or ROOT)
ANDROID = bool(os.environ.get("TRISYNC_ANDROID"))
IOS = bool(os.environ.get("TRISYNC_IOS"))
MOVIL = ANDROID or IOS  # en el móvil: sin Descargas, sin abrir carpetas, sin apagarse al cerrar la pestaña
# Lo pone la app del iPhone (la vista web no abre enlaces de fuera ni descarga archivos): abrir_url(url), compartir(ruta)
GANCHOS = {"abrir_url": None, "compartir": None}
CACHE = DATOS / "cache"
LOGS = DATOS / "logs"
IMPORTADOS = DATOS / "importados"  # exports subidos con «Importar export» (en el móvil, la única forma)
CACHE.mkdir(parents=True, exist_ok=True)
IMPORTADOS.mkdir(parents=True, exist_ok=True)


def _load_env():
    env = {}
    p = DATOS / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = _load_env()

EDITABLES = ["DATA_DIR", "SERIALIZD_USER", "LETTERBOXD_USER", "SERIALIZD_TOKEN", "DIXMAX_API_KEY", "DIXMAX_AUTH_KEY",
             "GITHUB_TOKEN", "ANILIST_USER", "ANILIST_TOKEN", "ANILIST_EXPIRA",
             "LETTERBOXD_CLIENT_ID", "LETTERBOXD_CLIENT_SECRET", "LETTERBOXD_TOKEN", "LETTERBOXD_REFRESH", "LETTERBOXD_EXPIRA",
             "IDIOMA"]  # es / en (vacío: el del navegador o el móvil)
SECRETOS = {"SERIALIZD_TOKEN", "DIXMAX_API_KEY", "DIXMAX_AUTH_KEY", "GITHUB_TOKEN", "ANILIST_TOKEN",
            "LETTERBOXD_CLIENT_SECRET", "LETTERBOXD_TOKEN", "LETTERBOXD_REFRESH"}

# Cada app y las claves del .env que son suyas («Quitar» las borra). Dixmax es el centro: todo se compara con él.
APPS = {"dixmax": ["DIXMAX_API_KEY", "DIXMAX_AUTH_KEY"],
        "letterboxd": ["LETTERBOXD_USER", "LETTERBOXD_CLIENT_ID", "LETTERBOXD_CLIENT_SECRET", "LETTERBOXD_TOKEN",
                       "LETTERBOXD_REFRESH", "LETTERBOXD_EXPIRA"],
        "serializd": ["SERIALIZD_USER", "SERIALIZD_TOKEN"],
        "anilist": ["ANILIST_USER", "ANILIST_TOKEN", "ANILIST_EXPIRA"]}


def dixmax_api():
    return bool(env("DIXMAX_API_KEY") and env("DIXMAX_AUTH_KEY"))


def apps():
    """Qué apps tienes conectadas: solo esas salen en la web y se revisan. «Quitar» una la apaga aunque quede su
    export en Descargas (APPS_OFF); volver a configurarla la enciende."""
    tiene = lambda pre: bool(find_exports(pre))  # noqa: E731
    off = set(env("APPS_OFF").split(","))
    return {k: v and k not in off for k, v in _apps(tiene).items()}


def _apps(tiene):
    return {"dixmax": dixmax_api() or tiene("playmax-userdata-"),
            "letterboxd": bool(env("LETTERBOXD_USER") or env("LETTERBOXD_TOKEN")),
            "serializd": bool(env("SERIALIZD_TOKEN")),
            "anilist": bool(env("ANILIST_TOKEN"))}


def config_publica():
    """Configuración para mostrar en la web: los secretos solo como 'puesto / no puesto'."""
    return {k: ({"puesto": bool(ENV.get(k))} if k in SECRETOS else ENV.get(k, "")) for k in EDITABLES}


def _escribir_env():
    otras = [k for k in ENV if k not in EDITABLES]  # p. ej. ADB: se conservan
    lines = [f"{k}={ENV.get(k, '')}" for k in EDITABLES + otras]
    (DATOS / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def guardar_config(cambios):
    """Actualiza el .env (solo claves conocidas; un secreto vacío no borra el existente)."""
    for k, v in cambios.items():
        if k not in EDITABLES:
            continue
        v = " ".join(str(v or "").split()) if k not in SECRETOS else "".join(str(v or "").split())  # sin saltos de línea: cada clave, una línea del .env
        if k in SECRETOS and not v:
            continue
        ENV[k] = v
        if v:  # configurar algo de una app la vuelve a encender
            app = next((a for a, ks in APPS.items() if k in ks), None)
            ENV["APPS_OFF"] = ",".join(x for x in env("APPS_OFF").split(",") if x and x != app)
    _escribir_env()


def quitar_app(app):
    """Desconecta una app: borra sus claves del .env (en la propia web no se toca nada)."""
    if app not in APPS:
        return
    for k in APPS[app]:
        ENV[k] = ""
    ENV["APPS_OFF"] = ",".join(sorted({x for x in env("APPS_OFF").split(",") if x} | {app}))
    _escribir_env()


def recargar_env():
    """Tras recibir un .env nuevo (pasar del PC al móvil)."""
    ENV.clear()
    ENV.update(_load_env())


def env(key, default=""):
    return ENV.get(key) or os.environ.get(key) or default


def descargas():
    return Path.home() / "Downloads"


def export_dirs():
    """Carpetas donde buscar exports (DATA_DIR, separadas por ';'). Por defecto: Descargas.
    Siempre, además, los importados desde la web (en el móvil son los únicos: Android no deja leer Descargas)."""
    out = [IMPORTADOS]
    if MOVIL:
        return out
    for x in (env("DATA_DIR") or str(descargas())).split(";"):
        x = x.strip()
        if x:
            d = Path(x)
            out.append(d if d.is_absolute() else ROOT / d)
    return out


# archivos que debe tener cada export para darlo por válido
REQUIRED = {"playmax-userdata-": ["fichas.json", "episodes.json", "lists.json"],
            "letterboxd-": ["watched.csv", "watchlist.csv", "ratings.csv", "diary.csv"]}


class Export:
    """Export descargado, en carpeta o directamente en el zip (no hace falta descomprimir)."""

    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name
        self.mtime = self.path.stat().st_mtime
        self.zip = self.path.suffix.lower() == ".zip"
        self._prefix = ""
        if self.zip:
            import zipfile
            self._zf = zipfile.ZipFile(self.path)
            names = [n for n in self._zf.namelist() if not n.endswith("/")]
            tops = {n.split("/")[0] for n in names}
            if len(tops) == 1 and all("/" in n for n in names):  # zip con una carpeta dentro
                self._prefix = tops.pop() + "/"
            self._names = set(names)

    def exists(self, rel):
        return (self._prefix + rel) in self._names if self.zip else (self.path / rel).exists()

    def read_text(self, rel):
        if self.zip:
            return self._zf.read(self._prefix + rel).decode("utf-8-sig")
        return (self.path / rel).read_text(encoding="utf-8-sig")

    def missing(self, prefix):
        return [f for f in REQUIRED.get(prefix, []) if not self.exists(f)]


def find_exports(prefix):
    """Exports válidos (carpetas o zips) de todas las carpetas, del más reciente al más antiguo.
    Se ordena por fecha de descarga: la fecha del nombre da igual. Los incompletos se descartan."""
    cands = []
    for d in export_dirs():
        if not d.exists():
            continue
        for p in d.glob(prefix + "*"):
            if p.is_dir() or p.suffix.lower() == ".zip":
                try:
                    x = Export(p)
                except Exception:  # zip a medio descargar o dañado
                    continue
                if not x.missing(prefix):
                    cands.append(x)
    return sorted(cands, key=lambda x: x.mtime, reverse=True)


def latest_export(prefix):
    found = find_exports(prefix)
    if not found:
        raise RuntimeError(f"No encuentro ningún export '{prefix}*' (zip o carpeta) en "
                         f"{' ; '.join(map(str, export_dirs()))}. Descárgalo y vuelve a revisar.")
    return found[0]


def rules():
    """Reglas editables (casos especiales). Ver rules.json."""
    p = DATOS / "rules.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cache_json(name, default=None):
    p = CACHE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default if default is not None else {})


def save_cache(name, data):
    (CACHE / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
