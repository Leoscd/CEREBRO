"""Búsqueda de documentación con filtros de empresa, proyecto y archivo."""
from markupsafe import Markup, escape
from psycopg import Connection

from app.permisos import archivos_visibles_sql

_RESALTADO = "StartSel=\x01, StopSel=\x02, MaxFragments=2, MaxWords=25, MinWords=8"
_ARCHIVOS = """
    JOIN versiones_archivo v ON v.empresa_id = c.empresa_id AND v.id = c.version_id
    JOIN archivos a ON a.empresa_id = c.empresa_id AND a.proyecto_id = c.proyecto_id
                    AND a.id = v.archivo_id AND a.version_actual_id = v.id
"""


def _marcar(fragmento: str) -> Markup:
    return escape(fragmento).replace("\x01", Markup("<mark>")).replace("\x02", Markup("</mark>"))


def buscar_palabras(db: Connection, u: dict, proyecto: dict, consulta: str, limite: int = 20) -> list[dict]:
    consulta = consulta.strip()
    if not consulta or limite <= 0:
        return []
    acceso, params = archivos_visibles_sql(u)
    filas = db.execute(
        f"""SELECT c.id, a.id AS archivo_id, a.nombre, c.pagina, c.texto,
                   ts_headline('spanish', c.texto, q.terminos, %s) AS fragmento
              FROM chunks c {_ARCHIVOS}
             CROSS JOIN websearch_to_tsquery('spanish', %s) AS q(terminos)
             WHERE c.empresa_id = %s AND c.proyecto_id = %s AND ({acceso}) AND c.tsv @@ q.terminos
             ORDER BY ts_rank(c.tsv, q.terminos) DESC, c.id LIMIT %s""",
        [_RESALTADO, consulta, u["empresa_id"], proyecto["id"], *params, limite],
    ).fetchall()
    for fila in filas:
        fila["fragmento"] = _marcar(fila["fragmento"])
    return filas


buscar = buscar_palabras
