"""Subida y descarga de archivos del proyecto."""
import re
import unicodedata
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from psycopg import Connection

from app.db import db_dependency
from app.permisos import archivos_visibles_sql, exigir, obtener_archivo, obtener_proyecto, puede_escribir_en_proyecto
from app.security import check_csrf, require_user
from app.services import almacen, auditoria

router = APIRouter()


def contexto_ficha(db: Connection, user: dict, proyecto: dict) -> dict:
    carpetas = db.execute(
        "SELECT id, nombre FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s ORDER BY posicion, id",
        (user["empresa_id"], proyecto["id"]),
    ).fetchall()
    condicion, params = archivos_visibles_sql(user)
    archivos = db.execute(
        f"""SELECT a.id, a.carpeta_id, a.nombre, v.numero, v.tamano_bytes, v.creada_en
              FROM archivos a
              JOIN versiones_archivo v ON v.id = a.version_actual_id AND v.empresa_id = a.empresa_id
                                       AND v.archivo_id = a.id
             WHERE a.proyecto_id = %s AND {condicion} ORDER BY a.nombre, a.id""",
        [proyecto["id"], *params],
    ).fetchall()
    archivos_por_carpeta = {carpeta["id"]: [] for carpeta in carpetas}
    for archivo in archivos:
        archivos_por_carpeta[archivo["carpeta_id"]].append(archivo)
    return {
        "carpetas": carpetas,
        "archivos_por_carpeta": archivos_por_carpeta,
        "puede_subir": puede_escribir_en_proyecto(user, proyecto),
    }


def _nombre_archivo(nombre: str | None) -> str:
    base = (nombre or "").replace("\\", "/").rsplit("/", 1)[-1]
    limpio = "".join(c for c in base if unicodedata.category(c) != "Cc").strip()[:200]
    return "archivo" if limpio in ("", ".", "..") else limpio


def _mime_archivo(archivo: UploadFile) -> str:
    declarada = (archivo.content_type or "").split(";", 1)[0].strip().lower()
    if re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", declarada):
        return declarada
    return "application/octet-stream"


def _crear_version(db: Connection, user: dict, archivo_id: int, numero: int, subida: UploadFile) -> int:
    sha256, tamano = almacen.guardar(subida.file)
    version = db.execute(
        """INSERT INTO versiones_archivo (empresa_id, archivo_id, numero, sha256, tamano_bytes, mime,
                                           origen, subida_por)
           VALUES (%s, %s, %s, %s, %s, %s, 'subida', %s) RETURNING id""",
        (user["empresa_id"], archivo_id, numero, sha256, tamano, _mime_archivo(subida), user["id"]),
    ).fetchone()
    db.execute(
        "UPDATE archivos SET version_actual_id = %s WHERE empresa_id = %s AND id = %s",
        (version["id"], user["empresa_id"], archivo_id),
    )
    return version["id"]


def _respuesta_archivo(archivo: dict, version: dict | None) -> FileResponse:
    if version is None:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    blob = almacen.ruta(version["sha256"])
    if not blob.is_file():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(blob, media_type=version["mime"], filename=archivo["nombre"])


@router.post("/proyectos/{codigo}/carpetas/{carpeta_id}/archivos")
def subir_archivo(codigo: str, carpeta_id: int, request: Request, archivo: UploadFile = File(...),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = obtener_proyecto(db, user, codigo)
    carpeta = db.execute(
        "SELECT id FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s AND id = %s",
        (user["empresa_id"], proyecto["id"], carpeta_id),
    ).fetchone()
    if carpeta is None:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    exigir(puede_escribir_en_proyecto(user, proyecto))
    nombre = _nombre_archivo(archivo.filename)
    nuevo = db.execute(
        """INSERT INTO archivos (empresa_id, proyecto_id, carpeta_id, nombre, extension, mime, creado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (user["empresa_id"], proyecto["id"], carpeta_id, nombre, PurePosixPath(nombre).suffix[1:].lower(),
         _mime_archivo(archivo), user["id"]),
    ).fetchone()
    version_id = _crear_version(db, user, nuevo["id"], 1, archivo)
    auditoria.registrar(db, user, "archivo.subir", proyecto_id=proyecto["id"], objeto="archivo",
                        objeto_id=nuevo["id"], detalle={"nombre": nombre, "version_id": version_id},
                        request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{codigo}#archivos", status_code=303)


@router.get("/archivos/{archivo_id}/descargar")
def descargar_archivo(archivo_id: int, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id)
    version = db.execute(
        "SELECT * FROM versiones_archivo WHERE empresa_id = %s AND archivo_id = %s AND id = %s",
        (user["empresa_id"], archivo_id, archivo["version_actual_id"]),
    ).fetchone()
    return _respuesta_archivo(archivo, version)
