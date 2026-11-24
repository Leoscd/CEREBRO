"""Pedidos, stock y alertas de materiales para las próximas tareas."""

from fastapi import HTTPException

from app import config
from app.services import auditoria, cronograma

ESTADOS = ("pendiente", "pedido", "recibido", "no_aplica")
_NIVELES = {"critico": 0, "rojo": 1, "amarillo": 2, "verde": 3}


def stock(db, proyecto, hoy):
    return db.execute(
        """WITH aplicable AS (
                SELECT * FROM stock_obra WHERE empresa_id=%s AND proyecto_id=%s AND fecha<=%s
             ), ultimos AS (
                SELECT DISTINCT ON (material_clave,unidad_clave) * FROM aplicable
                 ORDER BY material_clave,unidad_clave,fecha DESC,id DESC
             ), conteos AS (
                SELECT DISTINCT ON (material_clave,unidad_clave) * FROM aplicable WHERE reporte_id IS NULL
                 ORDER BY material_clave,unidad_clave,fecha DESC,id DESC
             )
             SELECT u.material,u.unidad,u.fecha,u.material_clave,u.unidad_clave,
                    coalesce(c.cantidad,0)+coalesce(i.cantidad,0) AS cantidad
               FROM ultimos u LEFT JOIN conteos c USING(material_clave,unidad_clave)
               LEFT JOIN LATERAL (
                    SELECT sum(a.cantidad) AS cantidad FROM aplicable a
                     WHERE a.material_clave=u.material_clave AND a.unidad_clave=u.unidad_clave
                       AND a.reporte_id IS NOT NULL AND (c.id IS NULL OR (a.fecha,a.id)>(c.fecha,c.id))
               ) i ON true ORDER BY u.material_clave,u.unidad_clave""",
        (proyecto["empresa_id"], proyecto["id"], hoy),
    ).fetchall()


def declarar_stock(db, usuario, proyecto, material, unidad, fecha, cantidad, *, request=None):
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    db.execute("SELECT id FROM proyectos WHERE empresa_id=%s AND id=%s FOR NO KEY UPDATE", (empresa, pid))
    registro = db.execute(
        """INSERT INTO stock_obra(empresa_id,proyecto_id,material,unidad,fecha,cantidad)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (empresa, pid, material, unidad, fecha, cantidad),
    ).fetchone()
    auditoria.registrar(db, usuario, "obra.stock_declarado", proyecto_id=pid, objeto="stock_obra",
                        objeto_id=registro["id"], request=request)


def materiales_planificados(db, proyecto):
    return db.execute(
        """SELECT m.id AS material_id,m.tarea_id,m.nombre AS material,m.cantidad,m.unidad,m.plazo_dias,
                   t.codigo,t.nombre AS tarea,t.inicio,t.critica,
                   clave_stock_obra(m.nombre) AS material_clave,clave_stock_obra(m.unidad) AS unidad_clave,
                   p.id AS pedido_id,p.estado,p.fecha,p.fecha_entrega
             FROM materiales_tarea m JOIN tareas_obra t
                  ON t.empresa_id=m.empresa_id AND t.proyecto_id=m.proyecto_id AND t.id=m.tarea_id
             LEFT JOIN pedidos_material p
                  ON p.empresa_id=m.empresa_id AND p.proyecto_id=m.proyecto_id AND p.tarea_id=m.tarea_id
                  AND p.material=m.nombre
            WHERE m.empresa_id=%s AND m.proyecto_id=%s
            ORDER BY t.inicio,t.codigo,m.nombre""",
        (proyecto["empresa_id"], proyecto["id"]),
    ).fetchall()


def guardar_pedido(db, usuario, proyecto, material_id, estado, fecha, entrega, *, request=None):
    if estado not in ESTADOS or (entrega is not None and entrega < fecha):
        raise HTTPException(400, "Revisá el estado y las fechas del pedido.")
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    pedido = db.execute(
        """INSERT INTO pedidos_material(empresa_id,proyecto_id,tarea_id,material,estado,fecha,fecha_entrega)
           SELECT empresa_id,proyecto_id,tarea_id,nombre,%s,%s,%s FROM materiales_tarea
            WHERE empresa_id=%s AND proyecto_id=%s AND id=%s
           ON CONFLICT (empresa_id,proyecto_id,tarea_id,material)
           DO UPDATE SET estado=EXCLUDED.estado,fecha=EXCLUDED.fecha,fecha_entrega=EXCLUDED.fecha_entrega
           RETURNING id""", (estado, fecha, entrega, empresa, pid, material_id),
    ).fetchone()
    if pedido is None:
        raise HTTPException(404, "Material no encontrado en la obra.")
    auditoria.registrar(db, usuario, "obra.pedido_actualizado", proyecto_id=pid, objeto="pedido_material",
                        objeto_id=pedido["id"], detalle={"estado": estado}, request=request)
    return pedido["id"]


def pedidos(db, proyecto, hoy):
    grupos = {estado: [] for estado in ESTADOS}
    for material in materiales_planificados(db, proyecto):
        if material["estado"]:
            material["entrega_vencida"] = bool(material["estado"] == "pedido" and material["fecha_entrega"]
                                               and material["fecha_entrega"] < hoy)
            grupos[material["estado"]].append(material)
    return grupos


def _nivel(dias, critica):
    if dias > 7:
        return "verde"
    if dias >= 0:
        return "amarillo"
    return "critico" if critica else "rojo"


def alertas(db, proyecto, hoy):
    calendario = cronograma.calendario(db, proyecto["empresa_id"])
    saldos = {(s["material_clave"], s["unidad_clave"]): s["cantidad"] for s in stock(db, proyecto, hoy)}
    resultado = []
    for material in materiales_planificados(db, proyecto):
        if material["inicio"] <= hoy or material["estado"] in {"pedido", "recibido", "no_aplica"}:
            continue
        cantidad = saldos.get((material["material_clave"], material["unidad_clave"]))
        if cantidad is not None and cantidad >= material["cantidad"]:
            continue
        plazo = material["plazo_dias"] + max(0, config.MARGEN_PEDIDO_DIAS)
        limite = calendario.restar_habiles(material["inicio"], plazo)
        dias = (limite - hoy).days
        resultado.append({**material, "fecha_limite": limite, "dias_para_limite": dias,
                          "nivel": _nivel(dias, material["critica"]), "stock_declarado": cantidad})
    return sorted(resultado, key=lambda a: (_NIVELES[a["nivel"]], a["fecha_limite"], a["material_id"]))
