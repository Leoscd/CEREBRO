"""Conversión de las marcas de tiempo a la zona horaria del curso.

SQLite guarda en UTC (`datetime('now')`). Si se compara eso contra el día local, un
alumno que estudia a las 22 hs queda registrado al día siguiente y se le rompe la racha.
"""
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import config

try:
    TZ = ZoneInfo(config.TIMEZONE)
except (ZoneInfoNotFoundError, ValueError):
    # Windows no trae la base IANA (se resuelve con el paquete `tzdata`). Ante una zona
    # inválida se sigue en UTC: las horas quedan corridas, pero la app no se cae.
    logging.warning(
        "Zona horaria '%s' no encontrada; se usa UTC. Instalá `tzdata` o revisá TIMEZONE.",
        config.TIMEZONE,
    )
    TZ = timezone.utc


def a_local(valor: str | datetime | None) -> datetime | None:
    """Pasa una marca guardada en UTC a la zona del curso."""
    if not valor:
        return None
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(TZ)


def dia_local(valor: str | datetime | None) -> date | None:
    fecha = a_local(valor)
    return fecha.date() if fecha else None


def hoy_local() -> date:
    return datetime.now(TZ).date()


def formatear(valor: str | date | datetime | None, con_hora: bool = True) -> str:
    """Para mostrar en pantalla, ya en hora local. Las fechas sin hora (date) van tal cual."""
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    fecha = a_local(valor)
    if not fecha:
        return "—"
    return fecha.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")
