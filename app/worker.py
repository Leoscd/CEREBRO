"""Procesa trabajos de Postgres. Uso: python -m app.worker [--una-vez]."""
import argparse
import logging
import os
import signal
from threading import Event

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.db import abrir_pool, cerrar_pool
from app.services import almacen, jobs

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


MANEJADORES = {"archivo.analizar": analizar_archivo}


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
