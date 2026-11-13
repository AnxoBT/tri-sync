"""Sincronizar por Wi-Fi (en casa) entre dos Tri-Sync: PC ↔ móvil (Android o iPhone), o PC ↔ PC. Hace lo mismo
que por USB: junta los datos de los dos en ambos sentidos (sincro.py) y, si uno es el Android y el otro tiene una
versión más nueva de la app compilada, se la pasa para instalarla.

Uno **espera** (abre un puerto en la red local solo 2 minutos y enseña su dirección y un código) y el otro **conecta**
escribiendo los dos. Todo va cifrado y autenticado con ese código (core/cifrado.py); 5 intentos fallidos cierran la
espera. Recomendado: que espere el móvil y conecte el PC (así el cortafuegos de Windows no pregunta nada).
"""
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from . import cifrado, config, sincro

PUERTOS = (8767, 8768, 8769)
ESPERA = 120  # segundos que se queda abierto
MAX_FALLOS = 5
MAX_CUERPO = 300_000_000
GANCHOS = {"bloqueo": threading.Lock()}  # web/server.py: que no se fusione a mitad de una revisión
ESTADO = {"esperando": False, "direccion": "", "codigo": "", "hasta": 0, "fallos": 0, "conectando": False,
          "log": [], "error": None, "resultado": None, "apk_listo": None}
_SRV = {"srv": None, "ks": None, "sal": b"", "ultimo_id": 0}


def _version():
    return (config.ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _num(v):
    return tuple(int(x) for x in (str(v).lstrip("v").split(".") + ["0", "0"])[:3] if x.isdigit())


def ip_local():
    """IP de este dispositivo en la red de casa (no envía nada: solo pregunta la ruta)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _apk_local():
    from .movil import _apk
    return _apk()


# ---------- mensajes: cabecera JSON + "\n" + datos binarios, todo sellado ----------

def _empaquetar(cabecera, carga=b""):
    return json.dumps(cabecera, ensure_ascii=False).encode() + b"\n" + carga


def _desempaquetar(b):
    i = b.index(b"\n")
    return json.loads(b[:i]), b[i + 1:]


# ---------- quien espera ----------

def _atender(cab, carga):
    """Una operación del otro dispositivo. Devuelve (cabecera, carga) de la respuesta."""
    op = cab.get("op")
    if op == "hola":
        return {"version": _version(), "android": config.ANDROID, "ios": config.IOS}, b""
    if op == "datos":
        return {}, sincro.datos()
    if op == "recibir":
        with GANCHOS["bloqueo"]:
            cambios = sincro.recibir(carga)
        return {"cambios": cambios}, b""
    if op == "apk_bajar":  # el Android pide la versión nueva al PC
        apk = _apk_local()
        return ({"ok": True}, apk.read_bytes()) if apk else ({"ok": False}, b"")
    if op == "apk_subir":  # el PC pasa la versión nueva al Android: se instala con un botón
        if not config.ANDROID:
            return {"ok": False}, b""
        (config.DATOS / "apk").mkdir(exist_ok=True)
        (config.DATOS / "apk" / "Tri-Sync.apk").write_bytes(carga)
        ESTADO["apk_listo"] = cab.get("version")
        return {"ok": True}, b""
    if op == "fin":
        ESTADO["resultado"] = {"aqui": cab.get("alli", []), "alli": cab.get("aqui", []), "t": time.strftime("%d/%m %H:%M")}
        threading.Timer(0.5, parar).start()  # después de contestar
        return {"ok": True}, b""
    raise ValueError("operación desconocida")


class _Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _responder(self, codigo, cuerpo, tipo="application/octet-stream"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path == "/wifi/sal" and ESTADO["esperando"]:  # la sal no es secreta
            return self._responder(200, json.dumps({"sal": _SRV["sal"].hex()}).encode(), "application/json")
        self._responder(404, b"")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if self.path != "/wifi" or not ESTADO["esperando"] or not 0 < n <= MAX_CUERPO or time.time() > ESTADO["hasta"]:
            return self._responder(404, b"")
        ks = _SRV["ks"]
        if not ks:
            return self._responder(404, b"")
        try:
            cab, carga = _desempaquetar(cifrado.abrir(ks, b"c", self.rfile.read(n)))
        except ValueError:
            ESTADO["fallos"] += 1
            if ESTADO["fallos"] >= MAX_FALLOS:
                ESTADO["error"] = "Demasiados intentos con un código incorrecto: se ha cerrado la espera"
                threading.Thread(target=parar, daemon=True).start()
            return self._responder(403, b"")
        # contra repeticiones: cada petición lleva un número mayor que la anterior y la hora
        if not isinstance(cab.get("id"), int) or cab["id"] <= _SRV["ultimo_id"] or abs(time.time() - cab.get("ts", 0)) > 300:
            return self._responder(409, b"")
        _SRV["ultimo_id"] = cab["id"]
        ESTADO["hasta"] = max(ESTADO["hasta"], time.time() + 60)  # mientras se sincroniza no se corta
        try:
            rc, rcarga = _atender(cab, carga)
            rc["id"] = cab["id"]
        except Exception as e:  # noqa: BLE001 — se le cuenta al otro lado
            rc, rcarga = {"id": cab["id"], "error": str(e)}, b""
        self._responder(200, cifrado.sellar(ks, b"s", _empaquetar(rc, rcarga)))


def esperar():
    """Abre la espera (2 min): devuelve el estado con la dirección y el código que hay que escribir en el otro."""
    parar()
    codigo, sal = cifrado.codigo_nuevo(), secrets.token_bytes(16)
    _SRV.update(ks=cifrado.claves(codigo, sal), sal=sal, ultimo_id=0)
    for puerto in PUERTOS:
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", puerto), _Manejador)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No hay ningún puerto libre para esperar la conexión")
    _SRV["srv"] = srv
    ESTADO.update(esperando=True, direccion=f"{ip_local()}:{puerto}", codigo=codigo, hasta=time.time() + ESPERA,
                  fallos=0, error=None, resultado=None, log=[])
    threading.Thread(target=srv.serve_forever, daemon=True, name="wifi").start()
    threading.Thread(target=_vigilar, daemon=True).start()
    return estado()


def _vigilar():
    while ESTADO["esperando"]:
        if time.time() > ESTADO["hasta"]:
            if not ESTADO["resultado"]:
                ESTADO["error"] = ESTADO["error"] or "Se acabó el tiempo sin que se conectara nadie"
            parar()
            return
        time.sleep(1)


def parar():
    srv = _SRV["srv"]
    _SRV.update(srv=None, ks=None)
    ESTADO.update(esperando=False, codigo="")
    if srv:
        srv.shutdown()
        srv.server_close()


def estado():
    return {**{k: v for k, v in ESTADO.items() if k != "hasta"},
            "quedan": max(0, int(ESTADO["hasta"] - time.time())) if ESTADO["esperando"] else 0}


# ---------- quien conecta ----------

def conectar(direccion, codigo, log=print):
    """Sincroniza con el dispositivo que espera en 'direccion' (IP:puerto). Devuelve {aqui, alli, t}."""
    direccion = direccion.strip().removeprefix("http://").rstrip("/")
    if ":" not in direccion:
        direccion += f":{PUERTOS[0]}"
    base = f"http://{direccion}"
    log(f"Conectando con {direccion}…")
    try:
        with urlopen(base + "/wifi/sal", timeout=10) as r:
            sal = bytes.fromhex(json.load(r)["sal"])
    except OSError:
        raise RuntimeError(f"No encuentro Tri-Sync esperando en {direccion}: comprueba la dirección, que los dos estéis "
                           "en el mismo Wi-Fi y que el otro siga esperando")
    ks = cifrado.claves(codigo, sal)
    contador = [int(time.time() * 1000)]

    def pedir(op, extra=None, carga=b"", timeout=120):
        contador[0] += 1
        cab = {"op": op, "id": contador[0], "ts": time.time(), **(extra or {})}
        req = Request(base + "/wifi", data=cifrado.sellar(ks, b"c", _empaquetar(cab, carga)), method="POST",
                      headers={"Content-Type": "application/octet-stream"})
        try:
            with urlopen(req, timeout=timeout) as r:
                rc, rcarga = _desempaquetar(cifrado.abrir(ks, b"s", r.read()))
        except OSError as e:
            if getattr(e, "code", None) == 403:
                raise RuntimeError("Código incorrecto")
            raise RuntimeError(f"Se cortó la conexión ({e})")
        if rc.get("id") != cab["id"]:
            raise RuntimeError("Respuesta que no corresponde a la petición")
        if rc.get("error"):
            raise RuntimeError(f"El otro dispositivo dice: {rc['error']}")
        return rc, rcarga

    otro, _ = pedir("hola")
    log("Leyendo sus datos…")
    _, b = pedir("datos", timeout=300)
    with GANCHOS["bloqueo"]:
        aqui = sincro.recibir(b)
    log("Pasándole los datos juntos…")
    alli = pedir("recibir", carga=sincro.datos(), timeout=300)[0].get("cambios", [])

    # versión de la app: el Android recibe la más nueva compilada en el PC y se instala con un botón
    mia, suya = _num(_version()), _num(otro.get("version", "0"))
    apk = None if config.MOVIL else _apk_local()
    if otro.get("android") and apk and mia > suya:
        log(f"Pasándole Tri-Sync {_version()}…")
        pedir("apk_subir", {"version": _version()}, apk.read_bytes(), timeout=600)
        alli.insert(0, f"Tri-Sync {_version()} (pulsa Instalar allí)")
    elif config.ANDROID and not otro.get("android") and not otro.get("ios") and suya > mia:
        log(f"Trayendo Tri-Sync {otro['version']}…")
        rc, datos_apk = pedir("apk_bajar", timeout=600)
        if rc.get("ok") and datos_apk:
            (config.DATOS / "apk").mkdir(exist_ok=True)
            (config.DATOS / "apk" / "Tri-Sync.apk").write_bytes(datos_apk)
            ESTADO["apk_listo"] = otro["version"]
            aqui.insert(0, f"Tri-Sync {otro['version']} (pulsa Instalar)")

    pedir("fin", {"aqui": aqui, "alli": alli})
    return {"aqui": aqui, "alli": alli, "t": time.strftime("%d/%m %H:%M")}
