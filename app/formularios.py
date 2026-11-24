"""Conversión de campos enviados por formularios HTML."""

import re

from fastapi import HTTPException


def id_opcional(valor: str, campo: str) -> int | None:
    valor = valor.strip()
    if not valor:
        return None
    if not re.fullmatch(r"[0-9]{1,19}", valor) or not 0 < (identificador := int(valor)) <= 2**63 - 1:
        raise HTTPException(400, f"Ingresá un identificador válido para {campo}.")
    return identificador
