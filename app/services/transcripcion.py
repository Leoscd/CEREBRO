"""Audio del parte y propuesta de texto a revisar por el DT."""

import re
from io import BytesIO

from fastapi import HTTPException
from openai import OpenAI, OpenAIError
from psycopg.types.json import Jsonb

from app import config
from app.services import almacen, auditoria, jobs, partes

_MAX_AUDIO = 20 * 1024**2
_MAX_TEXTO = 5000
_MIME = {"m4a": "audio/mp4", "ogg": "audio/ogg", "webm": "audio/webm", "mp3": "audio/mpeg"}


def verificar_configuracion():
    proveedor = config.TRANSCRIPCION_PROVEEDOR
    if proveedor == "falso":
        return
    if proveedor != "openai":
        raise ValueError("Configurá TRANSCRIPCION_PROVEEDOR como openai o falso.")
    if not config.MODELO_TRANSCRIPCION:
        raise ValueError("Configurá MODELO_TRANSCRIPCION para transcribir con OpenAI.")
    if not config.OPENAI_API_KEY:
        raise ValueError("Configurá OPENAI_API_KEY para transcribir con OpenAI.")


def _es_mp3(contenido):
    inicio = 0
    if contenido.startswith((b"ID3\x02", b"ID3\x03", b"ID3\x04")):
        tamano_id3 = contenido[6:10]
        if any(octeto & 0x80 for octeto in tamano_id3):
            return False
        inicio = 10 + sum(octeto << (7 * posicion) for posicion, octeto in enumerate(reversed(tamano_id3)))
        if contenido[3] == 4 and contenido[5] & 0x10:
            inicio += 10
    marco = contenido[inicio:inicio + 4]
    return (len(marco) == 4 and marco[0] == 0xff and (marco[1] & 0xe6) == 0xe2
            and (marco[1] & 0x18) != 0x08 and (marco[2] & 0x0c) != 0x0c and (marco[2] & 0xf0) != 0xf0)


def _formato(contenido):
    if len(contenido) < 12:
        return None
    if contenido[4:8] == b"ftyp":
        fin = min(int.from_bytes(contenido[:4], "big"), 128)
        marcas = contenido[8:fin]
        audio = b"M4A " in marcas or re.search(rb"hdlr.{8}soun", contenido, re.S)
        if audio and not re.search(rb"hdlr.{8}vide", contenido, re.S):
            return "m4a"
    if contenido.startswith(b"OggS\x00") and any(f in contenido[:4096] for f in (b"OpusHead", b"\x01vorbis", b"Speex   ")):
        return "ogg"
    if (contenido.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in contenido[:256]
            and any(f in contenido[:65536] for f in (b"A_OPUS", b"A_VORBIS"))):
        return "webm"
    return "mp3" if _es_mp3(contenido) else None


def cargar(db, usuario, proyecto, parte_id, stream, *, request=None):
    partes.editable(db, proyecto, parte_id)
    contenido = stream.read(_MAX_AUDIO + 1)
    if len(contenido) > _MAX_AUDIO:
        raise HTTPException(413, "El audio admite hasta 20 MB.")
    extension = _formato(contenido)
    if extension is None:
        raise HTTPException(400, "Subí un audio M4A, OGG, WebM o MP3 válido.")
    try:
        verificar_configuracion()
    except ValueError as error:
        raise HTTPException(503, str(error)) from error
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    sha, tamano = almacen.guardar(BytesIO(contenido))
    archivo, version = partes.archivar_adjunto(db, usuario, proyecto, "Audios de obra",
                                               f"Audio del parte {parte_id}.{extension}", extension,
                                               _MIME[extension], sha, tamano)
    audio = db.execute(
        """INSERT INTO audios_parte(empresa_id,proyecto_id,reporte_id,archivo_id,version_id,extension)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (empresa, pid, parte_id, archivo, version, extension),
    ).fetchone()["id"]
    job_id = jobs.encolar(db, empresa, "parte.transcribir", {"proyecto_id": pid, "parte_id": parte_id, "audio_id": audio})
    db.execute("UPDATE audios_parte SET job_id=%s WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
               (job_id, empresa, pid, audio))
    auditoria.registrar(db, usuario, "parte.audio_cargado", proyecto_id=pid, objeto="parte_obra", objeto_id=parte_id,
                        detalle={"audio_id": audio}, request=request)


def propuestas(db, proyecto, parte_id):
    return db.execute(
        """SELECT a.id,a.texto,j.estado FROM audios_parte a
             LEFT JOIN jobs j ON j.empresa_id=a.empresa_id AND j.id=a.job_id
            WHERE a.empresa_id=%s AND a.proyecto_id=%s AND a.reporte_id=%s AND a.aceptado_en IS NULL ORDER BY a.id""",
        (proyecto["empresa_id"], proyecto["id"], parte_id),
    ).fetchall()


def transcribir(ruta, extension):
    verificar_configuracion()
    if config.TRANSCRIPCION_PROVEEDOR == "falso":
        return "Dictado de prueba para revisar."
    try:
        with (OpenAI(api_key=config.OPENAI_API_KEY, base_url="https://api.openai.com/v1", max_retries=0, timeout=45.0)
              as cliente, ruta.open("rb") as audio):
            respuesta = cliente.audio.transcriptions.create(
                model=config.MODELO_TRANSCRIPCION, file=(f"audio.{extension}", audio, _MIME[extension]), language="es",
            )
    except OpenAIError as error:
        raise ValueError("OpenAI no pudo transcribir el audio.") from error
    return respuesta.text.strip()


def guardar_propuesta(db, empresa_id, payload):
    ids = (empresa_id, payload["proyecto_id"], payload["parte_id"], payload["audio_id"])
    audio = db.execute(
        """SELECT a.extension,v.sha256 FROM audios_parte a
             JOIN reportes_obra r ON r.empresa_id=a.empresa_id AND r.proyecto_id=a.proyecto_id AND r.id=a.reporte_id
             JOIN versiones_archivo v ON v.empresa_id=a.empresa_id AND v.archivo_id=a.archivo_id AND v.id=a.version_id
            WHERE a.empresa_id=%s AND a.proyecto_id=%s AND a.reporte_id=%s AND a.id=%s
              AND a.texto IS NULL AND r.estado='borrador'""", ids,
    ).fetchone()
    if audio is None:
        return
    texto = transcribir(almacen.ruta(audio["sha256"]), audio["extension"])
    if not texto:
        raise ValueError("El audio no produjo texto para revisar.")
    db.execute(
        """UPDATE audios_parte SET texto=%s
            WHERE empresa_id=%s AND proyecto_id=%s AND reporte_id=%s AND id=%s AND texto IS NULL""",
        (texto[:_MAX_TEXTO], *ids),
    )


def aceptar(db, usuario, proyecto, parte_id, audio_id, texto, *, request=None):
    parte = partes.editable(db, proyecto, parte_id)
    texto = texto.strip()
    if not texto:
        raise HTTPException(400, "Ingresá el texto revisado.")
    datos = parte["datos"]
    resumen = "\n".join(texto for texto in (datos["resumen"], texto) if texto)
    if len(resumen) > _MAX_TEXTO:
        raise HTTPException(400, "Las observaciones admiten hasta 5.000 caracteres.")
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    actualizado = db.execute(
        """UPDATE audios_parte SET aceptado_en=now() WHERE empresa_id=%s AND proyecto_id=%s AND reporte_id=%s
              AND id=%s AND texto IS NOT NULL AND aceptado_en IS NULL""", (empresa, pid, parte_id, audio_id),
    ).rowcount
    if not actualizado:
        raise HTTPException(409, "La propuesta no está disponible para aceptar.")
    datos["resumen"] = resumen
    db.execute("UPDATE reportes_obra SET datos=%s WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
               (Jsonb(datos), empresa, pid, parte_id))
    auditoria.registrar(db, usuario, "parte.transcripcion_aceptada", proyecto_id=pid, objeto="parte_obra",
                        objeto_id=parte_id, detalle={"audio_id": audio_id}, request=request)
