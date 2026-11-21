"""Aplica las migraciones SQL numeradas de app/db/migraciones, una sola vez cada una.

Uso: python -m app.db.migrar
Las migraciones son aditivas (nunca se edita una ya aplicada: se agrega otra).
"""
import sys
from pathlib import Path

import psycopg

from app import config

CARPETA = Path(__file__).parent / "migraciones"
_LOCK = 72_000_001  # advisory lock: dos procesos no migran a la vez


def migrar(url: str | None = None, verbose: bool = True) -> list[str]:
    aplicadas: list[str] = []
    with psycopg.connect(url or config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " nombre text PRIMARY KEY, aplicada_en timestamptz NOT NULL DEFAULT now())"
            )
            hechas = {r[0] for r in conn.execute("SELECT nombre FROM schema_migrations")}
            for archivo in sorted(CARPETA.glob("*.sql")):
                if archivo.name in hechas:
                    continue
                sql = archivo.read_text(encoding="utf-8")
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute("INSERT INTO schema_migrations (nombre) VALUES (%s)", (archivo.name,))
                aplicadas.append(archivo.name)
                if verbose:
                    print(f"migración aplicada: {archivo.name}")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK,))
    return aplicadas


if __name__ == "__main__":
    hechas = migrar(sys.argv[1] if len(sys.argv) > 1 else None)
    if not hechas:
        print("La base ya estaba al día.")
