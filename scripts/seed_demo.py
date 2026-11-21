"""Datos de demostración para probar en local: una empresa, equipo, clientes y proyectos.

Uso: python -m scripts.seed_demo
Crea (si no existe) la empresa 'demo'. Las contraseñas de demo se imprimen al final y
también quedan en data/demo-credenciales.txt (carpeta ignorada por git). Solo para local.
"""
import secrets

import psycopg
from psycopg.rows import dict_row

from app import config
from app.db.migrar import migrar
from app.security import hash_password
from app.services.empresa import crear_empresa
from app.services.proyectos import crear_proyecto


def main() -> None:
    migrar(verbose=True)
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as db:
        if db.execute("SELECT 1 FROM empresas WHERE slug = 'demo'").fetchone():
            print("La empresa demo ya existe; no se toca.")
            return
        clave = "demo-" + secrets.token_urlsafe(8)
        empresa, admin = crear_empresa(db, nombre="Estudio Demo", slug="demo", admin_email="admin@demo.test",
                                       admin_nombre="Admin Demo", admin_password=clave)
        e = empresa["id"]
        cliente = db.execute(
            "INSERT INTO clientes (empresa_id, nombre, email) VALUES (%s, 'Familia López', 'lopez@demo.test') RETURNING id",
            (e,),
        ).fetchone()
        personas = {}
        for email, nombre in [("dibujante@demo.test", "Ana Dibujante"), ("dt@demo.test", "Bruno DT"),
                              ("admin.obra@demo.test", "Carla Administración")]:
            personas[email] = db.execute(
                "INSERT INTO usuarios (empresa_id, email, password_hash, nombre) VALUES (%s,%s,%s,%s) RETURNING *",
                (e, email, hash_password(clave), nombre),
            ).fetchone()
        db.execute(
            """INSERT INTO usuarios (empresa_id, email, password_hash, nombre, rol_empresa, cliente_id)
               VALUES (%s, 'cliente@demo.test', %s, 'Juan López', 'cliente', %s)""",
            (e, hash_password(clave), cliente["id"]),
        )
        tipos = {t["slug"]: t["id"] for t in db.execute("SELECT id, slug FROM tipos_proyecto WHERE empresa_id=%s", (e,))}
        casa = crear_proyecto(db, admin, tipo_proyecto_id=tipos["revit"], nombre="Casa López",
                              cliente_id=cliente["id"], localidad="Yerba Buena", etapa="documentacion")
        local = crear_proyecto(db, admin, tipo_proyecto_id=tipos["autocad"], nombre="Local comercial Centro",
                               localidad="San Miguel de Tucumán", etapa="proyecto")
        crear_proyecto(db, admin, tipo_proyecto_id=tipos["presupuestos"], nombre="Presupuesto Casa López",
                       cliente_id=cliente["id"])
        for p, email, rol in [(casa, "dibujante@demo.test", "colaborador"), (casa, "dt@demo.test", "dt"),
                              (local, "dibujante@demo.test", "director")]:
            db.execute("INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol) VALUES (%s,%s,%s)",
                       (p["id"], personas[email]["id"], rol))
        db.execute("INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol) VALUES (%s,%s,'director')",
                   (casa["id"], admin["id"]))
        db.commit()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "demo-credenciales.txt").write_text(
        "Usuarios demo (solo local): admin@demo.test, dibujante@demo.test, dt@demo.test, "
        f"admin.obra@demo.test, cliente@demo.test\nContraseña de todos: {clave}\n",
        encoding="utf-8",
    )
    print("Demo creada. Credenciales en data/demo-credenciales.txt")


if __name__ == "__main__":
    main()
