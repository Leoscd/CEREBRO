"""Eventos de la obra y consultas de sus partes confirmados."""

import re

from fastapi import HTTPException

from app.permisos import es_cliente, proyectos_visibles_sql
from app.services.cronograma import normalizar

TIPOS = {"parte": "Parte", "nota": "Nota", "hito": "Hito", "avance": "Avance", "pedido": "Pedido"}


def proyecto_de_obra(db, usuario, proyecto):
    condicion, params = proyectos_visibles_sql(usuario)
    visible = None if es_cliente(usuario) else db.execute(
        f"SELECT p.id,p.empresa_id,p.codigo,p.nombre FROM proyectos p WHERE p.id=%s AND {condicion}",
        (proyecto["id"], *params),
    ).fetchone()
    if visible is None:
        raise HTTPException(404, "Obra no encontrada.")
    return visible


def bitacora(db, usuario, proyecto, desde=None, hasta=None, tipos=None):
    p = proyecto_de_obra(db, usuario, proyecto)
    if (desde and hasta and desde > hasta) or any(tipo not in TIPOS for tipo in (tipos or ())):
        raise HTTPException(400, "Revisá el período y los tipos de evento.")
    filas = db.execute(
        """WITH alcance(empresa_id,proyecto_id) AS (VALUES (%s::bigint,%s::bigint)),
                eventos(tipo,id,fecha,titulo,destino) AS (
            SELECT 'parte',r.id,r.fecha,'Parte N.º ' || r.numero,'/obra/partes/' || r.id
              FROM reportes_obra r JOIN alcance USING(empresa_id,proyecto_id) WHERE r.estado='confirmado'
            UNION ALL
            SELECT 'nota',n.id,n.fecha,n.asunto,'/obra/seguimiento#nota-' || n.id
              FROM notas_obra n JOIN alcance USING(empresa_id,proyecto_id)
            UNION ALL
            SELECT 'hito',h.id,h.fecha,h.titulo,'#hitos'
              FROM hitos h JOIN alcance USING(empresa_id,proyecto_id)
            UNION ALL
            SELECT 'avance',a.id,a.fecha,t.nombre,'/obra#tarea-' || t.id
              FROM avances_tarea a JOIN alcance USING(empresa_id,proyecto_id)
              JOIN tareas_obra t ON t.empresa_id=a.empresa_id AND t.proyecto_id=a.proyecto_id AND t.id=a.tarea_id
            UNION ALL
            SELECT 'pedido',m.id,m.fecha,m.material,'/obra/seguimiento#pedidos'
              FROM pedidos_material m JOIN alcance USING(empresa_id,proyecto_id)
        )
        SELECT * FROM eventos WHERE (%s::date IS NULL OR fecha >= %s) AND (%s::date IS NULL OR fecha <= %s)
          AND tipo=ANY(%s::text[]) ORDER BY fecha DESC,id DESC,tipo LIMIT 100""",
        (p["empresa_id"], p["id"], desde, desde, hasta, hasta, list(tipos or TIPOS)),
    ).fetchall()
    return [{**fila, "enlace": f"/proyecto/{p['codigo']}{fila['destino']}"} for fila in filas]


def _confirmados(db, proyecto, hasta=None, limite=None):
    return db.execute(
        """SELECT r.id,r.numero,r.fecha,r.datos,u.nombre AS dt_nombre
             FROM reportes_obra r JOIN usuarios u ON u.empresa_id=r.empresa_id AND u.id=r.dt_id
            WHERE r.empresa_id=%s AND r.proyecto_id=%s AND r.estado='confirmado'
              AND (%s::date IS NULL OR r.fecha<=%s)
            ORDER BY r.fecha DESC,r.numero DESC LIMIT %s""",
        (proyecto["empresa_id"], proyecto["id"], hasta, hasta, limite),
    )


def ultimos_partes(db, usuario, proyecto, hasta, *, cantidad=5):
    visible = proyecto_de_obra(db, usuario, proyecto)
    return _confirmados(db, visible, hasta, max(1, min(cantidad, 20))).fetchall()


def _textos(valor):
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for elemento in valor.values():
            yield from _textos(elemento)
    elif isinstance(valor, list):
        for elemento in valor:
            yield from _textos(elemento)


def _palabras(texto):
    return set(re.findall(r"\w+", normalizar(texto)))


def buscar_en_partes(db, usuario, proyecto, texto, *, cantidad=10):
    visible = proyecto_de_obra(db, usuario, proyecto)
    palabras = _palabras(texto)
    if not palabras:
        return []
    mejor = 0
    coincidencias = []
    for parte in _confirmados(db, visible):
        puntos, fragmento = max(
            ((len(palabras & _palabras(frag)), frag) for frag in _textos(parte["datos"])), default=(0, ""),
        )
        if puntos <= 0 or puntos < mejor:
            continue
        if puntos > mejor:
            mejor = puntos
            coincidencias = []
        if len(coincidencias) < max(1, min(cantidad, 20)):
            coincidencias.append({"id": parte["id"], "fecha": parte["fecha"], "numero": parte["numero"],
                                  "texto": fragmento[:400]})
    return coincidencias
