"""Herramientas del Documentador limitadas al contexto de sesión."""
import json
from dataclasses import dataclass, field

from agents import RunContextWrapper, function_tool
from psycopg import Connection
from psycopg.types.json import Jsonb

from app.db import pool
from app.permisos import archivos_visibles_sql
from app.services import busqueda


@dataclass
class ContextoDocumentador:
    usuario: dict
    proyecto: dict
    run_id: int
    fuentes: dict[int, dict] = field(default_factory=dict)


def ids_visibles(db: Connection, usuario: dict, proyecto: dict, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    acceso, params = busqueda.fuentes_visibles_sql(usuario, proyecto)
    filas = db.execute(
        f"SELECT c.id {busqueda.FUENTES_SQL} WHERE ({acceso}) AND c.id = ANY(%s)",
        [*params, ids],
    ).fetchall()
    return {fila["id"] for fila in filas}


def _registrar(db: Connection, ctx: ContextoDocumentador, herramienta: str, args: dict,
               resumen: str, estado: str = "ok") -> None:
    db.execute(
        """INSERT INTO tool_calls (empresa_id, agent_run_id, herramienta, argumentos, resultado_resumen, estado)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (ctx.usuario["empresa_id"], ctx.run_id, herramienta, Jsonb(args), resumen, estado),
    )


def _fuentes(ctx: ContextoDocumentador, filas: list[dict]) -> list[dict]:
    for fila in filas:
        ctx.fuentes[fila["id"]] = fila
    return [{"id": fila["id"], "nombre": fila["nombre"], "pagina": fila["pagina"], "texto": fila["texto"]}
            for fila in filas]


@function_tool(failure_error_function=None)
def buscar_documentacion(ctx: RunContextWrapper[ContextoDocumentador], consulta: str) -> str:
    """Busca una frase o concepto en el proyecto y sus criterios disponibles, con página y texto."""
    contexto = ctx.context
    consulta = consulta.replace("\x00", " ").strip()[:500]
    with pool().connection() as db:
        filas = busqueda.buscar(db, contexto.usuario, contexto.proyecto, consulta, limite=6)
        _registrar(db, contexto, "buscar_documentacion", {"consulta": consulta}, f"{len(filas)} fragmentos")
    return json.dumps({"fuentes": _fuentes(contexto, filas)}, ensure_ascii=False)


@function_tool(failure_error_function=None)
def leer_fragmento(ctx: RunContextWrapper[ContextoDocumentador], chunk_id: int) -> str:
    """Lee un fragmento citado por identificador, si continúa visible en este proyecto."""
    contexto = ctx.context
    acceso, params = busqueda.fuentes_visibles_sql(contexto.usuario, contexto.proyecto)
    fila = None
    with pool().connection() as db:
        if 0 < chunk_id <= 2**63 - 1:
            fila = db.execute(
                f"""SELECT {busqueda.CAMPOS_FUENTE} {busqueda.FUENTES_SQL}
                    WHERE ({acceso}) AND c.id = %s""",
                [*params, chunk_id],
            ).fetchone()
        resumen = "no encontrado" if fila is None else "1 fragmento"
        estado = "no encontrado" if fila is None else "ok"
        _registrar(db, contexto, "leer_fragmento", {"chunk_id": chunk_id}, resumen, estado)
    if fila is None:
        return '{"estado": "no encontrado", "fuentes": []}'
    return json.dumps({"fuentes": _fuentes(contexto, [fila])}, ensure_ascii=False)


@function_tool(failure_error_function=None)
def listar_archivos(ctx: RunContextWrapper[ContextoDocumentador], carpeta: str | None = None) -> str:
    """Lista archivos visibles del proyecto, opcionalmente por nombre de carpeta."""
    contexto = ctx.context
    acceso, params = archivos_visibles_sql(contexto.usuario)
    carpeta = carpeta.replace("\x00", " ").strip()[:200] if carpeta else None
    with pool().connection() as db:
        filas = db.execute(
            f"""SELECT a.id, a.nombre, c.nombre AS carpeta
                  FROM archivos a
                  JOIN carpetas c ON c.empresa_id = a.empresa_id AND c.proyecto_id = a.proyecto_id AND c.id = a.carpeta_id
                 WHERE a.proyecto_id = %s AND ({acceso}) AND (%s::text IS NULL OR c.nombre = %s)
                 ORDER BY c.posicion, a.nombre, a.id LIMIT 40""",
            [contexto.proyecto["id"], *params, carpeta, carpeta],
        ).fetchall()
        _registrar(db, contexto, "listar_archivos", {"carpeta": carpeta}, f"{len(filas)} archivos")
    return json.dumps({"archivos": filas}, ensure_ascii=False)
