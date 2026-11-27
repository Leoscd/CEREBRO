"""Configuración de Docs y enlaces temporales para el servidor de documentos."""
import hashlib
import json
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

import jwt
from itsdangerous import URLSafeTimedSerializer

from app import config
from app.permisos import puede_escribir_en_proyecto
from app.services import almacen

TIPOS = {"docx": "word", "xlsx": "cell", "pptx": "slide"}


def token_descarga(empresa_id: int, archivo_id: int, version_id: int) -> str:
    firma = URLSafeTimedSerializer(config.SECRET_KEY, salt="onlyoffice-descarga")
    return firma.dumps([empresa_id, archivo_id, version_id])


def leer_token_descarga(token: str) -> list[int]:
    firma = URLSafeTimedSerializer(config.SECRET_KEY, salt="onlyoffice-descarga")
    return firma.loads(token, max_age=600)


def token_callback(empresa_id: int, archivo_id: int, version_id: int, usuario_id: int) -> str:
    firma = URLSafeTimedSerializer(config.SECRET_KEY, salt="onlyoffice-callback")
    return firma.dumps([empresa_id, archivo_id, version_id, usuario_id])


def leer_token_callback(token: str) -> list[int]:
    firma = URLSafeTimedSerializer(config.SECRET_KEY, salt="onlyoffice-callback")
    return firma.loads(token, max_age=7 * 24 * 3600)


def clave_documento(archivo_id: int, version: dict) -> str:
    return f"{archivo_id}-{version['id']}-{version['sha256'][:12]}"


def evento_firmado(autorizacion: str, cuerpo: dict) -> dict:
    esquema, _, bearer = autorizacion.partition(" ")
    token = bearer if esquema.lower() == "bearer" else cuerpo.get("token")
    if not config.ONLYOFFICE_URL or not config.ONLYOFFICE_JWT_SECRET or not isinstance(token, str):
        raise ValueError("Falta la firma de ONLYOFFICE")
    datos = jwt.decode(token, config.ONLYOFFICE_JWT_SECRET, algorithms=["HS256"])
    evento = datos.get("payload", datos)
    if not isinstance(evento, dict) or type(evento.get("status")) is not int:
        raise ValueError("Evento inválido")
    return evento


def url_guardado_valida(url: str) -> bool:
    if not isinstance(url, str) or not url.isascii() or any(c.isspace() for c in url) or "\\" in url:
        return False
    destino = urlsplit(url)
    origen = urlsplit(config.ONLYOFFICE_URL_INTERNA)
    return (destino.scheme in {"http", "https"} and destino.scheme == origen.scheme
            and bool(destino.hostname) and destino.netloc.lower() == origen.netloc.lower()
            and destino.username is None and not destino.fragment)


def huella_guardado(evento: dict) -> str:
    # Identifica el reintento sin persistir la URL temporal del servidor.
    datos = [evento["status"], evento["url"], evento.get("lastsave")]
    return hashlib.sha256(json.dumps(datos).encode()).hexdigest()


class _SinRedirecciones(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def descargar_version(url: str) -> tuple[str, int]:
    cliente = build_opener(ProxyHandler({}), _SinRedirecciones())
    with cliente.open(url, timeout=30) as respuesta:
        if respuesta.status != 200:
            raise ValueError("Respuesta de guardado incompleta")
        longitud = respuesta.headers.get("Content-Length")
        sha, tamano = almacen.guardar(respuesta)
        if longitud is not None and int(longitud) != tamano:
            raise ValueError("Descarga incompleta")
        return sha, tamano


def config_editor(user: dict, archivo: dict, version: dict) -> dict:
    extension = archivo["extension"]
    descarga = token_descarga(user["empresa_id"], archivo["id"], version["id"])
    editable = puede_escribir_en_proyecto(user, archivo)
    editor = {
        "width": "100%", "height": "640px",
        "documentType": TIPOS[extension],
        "document": {
            "fileType": extension, "title": archivo["nombre"],
            "key": clave_documento(archivo["id"], version),
            "url": f"{config.APP_URL_INTERNA}/onlyoffice/descarga/{descarga}",
            "permissions": {"edit": editable, "comment": False, "review": False, "fillForms": False},
        },
        "editorConfig": {"mode": "edit" if editable else "view", "lang": "es",
                         "user": {"id": str(user["id"]), "name": user["nombre"]}},
    }
    if editable:
        callback = token_callback(user["empresa_id"], archivo["id"], version["id"], user["id"])
        editor["editorConfig"]["callbackUrl"] = f"{config.APP_URL_INTERNA}/onlyoffice/callback/{callback}"
    editor["token"] = jwt.encode(editor, config.ONLYOFFICE_JWT_SECRET, algorithm="HS256")
    return editor
