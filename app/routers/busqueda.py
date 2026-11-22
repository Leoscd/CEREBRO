"""Ruta de búsqueda de documentación del proyecto."""
from fastapi import APIRouter, Depends, Query, Request
from psycopg import Connection

from app.db import db_dependency
from app.permisos import obtener_proyecto
from app.security import require_user
from app.services import busqueda
from app.templates import templates

router = APIRouter(prefix="/proyectos")


@router.get("/{codigo}/buscar")
def buscar(codigo: str, request: Request, q: str = Query("", max_length=500),
           user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = obtener_proyecto(db, user, codigo)
    resultados = busqueda.buscar(db, user, proyecto, q)
    return templates.TemplateResponse(
        request, "buscar.html", {"user": user, "p": proyecto, "q": q, "resultados": resultados},
    )
