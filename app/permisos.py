"""Reglas de acceso, en un solo lugar (portado de GESTION-OBRAS/apps/cuentas/permisos.py).

- admin: ve y administra todo dentro de su empresa.
- miembro: ve los proyectos donde está asignado; actúa según su rol en el proyecto.
- cliente: ve solo los proyectos de su cliente (y, desde M1, lo compartido con él).

Regla de oro: `empresa_id` y el usuario salen SIEMPRE de la sesión. Toda consulta de
proyectos pasa por `proyectos_visibles_sql` o `obtener_proyecto`, que ya filtran.
"""
from fastapi import HTTPException
from psycopg import Connection

ROLES_PROYECTO = ("director", "colaborador", "dt", "administracion", "lector")
ROLES_ESCRITURA = {"director", "colaborador", "dt", "administracion"}


def es_admin(u: dict) -> bool:
    return u["rol_empresa"] == "admin"


def es_cliente(u: dict) -> bool:
    return u["rol_empresa"] == "cliente"


def proyectos_visibles_sql(u: dict, alias: str = "p") -> tuple[str, list]:
    """Condición SQL (y parámetros) que limita `proyectos {alias}` a lo que el usuario ve."""
    cond = f"{alias}.empresa_id = %s"
    params: list = [u["empresa_id"]]
    if es_admin(u):
        return cond, params
    if es_cliente(u):
        return cond + f" AND {alias}.cliente_id = %s", params + [u["cliente_id"]]
    return (
        cond + f" AND EXISTS (SELECT 1 FROM proyecto_miembros pm"
        f" WHERE pm.proyecto_id = {alias}.id AND pm.usuario_id = %s)",
        params + [u["id"]],
    )


def rol_en_proyecto(db: Connection, u: dict, proyecto_id: int) -> str | None:
    fila = db.execute(
        "SELECT rol FROM proyecto_miembros WHERE proyecto_id = %s AND usuario_id = %s",
        (proyecto_id, u["id"]),
    ).fetchone()
    return fila["rol"] if fila else None


def obtener_proyecto(db: Connection, u: dict, codigo: str) -> dict:
    """El proyecto si el usuario lo puede ver; si no, 404 (no se revela que existe)."""
    cond, params = proyectos_visibles_sql(u)
    fila = db.execute(
        f"""SELECT p.*, t.slug AS tipo_slug, t.nombre AS tipo_nombre, t.disciplina,
                   c.nombre AS cliente_nombre
              FROM proyectos p
              JOIN tipos_proyecto t ON t.id = p.tipo_proyecto_id
              LEFT JOIN clientes c ON c.id = p.cliente_id
             WHERE p.codigo = %s AND {cond}""",
        [codigo, *params],
    ).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    fila["mi_rol"] = "admin" if es_admin(u) else rol_en_proyecto(db, u, fila["id"])
    return fila


def puede_crear_proyecto(u: dict) -> bool:
    return es_admin(u)


def puede_editar_proyecto(u: dict, proyecto: dict) -> bool:
    return es_admin(u) or proyecto.get("mi_rol") == "director"


def puede_gestionar_equipo(u: dict, proyecto: dict) -> bool:
    return puede_editar_proyecto(u, proyecto)


def puede_escribir_en_proyecto(u: dict, proyecto: dict) -> bool:
    """Subir archivos, cargar avances, usar herramientas que escriben (M1+)."""
    return es_admin(u) or proyecto.get("mi_rol") in ROLES_ESCRITURA


def puede_aprobar_planos(u: dict, proyecto: dict) -> bool:
    return es_admin(u) or proyecto.get("mi_rol") == "dt"


def puede_ver_auditoria(u: dict, proyecto: dict | None = None) -> bool:
    if proyecto is None:
        return es_admin(u)
    return es_admin(u) or proyecto.get("mi_rol") == "director"


def exigir(condicion: bool, mensaje: str = "No tenés permiso para esto") -> None:
    if not condicion:
        raise HTTPException(status_code=403, detail=mensaje)
