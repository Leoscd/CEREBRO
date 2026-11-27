import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import jwt
import pytest
from itsdangerous import TimestampSigner

from app import config
from app.services import onlyoffice
from tests.test_visor import crear_archivo as crear_archivo
from tests.test_subida import directorio_almacen as directorio_almacen


@pytest.fixture
def office(monkeypatch):
    monkeypatch.setattr(config, "ONLYOFFICE_URL", "https://docs.test")
    monkeypatch.setattr(config, "ONLYOFFICE_JWT_SECRET", "secreto-de-prueba-de-al-menos-32-bytes")
    monkeypatch.setattr(config, "APP_URL_INTERNA", "http://app:8000")


def leer_editor(html):
    coincidencia = re.search(r'<script type="application/json" id="config-onlyoffice">(.*?)</script>', html, re.S)
    assert coincidencia
    return json.loads(coincidencia[1])


@pytest.mark.parametrize(("ext", "tipo"), [("docx", "word"), ("xlsx", "cell"), ("pptx", "slide")])
def test_config_firmada(office, ext, tipo):
    user = {"id": 7, "nombre": "Ana", "empresa_id": 2, "rol_empresa": "cliente"}
    archivo = {"id": 4, "nombre": "Archivo." + ext, "extension": ext}
    version = {"id": 9, "sha256": "abcd" * 16}
    editor = onlyoffice.config_editor(user, archivo, version)
    firmado = jwt.decode(editor.pop("token"), config.ONLYOFFICE_JWT_SECRET, algorithms=["HS256"])
    assert firmado == editor
    assert editor["documentType"] == tipo
    assert editor["editorConfig"]["mode"] == "view"
    assert editor["editorConfig"]["user"] == {"id": "7", "name": "Ana"}
    doc = editor["document"]
    assert not doc["permissions"]["edit"] and doc["fileType"] == ext
    assert doc["key"] == "4-9-abcdabcdabcd"
    assert doc["url"].startswith("http://app:8000/onlyoffice/descarga/")


def test_descarga_version_firmada_y_aislada(office, crear_archivo, como, app_client, db, mundo, monkeypatch):
    cliente, ruta = crear_archivo("Informe.docx", b"version original", "application/octet-stream")
    pagina = cliente.get(ruta)
    assert "https://docs.test/web-apps/apps/api/documents/api.js" in pagina.text
    url = urlsplit(leer_editor(pagina.text)["document"]["url"]).path
    anonimo = app_client()
    respuesta = anonimo.get(url)
    assert respuesta.content == b"version original" and respuesta.status_code == 200
    assert respuesta.headers["content-disposition"].startswith("attachment")
    assert respuesta.headers["cache-control"] == "private, no-store"
    assert anonimo.get(url + "x").status_code == 404
    assert como("admin@b.test").get(ruta).status_code == 404
    a = db.execute("SELECT * FROM archivos").fetchone()
    ajeno = onlyoffice.token_descarga(mundo["admin_b"]["empresa_id"], a["id"], a["version_actual_id"])
    assert anonimo.get("/onlyoffice/descarga/" + ajeno).status_code == 404
    with monkeypatch.context() as m:
        ahora = TimestampSigner.get_timestamp
        m.setattr(TimestampSigner, "get_timestamp", lambda self: ahora(self) + 601)
        assert anonimo.get(url).status_code == 404
    db.execute("UPDATE archivos SET en_papelera_en=now() WHERE id=%s", (a["id"],))
    db.commit()
    assert anonimo.get(url).status_code == 404


def test_sin_onlyoffice_conserva_pdf(crear_archivo, db, monkeypatch):
    monkeypatch.setattr(config, "ONLYOFFICE_URL", "")
    cliente, ruta = crear_archivo("Informe.docx", b"doc", "application/octet-stream")
    db.execute("""UPDATE versiones_archivo SET derivados='{"pdf":{"sha256":"abc"}}'""")
    db.commit()
    html = cliente.get(ruta).text
    assert 'id="visor-pdf"' in html and "/vista.pdf" in html
    assert "documents/api.js" not in html


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose se verifica en CI")
def test_perfil_onlyoffice(tmp_path):
    raiz = Path(__file__).resolve().parents[1]
    shutil.copy(raiz / "docker-compose.yml", tmp_path)
    shutil.copy(raiz / ".env.example", tmp_path / ".env")
    def servicios(*opciones):
        proceso = subprocess.run(["docker", "compose", *opciones, "config", "--format", "json"],
                                 cwd=tmp_path, capture_output=True, text=True, check=True, timeout=30)
        return json.loads(proceso.stdout)["services"]
    assert "onlyoffice" not in servicios()
    docs = servicios("--profile", "onlyoffice")["onlyoffice"]
    assert docs["image"].startswith("onlyoffice/documentserver:") and not docs.get("ports")
    assert int(docs["mem_limit"]) == 6 * 1024**3
