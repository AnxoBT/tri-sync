"""Cifrado para sincronizar por Wi-Fi (solo librería estándar: no hay AES en Python sin dependencias).

- Código de vinculación de 10 caracteres (≈50 bits) que enseña un dispositivo y se escribe en el otro.
- Clave = PBKDF2-HMAC-SHA256(código, sal aleatoria, 200 000 vueltas): aunque alguien de la red capture el tráfico,
  probar códigos por fuerza bruta es inviable.
- Cada mensaje: cifrado de flujo con BLAKE2b con clave (función pseudoaleatoria) sobre nonce‖contador, y después
  autenticado (encrypt-then-MAC) con otro BLAKE2b con clave, que cubre dirección, nonce y texto cifrado. Un mensaje
  cambiado, de otra sesión o con otro código se rechaza. Los mensajes llevan hora y número de petición contra repeticiones.
"""
import hashlib
import hmac
import secrets

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I: no se confunden al escribirlo
VUELTAS = 200_000
NONCE, ETIQUETA, BLOQUE = 16, 32, 64


def codigo_nuevo():
    """'K7P2Q-9XMA4': 10 caracteres de 32 posibles."""
    c = "".join(secrets.choice(ALFABETO) for _ in range(10))
    return c[:5] + "-" + c[5:]


def normalizar(codigo):
    return "".join(ch for ch in str(codigo).upper() if ch in ALFABETO)


def claves(codigo, sal):
    """(clave de cifrado, clave de autenticación) derivadas del código y la sal."""
    k = hashlib.pbkdf2_hmac("sha256", normalizar(codigo).encode(), sal, VUELTAS, dklen=64)
    return k[:32], k[32:]


def _flujo(k, nonce, n):
    # SHAKE-256 con clave y nonce: el flujo entero en una sola llamada (rápido también con el APK, decenas de MB).
    return hashlib.shake_256(k + nonce).digest(n) if n else b""


def _xor(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big") if a else b""


def _etiqueta(k, direccion, nonce, cifrado):
    return hashlib.blake2b(direccion + nonce + cifrado, key=k, digest_size=ETIQUETA).digest()


def sellar(ks, direccion, datos):
    """ks = claves(...); direccion = b"c" (cliente→servidor) o b"s" (servidor→cliente). Devuelve nonce‖etiqueta‖cifrado."""
    k_cif, k_mac = ks
    nonce = secrets.token_bytes(NONCE)
    cifrado = _xor(datos, _flujo(k_cif, nonce, len(datos)))
    return nonce + _etiqueta(k_mac, direccion, nonce, cifrado) + cifrado


def abrir(ks, direccion, paquete):
    """Descifra lo de sellar(); ValueError si está alterado o es de otra clave."""
    k_cif, k_mac = ks
    if len(paquete) < NONCE + ETIQUETA:
        raise ValueError("mensaje incompleto")
    nonce, etiqueta, cifrado = paquete[:NONCE], paquete[NONCE:NONCE + ETIQUETA], paquete[NONCE + ETIQUETA:]
    if not hmac.compare_digest(etiqueta, _etiqueta(k_mac, direccion, nonce, cifrado)):
        raise ValueError("código incorrecto o mensaje alterado")
    return _xor(cifrado, _flujo(k_cif, nonce, len(cifrado)))
