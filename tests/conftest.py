"""Pruebas contra un PostgreSQL real (con pgvector), embebido con `pgserver`.

Se levanta un servidor por sesión de pytest, se migra una base plantilla una sola vez y
cada test recibe una base nueva clonada de esa plantilla (rápido y aislado).
En CI o en el VPS se puede usar un Postgres existente con TEST_DATABASE_URL.
"""
import os
import re
import tempfile
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

_SERVIDOR = None


def _url_admin() -> str:
    global _SERVIDOR
    if os.getenv("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    import pgserver

    _SERVIDOR = pgserver.get_server(tempfile.mkdtemp(prefix="gsp-pg-"), cleanup_mode="stop")
    return _SERVIDOR.get_uri()


URL_ADMIN = _url_admin()
os.environ["DATABASE_URL"] = URL_ADMIN  # antes de importar app.config
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["EMBEDDINGS_PROVEEDOR"] = "falso"
os.environ["EMBEDDINGS_DIMENSIONES"] = "384"


def _con_db(url: str, nombre: str) -> str:
    return re.sub(r"/[^/?]*(\?|$)", f"/{nombre}\\1", url, count=1) if url.count("/") >= 3 else url


PLANTILLA = "gsp_plantilla"


@pytest.fixture(scope="session")
def plantilla():
    from app.db.migrar import migrar

    with psycopg.connect(URL_ADMIN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {PLANTILLA}")
        c.execute(f"CREATE DATABASE {PLANTILLA}")
    migrar(_con_db(URL_ADMIN, PLANTILLA), verbose=False)
    return PLANTILLA


@pytest.fixture()
def db_url(plantilla):
    from app import db as dbmod

    nombre = "t_" + uuid.uuid4().hex[:12]
    with psycopg.connect(URL_ADMIN, autocommit=True) as c:
        c.execute(f"CREATE DATABASE {nombre} TEMPLATE {plantilla}")
    url = _con_db(URL_ADMIN, nombre)
    dbmod.cerrar_pool()
    dbmod.abrir_pool(url, min_size=1, max_size=4)
    yield url
    dbmod.cerrar_pool()
    with psycopg.connect(URL_ADMIN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)")


@pytest.fixture()
def db(db_url):
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        yield conn


@pytest.fixture()
def app_client(db_url):
    from fastapi.testclient import TestClient

    from app.main import app

    return lambda: TestClient(app, follow_redirects=False)


CLAVE = "clave-de-prueba-123"


@pytest.fixture()
def mundo(db):
    """Dos empresas. En la A: admin, dos miembros, un cliente y tres proyectos."""
    from app.security import hash_password
    from app.services.empresa import crear_empresa
    from app.services.proyectos import crear_proyecto

    ea, admin_a = crear_empresa(db, nombre="Empresa A", slug="a", admin_email="admin@a.test",
                                admin_nombre="Admin A", admin_password=CLAVE)
    eb, admin_b = crear_empresa(db, nombre="Empresa B", slug="b", admin_email="admin@b.test",
                                admin_nombre="Admin B", admin_password=CLAVE)

    def usuario(empresa, email, rol="miembro", cliente_id=None):
        return db.execute(
            """INSERT INTO usuarios (empresa_id, email, password_hash, nombre, rol_empresa, cliente_id)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
            (empresa["id"], email, hash_password(CLAVE), email.split("@")[0], rol, cliente_id),
        ).fetchone()

    cli = db.execute("INSERT INTO clientes (empresa_id, nombre) VALUES (%s, 'Cliente A') RETURNING *",
                     (ea["id"],)).fetchone()
    ana = usuario(ea, "ana@a.test")
    beto = usuario(ea, "beto@a.test")
    cliente = usuario(ea, "cliente@a.test", "cliente", cli["id"])
    tipo_a = db.execute("SELECT id FROM tipos_proyecto WHERE empresa_id=%s AND slug='revit'", (ea["id"],)).fetchone()
    tipo_b = db.execute("SELECT id FROM tipos_proyecto WHERE empresa_id=%s AND slug='revit'", (eb["id"],)).fetchone()
    p1 = crear_proyecto(db, admin_a, tipo_proyecto_id=tipo_a["id"], nombre="Casa con cliente", cliente_id=cli["id"])
    p2 = crear_proyecto(db, admin_a, tipo_proyecto_id=tipo_a["id"], nombre="Local sin Ana")
    pb = crear_proyecto(db, admin_b, tipo_proyecto_id=tipo_b["id"], nombre="Proyecto de B")
    db.execute("INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol) VALUES (%s,%s,'colaborador')",
               (p1["id"], ana["id"]))
    db.execute("INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol) VALUES (%s,%s,'director')",
               (p2["id"], beto["id"]))
    db.commit()
    return {"ea": ea, "eb": eb, "admin_a": admin_a, "admin_b": admin_b, "ana": ana, "beto": beto,
            "cliente": cliente, "p1": p1, "p2": p2, "pb": pb}


def entrar(client, email: str, clave: str = CLAVE):
    r = client.post("/login", data={"email": email, "password": clave})
    assert r.status_code == 303, r.text
    return client


@pytest.fixture()
def como(app_client):
    """como('ana@a.test') → cliente HTTP ya logueado."""
    return lambda email, clave=CLAVE: entrar(app_client(), email, clave)


def csrf_de(usuario: dict) -> str:
    from app.security import csrf_token

    return csrf_token(usuario["id"])
