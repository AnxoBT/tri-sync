"""Pruebas de Tri-Sync. Sin red ni cuentas: todo en una carpeta temporal.

    python -m unittest discover -s tests -v
"""
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

# carpeta de datos temporal ANTES de importar core.config (ahí se decide dónde está el .env)
TMP = tempfile.mkdtemp(prefix="trisync-pruebas-")
os.environ["TRISYNC_DATOS"] = TMP
os.environ["DATA_DIR"] = str(Path(TMP) / "sin-descargas")
for k in ("DIXMAX_API_KEY", "DIXMAX_AUTH_KEY", "SERIALIZD_TOKEN", "LETTERBOXD_USER", "ANILIST_TOKEN", "LETTERBOXD_TOKEN"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, estadisticas, letterboxd_api, movil, sincro  # noqa: E402


def zip_de(archivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, txt in archivos.items():
            zf.writestr(n, txt)
    return buf.getvalue()


LB = {f"letterboxd-yo-2026/{n}": "Date,Name,Year\n" for n in config.REQUIRED["letterboxd-"]}


class Config(unittest.TestCase):
    def setUp(self):
        config.ENV.clear()
        (config.DATOS / ".env").unlink(missing_ok=True)
        for p in config.IMPORTADOS.glob("*"):
            p.unlink()

    def test_sin_nada_no_hay_apps(self):
        self.assertEqual(config.apps(), {"dixmax": False, "letterboxd": False, "serializd": False, "anilist": False})

    def test_apps_segun_lo_configurado(self):
        config.guardar_config({"DIXMAX_API_KEY": "a", "DIXMAX_AUTH_KEY": "b", "SERIALIZD_TOKEN": "t"})
        self.assertEqual(config.apps(), {"dixmax": True, "letterboxd": False, "serializd": True, "anilist": False})

    def test_quitar_app_borra_solo_sus_claves_y_conserva_otras(self):
        config.ENV["ADB"] = "C:/adb.exe"  # clave que no es de la web: se conserva al guardar
        config.guardar_config({"SERIALIZD_USER": "yo", "SERIALIZD_TOKEN": "t", "LETTERBOXD_USER": "yo"})
        config.quitar_app("serializd")
        config.recargar_env()
        self.assertEqual(config.env("SERIALIZD_TOKEN"), "")
        self.assertEqual(config.env("LETTERBOXD_USER"), "yo")
        self.assertEqual(config.env("ADB"), "C:/adb.exe")

    def test_quitar_dixmax_aunque_quede_su_export_y_volver_a_conectarla(self):
        (config.IMPORTADOS / "playmax-userdata-1.zip").write_bytes(
            zip_de({f: "[]" for f in config.REQUIRED["playmax-userdata-"]}))
        self.assertTrue(config.apps()["dixmax"])
        config.quitar_app("dixmax")
        self.assertFalse(config.apps()["dixmax"])
        config.guardar_config({"DIXMAX_API_KEY": "a", "DIXMAX_AUTH_KEY": "b"})
        self.assertTrue(config.apps()["dixmax"])

    def test_secreto_vacio_no_borra_el_guardado(self):
        config.guardar_config({"SERIALIZD_TOKEN": "t"})
        config.guardar_config({"SERIALIZD_TOKEN": ""})
        self.assertEqual(config.env("SERIALIZD_TOKEN"), "t")

    def test_un_valor_no_puede_colar_claves_en_el_env(self):
        config.guardar_config({"SERIALIZD_USER": "yo\nADB=C:/malo.exe", "SERIALIZD_TOKEN": "t\r\nADB=C:/malo.exe"})
        config.recargar_env()
        self.assertEqual(config.env("ADB"), "")  # ADB es un programa que se ejecuta: no se puede colar
        self.assertEqual(config.env("SERIALIZD_USER"), "yo ADB=C:/malo.exe")

    def test_publica_no_ensena_secretos(self):
        config.guardar_config({"SERIALIZD_TOKEN": "secreto"})
        self.assertNotIn("secreto", json.dumps(config.config_publica()))


class Exports(unittest.TestCase):
    def setUp(self):
        for p in config.IMPORTADOS.glob("*"):
            p.unlink()

    def test_importa_letterboxd_y_sustituye_al_anterior(self):
        r = movil.importar_export("letterboxd-yo-2026.zip", zip_de(LB))
        self.assertEqual(r["tipo"], "letterboxd")
        movil.importar_export("renombrado.zip", zip_de(LB))  # lo reconoce por lo que lleva dentro
        self.assertEqual(len(list(config.IMPORTADOS.glob("letterboxd-*"))), 1)
        self.assertEqual(config.find_exports("letterboxd-")[0].missing("letterboxd-"), [])

    def test_conserva_la_fecha_del_archivo_original(self):
        movil.importar_export("letterboxd-yo-2026.zip", zip_de(LB), "1715000000000")  # 6 de mayo de 2024
        p = next(config.IMPORTADOS.glob("letterboxd-*"))
        self.assertEqual(time.localtime(p.stat().st_mtime)[:2], (2024, 5))

    def test_rechaza_lo_que_no_es_un_export(self):
        with self.assertRaises(ValueError):
            movil.importar_export("foto.zip", b"no es un zip")
        with self.assertRaises(ValueError):
            movil.importar_export("letterboxd-x.zip", zip_de({"otra.csv": "x"}))
        self.assertEqual(list(config.IMPORTADOS.glob("*")), [])

    def test_ruta_rara_en_el_nombre_no_sale_de_la_carpeta(self):
        movil.importar_export("../../letterboxd-malo.zip", zip_de(LB))
        self.assertTrue((config.IMPORTADOS / "letterboxd-malo.zip").exists())


def paquete(env=None, archivos=None, mtimes=None):
    """Lo que manda otro Tri-Sync (sincro.datos())."""
    man = {"version": "1.0.0", "android": True, "ios": False, "env": env or {}, "mtimes": mtimes or {}}
    return zip_de({"sincro.json": json.dumps(man), **(archivos or {})})


class Sincronizar(unittest.TestCase):
    def setUp(self):
        for n in ("prueba.json", "historial.json", "diff.json", config.SELLOS):
            (config.CACHE / n).unlink(missing_ok=True)
        self.antes = dict(config.ENV)

    def tearDown(self):  # sin dejar exports ni ajustes que cambien otras pruebas
        for v in config.IMPORTADOS.glob("*"):
            v.unlink()
        (config.DATOS / "rules.json").unlink(missing_ok=True)
        config.ENV.clear()
        config.ENV.update(self.antes)
        config._escribir_env()

    def test_ajustes_gana_el_cambio_mas_reciente(self):
        config.guardar_config({"SERIALIZD_USER": "aqui", "ANILIST_USER": "viejo"})
        t = config.cache_json(config.SELLOS)["SERIALIZD_USER"]
        cambios = sincro.recibir(paquete({"SERIALIZD_USER": ["alli", t - 100], "ANILIST_USER": ["nuevo", t + 100],
                                          "DATA_DIR": ["C:/otro", t + 100]}))
        self.assertEqual(config.env("SERIALIZD_USER"), "aqui")  # lo de aquí es más nuevo
        self.assertEqual(config.env("ANILIST_USER"), "nuevo")
        self.assertNotEqual(config.ENV.get("DATA_DIR"), "C:/otro")  # es de cada dispositivo
        self.assertEqual(config.cache_json(config.SELLOS)["ANILIST_USER"], t + 100)  # conserva su momento
        self.assertIn("ajustes", cambios)

    def test_ajustes_sin_fechas_solo_rellena(self):
        config.ENV.pop("LETTERBOXD_USER", None)
        config.guardar_config({"SERIALIZD_USER": "aqui"})
        config.save_cache(config.SELLOS, {})
        sincro.recibir(paquete({"SERIALIZD_USER": ["alli", 0], "LETTERBOXD_USER": ["lb", 0]}))
        self.assertEqual(config.env("SERIALIZD_USER"), "aqui")
        self.assertEqual(config.env("LETTERBOXD_USER"), "lb")

    def test_reglas_y_cache_se_juntan(self):
        (config.DATOS / "rules.json").write_text(json.dumps({"series": {"excluir_tmdb": [1], "mapa": {"a": 1}}}), encoding="utf-8")
        config.save_cache("prueba.json", {"x": 1, "y": "error"})
        sincro.recibir(paquete(archivos={
            "rules.json": json.dumps({"series": {"excluir_tmdb": [1, 2], "mapa": {"a": 9, "b": 2}}, "peliculas": {}}),
            "cache/prueba.json": json.dumps({"x": 5, "y": 7, "z": 3})}))
        self.assertEqual(config.rules(), {"series": {"excluir_tmdb": [1, 2], "mapa": {"a": 1, "b": 2}}, "peliculas": {}})
        self.assertEqual(config.cache_json("prueba.json"), {"x": 1, "y": 7, "z": 3})

    def test_resultados_gana_el_mas_reciente_e_historial_se_une(self):
        config.save_cache("diff.json", {"de": "aqui"})
        config.save_cache("historial.json", [{"fecha": "01/01/2026 10:00", "modo": "rapida"}])
        ahora = time.time()
        sincro.recibir(paquete(archivos={"cache/diff.json": json.dumps({"de": "alli"}),
                                         "cache/historial.json": json.dumps([{"fecha": "02/01/2026 10:00", "modo": "completa"}])},
                               mtimes={"cache/diff.json": ahora - 3600}))
        self.assertEqual(config.cache_json("diff.json"), {"de": "aqui"})  # el de allí es más viejo
        self.assertEqual([h["modo"] for h in config.cache_json("historial.json")], ["rapida", "completa"])
        sincro.recibir(paquete(archivos={"cache/diff.json": json.dumps({"de": "alli"})}, mtimes={"cache/diff.json": ahora + 60}))
        self.assertEqual(config.cache_json("diff.json"), {"de": "alli"})

    def test_export_mas_nuevo_pasa(self):
        for v in config.IMPORTADOS.glob("letterboxd-*"):
            v.unlink()
        lb = io.BytesIO()
        with zipfile.ZipFile(lb, "w") as zf:
            for n, t in LB.items():
                zf.writestr(n, t)
        cambios = sincro.recibir(paquete(archivos={"importados/letterboxd-yo-2026.zip": lb.getvalue()},
                                         mtimes={"importados/letterboxd-yo-2026.zip": 1715000000}))
        self.assertIn("export de Letterboxd", cambios)
        self.assertEqual(int((config.IMPORTADOS / "letterboxd-yo-2026.zip").stat().st_mtime), 1715000000)
        self.assertNotIn("export de Letterboxd", sincro.recibir(sincro.datos()))  # el mismo: no cambia nada

    def test_ida_y_vuelta_no_cambia_nada(self):
        config.guardar_config({"SERIALIZD_USER": "yo"})
        config.save_cache("prueba.json", {"x": 1})
        self.assertEqual(sincro.recibir(sincro.datos()), [])

    def test_solo_acepta_configuracion_cache_y_exports(self):
        for malo in ("core/diff.py", "web/server.py", "apk/Tri-Sync.apk", "cache/sub/x.json", ".env", "../fuera.txt"):
            with self.assertRaises(ValueError, msg=malo):
                sincro.recibir(paquete(archivos={malo: "x"}))
        with self.assertRaises(ValueError):  # sin manifiesto
            sincro.recibir(zip_de({"rules.json": "{}"}))
        self.assertFalse((Path(TMP).parent / "fuera.txt").exists())


class Wifi(unittest.TestCase):
    def test_cifrado(self):
        from core import cifrado
        codigo = cifrado.codigo_nuevo()
        self.assertEqual(len(cifrado.normalizar(codigo)), 10)
        ks = cifrado.claves(codigo.lower(), b"s" * 16)  # da igual mayúsculas y guion
        datos = bytes(range(256)) * 300
        p = cifrado.sellar(ks, b"c", datos)
        self.assertNotIn(datos[:64], p)  # no viaja en claro
        self.assertEqual(cifrado.abrir(ks, b"c", p), datos)
        with self.assertRaises(ValueError):  # al revés (respuesta usada como petición)
            cifrado.abrir(ks, b"s", p)
        alterado = bytearray(p)
        alterado[-1] ^= 1
        with self.assertRaises(ValueError):
            cifrado.abrir(ks, b"c", bytes(alterado))
        with self.assertRaises(ValueError):  # otro código
            cifrado.abrir(cifrado.claves("AAAAA-AAAAA", b"s" * 16), b"c", p)

    def test_sincronizar_de_verdad(self):
        """Dos Tri-Sync en este PC (uno espera y otro conecta) por una conexión de red real."""
        from core import wifi
        recibido = []
        with mock.patch.object(sincro, "datos", lambda: b"mis datos"), \
                mock.patch.object(sincro, "recibir", lambda d: recibido.append(d) or ["caché"]), \
                mock.patch.object(wifi, "ip_local", lambda: "127.0.0.1"):
            e = wifi.esperar()
            try:
                self.assertTrue(e["esperando"])
                with self.assertRaises(RuntimeError):  # código equivocado
                    wifi.conectar(e["direccion"], "ZZZZZ-ZZZZZ", log=lambda m: None)
                self.assertEqual(wifi.ESTADO["fallos"], 1)
                res = wifi.conectar(e["direccion"], e["codigo"], log=lambda m: None)
            finally:
                wifi.parar()
        self.assertEqual(res["aqui"], ["caché"])
        self.assertEqual(res["alli"], ["caché"])
        self.assertEqual(recibido, [b"mis datos", b"mis datos"])  # cada lado recibió los datos del otro
        self.assertFalse(wifi.ESTADO["esperando"])  # tras sincronizar se cierra sola

    def test_conexion_muda_no_bloquea_la_buena(self):
        """Alguien de la red abre una conexión y no manda el cuerpo: la buena entra igual al cortarse por tiempo."""
        import socket
        from core import wifi
        with mock.patch.object(sincro, "datos", lambda: b"x"), mock.patch.object(sincro, "recibir", lambda d: []),                 mock.patch.object(wifi, "ip_local", lambda: "127.0.0.1"), mock.patch.object(wifi._Manejador, "timeout", 1):
            e = wifi.esperar()
            muda = socket.create_connection(("127.0.0.1", int(e["direccion"].rsplit(":", 1)[1])))
            try:
                muda.sendall(b"POST /wifi HTTP/1.1
Host: x
Content-Length: 100

")
                time.sleep(0.2)
                t = time.time()
                res = wifi.conectar(e["direccion"], e["codigo"], log=lambda m: None)
                self.assertLess(time.time() - t, 15)
                self.assertEqual(res["aqui"], [])
            finally:
                muda.close()
                wifi.parar()

    def test_se_cierra_con_intentos_fallidos(self):
        from core import wifi
        with mock.patch.object(wifi, "ip_local", lambda: "127.0.0.1"):
            e = wifi.esperar()
            try:
                for _ in range(wifi.MAX_FALLOS):
                    with self.assertRaises(RuntimeError):
                        wifi.conectar(e["direccion"], "ZZZZZ-ZZZZZ", log=lambda m: None)
                time.sleep(0.5)
                self.assertFalse(wifi.ESTADO["esperando"])
                self.assertIn("intentos", wifi.ESTADO["error"])
            finally:
                wifi.parar()


class Idioma(unittest.TestCase):
    def test_traducciones_validas(self):
        import re
        d = json.loads((Path(__file__).resolve().parent.parent / "web" / "i18n_en.json").read_text(encoding="utf-8"))
        self.assertGreater(len(d["exactos"]), 400)
        for patron, sust in d["patrones"]:
            re.compile(patron)
            self.assertIsInstance(sust, str)
        self.assertTrue(all(isinstance(v, str) and v for v in d["exactos"].values()))


class Novedades(unittest.TestCase):
    def test_hay_novedades_de_la_version_actual(self):
        """Al subir VERSION hay que escribir sus novedades (se enseñan al actualizar), en español e inglés."""
        raiz = Path(__file__).resolve().parent.parent
        v = (raiz / "VERSION").read_text(encoding="utf-8").strip()
        d = json.loads((raiz / "web" / "novedades.json").read_text(encoding="utf-8"))
        self.assertIn(v, d, f"Falta la entrada {v} en web/novedades.json")
        for idioma in ("es", "en"):
            self.assertTrue(d[v].get(idioma) and all(isinstance(x, str) and x for x in d[v][idioma]), idioma)
        self.assertEqual(len(d[v]["es"]), len(d[v]["en"]))


class Estadisticas(unittest.TestCase):
    def test_racha(self):
        from datetime import date
        dias = {date(2026, 1, d) for d in (1, 2, 3, 5, 6)}
        self.assertEqual(estadisticas._racha(dias), (3, date(2026, 1, 3)))

    def test_madrugada_cuenta_para_el_dia_anterior(self):
        from datetime import datetime
        self.assertEqual(str(estadisticas._dia(datetime(2026, 1, 2, 3, 0))), "2026-01-01")
        self.assertEqual(str(estadisticas._dia(datetime(2026, 1, 2, 7, 0))), "2026-01-02")


class LetterboxdAPI(unittest.TestCase):
    def test_lids_por_tmdb(self):
        resp = {"items": [{"id": "2bbs", "links": [{"type": "tmdb", "id": "11"}]}]}
        with mock.patch.object(letterboxd_api, "_call", return_value=resp) as c:
            self.assertEqual(letterboxd_api.lids([11, 12]), {"11": "2bbs", "12": None})
            self.assertIn("tmdb:11", c.call_args.kwargs["params"]["filmId"])

    def test_registrar_manda_diario_nota_y_like(self):
        letterboxd_api._LID["603"] = "abcd"
        with mock.patch.object(letterboxd_api, "_call") as c:
            letterboxd_api.registrar(603, "2026-01-02T20:00:00Z", 4.5, like=True)
        metodo, ruta, body = c.call_args.args
        self.assertEqual((metodo, ruta), ("POST", "/log-entries"))
        self.assertEqual(body, {"filmId": "abcd", "diaryDetails": {"diaryDate": "2026-01-02", "rewatch": False},
                                "like": True, "rating": 4.5})

    def test_codigo_con_state_distinto_se_rechaza(self):
        letterboxd_api._ESTADO["state"] = "bueno"
        with self.assertRaises(letterboxd_api.LetterboxdError):
            letterboxd_api.recibir_codigo("codigo", "malo")


class Revision(unittest.TestCase):
    def setUp(self):
        config.ENV.clear()
        (config.DATOS / ".env").unlink(missing_ok=True)
        for v in config.IMPORTADOS.glob("*"):  # los exports que dejan otras pruebas
            v.unlink()

    def test_sin_apps_avisa(self):
        from core import diff
        with self.assertRaisesRegex(RuntimeError, "al menos una app"):
            diff.compute(lambda *a: None)

    def test_letterboxd_sin_export_no_tumba_la_revision(self):
        from core import diff
        config.guardar_config({"DIXMAX_API_KEY": "a", "DIXMAX_AUTH_KEY": "b", "LETTERBOXD_USER": "yo", "SERIALIZD_TOKEN": "t"})
        avisos = []
        with mock.patch.object(diff, "Serializd") as sz, mock.patch.object(diff, "leer_serializd"), \
                mock.patch.object(diff.dixmax, "load", side_effect=RuntimeError("parado aquí")):
            sz.return_value.check.return_value = "yo"
            with self.assertRaisesRegex(RuntimeError, "parado aquí"):  # llega a Dixmax: Letterboxd no lo ha parado
                diff.compute(avisos.append)
        self.assertTrue(any("Letterboxd: no hay export" in a for a in avisos))

    def test_sin_dixmax_solo_serializd(self):
        """Sin Dixmax: el historial sale de Serializd y, sin AniList, no hay con qué compararlo (pero sí estadísticas)."""
        from concurrent.futures import Future
        from core import diff

        def hecho(v):
            f = Future()
            f.set_result(v)
            return f
        config.guardar_config({"SERIALIZD_TOKEN": "t"})
        pre = {"diario": hecho(DIARIO_SZ), "notas": hecho([]),
               "listas": {k: hecho({1399: {"name": "Juego de Tronos"}} if k == "watched" else {}) for k in
                          ("watched", "watchlist", "watching", "dropped")}}
        with mock.patch.object(diff, "Serializd") as sz, mock.patch.object(diff, "leer_serializd", return_value=pre):
            sz.return_value.user = "yo"
            r = diff.compute(lambda *a: None)
        self.assertTrue(r["sin_dixmax"])
        self.assertEqual(r["diferencias"], [])
        self.assertIn("no tienen nada en común", r["aviso"])
        b = config.cache_json(estadisticas.BASE)
        self.assertEqual([(x["t"], x["st"], len(x["eps"])) for x in b["series"]], [("Juego de Tronos", "finished", 2)])


DIARIO_SZ = [
    {"showId": 1399, "showName": "Juego de Tronos", "showPremiereDate": "2011-04-17", "seasonId": 10, "episodeNumber": 1,
     "showSeasons": [{"id": 10, "seasonNumber": 1}], "backdate": "2020-01-02T21:00:00Z"},
    {"showId": 1399, "showName": "Juego de Tronos", "showPremiereDate": "2011-04-17", "seasonId": 10, "episodeNumber": 2,
     "showSeasons": [{"id": 10, "seasonNumber": 1}], "backdate": "2020-01-03T21:00:00Z"},
    {"showId": 1399, "showName": "Juego de Tronos", "showPremiereDate": "2011-04-17", "seasonId": 10, "episodeNumber": 2,
     "showSeasons": [{"id": 10, "seasonNumber": 1}], "backdate": "2021-05-05T21:00:00Z"},  # vista otra vez: cuenta la primera
    {"showId": 1399, "showName": "Juego de Tronos", "seasonId": None, "episodeNumber": None, "rating": 9, "like": True,
     "dateAdded": "2021-06-01T00:00:00Z"},
]


class HistorialSinDixmax(unittest.TestCase):
    def test_series_de_serializd(self):
        from core import base
        listas = {"watched": {1399: {}}, "watching": {}, "watchlist": {66732: {"name": "Stranger Things"}}, "dropped": {}}
        s = {x["title"]: x for x in base.series_serializd(DIARIO_SZ, listas, [])}
        got = s["Juego de Tronos"]
        self.assertEqual((got["status"], got["year"], got["rating10"], got["favorite"]), ("finished", 2011, 9, True))
        self.assertEqual([(e["season"], e["episode"], e["date"][:10]) for e in got["episodes"]],
                         [(1, 1, "2020-01-02"), (1, 2, "2020-01-03")])
        self.assertEqual((s["Stranger Things"]["status"], s["Stranger Things"]["episodes"]), ("watchlist", []))

    def test_pelis_de_letterboxd(self):
        from core import base
        lb = {"films": [{"name": "Perfect Blue", "year": "1997", "uri": "https://boxd.it/x", "watched": True, "watchlist": False,
                         "rating": 4.5, "like": True, "diary": [{"date": "2023-02-01"}, {"date": "2024-03-01"}]},
                        {"name": "Nada", "year": "2000", "uri": "https://boxd.it/y", "watched": False, "watchlist": False,
                         "rating": None, "like": False, "diary": []}]}
        with mock.patch.object(base, "tmdb_letterboxd", return_value={"https://boxd.it/x": 10494}):
            pelis = base.pelis_letterboxd(lb)
        self.assertEqual(len(pelis), 1)
        p = pelis[0]
        self.assertEqual((p["tmdb"], p["year"], p["rating10"], p["favorite"], p["date"]),
                         (10494, 1997, 9.0, True, "2024-03-01T12:00:00"))

    def test_anime_solo_en_anilist(self):
        from core import base
        mp = {"tv": {"37854": [[21, 1]]}, "mv": {"10494": [437]}}
        dx = {"movies": [], "shows": [], "al_lista": {
            21: {"status": "CURRENT", "progress": 3, "score": 9.0, "completedAt": {}},
            437: {"status": "COMPLETED", "progress": 1, "score": 8.5, "completedAt": {"year": 2024, "month": 5, "day": 2}}}}
        med = {"21": {"formato": "TV", "titulo": "One Piece", "inicio": [1999, 10, 20]},
               "437": {"formato": "MOVIE", "titulo": "Perfect Blue", "inicio": [1997, 2, 28]}}
        with mock.patch("core.anilist.medios", return_value=med):
            base.anime_anilist(dx, mp)
        (sh,), (pe,) = dx["shows"], dx["movies"]
        self.assertEqual((sh["tmdb"], sh["status"], len(sh["episodes"]), dx["anime_al"][sh["id"]]), (37854, "watching", 3, 21))
        self.assertEqual((pe["tmdb"], pe["status"], pe["date"], pe["rating10"]), (10494, "watched", "2024-05-02T12:00:00", 8.5))
        # lo que ya está por Serializd no se duplica
        dx2 = {"movies": [], "shows": [{"tmdb": 37854}], "al_lista": {21: dx["al_lista"][21]}}
        with mock.patch("core.anilist.medios", return_value=med):
            base.anime_anilist(dx2, mp)
        self.assertEqual(len(dx2["shows"]), 1)


class Servidor(unittest.TestCase):
    """El servidor solo atiende a la propia web de Tri-Sync (ni otras webs del navegador ni DNS rebinding)."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer

        from web import server
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.puerto = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def pedir(self, metodo, ruta, cab=None, cuerpo=None):
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=5)
        c.request(metodo, ruta, body=cuerpo, headers=cab or {})
        r = c.getresponse()
        return r.status, r.read()

    def test_otra_web_no_puede_cambiar_nada(self):
        s, _ = self.pedir("POST", "/api/config", {"Origin": "https://web-mala.example"}, b'{"SERIALIZD_USER":"x"}')
        self.assertEqual(s, 403)

    def test_dns_rebinding(self):
        s, _ = self.pedir("GET", "/api/config", {"Host": "web-mala.example"})
        self.assertEqual(s, 403)

    def test_la_propia_web_si(self):
        s, _ = self.pedir("POST", "/api/config", {"Origin": f"http://127.0.0.1:{self.puerto}"}, b"{}")
        self.assertEqual(s, 200)
        s, b = self.pedir("GET", "/api/ping")
        self.assertEqual((s, json.loads(b)["ok"]), (200, True))

    def test_otro_puerto_de_localhost_tampoco(self):
        s, _ = self.pedir("POST", "/api/config", {"Origin": "http://localhost:3000"}, b"{}")
        self.assertEqual(s, 403)

    def test_en_android_otras_apps_necesitan_la_clave(self):
        # Otras apps del móvil llegan a 127.0.0.1 sin Origin: sin la clave del arranque no se les contesta
        from unittest import mock

        from web import server
        with mock.patch.object(server, "SECRETO", "clave-de-prueba"):
            self.assertEqual(self.pedir("GET", "/api/config")[0], 403)
            self.assertEqual(self.pedir("POST", "/api/run", None, b'{"simulacion": false}')[0], 403)
            self.assertEqual(self.pedir("GET", "/api/config", {"X-TriSync-Clave": "otra"})[0], 403)
            self.assertEqual(self.pedir("GET", "/api/config", {"X-TriSync-Clave": "clave-de-prueba"})[0], 200)
            self.assertEqual(self.pedir("GET", "/api/config", {"Cookie": "trisync=clave-de-prueba"})[0], 200)
            self.assertEqual(self.pedir("GET", "/api/ping")[0], 200)  # el arranque de la app espera al ping

    def test_la_app_recibe_la_clave_en_una_cookie(self):
        from unittest import mock

        from web import server
        with mock.patch.object(server, "SECRETO", "clave-de-prueba"):
            c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=5)
            c.request("GET", "/?k=clave-de-prueba")
            r = c.getresponse()
            r.read()
            self.assertEqual(r.status, 302)
            self.assertIn("trisync=clave-de-prueba", r.getheader("Set-Cookie"))
            self.assertIn("HttpOnly", r.getheader("Set-Cookie"))
            self.assertEqual(self.pedir("GET", "/?k=mala")[0], 403)

    def test_permiso_de_anilist_solo_si_lo_has_pedido(self):
        # una web que abra /anilist#access_token=<el suyo> no puede colarlo
        o = {"Origin": f"http://127.0.0.1:{self.puerto}"}
        _, b = self.pedir("POST", "/api/anilist_token", o, b'{"access_token": "del-atacante"}')
        self.assertFalse(json.loads(b)["ok"])
        self.pedir("POST", "/api/anilist/conectar", o, b"{}")
        with mock.patch("core.anilist.viewer", return_value={"name": "yo"}):
            _, b = self.pedir("POST", "/api/anilist_token", o, b'{"access_token": "bueno", "expires_in": 100}')
        self.assertTrue(json.loads(b)["ok"])
        _, b = self.pedir("POST", "/api/anilist_token", o, b'{"access_token": "otro"}')  # de un solo uso
        self.assertFalse(json.loads(b)["ok"])

    def test_en_el_pc_no_se_reciben_datos_de_fuera(self):
        s, _ = self.pedir("POST", "/api/sincro/recibir", {}, zip_de({".env": "ADB=malo"}))
        self.assertEqual(s, 403)

    def test_descargar_no_sale_de_logs(self):
        s, _ = self.pedir("GET", "/api/descargar/..%2F.env")
        self.assertEqual(s, 404)

    def test_config_no_ensena_secretos(self):
        config.guardar_config({"SERIALIZD_TOKEN": "secreto"})
        _, b = self.pedir("GET", "/api/config")
        self.assertNotIn(b"secreto", b)


if __name__ == "__main__":
    unittest.main()
