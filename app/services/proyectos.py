"""Alta de proyectos con código correlativo PR-AAAA-NNN por empresa."""
from datetime import date

from psycopg import Connection


def siguiente_codigo(db: Connection, empresa_id: int, anio: int | None = None) -> str:
    """Correlativo por empresa y año. El lock evita que dos altas simultáneas choquen."""
    anio = anio or date.today().year
    db.execute("SELECT pg_advisory_xact_lock(%s, %s)", (910_001, empresa_id))
    prefijo = f"PR-{anio}-"
    fila = db.execute(
        """SELECT max(substring(codigo FROM %s)::int) AS n FROM proyectos
            WHERE empresa_id = %s AND codigo LIKE %s""",
        (len(prefijo) + 1, empresa_id, prefijo + "%"),
    ).fetchone()
    return f"{prefijo}{(fila['n'] or 0) + 1:03d}"


def crear_proyecto(db: Connection, usuario: dict, *, tipo_proyecto_id: int, nombre: str,
                   cliente_id: int | None = None, **campos) -> dict:
    tipo = db.execute(
        "SELECT id FROM tipos_proyecto WHERE id = %s AND empresa_id = %s",
        (tipo_proyecto_id, usuario["empresa_id"]),
    ).fetchone()
    if not tipo:
        raise ValueError("Tipo de proyecto inexistente")
    if cliente_id is not None and not db.execute(
        "SELECT 1 FROM clientes WHERE id = %s AND empresa_id = %s", (cliente_id, usuario["empresa_id"])
    ).fetchone():
        raise ValueError("Cliente inexistente")
    permitidos = {"descripcion", "direccion", "localidad", "etapa", "fecha_inicio", "fecha_fin_estimada",
                  "superficie_m2", "permite_difusion"}
    extra = {k: v for k, v in campos.items() if k in permitidos and v not in (None, "")}
    codigo = siguiente_codigo(db, usuario["empresa_id"])
    columnas = ["empresa_id", "tipo_proyecto_id", "codigo", "nombre", "cliente_id", "creado_por", *extra]
    valores = [usuario["empresa_id"], tipo_proyecto_id, codigo, nombre.strip(), cliente_id, usuario["id"],
               *extra.values()]
    marcas = ", ".join(["%s"] * len(valores))
    return db.execute(
        f"INSERT INTO proyectos ({', '.join(columnas)}) VALUES ({marcas}) RETURNING *", valores
    ).fetchone()
