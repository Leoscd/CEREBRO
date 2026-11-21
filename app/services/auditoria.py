"""Registro de actividad: quién hizo qué, cuándo y sobre qué. Solo se agregan filas."""
from fastapi import Request
from psycopg import Connection
from psycopg.types.json import Jsonb

from app.services.limitador import ip_de


def registrar(
    db: Connection,
    usuario: dict | None,
    accion: str,
    *,
    empresa_id: int | None = None,
    proyecto_id: int | None = None,
    objeto: str = "",
    objeto_id: str | int = "",
    detalle: dict | None = None,
    request: Request | None = None,
) -> None:
    """Agrega una fila. No hace commit: va dentro de la misma transacción del cambio."""
    db.execute(
        """INSERT INTO auditoria (empresa_id, usuario_id, proyecto_id, accion, objeto, objeto_id, detalle, ip)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            empresa_id if empresa_id is not None else usuario["empresa_id"],
            usuario["id"] if usuario else None,
            proyecto_id,
            accion,
            objeto,
            str(objeto_id),
            Jsonb(detalle or {}),
            ip_de(request) if request is not None else "",
        ),
    )
