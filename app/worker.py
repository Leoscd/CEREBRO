"""Procesa trabajos de Postgres. Uso: python -m app.worker [--una-vez]."""
import argparse
import logging
import os
import signal
from threading import Event

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.db import abrir_pool, cerrar_pool
from app.services import almacen, embeddings, jobs, pdf_parte, texto

log = logging.getLogger(__name__)

_FIRMAS = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
)


def analizar_archivo(db: Connection, empresa_id: int, payload: dict) -> None:
    version_id = payload["version_id"]
    version = db.execute(
        "SELECT sha256 FROM versiones_archivo WHERE empresa_id = %s AND id = %s",
        (empresa_id, version_id),
    ).fetchone()
    if version is None:
        raise ValueError("Versión no encontrada")
    with almacen.ruta(version["sha256"]).open("rb") as blob:
        cabecera = blob.read(12)
        tamano = os.fstat(blob.fileno()).st_size
    # DOCX, XLSX y PPTX comparten la firma ZIP; la cabecera confirma el contenedor.
    mime = next((tipo for firma, tipo in _FIRMAS if cabecera.startswith(firma)), "application/octet-stream")
    db.execute(
        """UPDATE versiones_archivo
              SET derivados = jsonb_set(derivados, '{meta}', coalesce(derivados->'meta', '{}'::jsonb) || %s)
            WHERE empresa_id = %s AND id = %s""",
        (Jsonb({"mime_real": mime, "tamano": tamano}), empresa_id, version_id),
    )


def indexar_archivo(db: Connection, empresa_id: int, payload: dict) -> None:
    version_id = payload["version_id"]
    archivo = db.execute(
        """SELECT v.sha256, a.id, a.proyecto_id
             FROM versiones_archivo v JOIN archivos a ON a.empresa_id = v.empresa_id AND a.id = v.archivo_id
            WHERE v.empresa_id = %s AND v.id = %s AND a.version_actual_id = v.id""",
        (empresa_id, version_id),
    ).fetchone()
    if archivo is None:
        return
    fragmentos = list(texto.fragmentos_pdf(almacen.ruta(archivo["sha256"])))
    # La versión puede haber cambiado mientras se extraía el texto.
    vigente = db.execute(
        """SELECT 1 FROM archivos WHERE empresa_id = %s AND proyecto_id = %s AND id = %s AND version_actual_id = %s
           FOR UPDATE""",
        (empresa_id, archivo["proyecto_id"], archivo["id"], version_id),
    ).fetchone()
    if vigente is None:
        return
    db.execute(
        """DELETE FROM chunks WHERE empresa_id = %s AND proyecto_id = %s AND version_id IN (
               SELECT id FROM versiones_archivo WHERE empresa_id = %s AND archivo_id = %s
           )""",
        (empresa_id, archivo["proyecto_id"], empresa_id, archivo["id"]),
    )
    with db.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO chunks (empresa_id, proyecto_id, version_id, pagina, orden, texto)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            [(empresa_id, archivo["proyecto_id"], version_id, *fragmento) for fragmento in fragmentos],
        )
    db.execute(
        """UPDATE versiones_archivo SET derivados = derivados || %s WHERE empresa_id = %s AND id = %s""",
        (Jsonb({"texto": "indexado" if fragmentos else "sin_texto"}), empresa_id, version_id),
    )
    if fragmentos:
        jobs.encolar(db, empresa_id, "chunks.embeber", {"version_id": version_id})


def embeber_chunks(db: Connection, empresa_id: int, payload: dict) -> None:
    if "biblioteca_id" in payload:
        filas = db.execute(
            """SELECT id, texto FROM chunks WHERE empresa_id = %s AND biblioteca_id = %s AND embedding IS NULL
               ORDER BY id""",
            (empresa_id, payload["biblioteca_id"]),
        ).fetchall()
    else:
        filas = db.execute(
            """SELECT c.id, c.texto FROM chunks c
             JOIN archivos a ON a.empresa_id = c.empresa_id AND a.proyecto_id = c.proyecto_id
                            AND a.version_actual_id = c.version_id
            WHERE c.empresa_id = %s AND c.version_id = %s AND c.embedding IS NULL
            ORDER BY c.id""",
            (empresa_id, payload["version_id"]),
        ).fetchall()
    vectores = embeddings.embeber([fila["texto"] for fila in filas])
    with db.cursor() as cursor:
        cursor.executemany(
            """UPDATE chunks SET embedding = %s::vector
                WHERE empresa_id = %s AND id = %s AND embedding IS NULL""",
            [(embeddings.vector_sql(vector), empresa_id, fila["id"]) for fila, vector in zip(filas, vectores, strict=True)],
        )


def indexar_biblioteca(db: Connection, empresa_id: int, payload: dict) -> None:
    documento_id = payload["biblioteca_id"]
    fila = db.execute(
        "SELECT sha256 FROM biblioteca_documentos WHERE empresa_id = %s AND id = %s",
        (empresa_id, documento_id),
    ).fetchone()
    if fila is None:
        return
    fragmentos = list(texto.fragmentos_pdf(almacen.ruta(fila["sha256"])))
    db.execute("DELETE FROM chunks WHERE empresa_id = %s AND biblioteca_id = %s", (empresa_id, documento_id))
    with db.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO chunks (empresa_id, biblioteca_id, pagina, orden, texto)
               VALUES (%s, %s, %s, %s, %s)""",
            [(empresa_id, documento_id, *fragmento) for fragmento in fragmentos],
        )
    if fragmentos:
        jobs.encolar(db, empresa_id, "chunks.embeber", {"biblioteca_id": documento_id})


MANEJADORES = {
    "parte.pdf": pdf_parte.publicar,
    "archivo.analizar": analizar_archivo,
    "archivo.indexar": indexar_archivo,
    "chunks.embeber": embeber_chunks,
    "biblioteca.indexar": indexar_biblioteca,
}


def procesar_uno(db: Connection) -> bool:
    trabajo = jobs.tomar(db)
    db.commit()
    if trabajo is None:
        return False
    try:
        manejador = MANEJADORES.get(trabajo["tipo"])
        if manejador is None:
            raise ValueError(f"Tipo de trabajo desconocido: {trabajo['tipo']}")
        manejador(db, trabajo["empresa_id"], trabajo["payload"])
        if jobs.completar(db, trabajo):
            db.commit()
        else:
            # Otro worker recuperó la reserva durante el análisis.
            db.rollback()
    except Exception as error:
        db.rollback()
        jobs.fallar(db, trabajo, str(error))
        db.commit()
        log.warning("Falló el intento %s del trabajo %s", trabajo["intentos"], trabajo["id"])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--una-vez", action="store_true", help="Procesar los trabajos disponibles y salir")
    opciones = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    detener = Event()

    def pedir_cierre(_signum, _frame):
        detener.set()

    signal.signal(signal.SIGINT, pedir_cierre)
    signal.signal(signal.SIGTERM, pedir_cierre)
    try:
        with abrir_pool(min_size=1, max_size=1).connection() as db:
            while not detener.is_set():
                if procesar_uno(db):
                    continue
                if opciones.una_vez:
                    break
                detener.wait(2)
    finally:
        cerrar_pool()


if __name__ == "__main__":
    main()
