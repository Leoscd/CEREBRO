"""Conversión de Office a PDF con el servicio de la red interna."""
from pathlib import Path

import httpx

from app import config

EXTENSIONES = frozenset("docx xlsx pptx odt ods odp doc xls ppt rtf".split())


class SinConversor(Exception):
    pass


def a_pdf(ruta: Path, nombre: str) -> bytes:
    if not config.GOTENBERG_URL:
        raise SinConversor()
    limite = config.GOTENBERG_PDF_MAX_MB * 1024**2
    contenido = bytearray()
    with ruta.open("rb") as origen, httpx.Client(timeout=config.GOTENBERG_TIMEOUT, trust_env=False) as cliente:
        with cliente.stream("POST", config.GOTENBERG_URL + "/forms/libreoffice/convert",
                            files={"files": (nombre, origen, "application/octet-stream")}) as respuesta:
            respuesta.raise_for_status()
            for bloque in respuesta.iter_bytes(chunk_size=65536):
                if len(contenido) + len(bloque) > limite:
                    raise ValueError("El PDF convertido supera el tamaño permitido.")
                contenido.extend(bloque)
    return bytes(contenido)
