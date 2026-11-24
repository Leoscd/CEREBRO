"""Consultas de obra y escrituras aprobables sobre el parte del usuario."""

import json
from contextlib import contextmanager
from datetime import date
from typing import Annotated

from agents import RunContextWrapper, function_tool
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.agentes import aprobaciones
from app.agentes.herramientas_presupuestos import PropuestaInvalida
from app.db import pool
from app.permisos import es_cliente, exigir, puede_registrar_obra
from app.services import bitacora, cronograma, jobs, materiales_obra, partes
from app.services.resumen_obra import resumen_obra as obtener_resumen
from app.services.tiempo import hoy_local

Contexto = RunContextWrapper[aprobaciones.Contexto]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^\x00]+$")]


@contextmanager
def _lectura(ctx):
    with pool().connection() as db:
        usuario, proyecto = aprobaciones._autorizado(db, ctx.context)
        if es_cliente(usuario):
            raise HTTPException(404, "Obra no encontrada.")
        yield db, usuario, proyecto


def _json(datos):
    return json.dumps(datos, ensure_ascii=False, default=str)


@function_tool
def consultar_cronograma(ctx: Contexto) -> str:
    """Devuelve tareas, fechas, avance previsto, real y atrasos de la obra."""
    with _lectura(ctx) as (db, _, proyecto):
        return _json(cronograma.avance_obra(db, proyecto, hoy_local()))


@function_tool
def resumen_obra(ctx: Contexto) -> str:
    """Resume avances, atrasos, notas, alertas y el último parte confirmado."""
    with _lectura(ctx) as (db, usuario, proyecto):
        return _json(obtener_resumen(db, usuario, proyecto, hoy_local()))


@function_tool
def alertas_materiales(ctx: Contexto) -> str:
    """Lista materiales que requieren atención según sus plazos y el stock."""
    with _lectura(ctx) as (db, _, proyecto):
        return _json(materiales_obra.alertas(db, proyecto, hoy_local()))


@function_tool
def buscar_en_partes(ctx: Contexto, texto: Annotated[Texto, Field(max_length=240)]) -> str:
    """Busca texto en los partes confirmados de la obra."""
    with _lectura(ctx) as (db, usuario, proyecto):
        return _json(bitacora.buscar_en_partes(db, usuario, proyecto, texto))


@function_tool
def ultimos_partes(ctx: Contexto, cantidad: Annotated[int, Field(ge=1, le=20)] = 5) -> str:
    """Devuelve los últimos partes confirmados, del más reciente al más antiguo."""
    with _lectura(ctx) as (db, usuario, proyecto):
        return _json(bitacora.ultimos_partes(db, usuario, proyecto, hoy_local(), cantidad=cantidad))


class ParteDelDia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha: date


class Avance(ParteDelDia):
    tarea_id: int = Field(gt=0, le=2**63 - 1)
    avance_pb: int = Field(ge=0, le=10000)
    detalle: str = Field(max_length=1500, pattern=r"^[^\x00]*$")


class Personal(ParteDelDia):
    empresa: Texto = Field(max_length=200)
    categoria: Texto = Field(max_length=160)
    cantidad: int = Field(ge=1, le=100000)


class Nota(ParteDelDia):
    texto: Texto = Field(max_length=5000)


class Pedido(ParteDelDia):
    material: Texto = Field(max_length=200)
    cantidad: str = Field(max_length=20, pattern=r"^(?:[0-9]{1,10}(?:[.,][0-9]{1,4})?)?$")
    unidad: str = Field(max_length=40, pattern=r"^[^\x00]*$")
    detalle: str = Field(max_length=600, pattern=r"^[^\x00]*$")


def _permiso(_db, usuario, proyecto):
    return puede_registrar_obra(usuario, proyecto)


def _comprobar(db, usuario, proyecto, datos):
    if datos.fecha != hoy_local():
        raise HTTPException(409, "La propuesta debe corresponder al parte de hoy.")
    parte = partes.buscar_dia(db, proyecto, usuario, datos.fecha)
    if parte and parte["estado"] != "borrador":
        raise HTTPException(409, "Parte cerrado.")
    if isinstance(datos, Avance):
        cronograma._tarea(db, proyecto, datos.tarea_id)
    return parte


def validar_propuesta(regla):
    async def necesita_aprobacion(ctx, argumentos, _id):
        try:
            datos = regla.argumentos.model_validate(argumentos)
            with pool().connection() as db:
                usuario, proyecto = aprobaciones._autorizado(db, ctx.context)
                exigir(regla.permiso(db, usuario, proyecto))
                parte = _comprobar(db, usuario, proyecto, datos)
                if regla.nombre == "cerrar_reporte":
                    if parte is None:
                        raise HTTPException(409, "Todavía no hay un borrador para cerrar.")
                    faltantes = partes.faltantes(parte, len(partes.fotos(db, proyecto, parte["id"])))
                    if faltantes:
                        raise HTTPException(409, "Para cerrar el parte falta completar: " + ", ".join(faltantes))
        except HTTPException as error:
            raise PropuestaInvalida(error.status_code, error.detail) from error
        except ValidationError as error:
            raise PropuestaInvalida(422, "Revisá los datos propuestos para el parte.") from error
        return True

    return necesita_aprobacion


def _borrador(db, usuario, proyecto, datos):
    # Mismo orden que confirmar: primero el proyecto, después el parte.
    db.execute("SELECT id FROM proyectos WHERE empresa_id=%s AND id=%s FOR NO KEY UPDATE",
               (usuario["empresa_id"], proyecto["id"]))
    parte = _comprobar(db, usuario, proyecto, datos)
    if parte is None:
        parte, nuevo = partes.crear_borrador(db, usuario, proyecto, datos.fecha)
        if nuevo:
            jobs.encolar(db, usuario["empresa_id"], "parte.clima", {"proyecto_id": proyecto["id"], "parte_id": parte["id"]},
                         max_intentos=1)
    return partes.editable(db, proyecto, parte["id"])


def _guardar_seccion(seccion):
    def ejecutar(db, usuario, proyecto, datos):
        parte = _borrador(db, usuario, proyecto, datos)
        campos = {k: str(v) for k, v in datos.model_dump(exclude={"fecha"}).items()}
        if seccion == "resumen":
            campos["texto"] = "\n".join(filter(None, (parte["datos"]["resumen"], campos["texto"])))
        partes.actualizar_seccion(db, usuario, proyecto, parte["id"], seccion, campos)
        return _json({"parte_id": parte["id"], "estado": "borrador", "seccion": seccion})

    return ejecutar


def _cerrar(db, usuario, proyecto, datos):
    parte = _borrador(db, usuario, proyecto, datos)
    confirmado = partes.confirmar(db, usuario, proyecto, parte["id"])
    return _json({"estado": "confirmado", "numero": confirmado["numero"], "parte_id": parte["id"]})


LECTURAS = [consultar_cronograma, resumen_obra, alertas_materiales, buscar_en_partes, ultimos_partes]
ESCRITURAS = (
    aprobaciones.Escritura("registrar_avance", "Guardar avance acumulado en el parte", Avance, _permiso,
                           _guardar_seccion("avances")),
    aprobaciones.Escritura("registrar_personal", "Agregar personal al parte", Personal, _permiso,
                           _guardar_seccion("personal")),
    aprobaciones.Escritura("registrar_nota", "Agregar una nota a las observaciones del parte", Nota, _permiso,
                           _guardar_seccion("resumen")),
    aprobaciones.Escritura("registrar_pedido", "Anotar un material a pedir en los faltantes del parte", Pedido,
                           _permiso, _guardar_seccion("faltantes")),
    aprobaciones.Escritura("cerrar_reporte", "Confirmar el parte y encolar su PDF", ParteDelDia, _permiso, _cerrar),
)
