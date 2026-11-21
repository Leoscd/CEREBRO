"""Ingreso, invitaciones, sesiones versionadas, recuperar contraseña y segundo factor."""
import re
from pathlib import Path

import pyotp
import pytest

from app import config
from tests.conftest import CLAVE, csrf_de, entrar


def test_login_incorrecto(app_client, mundo):
    r = app_client().post("/login", data={"email": "ana@a.test", "password": "mala-clave-xx"})
    assert r.status_code == 401


@pytest.mark.parametrize("pagina", ["/", "/mi-cuenta"])
def test_salir_con_formulario_cierra_sesion(mundo, como, pagina):
    cliente = como("ana@a.test")
    respuesta = cliente.get(pagina)
    assert respuesta.status_code == 200
    formulario = re.search(r'<form\b[^>]*action="/logout"[^>]*>(.*?)</form>', respuesta.text, re.S)
    assert formulario
    assert 'method="post"' in formulario[0].split(">", 1)[0]
    campo = re.search(r'<input\b[^>]*name="csrf"[^>]*value="([^"]+)"', formulario[1])
    assert campo

    salida = cliente.post("/logout", data={"csrf": campo[1]})
    assert salida.status_code == 303
    assert salida.headers["location"] == "/login"
    assert config.SESSION_COOKIE not in cliente.cookies
    assert cliente.get("/").status_code == 303


@pytest.mark.parametrize("datos", [{}, {"csrf": "invalido"}], ids=["sin-token", "token-invalido"])
def test_logout_rechazado_conserva_sesion(mundo, como, datos):
    cliente = como("ana@a.test")
    assert cliente.post("/logout", data=datos).status_code == 403
    assert cliente.get("/").status_code == 200


def test_invitacion_crea_cuenta_y_suma_al_proyecto(mundo, como, app_client, db):
    admin = como("admin@a.test")
    r = admin.post("/admin/usuarios/invitar", data={
        "csrf": csrf_de(mundo["admin_a"]), "email": "nueva@a.test", "rol_empresa": "miembro",
        "proyecto_id": mundo["p2"]["id"], "rol_proyecto": "lector",
    })
    assert r.status_code == 200  # sin SMTP: muestra el link una vez
    link = re.search(r'value="(http[^"]+registro\?invitacion=[^"]+)"', r.text).group(1)
    codigo = link.split("invitacion=")[1]
    # En la base no queda el código en claro.
    assert not db.execute("SELECT 1 FROM invitaciones WHERE code_hash = %s", (codigo,)).fetchone()

    nuevo = app_client()
    assert nuevo.get(f"/registro?invitacion={codigo}").status_code == 200
    r = nuevo.post("/registro", data={"invitacion": codigo, "nombre": "Nueva", "password": CLAVE, "repetir": CLAVE})
    assert r.status_code == 303
    assert nuevo.get(f"/proyecto/{mundo['p2']['codigo']}").status_code == 200
    assert nuevo.get(f"/proyecto/{mundo['p1']['codigo']}").status_code == 404
    # La invitación no se puede reusar.
    r = app_client().post("/registro", data={"invitacion": codigo, "nombre": "X", "password": CLAVE, "repetir": CLAVE})
    assert r.status_code == 400


def test_cambiar_password_cierra_las_otras_sesiones(mundo, como):
    equipo1 = como("ana@a.test")
    equipo2 = como("ana@a.test")
    nueva = "otra-clave-segura-456"
    r = equipo1.post("/mi-cuenta/password", data={"csrf": csrf_de(mundo["ana"]), "actual": CLAVE,
                                                  "nueva": nueva, "repetir": nueva})
    assert r.status_code == 200
    assert equipo1.get("/").status_code == 200       # la sesión que cambió sigue
    assert equipo2.get("/").status_code == 303       # la otra quedó afuera


def test_recuperar_password(mundo, app_client, tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = app_client()
    assert c.post("/olvide", data={"email": "ana@a.test"}).status_code == 200
    import email
    from email import policy

    crudo = next(Path(tmp_path, "correos").glob("*.eml")).read_bytes()
    texto = email.message_from_bytes(crudo, policy=policy.default).get_body(("plain",)).get_content()
    token = re.search(r"restablecer\?token=([A-Za-z0-9_\-]+)", texto).group(1)
    nueva = "recuperada-clave-789"
    r = c.post("/restablecer", data={"token": token, "nueva": nueva, "repetir": nueva})
    assert r.status_code == 200
    entrar(app_client(), "ana@a.test", nueva)
    # El link sirve una sola vez.
    assert c.post("/restablecer", data={"token": token, "nueva": nueva, "repetir": nueva}).status_code == 400


def test_segundo_factor(mundo, app_client, db):
    secreto = pyotp.random_base32()
    db.execute("UPDATE usuarios SET totp_secret = %s WHERE id = %s", (secreto, mundo["admin_a"]["id"]))
    db.commit()
    c = app_client()
    r = c.post("/login", data={"email": "admin@a.test", "password": CLAVE})
    assert r.headers["location"] == "/login/2fa"
    assert c.get("/").status_code == 303  # todavía sin sesión
    assert c.post("/login/2fa", data={"codigo": "000000"}).status_code == 401
    r = c.post("/login/2fa", data={"codigo": pyotp.TOTP(secreto).now()})
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert c.get("/").status_code == 200


def test_admin_obligado_a_activar_2fa(mundo, como, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ADMIN_REQUIERE_2FA", True)
    c = como("admin@a.test")
    r = c.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/mi-cuenta/2fa"
    assert c.get("/mi-cuenta/2fa").status_code == 200
