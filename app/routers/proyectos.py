"""Ficha del proyecto, edición, equipo e hitos."""
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from psycopg import Connection

from app.db import db_dependency
from app.permisos import (
    ROLES_PROYECTO,
    exigir,
    obtener_proyecto,
    puede_editar_proyecto,
    puede_gestionar_equipo,
    puede_ver_auditoria,
)
from app.routers.archivos import contexto_ficha
from app.security import check_csrf, require_user
from app.services import auditoria
from app.templates import ETAPAS, ESTADOS, templates

router = APIRouter(prefix="/proyecto")


def _fecha(valor: str) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida")


@router.get("/{codigo}")
def ficha(codigo: str, request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    p = obtener_proyecto(db, user, codigo)
    equipo = db.execute(
        """SELECT u.id, u.nombre, u.email, pm.rol, pm.funcion, pm.desde
             FROM proyecto_miembros pm JOIN usuarios u ON u.id = pm.usuario_id
            WHERE pm.proyecto_id = %s ORDER BY pm.rol, u.nombre""",
        (p["id"],),
    ).fetchall()
    solo_visibles = user["rol_empresa"] == "cliente"
    hitos = db.execute(
        "SELECT * FROM hitos WHERE proyecto_id = %s" + (" AND visible_cliente" if solo_visibles else "")
        + " ORDER BY fecha",
        (p["id"],),
    ).fetchall()
    actividad = []
    if puede_ver_auditoria(user, p):
        actividad = db.execute(
            """SELECT a.*, u.nombre AS usuario_nombre FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
                WHERE a.proyecto_id = %s AND a.empresa_id = %s ORDER BY a.creado_en DESC LIMIT 20""",
            (p["id"], user["empresa_id"]),
        ).fetchall()
    candidatos = []
    if puede_gestionar_equipo(user, p):
        candidatos = db.execute(
            """SELECT id, nombre, email FROM usuarios
                WHERE empresa_id = %s AND activo AND rol_empresa <> 'cliente'
                  AND id NOT IN (SELECT usuario_id FROM proyecto_miembros WHERE proyecto_id = %s)
                ORDER BY nombre""",
            (user["empresa_id"], p["id"]),
        ).fetchall()
    return templates.TemplateResponse(
        request,
        "proyecto.html",
        {
            "user": user, "p": p, "equipo": equipo, "hitos": hitos, "actividad": actividad,
            "candidatos": candidatos,
            "puede_editar": puede_editar_proyecto(user, p),
            "puede_equipo": puede_gestionar_equipo(user, p),
            **contexto_ficha(db, user, p),
        },
    )


@router.post("/{codigo}/editar")
def editar(
    codigo: str,
    request: Request,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    direccion: str = Form(""),
    localidad: str = Form(""),
    etapa: str = Form("anteproyecto"),
    estado: str = Form("activo"),
    avance: int = Form(0),
    fecha_inicio: str = Form(""),
    fecha_fin_estimada: str = Form(""),
    permite_difusion: str = Form(""),
    user=Depends(check_csrf),
    db: Connection = Depends(db_dependency),
):
    p = obtener_proyecto(db, user, codigo)
    exigir(puede_editar_proyecto(user, p))
    if etapa not in ETAPAS or estado not in ESTADOS or not (0 <= avance <= 100) or not nombre.strip():
        raise HTTPException(status_code=400, detail="Datos inválidos")
    nuevos = {
        "nombre": nombre.strip()[:200], "descripcion": descripcion.strip(), "direccion": direccion.strip(),
        "localidad": localidad.strip(), "etapa": etapa, "estado": estado, "avance": avance,
        "fecha_inicio": _fecha(fecha_inicio), "fecha_fin_estimada": _fecha(fecha_fin_estimada),
        "permite_difusion": permite_difusion == "1",
    }
    cambios = {k: str(v) for k, v in nuevos.items() if p.get(k) != v}
    db.execute(
        """UPDATE proyectos SET nombre=%(nombre)s, descripcion=%(descripcion)s, direccion=%(direccion)s,
               localidad=%(localidad)s, etapa=%(etapa)s, estado=%(estado)s, avance=%(avance)s,
               fecha_inicio=%(fecha_inicio)s, fecha_fin_estimada=%(fecha_fin_estimada)s,
               permite_difusion=%(permite_difusion)s, actualizado_en=now()
            WHERE id=%(id)s AND empresa_id=%(empresa_id)s""",
        {**nuevos, "id": p["id"], "empresa_id": user["empresa_id"]},
    )
    if cambios:
        auditoria.registrar(db, user, "proyecto_editado", proyecto_id=p["id"], objeto="proyecto",
                            objeto_id=p["codigo"], detalle=cambios, request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{codigo}", status_code=303)


def _coordenada(entrada: str, limite: int) -> float:
    try:
        valor = Decimal(entrada.strip().replace(",", "."))
        if not valor.is_finite() or not -limite <= valor <= limite:
            raise InvalidOperation
        return float(valor.quantize(Decimal("0.000001")))
    except InvalidOperation as error:
        raise HTTPException(400, "Revisá la latitud y la longitud del proyecto.") from error


@router.post("/{codigo}/ubicacion")
def guardar_ubicacion(codigo: str, request: Request, lat: str = Form("", max_length=30),
                      lon: str = Form("", max_length=30), user=Depends(check_csrf),
                      db: Connection = Depends(db_dependency)):
    proyecto = obtener_proyecto(db, user, codigo)
    exigir(puede_editar_proyecto(user, proyecto))
    if not lat.strip() and not lon.strip():
        latitud = longitud = None
    else:
        latitud, longitud = _coordenada(lat, 90), _coordenada(lon, 180)
    if (proyecto["lat"], proyecto["lon"]) != (latitud, longitud):
        db.execute("UPDATE proyectos SET lat=%s,lon=%s,actualizado_en=now() WHERE empresa_id=%s AND id=%s",
                   (latitud, longitud, user["empresa_id"], proyecto["id"]))
        auditoria.registrar(db, user, "proyecto.ubicacion_guardada", proyecto_id=proyecto["id"], objeto="proyecto",
                            objeto_id=proyecto["codigo"], request=request)
        db.commit()
    return RedirectResponse(f"/proyecto/{codigo}#ubicacion", 303)


@router.post("/{codigo}/equipo")
def agregar_miembro(
    codigo: str,
    request: Request,
    usuario_id: int = Form(...),
    rol: str = Form("colaborador"),
    funcion: str = Form(""),
    user=Depends(check_csrf),
    db: Connection = Depends(db_dependency),
):
    p = obtener_proyecto(db, user, codigo)
    exigir(puede_gestionar_equipo(user, p))
    if rol not in ROLES_PROYECTO:
        raise HTTPException(status_code=400, detail="Rol inválido")
    # Solo personal activo de la MISMA empresa.
    otro = db.execute(
        "SELECT id FROM usuarios WHERE id = %s AND empresa_id = %s AND activo AND rol_empresa <> 'cliente'",
        (usuario_id, user["empresa_id"]),
    ).fetchone()
    if not otro:
        raise HTTPException(status_code=400, detail="Usuario inválido")
    db.execute(
        """INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol, funcion) VALUES (%s, %s, %s, %s)
           ON CONFLICT (proyecto_id, usuario_id) DO UPDATE SET rol = EXCLUDED.rol, funcion = EXCLUDED.funcion""",
        (p["id"], usuario_id, rol, funcion.strip()[:120]),
    )
    auditoria.registrar(db, user, "miembro_agregado", proyecto_id=p["id"], objeto="usuario",
                        objeto_id=usuario_id, detalle={"rol": rol}, request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{codigo}#equipo", status_code=303)


@router.post("/{codigo}/equipo/{usuario_id}/quitar")
def quitar_miembro(codigo: str, usuario_id: int, request: Request, user=Depends(check_csrf),
                   db: Connection = Depends(db_dependency)):
    p = obtener_proyecto(db, user, codigo)
    exigir(puede_gestionar_equipo(user, p))
    db.execute("DELETE FROM proyecto_miembros WHERE proyecto_id = %s AND usuario_id = %s", (p["id"], usuario_id))
    auditoria.registrar(db, user, "miembro_quitado", proyecto_id=p["id"], objeto="usuario",
                        objeto_id=usuario_id, request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{codigo}#equipo", status_code=303)


@router.post("/{codigo}/hitos")
def agregar_hito(
    codigo: str,
    request: Request,
    titulo: str = Form(...),
    fecha: str = Form(...),
    visible_cliente: str = Form(""),
    user=Depends(check_csrf),
    db: Connection = Depends(db_dependency),
):
    p = obtener_proyecto(db, user, codigo)
    exigir(puede_editar_proyecto(user, p))
    if not titulo.strip():
        raise HTTPException(status_code=400, detail="Falta el título")
    h = db.execute(
        """INSERT INTO hitos (empresa_id, proyecto_id, titulo, fecha, visible_cliente)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (user["empresa_id"], p["id"], titulo.strip()[:200], _fecha(fecha), visible_cliente == "1"),
    ).fetchone()
    auditoria.registrar(db, user, "hito_agregado", proyecto_id=p["id"], objeto="hito", objeto_id=h["id"],
                        detalle={"titulo": titulo.strip()}, request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{codigo}#hitos", status_code=303)


@router.post("/{codigo}/hitos/{hito_id}/completar")
def completar_hito(codigo: str, hito_id: int, request: Request, user=Depends(check_csrf),
                   db: Connection = Depends(db_dependency)):
    p = obtener_proyecto(db, user, codigo)
    exigir(puede_editar_proyecto(user, p))
    db.execute("UPDATE hitos SET completado = NOT completado WHERE id = %s AND proyecto_id = %s", (hito_id, p["id"]))
    auditoria.registrar(db, user, "hito_cambiado", proyecto_id=p["id"], objeto="hito", objeto_id=hito_id,
                        request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{codigo}#hitos", status_code=303)
