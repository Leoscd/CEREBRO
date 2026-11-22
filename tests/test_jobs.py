"""Encolado transaccional, reintentos y recuperación de trabajos."""
import os
import subprocess
import sys

import psycopg
from psycopg.rows import dict_row

from app import config
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen
from tests.test_versiones import nueva_version


def test_subidas_encolan_y_worker_analiza_pdf(db, db_url, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    usuario = mundo["ana"]
    ana = como("ana@a.test")
    assert subir(ana, usuario, proyecto, primera_carpeta(db, proyecto)).status_code == 303
    archivo, = archivos_del_proyecto(db, proyecto)
    assert nueva_version(ana, usuario, f"/archivos/{archivo['id']}").status_code == 303
    pendientes = db.execute(
        "SELECT estado, tipo FROM jobs WHERE empresa_id = %s ORDER BY id", (usuario["empresa_id"],),
    ).fetchall()
    assert pendientes == [{"estado": "pendiente", "tipo": "archivo.analizar"}] * 2
    db.commit()

    subprocess.run(
        [sys.executable, "-m", "app.worker", "--una-vez"], check=True, timeout=35,
        env={**os.environ, "DATABASE_URL": db_url, "ALMACEN_DIR": str(directorio_almacen)},
    )
    versiones = db.execute(
        """SELECT tamano_bytes, derivados FROM versiones_archivo WHERE empresa_id = %s AND archivo_id = %s
           ORDER BY numero""",
        (usuario["empresa_id"], archivo["id"]),
    ).fetchall()
    assert len(versiones) == 2
    for version in versiones:
        assert version["derivados"]["meta"] == {"mime_real": "application/pdf", "tamano": version["tamano_bytes"]}
    assert db.execute(
        "SELECT count(*) AS total FROM jobs WHERE empresa_id = %s AND estado = 'hecho'", (usuario["empresa_id"],),
    ).fetchone()["total"] == 2


def test_error_reintenta_y_al_agotar_queda_fallido(db, mundo, monkeypatch):
    from app import worker
    from app.services import jobs

    def falla(*args):
        raise ValueError("no se pudo analizar")

    monkeypatch.setitem(worker.MANEJADORES, "prueba.error", falla)
    empresa_id = mundo["ea"]["id"]
    trabajo_id = jobs.encolar(db, empresa_id, "prueba.error", {}, max_intentos=2)
    db.commit()
    assert worker.procesar_uno(db)
    fila = db.execute(
        """SELECT estado, intentos, disponible_desde > now() AS diferido
           FROM jobs WHERE empresa_id = %s AND id = %s""",
        (empresa_id, trabajo_id),
    ).fetchone()
    assert fila == {"estado": "pendiente", "intentos": 1, "diferido": True}
    db.execute("UPDATE jobs SET disponible_desde = now() WHERE empresa_id = %s AND id = %s",
               (empresa_id, trabajo_id))
    db.commit()
    assert worker.procesar_uno(db)
    fila = db.execute(
        "SELECT estado, intentos, error, terminado_en FROM jobs WHERE empresa_id = %s AND id = %s",
        (empresa_id, trabajo_id),
    ).fetchone()
    assert fila["estado"] == "fallido"
    assert fila["intentos"] == 2
    assert "no se pudo analizar" in fila["error"]
    assert fila["terminado_en"] is not None


def test_tomar_en_dos_conexiones_salta_el_trabajo_bloqueado(db, db_url, mundo):
    from app.services import jobs

    empresa_id = mundo["ea"]["id"]
    primero = jobs.encolar(db, empresa_id, "prueba", {})
    segundo = jobs.encolar(db, empresa_id, "prueba", {})
    db.commit()
    with psycopg.connect(db_url, row_factory=dict_row) as otra:
        otra.execute("SET LOCAL statement_timeout = '3s'")
        assert jobs.tomar(db)["id"] == primero
        assert jobs.tomar(otra)["id"] == segundo
        otra.commit()
    db.commit()


def test_trabajo_abandonado_se_retoma_y_el_intento_anterior_no_lo_cierra(db, mundo):
    from app.services import jobs

    empresa_id = mundo["ea"]["id"]
    trabajo_id = jobs.encolar(db, empresa_id, "prueba", {})
    anterior = jobs.tomar(db)
    assert anterior["id"] == trabajo_id
    db.execute(
        "UPDATE jobs SET tomado_en = now() - interval '16 minutes' WHERE empresa_id = %s AND id = %s",
        (empresa_id, trabajo_id),
    )
    db.commit()
    nuevo = jobs.tomar(db)
    assert nuevo["id"] == anterior["id"]
    assert nuevo["intentos"] == anterior["intentos"] + 1
    assert not jobs.completar(db, anterior)
    assert jobs.completar(db, nuevo)


def test_subida_rechazada_no_encola(db, mundo, como, directorio_almacen, monkeypatch):
    monkeypatch.setattr(config, "ARCHIVO_MAX_MB", 1)
    proyecto = mundo["p1"]
    ana = como("ana@a.test")
    respuesta = subir(ana, mundo["ana"], proyecto, primera_carpeta(db, proyecto), contenido=b"x" * (1024**2 + 1))
    assert respuesta.status_code == 413
    assert db.execute("SELECT 1 FROM jobs WHERE empresa_id = %s", (mundo["ea"]["id"],)).fetchone() is None


def test_analisis_filtra_version_por_empresa(db, mundo, como, directorio_almacen):
    from app import worker
    from app.services import jobs

    proyecto = mundo["p1"]
    ana = como("ana@a.test")
    assert subir(ana, mundo["ana"], proyecto, primera_carpeta(db, proyecto)).status_code == 303
    empresa_a, empresa_b = mundo["ea"]["id"], mundo["eb"]["id"]
    version = db.execute("SELECT id FROM versiones_archivo WHERE empresa_id = %s", (empresa_a,)).fetchone()
    ajeno = jobs.encolar(db, empresa_b, "archivo.analizar", {"version_id": version["id"]}, max_intentos=1)
    # El intento de la otra empresa corre antes de que se analice la versión válida.
    db.execute("UPDATE jobs SET disponible_desde = now() - interval '1 minute' WHERE empresa_id = %s AND id = %s",
               (empresa_b, ajeno))
    db.commit()
    assert worker.procesar_uno(db)
    assert db.execute("SELECT estado FROM jobs WHERE empresa_id = %s AND id = %s",
                      (empresa_b, ajeno)).fetchone()["estado"] == "fallido"
    assert db.execute("SELECT derivados FROM versiones_archivo WHERE empresa_id = %s AND id = %s",
                      (empresa_a, version["id"])).fetchone()["derivados"] == {}
