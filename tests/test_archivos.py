"""Carpetas de plantilla y acceso a archivos por empresa y proyecto."""
import pytest
from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app import permisos
from app.db.migrar import CARPETA


def carpetas_raiz(db, proyecto):
    return db.execute(
        """SELECT nombre, posicion FROM carpetas
            WHERE empresa_id = %s AND proyecto_id = %s AND padre_id IS NULL
            ORDER BY posicion""",
        (proyecto["empresa_id"], proyecto["id"]),
    ).fetchall()


def test_proyecto_nuevo_copia_carpetas_en_orden(db, mundo):
    proyecto = mundo["p1"]
    tipo = db.execute(
        "SELECT plantilla_carpetas FROM tipos_proyecto WHERE empresa_id = %s AND id = %s",
        (proyecto["empresa_id"], proyecto["tipo_proyecto_id"]),
    ).fetchone()
    assert tipo["plantilla_carpetas"]
    assert carpetas_raiz(db, proyecto) == [
        {"nombre": nombre, "posicion": posicion}
        for posicion, nombre in enumerate(tipo["plantilla_carpetas"])
    ]


def test_migracion_copia_carpetas_de_proyectos_existentes(db):
    db.execute("CREATE SCHEMA antes_de_archivos")
    db.execute("SET LOCAL search_path TO antes_de_archivos, public")
    db.execute((CARPETA / "0001_base.sql").read_text(encoding="utf-8"))
    empresa = db.execute("INSERT INTO empresas (nombre, slug) VALUES ('A', 'a') RETURNING id").fetchone()
    tipo = db.execute(
        """INSERT INTO tipos_proyecto (empresa_id, slug, nombre, plantilla_carpetas)
           VALUES (%s, 'tipo', 'Tipo', %s) RETURNING id""",
        (empresa["id"], Jsonb(["Planos", "Actas", "Planos"])),
    ).fetchone()
    proyecto = db.execute(
        """INSERT INTO proyectos (empresa_id, tipo_proyecto_id, codigo, nombre)
           VALUES (%s, %s, 'PR-2026-001', 'Obra') RETURNING id, empresa_id""",
        (empresa["id"], tipo["id"]),
    ).fetchone()
    db.execute((CARPETA / "0002_archivos.sql").read_text(encoding="utf-8"))
    assert carpetas_raiz(db, proyecto) == [
        {"nombre": "Planos", "posicion": 0},
        {"nombre": "Actas", "posicion": 1},
    ]


@pytest.fixture()
def archivos_mundo(db, mundo):
    def insertar(proyecto, visible=False, en_papelera=False):
        return db.execute(
            """INSERT INTO archivos (empresa_id, proyecto_id, carpeta_id, nombre, extension, mime,
                                     visible_cliente, en_papelera_en)
               SELECT empresa_id, proyecto_id, id, 'Plano.pdf', 'pdf', 'application/pdf',
                      %s, CASE WHEN %s THEN now() END
                 FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s
                 ORDER BY posicion LIMIT 1 RETURNING id""",
            (visible, en_papelera, proyecto["empresa_id"], proyecto["id"]),
        ).fetchone()["id"]

    return {
        "privado": insertar(mundo["p1"]),
        "compartido": insertar(mundo["p1"], visible=True),
        "papelera": insertar(mundo["p1"], visible=True, en_papelera=True),
        "p2": insertar(mundo["p2"], visible=True),
        "pb": insertar(mundo["pb"], visible=True),
    }


def test_archivos_visibles_por_rol(db, mundo, archivos_mundo):
    for usuario, claves in [
        ("admin_a", {"privado", "compartido", "p2"}),
        ("ana", {"privado", "compartido"}),
        ("cliente", {"compartido"}),
        ("admin_b", {"pb"}),
    ]:
        condicion, params = permisos.archivos_visibles_sql(mundo[usuario], "archivo")
        filas = db.execute(f"SELECT archivo.id FROM archivos archivo WHERE {condicion}", params).fetchall()
        assert {fila["id"] for fila in filas} == {archivos_mundo[clave] for clave in claves}


def test_obtener_archivo_devuelve_rol_o_404(db, mundo, archivos_mundo):
    for usuario, rol in [("admin_a", "admin"), ("ana", "colaborador"), ("cliente", None)]:
        archivo = permisos.obtener_archivo(db, mundo[usuario], archivos_mundo["compartido"])
        assert archivo["mi_rol"] == rol
    for usuario, clave in [("admin_b", "compartido"), ("ana", "p2"), ("admin_a", "papelera"),
                           ("cliente", "privado")]:
        with pytest.raises(HTTPException) as error:
            permisos.obtener_archivo(db, mundo[usuario], archivos_mundo[clave])
        assert error.value.status_code == 404
