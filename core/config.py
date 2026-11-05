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
