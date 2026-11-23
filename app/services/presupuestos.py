"""Presupuestos por proyecto con cálculo exacto y versiones emitidas congeladas."""

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.services import apus, auditoria, dinero
from app.services.tiempo import TZ


def _valor_item(db, empresa_id, fila, presupuesto, cache):
    if presupuesto["estado"] == "emitido":
        return fila["precio_emitido_centavos"], fila["metadatos_emision"]
    datos = {"unidad_apu": fila["unidad_apu"], "faltantes": [], "fechas_cotizaciones": []}
    apu_id = fila["apu_id"]
    if apu_id is None:
        return fila["precio_unitario_centavos"], datos
    if apu_id not in cache:
        cache[apu_id] = apus.precio_unitario(db, empresa_id, apu_id, presupuesto["fecha_precios"])
    resultado = cache[apu_id]
    datos["faltantes"] = [insumo["nombre"] for insumo in resultado["faltantes"]]
    datos["fechas_cotizaciones"] = [
        cotizacion["vigente_desde"].astimezone(TZ).date().isoformat() for cotizacion in resultado["detalle"]
    ]
    return resultado["total_centavos"] if resultado["detalle"] else None, datos


def calcular(db: Connection, empresa_id: int, presupuesto_id: int) -> dict | None:
    """Valora cada ítem con su PU manual o su APU a fecha. Redondea cada cantidad × PU.

    Suma ítems por rubro y los rubros como costo directo (CD). Aplica GG sobre CD,
    beneficio sobre CD + GG e impuestos sobre CD + GG + beneficio. Redondea cada
    coeficiente por separado y suma los cuatro importes. En emitidos usa los PU congelados.
    """
    p = db.execute(
        "SELECT * FROM presupuestos WHERE empresa_id=%s AND id=%s", (empresa_id, presupuesto_id),
    ).fetchone()
    if p is None:
        return None
    rubros = db.execute(
        """SELECT id,nombre,orden FROM rubros_presupuesto
            WHERE empresa_id=%s AND presupuesto_id=%s ORDER BY orden,id""",
        (empresa_id, presupuesto_id),
    ).fetchall()
    por_id = {r["id"]: r for r in rubros}
    for rubro in rubros:
        rubro["items"] = []
    items = db.execute(
        """SELECT i.*, a.codigo AS codigo_apu, a.unidad AS unidad_apu
             FROM items_presupuesto i LEFT JOIN apus a ON a.empresa_id=i.empresa_id AND a.id=i.apu_id
            WHERE i.empresa_id=%s AND i.presupuesto_id=%s ORDER BY i.orden,i.id""",
        (empresa_id, presupuesto_id),
    ).fetchall()
    cache = {}
    for fila in items:
        unitario, datos = _valor_item(db, empresa_id, fila, p, cache)
        fila.update(datos, unitario_centavos=unitario,
                    subtotal_centavos=None if unitario is None else dinero.multiplicar(unitario, fila["cantidad"]))
        por_id[fila["rubro_id"]]["items"].append(fila)
    for rubro in rubros:
        rubro["subtotal_centavos"] = dinero.sumar(
            i["subtotal_centavos"] for i in rubro["items"] if i["subtotal_centavos"] is not None
        )
    directo = dinero.sumar(r["subtotal_centavos"] for r in rubros)
    gg = dinero.aplicar_coeficiente(directo, p["gastos_generales_pb"])
    beneficio = dinero.aplicar_coeficiente(directo + gg, p["beneficio_pb"])
    impuestos = dinero.aplicar_coeficiente(directo + gg + beneficio, p["impuestos_pb"])
    return {"presupuesto": p, "rubros": rubros, "costo_directo_centavos": directo, "gastos_generales_centavos": gg,
            "beneficio_centavos": beneficio, "impuestos_centavos": impuestos,
            "total_centavos": dinero.sumar((directo, gg, beneficio, impuestos))}


def agregar_rubro(db: Connection, usuario: dict, presupuesto: dict, nombre: str, *, request=None) -> int:
    """Agrega un rubro con el presupuesto bloqueado en la transacción del llamador."""
    ids = (usuario["empresa_id"], presupuesto["id"])
    fila = db.execute(
        """INSERT INTO rubros_presupuesto(empresa_id,presupuesto_id,nombre,orden)
           SELECT %s,%s,%s,coalesce(max(orden),0)+1 FROM rubros_presupuesto
            WHERE empresa_id=%s AND presupuesto_id=%s RETURNING id""",
        (*ids, nombre, *ids),
    ).fetchone()
    auditoria.registrar(db, usuario, "presupuesto.rubro_creado", proyecto_id=presupuesto["proyecto_id"],
                        objeto="rubro_presupuesto", objeto_id=fila["id"], request=request)
    return fila["id"]


def guardar_item(db: Connection, usuario: dict, presupuesto: dict, datos: dict, *,
                 item_id: int | None = None, request=None) -> int | None:
    """Guarda un ítem en el borrador bloqueado. Devuelve None si algún ID queda afuera."""
    ids = (usuario["empresa_id"], presupuesto["id"])
    rubro = datos["rubro_id"]
    apu = datos["apu_id"]
    if not db.execute(
        "SELECT 1 FROM rubros_presupuesto WHERE empresa_id=%s AND presupuesto_id=%s AND id=%s", (*ids, rubro),
    ).fetchone():
        return None
    if apu is not None and not db.execute(
        "SELECT 1 FROM apus WHERE empresa_id=%s AND id=%s", (ids[0], apu),
    ).fetchone():
        return None
    campos = (rubro, datos["descripcion"], datos["unidad"], datos["cantidad"], apu,
              datos["precio_unitario_centavos"], datos["origen_cantidad"])
    if item_id is None:
        fila = db.execute(
            """INSERT INTO items_presupuesto(empresa_id,presupuesto_id,rubro_id,descripcion,unidad,cantidad,
                                             apu_id,precio_unitario_centavos,origen_cantidad,orden)
               SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,coalesce(max(orden),0)+1 FROM items_presupuesto
                WHERE empresa_id=%s AND presupuesto_id=%s AND rubro_id=%s RETURNING id""",
            (*ids, *campos, *ids, rubro),
        ).fetchone()
    else:
        fila = db.execute(
            """UPDATE items_presupuesto
                  SET rubro_id=%s,descripcion=%s,unidad=%s,cantidad=%s,apu_id=%s,
                      precio_unitario_centavos=%s,origen_cantidad=%s
                WHERE empresa_id=%s AND presupuesto_id=%s AND id=%s RETURNING id""",
            (*campos, *ids, item_id),
        ).fetchone()
    if fila:
        accion = "presupuesto.item_creado" if item_id is None else "presupuesto.item_editado"
        auditoria.registrar(db, usuario, accion, proyecto_id=presupuesto["proyecto_id"],
                            objeto="item_presupuesto", objeto_id=fila["id"], request=request)
    return fila["id"] if fila else None


def emitir(db: Connection, usuario: dict, presupuesto: dict, resultado: dict, *, request=None) -> None:
    empresa, pid = usuario["empresa_id"], presupuesto["id"]
    for rubro in resultado["rubros"]:
        for item in rubro["items"]:
            unitario = item["unitario_centavos"]
            if unitario is not None and unitario > 2**63 - 1:
                raise ValueError("Un precio unitario supera el máximo que se puede guardar.")
            datos = {clave: item[clave] for clave in ("unidad_apu", "faltantes", "fechas_cotizaciones")}
            db.execute(
                """UPDATE items_presupuesto SET precio_emitido_centavos=%s,metadatos_emision=%s
                    WHERE empresa_id=%s AND presupuesto_id=%s AND id=%s""",
                (unitario, Jsonb(datos), empresa, pid, item["id"]),
            )
    db.execute(
        "UPDATE presupuestos SET estado='emitido',emitido_en=now() WHERE empresa_id=%s AND id=%s",
        (empresa, pid),
    )
    auditoria.registrar(db, usuario, "presupuesto.emitido", proyecto_id=presupuesto["proyecto_id"],
                        objeto="presupuesto", objeto_id=pid, request=request)


def nueva_version(db: Connection, usuario: dict, presupuesto: dict, *, request=None) -> int:
    empresa, pid, proyecto = usuario["empresa_id"], presupuesto["id"], presupuesto["proyecto_id"]
    raiz = presupuesto["raiz_id"] or pid
    db.execute(
        "SELECT id FROM presupuestos WHERE empresa_id=%s AND proyecto_id=%s AND id=%s FOR UPDATE",
        (empresa, proyecto, raiz),
    ).fetchone()
    version = db.execute(
        """SELECT max(version)+1 AS version FROM presupuestos
            WHERE empresa_id=%s AND proyecto_id=%s AND coalesce(raiz_id,id)=%s""",
        (empresa, proyecto, raiz),
    ).fetchone()["version"]
    nuevo = db.execute(
        """INSERT INTO presupuestos(empresa_id,proyecto_id,raiz_id,nombre,version,fecha_precios,gastos_generales_pb,
                                    beneficio_pb,impuestos_pb,creado_por)
           SELECT empresa_id,proyecto_id,%s,nombre,%s,fecha_precios,gastos_generales_pb,beneficio_pb,impuestos_pb,%s
             FROM presupuestos WHERE empresa_id=%s AND proyecto_id=%s AND id=%s RETURNING id""",
        (raiz, version, usuario["id"], empresa, proyecto, pid),
    ).fetchone()["id"]
    rubros = db.execute(
        "SELECT id,nombre,orden FROM rubros_presupuesto WHERE empresa_id=%s AND presupuesto_id=%s ORDER BY orden,id",
        (empresa, pid),
    ).fetchall()
    for rubro in rubros:
        nuevo_rubro = db.execute(
            "INSERT INTO rubros_presupuesto(empresa_id,presupuesto_id,nombre,orden) VALUES (%s,%s,%s,%s) RETURNING id",
            (empresa, nuevo, rubro["nombre"], rubro["orden"]),
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO items_presupuesto(empresa_id,presupuesto_id,rubro_id,descripcion,unidad,cantidad,
                                             apu_id,precio_unitario_centavos,origen_cantidad,orden)
               SELECT empresa_id,%s,%s,descripcion,unidad,cantidad,apu_id,precio_unitario_centavos,origen_cantidad,orden
                 FROM items_presupuesto WHERE empresa_id=%s AND presupuesto_id=%s AND rubro_id=%s
                ORDER BY orden,id""",
            (nuevo, nuevo_rubro, empresa, pid, rubro["id"]),
        )
    auditoria.registrar(db, usuario, "presupuesto.version_creada", proyecto_id=proyecto,
                        objeto="presupuesto", objeto_id=nuevo, detalle={"origen_id": pid, "version": version},
                        request=request)
    return nuevo
