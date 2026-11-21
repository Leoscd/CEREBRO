"""Inicio (tarjetas por tipo de proyecto, como los cursos) y listado por tipo."""
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Connection

from app.db import db_dependency
from app.permisos import proyectos_visibles_sql, puede_crear_proyecto
from app.security import require_user
from app.templates import templates

router = APIRouter()


@router.get("/")
def home(request: Request, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    cond, params = proyectos_visibles_sql(user)
    tipos = db.execute(
        f"""SELECT t.*,
                   (SELECT count(*) FROM proyectos p WHERE p.tipo_proyecto_id = t.id AND {cond}) AS total,
                   (SELECT count(*) FROM proyectos p
                     WHERE p.tipo_proyecto_id = t.id AND p.estado = 'activo' AND {cond}) AS activos
              FROM tipos_proyecto t
             WHERE t.empresa_id = %s AND t.publicado
             ORDER BY t.posicion, t.nombre""",
        [*params, *params, user["empresa_id"]],
    ).fetchall()
    recientes = db.execute(
        f"""SELECT p.*, t.nombre AS tipo_nombre, t.slug AS tipo_slug
              FROM proyectos p JOIN tipos_proyecto t ON t.id = p.tipo_proyecto_id
             WHERE {cond}
             ORDER BY p.actualizado_en DESC LIMIT 6""",
        params,
    ).fetchall()
    return templates.TemplateResponse(
        request, "inicio.html", {"user": user, "tipos": tipos, "recientes": recientes}
    )


@router.get("/tipo/{slug}")
def tipo_page(slug: str, request: Request, estado: str = "", user=Depends(require_user),
              db: Connection = Depends(db_dependency)):
    tipo = db.execute(
        "SELECT * FROM tipos_proyecto WHERE empresa_id = %s AND slug = %s AND publicado",
        (user["empresa_id"], slug),
    ).fetchone()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de proyecto no encontrado")
    cond, params = proyectos_visibles_sql(user)
    filtro_estado = ""
    if estado in ("activo", "pausado", "finalizado"):
        filtro_estado = " AND p.estado = %s"
        params = [*params, estado]
    proyectos = db.execute(
        f"""SELECT p.*, c.nombre AS cliente_nombre,
                   (SELECT count(*) FROM proyecto_miembros pm WHERE pm.proyecto_id = p.id) AS equipo
              FROM proyectos p LEFT JOIN clientes c ON c.id = p.cliente_id
             WHERE p.tipo_proyecto_id = %s AND {cond}{filtro_estado}
             ORDER BY p.estado = 'activo' DESC, p.actualizado_en DESC""",
        [tipo["id"], *params],
    ).fetchall()
    return templates.TemplateResponse(
        request,
        "tipo.html",
        {"user": user, "tipo": tipo, "proyectos": proyectos, "estado": estado,
         "puede_crear": puede_crear_proyecto(user)},
    )
