"""Subida y descarga de archivos del proyecto."""
import re
import unicodedata
from http.client import HTTPException as ErrorTransporte
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from itsdangerous import BadData
from jwt import InvalidTokenError
from psycopg import Connection
from starlette.concurrency import run_in_threadpool

from app import config
from app.db import db_dependency
from app.permisos import (
    archivos_visibles_sql,
    exigir,
    obtener_archivo,
    obtener_proyecto,
    puede_editar_proyecto,
    puede_escribir_en_proyecto,
)
from app.security import check_csrf, require_user
from app.services import almacen, auditoria, gotenberg, jobs, onlyoffice, texto
from app.templates import templates

router = APIRouter()


def contexto_ficha(db: Connection, user: dict, proyecto: dict) -> dict:
    carpetas = db.execute(
        "SELECT id, nombre FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s ORDER BY posicion, id",
        (user["empresa_id"], proyecto["id"]),
    ).fetchall()
    condicion, params = archivos_visibles_sql(user)
    archivos = db.execute(
        f"""SELECT a.id, a.carpeta_id, a.nombre, a.visible_cliente, v.numero, v.tamano_bytes, v.creada_en
              FROM archivos a
              JOIN versiones_archivo v ON v.id = a.version_actual_id AND v.empresa_id = a.empresa_id
                                       AND v.archivo_id = a.id
             WHERE a.proyecto_id = %s AND {condicion} ORDER BY a.nombre, a.id""",
        [proyecto["id"], *params],
    ).fetchall()
    por_id = {archivo["id"]: archivo for archivo in archivos}
    archivos_por_carpeta = {carpeta["id"]: [] for carpeta in carpetas}
    for archivo in archivos:
        archivo["historial"] = []
        archivos_por_carpeta[archivo["carpeta_id"]].append(archivo)
    if por_id:
        historial = db.execute(
            """SELECT archivo_id, numero, creada_en, tamano_bytes FROM versiones_archivo
               WHERE empresa_id = %s AND archivo_id = ANY(%s) ORDER BY numero DESC""",
            (user["empresa_id"], list(por_id)),
        )
        for version in historial:
            por_id[version["archivo_id"]]["historial"].append(version)
    puede_subir = puede_escribir_en_proyecto(user, proyecto)
    papelera = []
    if puede_subir:
        condicion, params = archivos_visibles_sql(user, solo_papelera=True)
        papelera = db.execute(
            f"""SELECT a.id, a.nombre, a.en_papelera_en FROM archivos a
                WHERE a.proyecto_id = %s AND {condicion} ORDER BY a.en_papelera_en DESC""",
            [proyecto["id"], *params],
        ).fetchall()
    return {
        "carpetas": carpetas,
        "archivos_por_carpeta": archivos_por_carpeta,
        "puede_subir": puede_subir,
        "papelera": papelera,
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
    return _registrar_version(db, user, archivo_id, numero, sha256, tamano, _mime_archivo(subida))


def _registrar_version(db: Connection, user: dict, archivo_id: int, numero: int,
                       sha256: str, tamano: int, mime: str) -> int:
    version = db.execute(
        """INSERT INTO versiones_archivo (empresa_id, archivo_id, numero, sha256, tamano_bytes, mime,
                                           origen, subida_por)
           VALUES (%s, %s, %s, %s, %s, %s, 'subida', %s) RETURNING id""",
        (user["empresa_id"], archivo_id, numero, sha256, tamano, mime, user["id"]),
    ).fetchone()
    archivo = db.execute(
        "UPDATE archivos SET version_actual_id = %s, mime = %s WHERE empresa_id = %s AND id = %s RETURNING extension",
        (version["id"], mime, user["empresa_id"], archivo_id),
    ).fetchone()
    jobs.encolar(db, user["empresa_id"], "archivo.analizar", {"version_id": version["id"]})
    extension = archivo["extension"]
    tipo_job = "archivo.vista_pdf" if extension in gotenberg.EXTENSIONES else {
        "dxf": "archivo.dxf", "ifc": "archivo.ifc",
    }.get(extension)
    if tipo_job:
        clave = "vista_ifc" if extension == "ifc" else "vista"
        db.execute("""UPDATE versiones_archivo SET derivados=derivados || jsonb_build_object(%s::text,'pendiente')
                      WHERE empresa_id=%s AND id=%s""", (clave, user["empresa_id"], version["id"]))
        jobs.encolar(db, user["empresa_id"], tipo_job, {"version_id": version["id"]})
    elif texto.es_pdf(almacen.ruta(sha256)):
        jobs.encolar(db, user["empresa_id"], "archivo.indexar", {"version_id": version["id"]})
    return version["id"]


def _tipo_de_vista(blob: Path, mime: str, extension: str) -> str | None:
    firmas = {
        "application/pdf": (b"%PDF-",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/gif": (b"GIF87a", b"GIF89a"),
    }
    if extension in {"svg", "svgz", "html", "htm", "xhtml"}:
        return None
    es_modelo = extension in {"glb", "gltf", "obj", "stl", "ply", "3ds", "off", "ifc"}
    if not es_modelo and mime not in firmas and mime != "image/webp":
        return None
    try:
        with blob.open("rb") as stream:
            cabecera = stream.read(84)
            if extension == "stl":
                triangulos = int.from_bytes(cabecera[80:84], "little")
                binario = len(cabecera) == 84 and stream.seek(0, 2) == 84 + 50 * triangulos
                return "modelo3d" if binario or cabecera.lstrip().startswith(b"solid") else None
    except FileNotFoundError:
        return None
    if es_modelo:
        firma = {"glb": b"glTF", "ifc": b"ISO-10303-21"}.get(extension, b"")
        return "modelo3d" if cabecera and cabecera.startswith(firma) else None
    if mime == "image/webp":
        return "imagen" if cabecera.startswith(b"RIFF") and cabecera[8:12] == b"WEBP" else None
    if cabecera.startswith(firmas[mime]):
        return "pdf" if mime == "application/pdf" else "imagen"
    return None


def _respuesta_archivo(archivo: dict, version: dict | None, *, previsualizar: bool = False) -> FileResponse:
    if version is None:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    blob = almacen.ruta(version["sha256"])
    if not blob.is_file():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    inline = previsualizar and _tipo_de_vista(blob, version["mime"], archivo["extension"]) in {"pdf", "imagen"}
    return FileResponse(
        blob, media_type=version["mime"], filename=archivo["nombre"],
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.get("/archivos/{archivo_id}")
def pagina_archivo(archivo_id: int, request: Request, user=Depends(require_user),
                   db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id)
    carpeta = db.execute(
        "SELECT nombre FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s AND id = %s",
        (user["empresa_id"], archivo["proyecto_id"], archivo["carpeta_id"]),
    ).fetchone()
    version = _obtener_version(db, archivo)
    historial = db.execute(
        """SELECT numero, tamano_bytes, creada_en FROM versiones_archivo
           WHERE empresa_id = %s AND archivo_id = %s ORDER BY numero DESC""",
        (user["empresa_id"], archivo_id),
    ).fetchall()
    tipo = _tipo_de_vista(almacen.ruta(version["sha256"]), version["mime"], archivo["extension"]) if version else None
    editor = None
    if version and archivo["extension"] in onlyoffice.TIPOS and config.ONLYOFFICE_URL and config.ONLYOFFICE_JWT_SECRET:
        tipo = "onlyoffice"
        editor = onlyoffice.config_editor(user, archivo, version)
    elif version and version["derivados"].get("pdf"):
        tipo = "pdf"
    elif version and version["derivados"].get("svg"):
        tipo = "imagen"
    nombres_ifc = {}
    if version and version["derivados"].get("meta", {}).get("ifc"):
        from app.services.ifc import TIPOS
        nombres_ifc = {clase: plural for clase, (_, plural) in TIPOS.items()}
    return templates.TemplateResponse(
        request, "archivo.html",
        {"user": user, "archivo": archivo, "carpeta": carpeta, "version": version, "historial": historial,
         "tipo": tipo, "editor": editor, "onlyoffice_url": config.ONLYOFFICE_URL, "nombres_ifc": nombres_ifc},
    )


@router.get("/archivos/{archivo_id}/contenido")
def contenido_archivo(archivo_id: int, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id)
    return _respuesta_archivo(archivo, _obtener_version(db, archivo), previsualizar=True)


@router.get("/onlyoffice/descarga/{token}")
def descarga_onlyoffice(token: str, db: Connection = Depends(db_dependency)):
    try:
        empresa_id, archivo_id, version_id = onlyoffice.leer_token_descarga(token)
    except BadData:
        raise HTTPException(404, "Versión no encontrada")
    version = db.execute(
        """SELECT a.nombre, v.mime, v.sha256 FROM versiones_archivo v
           JOIN archivos a ON a.id=v.archivo_id AND a.empresa_id=v.empresa_id
           WHERE v.empresa_id=%s AND v.archivo_id=%s AND v.id=%s AND a.en_papelera_en IS NULL""",
        (empresa_id, archivo_id, version_id),
    ).fetchone()
    if version is None:
        raise HTTPException(404, "Versión no encontrada")
    return _respuesta_archivo(version, version)


def _editor_autorizado(db, empresa_id, archivo_id, usuario_id, *, bloquear=False):
    user = db.execute("""SELECT id, empresa_id, rol_empresa, cliente_id FROM usuarios
                         WHERE empresa_id=%s AND id=%s AND activo""", (empresa_id, usuario_id)).fetchone()
    if user is None:
        raise HTTPException(404)
    archivo = obtener_archivo(db, user, archivo_id, bloquear=bloquear)
    exigir(archivo["extension"] in onlyoffice.TIPOS and puede_escribir_en_proyecto(user, archivo))
    return user, archivo


def _guardar_callback(db, ids, evento, request):
    empresa_id, archivo_id, base_id, usuario_id = ids
    _editor_autorizado(db, empresa_id, archivo_id, usuario_id)
    base = db.execute("""SELECT id, sha256 FROM versiones_archivo
                         WHERE empresa_id=%s AND archivo_id=%s AND id=%s""",
                      (empresa_id, archivo_id, base_id)).fetchone()
    if not base or evento.get("key") != onlyoffice.clave_documento(archivo_id, base):
        return {"error": 1}
    url = evento.get("url")
    if not onlyoffice.url_guardado_valida(url):
        return {"error": 1}
    sha, tamano = onlyoffice.descargar_version(url)
    # Durante la descarga pueden cambiar la asignación, la papelera o la versión actual.
    user, archivo = _editor_autorizado(db, empresa_id, archivo_id, usuario_id, bloquear=True)
    actual = _obtener_version(db, archivo)
    if actual["sha256"] == sha:
        return {"error": 0}
    if actual["id"] != base_id and actual["derivados"].get("onlyoffice_base") != base_id:
        return {"error": 1}
    huella = onlyoffice.huella_guardado(evento)
    repetido = db.execute("""SELECT 1 FROM versiones_archivo WHERE empresa_id=%s AND archivo_id=%s
                             AND sha256=%s AND derivados->>'onlyoffice_base'=%s
                             AND derivados->>'onlyoffice_evento'=%s""",
                          (empresa_id, archivo_id, sha, str(base_id), huella)).fetchone()
    if repetido:
        return {"error": 0}
    numero = actual["numero"] + 1
    nueva = _registrar_version(db, user, archivo_id, numero, sha, tamano, actual["mime"])
    db.execute("""UPDATE versiones_archivo SET derivados=derivados ||
                  jsonb_build_object('onlyoffice_base', %s::bigint, 'onlyoffice_evento', %s::text)
                  WHERE empresa_id=%s AND archivo_id=%s AND id=%s""", (base_id, huella, empresa_id, archivo_id, nueva))
    auditoria.registrar(db, user, "archivo.version_onlyoffice", proyecto_id=archivo["proyecto_id"],
                        objeto="archivo", objeto_id=archivo_id, detalle={"version_id": nueva, "numero": numero},
                        request=request)
    db.commit()
    return {"error": 0}


@router.post("/onlyoffice/callback/{token}")
async def callback_onlyoffice(token: str, request: Request, db: Connection = Depends(db_dependency)):
    try:
        ids = onlyoffice.leer_token_callback(token)
        autorizacion = request.headers.get("authorization", "")
        cuerpo = {} if autorizacion.lower().startswith("bearer ") else await request.json()
        if not isinstance(cuerpo, dict):
            return {"error": 1}
        evento = onlyoffice.evento_firmado(autorizacion, cuerpo)
        if evento["status"] not in (2, 6):
            return {"error": 0}
        return await run_in_threadpool(_guardar_callback, db, ids, evento, request)
    except (BadData, InvalidTokenError, ValueError, HTTPException, OSError, ErrorTransporte):
        await run_in_threadpool(db.rollback)
        return {"error": 1}


@router.get("/archivos/{archivo_id}/vista.pdf")
def vista_pdf(archivo_id: int, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    return _vista_derivada(db, user, archivo_id, "pdf")


@router.get("/archivos/{archivo_id}/vista.svg")
def vista_svg(archivo_id: int, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    return _vista_derivada(db, user, archivo_id, "svg")


def _vista_derivada(db, user, archivo_id, tipo):
    archivo = obtener_archivo(db, user, archivo_id)
    version = _obtener_version(db, archivo)
    derivado = version["derivados"].get(tipo) if version else None
    if not derivado or not (blob := almacen.ruta(derivado["sha256"])).is_file():
        raise HTTPException(404, "Vista previa no disponible")
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
    if tipo == "svg":
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return FileResponse(blob, media_type={"pdf": "application/pdf", "svg": "image/svg+xml"}[tipo],
                        filename=f"{Path(archivo['nombre']).stem}.{tipo}", content_disposition_type="inline", headers=headers)


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
    return _respuesta_archivo(archivo, _obtener_version(db, archivo))


def _obtener_version(db: Connection, archivo: dict, numero: int | None = None) -> dict | None:
    columna = "id" if numero is None else "numero"
    valor = archivo["version_actual_id"] if numero is None else numero
    return db.execute(
        f"SELECT * FROM versiones_archivo WHERE empresa_id = %s AND archivo_id = %s AND {columna} = %s",
        (archivo["empresa_id"], archivo["id"], valor),
    ).fetchone()


@router.get("/archivos/{archivo_id}/versiones/{numero}/descargar")
def descargar_version(archivo_id: int, numero: int, user=Depends(require_user),
                      db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id)
    return _respuesta_archivo(archivo, _obtener_version(db, archivo, numero))


def _confirmar_cambio(db: Connection, user: dict, archivo: dict, accion: str, request: Request,
                      detalle: dict | None = None) -> RedirectResponse:
    auditoria.registrar(db, user, accion, proyecto_id=archivo["proyecto_id"], objeto="archivo",
                        objeto_id=archivo["id"], detalle=detalle, request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{archivo['codigo_proyecto']}#archivos", status_code=303)


@router.post("/archivos/{archivo_id}/versiones")
def subir_version(archivo_id: int, request: Request, archivo: UploadFile = File(...),
                  user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    registro = obtener_archivo(db, user, archivo_id, bloquear=True)
    exigir(puede_escribir_en_proyecto(user, registro))
    # El lock del archivo serializa el correlativo y el puntero a la versión actual.
    fila = db.execute(
        """SELECT coalesce(max(numero), 0) + 1 AS numero FROM versiones_archivo
            WHERE empresa_id = %s AND archivo_id = %s""",
        (user["empresa_id"], archivo_id),
    ).fetchone()
    version_id = _crear_version(db, user, archivo_id, fila["numero"], archivo)
    return _confirmar_cambio(db, user, registro, "archivo.version", request,
                             {"version_id": version_id, "numero": fila["numero"]})


@router.post("/archivos/{archivo_id}/papelera")
def enviar_a_papelera(archivo_id: int, request: Request, user=Depends(check_csrf),
                      db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id, bloquear=True)
    exigir(puede_escribir_en_proyecto(user, archivo))
    db.execute("UPDATE archivos SET en_papelera_en = now() WHERE empresa_id = %s AND id = %s",
               (user["empresa_id"], archivo_id))
    return _confirmar_cambio(db, user, archivo, "archivo.papelera", request)


@router.post("/archivos/{archivo_id}/restaurar")
def restaurar_archivo(archivo_id: int, request: Request, user=Depends(check_csrf),
                      db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id, solo_papelera=True, bloquear=True)
    exigir(puede_escribir_en_proyecto(user, archivo))
    db.execute("UPDATE archivos SET en_papelera_en = NULL WHERE empresa_id = %s AND id = %s",
               (user["empresa_id"], archivo_id))
    return _confirmar_cambio(db, user, archivo, "archivo.restaurar", request)


@router.post("/archivos/{archivo_id}/visibilidad")
def cambiar_visibilidad(archivo_id: int, request: Request, visible_cliente: str = Form(""),
                        user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    archivo = obtener_archivo(db, user, archivo_id, bloquear=True)
    exigir(puede_editar_proyecto(user, archivo))
    visible = visible_cliente == "1"
    db.execute("UPDATE archivos SET visible_cliente = %s WHERE empresa_id = %s AND id = %s",
               (visible, user["empresa_id"], archivo_id))
    return _confirmar_cambio(db, user, archivo, "archivo.visibilidad", request, {"visible_cliente": visible})
