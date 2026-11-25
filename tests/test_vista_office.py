import shutil
import subprocess

import pytest

from app import config
from app.services import gotenberg
from tests.fixtures.pdf import pdf_de_paginas
from tests.test_busqueda import buscar, procesar_pendientes
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


@pytest.fixture
def office(db, mundo, como, directorio_almacen):
    proyecto = mundo["p2"]
    admin = como("admin@a.test")
    assert subir(admin, mundo["admin_a"], proyecto, primera_carpeta(db, proyecto),
                 "Memoria.docx", b"documento de prueba", "application/octet-stream").status_code == 303
    archivo, = archivos_del_proyecto(db, proyecto)
    return f"/archivos/{archivo['id']}"


def test_office_pdf_cita_y_aislamiento(db, mundo, como, office, monkeypatch):
    pdf = pdf_de_paginas("Portada", "estereotomia violeta")
    def convertir(ruta, nombre):
        assert nombre == "Memoria.docx" and ruta.read_bytes() == b"documento de prueba"
        return pdf

    monkeypatch.setattr(gotenberg, "a_pdf", convertir)
    admin = como("admin@a.test")
    assert "Preparando la vista previa" in admin.get(office).text
    assert admin.get(office + "/vista.pdf").status_code == 404
    procesar_pendientes(db)
    d = db.execute("SELECT derivados FROM versiones_archivo").fetchone()["derivados"]
    assert d["vista"] == "lista" and d["pdf"]["tamano"] == len(pdf)
    r = admin.get(office + "/vista.pdf")
    assert r.content == pdf and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline") and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "private, no-store"
    assert f'data-contenido="{office}/vista.pdf"' in admin.get(office).text
    assert office + "#page=2" in buscar(admin, mundo["p2"], "estereotomia").text
    for email, proyecto in [("ana@a.test", "p1"), ("admin@b.test", "pb")]:
        otro = como(email)
        assert otro.get(office + "/vista.pdf").status_code == otro.get(office + "/descargar").status_code == 404
        assert office + "#page=" not in buscar(otro, mundo[proyecto], "estereotomia").text


def test_office_sin_conversor(db, como, office, monkeypatch):
    monkeypatch.setattr(config, "GOTENBERG_URL", "")
    procesar_pendientes(db)
    assert db.execute("SELECT derivados->>'vista' AS estado FROM versiones_archivo").fetchone()["estado"] == "sin_conversor"
    assert db.execute("SELECT estado FROM jobs WHERE tipo='archivo.vista_pdf'").fetchone()["estado"] == "hecho"
    assert "La vista previa no está disponible" in como("admin@a.test").get(office).text


def test_office_marca_error_al_agotar_reintentos(db, office, monkeypatch):
    monkeypatch.setattr(gotenberg, "a_pdf", lambda *args: b"PDF invalido")
    db.execute("UPDATE jobs SET max_intentos=2 WHERE tipo='archivo.vista_pdf'")
    procesar_pendientes(db)
    assert db.execute("SELECT derivados->>'vista' AS estado FROM versiones_archivo").fetchone()["estado"] == "pendiente"
    db.execute("UPDATE jobs SET disponible_desde=now() WHERE estado='pendiente'")
    procesar_pendientes(db)
    assert db.execute("SELECT derivados->>'vista' AS estado FROM versiones_archivo").fetchone()["estado"] == "error"


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose se verifica en CI")
def test_configuracion_compose(tmp_path):
    # Compose resuelve el env_file de los servicios respecto del proyecto.
    shutil.copyfile("docker-compose.yml", tmp_path / "docker-compose.yml")
    shutil.copyfile(".env.ci", tmp_path / ".env")
    subprocess.run(["docker", "compose", "config", "--quiet"], cwd=tmp_path, check=True, timeout=30)
