"""Importa los exports descargados (zips en Descargas) a la carpeta de datos, y estado de las fuentes."""
import zipfile
from datetime import datetime
from pathlib import Path

from .config import data_dir

PREFIJOS = {"dixmax": "playmax-userdata-", "letterboxd": "letterboxd-"}


def descargas():
    return Path.home() / "Downloads"


def _latest(folder, prefix, pattern):
    found = [p for p in folder.glob(prefix + pattern)]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def estado_exports():
    out = {}
    for k, pre in PREFIJOS.items():
        d = _latest(data_dir(), pre, "*")
        d = d if d and d.is_dir() else None
        out[k] = {"carpeta": d.name if d else None,
                  "fecha": datetime.fromtimestamp(d.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if d else None}
    return out


def importar_desde_descargas():
    """Descomprime en la carpeta de datos los zips de export más recientes de Descargas
    que aún no estén importados. Devuelve lo que ha hecho."""
    hecho = []
    dd = data_dir()
    dd.mkdir(parents=True, exist_ok=True)
    for k, pre in PREFIJOS.items():
        z = _latest(descargas(), pre, "*.zip")
        if not z:
            hecho.append(f"{k}: no hay ningún zip '{pre}*.zip' en Descargas")
            continue
        destino = dd / z.stem
        if destino.exists():
            hecho.append(f"{k}: {z.name} ya estaba importado")
            continue
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():  # protección contra rutas raras dentro del zip
                if m.startswith("/") or ".." in Path(m).parts:
                    raise ValueError(f"zip sospechoso: {m}")
            zf.extractall(destino)
        # Dixmax mete a veces una carpeta dentro con el mismo nombre
        inner = destino / z.stem
        if inner.is_dir() and not (destino / "fichas.json").exists():
            for p in inner.iterdir():
                p.rename(destino / p.name)
            inner.rmdir()
        hecho.append(f"{k}: importado {z.name}")
    return hecho
