"""Extracción de texto por página y fragmentos con solapamiento por palabras."""
from collections.abc import Iterator
from pathlib import Path

from pypdf import PdfReader

_LARGO = 1000
_SOLAPAMIENTO = 150


def es_pdf(ruta: Path) -> bool:
    """Detecta un PDF completo sin analizar sus objetos durante la subida."""
    with ruta.open("rb") as stream:
        if not stream.read(5).startswith(b"%PDF-"):
            return False
        tamano = stream.seek(0, 2)
        stream.seek(max(0, tamano - 4096))
        return b"%%EOF" in stream.read()


def _partir(texto: str) -> Iterator[str]:
    palabras = texto.replace("\x00", " ").replace("\x01", " ").replace("\x02", " ").split()
    inicio = 0
    while inicio < len(palabras):
        fin = inicio + 1
        largo = len(palabras[inicio])
        while fin < len(palabras) and largo + 1 + len(palabras[fin]) <= _LARGO:
            largo += 1 + len(palabras[fin])
            fin += 1
        yield " ".join(palabras[inicio:fin])
        if fin == len(palabras):
            break
        siguiente = fin
        solapamiento = 0
        while siguiente > inicio + 1 and solapamiento + 1 + len(palabras[siguiente - 1]) <= _SOLAPAMIENTO:
            siguiente -= 1
            solapamiento += 1 + len(palabras[siguiente])
        inicio = siguiente


def fragmentos_pdf(ruta: Path) -> Iterator[tuple[int, int, str]]:
    with ruta.open("rb") as stream:
        pdf = PdfReader(stream)
        for pagina, hoja in enumerate(pdf.pages, 1):
            for orden, fragmento in enumerate(_partir(hoja.extract_text() or "")):
                yield pagina, orden, fragmento
