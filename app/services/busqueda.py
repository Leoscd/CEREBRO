"""Búsqueda de documentación con filtros de empresa, proyecto y archivo."""
import logging

from markupsafe import Markup, escape
from openai import OpenAIError
from psycopg import Connection

from app.permisos import archivos_visibles_sql, es_cliente, proyectos_visibles_sql
from app.services import embeddings

log = logging.getLogger(__name__)
_RESALTADO = "StartSel=\x01, StopSel=\x02, MaxFragments=2, MaxWords=25, MinWords=8"
FUENTES_SQL = """
    FROM chunks c
    LEFT JOIN versiones_archivo v ON v.empresa_id = c.empresa_id AND v.id = c.version_id
    LEFT JOIN archivos a ON a.empresa_id = c.empresa_id AND a.proyecto_id = c.proyecto_id
                         AND a.id = v.archivo_id AND a.version_actual_id = v.id
    LEFT JOIN biblioteca_documentos b ON b.empresa_id = c.empresa_id AND b.id = c.biblioteca_id
"""
CAMPOS_FUENTE = "c.id, a.id AS archivo_id, b.id AS biblioteca_id, coalesce(a.nombre, b.titulo) AS nombre, c.pagina, c.texto"


def fuentes_visibles_sql(u: dict, proyecto: dict) -> tuple[str, list]:
    """Filtro para las filas de FUENTES_SQL. Valida también el proyecto para la biblioteca."""
    acceso_archivo, params_archivo = archivos_visibles_sql(u)
    acceso_proyecto, params_proyecto = proyectos_visibles_sql(u)
    condicion = f"""c.empresa_id = %s
                     AND EXISTS (SELECT 1 FROM proyectos p WHERE p.id = %s AND {acceso_proyecto})
                     AND ((c.proyecto_id = %s AND {acceso_archivo})
                          OR (b.estado = 'aprobado' AND %s))"""
    return condicion, [u["empresa_id"], proyecto["id"], *params_proyecto,
                       proyecto["id"], *params_archivo, not es_cliente(u)]


def _marcar(fragmento: str) -> Markup:
    return escape(fragmento).replace("\x01", Markup("<mark>")).replace("\x02", Markup("</mark>"))


def buscar_palabras(db: Connection, u: dict, proyecto: dict, consulta: str, limite: int = 20) -> list[dict]:
    consulta = consulta.strip()
    if not consulta or limite <= 0:
        return []
    acceso, params = fuentes_visibles_sql(u, proyecto)
    filas = db.execute(
        f"""SELECT {CAMPOS_FUENTE},
                   ts_headline('spanish', c.texto, q.terminos, %s) AS fragmento
              {FUENTES_SQL}
             CROSS JOIN websearch_to_tsquery('spanish', %s) AS q(terminos)
             WHERE ({acceso}) AND c.tsv @@ q.terminos
             ORDER BY ts_rank(c.tsv, q.terminos) DESC, c.id LIMIT %s""",
        [_RESALTADO, consulta, *params, limite],
    ).fetchall()
    for fila in filas:
        fila["fragmento"] = _marcar(fila["fragmento"])
    return filas


def _buscar_vectorial(db: Connection, u: dict, proyecto: dict, consulta: str, limite: int) -> list[dict]:
    acceso, params = fuentes_visibles_sql(u, proyecto)
    if db.execute(
        f"SELECT 1 {FUENTES_SQL} WHERE ({acceso}) AND c.embedding IS NOT NULL LIMIT 1", params,
    ).fetchone() is None:
        return []
    try:
        vector = embeddings.vector_sql(embeddings.embeber([consulta])[0])
    except (embeddings.ConfiguracionEmbeddings, OpenAIError) as error:
        log.warning("Búsqueda semántica no disponible (%s)", type(error).__name__)
        return []
    return db.execute(
        f"""WITH visibles AS MATERIALIZED (
                SELECT {CAMPOS_FUENTE}, c.embedding {FUENTES_SQL}
                 WHERE ({acceso}) AND c.embedding IS NOT NULL
            ), distancias AS (
                SELECT id, archivo_id, biblioteca_id, nombre, pagina, texto, left(texto, 350) AS fragmento,
                       embedding <=> %s::vector AS distancia
                  FROM visibles
            )
            SELECT * FROM distancias WHERE distancia <= 0.75 ORDER BY distancia, id LIMIT %s""",
        [*params, vector, limite],
    ).fetchall()


def buscar(db: Connection, u: dict, proyecto: dict, consulta: str, limite: int = 10) -> list[dict]:
    consulta = consulta.strip()
    if not consulta or limite <= 0:
        return []
    candidatos = max(20, limite * 3)
    por_palabras = buscar_palabras(db, u, proyecto, consulta, candidatos)
    por_vector = _buscar_vectorial(db, u, proyecto, consulta, candidatos)
    filas = {}
    puntajes = {}
    for resultados in (por_palabras, por_vector):
        for rango, fila in enumerate(resultados, 1):
            chunk = fila["id"]
            filas.setdefault(chunk, fila)
            puntajes[chunk] = puntajes.get(chunk, 0.0) + 1 / (60 + rango)
    elegidos = sorted(puntajes, key=lambda chunk: (-puntajes[chunk], chunk))[:limite]
    return [filas[chunk] for chunk in elegidos]
