"""Almacenamiento local por SHA-256, con publicación atómica del blob."""
import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from fastapi import HTTPException

from app import config

_BLOQUE = 1024 * 1024


def ruta(sha256: str) -> Path:
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ValueError("SHA-256 inválido")
    return config.ALMACEN_DIR / sha256[:2] / sha256


def guardar(stream: BinaryIO) -> tuple[str, int]:
    config.ALMACEN_DIR.mkdir(parents=True, exist_ok=True)
    limite = config.ARCHIVO_MAX_MB * 1024 * 1024
    hasher = hashlib.sha256()
    tamano = 0
    temporal = NamedTemporaryFile(dir=config.ALMACEN_DIR, prefix=".subida-", delete=False)
    try:
        with temporal:
            while bloque := stream.read(_BLOQUE):
                tamano += len(bloque)
                if tamano > limite:
                    raise HTTPException(status_code=413, detail=f"El máximo es {config.ARCHIVO_MAX_MB} MB por archivo")
                hasher.update(bloque)
                temporal.write(bloque)
        sha256 = hasher.hexdigest()
        destino = ruta(sha256)
        destino.parent.mkdir(exist_ok=True)
        if not destino.exists():
            os.replace(temporal.name, destino)
        return sha256, tamano
    finally:
        Path(temporal.name).unlink(missing_ok=True)
