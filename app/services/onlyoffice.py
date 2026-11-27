"""Configuración de Docs y enlaces temporales para el servidor de documentos."""
import jwt
from itsdangerous import URLSafeTimedSerializer

from app import config

TIPOS = {"docx": "word", "xlsx": "cell", "pptx": "slide"}


def token_descarga(empresa_id: int, archivo_id: int, version_id: int) -> str:
    firma = URLSafeTimedSerializer(config.SECRET_KEY, salt="onlyoffice-descarga")
    return firma.dumps([empresa_id, archivo_id, version_id])


def leer_token_descarga(token: str) -> list[int]:
    firma = URLSafeTimedSerializer(config.SECRET_KEY, salt="onlyoffice-descarga")
    return firma.loads(token, max_age=600)


def config_editor(user: dict, archivo: dict, version: dict) -> dict:
    extension = archivo["extension"]
    descarga = token_descarga(user["empresa_id"], archivo["id"], version["id"])
    editor = {
        "width": "100%", "height": "640px",
        "documentType": TIPOS[extension],
        "document": {
            "fileType": extension, "title": archivo["nombre"],
            "key": f"{archivo['id']}-{version['id']}-{version['sha256'][:12]}",
            "url": f"{config.APP_URL_INTERNA}/onlyoffice/descarga/{descarga}",
            "permissions": {"edit": False, "comment": False, "review": False, "fillForms": False},
        },
        "editorConfig": {"mode": "view", "lang": "es", "user": {"id": str(user["id"]), "name": user["nombre"]}},
    }
    editor["token"] = jwt.encode(editor, config.ONLYOFFICE_JWT_SECRET, algorithm="HS256")
    return editor
