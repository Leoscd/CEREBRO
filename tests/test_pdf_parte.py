from base64 import b64decode

from pypdf import PdfReader

from app import config
from app.services import almacen, busqueda, jobs
from app.services.tiempo import hoy_local
from app.worker import procesar_uno
from tests.conftest import csrf_de

PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOQi1oAAAGyARnBUHQ0AAAAAElFTkSuQmCC")


def test_generar_y_publicar_pdf_del_parte_sin_duplicados(db, mundo, como, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ALMACEN_DIR", tmp_path)
    proyecto, usuario = mundo["p1"], mundo["admin_a"]
    cliente = como(usuario["email"])
    base = f"/proyecto/{proyecto['codigo']}/obra/partes"
    csrf = {"csrf": csrf_de(usuario)}
    parte = cliente.post(f"{base}/hoy", data=csrf).headers["location"]
    frase = "Se verificó la alineación del cañón de desagüe."
    for seccion, campos in (
        ("condiciones", {"texto": "Terreno húmedo", "confirmado": "1"}),
        ("jornada", {"tipo": "no_laborable"}),
        ("hys", {"epp_ok": "1"}),
        ("resumen", {"texto": frase}),
    ):
        assert cliente.post(f"{parte}/secciones/{seccion}", data=csrf | campos).status_code == 303
    r = cliente.post(f"{parte}/fotos", data=csrf | {"descripcion": "Cañería recién inspeccionada"},
                     files={"foto": ("foto.png", PNG, "image/png")})
    assert r.status_code == 303, r.text
    assert cliente.post(f"{parte}/confirmar", data=csrf).status_code == 303
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    trabajo = db.execute("SELECT * FROM jobs WHERE empresa_id=%s AND tipo='parte.pdf'", (empresa,)).fetchone()
    assert trabajo is not None and trabajo["estado"] == "pendiente"
    jobs.encolar(db, empresa, "parte.pdf", trabajo["payload"])
    db.commit()
    for _ in range(8):
        if not procesar_uno(db):
            break
    assert db.execute("SELECT count(*) AS total FROM jobs WHERE tipo='parte.pdf' AND estado='hecho'").fetchone()["total"] == 2
    archivos = db.execute(
        """SELECT a.id,a.nombre,v.sha256,v.origen FROM archivos a
             JOIN carpetas c ON c.empresa_id=a.empresa_id AND c.proyecto_id=a.proyecto_id AND c.id=a.carpeta_id
             JOIN versiones_archivo v ON v.empresa_id=a.empresa_id AND v.archivo_id=a.id AND v.id=a.version_actual_id
            WHERE a.empresa_id=%s AND a.proyecto_id=%s AND c.nombre='Bitácora' AND a.extension='pdf'""",
        (empresa, pid),
    ).fetchall()
    assert len(archivos) == 1
    archivo, = archivos
    assert archivo["nombre"] == f"Parte 001 - {hoy_local().isoformat()}.pdf"
    assert archivo["origen"] == "agente"
    pdf = PdfReader(almacen.ruta(archivo["sha256"]))
    texto = "\n".join(pagina.extract_text() for pagina in pdf.pages)
    assert "Parte N.º 001" in texto and hoy_local().strftime("%d/%m/%Y") in texto
    assert frase in texto and "Cañería recién inspeccionada" in texto
    assert any(pagina.images for pagina in pdf.pages)
    assert f"página 1 de {len(pdf.pages)}" in texto
    hallazgos = busqueda.buscar_palabras(db, usuario, proyecto, '"alineación del cañón"')
    assert hallazgos and hallazgos[0]["archivo_id"] == archivo["id"] and hallazgos[0]["pagina"] == 1
    vista = cliente.get(f"/archivos/{archivo['id']}/contenido")
    assert vista.status_code == 200 and vista.content.startswith(b"%PDF-")
