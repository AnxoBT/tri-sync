"""Importa los exports descargados (zips) a la carpeta de datos, y estado de las fuentes.

Busca zips cuyo nombre EMPIECE por 'playmax-userdata-' (Dixmax) o 'letterboxd-' (Letterboxd)
en Descargas y en la carpeta de datos. De cada web coge el más reciente (por fecha de descarga),
lo descomprime en la carpeta de datos y no repite los ya importados. La fecha del nombre da igual.
"""
import zipfile
from datetime import datetime
from pathlib import Path

from .config import data_dir

PREFIJOS = {"dixmax": "playmax-userdata-", "letterboxd": "letterboxd-"}


def descargas():
    return Path.home() / "Downloads"


def _latest(folders, prefix, pattern):
    found = [p for f in folders if f.exists() for p in f.glob(prefix + pattern)]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def estado_exports():
    out = {}
    for k, pre in PREFIJOS.items():
        d = _latest([data_dir()], pre, "*")
        d = d if d and d.is_dir() else None
        out[k] = {"carpeta": d.name if d else None,
                  "fecha": datetime.fromtimestamp(d.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if d else None}
    return out


def importar_desde_descargas():
    hecho = []
    dd = data_dir()
    dd.mkdir(parents=True, exist_ok=True)
    for k, pre in PREFIJOS.items():
        z = _latest([descargas(), dd], pre, "*.zip")
        if not z:
            hecho.append(f"{k}: sin zip nuevo")
            continue
        destino = dd / z.stem
        if destino.exists():
            hecho.append(f"{k}: {z.name} ya importado")
            continue
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():  # protección contra rutas raras dentro del zip
                if m.startswith("/") or ".." in Path(m).parts:
                    raise ValueError(f"zip sospechoso: {m}")
            zf.extractall(destino)
        inner = destino / z.stem  # algunos zips traen una carpeta dentro con el mismo nombre
        if inner.is_dir() and not any(destino.glob("*.json")) and not any(destino.glob("*.csv")):
            for p in inner.iterdir():
                p.rename(destino / p.name)
            inner.rmdir()
        hecho.append(f"{k}: importado {z.name}")
    return hecho
