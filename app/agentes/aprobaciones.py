"""Pausa y reanudación de herramientas de escritura con decisión humana."""

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from agents import Agent, FunctionTool, RunConfig, Runner, RunState
from agents.strict_schema import ensure_strict_json_schema
from fastapi import HTTPException
from openai.types.responses import ResponseFunctionToolCall
from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.db import pool
from app.permisos import exigir, obtener_proyecto
from app.services import auditoria

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Contexto:
    usuario: dict
    proyecto: dict
    run_id: int
    conversacion_id: int


@dataclass(frozen=True)
class Escritura:
    nombre: str
    descripcion: str
    argumentos: type[BaseModel]
    permiso: Callable[[Connection, dict, dict], bool]
    ejecutar: Callable[[Connection, dict, dict, BaseModel], str]


@dataclass(frozen=True)
class AgenteRegistrado:
    abrir: Callable[[str, list[FunctionTool]], AbstractAsyncContextManager[Agent]]
    escrituras: tuple[Escritura, ...]

    def regla(self, nombre: str) -> Escritura:
        regla = next((r for r in self.escrituras if r.nombre == nombre), None)
        if regla is None:
            raise ValueError("La herramienta no está registrada para este agente.")
        return regla


AGENTES: dict[str, AgenteRegistrado] = {}


class FalloModelo(RuntimeError):
    pass


def _autorizado(db, contexto):
    usuario = contexto.usuario
    actual = db.execute(
        """SELECT * FROM usuarios WHERE empresa_id=%s AND id=%s AND sesion_version=%s AND activo""",
        (usuario["empresa_id"], usuario["id"], usuario["sesion_version"]),
    ).fetchone()
    if actual is None:
        raise HTTPException(404, "Ejecución no encontrada")
    proyecto = obtener_proyecto(db, actual, contexto.proyecto["codigo"])
    if proyecto["id"] != contexto.proyecto["id"]:
        raise HTTPException(404, "Ejecución no encontrada")
    return actual, proyecto


def _invocar(regla, contexto, sdk_id, argumentos):
    empresa = contexto.usuario["empresa_id"]
    datos = regla.argumentos.model_validate_json(argumentos)
    exactos = datos.model_dump(mode="json")
    with pool().connection() as db, db.transaction():
        usuario, proyecto = _autorizado(db, contexto)
        exigir(regla.permiso(db, usuario, proyecto))
        llamada = db.execute(
            """SELECT id,estado,argumentos,resultado_resumen FROM tool_calls
                WHERE empresa_id=%s AND agent_run_id=%s AND sdk_call_id=%s AND herramienta=%s
                FOR UPDATE""", (empresa, contexto.run_id, sdk_id, regla.nombre),
        ).fetchone()
        if llamada is None or llamada["argumentos"] != exactos or llamada["estado"] not in {"aprobada", "ejecutada"}:
            raise RuntimeError("La llamada de escritura no coincide con una aprobación.")
        if llamada["estado"] == "ejecutada":
            return llamada["resultado_resumen"]
        resultado = regla.ejecutar(db, usuario, proyecto, datos)
        db.execute(
            """UPDATE tool_calls SET estado='ejecutada',resultado_resumen=%s
                WHERE empresa_id=%s AND agent_run_id=%s AND id=%s""",
            (resultado, empresa, contexto.run_id, llamada["id"]),
        )
        return resultado


def _tool(regla):
    async def invocar(ctx, argumentos):
        return _invocar(regla, ctx.context, ctx.tool_call_id, argumentos)

    return FunctionTool(
        name=regla.nombre, description=regla.descripcion, needs_approval=True,
        params_json_schema=ensure_strict_json_schema(regla.argumentos.model_json_schema()),
        on_invoke_tool=invocar,
    )


def _llamada(registro, interrupcion):
    cruda = interrupcion.raw_item
    if not isinstance(cruda, ResponseFunctionToolCall):
        raise TypeError("Tipo de aprobación de herramienta no admitido.")
    regla = registro.regla(cruda.name)
    return cruda.call_id, regla, regla.argumentos.model_validate_json(cruda.arguments).model_dump(mode="json")


def _solicitudes(db, registro, contexto):
    filas = db.execute(
        """SELECT id,herramienta,argumentos FROM tool_calls WHERE empresa_id=%s AND agent_run_id=%s
            AND estado='pendiente' AND sdk_call_id IS NOT NULL ORDER BY id""",
        (contexto.usuario["empresa_id"], contexto.run_id),
    ).fetchall()
    return {
        "estado": "esperando_aprobacion", "run_id": contexto.run_id, "conversacion_id": contexto.conversacion_id,
        "aprobaciones": [fila | {"descripcion": registro.regla(fila["herramienta"]).descripcion} for fila in filas],
    }


def _guardar(registro, slug, contexto, resultado, mensaje):
    empresa = contexto.usuario["empresa_id"]
    uso = resultado.context_wrapper.usage
    sdk = resultado.to_state().to_json(context_serializer=lambda _: {}, strict_context=True)
    estado_sdk = Jsonb({"sdk": sdk, "mensaje": mensaje})
    with pool().connection() as db:
        usuario, proyecto = _autorizado(db, contexto)
        run = db.execute(
            """SELECT r.id FROM agent_runs r JOIN conversaciones c
                 ON c.empresa_id=r.empresa_id AND c.id=r.conversacion_id
               WHERE r.empresa_id=%s AND r.id=%s AND r.conversacion_id=%s AND r.estado='en_curso'
                 AND c.usuario_id=%s AND c.proyecto_id=%s AND c.agente=%s FOR UPDATE OF r""",
            (empresa, contexto.run_id, contexto.conversacion_id, usuario["id"], proyecto["id"], slug),
        ).fetchone()
        if run is None:
            raise HTTPException(409, "La ejecución cambió de estado.")
        if resultado.interruptions:
            for interrupcion in resultado.interruptions:
                sdk_id, regla, argumentos = _llamada(registro, interrupcion)
                db.execute(
                    """INSERT INTO tool_calls(empresa_id,agent_run_id,herramienta,argumentos,resultado_resumen,estado,sdk_call_id)
                       VALUES (%s,%s,%s,%s,'','pendiente',%s)""",
                    (empresa, contexto.run_id, regla.nombre, Jsonb(argumentos), sdk_id),
                )
            estado = "esperando_aprobacion"
            payload = _solicitudes(db, registro, contexto)
        else:
            salida = resultado.final_output
            if isinstance(salida, BaseModel):
                salida = salida.model_dump_json()
            elif not isinstance(salida, str):
                salida = json.dumps(salida, ensure_ascii=False)
            db.execute(
                """INSERT INTO mensajes(empresa_id,conversacion_id,rol,contenido)
                   VALUES (%s,%s,'user',%s),(%s,%s,'assistant',%s)""",
                (empresa, contexto.conversacion_id, mensaje, empresa, contexto.conversacion_id, salida),
            )
            estado = "hecho"
            payload = {"estado": estado, "respuesta": salida, "run_id": contexto.run_id,
                       "conversacion_id": contexto.conversacion_id, "citas": [], "aprobaciones": []}
        db.execute(
            """UPDATE agent_runs SET estado=%s,estado_sdk=%s,tokens_entrada=%s,tokens_salida=%s
                WHERE empresa_id=%s AND id=%s""",
            (estado, estado_sdk, uso.input_tokens, uso.output_tokens, empresa, contexto.run_id),
        )
        return payload


def _fallido(contexto):
    empresa = contexto.usuario["empresa_id"]
    with pool().connection() as db:
        run = db.execute(
            """UPDATE agent_runs SET estado='fallido'
                WHERE empresa_id=%s AND id=%s AND estado='en_curso' RETURNING id""", (empresa, contexto.run_id),
        ).fetchone()
        if run:
            db.execute(
                """UPDATE tool_calls SET estado='fallida' WHERE empresa_id=%s AND agent_run_id=%s
                    AND estado IN ('pendiente','aprobada') AND sdk_call_id IS NOT NULL""",
                (empresa, contexto.run_id),
            )


async def _correr(registro, slug, modelo, contexto, mensaje, *, entrada=None, estado=None, decisiones=None):
    try:
        async with registro.abrir(modelo, [_tool(regla) for regla in registro.escrituras]) as agente:
            if estado is not None:
                entrada = await RunState.from_json(agente, estado, context_override=contexto)
                for interrupcion in entrada.get_interruptions():
                    sdk_id, regla, argumentos = _llamada(registro, interrupcion)
                    decision = decisiones.get(sdk_id)
                    if not decision or (decision["herramienta"], decision["argumentos"]) != (regla.nombre, argumentos):
                        raise ValueError("La decisión no corresponde a la llamada que se mostró.")
                    if decision["estado"] == "aprobada":
                        entrada.approve(interrupcion)
                    else:
                        entrada.reject(interrupcion, rejection_message=decision["resultado_resumen"])
            resultado = await Runner.run(
                agente, entrada, context=contexto if estado is None else None, max_turns=12, run_config=RunConfig(tracing_disabled=True),
            )
        return _guardar(registro, slug, contexto, resultado, mensaje)
    except Exception as error:
        _fallido(contexto)
        if isinstance(error, HTTPException):
            raise
        log.warning("Falló la ejecución con aprobaciones %s (%s)", contexto.run_id, type(error).__name__)
        raise FalloModelo("El agente no pudo completar la ejecución.") from None


async def iniciar(slug: str, modelo: str, contexto: Contexto, entrada: list[dict]) -> dict:
    """Ejecuta un run ya creado por el agente y guarda su pausa o respuesta."""
    return await _correr(AGENTES[slug], slug, modelo, contexto, entrada[-1]["content"], entrada=entrada)


def decidir(usuario: dict, run_id: int, llamada_id: int, aprobar: bool, request) -> dict:
    empresa = usuario["empresa_id"]
    # Fase 1: autorización y decisión durable. El bloqueo del run ordena decisiones simultáneas.
    with pool().connection() as db:
        run = db.execute(
            """SELECT r.estado,r.estado_sdk,r.modelo,r.conversacion_id,c.agente,p.codigo
                 FROM agent_runs r JOIN conversaciones c ON c.empresa_id=r.empresa_id AND c.id=r.conversacion_id
                 JOIN proyectos p ON p.empresa_id=c.empresa_id AND p.id=c.proyecto_id
                WHERE r.empresa_id=%s AND r.id=%s AND c.usuario_id=%s FOR UPDATE OF r""",
            (empresa, run_id, usuario["id"]),
        ).fetchone()
        if run is None:
            raise HTTPException(404, "Ejecución no encontrada")
        proyecto = obtener_proyecto(db, usuario, run["codigo"])
        contexto = Contexto(usuario, proyecto, run_id, run["conversacion_id"])
        usuario, proyecto = _autorizado(db, contexto)
        llamada = db.execute(
            """SELECT herramienta,estado FROM tool_calls WHERE empresa_id=%s AND agent_run_id=%s
                AND id=%s AND sdk_call_id IS NOT NULL""",
            (empresa, run_id, llamada_id),
        ).fetchone()
        registro = AGENTES.get(run["agente"])
        if llamada is None or registro is None:
            raise HTTPException(404, "Solicitud no encontrada")
        if run["estado"] != "esperando_aprobacion" or llamada["estado"] != "pendiente":
            raise HTTPException(409, "Esta solicitud ya fue resuelta.")
        regla = registro.regla(llamada["herramienta"])
        exigir(regla.permiso(db, usuario, proyecto))
        nuevo_estado = "aprobada" if aprobar else "rechazada"
        rechazo = "" if aprobar else f"rechazado por {usuario['nombre'] or usuario['email']}"
        db.execute(
            """UPDATE tool_calls SET estado=%s,resultado_resumen=%s,decidido_en=now()
                WHERE empresa_id=%s AND agent_run_id=%s AND id=%s AND estado='pendiente'""",
            (nuevo_estado, rechazo, empresa, run_id, llamada_id),
        )
        auditoria.registrar(
            db, usuario, "agente.aprobacion" if aprobar else "agente.rechazo", proyecto_id=proyecto["id"],
            objeto="tool_call", objeto_id=llamada_id, detalle={"run_id": run_id}, request=request,
        )
        solicitudes = _solicitudes(db, registro, contexto)
        if solicitudes["aprobaciones"]:
            return solicitudes
        decisiones = {fila["sdk_call_id"]: fila for fila in db.execute(
            """SELECT sdk_call_id,herramienta,argumentos,estado,resultado_resumen FROM tool_calls
                WHERE empresa_id=%s AND agent_run_id=%s AND estado IN ('aprobada','rechazada')
                  AND sdk_call_id IS NOT NULL""", (empresa, run_id),
        )}
        db.execute(
            "UPDATE agent_runs SET estado='en_curso' WHERE empresa_id=%s AND id=%s AND estado='esperando_aprobacion'",
            (empresa, run_id),
        )
        estado = run["estado_sdk"]
    # Fase 2: el SDK retoma sin conexión prestada. Cada efecto toma una transacción propia.
    # Fase 3: _guardar registra la siguiente pausa o la respuesta final.
    return asyncio.run(_correr(registro, run["agente"], run["modelo"], contexto, estado["mensaje"],
                               estado=estado["sdk"], decisiones=decisiones))
