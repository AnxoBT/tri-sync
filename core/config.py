"""Configuración: .env, rutas y reglas (casos especiales)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)


def _load_env():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = _load_env()

EDITABLES = ["DATA_DIR", "SERIALIZD_USER", "LETTERBOXD_USER", "SERIALIZD_TOKEN", "DIXMAX_API_KEY", "DIXMAX_AUTH_KEY"]
SECRETOS = {"SERIALIZD_TOKEN", "DIXMAX_API_KEY", "DIXMAX_AUTH_KEY"}


def config_publica():
    """Configuración para mostrar en la web: los secretos solo como 'puesto / no puesto'."""
    return {k: ({"puesto": bool(ENV.get(k))} if k in SECRETOS else ENV.get(k, "")) for k in EDITABLES}


def guardar_config(cambios):
    """Actualiza el .env (solo claves conocidas; un secreto vacío no borra el existente)."""
    for k, v in cambios.items():
        if k not in EDITABLES:
            continue
        v = (v or "").strip()
        if k in SECRETOS and not v:
            continue
        ENV[k] = v
    lines = [f"{k}={ENV.get(k, '')}" for k in EDITABLES]
    (ROOT / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def env(key, default=""):
    return ENV.get(key) or os.environ.get(key) or default


def descargas():
    return Path.home() / "Downloads"


def export_dirs():
    """Carpetas donde buscar exports (DATA_DIR, separadas por ';'). Por defecto: Descargas."""
    out = []
    for x in (env("DATA_DIR") or str(descargas())).split(";"):
        x = x.strip()
        if x:
            d = Path(x)
            out.append(d if d.is_absolute() else ROOT / d)
    return out


def data_dir():
    return export_dirs()[0]


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
        raise SystemExit(f"No encuentro ningún export '{prefix}*' (zip o carpeta) en "
                         f"{' ; '.join(map(str, export_dirs()))}. Descárgalo y vuelve a revisar.")
    return found[0]


def rules():
    """Reglas editables (casos especiales). Ver rules.json."""
    p = ROOT / "rules.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cache_json(name, default=None):
    p = CACHE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default if default is not None else {})


def save_cache(name, data):
    (CACHE / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
