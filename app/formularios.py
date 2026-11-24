"""Conversión de campos enviados por formularios HTML."""

import re
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException


def id_opcional(valor: str, campo: str) -> int | None:
    valor = valor.strip()
    if not valor:
        return None
    if not re.fullmatch(r"[0-9]{1,19}", valor) or not 0 < (identificador := int(valor)) <= 2**63 - 1:
        raise HTTPException(400, f"Ingresá un identificador válido para {campo}.")
    return identificador


def porcentaje_a_pb(valor: str | None, campo: str, *, anterior: int = 0, maximo: int = 2**31 - 1) -> int:
    if valor is None:
        return anterior
    if isinstance(valor, str) and re.fullmatch(r"[0-9]{1,10}(?:[.,][0-9]{1,2})?", valor.strip()):
        puntos = int(Decimal(valor.strip().replace(",", ".")) * 100)
        if puntos <= maximo:
            return puntos
    raise HTTPException(400, f"Ingresá un porcentaje válido para {campo}, con hasta dos decimales.")


def cantidad_decimal(valor: str, *, positiva: bool = False) -> Decimal:
    entrada = valor.strip()
    if re.fullmatch(r"[+-]?[0-9]{1,3}(?:\.[0-9]{3})+,[0-9]+", entrada):
        entrada = entrada.replace(".", "")
    try:
        cantidad = Decimal(entrada.replace(",", "."))
        if not cantidad.is_finite() or not abs(cantidad) < 10**10 or (positiva and cantidad <= 0):
            raise InvalidOperation
        exacta = cantidad.quantize(Decimal("0.0001"))
        if cantidad != exacta:
            raise InvalidOperation
    except InvalidOperation as error:
        raise HTTPException(400, "Ingresá una cantidad válida con hasta cuatro decimales.") from error
    return exacta
