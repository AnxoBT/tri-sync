"""Tri-Sync para iPhone (BeeWare: Briefcase + Toga), como la app de Android con Chaquopy.

Python va dentro de la app: se arranca el servidor de web/server.py en 127.0.0.1:8765 (el mismo puerto que en el PC,
así vale el mismo permiso de AniList) y se enseña en una vista web. Los datos (.env, rules.json, caché…) van en la
carpeta privada de la app. Lo que la vista web del iPhone no sabe hacer sola lo hace aquí, con las APIs de iOS:
abrir enlaces de fuera en Safari y compartir los CSV de Letterboxd (Guardar en Archivos, AirDrop…).
"""
import os
import threading
import time
import urllib.request

import toga
from toga.style import Pack

PUERTO = 8765
BASE = f"http://127.0.0.1:{PUERTO}"


class TriSync(toga.App):
    def startup(self):
        datos = self.paths.data
        datos.mkdir(parents=True, exist_ok=True)
        os.environ["TRISYNC_DATOS"] = str(datos)  # antes de importar core.config
        os.environ["TRISYNC_IOS"] = "1"
        os.environ["TRISYNC_VERSION"] = str(self.version or "0")
        try:  # Python en iOS no trae certificados raíz: los de certifi (si no, nada de https funciona)
            import certifi
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        except ImportError:
            pass
        from core import config
        config.GANCHOS.update(abrir_url=self.abrir_url, compartir=self.compartir)
        from web import server
        threading.Thread(target=server.serve, args=(PUERTO, False), daemon=True, name="trisync").start()

        self.web = toga.WebView(style=Pack(flex=1))
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.web
        self.main_window.show()
        self._sin_barra_de_titulo()  # y, con la vista ya en su sitio, se carga la página (_zona_segura)

    def _sin_barra_de_titulo(self):
        """Toga pone una barra blanca con el título encima; la web ya tiene su cabecera."""
        try:
            impl = self.main_window._impl
            nav = getattr(getattr(impl, "container", None), "controller", None) or getattr(impl, "controller", None)
            nav.setNavigationBarHidden(True, animated=False)
        except Exception as e:  # si cambia Toga, se queda la barra (no rompe nada)
            print(f"Tri-Sync: no se pudo ocultar la barra de título ({e})")
        # sin la barra, la web empezaría debajo de la hora y la isla: dentro de la vista web de Toga el CSS
        # env(safe-area-inset-*) vale 0, así que se deja el hueco aquí (cuando la ventana ya tiene su tamaño)
        self.loop.call_later(0.3, self._zona_segura)

    def _zona_segura(self):
        """Primero se coloca la vista web (debajo de la hora) y DESPUÉS se carga la página: moverla mientras carga
        dejaba la pantalla en blanco cuando el motor web del iPhone tardaba en arrancar."""
        try:
            from rubicon.objc import ObjCClass
            ins = ObjCClass("UIApplication").sharedApplication.keyWindow.safeAreaInsets
            arriba, abajo = int(ins.top), int(ins.bottom)
            # caja oscura a pantalla completa y, dentro, la web con un margen arriba y abajo (el hueco sale oscuro)
            caja = toga.Box(style=Pack(direction="column", flex=1, background_color="#171d23"))
            self.main_window.content = caja
            for nombre in ("margin", "padding"):  # Toga 0.5 llama margin a lo que antes era padding
                try:
                    setattr(self.web.style, f"{nombre}_top", arriba)
                    setattr(self.web.style, f"{nombre}_bottom", abajo)
                    break
                except Exception:
                    continue
            caja.add(self.web)
        except Exception as e:
            print(f"Tri-Sync: no se pudo dejar el hueco de la hora ({e})")
        threading.Thread(target=self._abrir_cuando_responda, daemon=True).start()

    def _abrir_cuando_responda(self):
        for _ in range(150):  # la primera vez tarda un poco
            try:
                with urllib.request.urlopen(BASE + "/api/ping", timeout=1):
                    break
            except Exception:
                time.sleep(0.2)
        self.loop.call_soon_threadsafe(lambda: setattr(self.web, "url", BASE + "/"))

    # ---------------- lo que la vista web no hace sola ----------------
    def abrir_url(self, url):
        """Enlace de fuera (Dixmax, Letterboxd, GitHub…): en Safari."""
        def f():
            from rubicon.objc import ObjCClass
            NSURL, UIApplication = ObjCClass("NSURL"), ObjCClass("UIApplication")
            UIApplication.sharedApplication.openURL(NSURL.URLWithString(url), options={}, completionHandler=None)
        self.loop.call_soon_threadsafe(f)

    def compartir(self, ruta):
        """Menú de compartir de iOS con el archivo (para el CSV de Letterboxd: Guardar en Archivos, AirDrop…)."""
        def f():
            from rubicon.objc import ObjCClass
            NSURL, NSArray = ObjCClass("NSURL"), ObjCClass("NSArray")
            vc = ObjCClass("UIActivityViewController").alloc().initWithActivityItems(
                NSArray.arrayWithObject(NSURL.fileURLWithPath(ruta)), applicationActivities=None)
            raiz = ObjCClass("UIApplication").sharedApplication.keyWindow.rootViewController
            while raiz.presentedViewController:  # encima de lo que esté a la vista
                raiz = raiz.presentedViewController
            raiz.presentViewController(vc, animated=True, completion=None)
        self.loop.call_soon_threadsafe(f)


def main():
    return TriSync("Tri-Sync", "com.anxobt.trisync")
