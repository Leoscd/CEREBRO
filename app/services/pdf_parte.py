"""Generación y publicación del PDF del parte diario confirmado."""

from io import BytesIO
from unicodedata import normalize

from fpdf import FPDF
from PIL import Image, ImageOps

from app.services import almacen, auditoria, jobs, partes
from app.services.tiempo import formatear

_REEMPLAZOS = str.maketrans({"–": "-", "—": "-", "’": "'", "“": '"', "”": '"', "…": "..."})


def _texto(valor):
    texto = normalize("NFC", str(valor or "")).translate(_REEMPLAZOS)
    return texto.encode("latin-1", "replace").decode("latin-1")


class _PDFParte(FPDF):
    def __init__(self, numero):
        super().__init__(format="A4")
        self.numero = f"{numero:03d}"
        self.set_auto_page_break(auto=True, margin=16)
        self.alias_nb_pages()

    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 10, f"Parte N.º {self.numero}", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", size=10)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.cell(0, 5, f"Parte N.º {self.numero} · página {self.page_no()} de {{nb}}", align="R")


def _parrafo(pdf, texto):
    pdf.multi_cell(0, 5, _texto(texto), new_x="LMARGIN", new_y="NEXT")


def _seccion(pdf, titulo, lineas):
    if not lineas:
        return
    if pdf.will_page_break(15):
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(235)
    pdf.cell(0, 7, _texto(titulo), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for linea in lineas:
        _parrafo(pdf, linea)


def _foto(pdf, foto):
    epigrafe = " · ".join(str(v) for v in (foto["descripcion"], foto["tarea"], formatear(foto["hora"])) if v)
    try:
        with Image.open(almacen.ruta(foto["sha256"])) as original:
            imagen = ImageOps.exif_transpose(original)
            imagen.thumbnail((900, 900))
            reducido = BytesIO()
            imagen.convert("RGB").save(reducido, format="JPEG", quality=82)
            ancho, alto = imagen.size
    except (OSError, ValueError, Image.DecompressionBombError):
        _parrafo(pdf, f"Foto no disponible · {epigrafe}")
        return
    escala = min(105 / ancho, 68 / alto)
    if pdf.will_page_break(alto * escala + 14):
        pdf.add_page()
    reducido.seek(0)
    pdf.image(reducido, x=pdf.l_margin, w=ancho * escala, h=alto * escala)
    _parrafo(pdf, epigrafe)
    pdf.ln(3)


def generar(parte, fotos):
    pdf = _PDFParte(parte["numero"])
    pdf.add_page()
    datos = parte["datos"]
    _parrafo(pdf, f"Obra: {parte['obra']} · {parte['codigo']}")
    _parrafo(pdf, f"Fecha: {formatear(parte['fecha'], con_hora=False)} · DT: {parte['dt_nombre']}")
    condiciones = datos["condiciones"]
    clima = (condiciones.get("propuesto") or {}).get("resumen") or "Sin datos automáticos"
    texto_condiciones = condiciones.get("texto")
    _parrafo(pdf, f"Clima: {clima}" + (f" · {texto_condiciones}" if texto_condiciones else ""))
    _seccion(pdf, "Observaciones", [datos["resumen"]] if datos["resumen"] else [])
    jornada = datos["jornada"]
    _seccion(pdf, "Jornada", [jornada["tipo"].replace("_", " ").capitalize(), jornada.get("detalle", "")])
    _seccion(pdf, "Personal", [f"{p['empresa']} · {p['categoria']} · {p['cantidad']}" for p in datos["personal"]])
    _seccion(pdf, "Avances", [
        f"{a['tarea']} · {a['avance_pb'] / 100:.2f} % · {a['detalle']}" for a in datos["avances"]
    ])
    for clave, titulo in (("ingresos", "Ingresos"), ("faltantes", "Faltantes"), ("stock", "Stock")):
        _seccion(pdf, f"Materiales · {titulo}", [
            " · ".join(str(v) for v in (m["material"], m["cantidad"], m["unidad"], m["detalle"]) if v)
            for m in datos["materiales"][clave]
        ])
    _seccion(pdf, "Equipos", [f"{e['equipo']} · {e['detalle']}" for e in datos["equipos"]])
    hys = datos["hys"]
    _seccion(pdf, "Higiene y seguridad", [
        f"Uso de EPP: {'Sí' if hys['epp_ok'] else 'No'}",
        *[f"{campo.capitalize()}: {hys[campo]}" for campo in ("visitas", "incidentes") if hys.get(campo)],
    ])
    if fotos:
        _seccion(pdf, "Fotos", [f"{len(fotos)} imágenes"])
        for foto in fotos:
            _foto(pdf, foto)
    return bytes(pdf.output())


def publicar(db, empresa_id, payload):
    pid, parte_id = payload["proyecto_id"], payload["parte_id"]
    proyecto = db.execute(
        "SELECT id,empresa_id FROM proyectos WHERE empresa_id=%s AND id=%s FOR UPDATE", (empresa_id, pid),
    ).fetchone()
    if proyecto is None or db.execute(
        """SELECT 1 FROM auditoria WHERE empresa_id=%s AND proyecto_id=%s
            AND accion='parte.pdf_generado' AND objeto='parte_obra' AND objeto_id=%s""",
        (empresa_id, pid, str(parte_id)),
    ).fetchone():
        return
    parte = db.execute(
        """SELECT r.*,p.nombre AS obra,p.codigo,u.nombre AS dt_nombre FROM reportes_obra r
             JOIN proyectos p ON p.empresa_id=r.empresa_id AND p.id=r.proyecto_id
             JOIN usuarios u ON u.empresa_id=r.empresa_id AND u.id=r.dt_id
            WHERE r.empresa_id=%s AND r.proyecto_id=%s AND r.id=%s AND r.estado='confirmado'""",
        (empresa_id, pid, parte_id),
    ).fetchone()
    if parte is None:
        return
    contenido = generar(parte, partes.fotos(db, proyecto, parte_id))
    sha, tamano = almacen.guardar(BytesIO(contenido))
    archivo_id, version_id = partes.archivar_adjunto(
        db, {"id": parte["dt_id"]}, proyecto, "Bitácora", f"Parte {parte['numero']:03d} - {parte['fecha']}.pdf",
        "pdf", "application/pdf", sha, tamano, origen="agente",
    )
    jobs.encolar(db, empresa_id, "archivo.analizar", {"version_id": version_id})
    jobs.encolar(db, empresa_id, "archivo.indexar", {"version_id": version_id})
    auditoria.registrar(db, None, "parte.pdf_generado", empresa_id=empresa_id, proyecto_id=pid, objeto="parte_obra",
                        objeto_id=parte_id, detalle={"archivo_id": archivo_id, "version_id": version_id})
