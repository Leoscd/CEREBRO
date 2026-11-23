"""Análisis de precios unitarios con cotizaciones vigentes a la fecha solicitada."""

from datetime import date, datetime
from decimal import Decimal

from psycopg import Connection

from app.services import dinero, precios


def precio_unitario(db: Connection, empresa_id: int, apu_id: int, a_fecha: date | datetime) -> dict:
    """Redondea cada insumo con su desperdicio y suma solo los que tienen precio vigente."""
    insumos = db.execute(
        """SELECT m.id AS material_id, m.codigo, m.nombre, m.unidad, i.cantidad, i.desperdicio_pb
             FROM apu_insumos i JOIN materiales m ON m.empresa_id=i.empresa_id AND m.id=i.material_id
            WHERE i.empresa_id=%s AND i.apu_id=%s ORDER BY m.codigo, m.id""",
        (empresa_id, apu_id),
    ).fetchall()
    detalle, faltantes = [], []
    for fila in insumos:
        precio = precios.vigente(db, empresa_id, fila["material_id"], a_fecha)
        if precio is None:
            faltantes.append(fila)
            continue
        factor = Decimal(10_000 + fila["desperdicio_pb"]) / 10_000
        detalle.append({
            "insumo": fila, "cantidad": fila["cantidad"], "precio_centavos": precio["precio_centavos"],
            "vigente_desde": precio["vigente_desde"],
            "subtotal_centavos": dinero.multiplicar(precio["precio_centavos"], fila["cantidad"] * factor),
        })
    return {
        "total_centavos": dinero.sumar(fila["subtotal_centavos"] for fila in detalle),
        "detalle": detalle,
        "faltantes": faltantes,
    }
