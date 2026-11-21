"""Frena la fuerza bruta en login y registro.

Cuenta intentos fallidos en memoria (el servidor corre con un solo proceso): por IP y
por email. Pasado el tope bloquea un rato. Un reinicio del servidor lo reinicia, lo
cual es aceptable para este uso.
"""
import time
from collections import defaultdict, deque

from fastapi import Request

VENTANA_SEG = 15 * 60
TOPE_POR_EMAIL = 6  # a una cuenta concreta
TOPE_POR_IP = 20  # desde una misma conexión, contra cualquier cuenta o código

_fallos: dict[str, deque] = defaultdict(deque)


def ip_de(request: Request) -> str:
    # Detrás de Caddy o de Tailscale Funnel la IP real llega en X-Forwarded-For. La app
    # solo escucha en 127.0.0.1, así que ese encabezado lo pone el proxy, no el cliente.
    adelante = request.headers.get("x-forwarded-for", "")
    return (adelante.split(",")[0].strip() if adelante else "") or (request.client.host if request.client else "?")


def _purgar(clave: str) -> deque:
    q = _fallos[clave]
    limite = time.monotonic() - VENTANA_SEG
    while q and q[0] < limite:
        q.popleft()
    return q


def bloqueado(request: Request, email: str = "") -> bool:
    if len(_purgar("ip:" + ip_de(request))) >= TOPE_POR_IP:
        return True
    return bool(email) and len(_purgar("em:" + email.lower())) >= TOPE_POR_EMAIL


def registrar_fallo(request: Request, email: str = "") -> None:
    ahora = time.monotonic()
    _fallos["ip:" + ip_de(request)].append(ahora)
    if email:
        _fallos["em:" + email.lower()].append(ahora)


def limpiar_email(email: str) -> None:
    """Un ingreso correcto borra los fallos de esa cuenta."""
    _fallos.pop("em:" + email.lower(), None)


MENSAJE = "Demasiados intentos. Esperá unos 15 minutos y probá de nuevo."
