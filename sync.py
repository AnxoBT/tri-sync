"""seriesypelis-sync: compara Dixmax, Letterboxd y Serializd y te deja elegir qué corregir.

Uso:
    python sync.py                 # calcula diferencias y abre la web local
    python sync.py --solo peliculas|series
    python sync.py --sin-calcular  # abre la web con el último cálculo
    python sync.py --no-navegador
"""
import argparse
import json
import sys
import webbrowser
from threading import Timer

from core.config import save_cache
from core.serializd import TokenError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", choices=["peliculas", "series"])
    ap.add_argument("--sin-calcular", action="store_true")
    ap.add_argument("--no-navegador", action="store_true")
    ap.add_argument("--puerto", type=int, default=8765)
    args = ap.parse_args()

    if not args.sin_calcular:
        from core import diff
        try:
            res = diff.compute(solo=args.solo)
        except TokenError as e:
            sys.exit(f"ERROR: {e}")
        save_cache("diff.json", res)
        por_cat = {}
        for d in res["diferencias"]:
            por_cat[d["categoria"]] = por_cat.get(d["categoria"], 0) + 1
        print(f"\n{len(res['diferencias'])} diferencias:")
        for k, v in sorted(por_cat.items(), key=lambda x: -x[1]):
            print(f"  {v:5}  {k}")

    from web.server import serve
    if not args.no_navegador:
        Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{args.puerto}")).start()
    serve(args.puerto)


if __name__ == "__main__":
    main()
