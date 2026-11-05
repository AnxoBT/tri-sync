"""Estado de los exports: qué zip/carpeta se usará de cada web y si está completo.

Ya no hace falta descomprimir: se lee directamente el zip más reciente."""
import time
from datetime import datetime

from .config import REQUIRED, export_dirs, find_exports

WEBS = {"dixmax": "playmax-userdata-", "letterboxd": "letterboxd-"}


def _edad(mtime):
    h = (time.time() - mtime) / 3600
    return f"hace {int(h * 60)} min" if h < 1 else f"hace {int(h)} h" if h < 48 else f"hace {int(h / 24)} días"


def estado_exports():
    out = {}
    for k, pre in WEBS.items():
        found = find_exports(pre)
        x = found[0] if found else None
        out[k] = {"carpeta": x.name if x else None,
                  "fecha": datetime.fromtimestamp(x.mtime).strftime("%d/%m/%Y %H:%M") if x else None,
                  "edad": _edad(x.mtime) if x else None,
                  "horas": round((time.time() - x.mtime) / 3600, 1) if x else None,
                  "ubicacion": str(x.path.parent) if x else None,
                  "tipo": ("zip" if x.zip else "carpeta") if x else None,
                  "archivos": REQUIRED[pre],
                  "otros": len(found) - 1 if found else 0}
    out["carpetas"] = [str(d) + ("" if d.exists() else " (no existe)") for d in export_dirs()]
    return out
