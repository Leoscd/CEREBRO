"""Importes en centavos enteros y cantidades decimales exactas."""

import re
from collections.abc import Iterable
from decimal import Decimal

_PESOS = re.compile(
    r"(?:(?P<signo>[+-])\s*\$?|\$\s*(?P<signo_monto>[+-])?)?\s*"
    r"(?P<entero>[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,(?P<decimal>[0-9]{1,2}))?"
)


def leer_pesos(texto: str) -> int:
    importe = _PESOS.fullmatch(texto.strip())
    if not importe:
        raise ValueError("Importe inválido. Ingresá pesos con hasta dos decimales, por ejemplo $ 1.234,56.")
    pesos = int(importe["entero"].replace(".", ""))
    centavos = pesos * 100 + int((importe["decimal"] or "").ljust(2, "0"))
    return -centavos if "-" in (importe["signo"], importe["signo_monto"]) else centavos


def _redondear(numerador: int, denominador: int) -> int:
    """Redondea al entero más cercano. En un empate, se aleja de cero (half-up)."""
    entero, resto = divmod(abs(numerador), denominador)
    if 2 * resto >= denominador:
        entero += 1
    return -entero if numerador < 0 else entero


def multiplicar(centavos: int, cantidad: Decimal) -> int:
    numerador, denominador = cantidad.as_integer_ratio()
    return _redondear(centavos * numerador, denominador)


def aplicar_coeficiente(centavos: int, puntos_basicos: int) -> int:
    return _redondear(centavos * puntos_basicos, 10_000)


def sumar(importes: Iterable[int]) -> int:
    return sum(importes)


def formatear(centavos: int) -> str:
    pesos, resto = divmod(abs(centavos), 100)
    miles = f"{pesos:,}".replace(",", ".")
    signo = "-" if centavos < 0 else ""
    return f"{signo}$ {miles},{resto:02d}"
