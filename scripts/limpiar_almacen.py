"""Lista los blobs huérfanos y temporales viejos. En el VPS:

    docker compose exec app python -m scripts.limpiar_almacen --borrar

Se busca en todas las empresas porque el almacén físico es compartido.
"""
import argparse
import re
import stat
import time
from collections.abc import Iterator
from pathlib import Path

import psycopg
from psycopg import Connection

from app import config
from app.services import almacen

_PREFIJO = re.compile(r"[0-9a-f]{2}")
_HASH = re.compile(r"[0-9a-f]{64}")


def _candidatos(raiz: Path) -> Iterator[tuple[Path, str | None]]:
    if not raiz.is_dir():
        return
    for entrada in sorted(raiz.iterdir()):
        if entrada.name.startswith(".subida-"):
            yield entrada, None
        elif (_PREFIJO.fullmatch(entrada.name) and not entrada.is_symlink()
              and not entrada.is_junction() and entrada.is_dir()):
            for blob in sorted(entrada.iterdir()):
                if _HASH.fullmatch(blob.name) and blob.name.startswith(entrada.name):
                    yield blob, blob.name


def _tamano_viejo(ruta: Path, corte: float) -> int | None:
    try:
        datos = ruta.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISREG(datos.st_mode) and datos.st_mtime < corte:
        return datos.st_size
    return None


def _referenciado(db: Connection, sha256: str) -> bool:
    return db.execute(
        """SELECT EXISTS (SELECT 1 FROM versiones_archivo WHERE sha256 = %s)
               OR EXISTS (SELECT 1 FROM biblioteca_documentos WHERE sha256 = %s)""",
        (sha256, sha256),
    ).fetchone()[0]


def _borrar(db: Connection, ruta: Path, sha256: str | None, corte: float) -> int | None:
    with almacen.bloqueo_publicacion():
        tamano = _tamano_viejo(ruta, corte)
        if tamano is None or (sha256 is not None and _referenciado(db, sha256)):
            return None
        try:
            ruta.unlink()
        except FileNotFoundError:
            return None
        return tamano


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--borrar", action="store_true", help="Borra los archivos listados")
    parser.add_argument("--horas", type=int, default=24, help="Antigüedad mínima de los candidatos")
    opciones = parser.parse_args()
    if opciones.horas < 1:
        parser.error("--horas debe ser al menos 1")

    corte = time.time() - opciones.horas * 3600
    raiz = config.ALMACEN_DIR
    cantidad = total = 0
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as db:
        for ruta, sha256 in _candidatos(raiz):
            tamano = _tamano_viejo(ruta, corte)
            if tamano is None or (sha256 is not None and _referenciado(db, sha256)):
                continue
            if opciones.borrar:
                tamano = _borrar(db, ruta, sha256, corte)
                if tamano is None:
                    continue
            print(ruta.relative_to(raiz))
            cantidad += 1
            total += tamano
    verbo = "Borrados" if opciones.borrar else "Candidatos"
    print(f"{verbo}: {cantidad} archivos, {total} bytes")


if __name__ == "__main__":
    main()
