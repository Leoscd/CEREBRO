"""Acceso a PostgreSQL con un pool de conexiones (psycopg 3, filas como dict).

Cada pedido HTTP toma una conexión del pool con `db_dependency`. Los endpoints que
escriben hacen `db.commit()` explícito antes de responder (igual que en el curso), así
el siguiente pedido ya ve el cambio.
"""
from collections.abc import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

_pool: ConnectionPool | None = None


def abrir_pool(url: str | None = None, min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            url or config.DATABASE_URL,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


def cerrar_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def pool() -> ConnectionPool:
    return abrir_pool()


def db_dependency() -> Iterator[Connection]:
    with pool().connection() as conn:
        yield conn
