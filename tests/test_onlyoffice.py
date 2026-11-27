import io
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
from app.services import almacen, onlyoffice
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


@pytest.fixture
def sesion_editor(office, crear_archivo, app_client, monkeypatch):
    monkeypatch.setattr(config, "ONLYOFFICE_URL_INTERNA", "http://onlyoffice")
    usuario, ruta = crear_archivo("Informe.docx", b"original", "application/octet-stream")
    editor = leer_editor(usuario.get(ruta).text)
    assert editor["editorConfig"]["mode"] == "edit"
    assert editor["document"]["permissions"]["edit"] is True
    return app_client(), urlsplit(editor["editorConfig"]["callbackUrl"]).path, editor["document"]["key"]


def evento(clave, status=2, url="http://onlyoffice/cache/documento.docx"):
    return {"key": clave, "status": status, "url": url}


def firmado(datos):
    return jwt.encode(datos, config.ONLYOFFICE_JWT_SECRET, algorithm="HS256")


def test_guardado_version_auditoria_jobs_y_reintento(sesion_editor, monkeypatch, db, mundo):
    cliente, ruta, clave = sesion_editor
    respuestas = [b"editado", b"editado", b"final", b"editado"]
    monkeypatch.setattr(onlyoffice, "descargar_version", lambda url: almacen.guardar(io.BytesIO(respuestas.pop(0))))
    datos = evento(clave, status=6)
    for _ in range(2):
        # El campo url del cuerpo nunca sustituye al del JWT de la cabecera.
        r = cliente.post(ruta, json={"url": "https://invalido.test", "status": 4},
                         headers={"Authorization": "Bearer " + firmado({"payload": datos})})
        assert r.json() == {"error": 0}
    assert cliente.post(ruta, json={"token": firmado(evento(clave))}).json() == {"error": 0}
    assert cliente.post(ruta, json={"token": firmado(datos)}).json() == {"error": 0}
    versiones = db.execute("SELECT * FROM versiones_archivo ORDER BY numero").fetchall()
    assert [v["numero"] for v in versiones] == [1, 2, 3]
    assert [almacen.ruta(v["sha256"]).read_bytes() for v in versiones] == [b"original", b"editado", b"final"]
    for v in versiones[1:]:
        assert v["origen"] == "subida" and v["subida_por"] == mundo["ana"]["id"]
        jobs = db.execute("SELECT tipo FROM jobs WHERE payload->>'version_id'=%s", (str(v["id"]),))
        assert {j["tipo"] for j in jobs} == {"archivo.analizar", "archivo.vista_pdf"}
    auditoria = db.execute("SELECT usuario_id FROM auditoria WHERE accion='archivo.version_onlyoffice'").fetchall()
    assert len(auditoria) == 2 and all(f["usuario_id"] == mundo["ana"]["id"] for f in auditoria)


def test_callback_invalido_no_escribe(sesion_editor, db, mundo, monkeypatch):
    cliente, ruta, clave = sesion_editor
    monkeypatch.setattr(onlyoffice, "descargar_version", lambda url: pytest.fail("Descarga no autorizada"))
    datos = evento(clave)
    a = db.execute("SELECT * FROM archivos").fetchone()
    ajeno = onlyoffice.token_callback(mundo["eb"]["id"], a["id"], a["version_actual_id"], mundo["admin_b"]["id"])
    for destino, jwt_servidor in [
        (ruta, "invalido"), (ruta + "x", firmado(datos)), ("/onlyoffice/callback/" + ajeno, firmado(datos)),
        (ruta, firmado(evento("otra-clave"))),
        (ruta, firmado(evento(clave, url="https://otro.test/cache"))),
        (ruta, firmado(evento(clave, url="https://onlyoffice/cache"))),
        (ruta, firmado(evento(clave, url="http://onlyoffice:8888/cache"))),
    ]:
        assert cliente.post(destino, json={"token": jwt_servidor}).json() == {"error": 1}
    assert cliente.post(ruta, json={"token": firmado(evento(clave, status=1))}).json() == {"error": 0}
    with monkeypatch.context() as m:
        ahora = TimestampSigner.get_timestamp
        m.setattr(TimestampSigner, "get_timestamp", lambda self: ahora(self) + 7 * 86400 + 1)
        assert cliente.post(ruta, json={"token": firmado(datos)}).json() == {"error": 1}
    db.execute("UPDATE proyecto_miembros SET rol='lector' WHERE proyecto_id=%s AND usuario_id=%s",
               (a["proyecto_id"], mundo["ana"]["id"]))
    db.commit()
    assert cliente.post(ruta, json={"token": firmado(datos)}).json() == {"error": 1}
    assert db.execute("SELECT count(*) AS n FROM versiones_archivo").fetchone()["n"] == 1


def test_cliente_con_acceso_solo_lee(office, crear_archivo, db, como):
    _, ruta = crear_archivo("Compartido.xlsx", b"original", "application/octet-stream")
    db.execute("UPDATE archivos SET visible_cliente=true")
    db.commit()
    editor = leer_editor(como("cliente@a.test").get(ruta).text)
    assert editor["editorConfig"]["mode"] == "view" and not editor["document"]["permissions"]["edit"]
    assert "callbackUrl" not in editor["editorConfig"]


def test_descarta_edicion_si_hubo_subida_manual(sesion_editor, como, db, mundo, monkeypatch):
    from tests.conftest import csrf_de

    cliente, ruta, clave = sesion_editor
    archivo = db.execute("SELECT id FROM archivos").fetchone()
    r = como("ana@a.test").post(f"/archivos/{archivo['id']}/versiones", data={"csrf": csrf_de(mundo["ana"])},
                                files={"archivo": ("Informe.docx", b"subida manual", "application/octet-stream")})
    assert r.status_code == 303
    monkeypatch.setattr(onlyoffice, "descargar_version", lambda url: almacen.guardar(io.BytesIO(b"editor anterior")))
    assert cliente.post(ruta, json={"token": firmado(evento(clave))}).json() == {"error": 1}
    actual = db.execute("SELECT sha256, numero FROM versiones_archivo ORDER BY numero DESC LIMIT 1").fetchone()
    assert actual["numero"] == 2 and almacen.ruta(actual["sha256"]).read_bytes() == b"subida manual"
