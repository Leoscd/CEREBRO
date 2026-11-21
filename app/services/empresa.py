"""Alta de una empresa con sus áreas, los tipos de proyecto base y su primer admin."""
from psycopg import Connection
from psycopg.types.json import Jsonb

from app.security import hash_password

AREAS = [
    ("gerencia", "Gerencia"),
    ("gestion_obras", "Gestión de Obras"),
    ("gestion_administrativa", "Gestión Administrativa"),
    ("gestion_proyectos", "Gestión de Proyectos"),
    ("desarrollo_proyectos", "Desarrollo de Proyectos"),
    ("direccion_tecnica", "Dirección Técnica"),
]

CARPETAS_BASE = ["01 Relevamiento", "02 Anteproyecto", "03 Proyecto", "04 Documentación", "05 Obra", "Bitácora"]

TIPOS = [
    {
        "slug": "revit", "nombre": "Proyectos Revit", "disciplina": "revit", "agente_slug": "revit",
        "descripcion": "Modelos BIM, láminas, planillas de carpinterías y cómputos desde Revit.",
        "plantilla": CARPETAS_BASE + ["Modelos IFC", "Láminas"],
    },
    {
        "slug": "autocad", "nombre": "Proyectos AutoCAD", "disciplina": "autocad", "agente_slug": "autocad",
        "descripcion": "Plantas, estructura, instalaciones y presentaciones en AutoCAD.",
        "plantilla": CARPETAS_BASE + ["DWG", "Láminas PDF"],
    },
    {
        "slug": "sketchup", "nombre": "Proyectos SketchUp", "disciplina": "sketchup", "agente_slug": "sketchup",
        "descripcion": "Modelado 3D, vistas y renders desde SketchUp.",
        "plantilla": CARPETAS_BASE + ["Modelos 3D", "Renders"],
    },
    {
        "slug": "presupuestos", "nombre": "Presupuestos y Excel", "disciplina": "presupuestos",
        "agente_slug": "presupuestos",
        "descripcion": "Cómputo y presupuesto, análisis de precios y planillas.",
        "plantilla": ["Cómputos", "Presupuestos", "Precios y cotizaciones", "Bitácora"],
    },
]


def crear_empresa(db: Connection, *, nombre: str, slug: str, admin_email: str, admin_nombre: str,
                  admin_password: str) -> tuple[dict, dict]:
    empresa = db.execute(
        "INSERT INTO empresas (nombre, slug) VALUES (%s, %s) RETURNING *", (nombre, slug)
    ).fetchone()
    for orden, (codigo, nom) in enumerate(AREAS):
        db.execute(
            "INSERT INTO areas (empresa_id, codigo, nombre, orden) VALUES (%s, %s, %s, %s)",
            (empresa["id"], codigo, nom, orden),
        )
    for pos, t in enumerate(TIPOS):
        db.execute(
            """INSERT INTO tipos_proyecto (empresa_id, slug, nombre, descripcion, disciplina, agente_slug,
                                           plantilla_carpetas, posicion)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (empresa["id"], t["slug"], t["nombre"], t["descripcion"], t["disciplina"], t["agente_slug"],
             Jsonb(t["plantilla"]), pos),
        )
    admin = db.execute(
        """INSERT INTO usuarios (empresa_id, email, password_hash, nombre, rol_empresa)
           VALUES (%s, %s, %s, %s, 'admin') RETURNING *""",
        (empresa["id"], admin_email.strip().lower(), hash_password(admin_password), admin_nombre),
    ).fetchone()
    gerencia = db.execute(
        "SELECT id FROM areas WHERE empresa_id = %s AND codigo = 'gerencia'", (empresa["id"],)
    ).fetchone()
    db.execute("INSERT INTO usuario_areas (usuario_id, area_id, rol) VALUES (%s, %s, 'responsable')",
               (admin["id"], gerencia["id"]))
    return empresa, admin
