"""Envío de emails (invitaciones, recuperar contraseña) por SMTP.

Sin SMTP configurado no falla: guarda el email en data/correos/ y devuelve False, para que
quien llama le muestre el link al admin. Nunca registra la contraseña SMTP.
"""
import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid

from app import config

logger = logging.getLogger("correo")


def configurado() -> bool:
    return bool(config.SMTP_HOST)


def enviar(destino: str, asunto: str, texto: str, html: str) -> bool:
    """Devuelve True si el servidor de correo lo aceptó."""
    msg = EmailMessage()
    msg["From"] = config.MAIL_FROM
    msg["To"] = destino
    msg["Subject"] = asunto
    msg["Message-ID"] = make_msgid(domain=config.MAIL_FROM.rsplit("@", 1)[-1].strip(">"))
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    if not configurado():
        carpeta = config.DATA_DIR / "correos"
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".eml"
        (carpeta / nombre).write_bytes(bytes(msg))
        logger.warning("SMTP sin configurar: email a %s guardado en %s", destino, nombre)
        return False

    try:
        contexto = ssl.create_default_context()
        if config.SMTP_PORT == 465:
            servidor = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=contexto, timeout=20)
        else:
            servidor = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
            servidor.starttls(context=contexto)
        with servidor:
            if config.SMTP_USER:
                servidor.login(config.SMTP_USER, config.SMTP_PASSWORD)
            servidor.send_message(msg)
        return True
    except Exception:
        logger.exception("No se pudo enviar el email a %s", destino)
        return False


def _plantilla(titulo: str, cuerpo_html: str, boton: str, link: str, pie: str) -> str:
    """HTML simple y compatible con clientes de correo (tablas y estilos en línea)."""
    from html import escape

    return f"""<!doctype html><html><body style="margin:0;background:#0b0b0b;font-family:Arial,Helvetica,sans-serif;color:#e8eaf0">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" style="max-width:520px;background:#141414;border:1px solid #2c2c2c;border-radius:12px">
<tr><td style="padding:28px 28px 8px;font-size:20px;font-weight:bold">{escape(config.MARCA)}</td></tr>
<tr><td style="padding:8px 28px 0;font-size:22px;font-weight:bold;color:#ffffff">{escape(titulo)}</td></tr>
<tr><td style="padding:12px 28px;font-size:15px;line-height:1.6;color:#c9ccd6">{cuerpo_html}</td></tr>
<tr><td style="padding:8px 28px 20px"><a href="{escape(link)}" style="display:inline-block;background:#c4981f;color:#14120a;text-decoration:none;font-weight:bold;padding:12px 22px;border-radius:8px">{escape(boton)}</a></td></tr>
<tr><td style="padding:0 28px 24px;font-size:12px;line-height:1.5;color:#8a8f9e">Si el botón no funciona, copiá este link en el navegador:<br><span style="color:#c4981f;word-break:break-all">{escape(link)}</span><br><br>{escape(pie)}</td></tr>
</table></td></tr></table></body></html>"""


def invitacion(destino: str, link: str, empresa: str, invita: str) -> bool:
    from html import escape

    asunto = f"Te invitaron a {empresa} en {config.MARCA}"
    texto = (
        f"Hola,\n\n{invita} te invitó a trabajar en los proyectos de {empresa} en {config.MARCA}.\n\n"
        f"Creá tu cuenta con este link (es personal y vence en {config.INVITACION_DIAS} días):\n{link}\n\n"
        "La cuenta queda asociada a este email.\n"
    )
    html = _plantilla(
        "Te invitaron al gestor de proyectos",
        f"{escape(invita)} te invitó a trabajar en los proyectos de <strong>{escape(empresa)}</strong>. "
        "Creá tu cuenta con tu nombre y una contraseña: el email ya queda asociado al tuyo.",
        "Crear mi cuenta",
        link,
        f"El link es personal y vence en {config.INVITACION_DIAS} días. Si no esperabas este email, ignoralo.",
    )
    return enviar(destino, asunto, texto, html)


def recuperar(destino: str, link: str) -> bool:
    asunto = f"Cambiá tu contraseña de {config.MARCA}"
    texto = (
        f"Hola,\n\nPara elegir una contraseña nueva entrá a este link (vence en 1 hora):\n{link}\n\n"
        "Si no lo pediste, ignorá este email: tu contraseña sigue igual.\n"
    )
    html = _plantilla(
        "Cambiá tu contraseña",
        "Recibimos un pedido para cambiar la contraseña de tu cuenta.",
        "Elegir contraseña nueva",
        link,
        "El link vence en 1 hora y sirve una sola vez. Si no lo pediste, ignorá este email.",
    )
    return enviar(destino, asunto, texto, html)
