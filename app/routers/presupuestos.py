"""Presupuestos internos de un proyecto."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.db import db_dependency
from app.permisos import es_cliente, exigir, obtener_proyecto, proyectos_visibles_sql, puede_editar_presupuesto
from app.security import check_csrf, require_user
from app.services import auditoria, dinero, presupuestos, verificador
from app.services.tiempo import hoy_local
from app.templates import templates

router = APIRouter()
_COLECCION = "/proyecto/{codigo}/presupuestos"
_DETALLE = "/presupuestos/{presupuesto_id:int}"


def _proyecto(db, user, codigo):
    if es_cliente(user):
        raise HTTPException(404, "Presupuesto no encontrado")
    return obtener_proyecto(db, user, codigo)


def _obtener(db, user, presupuesto_id, *, bloquear=False):
    if es_cliente(user):
        raise HTTPException(404, "Presupuesto no encontrado")
    condicion, params = proyectos_visibles_sql(user)
    bloqueo = " FOR UPDATE OF b" if bloquear else ""
    presupuesto = db.execute(
        f"""SELECT b.*, p.codigo AS codigo_proyecto
              FROM presupuestos b JOIN proyectos p ON p.empresa_id=b.empresa_id AND p.id=b.proyecto_id
             WHERE b.empresa_id=%s AND b.id=%s AND {condicion}{bloqueo}""",
        [user["empresa_id"], presupuesto_id, *params],
    ).fetchone()
    if presupuesto is None:
        raise HTTPException(404, "Presupuesto no encontrado")
    return presupuesto, obtener_proyecto(db, user, presupuesto["codigo_proyecto"])


def _editable(db, user, presupuesto_id, *, solo_borrador=True):
    presupuesto, proyecto = _obtener(db, user, presupuesto_id, bloquear=True)
    exigir(puede_editar_presupuesto(user, proyecto))
    if solo_borrador and presupuesto["estado"] != "borrador":
        raise HTTPException(409, "El presupuesto ya fue emitido. Creá una nueva versión para editarlo.")
    return presupuesto


def _texto(valor, campo):
    limpio = valor.replace("\x00", " ").strip()
    if not limpio:
        raise HTTPException(422, f"Completá {campo}.")
    return limpio


def _ficha(nombre: str = Form(max_length=240), fecha_precios: date = Form(),
           gastos_generales_pb: int = Form(0, ge=0, le=2**31-1),
           beneficio_pb: int = Form(0, ge=0, le=2**31-1), impuestos_pb: int = Form(0, ge=0, le=2**31-1)):
    return (_texto(nombre, "el nombre"), fecha_precios, gastos_generales_pb, beneficio_pb, impuestos_pb)


def _datos_item(rubro_id: int = Form(gt=0, le=2**63-1), descripcion: str = Form(max_length=240),
                unidad: str = Form(max_length=40), cantidad: Decimal = Form(max_digits=14, decimal_places=4),
                apu_id: int | None = Form(None, gt=0, le=2**63-1), precio: str = Form("", max_length=64),
                origen_cantidad: Literal["manual", "revit", "autocad"] = Form("manual")):
    precio = precio.strip()
    if (apu_id is None) == (not precio):
        raise HTTPException(422, "Elegí un APU o ingresá un único precio manual.")
    centavos = None
    if precio:
        try:
            centavos = dinero.leer_pesos(precio)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if not 0 <= centavos <= 2**63 - 1:
            raise HTTPException(422, "El precio manual debe ser un importe válido no negativo.")
    return {"rubro_id": rubro_id, "descripcion": _texto(descripcion, "la descripción"),
            "unidad": _texto(unidad, "la unidad"), "cantidad": cantidad, "apu_id": apu_id,
            "precio_unitario_centavos": centavos, "origen_cantidad": origen_cantidad}


@router.get(_COLECCION)
def listar(codigo: str, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = _proyecto(db, user, codigo)
    filas = db.execute(
        """SELECT id,nombre,version,estado,fecha_precios FROM presupuestos
            WHERE empresa_id=%s AND proyecto_id=%s ORDER BY creado_en DESC,id DESC""",
        (user["empresa_id"], proyecto["id"]),
    ).fetchall()
    return templates.TemplateResponse(request, "presupuestos.html", {
        "user": user, "proyecto": proyecto, "filas": filas, "hoy": hoy_local(),
        "editar": puede_editar_presupuesto(user, proyecto),
    })


@router.post(_COLECCION)
def crear(codigo: str, request: Request, user=Depends(check_csrf), ficha=Depends(_ficha),
          db: Connection = Depends(db_dependency)):
    proyecto = _proyecto(db, user, codigo)
    exigir(puede_editar_presupuesto(user, proyecto))
    presupuesto = db.execute(
        """INSERT INTO presupuestos(empresa_id,proyecto_id,nombre,fecha_precios,gastos_generales_pb,
                                    beneficio_pb,impuestos_pb,creado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (user["empresa_id"], proyecto["id"], *ficha, user["id"]),
    ).fetchone()["id"]
    auditoria.registrar(db, user, "presupuesto.creado", proyecto_id=proyecto["id"],
                        objeto="presupuesto", objeto_id=presupuesto, request=request)
    db.commit()
    return RedirectResponse(f"/presupuestos/{presupuesto}", 303)


@router.get(_DETALLE)
def detalle(presupuesto_id: int, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    presupuesto, proyecto = _obtener(db, user, presupuesto_id)
    calculo = presupuestos.calcular(db, user["empresa_id"], presupuesto_id)
    return _mostrar_detalle(request, user, db, presupuesto, proyecto, calculo, verificador.analizar_calculo(calculo))


def _mostrar_detalle(request, user, db, presupuesto, proyecto, calculo, hallazgos, *, status_code=200):
    editar = puede_editar_presupuesto(user, proyecto)
    apus = db.execute(
        "SELECT id,codigo,descripcion,activo FROM apus WHERE empresa_id=%s ORDER BY codigo",
        (user["empresa_id"],),
    ).fetchall() if editar and presupuesto["estado"] == "borrador" else []
    return templates.TemplateResponse(request, "presupuesto.html", {
        "user": user, "proyecto": proyecto, "editar": editar, "apus": apus,
        "calculo": calculo, "hallazgos": hallazgos,
    }, status_code=status_code)


@router.post(_DETALLE + "/editar")
def editar(presupuesto_id: int, request: Request, user=Depends(check_csrf), ficha=Depends(_ficha),
           db: Connection = Depends(db_dependency)):
    presupuesto = _editable(db, user, presupuesto_id)
    db.execute(
        """UPDATE presupuestos SET nombre=%s,fecha_precios=%s,gastos_generales_pb=%s,beneficio_pb=%s,impuestos_pb=%s
            WHERE empresa_id=%s AND id=%s""",
        (*ficha, user["empresa_id"], presupuesto_id),
    )
    auditoria.registrar(db, user, "presupuesto.editado", proyecto_id=presupuesto["proyecto_id"],
                        objeto="presupuesto", objeto_id=presupuesto_id, request=request)
    db.commit()
    return RedirectResponse(f"/presupuestos/{presupuesto_id}", 303)


@router.post(_DETALLE + "/rubros")
def agregar_rubro(presupuesto_id: int, request: Request, nombre: str = Form(max_length=120),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    presupuesto = _editable(db, user, presupuesto_id)
    try:
        presupuestos.agregar_rubro(db, user, presupuesto, _texto(nombre, "el nombre del rubro"), request=request)
    except UniqueViolation as error:
        raise HTTPException(409, "Ya existe ese rubro en el presupuesto.") from error
    db.commit()
    return RedirectResponse(f"/presupuestos/{presupuesto_id}", 303)


def _guardar_item(db, user, presupuesto_id, datos, request, item_id=None):
    presupuesto = _editable(db, user, presupuesto_id)
    if presupuestos.guardar_item(db, user, presupuesto, datos, item_id=item_id, request=request) is None:
        raise HTTPException(404, "Ítem, rubro o APU no encontrado")
    db.commit()
    return RedirectResponse(f"/presupuestos/{presupuesto_id}", 303)


@router.post(_DETALLE + "/items")
def agregar_item(presupuesto_id: int, request: Request, user=Depends(check_csrf), datos=Depends(_datos_item),
                 db: Connection = Depends(db_dependency)):
    return _guardar_item(db, user, presupuesto_id, datos, request)


@router.post(_DETALLE + "/items/{item_id}")
def editar_item(presupuesto_id: int, item_id: int, request: Request, user=Depends(check_csrf),
                datos=Depends(_datos_item), db: Connection = Depends(db_dependency)):
    return _guardar_item(db, user, presupuesto_id, datos, request, item_id)


@router.post(_DETALLE + "/emitir")
def emitir(presupuesto_id: int, request: Request, user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    presupuesto = _editable(db, user, presupuesto_id)
    resultado = presupuestos.calcular(db, user["empresa_id"], presupuesto_id)
    hallazgos = verificador.analizar_calculo(resultado)
    if any(h["severidad"] == "error" for h in hallazgos):
        if request.headers.get("x-csrf") or request.headers.get("accept", "").startswith("application/json"):
            raise HTTPException(409, hallazgos)
        proyecto = obtener_proyecto(db, user, presupuesto["codigo_proyecto"])
        return _mostrar_detalle(request, user, db, presupuesto, proyecto, resultado, hallazgos, status_code=409)
    try:
        presupuestos.emitir(db, user, presupuesto, resultado, request=request)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    return RedirectResponse(f"/presupuestos/{presupuesto_id}", 303)


@router.post(_DETALLE + "/nueva-version")
def nueva_version(presupuesto_id: int, request: Request, user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    presupuesto = _editable(db, user, presupuesto_id, solo_borrador=False)
    if presupuesto["estado"] != "emitido":
        raise HTTPException(409, "Emití el presupuesto antes de crear otra versión.")
    nuevo = presupuestos.nueva_version(db, user, presupuesto, request=request)
    db.commit()
    return RedirectResponse(f"/presupuestos/{nuevo}", 303)
