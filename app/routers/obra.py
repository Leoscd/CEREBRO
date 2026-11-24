"""Cronograma y seguimiento de obra por proyecto."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.db import db_dependency
from app.permisos import es_cliente, exigir, obtener_proyecto, puede_registrar_obra
from app.routers.presupuestos import _texto
from app.security import check_csrf, require_user
from app.services import almacen, auditoria, cronograma, excel, jobs, materiales_obra, notas_obra, partes, transcripcion
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


def _ruta_partes(proyecto):
    return f"{_ruta(proyecto)}/partes"


def _vista_parte(request, db, user, proyecto, parte):
    fotos = partes.fotos(db, proyecto, parte["id"])
    editable = parte["estado"] == "borrador" and puede_registrar_obra(user, proyecto)
    return templates.TemplateResponse(request, "obra/parte.html", {
        "user": user, "proyecto": proyecto, "ruta": _ruta(proyecto), "parte": parte,
        "destino": f"{_ruta_partes(proyecto)}/{parte['id']}", "fotos": fotos,
        "faltantes": partes.faltantes(parte, len(fotos)), "tareas": cronograma.avance_obra(db, proyecto, parte["fecha"])["tareas"],
        "editable": editable, "propuestas_audio": transcripcion.propuestas(db, proyecto, parte["id"]) if editable else [],
    })


@router.get("/partes")
def listado_partes(codigo: str, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = _obra(db, user, codigo)
    return templates.TemplateResponse(request, "obra/partes.html", {
        "user": user, "proyecto": proyecto, "ruta": _ruta(proyecto), "partes": partes.listar(db, proyecto),
        "editar": puede_registrar_obra(user, proyecto),
    })


@router.get("/partes/hoy")
def ver_parte_hoy(codigo: str, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    parte = partes.buscar_dia(db, proyecto, user, hoy_local())
    if parte:
        return _vista_parte(request, db, user, proyecto, parte)
    return templates.TemplateResponse(request, "obra/partes.html", {
        "user": user, "proyecto": proyecto, "ruta": _ruta(proyecto), "partes": partes.listar(db, proyecto), "editar": True,
    })


@router.post("/partes/hoy")
def iniciar_parte(codigo: str, request: Request, user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    parte, nuevo = partes.crear_borrador(db, user, proyecto, hoy_local(), request=request)
    if nuevo:
        jobs.encolar(db, user["empresa_id"], "parte.clima", {"proyecto_id": proyecto["id"], "parte_id": parte["id"]},
                     max_intentos=1)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte['id']}", 303)


@router.get("/partes/{parte_id}")
def ver_parte(codigo: str, parte_id: int, request: Request, user=Depends(require_user),
              db: Connection = Depends(db_dependency)):
    proyecto = _obra(db, user, codigo)
    return _vista_parte(request, db, user, proyecto, partes.obtener(db, proyecto, parte_id))


@router.post("/partes/{parte_id}/secciones/{seccion}")
async def guardar_seccion(codigo: str, parte_id: int, seccion: str, request: Request,
                          user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    partes.actualizar_seccion(db, user, proyecto, parte_id, seccion, await request.form(), request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte_id}#{seccion}", 303)


@router.get("/partes/{parte_id}/fotos/{foto_id}")
def ver_foto(codigo: str, parte_id: int, foto_id: int, user=Depends(require_user),
             db: Connection = Depends(db_dependency)):
    proyecto = _obra(db, user, codigo)
    foto = next((f for f in partes.fotos(db, proyecto, parte_id) if f["id"] == foto_id), None)
    if foto is None or not (blob := almacen.ruta(foto["sha256"])).is_file():
        raise HTTPException(404, "Foto no encontrada.")
    return FileResponse(blob, media_type=foto["mime"], headers={"X-Content-Type-Options": "nosniff"})


@router.post("/partes/{parte_id}/fotos")
def cargar_foto(codigo: str, parte_id: int, request: Request, foto: UploadFile = File(),
                descripcion: str = Form("", max_length=600), tarea_id: str = Form("", max_length=20),
                user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    try:
        tarea = cronograma._entero(tarea_id, 1, 2**63 - 1) if tarea_id.strip() else None
    except ValueError as error:
        raise HTTPException(400, "Elegí una tarea válida.") from error
    partes.agregar_foto(db, user, proyecto, parte_id, foto.file, descripcion.strip(), tarea, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte_id}#fotos", 303)


@router.post("/partes/{parte_id}/fotos/{foto_id}/quitar")
def quitar_foto(codigo: str, parte_id: int, foto_id: int, request: Request, user=Depends(check_csrf),
                db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    partes.quitar_foto(db, user, proyecto, parte_id, foto_id, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte_id}#fotos", 303)


@router.post("/partes/{parte_id}/audios")
def subir_audio(codigo: str, parte_id: int, request: Request, audio: UploadFile = File(),
                user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    transcripcion.cargar(db, user, proyecto, parte_id, audio.file, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte_id}#dictado", 303)


@router.post("/partes/{parte_id}/audios/{audio_id}/aceptar")
def aceptar_audio(codigo: str, parte_id: int, audio_id: int, request: Request, texto: str = Form(max_length=5000),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    transcripcion.aceptar(db, user, proyecto, parte_id, audio_id, texto, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte_id}#resumen", 303)


@router.post("/partes/{parte_id}/confirmar")
def confirmar_parte(codigo: str, parte_id: int, request: Request, user=Depends(check_csrf),
                    db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    partes.confirmar(db, user, proyecto, parte_id, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_partes(proyecto)}/{parte_id}", 303)


def _ruta_seguimiento(proyecto):
    return f"{_ruta(proyecto)}/seguimiento"


@router.get("/seguimiento")
def seguimiento(codigo: str, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = _obra(db, user, codigo)
    hoy = hoy_local()
    return templates.TemplateResponse(request, "obra/seguimiento.html", {
        "user": user, "proyecto": proyecto, "ruta": _ruta(proyecto), "destino": _ruta_seguimiento(proyecto), "hoy": hoy,
        "editar": puede_registrar_obra(user, proyecto), "notas": notas_obra.listar(db, proyecto, hoy),
        "tipos_nota": notas_obra.TIPOS, "estados_nota": notas_obra.ESTADOS,
        "alertas": materiales_obra.alertas(db, proyecto, hoy), "pedidos": materiales_obra.pedidos(db, proyecto, hoy),
        "materiales": materiales_obra.materiales_planificados(db, proyecto), "stock": materiales_obra.stock(db, proyecto, hoy),
        "partes": partes.listar(db, proyecto),
    })


def _fecha_opcional(texto):
    try:
        return date.fromisoformat(texto) if texto.strip() else None
    except ValueError as error:
        raise HTTPException(400, "Ingresá una fecha válida.") from error


@router.post("/seguimiento/notas")
def guardar_nota(codigo: str, request: Request, tipo: str = Form(max_length=24), fecha: date = Form(),
                 emisor: str = Form(max_length=200), destinatario: str = Form(max_length=200),
                 asunto: str = Form(max_length=240), texto: str = Form(max_length=8000),
                 plazo: str = Form("", max_length=10), reporte: str = Form("", max_length=20),
                 user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    try:
        reporte_id = cronograma._entero(reporte, 1, 2**63 - 1) if reporte.strip() else None
    except ValueError as error:
        raise HTTPException(400, "Elegí un parte válido.") from error
    notas_obra.crear(db, user, proyecto, {
        "tipo": tipo, "fecha": fecha, "emisor": _texto(emisor, "el emisor"),
        "destinatario": _texto(destinatario, "el destinatario"), "asunto": _texto(asunto, "el asunto"),
        "texto": _texto(texto, "el texto"), "plazo": _fecha_opcional(plazo), "reporte_id": reporte_id,
    }, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_seguimiento(proyecto)}#notas", 303)


@router.post("/seguimiento/notas/{nota_id}/estado")
def estado_nota(codigo: str, nota_id: int, request: Request, estado: str = Form(max_length=24),
                user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    notas_obra.cambiar_estado(db, user, proyecto, nota_id, estado, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_seguimiento(proyecto)}#nota-{nota_id}", 303)


@router.post("/seguimiento/pedidos/{material_id}")
def estado_pedido(codigo: str, material_id: int, request: Request, estado: str = Form(max_length=24),
                  fecha: str = Form("", max_length=10), fecha_entrega: str = Form("", max_length=10),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    materiales_obra.guardar_pedido(db, user, proyecto, material_id, estado, _fecha_opcional(fecha) or hoy_local(),
                                  _fecha_opcional(fecha_entrega), request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_seguimiento(proyecto)}#pedidos", 303)


@router.post("/seguimiento/stock")
def registrar_stock(codigo: str, request: Request, material: str = Form(max_length=200), unidad: str = Form(max_length=40),
                    cantidad: str = Form(max_length=20), user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = _editar_obra(db, user, codigo)
    try:
        saldo = excel._decimal(cantidad, "la cantidad")
        if not 0 <= saldo < 10**14 or saldo.as_tuple().exponent < -4:
            raise ValueError("Ingresá una cantidad de stock válida.")
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    materiales_obra.declarar_stock(db, user, proyecto, _texto(material, "el material"), _texto(unidad, "la unidad"),
                                  hoy_local(), saldo, request=request)
    db.commit()
    return RedirectResponse(f"{_ruta_seguimiento(proyecto)}#stock", 303)


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
