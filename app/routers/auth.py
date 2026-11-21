"""Ingreso, segundo factor, registro por invitación, recuperar contraseña y mi cuenta.

Portado del curso (app/routers/auth.py) a Postgres, con sesión versionada y TOTP.
"""
import hashlib
import io
import re
import secrets

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from psycopg import Connection

from app import config
from app.db import db_dependency
from app.security import (
    check_csrf,
    crear_token_pre2fa,
    hash_password,
    leer_token_pre2fa,
    nuevo_secreto_totp,
    poner_cookie_sesion,
    require_user,
    uri_totp,
    verificar_totp,
    verify_password,
    es_https,
)
from app.services import auditoria, correo, limitador
from app.templates import templates

router = APIRouter()

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
RESET_MINUTOS = 60
MENSAJE_RESET = (
    "Si ese email tiene una cuenta, te mandamos un link para elegir una contraseña nueva. "
    "Revisá también la carpeta de spam."
)
LINK_VENCIDO = "Este link ya se usó o venció. Pedí uno nuevo desde «Olvidé mi contraseña»."


def sha256(valor: str) -> str:
    return hashlib.sha256((valor or "").encode()).hexdigest()


def _entrar(request: Request, db: Connection, usuario: dict) -> RedirectResponse:
    db.execute("UPDATE usuarios SET ultimo_ingreso = now() WHERE id = %s", (usuario["id"],))
    auditoria.registrar(db, usuario, "ingreso", objeto="usuario", objeto_id=usuario["id"], request=request)
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    poner_cookie_sesion(resp, request, usuario)
    resp.delete_cookie(config.PRE2FA_COOKIE)
    return resp


# ---------- ingreso ----------

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "user": None})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Connection = Depends(db_dependency),
):
    email = email.strip().lower()

    def error(msg: str, code: int):
        return templates.TemplateResponse(request, "login.html", {"error": msg, "user": None}, status_code=code)

    if limitador.bloqueado(request, email):
        return error(limitador.MENSAJE, 429)
    u = db.execute("SELECT * FROM usuarios WHERE email = %s", (email,)).fetchone()
    if not u or not verify_password(password, u["password_hash"]):
        limitador.registrar_fallo(request, email)
        return error("Email o contraseña incorrectos", 401)
    if not u["activo"]:
        return error("Tu acceso está desactivado. Si creés que es un error, hablá con el administrador.", 403)
    limitador.limpiar_email(email)
    if u["totp_secret"]:
        resp = RedirectResponse("/login/2fa", status_code=303)
        resp.set_cookie(
            config.PRE2FA_COOKIE, crear_token_pre2fa(u["id"]), max_age=config.PRE2FA_MAX_AGE,
            httponly=True, samesite="lax", secure=es_https(request),
        )
        return resp
    return _entrar(request, db, u)


@router.get("/login/2fa")
def login_2fa_page(request: Request):
    if leer_token_pre2fa(request.cookies.get(config.PRE2FA_COOKIE)) is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "login_2fa.html", {"error": None, "user": None})


@router.post("/login/2fa")
def login_2fa(request: Request, codigo: str = Form(""), db: Connection = Depends(db_dependency)):
    uid = leer_token_pre2fa(request.cookies.get(config.PRE2FA_COOKIE))
    if uid is None:
        return RedirectResponse("/login", status_code=303)
    clave = f"2fa:{uid}"
    if limitador.bloqueado(request, clave):
        return templates.TemplateResponse(
            request, "login_2fa.html", {"error": limitador.MENSAJE, "user": None}, status_code=429
        )
    u = db.execute("SELECT * FROM usuarios WHERE id = %s AND activo", (uid,)).fetchone()
    if not u or not verificar_totp(u["totp_secret"], codigo):
        limitador.registrar_fallo(request, clave)
        return templates.TemplateResponse(
            request, "login_2fa.html", {"error": "Código incorrecto o vencido", "user": None}, status_code=401
        )
    limitador.limpiar_email(clave)
    return _entrar(request, db, u)


@router.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(config.SESSION_COOKIE)
    return resp


# ---------- registro por invitación ----------

def invitacion_valida(db: Connection, codigo: str) -> dict | None:
    return db.execute(
        """SELECT i.*, e.nombre AS empresa_nombre FROM invitaciones i JOIN empresas e ON e.id = i.empresa_id
            WHERE i.code_hash = %s AND i.usada_por IS NULL AND i.cancelada_en IS NULL AND i.expira_at > now()""",
        (sha256(codigo.strip()),),
    ).fetchone()


@router.get("/registro")
def register_page(request: Request, invitacion: str = "", db: Connection = Depends(db_dependency)):
    ctx = {"error": None, "invitacion": "", "email": "", "empresa": "", "user": None}
    inv = invitacion_valida(db, invitacion) if invitacion else None
    if not inv:
        ctx["error"] = "Este link de invitación ya se usó, venció o no es válido. Pedí que te lo reenvíen."
    else:
        ctx.update(invitacion=invitacion, email=inv["email"], empresa=inv["empresa_nombre"])
    return templates.TemplateResponse(request, "register.html", ctx, status_code=200 if inv else 400)


@router.post("/registro")
def register(
    request: Request,
    invitacion: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(...),
    repetir: str = Form(...),
    db: Connection = Depends(db_dependency),
):
    inv = None

    def err(msg: str, code: int = 400):
        ctx = {"error": msg, "invitacion": invitacion if inv else "", "user": None,
               "email": inv["email"] if inv else "", "empresa": inv["empresa_nombre"] if inv else ""}
        return templates.TemplateResponse(request, "register.html", ctx, status_code=code)

    if limitador.bloqueado(request):
        return err(limitador.MENSAJE, 429)
    inv = invitacion_valida(db, invitacion)
    if not inv:
        limitador.registrar_fallo(request)
        return err("Invitación inválida, vencida o ya usada")
    # El email sale de la invitación personal, no del formulario.
    email = inv["email"].strip().lower()
    if not EMAIL_RE.match(email):
        return err("La invitación tiene un email inválido. Pedí una nueva.")
    if len(password) < 10:
        return err("La contraseña debe tener al menos 10 caracteres")
    if password != repetir:
        return err("Las dos contraseñas no coinciden")
    if not nombre.strip():
        return err("Escribí tu nombre")
    if db.execute("SELECT 1 FROM usuarios WHERE email = %s", (email,)).fetchone():
        return err("Ya existe una cuenta con ese email. Entrá desde Ingresar.")

    u = db.execute(
        """INSERT INTO usuarios (empresa_id, email, password_hash, nombre, rol_empresa, cliente_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (inv["empresa_id"], email, hash_password(password), nombre.strip()[:120], inv["rol_empresa"], inv["cliente_id"]),
    ).fetchone()
    db.execute("UPDATE invitaciones SET usada_por = %s, usada_en = now() WHERE id = %s", (u["id"], inv["id"]))
    if inv["proyecto_id"] and inv["rol_proyecto"]:
        db.execute(
            """INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol) VALUES (%s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (inv["proyecto_id"], u["id"], inv["rol_proyecto"]),
        )
    auditoria.registrar(db, u, "registro", objeto="usuario", objeto_id=u["id"],
                        detalle={"invitacion": inv["id"]}, request=request)
    return _entrar(request, db, u)


# ---------- olvidé mi contraseña ----------

@router.get("/olvide")
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "olvide.html", {"error": None, "ok": None, "user": None})


@router.post("/olvide")
def forgot(request: Request, email: str = Form(""), db: Connection = Depends(db_dependency)):
    email = email.strip().lower()
    if limitador.bloqueado(request, email):
        return templates.TemplateResponse(
            request, "olvide.html", {"error": limitador.MENSAJE, "ok": None, "user": None}, status_code=429
        )
    limitador.registrar_fallo(request, email)  # cada pedido cuenta: frena el spam
    u = db.execute("SELECT id, activo FROM usuarios WHERE email = %s", (email,)).fetchone()
    if u and u["activo"]:
        token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO password_resets (token_hash, usuario_id, expira_at) VALUES (%s, %s, now() + %s * interval '1 minute')",
            (sha256(token), u["id"], RESET_MINUTOS),
        )
        db.commit()
        correo.recuperar(email, f"{config.URL_PUBLICA}/restablecer?token={token}")
    # Misma respuesta exista o no la cuenta.
    return templates.TemplateResponse(request, "olvide.html", {"error": None, "ok": MENSAJE_RESET, "user": None})


def _reset_valido(db: Connection, token: str) -> dict | None:
    return db.execute(
        "SELECT * FROM password_resets WHERE token_hash = %s AND usado_at IS NULL AND expira_at > now()",
        (sha256(token),),
    ).fetchone()


@router.get("/restablecer")
def reset_page(request: Request, token: str = "", db: Connection = Depends(db_dependency)):
    if not _reset_valido(db, token):
        return templates.TemplateResponse(
            request, "restablecer.html", {"token": "", "error": LINK_VENCIDO, "user": None}, status_code=400
        )
    return templates.TemplateResponse(request, "restablecer.html", {"token": token, "error": None, "user": None})


@router.post("/restablecer")
def reset(
    request: Request,
    token: str = Form(""),
    nueva: str = Form(""),
    repetir: str = Form(""),
    db: Connection = Depends(db_dependency),
):
    fila = _reset_valido(db, token)
    if not fila:
        return templates.TemplateResponse(
            request, "restablecer.html", {"token": "", "error": LINK_VENCIDO, "user": None}, status_code=400
        )
    if len(nueva) < 10 or nueva != repetir:
        return templates.TemplateResponse(
            request, "restablecer.html",
            {"token": token, "user": None,
             "error": "La contraseña tiene que tener al menos 10 caracteres y coincidir en los dos campos."},
            status_code=400,
        )
    db.execute(
        "UPDATE usuarios SET password_hash = %s, sesion_version = sesion_version + 1 WHERE id = %s",
        (hash_password(nueva), fila["usuario_id"]),
    )
    db.execute(
        "UPDATE password_resets SET usado_at = now() WHERE usuario_id = %s AND usado_at IS NULL",
        (fila["usuario_id"],),
    )
    u = db.execute("SELECT * FROM usuarios WHERE id = %s", (fila["usuario_id"],)).fetchone()
    auditoria.registrar(db, u, "password_restablecida", objeto="usuario", objeto_id=u["id"], request=request)
    db.commit()
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "aviso": "Listo, ya podés entrar con tu contraseña nueva.", "user": None}
    )


# ---------- mi cuenta ----------

@router.get("/mi-cuenta")
def account_page(request: Request, user=Depends(require_user)):
    return templates.TemplateResponse(request, "account.html", {"user": user, "error": None, "ok": None})


@router.post("/mi-cuenta/password")
def change_password(
    request: Request,
    actual: str = Form(...),
    nueva: str = Form(...),
    repetir: str = Form(...),
    user=Depends(check_csrf),
    db: Connection = Depends(db_dependency),
):
    def responder(error=None, ok=None):
        return templates.TemplateResponse(
            request, "account.html", {"user": user, "error": error, "ok": ok}, status_code=400 if error else 200
        )

    if not verify_password(actual, user["password_hash"]):
        return responder("La contraseña actual no es correcta")
    if len(nueva) < 10:
        return responder("La nueva contraseña debe tener al menos 10 caracteres")
    if nueva != repetir:
        return responder("Las dos contraseñas nuevas no coinciden")
    u = db.execute(
        """UPDATE usuarios SET password_hash = %s, sesion_version = sesion_version + 1
            WHERE id = %s RETURNING *""",
        (hash_password(nueva), user["id"]),
    ).fetchone()
    auditoria.registrar(db, user, "password_cambiada", objeto="usuario", objeto_id=user["id"], request=request)
    db.commit()
    # Esta sesión sigue; las de otros equipos quedan cerradas.
    resp = responder(ok="Contraseña actualizada. Se cerró la sesión en los demás equipos.")
    poner_cookie_sesion(resp, request, u)
    return resp


def _qr_svg(texto: str) -> str:
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


@router.get("/mi-cuenta/2fa")
def twofa_page(request: Request, user=Depends(require_user)):
    ctx = {"user": user, "error": None, "secreto": None, "qr": None}
    if not user["totp_secret"]:
        secreto = nuevo_secreto_totp()
        ctx.update(secreto=secreto, qr=_qr_svg(uri_totp(secreto, user["email"])))
    return templates.TemplateResponse(request, "account_2fa.html", ctx)


@router.post("/mi-cuenta/2fa/activar")
def twofa_activar(
    request: Request,
    secreto: str = Form(...),
    codigo: str = Form(...),
    user=Depends(check_csrf),
    db: Connection = Depends(db_dependency),
):
    if user["totp_secret"]:
        return RedirectResponse("/mi-cuenta/2fa", status_code=303)
    if not verificar_totp(secreto, codigo):
        ctx = {"user": user, "error": "El código no coincide. Probá con el siguiente que muestre la app.",
               "secreto": secreto, "qr": _qr_svg(uri_totp(secreto, user["email"]))}
        return templates.TemplateResponse(request, "account_2fa.html", ctx, status_code=400)
    db.execute("UPDATE usuarios SET totp_secret = %s WHERE id = %s", (secreto, user["id"]))
    auditoria.registrar(db, user, "2fa_activado", objeto="usuario", objeto_id=user["id"], request=request)
    db.commit()
    return RedirectResponse("/mi-cuenta?ok=2fa", status_code=303)
