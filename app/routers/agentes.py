"""Chat del Documentador y su historial por persona y proyecto."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import config, security
from app.agentes import aprobaciones, documentador, obra, presupuestos
from app.agentes.herramientas import ContextoDocumentador, ids_visibles
from app.db import db_dependency, pool
from app.permisos import obtener_proyecto
from app.routers.obra import _obra as obtener_obra
from app.routers.presupuestos import _obtener as obtener_presupuesto
from app.security import require_user
from app.services import auditoria
from app.services.tiempo import hoy_local

router = APIRouter()
_AGENTE = "documentador"
_PRIVADO = {"Cache-Control": "private, no-store"}
log = logging.getLogger(__name__)


class Pregunta(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1600)
    conversacion_id: int | None = Field(default=None, ge=1, le=2**63 - 1)


def _alcance(usuario: dict, proyecto: dict, agente: str = _AGENTE) -> tuple:
    return usuario["empresa_id"], proyecto["id"], usuario["id"], agente


def _mensajes(db: Connection, usuario: dict, proyecto: dict, conversacion_id: int) -> list[dict]:
    recientes = db.execute(
        """SELECT rol, contenido, citas FROM mensajes WHERE empresa_id = %s AND conversacion_id = %s
           ORDER BY id DESC LIMIT 40""",
        (usuario["empresa_id"], conversacion_id),
    ).fetchall()
    ids = {cita["chunk_id"] for fila in recientes for cita in fila["citas"]}
    visibles = ids_visibles(db, usuario, proyecto, list(ids))
    # Una respuesta cuyo respaldo cambió se excluye del historial visible y del próximo prompt.
    return [fila for fila in reversed(recientes) if all(cita["chunk_id"] in visibles for cita in fila["citas"])]


@router.get("/proyectos/{codigo}/documentador")
def historial_documentador(codigo: str, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    proyecto = obtener_proyecto(db, user, codigo)
    fila = db.execute(
        """SELECT id FROM conversaciones
            WHERE empresa_id = %s AND proyecto_id = %s AND usuario_id = %s AND agente = %s""",
        _alcance(user, proyecto),
    ).fetchone()
    if fila is None:
        return JSONResponse({"conversacion_id": None, "mensajes": []}, headers=_PRIVADO)
    return JSONResponse({"conversacion_id": fila["id"], "mensajes": _mensajes(db, user, proyecto, fila["id"])},
                        headers=_PRIVADO)


def _abrir_conversacion(db: Connection, usuario: dict, proyecto: dict, conversacion_id: int | None,
                       *, agente: str = _AGENTE) -> int:
    params = _alcance(usuario, proyecto, agente)
    if conversacion_id is None:
        fila = db.execute(
            """INSERT INTO conversaciones (empresa_id, proyecto_id, usuario_id, agente)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (empresa_id, proyecto_id, usuario_id, agente) DO UPDATE SET agente = excluded.agente
               RETURNING id""",
            params,
        ).fetchone()
    else:
        fila = db.execute(
            """SELECT id FROM conversaciones
                WHERE empresa_id = %s AND proyecto_id = %s AND usuario_id = %s AND agente = %s AND id = %s
                FOR UPDATE""",
            (*params, conversacion_id),
        ).fetchone()
        if fila is None:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return fila["id"]


def _usuario_documentador(request: Request) -> dict:
    with pool().connection() as db:
        return require_user(request, security.get_optional_user(request, db))


async def check_csrf(request: Request, user=Depends(_usuario_documentador)) -> dict:
    """Usa el control CSRF común con la sesión ya leída y la conexión devuelta al pool."""
    return await security.check_csrf(request, user)


def _marcar_fallido(empresa_id: int, conversacion: int, run: int) -> None:
    with pool().connection() as db:
        db.execute(
            """UPDATE agent_runs SET estado = 'fallido'
                WHERE empresa_id = %s AND conversacion_id = %s AND id = %s AND estado = 'en_curso'""",
            (empresa_id, conversacion, run),
        )


@router.post("/proyectos/{codigo}/documentador")
def preguntar_documentador(codigo: str, pregunta: Pregunta, request: Request, user=Depends(check_csrf)):
    mensaje = pregunta.mensaje.replace("\x00", " ").strip()
    empresa_id = user["empresa_id"]
    with pool().connection() as db:
        proyecto = obtener_proyecto(db, user, codigo)
        if not mensaje:
            raise HTTPException(status_code=400, detail="Escribí una consulta")
        try:
            modelo = documentador.modelo_configurado()
        except documentador.ConfiguracionDocumentador as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        conversacion = _abrir_conversacion(db, user, proyecto, pregunta.conversacion_id)
        entrada = [{"role": fila["rol"], "content": fila["contenido"]}
                   for fila in _mensajes(db, user, proyecto, conversacion)[-12:]]
        entrada.append({"role": "user", "content": mensaje})
        run = db.execute(
            """INSERT INTO agent_runs (empresa_id, conversacion_id, modelo, estado)
               VALUES (%s, %s, %s, 'en_curso') RETURNING id""",
            (empresa_id, conversacion, modelo),
        ).fetchone()["id"]

    contexto = ContextoDocumentador(user, proyecto, run)
    try:
        resultado = asyncio.run(documentador.ejecutar(contexto, entrada, modelo))
    except Exception as error:
        _marcar_fallido(empresa_id, conversacion, run)
        log.warning("El run %s del Documentador falló (%s)", run, type(error).__name__)
        raise HTTPException(status_code=503, detail="El Documentador no pudo responder. Probá de nuevo.") from None

    try:
        with pool().connection() as db:
            actual = security.get_optional_user(request, db)
            if actual is None or (actual["empresa_id"], actual["id"]) != (empresa_id, user["id"]):
                raise HTTPException(status_code=404, detail="Proyecto no encontrado")
            proyecto_actual = obtener_proyecto(db, actual, codigo)
            if proyecto_actual["id"] != proyecto["id"]:
                raise HTTPException(status_code=404, detail="Proyecto no encontrado")
            # Mantiene juntos pregunta y respuesta aunque se cierren dos turnos simultáneos.
            _abrir_conversacion(db, actual, proyecto_actual, conversacion)
            disponibles = ids_visibles(db, actual, proyecto_actual, list(contexto.fuentes))
            respuesta, citas = documentador.verificar_respuesta(contexto, resultado["salida"], disponibles)
            db.execute(
                """INSERT INTO mensajes (empresa_id, conversacion_id, rol, contenido, citas)
                   VALUES (%s, %s, 'user', %s, '[]'), (%s, %s, 'assistant', %s, %s)""",
                (empresa_id, conversacion, mensaje, empresa_id, conversacion, respuesta, Jsonb(citas)),
            )
            db.execute(
                """UPDATE agent_runs SET estado = 'hecho', tokens_entrada = %s, tokens_salida = %s, estado_sdk = %s
                    WHERE empresa_id = %s AND conversacion_id = %s AND id = %s""",
                (resultado["tokens_entrada"], resultado["tokens_salida"], Jsonb(resultado["estado_sdk"]),
                 empresa_id, conversacion, run),
            )
            auditoria.registrar(db, actual, "agente.consulta", proyecto_id=proyecto["id"], objeto="conversacion",
                                objeto_id=conversacion, detalle={"agente": _AGENTE, "run_id": run}, request=request)
    except Exception:
        _marcar_fallido(empresa_id, conversacion, run)
        raise
    return JSONResponse({"conversacion_id": conversacion, "respuesta": respuesta, "citas": citas}, headers=_PRIVADO)


def _mensajes_recientes(db, empresa, conversacion):
    filas = db.execute(
        """SELECT rol,contenido,citas FROM mensajes WHERE empresa_id=%s AND conversacion_id=%s
            ORDER BY id DESC LIMIT 12""", (empresa, conversacion),
    ).fetchall()
    return list(reversed(filas))


@router.get("/presupuestos/{presupuesto_id:int}/agente")
def historial_presupuestos(presupuesto_id: int, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    _, proyecto = obtener_presupuesto(db, user, presupuesto_id)
    return _historial_agente(db, user, proyecto, presupuestos)


@router.get("/proyecto/{codigo}/obra/agente")
def historial_obra(codigo: str, user=Depends(require_user), db: Connection = Depends(db_dependency)):
    return _historial_agente(db, user, obtener_obra(db, user, codigo), obra)


def _historial_agente(db, user, proyecto, agente):
    empresa = user["empresa_id"]
    fila = db.execute(
        """SELECT id FROM conversaciones WHERE empresa_id=%s AND proyecto_id=%s AND usuario_id=%s AND agente=%s""",
        _alcance(user, proyecto, agente.SLUG),
    ).fetchone()
    if not fila:
        return JSONResponse({"conversacion_id": None, "mensajes": []}, headers=_PRIVADO)
    conv = fila["id"]
    mensajes = _mensajes_recientes(db, empresa, conv)
    pendiente = db.execute(
        """SELECT id,estado_sdk FROM agent_runs WHERE empresa_id=%s AND conversacion_id=%s
            AND estado='esperando_aprobacion' ORDER BY id DESC LIMIT 1""", (empresa, conv),
    ).fetchone()
    datos = {"conversacion_id": conv, "mensajes": mensajes}
    if pendiente:
        mensajes.append({"rol": "user", "contenido": pendiente["estado_sdk"]["mensaje"], "citas": []})
        contexto = aprobaciones.Contexto(user, proyecto, pendiente["id"], conv)
        datos.update(aprobaciones._solicitudes(db, agente.REGISTRO, contexto))
    return JSONResponse(datos, headers=_PRIVADO)


@router.post("/presupuestos/{presupuesto_id:int}/agente")
def preguntar_presupuestos(presupuesto_id: int, pregunta: Pregunta, user=Depends(check_csrf)):
    return _preguntar_agente(pregunta, user, presupuestos, lambda db: obtener_presupuesto(db, user, presupuesto_id)[1],
                             f"La ficha abierta corresponde al presupuesto ID {presupuesto_id}.",
                             config.PRESUPUESTOS_CONSULTAS_POR_HORA)


@router.post("/proyecto/{codigo}/obra/agente")
def preguntar_obra(codigo: str, pregunta: Pregunta, user=Depends(check_csrf)):
    return _preguntar_agente(pregunta, user, obra, lambda db: obtener_obra(db, user, codigo),
                             f"La fecha local del parte de hoy es {hoy_local().isoformat()}.",
                             config.OBRA_CONSULTAS_POR_HORA)


def _preguntar_agente(pregunta, user, agente, resolver_proyecto, indicacion, limite):
    mensaje = pregunta.mensaje.replace("\x00", " ").strip()
    if not mensaje:
        raise HTTPException(400, "Escribí una consulta.")
    empresa = user["empresa_id"]
    with pool().connection() as db:
        proyecto = resolver_proyecto(db)
        try:
            modelo = agente.modelo_configurado()
        except presupuestos.ConfiguracionPresupuestos as error:
            raise HTTPException(503, str(error)) from error
        db.execute("SELECT id FROM usuarios WHERE empresa_id=%s AND id=%s FOR UPDATE", (empresa, user["id"]))
        recientes = db.execute(
            """SELECT count(*) AS cantidad FROM agent_runs r JOIN conversaciones c
                ON c.empresa_id=r.empresa_id AND c.id=r.conversacion_id
                WHERE r.empresa_id=%s AND c.usuario_id=%s AND c.agente=%s
                  AND r.creado_en>=now()-interval '1 hour'""", (empresa, user["id"], agente.SLUG),
        ).fetchone()["cantidad"]
        if recientes >= max(1, limite):
            raise HTTPException(429, f"Alcanzaste el límite de consultas por hora del agente {agente.SLUG.capitalize()}.")
        conv = _abrir_conversacion(db, user, proyecto, pregunta.conversacion_id, agente=agente.SLUG)
        if db.execute(
            """SELECT 1 FROM agent_runs WHERE empresa_id=%s AND conversacion_id=%s
                AND estado IN ('en_curso','esperando_aprobacion') LIMIT 1""", (empresa, conv),
        ).fetchone():
            raise HTTPException(409, "Resolvé la consulta pendiente antes de iniciar otra.")
        entrada = [{"role": "developer", "content": indicacion}]
        entrada.extend({"role": fila["rol"], "content": fila["contenido"]}
                       for fila in _mensajes_recientes(db, empresa, conv))
        entrada.append({"role": "user", "content": mensaje})
        run = db.execute(
            """INSERT INTO agent_runs(empresa_id,conversacion_id,modelo,estado)
               VALUES (%s,%s,%s,'en_curso') RETURNING id""", (empresa, conv, modelo),
        ).fetchone()["id"]
    contexto = aprobaciones.Contexto(user, proyecto, run, conv)
    try:
        datos = asyncio.run(aprobaciones.iniciar(agente.SLUG, modelo, contexto, entrada))
    except aprobaciones.FalloModelo as error:
        raise HTTPException(503, str(error)) from error
    return JSONResponse(datos, headers=_PRIVADO)


def _decidir(run_id, llamada_id, aprobar, request, user):
    try:
        datos = aprobaciones.decidir(user, run_id, llamada_id, aprobar, request)
    except aprobaciones.FalloModelo as error:
        raise HTTPException(503, str(error)) from error
    return JSONResponse(datos, headers=_PRIVADO)


@router.post("/agentes/runs/{run_id}/tool-calls/{llamada_id}/aprobar")
def aprobar(run_id: int, llamada_id: int, request: Request, user=Depends(check_csrf)):
    return _decidir(run_id, llamada_id, True, request, user)


@router.post("/agentes/runs/{run_id}/tool-calls/{llamada_id}/rechazar")
def rechazar(run_id: int, llamada_id: int, request: Request, user=Depends(check_csrf)):
    return _decidir(run_id, llamada_id, False, request, user)
