"""Órdenes de servicio y notas de pedido numeradas por obra y tipo."""

from fastapi import HTTPException

from app.services import auditoria, partes

TIPOS = {"orden_servicio": "Orden de servicio", "nota_pedido": "Nota de pedido"}
ESTADOS = ("abierta", "respondida", "cerrada")


def listar(db, proyecto, hoy):
    return db.execute(
        """SELECT n.*,n.plazo-%s AS dias_plazo,coalesce(n.estado='abierta' AND n.plazo<%s,false) AS vencida
             FROM notas_obra n WHERE n.empresa_id=%s AND n.proyecto_id=%s ORDER BY n.fecha DESC,n.id DESC""",
        (hoy, hoy, proyecto["empresa_id"], proyecto["id"]),
    ).fetchall()


def abiertas(db, proyecto, hoy):
    return [n for n in listar(db, proyecto, hoy) if n["estado"] == "abierta"]


def crear(db, usuario, proyecto, datos, *, request=None):
    tipo, fecha, plazo = datos["tipo"], datos["fecha"], datos["plazo"]
    if tipo not in TIPOS or (plazo is not None and plazo < fecha):
        raise HTTPException(400, "Revisá el tipo y el plazo de la nota.")
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    db.execute("SELECT id FROM proyectos WHERE empresa_id=%s AND id=%s FOR NO KEY UPDATE", (empresa, pid))
    if datos["reporte_id"] is not None:
        partes.obtener(db, proyecto, datos["reporte_id"])
    nota = db.execute(
        """INSERT INTO notas_obra(empresa_id,proyecto_id,tipo,numero,fecha,emisor,destinatario,asunto,texto,plazo,reporte_id)
           SELECT %s,%s,%s,coalesce(max(numero),0)+1,%s,%s,%s,%s,%s,%s,%s
             FROM notas_obra WHERE empresa_id=%s AND proyecto_id=%s AND tipo=%s RETURNING id,numero""",
        (empresa, pid, tipo, fecha, datos["emisor"], datos["destinatario"], datos["asunto"], datos["texto"],
         plazo, datos["reporte_id"], empresa, pid, tipo),
    ).fetchone()
    auditoria.registrar(db, usuario, "obra.nota_creada", proyecto_id=pid, objeto="nota_obra", objeto_id=nota["id"],
                        detalle={"tipo": tipo, "numero": nota["numero"]}, request=request)
    return nota["id"]


def cambiar_estado(db, usuario, proyecto, nota_id, estado, *, request=None):
    if estado not in ESTADOS:
        raise HTTPException(400, "Elegí un estado válido para la nota.")
    if not db.execute("UPDATE notas_obra SET estado=%s WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
                      (estado, usuario["empresa_id"], proyecto["id"], nota_id)).rowcount:
        raise HTTPException(404, "Nota no encontrada en la obra.")
    auditoria.registrar(db, usuario, "obra.nota_actualizada", proyecto_id=proyecto["id"], objeto="nota_obra",
                        objeto_id=nota_id, detalle={"estado": estado}, request=request)
