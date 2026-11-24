"""Cronograma y seguimiento de obra por proyecto."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.db import db_dependency
from app.permisos import es_cliente, exigir, obtener_proyecto, puede_registrar_obra
from app.routers.presupuestos import _texto
from app.security import check_csrf, require_user
from app.services import auditoria, cronograma, excel
from app.services.tiempo import hoy_local
from app.templates import templates

router = APIRouter(prefix="/proyecto/{codigo}/obra")


def _obra(db, user, codigo):
    if es_cliente(user):
        raise HTTPException(404, "Obra no encontrada.")
    return obtener_proyecto(db, user, codigo)


def _editar_obra(db, user, codigo):
    proyecto = _obra(db, user, codigo)
    exigir(puede_registrar_obra(user, proyecto))
    return proyecto


def _bloquear_proyecto(db, proyecto):
    db.execute("SELECT id FROM proyectos WHERE empresa_id=%s AND id=%s FOR UPDATE",
               (proyecto["empresa_id"], proyecto["id"])).fetchone()


def _ruta(proyecto):
    return f"/proyecto/{proyecto['codigo']}/obra"


def _auditar(db, user, proyecto, accion, objeto, objeto_id, request, detalle=None):
    auditoria.registrar(db, user, accion, proyecto_id=proyecto["id"], objeto=objeto,
                        objeto_id=objeto_id, request=request, detalle=detalle)


@router.get("")
def tablero(codigo: str, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = _obra(db, user, codigo)
    hoy = hoy_local()
    editar = puede_registrar_obra(user, proyecto)
    return templates.TemplateResponse(request, "obra/cronograma.html", {
        "user": user, "proyecto": proyecto, "hoy": hoy, "ruta": _ruta(proyecto), "editar": editar,
        "obra": cronograma.avance_obra(db, proyecto, hoy),
        "items": cronograma.items_emitidos(db, proyecto) if editar else [],
    })


@router.post("/tareas")
def alta_tarea(codigo: str, request: Request, clave: str = Form(max_length=80), nombre: str = Form(max_length=240),
               rubro: str = Form("", max_length=120), inicio: date = Form(), fin: date = Form(),
               critica: bool = Form(False), item: str = Form("", max_length=20),
               user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    try:
        item_id = cronograma._entero(item, 1, 2**63 - 1) if item.strip() else None
    except ValueError as error:
        raise HTTPException(400, "Ingresá un ítem de presupuesto válido.") from error
    _bloquear_proyecto(db, proyecto)
    tarea_id = cronograma.crear_tarea(db, proyecto, {
        "codigo": _texto(clave, "el código"), "nombre": _texto(nombre, "la tarea"), "rubro": rubro.strip(),
        "inicio": inicio, "fin": fin, "critica": critica, "item_presupuesto_id": item_id,
    })
    _auditar(db, user, proyecto, "obra.tarea_creada", "tarea_obra", tarea_id, request)
    db.commit()
    return RedirectResponse(_ruta(proyecto), 303)


@router.post("/tareas/{tarea_id}/avance")
def guardar_avance(codigo: str, tarea_id: int, request: Request, fecha: date = Form(),
                   avance_pb: int = Form(ge=0, le=10000), user=Depends(check_csrf),
                   db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    cronograma.registrar_avance(db, user, proyecto, tarea_id, fecha, avance_pb, request=request)
    db.commit()
    return RedirectResponse(_ruta(proyecto), 303)


@router.post("/tareas/{tarea_id}/materiales")
def registrar_material(codigo: str, tarea_id: int, request: Request, nombre: str = Form(max_length=200),
                       cantidad: Decimal = Form(gt=0, max_digits=14, decimal_places=4),
                       unidad: str = Form(max_length=40), plazo_dias: int = Form(ge=0, le=3650),
                       user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    material = _texto(nombre, "el material")
    cronograma.agregar_material(db, proyecto, tarea_id, {
        "nombre": material, "cantidad": cantidad, "unidad": _texto(unidad, "la unidad"), "plazo_dias": plazo_dias,
    })
    _auditar(db, user, proyecto, "obra.material_requerido", "tarea_obra", tarea_id, request, {"material": material})
    db.commit()
    return RedirectResponse(_ruta(proyecto), 303)


@router.post("/feriados")
def alta_feriado(codigo: str, request: Request, fecha: date = Form(), nombre: str = Form(max_length=200),
                 user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    try:
        db.execute("INSERT INTO feriados(empresa_id,fecha,nombre) VALUES (%s,%s,%s)",
                   (user["empresa_id"], fecha, _texto(nombre, "el nombre del feriado")))
    except UniqueViolation as error:
        raise HTTPException(409, "Ya hay un feriado en esa fecha.") from error
    _auditar(db, user, proyecto, "obra.feriado_creado", "feriado", fecha.isoformat(), request)
    db.commit()
    return RedirectResponse(_ruta(proyecto), 303)


@router.get("/excel/plantilla.xlsx")
def plantilla_cronograma(codigo: str, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    _editar_obra(db, user, codigo)
    return Response(excel.plantilla(cronograma.COLUMNAS), media_type=excel.TIPO_EXCEL,
                    headers={"Content-Disposition": 'attachment; filename="plantilla-cronograma.xlsx"'})


def _vista_cronograma(request, user, destino, filas, token, estado=200):
    return templates.TemplateResponse(request, "obra/cronograma_previa.html", {
        "user": user, "destino": destino, "filas": filas, "confirmacion": token,
    }, status_code=estado, headers={"Cache-Control": "private, no-store"})


@router.post("/excel/vista-previa")
def previa_cronograma(codigo: str, request: Request, archivo: UploadFile = File(),
                     user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    destino = _ruta(proyecto)
    try:
        contenido = excel.subir(archivo)
        filas = cronograma.planilla(db, proyecto, contenido)
    except excel.ExcelInvalido as error:
        raise HTTPException(error.estado, str(error)) from error
    token = None if any("error" in f for f in filas) else excel.firmar(contenido, user, destino, filas)
    return _vista_cronograma(request, user, destino, filas, token)


@router.post("/excel/confirmar")
def confirmar_cronograma(codigo: str, request: Request, confirmacion: str = Form(max_length=excel.MAX_CONFIRMACION),
                         user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    _bloquear_proyecto(db, proyecto)
    destino = _ruta(proyecto)
    try:
        contenido, huella = excel.abrir_confirmacion(confirmacion, user, destino)
        filas = cronograma.planilla(db, proyecto, contenido)
        excel.comprobar_filas(filas, huella)
    except excel.ExcelInvalido as error:
        raise HTTPException(error.estado, str(error)) from error
    if any("error" in f for f in filas):
        return _vista_cronograma(request, user, destino, filas, None, 409)
    tareas = {}
    for fila in filas:
        datos = fila["datos"]
        tarea = datos["tarea"]
        if tarea["codigo"] not in tareas:
            tid = cronograma.crear_tarea(db, proyecto, tarea)
            tareas[tarea["codigo"]] = tid
            _auditar(db, user, proyecto, "obra.tarea_creada", "tarea_obra", tid, request, {"origen": "excel"})
        if datos["material"]:
            cronograma.agregar_material(db, proyecto, tareas[tarea["codigo"]], datos["material"])
    db.commit()
    return RedirectResponse(destino, 303)
