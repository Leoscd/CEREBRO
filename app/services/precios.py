"""Catálogo y cotizaciones por empresa. Una cotización siempre agrega una fila."""

from datetime import date, datetime, time

from psycopg import Connection

from app.services import auditoria
from app.services.tiempo import TZ


def vigente(db: Connection, empresa_id: int, material_id: int, a_fecha: date | datetime) -> dict | None:
    """Resuelve al instante indicado o al cierre del día local si recibe una fecha."""
    limite = a_fecha if isinstance(a_fecha, datetime) else datetime.combine(a_fecha, time.max, TZ)
    if limite.tzinfo is None:
        limite = limite.replace(tzinfo=TZ)
    return db.execute(
        """SELECT id, precio_centavos, vigente_desde, proveedor_id, fuente
             FROM precios WHERE empresa_id=%s AND material_id=%s AND vigente_desde<=%s
            ORDER BY vigente_desde DESC, id DESC LIMIT 1""",
        (empresa_id, material_id, limite),
    ).fetchone()


def cargar(db: Connection, usuario: dict, material_id: int, precio_centavos: int, vigente_desde: datetime,
           *, proveedor_id: int | None = None, fuente: str = "manual", request=None) -> dict | None:
    """Carga y audita en la transacción del llamador. Devuelve None si algún ID es ajeno."""
    empresa_id = usuario["empresa_id"]
    fila = db.execute(
        """INSERT INTO precios(empresa_id,material_id,proveedor_id,precio_centavos,vigente_desde,fuente,cargado_por)
           SELECT m.empresa_id, m.id, %s, %s, %s, %s, %s
             FROM materiales m
            WHERE m.empresa_id=%s AND m.id=%s
              AND (%s::bigint IS NULL OR EXISTS (
                   SELECT 1 FROM proveedores p WHERE p.empresa_id=m.empresa_id AND p.id=%s))
           RETURNING id""",
        (proveedor_id, precio_centavos, vigente_desde, fuente, usuario["id"],
         empresa_id, material_id, proveedor_id, proveedor_id),
    ).fetchone()
    if fila:
        auditoria.registrar(db, usuario, "precio.cargado", objeto="precio", objeto_id=fila["id"],
                            detalle={"material_id": material_id, "fuente": fuente}, request=request)
    return fila
