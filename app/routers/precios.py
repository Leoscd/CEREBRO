"""Catálogo interno de materiales, proveedores y precios."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.db import db_dependency
from app.formularios import id_opcional
from app.permisos import es_cliente, exigir, puede_gestionar_precios
from app.security import check_csrf, require_user
from app.services import apus, auditoria, dinero, excel, precios
from app.services.tiempo import TZ, hoy_local
from app.templates import templates

router = APIRouter(prefix="/precios")


def _personal(user=Depends(require_user)):
    if es_cliente(user):
        raise HTTPException(404, "Sección no encontrada")
    return user


def _texto(valor: str, campo: str) -> str:
    valor = valor.strip()
    if not valor:
        raise HTTPException(422, f"Completá {campo}.")
    return valor


@router.get("")
def catalogo(request: Request, user=Depends(_personal), db: Connection = Depends(db_dependency)):
    empresa_id = user["empresa_id"]
    materiales = db.execute(
        """SELECT m.*, v.actual_centavos, v.variacion_pb
             FROM materiales m LEFT JOIN LATERAL (
                SELECT actual_centavos, variacion_pb FROM v_cambios_precio
                 WHERE empresa_id=m.empresa_id AND material_id=m.id AND vigente_desde<=now()
                 ORDER BY vigente_desde DESC, id DESC LIMIT 1
             ) v ON true
            WHERE m.empresa_id=%s ORDER BY m.codigo""", (empresa_id,),
    ).fetchall()
    indices = db.execute(
        "SELECT nombre, periodo, valor FROM indices_costo WHERE empresa_id=%s ORDER BY periodo DESC, nombre",
        (empresa_id,),
    ).fetchall()
    return templates.TemplateResponse(request, "precios/catalogo.html", {
        "user": user, "materiales": materiales, "indices": indices, "editar": puede_gestionar_precios(user, db),
    })


@router.post("/materiales")
def alta_material(request: Request, codigo: str = Form(max_length=80), nombre: str = Form(max_length=240),
                  unidad: str = Form(max_length=40), tipo: Literal["material", "mano_obra", "equipo"] = Form(),
                  rubro: str = Form("", max_length=120), user=Depends(check_csrf),
                  db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        material = db.execute(
            """INSERT INTO materiales(empresa_id,codigo,nombre,unidad,tipo,rubro)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (user["empresa_id"], _texto(codigo, "el código"), _texto(nombre, "el nombre"),
             _texto(unidad, "la unidad"), tipo, rubro.strip()),
        ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(409, "Ya existe un material con ese código.") from exc
    auditoria.registrar(db, user, "material.creado", objeto="material", objeto_id=material["id"], request=request)
    db.commit()
    return RedirectResponse(f"/precios/materiales/{material['id']}", 303)


@router.get("/materiales/{material_id}")
def historial(request: Request, material_id: int, user=Depends(_personal), db: Connection = Depends(db_dependency)):
    empresa_id = user["empresa_id"]
    material = db.execute("SELECT * FROM materiales WHERE empresa_id=%s AND id=%s", (empresa_id, material_id)).fetchone()
    if not material:
        raise HTTPException(404, "Material no encontrado")
    filas = db.execute(
        """SELECT v.*, p.nombre AS proveedor FROM v_cambios_precio v
             LEFT JOIN proveedores p ON p.id=v.proveedor_id AND p.empresa_id=v.empresa_id
            WHERE v.empresa_id=%s AND v.material_id=%s ORDER BY v.vigente_desde DESC, v.id DESC""",
        (empresa_id, material_id),
    ).fetchall()
    proveedores = db.execute(
        "SELECT id,nombre FROM proveedores WHERE empresa_id=%s AND activo ORDER BY nombre,id", (empresa_id,),
    ).fetchall()
    return templates.TemplateResponse(request, "precios/historial.html", {
        "user": user, "material": material, "filas": filas, "proveedores": proveedores,
        "editar": puede_gestionar_precios(user, db),
    })


@router.post("/materiales/{material_id}/precios")
def cargar_precio(request: Request, material_id: int, precio: str = Form(max_length=64),
                  vigente_desde: date = Form(), proveedor_id: str = Form(""),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        centavos = dinero.leer_pesos(precio)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not 0 < centavos <= 2**63 - 1:
        raise HTTPException(422, "El precio debe ser positivo y caber en el catálogo.")
    fecha = datetime.combine(vigente_desde, time.min, TZ)
    proveedor = id_opcional(proveedor_id, "el proveedor")
    if not precios.cargar(db, user, material_id, centavos, fecha, proveedor_id=proveedor, request=request):
        raise HTTPException(404, "Material o proveedor no encontrado")
    db.commit()
    return RedirectResponse(f"/precios/materiales/{material_id}", 303)


@router.get("/proveedores")
def listar_proveedores(request: Request, user=Depends(_personal), db: Connection = Depends(db_dependency)):
    filas = db.execute(
        "SELECT nombre,cuit,contacto,activo FROM proveedores WHERE empresa_id=%s ORDER BY nombre,id",
        (user["empresa_id"],),
    ).fetchall()
    return templates.TemplateResponse(request, "precios/proveedores.html", {
        "user": user, "proveedores": filas, "editar": puede_gestionar_precios(user, db),
    })


@router.post("/proveedores")
def alta_proveedor(request: Request, nombre: str = Form(max_length=240), cuit: str = Form("", max_length=25),
                   contacto: str = Form("", max_length=240), user=Depends(check_csrf),
                   db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    proveedor = db.execute(
        "INSERT INTO proveedores(empresa_id,nombre,cuit,contacto) VALUES (%s,%s,%s,%s) RETURNING id",
        (user["empresa_id"], _texto(nombre, "el nombre"), cuit.strip(), contacto.strip()),
    ).fetchone()
    auditoria.registrar(db, user, "proveedor.creado", objeto="proveedor", objeto_id=proveedor["id"], request=request)
    db.commit()
    return RedirectResponse("/precios/proveedores", 303)


def _apu(db: Connection, empresa_id: int, apu_id: int) -> dict:
    fila = db.execute("SELECT * FROM apus WHERE empresa_id=%s AND id=%s", (empresa_id, apu_id)).fetchone()
    if not fila:
        raise HTTPException(404, "APU no encontrado")
    return fila


@router.get("/apus")
def lista_apus(request: Request, user=Depends(_personal), db: Connection = Depends(db_dependency)):
    empresa_id = user["empresa_id"]
    filas = db.execute(
        "SELECT id,codigo,descripcion,unidad,activo FROM apus WHERE empresa_id=%s ORDER BY codigo",
        (empresa_id,),
    ).fetchall()
    hoy = hoy_local()
    for fila in filas:
        fila["calculo"] = apus.precio_unitario(db, empresa_id, fila["id"], hoy)
    return templates.TemplateResponse(request, "precios/apus.html", {
        "user": user, "filas": filas, "editar": puede_gestionar_precios(user, db),
    })


@router.get("/apus/{apu_id}")
def detalle_apu(request: Request, apu_id: int, user=Depends(_personal), db: Connection = Depends(db_dependency)):
    empresa_id = user["empresa_id"]
    apu = _apu(db, empresa_id, apu_id)
    materiales = db.execute(
        "SELECT id,codigo,nombre FROM materiales WHERE empresa_id=%s AND activo ORDER BY codigo", (empresa_id,),
    ).fetchall()
    return templates.TemplateResponse(request, "precios/apu.html", {
        "user": user, "apu": apu, "calculo": apus.precio_unitario(db, empresa_id, apu_id, hoy_local()),
        "materiales": materiales, "editar": puede_gestionar_precios(user, db),
    })


@router.post("/apus")
def alta_apu(request: Request, codigo: str = Form(max_length=80), descripcion: str = Form(max_length=240),
             unidad: str = Form(max_length=40), rubro: str = Form("", max_length=120),
             user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        fila = db.execute(
            "INSERT INTO apus(empresa_id,codigo,descripcion,unidad,rubro) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (user["empresa_id"], _texto(codigo, "el código"), _texto(descripcion, "la descripción"),
             _texto(unidad, "la unidad"), rubro.strip()),
        ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(409, "Ya existe un APU con ese código.") from exc
    auditoria.registrar(db, user, "apu.creado", objeto="apu", objeto_id=fila["id"], request=request)
    db.commit()
    return RedirectResponse(f"/precios/apus/{fila['id']}", 303)


@router.post("/apus/{apu_id}/editar")
def editar_apu(request: Request, apu_id: int, codigo: str = Form(max_length=80),
               descripcion: str = Form(max_length=240), unidad: str = Form(max_length=40),
               rubro: str = Form("", max_length=120), activo: bool = Form(False),
               user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        fila = db.execute(
            """UPDATE apus SET codigo=%s,descripcion=%s,unidad=%s,rubro=%s,activo=%s
                WHERE empresa_id=%s AND id=%s RETURNING id""",
            (_texto(codigo, "el código"), _texto(descripcion, "la descripción"), _texto(unidad, "la unidad"),
             rubro.strip(), activo, user["empresa_id"], apu_id),
        ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(409, "Ya existe un APU con ese código.") from exc
    if not fila:
        raise HTTPException(404, "APU no encontrado")
    auditoria.registrar(db, user, "apu.editado", objeto="apu", objeto_id=apu_id, request=request)
    db.commit()
    return RedirectResponse(f"/precios/apus/{apu_id}", 303)


@router.post("/apus/{apu_id}/insumos")
def guardar_insumo(request: Request, apu_id: int, material_id: int = Form(gt=0, le=2**63-1),
                   cantidad: Decimal = Form(gt=0, max_digits=14, decimal_places=4),
                   desperdicio_pb: int = Form(0, ge=0, le=2**31-1),
                   user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    empresa_id = user["empresa_id"]
    fila = db.execute(
        """INSERT INTO apu_insumos(empresa_id,apu_id,material_id,cantidad,desperdicio_pb)
           SELECT a.empresa_id,a.id,m.id,%s,%s FROM apus a
             JOIN materiales m ON m.empresa_id=a.empresa_id AND m.id=%s
            WHERE a.empresa_id=%s AND a.id=%s
           ON CONFLICT (empresa_id,apu_id,material_id)
           DO UPDATE SET cantidad=excluded.cantidad, desperdicio_pb=excluded.desperdicio_pb RETURNING apu_id""",
        (cantidad, desperdicio_pb, material_id, empresa_id, apu_id),
    ).fetchone()
    if not fila:
        raise HTTPException(404, "APU o insumo no encontrado")
    auditoria.registrar(db, user, "apu.insumo_guardado", objeto="apu", objeto_id=apu_id,
                        detalle={"material_id": material_id}, request=request)
    db.commit()
    return RedirectResponse(f"/precios/apus/{apu_id}", 303)


@router.post("/apus/{apu_id}/insumos/{material_id}/quitar")
def quitar_insumo(request: Request, apu_id: int, material_id: int,
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    fila = db.execute(
        "DELETE FROM apu_insumos WHERE empresa_id=%s AND apu_id=%s AND material_id=%s RETURNING apu_id",
        (user["empresa_id"], apu_id, material_id),
    ).fetchone()
    if not fila:
        raise HTTPException(404, "Insumo no encontrado")
    auditoria.registrar(db, user, "apu.insumo_quitado", objeto="apu", objeto_id=apu_id,
                        detalle={"material_id": material_id}, request=request)
    db.commit()
    return RedirectResponse(f"/precios/apus/{apu_id}", 303)


@router.get("/excel/plantilla.xlsx")
def plantilla_precios_excel(user=Depends(_personal)):
    return Response(
        excel.plantilla(excel.COLUMNAS_PRECIOS), media_type=excel.TIPO_EXCEL,
        headers={"Content-Disposition": 'attachment; filename="plantilla-precios.xlsx"'},
    )


@router.post("/excel/vista-previa")
def vista_previa_precios_excel(request: Request, archivo: UploadFile = File(), user=Depends(check_csrf),
                              db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        contenido = excel.subir(archivo)
        filas = excel.filas_precios(db, user["empresa_id"], contenido)
    except excel.ExcelInvalido as error:
        raise HTTPException(error.estado, str(error)) from error
    confirmacion = None if any("error" in f for f in filas) else excel.firmar(contenido, user, "/precios", filas)
    return templates.TemplateResponse(request, "excel_previa.html", {
        "user": user, "filas": filas, "destino": "/precios", "confirmacion": confirmacion, "titulo": "Importar precios",
    }, headers={"Cache-Control": "private, no-store"})


@router.post("/excel/confirmar")
def confirmar_precios_excel(request: Request, confirmacion: str = Form(max_length=excel.MAX_CONFIRMACION),
                            user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        contenido, huella = excel.abrir_confirmacion(confirmacion, user, "/precios")
        filas = excel.filas_precios(db, user["empresa_id"], contenido)
        excel.comprobar_filas(filas, huella)
    except excel.ExcelInvalido as error:
        raise HTTPException(error.estado, str(error)) from error
    if any("error" in f for f in filas):
        return templates.TemplateResponse(request, "excel_previa.html", {
            "user": user, "filas": filas, "destino": "/precios", "confirmacion": None, "titulo": "Importar precios",
        }, status_code=409, headers={"Cache-Control": "private, no-store"})
    for fila in filas:
        datos = fila["datos"]
        if not precios.cargar(db, user, datos["material_id"], datos["precio_centavos"], datos["vigente_desde"],
                             proveedor_id=datos["proveedor_id"], fuente="excel", request=request):
            raise HTTPException(409, f"Fila {fila['numero']}: material o proveedor no disponible.")
    db.commit()
    return RedirectResponse("/precios", 303)
