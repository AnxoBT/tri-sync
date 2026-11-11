"""Tri-Sync: compara Dixmax, Letterboxd, Serializd y AniList y te deja elegir qué corregir.

Uso:
    python sync.py              # abre la web local (desde ahí importas, revisas y aplicas)
    python sync.py --revisar    # revisa antes de abrir la web
    python sync.py --no-navegador
"""
import argparse
import sys
import webbrowser
from datetime import datetime
from threading import Timer

from core.config import save_cache


def _sin_consola():
    """Con pythonw no hay consola: lo que se imprimiría va a logs/servidor.log."""
    if sys.stdout is None or sys.stderr is None:
        from core.config import ROOT
        (ROOT / "logs").mkdir(exist_ok=True)
        f = open(ROOT / "logs" / "servidor.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def main():
    _sin_consola()
    ap = argparse.ArgumentParser()
    ap.add_argument("--revisar", action="store_true")
    ap.add_argument("--solo", choices=["peliculas", "series"])
    ap.add_argument("--no-navegador", action="store_true")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--esperar", action="store_true", help="tras actualizar: espera a que se cierre la versión anterior")
    args = ap.parse_args()

    if args.revisar:
        from core import diff
        try:
            res = diff.compute(solo=args.solo)
        except Exception as e:
            sys.exit(f"ERROR: {e}")
        res["calculado"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_cache("diff.json", res)
        print(f"{len(res['diferencias'])} diferencias")

    url = f"http://127.0.0.1:{args.puerto}"
    import socket
    import time

    def abierto():
        with socket.socket() as s:
            return s.connect_ex(("127.0.0.1", args.puerto)) == 0
    for _ in range(40 if args.esperar else 0):
        if not abierto():
            break
        time.sleep(0.5)
    ya_abierto = abierto()
    if ya_abierto:  # Tri-Sync ya está en marcha: solo abre la página
        if not args.no_navegador:
            webbrowser.open(url)
        return

    from web.server import serve
    if not args.no_navegador:
        Timer(1.0, lambda: webbrowser.open(url)).start()
    serve(args.puerto)


if __name__ == "__main__":
    main()
