"""Borradores y confirmación del parte diario."""

from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app.services import almacen, auditoria, cronograma

MIN_FOTOS = 3
_LISTAS = {"personal", "avances", "equipos"}
_MATERIALES = {"ingresos", "faltantes", "stock"}


def datos_iniciales():
    return {
        "condiciones": {"propuesto": None, "confirmado": False},
        "jornada": {},
        "personal": [],
        "avances": [],
        "materiales": {"ingresos": [], "faltantes": [], "stock": []},
        "equipos": [],
        "hys": {},
        "fotos_sin_revisar": [],
        "resumen": "",
        "listo": False,
    }


def buscar_dia(db, proyecto, usuario, dia):
    return db.execute(
        """SELECT * FROM reportes_obra WHERE empresa_id=%s AND proyecto_id=%s AND fecha=%s AND dt_id=%s""",
        (proyecto["empresa_id"], proyecto["id"], dia, usuario["id"]),
    ).fetchone()


def crear_borrador(db, usuario, proyecto, dia, *, request=None):
    parte = db.execute(
        """INSERT INTO reportes_obra(empresa_id,proyecto_id,dt_id,fecha,datos) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (proyecto_id,fecha,dt_id) DO NOTHING RETURNING *""",
        (usuario["empresa_id"], proyecto["id"], usuario["id"], dia, Jsonb(datos_iniciales())),
    ).fetchone()
    if parte is None:
        return buscar_dia(db, proyecto, usuario, dia), False
    _auditar(db, usuario, proyecto, "parte.borrador_creado", parte["id"], request)
    return parte, True


def listar(db, proyecto):
    return db.execute(
        """SELECT r.id,r.fecha,r.numero,r.estado,u.nombre AS dt_nombre
             FROM reportes_obra r JOIN usuarios u ON u.empresa_id=r.empresa_id AND u.id=r.dt_id
            WHERE r.empresa_id=%s AND r.proyecto_id=%s
            ORDER BY r.fecha DESC,r.numero DESC NULLS LAST,r.id DESC""",
        (proyecto["empresa_id"], proyecto["id"]),
    ).fetchall()


def obtener(db, proyecto, parte_id, *, bloquear=False):
    consulta = "SELECT * FROM reportes_obra WHERE empresa_id=%s AND proyecto_id=%s AND id=%s"
    if bloquear:
        consulta += " FOR UPDATE"
    parte = db.execute(consulta, (proyecto["empresa_id"], proyecto["id"], parte_id)).fetchone()
    if parte is None:
        raise HTTPException(404, "Parte no encontrado.")
    return parte


def editable(db, proyecto, parte_id):
    parte = obtener(db, proyecto, parte_id, bloquear=True)
    if parte["estado"] != "borrador":
        raise HTTPException(409, "El parte ya fue confirmado.")
    return parte


def fotos(db, proyecto, parte_id):
    return db.execute(
        """SELECT f.*,v.mime,t.nombre AS tarea FROM fotos_obra f
             JOIN versiones_archivo v ON v.empresa_id=f.empresa_id AND v.archivo_id=f.archivo_id AND v.id=f.version_id
             LEFT JOIN tareas_obra t ON t.empresa_id=f.empresa_id AND t.proyecto_id=f.proyecto_id AND t.id=f.tarea_id
            WHERE f.empresa_id=%s AND f.proyecto_id=%s AND f.reporte_id=%s ORDER BY f.hora,f.id""",
        (proyecto["empresa_id"], proyecto["id"], parte_id),
    ).fetchall()


def faltantes(parte, cantidad_fotos):
    datos = parte["datos"]
    falta = []
    if not datos["condiciones"].get("confirmado"):
        falta.append("Clima y estado del terreno revisados")
    if not datos["jornada"].get("tipo"):
        falta.append("Tipo de jornada")
    if datos["jornada"].get("tipo") != "no_laborable":
        if not datos["personal"]:
            falta.append("Personal en obra")
        if not datos["avances"]:
            falta.append("Al menos un avance vinculado al cronograma")
        if cantidad_fotos < MIN_FOTOS:
            falta.append(f"Fotos: hay {cantidad_fotos}, el mínimo es {MIN_FOTOS}")
    if "epp_ok" not in datos["hys"]:
        falta.append("Higiene y seguridad: uso de EPP")
    return falta


def _auditar(db, usuario, proyecto, accion, parte_id, request, detalle=None):
    auditoria.registrar(db, usuario, accion, proyecto_id=proyecto["id"], objeto="parte_obra",
                        objeto_id=parte_id, detalle=detalle, request=request)


def _texto(campos, llave, maximo, *, requerido=False):
    entrada = campos.get(llave, "")
    texto = entrada.strip() if isinstance(entrada, str) else ""
    if len(texto) > maximo or (requerido and not texto):
        raise HTTPException(400, f"Revisá el campo {llave}.")
    return texto


def _numero(campos, llave, minimo, maximo):
    entrada = _texto(campos, llave, 20, requerido=True)
    try:
        return cronograma._entero(entrada, minimo, maximo)
    except ValueError as error:
        raise HTTPException(400, f"Revisá el campo {llave}.") from error


def _dato_material(seccion, campos):
    requerido = seccion != "faltantes"
    texto = _texto(campos, "cantidad", 20, requerido=requerido).replace(",", ".")
    cantidad = None
    if texto:
        try:
            cantidad = Decimal(texto)
            if not cantidad.is_finite() or not 0 <= cantidad < 10**10 or cantidad.as_tuple().exponent < -4:
                raise InvalidOperation
        except InvalidOperation as error:
            raise HTTPException(400, "Ingresá una cantidad válida.") from error
    return {"material": _texto(campos, "material", 200, requerido=True),
            "cantidad": str(cantidad) if cantidad is not None else None,
            "unidad": _texto(campos, "unidad", 40, requerido=requerido), "detalle": _texto(campos, "detalle", 600)}


def _entrada_de_lista(db, proyecto, seccion, campos):
    if seccion == "personal":
        return {"empresa": _texto(campos, "empresa", 200, requerido=True),
                "categoria": _texto(campos, "categoria", 160, requerido=True),
                "cantidad": _numero(campos, "cantidad", 1, 100000)}
    if seccion == "avances":
        tarea_id = _numero(campos, "tarea_id", 1, 2**63 - 1)
        tarea = cronograma._tarea(db, proyecto, tarea_id)
        return {"tarea_id": tarea_id, "tarea": tarea["nombre"], "avance_pb": _numero(campos, "avance_pb", 0, 10000),
                "detalle": _texto(campos, "detalle", 1500)}
    if seccion == "equipos":
        return {"equipo": _texto(campos, "equipo", 200, requerido=True), "detalle": _texto(campos, "detalle", 600)}
    return _dato_material(seccion, campos)


def _actualizar_lista(db, proyecto, datos, seccion, campos):
    lista = datos["materiales"][seccion] if seccion in _MATERIALES else datos[seccion]
    if "indice" in campos:
        lista.pop(_numero(campos, "indice", 0, len(lista) - 1))
        return
    entrada = _entrada_de_lista(db, proyecto, seccion, campos)
    if seccion == "avances":
        lista[:] = [avance for avance in lista if avance["tarea_id"] != entrada["tarea_id"]]
    if len(lista) >= 100:
        raise HTTPException(409, "La sección admite hasta 100 entradas.")
    lista.append(entrada)


def actualizar_seccion(db, usuario, proyecto, parte_id, seccion, campos, *, request=None):
    parte = editable(db, proyecto, parte_id)
    datos = parte["datos"]
    if seccion == "condiciones":
        datos[seccion].update(texto=_texto(campos, "texto", 1500), confirmado=campos.get("confirmado") == "1")
    elif seccion == "jornada":
        tipo = campos.get("tipo")
        if tipo not in ("completa", "parcial", "no_laborable"):
            raise HTTPException(400, "Elegí un tipo de jornada.")
        datos[seccion] = {"tipo": tipo, "detalle": _texto(campos, "detalle", 1000)}
    elif seccion == "hys":
        epp = campos.get("epp_ok")
        if epp not in ("0", "1"):
            raise HTTPException(400, "Indicá si se utilizó EPP.")
        datos[seccion] = {"epp_ok": epp == "1", "visitas": _texto(campos, "visitas", 1000),
                          "incidentes": _texto(campos, "incidentes", 1000)}
    elif seccion == "resumen":
        datos[seccion] = _texto(campos, "texto", 5000)
    elif seccion in _LISTAS | _MATERIALES:
        _actualizar_lista(db, proyecto, datos, seccion, campos)
    else:
        raise HTTPException(404, "Sección no encontrada.")
    db.execute("UPDATE reportes_obra SET datos=%s WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
               (Jsonb(datos), proyecto["empresa_id"], proyecto["id"], parte_id))
    _auditar(db, usuario, proyecto, "parte.seccion_guardada", parte_id, request, {"seccion": seccion})


def _imagen(ruta: Path):
    with ruta.open("rb") as archivo:
        firma = archivo.read(12)
    for formato, tipo, prefijos in (
        ("png", "image/png", (b"\x89PNG\r\n\x1a\n",)),
        ("jpg", "image/jpeg", (b"\xff\xd8\xff",)),
        ("gif", "image/gif", (b"GIF87a", b"GIF89a")),
    ):
        if firma.startswith(prefijos):
            return formato, tipo
    if firma.startswith(b"RIFF") and firma[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def archivar_adjunto(db, usuario, proyecto, carpeta, nombre, extension, mime, sha, tamano, *, origen="subida"):
    """Registra el blob como versión interna para preservarlo en el almacén."""
    empresa, pid = proyecto["empresa_id"], proyecto["id"]
    db.execute(
        """INSERT INTO carpetas(empresa_id,proyecto_id,nombre) VALUES (%s,%s,%s)
           ON CONFLICT (proyecto_id,padre_id,nombre) DO NOTHING""", (empresa, pid, carpeta),
    )
    archivo = db.execute(
        """INSERT INTO archivos(empresa_id,proyecto_id,carpeta_id,nombre,extension,mime,creado_por)
           SELECT empresa_id,proyecto_id,id,%s,%s,%s,%s FROM carpetas
            WHERE empresa_id=%s AND proyecto_id=%s AND padre_id IS NULL AND nombre=%s RETURNING id""",
        (nombre, extension, mime, usuario["id"], empresa, pid, carpeta),
    ).fetchone()
    version = db.execute(
        """INSERT INTO versiones_archivo(empresa_id,archivo_id,numero,sha256,tamano_bytes,mime,origen,subida_por)
           VALUES (%s,%s,1,%s,%s,%s,%s,%s) RETURNING id""",
        (empresa, archivo["id"], sha, tamano, mime, origen, usuario["id"]),
    ).fetchone()
    db.execute("UPDATE archivos SET version_actual_id=%s WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
               (version["id"], empresa, pid, archivo["id"]))
    return archivo["id"], version["id"]


def agregar_foto(db, usuario, proyecto, parte_id, stream, descripcion, tarea_id, *, request=None):
    editable(db, proyecto, parte_id)
    if tarea_id is not None:
        cronograma._tarea(db, proyecto, tarea_id)
    if len(fotos(db, proyecto, parte_id)) >= 50:
        raise HTTPException(409, "El parte admite hasta 50 fotos.")
    sha, tamano = almacen.guardar(stream, validar=lambda ruta: _imagen(ruta) is not None)
    extension, mime = _imagen(almacen.ruta(sha))
    archivo_id, version_id = archivar_adjunto(db, usuario, proyecto, "Fotos de obra", f"Foto del parte {parte_id}",
                                             extension, mime, sha, tamano)
    foto = db.execute(
        """INSERT INTO fotos_obra(empresa_id,proyecto_id,reporte_id,archivo_id,version_id,sha256,descripcion,tarea_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (proyecto["empresa_id"], proyecto["id"], parte_id, archivo_id, version_id, sha, descripcion, tarea_id),
    ).fetchone()
    _auditar(db, usuario, proyecto, "parte.foto_agregada", parte_id, request, {"foto_id": foto["id"]})


def quitar_foto(db, usuario, proyecto, parte_id, foto_id, *, request=None):
    editable(db, proyecto, parte_id)
    foto = db.execute(
        """DELETE FROM fotos_obra WHERE empresa_id=%s AND proyecto_id=%s AND reporte_id=%s AND id=%s
           RETURNING archivo_id""", (proyecto["empresa_id"], proyecto["id"], parte_id, foto_id),
    ).fetchone()
    if foto is None:
        raise HTTPException(404, "Foto no encontrada.")
    db.execute("UPDATE archivos SET en_papelera_en=now() WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
               (proyecto["empresa_id"], proyecto["id"], foto["archivo_id"]))
    _auditar(db, usuario, proyecto, "parte.foto_quitada", parte_id, request, {"foto_id": foto_id})


def confirmar(db, usuario, proyecto, parte_id, *, request=None):
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    db.execute("SELECT id FROM proyectos WHERE empresa_id=%s AND id=%s FOR NO KEY UPDATE", (empresa, pid))
    parte = editable(db, proyecto, parte_id)
    faltan = faltantes(parte, len(fotos(db, proyecto, parte_id)))
    if faltan:
        raise HTTPException(409, detail=faltan)
    for avance in parte["datos"]["avances"]:
        cronograma.registrar_avance(db, usuario, proyecto, avance["tarea_id"], parte["fecha"], avance["avance_pb"],
                                    request=request)
    nuevo = db.execute(
        """UPDATE reportes_obra SET estado='confirmado',confirmado_en=now(),
                numero=(SELECT coalesce(max(numero),0)+1 FROM reportes_obra WHERE empresa_id=%s AND proyecto_id=%s)
            WHERE empresa_id=%s AND proyecto_id=%s AND id=%s RETURNING *""",
        (empresa, pid, empresa, pid, parte_id),
    ).fetchone()
    _auditar(db, usuario, proyecto, "parte.confirmado", parte_id, request, {"numero": nuevo["numero"]})
    return nuevo
