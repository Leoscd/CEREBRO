"""Chat del Documentador y su historial por persona y proyecto."""
import asyncio

from agents import AgentsException
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import OpenAIError
from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.agentes import documentador
from app.agentes.herramientas import ContextoDocumentador, ids_visibles
from app.db import db_dependency
from app.permisos import obtener_proyecto
from app.security import check_csrf, require_user
from app.services import auditoria

router = APIRouter(prefix="/proyectos")
_AGENTE = "documentador"
_PRIVADO = {"Cache-Control": "private, no-store"}


class Pregunta(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1600)
    conversacion_id: int | None = Field(default=None, ge=1, le=2**63 - 1)


def _alcance(usuario: dict, proyecto: dict) -> tuple:
    return usuario["empresa_id"], proyecto["id"], usuario["id"], _AGENTE


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


@router.get("/{codigo}/documentador")
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


def _abrir_conversacion(db: Connection, usuario: dict, proyecto: dict, conversacion_id: int | None) -> int:
    params = _alcance(usuario, proyecto)
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


@router.post("/{codigo}/documentador")
def preguntar_documentador(codigo: str, pregunta: Pregunta, request: Request,
                           user=Depends(check_csrf), db: Connection = Depends(db_dependency)):
    proyecto = obtener_proyecto(db, user, codigo)
    mensaje = pregunta.mensaje.replace("\x00", " ").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="Escribí una consulta")
    try:
        modelo = documentador.modelo_configurado()
    except documentador.ConfiguracionDocumentador as error:
        raise HTTPException(status_code=503, detail=str(error)) from None

    empresa_id = user["empresa_id"]
    conversacion = _abrir_conversacion(db, user, proyecto, pregunta.conversacion_id)
    entrada = [{"role": fila["rol"], "content": fila["contenido"]}
               for fila in _mensajes(db, user, proyecto, conversacion)[-12:]]
    entrada.append({"role": "user", "content": mensaje})
    run = db.execute(
        """INSERT INTO agent_runs (empresa_id, conversacion_id, modelo, estado)
           VALUES (%s, %s, %s, 'en_curso') RETURNING id""",
        (empresa_id, conversacion, modelo),
    ).fetchone()["id"]
    contexto = ContextoDocumentador(db, user, proyecto, run)
    try:
        resultado = asyncio.run(documentador.ejecutar(contexto, entrada, modelo))
    except (OpenAIError, AgentsException, TimeoutError):
        db.rollback()
        raise HTTPException(status_code=503, detail="El Documentador no pudo responder. Probá de nuevo.") from None

    obtener_proyecto(db, user, codigo)
    respuesta, citas = resultado["respuesta"], resultado["citas"]
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
    auditoria.registrar(db, user, "agente.consulta", proyecto_id=proyecto["id"], objeto="conversacion",
                        objeto_id=conversacion, detalle={"agente": _AGENTE, "run_id": run}, request=request)
    db.commit()
    return JSONResponse({"conversacion_id": conversacion, "respuesta": respuesta, "citas": citas}, headers=_PRIVADO)
