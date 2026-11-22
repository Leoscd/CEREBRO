"""Almacenamiento local por SHA-256, con publicación atómica del blob."""
import hashlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from typing import BinaryIO

from fastapi import HTTPException

from app import config

_BLOQUE = 1024 * 1024


def ruta(sha256: str) -> Path:
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ValueError("SHA-256 inválido")
    return config.ALMACEN_DIR / sha256[:2] / sha256


@contextmanager
def bloqueo_publicacion() -> Iterator[None]:
    """Serializa la publicación y el borrado de blobs en este almacén."""
    if os.name == "nt":
        import msvcrt

        clave = hashlib.sha256(str(config.ALMACEN_DIR.resolve()).casefold().encode()).hexdigest()
        with (Path(gettempdir()) / f"gsp-almacen-{clave}.lock").open("a+b") as lock:
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            yield
    else:
        import fcntl

        fd = os.open(config.ALMACEN_DIR, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)


def guardar(stream: BinaryIO, validar: Callable[[Path], bool] | None = None) -> tuple[str, int]:
    config.ALMACEN_DIR.mkdir(parents=True, exist_ok=True)
    limite = config.ARCHIVO_MAX_MB * 1024 * 1024
    hasher = hashlib.sha256()
    tamano = 0
    temporal = NamedTemporaryFile(dir=config.ALMACEN_DIR, prefix=".subida-", delete=False)
    ruta_temporal = Path(temporal.name)
    try:
        with temporal:
            while bloque := stream.read(_BLOQUE):
                tamano += len(bloque)
                if tamano > limite:
                    raise HTTPException(status_code=413, detail=f"El máximo es {config.ARCHIVO_MAX_MB} MB por archivo")
                hasher.update(bloque)
                temporal.write(bloque)
        if validar is not None and not validar(ruta_temporal):
            raise HTTPException(status_code=400, detail="El archivo no es válido para esta carga")
        sha256 = hasher.hexdigest()
        destino = ruta(sha256)
        with bloqueo_publicacion():
            destino.parent.mkdir(exist_ok=True)
            # Una subida que reutiliza un blob viejo también necesita el margen para el commit.
            if destino.exists():
                os.utime(destino)
            else:
                os.utime(ruta_temporal)
                os.replace(ruta_temporal, destino)
        return sha256, tamano
    finally:
        ruta_temporal.unlink(missing_ok=True)
