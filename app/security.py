"""Sesiones, contraseñas, CSRF y segundo factor.

La sesión es una cookie firmada (itsdangerous) con el id del usuario y su
`sesion_version`: cambiar la contraseña sube la versión e invalida las demás sesiones.
El usuario que devuelve `require_user` trae siempre su `empresa_id`: todas las consultas
de negocio filtran por ese valor, nunca por algo que llegue en el pedido.
"""
import hmac

import bcrypt
import pyotp
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from psycopg import Connection

from app import config
from app.db import db_dependency

_sesiones = URLSafeTimedSerializer(config.SECRET_KEY, salt="sesion")
_pre2fa = URLSafeTimedSerializer(config.SECRET_KEY, salt="pre2fa")
_csrf = URLSafeTimedSerializer(config.SECRET_KEY, salt="csrf")


# ---------- contraseñas ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ---------- sesión ----------

def crear_token_sesion(usuario: dict) -> str:
    return _sesiones.dumps({"uid": usuario["id"], "v": usuario["sesion_version"]})


def leer_token_sesion(token: str) -> tuple[int, int] | None:
    try:
        data = _sesiones.loads(token, max_age=config.SESSION_MAX_AGE)
        return int(data["uid"]), int(data["v"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


def es_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def poner_cookie_sesion(resp, request: Request, usuario: dict) -> None:
    resp.set_cookie(
        config.SESSION_COOKIE,
        crear_token_sesion(usuario),
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=es_https(request),
    )


def get_optional_user(request: Request, db: Connection = Depends(db_dependency)) -> dict | None:
    token = request.cookies.get(config.SESSION_COOKIE)
    datos = leer_token_sesion(token) if token else None
    if datos is None:
        return None
    uid, version = datos
    fila = db.execute(
        """SELECT u.*, e.nombre AS empresa_nombre
             FROM usuarios u JOIN empresas e ON e.id = u.empresa_id
            WHERE u.id = %s""",
        (uid,),
    ).fetchone()
    if fila is None or not fila["activo"] or fila["sesion_version"] != version:
        return None
    return fila


def require_user(request: Request, user=Depends(get_optional_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    # Admin sin segundo factor cuando es obligatorio: solo puede ir a activarlo o salir.
    if (
        config.ADMIN_REQUIERE_2FA
        and user["rol_empresa"] == "admin"
        and not user["totp_secret"]
        and not request.url.path.startswith(("/mi-cuenta", "/logout"))
    ):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/mi-cuenta/2fa"})
    return user


def require_personal(user=Depends(require_user)) -> dict:
    """Personal de la empresa (admin o miembro). Los clientes no entran acá."""
    if user["rol_empresa"] == "cliente":
        raise HTTPException(status_code=403, detail="Sección solo para el equipo")
    return user


def require_admin(user=Depends(require_user)) -> dict:
    if user["rol_empresa"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    return user


# ---------- CSRF ----------
# Todo formulario que escribe manda el campo `csrf`; los fetch, el header X-CSRF.

def csrf_token(usuario_id: int) -> str:
    return _csrf.dumps({"uid": usuario_id})


def _csrf_valido(usuario_id: int, token: str | None) -> bool:
    try:
        return int(_csrf.loads(token or "", max_age=config.SESSION_MAX_AGE)["uid"]) == usuario_id
    except (BadSignature, KeyError, ValueError, TypeError):
        return False


async def check_csrf(request: Request, user=Depends(require_user)) -> dict:
    token = request.headers.get("x-csrf")
    if not token:
        form = await request.form()
        token = form.get("csrf")
    if not _csrf_valido(user["id"], token):
        raise HTTPException(status_code=403, detail="El formulario venció. Recargá la página e intentá de nuevo.")
    return user


# ---------- segundo factor (TOTP) ----------

def nuevo_secreto_totp() -> str:
    return pyotp.random_base32()


def verificar_totp(secreto: str, codigo: str) -> bool:
    codigo = (codigo or "").replace(" ", "").strip()
    if not secreto or not codigo.isdigit():
        return False
    return pyotp.TOTP(secreto).verify(codigo, valid_window=1)


def uri_totp(secreto: str, email: str) -> str:
    return pyotp.TOTP(secreto).provisioning_uri(name=email, issuer_name=config.MARCA)


def crear_token_pre2fa(usuario_id: int) -> str:
    return _pre2fa.dumps({"uid": usuario_id})


def leer_token_pre2fa(token: str | None) -> int | None:
    try:
        return int(_pre2fa.loads(token or "", max_age=config.PRE2FA_MAX_AGE)["uid"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


def iguales(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
