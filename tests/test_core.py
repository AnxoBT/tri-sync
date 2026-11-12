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

from core import config, estadisticas, letterboxd_api, movil  # noqa: E402


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

    def test_rechaza_lo_que_no_es_un_export(self):
        with self.assertRaises(ValueError):
            movil.importar_export("foto.zip", b"no es un zip")
        with self.assertRaises(ValueError):
            movil.importar_export("letterboxd-x.zip", zip_de({"otra.csv": "x"}))
        self.assertEqual(list(config.IMPORTADOS.glob("*")), [])

    def test_ruta_rara_en_el_nombre_no_sale_de_la_carpeta(self):
        movil.importar_export("../../letterboxd-malo.zip", zip_de(LB))
        self.assertTrue((config.IMPORTADOS / "letterboxd-malo.zip").exists())


class PasarAlMovil(unittest.TestCase):
    def test_recibe_y_conserva_la_fecha(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zi = zipfile.ZipInfo("cache/prueba.json", date_time=(2024, 5, 1, 12, 0, 0))
            zf.writestr(zi, "{}")
        movil.recibir(buf.getvalue())
        p = config.CACHE / "prueba.json"
        self.assertTrue(p.exists())
        self.assertEqual(time.localtime(p.stat().st_mtime)[:3], (2024, 5, 1))

    def test_solo_acepta_configuracion_cache_y_exports(self):
        for malo in ("core/diff.py", "web/server.py", "apk/Tri-Sync.apk", "cache/sub/x.json"):
            with self.assertRaises(ValueError, msg=malo):
                movil.recibir(zip_de({malo: "x"}))
        movil.recibir(zip_de({".env": "SERIALIZD_USER=yo\n", "rules.json": "{}", "importados/letterboxd-a.zip": "z"}))

    def test_zip_con_rutas_hacia_fuera_se_rechaza(self):
        with self.assertRaises(ValueError):
            movil.recibir(zip_de({"../fuera.txt": "x"}))
        self.assertFalse((Path(TMP).parent / "fuera.txt").exists())


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

    def test_sin_dixmax_avisa(self):
        from core import diff
        with self.assertRaisesRegex(RuntimeError, "Conecta Dixmax"):
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

    def test_solo_dixmax_pide_otra_app(self):
        from core import diff
        config.guardar_config({"DIXMAX_API_KEY": "a", "DIXMAX_AUTH_KEY": "b"})
        with self.assertRaisesRegex(RuntimeError, "al menos una app más"):
            diff.compute(lambda *a: None)


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
