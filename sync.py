"""Tri-Sync: compara Dixmax, Letterboxd y Serializd y te deja elegir qué corregir.

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--revisar", action="store_true")
    ap.add_argument("--solo", choices=["peliculas", "series"])
    ap.add_argument("--no-navegador", action="store_true")
    ap.add_argument("--puerto", type=int, default=8765)
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

    from web.server import serve
    if not args.no_navegador:
        Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{args.puerto}")).start()
    serve(args.puerto)


if __name__ == "__main__":
    main()
