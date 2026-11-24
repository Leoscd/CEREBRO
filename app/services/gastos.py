"""Gastos reales y sus comprobantes dentro de un proyecto."""

from fastapi import HTTPException

from app.permisos import obtener_archivo
from app.services import auditoria


def listar(db, empresa_id, proyecto_id):
    return db.execute(
        """SELECT g.*,p.nombre AS proveedor,a.nombre AS comprobante FROM gastos g
             LEFT JOIN proveedores p ON p.empresa_id=g.empresa_id AND p.id=g.proveedor_id
             LEFT JOIN archivos a ON a.empresa_id=g.empresa_id AND a.proyecto_id=g.proyecto_id
                                AND a.id=g.archivo_id AND a.en_papelera_en IS NULL
            WHERE g.empresa_id=%s AND g.proyecto_id=%s ORDER BY g.fecha DESC,g.id DESC""",
        (empresa_id, proyecto_id),
    ).fetchall()


def registrar(db, usuario, proyecto, fecha, descripcion, importe_centavos, *,
              proveedor_id=None, rubro="", archivo_id=None, request=None):
    empresa = usuario["empresa_id"]
    pid = proyecto["id"]
    if archivo_id is not None and obtener_archivo(db, usuario, archivo_id)["proyecto_id"] != pid:
        raise HTTPException(404, "Comprobante no encontrado")
    if proveedor_id is not None and not db.execute(
        "SELECT 1 FROM proveedores WHERE empresa_id=%s AND id=%s", (empresa, proveedor_id),
    ).fetchone():
        raise HTTPException(404, "Proveedor no encontrado")
    fila = db.execute(
        """INSERT INTO gastos(empresa_id,proyecto_id,fecha,descripcion,importe_centavos,proveedor_id,rubro,archivo_id,cargado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (empresa, pid, fecha, descripcion, importe_centavos, proveedor_id, rubro, archivo_id, usuario["id"]),
    ).fetchone()
    auditoria.registrar(db, usuario, "gasto.registrado", proyecto_id=pid, objeto="gasto", objeto_id=fila["id"],
                        request=request)
    return fila["id"]
