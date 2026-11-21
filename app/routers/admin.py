"""Panel de administración de la empresa: personas, invitaciones, clientes, tipos de
proyecto, alta de proyectos y registro de actividad. Todo filtrado por la empresa del admin."""
import json
import re
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from psycopg import Connection
from psycopg.types.json import Jsonb

from app import config
from app.db import db_dependency
from app.permisos import ROLES_PROYECTO
from app.routers.auth import EMAIL_RE, sha256
from app.security import check_csrf, require_admin
from app.services import auditoria, correo
from app.services.proyectos import crear_proyecto
from app.templates import ROLES_EMPRESA, templates

router = APIRouter(prefix="/admin")

DISCIPLINAS = ("revit", "autocad", "sketchup", "presupuestos", "obra", "general")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _admin_csrf(request: Request, user=Depends(check_csrf)):
    if user["rol_empresa"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    return user


@router.get("")
def panel(request: Request, user=Depends(require_admin), db: Connection = Depends(db_dependency)):
    e = user["empresa_id"]
    cuentas = db.execute(
        """SELECT (SELECT count(*) FROM usuarios WHERE empresa_id=%s AND activo) AS usuarios,
                  (SELECT count(*) FROM proyectos WHERE empresa_id=%s AND estado='activo') AS proyectos,
                  (SELECT count(*) FROM clientes WHERE empresa_id=%s) AS clientes,
                  (SELECT count(*) FROM invitaciones WHERE empresa_id=%s AND usada_por IS NULL
                     AND cancelada_en IS NULL AND expira_at > now()) AS invitaciones""",
        (e, e, e, e),
    ).fetchone()
    return templates.TemplateResponse(request, "admin/panel.html", {"user": user, "cuentas": cuentas})


# ---------- personas e invitaciones ----------

@router.get("/usuarios")
def usuarios(request: Request, link: str = "", user=Depends(require_admin), db: Connection = Depends(db_dependency)):
    filas = db.execute(
        """SELECT u.*, c.nombre AS cliente_nombre,
                  (SELECT count(*) FROM proyecto_miembros pm WHERE pm.usuario_id = u.id) AS proyectos
             FROM usuarios u LEFT JOIN clientes c ON c.id = u.cliente_id
            WHERE u.empresa_id = %s ORDER BY u.activo DESC, u.nombre""",
        (user["empresa_id"],),
    ).fetchall()
    pendientes = db.execute(
        """SELECT i.*, p.codigo AS proyecto_codigo FROM invitaciones i LEFT JOIN proyectos p ON p.id = i.proyecto_id
            WHERE i.empresa_id = %s AND i.usada_por IS NULL AND i.cancelada_en IS NULL AND i.expira_at > now()
            ORDER BY i.creada_en DESC""",
        (user["empresa_id"],),
    ).fetchall()
    clientes = db.execute("SELECT id, nombre FROM clientes WHERE empresa_id = %s ORDER BY nombre",
                          (user["empresa_id"],)).fetchall()
    proyectos = db.execute("SELECT id, codigo, nombre FROM proyectos WHERE empresa_id = %s AND estado <> 'finalizado' "
                           "ORDER BY codigo DESC", (user["empresa_id"],)).fetchall()
    return templates.TemplateResponse(
        request, "admin/usuarios.html",
        {"user": user, "usuarios": filas, "pendientes": pendientes, "clientes": clientes,
         "proyectos": proyectos, "link": link},
    )


@router.post("/usuarios/invitar")
def invitar(
    request: Request,
    email: str = Form(...),
    rol_empresa: str = Form("miembro"),
    cliente_id: str = Form(""),
    proyecto_id: str = Form(""),
    rol_proyecto: str = Form(""),
    user=Depends(_admin_csrf),
    db: Connection = Depends(db_dependency),
):
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or rol_empresa not in ROLES_EMPRESA:
        raise HTTPException(status_code=400, detail="Email o rol inválido")
    if db.execute("SELECT 1 FROM usuarios WHERE email = %s", (email,)).fetchone():
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese email")
    cid = int(cliente_id) if cliente_id else None
    if rol_empresa == "cliente":
        if cid is None or not db.execute("SELECT 1 FROM clientes WHERE id=%s AND empresa_id=%s",
                                         (cid, user["empresa_id"])).fetchone():
            raise HTTPException(status_code=400, detail="Elegí el cliente al que pertenece")
    else:
        cid = None
    pid = int(proyecto_id) if proyecto_id else None
    if pid is not None:
        if rol_proyecto not in ROLES_PROYECTO or not db.execute(
            "SELECT 1 FROM proyectos WHERE id=%s AND empresa_id=%s", (pid, user["empresa_id"])
        ).fetchone():
            raise HTTPException(status_code=400, detail="Proyecto o rol en el proyecto inválido")
    codigo = secrets.token_urlsafe(24)
    inv = db.execute(
        """INSERT INTO invitaciones (empresa_id, code_hash, email, rol_empresa, cliente_id, proyecto_id,
                                     rol_proyecto, creada_por, expira_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now() + %s * interval '1 day') RETURNING id""",
        (user["empresa_id"], sha256(codigo), email, rol_empresa, cid, pid, rol_proyecto or None,
         user["id"], config.INVITACION_DIAS),
    ).fetchone()
    auditoria.registrar(db, user, "invitacion_creada", objeto="invitacion", objeto_id=inv["id"],
                        detalle={"email": email, "rol": rol_empresa}, request=request)
    db.commit()
    link = f"{config.URL_PUBLICA}/registro?invitacion={codigo}"
    enviado = correo.invitacion(email, link, user["empresa_nombre"], user["nombre"] or user["email"])
    if enviado:
        db.execute("UPDATE invitaciones SET enviado_at = now() WHERE id = %s", (inv["id"],))
        db.commit()
        return RedirectResponse("/admin/usuarios?link=enviado", status_code=303)
    # Sin SMTP: el link se muestra una única vez para mandarlo a mano (no se guarda en claro).
    return templates.TemplateResponse(
        request, "admin/invitacion_link.html", {"user": user, "email": email, "link": link}
    )


@router.post("/invitacion/{inv_id}/cancelar")
def cancelar_invitacion(inv_id: int, request: Request, user=Depends(_admin_csrf),
                        db: Connection = Depends(db_dependency)):
    db.execute("UPDATE invitaciones SET cancelada_en = now() WHERE id = %s AND empresa_id = %s",
               (inv_id, user["empresa_id"]))
    auditoria.registrar(db, user, "invitacion_cancelada", objeto="invitacion", objeto_id=inv_id, request=request)
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/usuarios/{uid}/acceso")
def cambiar_acceso(uid: int, request: Request, user=Depends(_admin_csrf), db: Connection = Depends(db_dependency)):
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="No podés desactivar tu propia cuenta")
    fila = db.execute(
        "UPDATE usuarios SET activo = NOT activo WHERE id = %s AND empresa_id = %s RETURNING activo",
        (uid, user["empresa_id"]),
    ).fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    auditoria.registrar(db, user, "acceso_activado" if fila["activo"] else "acceso_desactivado",
                        objeto="usuario", objeto_id=uid, request=request)
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/usuarios/{uid}/rol")
def cambiar_rol(uid: int, request: Request, rol_empresa: str = Form(...), user=Depends(_admin_csrf),
                db: Connection = Depends(db_dependency)):
    if rol_empresa not in ("admin", "miembro"):
        raise HTTPException(status_code=400, detail="Rol inválido")
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="No podés cambiar tu propio rol")
    fila = db.execute(
        """UPDATE usuarios SET rol_empresa = %s, sesion_version = sesion_version + 1
            WHERE id = %s AND empresa_id = %s AND rol_empresa <> 'cliente' RETURNING id""",
        (rol_empresa, uid, user["empresa_id"]),
    ).fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    auditoria.registrar(db, user, "rol_cambiado", objeto="usuario", objeto_id=uid,
                        detalle={"rol": rol_empresa}, request=request)
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


# ---------- clientes ----------

@router.get("/clientes")
def clientes(request: Request, user=Depends(require_admin), db: Connection = Depends(db_dependency)):
    filas = db.execute(
        """SELECT c.*, (SELECT count(*) FROM proyectos p WHERE p.cliente_id = c.id) AS proyectos
             FROM clientes c WHERE c.empresa_id = %s ORDER BY c.nombre""",
        (user["empresa_id"],),
    ).fetchall()
    return templates.TemplateResponse(request, "admin/clientes.html", {"user": user, "clientes": filas})


@router.post("/clientes")
def crear_cliente(request: Request, nombre: str = Form(...), cuit: str = Form(""), email: str = Form(""),
                  telefono: str = Form(""), user=Depends(_admin_csrf), db: Connection = Depends(db_dependency)):
    if not nombre.strip():
        raise HTTPException(status_code=400, detail="Falta el nombre")
    c = db.execute(
        "INSERT INTO clientes (empresa_id, nombre, cuit, email, telefono) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (user["empresa_id"], nombre.strip()[:200], cuit.strip(), email.strip().lower(), telefono.strip()),
    ).fetchone()
    auditoria.registrar(db, user, "cliente_creado", objeto="cliente", objeto_id=c["id"],
                        detalle={"nombre": nombre.strip()}, request=request)
    db.commit()
    return RedirectResponse("/admin/clientes", status_code=303)


# ---------- tipos de proyecto ----------

@router.get("/tipos")
def tipos(request: Request, user=Depends(require_admin), db: Connection = Depends(db_dependency)):
    filas = db.execute(
        """SELECT t.*, (SELECT count(*) FROM proyectos p WHERE p.tipo_proyecto_id = t.id) AS proyectos
             FROM tipos_proyecto t WHERE t.empresa_id = %s ORDER BY t.posicion, t.nombre""",
        (user["empresa_id"],),
    ).fetchall()
    return templates.TemplateResponse(request, "admin/tipos.html",
                                      {"user": user, "tipos": filas, "disciplinas": DISCIPLINAS})


def _carpetas(texto: str) -> list[str]:
    return [linea.strip() for linea in texto.splitlines() if linea.strip()][:40]


@router.post("/tipos")
def guardar_tipo(
    request: Request,
    tipo_id: str = Form(""),
    slug: str = Form(...),
    nombre: str = Form(...),
    descripcion: str = Form(""),
    disciplina: str = Form("general"),
    agente_slug: str = Form("documentador"),
    agent_context: str = Form(""),
    plantilla_carpetas: str = Form(""),
    posicion: int = Form(0),
    publicado: str = Form(""),
    user=Depends(_admin_csrf),
    db: Connection = Depends(db_dependency),
):
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug) or disciplina not in DISCIPLINAS or not nombre.strip():
        raise HTTPException(status_code=400, detail="Datos inválidos (el slug va en minúsculas, sin espacios)")
    valores = (slug, nombre.strip()[:120], descripcion.strip(), disciplina, agente_slug.strip() or "documentador",
               agent_context.strip(), Jsonb(_carpetas(plantilla_carpetas)), posicion, publicado == "1")
    if tipo_id:
        fila = db.execute(
            """UPDATE tipos_proyecto SET slug=%s, nombre=%s, descripcion=%s, disciplina=%s, agente_slug=%s,
                   agent_context=%s, plantilla_carpetas=%s, posicion=%s, publicado=%s
                WHERE id=%s AND empresa_id=%s RETURNING id""",
            (*valores, int(tipo_id), user["empresa_id"]),
        ).fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="Tipo no encontrado")
        accion = "tipo_editado"
    else:
        fila = db.execute(
            """INSERT INTO tipos_proyecto (slug, nombre, descripcion, disciplina, agente_slug, agent_context,
                                           plantilla_carpetas, posicion, publicado, empresa_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (empresa_id, slug) DO NOTHING RETURNING id""",
            (*valores, user["empresa_id"]),
        ).fetchone()
        if not fila:
            raise HTTPException(status_code=400, detail="Ya existe un tipo con ese slug")
        accion = "tipo_creado"
    auditoria.registrar(db, user, accion, objeto="tipo_proyecto", objeto_id=fila["id"],
                        detalle={"slug": slug}, request=request)
    db.commit()
    return RedirectResponse("/admin/tipos", status_code=303)


# ---------- alta de proyectos ----------

@router.get("/proyectos/nuevo")
def nuevo_proyecto_page(request: Request, tipo: str = "", user=Depends(require_admin),
                        db: Connection = Depends(db_dependency)):
    tipos_ = db.execute("SELECT id, slug, nombre FROM tipos_proyecto WHERE empresa_id=%s ORDER BY posicion, nombre",
                        (user["empresa_id"],)).fetchall()
    clientes_ = db.execute("SELECT id, nombre FROM clientes WHERE empresa_id=%s ORDER BY nombre",
                           (user["empresa_id"],)).fetchall()
    return templates.TemplateResponse(request, "admin/proyecto_nuevo.html",
                                      {"user": user, "tipos": tipos_, "clientes": clientes_, "tipo_sel": tipo})


@router.post("/proyectos/nuevo")
def nuevo_proyecto(
    request: Request,
    tipo_proyecto_id: int = Form(...),
    nombre: str = Form(...),
    cliente_id: str = Form(""),
    descripcion: str = Form(""),
    direccion: str = Form(""),
    localidad: str = Form(""),
    user=Depends(_admin_csrf),
    db: Connection = Depends(db_dependency),
):
    if not nombre.strip():
        raise HTTPException(status_code=400, detail="Falta el nombre")
    try:
        p = crear_proyecto(db, user, tipo_proyecto_id=tipo_proyecto_id, nombre=nombre,
                           cliente_id=int(cliente_id) if cliente_id else None,
                           descripcion=descripcion.strip(), direccion=direccion.strip(), localidad=localidad.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Quien lo crea queda como director, así el proyecto nunca nace sin responsable.
    db.execute("INSERT INTO proyecto_miembros (proyecto_id, usuario_id, rol) VALUES (%s, %s, 'director')",
               (p["id"], user["id"]))
    auditoria.registrar(db, user, "proyecto_creado", proyecto_id=p["id"], objeto="proyecto",
                        objeto_id=p["codigo"], detalle={"nombre": p["nombre"]}, request=request)
    db.commit()
    return RedirectResponse(f"/proyecto/{p['codigo']}", status_code=303)


# ---------- auditoría ----------

@router.get("/auditoria")
def ver_auditoria(request: Request, user=Depends(require_admin), db: Connection = Depends(db_dependency)):
    filas = db.execute(
        """SELECT a.*, u.nombre AS usuario_nombre, p.codigo AS proyecto_codigo
             FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
             LEFT JOIN proyectos p ON p.id = a.proyecto_id
            WHERE a.empresa_id = %s ORDER BY a.creado_en DESC LIMIT 200""",
        (user["empresa_id"],),
    ).fetchall()
    for f in filas:
        f["detalle_txt"] = json.dumps(f["detalle"], ensure_ascii=False) if f["detalle"] else ""
    return templates.TemplateResponse(request, "admin/auditoria.html", {"user": user, "filas": filas})
