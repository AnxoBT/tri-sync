"""Arranque de Tri-Sync en Android (lo llama MainActivity a través de Chaquopy).

Los datos que la app modifica (.env, rules.json, caché, logs, exports importados) van en la carpeta privada
de la app: el código viene dentro del APK y se reemplaza en cada actualización.
"""
import os
import sys
import threading

ARRANCADO = threading.Event()


def arrancar(datos, puerto=8765, secreto=""):
    if ARRANCADO.is_set():
        return
    os.environ["TRISYNC_DATOS"] = datos  # antes de importar core.config
    os.environ["TRISYNC_ANDROID"] = "1"
    os.environ["TRISYNC_SECRETO"] = secreto  # sin ella, el servidor no contesta (otras apps llegan a 127.0.0.1)
    os.makedirs(os.path.join(datos, "logs"), exist_ok=True)
    log = open(os.path.join(datos, "logs", "servidor.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    from web import server
    threading.Thread(target=server.serve, args=(puerto, False), daemon=True, name="trisync").start()
    ARRANCADO.set()
