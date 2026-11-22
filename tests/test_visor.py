"""Visor local, tipo de contenido y aislamiento de archivos."""
import pytest

from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


@pytest.fixture()
def crear_archivo(db, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    carpeta = primera_carpeta(db, proyecto)
    cliente = como("ana@a.test")

    def crear(nombre, contenido, mime):
        assert subir(cliente, mundo["ana"], proyecto, carpeta, nombre, contenido, mime).status_code == 303
        ruta = "/archivos/{}".format(archivos_del_proyecto(db, proyecto)[-1]["id"])
        return cliente, ruta

    return crear


def test_pdf_referencia_visor_local_y_enlace_en_ficha(crear_archivo, mundo):
    cliente, ruta = crear_archivo("Plano.pdf", b"%PDF-1.7", "application/pdf")
    ficha = cliente.get(f"/proyecto/{mundo['p1']['codigo']}")
    assert f'href="{ruta}"' in ficha.text
    pagina = cliente.get(ruta)
    assert pagina.status_code == 200
    assert 'id="visor-pdf"' in pagina.text
    assert 'id="panel-agente"' in pagina.text
    assert '/static/vendor/pdfjs/pdf.mjs' in pagina.text
    assert 'src="https://' not in pagina.text
    assert cliente.get("/static/vendor/pdfjs/pdf.mjs").status_code == 200


def test_pdf_inline_y_archivos_activos_como_descarga(crear_archivo):
    for nombre, datos, mime, disposicion in [
        ("Plano.pdf", b"%PDF-1.7", "application/pdf", "inline"),
        ("imagen.svg", b"<svg/>", "image/svg+xml", "attachment"),
        ("pagina.html", b"<h1>Vista</h1>", "text/html", "attachment"),
        ("pagina.html", b"<h1>Vista</h1>", "application/pdf", "attachment"),
    ]:
        cliente, ruta = crear_archivo(nombre, datos, mime)
        respuesta = cliente.get(f"{ruta}/contenido")
        assert respuesta.status_code == 200
        assert respuesta.content == datos
        assert respuesta.headers["content-disposition"].startswith(disposicion)
        assert respuesta.headers["x-content-type-options"] == "nosniff"


def test_visor_y_contenido_de_archivo_ajeno_devuelven_404(crear_archivo, como):
    ana, ruta = crear_archivo("Plano.pdf", b"%PDF-1.7", "application/pdf")
    for email in ("admin@b.test", "cliente@a.test"):
        cliente = como(email)
        assert cliente.get(ruta).status_code == 404
        assert cliente.get(f"{ruta}/contenido").status_code == 404
    assert ana.get(ruta).status_code == 200
