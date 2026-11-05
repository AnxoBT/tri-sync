"""Peticiones HTTP JSON con reintentos (solo librería estándar)."""
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

UA = "seriesypelis-sync/1.0 (uso personal)"


def call(method, url, body=None, headers=None, retries=4, delay=0.25, timeout=90):
    h = {"User-Agent": UA, **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    for attempt in range(retries):
        time.sleep(delay)
        try:
            with urlopen(Request(url, data=data, method=method, headers=h), timeout=timeout) as r:
                raw = r.read().decode("utf-8")
                return r.status, (json.loads(raw) if raw.strip()[:1] in "{[" else raw)
        except HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            return e.code, e.read().decode("utf-8", "replace")[:300]
        except OSError as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            return 0, str(e)
