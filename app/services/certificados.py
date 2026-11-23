"""Certificación incremental de los subtotales congelados al emitir un presupuesto."""

from fastapi import HTTPException

from app.services import auditoria, dinero


def exigir_emitido(presupuesto):
    if presupuesto["estado"] != "emitido":
        raise HTTPException(409, "Solo se puede certificar un presupuesto emitido.")


def _lineas(db, empresa_id, presupuesto_id, numero, certificado_id=None):
    return db.execute(
        """WITH anterior AS (
            SELECT id FROM certificados WHERE empresa_id=%s AND presupuesto_id=%s AND estado='emitido' AND numero<%s
                ORDER BY numero DESC LIMIT 1
        )
        SELECT i.id,i.descripcion,i.unidad,i.cantidad,i.precio_emitido_centavos,
               coalesce(a.avance_pb,0) AS anterior_pb, d.avance_pb
          FROM items_presupuesto i JOIN rubros_presupuesto r
            ON (r.empresa_id,r.presupuesto_id,r.id)=(i.empresa_id,i.presupuesto_id,i.rubro_id)
          LEFT JOIN certificado_items a ON a.empresa_id=i.empresa_id AND a.presupuesto_id=i.presupuesto_id
                   AND a.item_presupuesto_id=i.id AND a.certificado_id=(SELECT id FROM anterior)
          LEFT JOIN certificado_items d ON d.empresa_id=i.empresa_id AND d.presupuesto_id=i.presupuesto_id
                   AND d.item_presupuesto_id=i.id AND d.certificado_id=%s
         WHERE i.empresa_id=%s AND i.presupuesto_id=%s ORDER BY r.orden,r.id,i.orden,i.id""",
        (empresa_id, presupuesto_id, numero, certificado_id, empresa_id, presupuesto_id),
    ).fetchall()


def _con_montos(filas):
    for fila in filas:
        precio = fila["precio_emitido_centavos"]
        if precio is None:
            raise HTTPException(409, "El presupuesto necesita ítems con precio emitido.")
        if fila["avance_pb"] is None:
            fila["avance_pb"] = fila["anterior_pb"]
        subtotal = dinero.multiplicar(precio, fila["cantidad"])
        fila["certificado_centavos"] = dinero.aplicar_coeficiente(subtotal, fila["avance_pb"] - fila["anterior_pb"])
    return dinero.sumar(fila["certificado_centavos"] for fila in filas)


def listar(db, empresa_id, presupuesto_id):
    filas = db.execute(
        "SELECT * FROM certificados WHERE empresa_id=%s AND presupuesto_id=%s ORDER BY numero",
        (empresa_id, presupuesto_id),
    ).fetchall()
    for c in filas:
        items = _lineas(db, empresa_id, presupuesto_id, c["numero"], c["id"])
        c["items"] = items
        c["total_centavos"] = _con_montos(items)
    return filas


def avances_base(db, empresa_id, presupuesto_id):
    return _lineas(db, empresa_id, presupuesto_id, 2**31)


def crear(db, usuario, presupuesto, periodo, avances, *, request=None):
    """Agrega un borrador con el presupuesto padre bloqueado por el llamador."""
    exigir_emitido(presupuesto)
    empresa, pid = usuario["empresa_id"], presupuesto["id"]
    anterior = db.execute(
        "SELECT numero,estado,periodo FROM certificados WHERE empresa_id=%s AND presupuesto_id=%s ORDER BY numero DESC LIMIT 1",
        (empresa, pid),
    ).fetchone()
    if anterior and anterior["estado"] == "borrador":
        raise HTTPException(409, "Emití el borrador pendiente antes de crear otro certificado.")
    if anterior and periodo < anterior["periodo"]:
        raise HTTPException(400, "El período no puede ser anterior al último certificado.")
    numero = anterior["numero"] + 1 if anterior else 1
    filas = _lineas(db, empresa, pid, numero)
    if avances.keys() - {f["id"] for f in filas}:
        raise HTTPException(404, "Ítem no encontrado en este presupuesto.")
    if not filas or any(f["precio_emitido_centavos"] is None for f in filas):
        raise HTTPException(409, "El presupuesto necesita ítems con precio emitido.")
    for fila in filas:
        avance = avances.get(fila["id"], fila["anterior_pb"])
        if not fila["anterior_pb"] <= avance <= 10000:
            raise HTTPException(400, f"El avance de «{fila['descripcion']}» debe estar entre el anterior y 100 %.")
        fila["avance_pb"] = avance
    cid = db.execute(
        "INSERT INTO certificados(empresa_id,presupuesto_id,numero,periodo) VALUES (%s,%s,%s,%s) RETURNING id",
        (empresa, pid, numero, periodo),
    ).fetchone()["id"]
    for fila in filas:
        db.execute(
            """INSERT INTO certificado_items(empresa_id,presupuesto_id,certificado_id,item_presupuesto_id,avance_pb)
               VALUES (%s,%s,%s,%s,%s)""", (empresa, pid, cid, fila["id"], fila["avance_pb"]),
        )
    auditoria.registrar(db, usuario, "certificado.creado", proyecto_id=presupuesto["proyecto_id"],
                        objeto="certificado", objeto_id=cid, request=request)
    return cid


def emitir(db, usuario, presupuesto, certificado_id, *, request=None):
    exigir_emitido(presupuesto)
    ids = (usuario["empresa_id"], presupuesto["id"], certificado_id)
    certificado = db.execute(
        "SELECT estado FROM certificados WHERE empresa_id=%s AND presupuesto_id=%s AND id=%s FOR UPDATE", ids,
    ).fetchone()
    if not certificado:
        raise HTTPException(404, "Certificado no encontrado")
    if certificado["estado"] != "borrador":
        raise HTTPException(409, "El certificado ya fue emitido.")
    db.execute("UPDATE certificados SET estado='emitido' WHERE empresa_id=%s AND presupuesto_id=%s AND id=%s", ids)
    auditoria.registrar(db, usuario, "certificado.emitido", proyecto_id=presupuesto["proyecto_id"],
                        objeto="certificado", objeto_id=certificado_id, request=request)
