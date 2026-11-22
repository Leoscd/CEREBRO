"""Cola compartida de Postgres. El llamador define los límites de la transacción."""
from psycopg import Connection
from psycopg.types.json import Jsonb


def encolar(db: Connection, empresa_id: int, tipo: str, payload: dict, *, max_intentos: int = 3) -> int:
    fila = db.execute(
        """INSERT INTO jobs (empresa_id, tipo, payload, max_intentos)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (empresa_id, tipo, Jsonb(payload), max_intentos),
    ).fetchone()
    return fila["id"]


def tomar(db: Connection) -> dict | None:
    """Recupera trabajos vencidos y reserva un trabajo listo para este worker."""
    db.execute(
        """WITH abandonados AS (
               SELECT id FROM jobs WHERE estado = 'en_curso' AND tomado_en < now() - interval '15 minutes'
               FOR UPDATE SKIP LOCKED
           )
           UPDATE jobs j
              SET estado = CASE WHEN intentos >= max_intentos THEN 'fallido' ELSE 'pendiente' END,
                  terminado_en = CASE WHEN intentos >= max_intentos THEN now() END,
                  disponible_desde = now(), tomado_en = NULL,
                  error = 'El worker no terminó el trabajo en 15 minutos'
             FROM abandonados WHERE j.id = abandonados.id""",
    )
    return db.execute(
        """WITH candidato AS (
               SELECT id FROM jobs WHERE estado = 'pendiente' AND disponible_desde <= now()
               ORDER BY disponible_desde, id LIMIT 1 FOR UPDATE SKIP LOCKED
           )
           UPDATE jobs j SET estado = 'en_curso', intentos = j.intentos + 1, tomado_en = now()
             FROM candidato WHERE j.id = candidato.id
           RETURNING j.*""",
    ).fetchone()


def _reserva(trabajo: dict) -> tuple:
    return trabajo["empresa_id"], trabajo["id"], trabajo["intentos"], trabajo["tomado_en"]


def completar(db: Connection, trabajo: dict) -> bool:
    return db.execute(
        """UPDATE jobs SET estado = 'hecho', terminado_en = now(), error = NULL
            WHERE empresa_id = %s AND id = %s AND intentos = %s AND tomado_en = %s AND estado = 'en_curso'""",
        _reserva(trabajo),
    ).rowcount == 1


def fallar(db: Connection, trabajo: dict, error: str) -> bool:
    espera = min(300, 5 * 2 ** min(trabajo["intentos"] - 1, 6))
    return db.execute(
        """UPDATE jobs
              SET estado = CASE WHEN intentos >= max_intentos THEN 'fallido' ELSE 'pendiente' END,
                  terminado_en = CASE WHEN intentos >= max_intentos THEN now() END,
                  disponible_desde = now() + make_interval(secs => %s),
                  tomado_en = NULL, error = %s
            WHERE empresa_id = %s AND id = %s AND intentos = %s AND tomado_en = %s AND estado = 'en_curso'""",
        (espera, error.replace("\x00", "")[:1000], *_reserva(trabajo)),
    ).rowcount == 1
