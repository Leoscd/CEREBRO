"""Subidas, descargas, aislamiento y almacenamiento por contenido."""
from urllib.parse import unquote

import pytest

from app import config
from tests.conftest import csrf_de


@pytest.fixture()
def directorio_almacen(tmp_path, monkeypatch):
    directorio = tmp_path / "archivos"
    monkeypatch.setattr(config, "ALMACEN_DIR", directorio)
    return directorio


def primera_carpeta(db, proyecto):
    return db.execute(
        """SELECT id FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s
           ORDER BY posicion, id LIMIT 1""",
        (proyecto["empresa_id"], proyecto["id"]),
    ).fetchone()["id"]


def subir(cliente, usuario, proyecto, carpeta_id, nombre="Plano Ñ.pdf", contenido=b"%PDF-1.7",
          mime="application/pdf"):
    return cliente.post(
        f"/proyectos/{proyecto['codigo']}/carpetas/{carpeta_id}/archivos",
        data={"csrf": csrf_de(usuario)}, files={"archivo": (nombre, contenido, mime)},
    )


def archivos_del_proyecto(db, proyecto):
    return db.execute(
        """SELECT a.id, a.nombre, a.extension, v.sha256
             FROM archivos a JOIN versiones_archivo v ON v.id = a.version_actual_id
            WHERE a.empresa_id = %s AND a.proyecto_id = %s ORDER BY a.id""",
        (proyecto["empresa_id"], proyecto["id"]),
    ).fetchall()


def test_subida_aparece_en_ficha_y_se_descarga(db, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    cliente = como("ana@a.test")
    carpeta = primera_carpeta(db, proyecto)
    ficha = f"/proyecto/{proyecto['codigo']}"
    assert f'/carpetas/{carpeta}/archivos"' in cliente.get(ficha).text
    respuesta = subir(cliente, mundo["ana"], proyecto, carpeta)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].split("#")[0] == ficha
    archivo, = archivos_del_proyecto(db, proyecto)
    assert "Plano Ñ.pdf" in cliente.get(ficha).text
    descarga = cliente.get(f"/archivos/{archivo['id']}/descargar")
    assert descarga.status_code == 200
    assert descarga.content == b"%PDF-1.7"
    assert "Plano Ñ.pdf" in unquote(descarga.headers["content-disposition"])
    assert descarga.headers["content-disposition"].startswith("attachment")
    assert db.execute(
        """SELECT usuario_id FROM auditoria
            WHERE empresa_id = %s AND proyecto_id = %s AND accion = 'archivo.subir' AND objeto_id = %s""",
        (proyecto["empresa_id"], proyecto["id"], str(archivo["id"])),
    ).fetchone() == {"usuario_id": mundo["ana"]["id"]}


def test_subida_rechaza_proyecto_carpeta_o_rol_ajeno(db, mundo, como, directorio_almacen):
    p1, p2 = mundo["p1"], mundo["p2"]
    c1, c2 = primera_carpeta(db, p1), primera_carpeta(db, p2)
    ana = como("ana@a.test")
    cliente = como("cliente@a.test")
    assert subir(ana, mundo["ana"], p2, c2).status_code == 404
    assert subir(cliente, mundo["cliente"], p1, c1).status_code == 403
    assert subir(ana, mundo["ana"], p1, c2).status_code == 404
    assert not archivos_del_proyecto(db, p1)
    assert not list(directorio_almacen.rglob("*"))


def test_descarga_protege_archivo_privado(db, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    assert subir(como("ana@a.test"), mundo["ana"], proyecto, primera_carpeta(db, proyecto)).status_code == 303
    archivo, = archivos_del_proyecto(db, proyecto)
    descarga = f"/archivos/{archivo['id']}/descargar"
    assert como("admin@b.test").get(descarga).status_code == 404
    assert como("cliente@a.test").get(descarga).status_code == 404


def test_subida_deduplica_blobs_y_limpia_nombre(db, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    ana = como("ana@a.test")
    carpeta = primera_carpeta(db, proyecto)
    for nombre in ["../../etc/passwd", "Otro.PDF"]:
        assert subir(ana, mundo["ana"], proyecto, carpeta, nombre=nombre).status_code == 303
    primero, segundo = archivos_del_proyecto(db, proyecto)
    assert primero["nombre"] == "passwd"
    assert segundo["extension"] == "pdf"
    assert primero["sha256"] == segundo["sha256"]
    assert [p.name for p in directorio_almacen.rglob("*") if p.is_file()] == [primero["sha256"]]


def test_subida_grande_limpia_temporal_y_no_crea_filas(db, mundo, como, directorio_almacen, monkeypatch):
    monkeypatch.setattr(config, "ARCHIVO_MAX_MB", 1, raising=False)
    proyecto = mundo["p1"]
    respuesta = subir(como("ana@a.test"), mundo["ana"], proyecto, primera_carpeta(db, proyecto),
                      contenido=b"x" * (1024 * 1024 + 1))
    assert respuesta.status_code == 413
    assert not archivos_del_proyecto(db, proyecto)
    assert not [p for p in directorio_almacen.rglob("*") if p.is_file()]
