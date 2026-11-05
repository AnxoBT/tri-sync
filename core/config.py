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


def env(key, default=""):
    return ENV.get(key) or os.environ.get(key) or default


def data_dir():
    d = Path(env("DATA_DIR", "data"))
    return d if d.is_absolute() else (ROOT / d)


def latest_export(prefix):
    """Carpeta de export más reciente (playmax-userdata-* / letterboxd-*)."""
    # por fecha de modificación (Dixmax nombra con DD-MM-YYYY y el orden alfabético falla entre meses)
    found = sorted((p for p in data_dir().glob(prefix + "*") if p.is_dir()), key=lambda p: p.stat().st_mtime)
    if not found:
        raise SystemExit(f"No encuentro ningún export '{prefix}*' en {data_dir()}. "
                         f"Descárgalo, descomprímelo y déjalo ahí.")
    return found[-1]


def rules():
    """Reglas editables (casos especiales). Ver rules.json."""
    p = ROOT / "rules.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cache_json(name, default=None):
    p = CACHE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default if default is not None else {})


def save_cache(name, data):
    (CACHE / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
