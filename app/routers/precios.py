"""Catálogo interno de materiales, proveedores y precios."""

from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.db import db_dependency
from app.permisos import es_cliente, exigir, puede_gestionar_precios
from app.security import check_csrf, require_user
from app.services import auditoria, dinero, precios
from app.services.tiempo import TZ
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
                  vigente_desde: date = Form(), proveedor_id: int | None = Form(None),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    exigir(puede_gestionar_precios(user, db))
    try:
        centavos = dinero.leer_pesos(precio)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not 0 < centavos <= 2**63 - 1:
        raise HTTPException(422, "El precio debe ser positivo y caber en el catálogo.")
    fecha = datetime.combine(vigente_desde, time.min, TZ)
    if not precios.cargar(db, user, material_id, centavos, fecha, proveedor_id=proveedor_id, request=request):
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
