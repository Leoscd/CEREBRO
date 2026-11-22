"""Indexación de PDF, citas por página y visibilidad del proyecto."""
import os
import subprocess
import sys

import pytest

from tests.fixtures.pdf import pdf_de_paginas
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen
from tests.test_versiones import accion, nueva_version

FRASE = "cimborrio turquesa"


def procesar_pendientes(db):
    from app.worker import procesar_uno

    db.commit()
    while procesar_uno(db):
        pass


def buscar(cliente, proyecto, consulta=FRASE):
    return cliente.get(f"/proyectos/{proyecto['codigo']}/buscar", params={"q": consulta})


@pytest.fixture()
def pdf_indexable(db, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    usuario = mundo["ana"]
    cliente = como("ana@a.test")
    contenido = pdf_de_paginas("Primera pagina", f"El {FRASE} es la referencia del detalle.")
    assert subir(cliente, usuario, proyecto, primera_carpeta(db, proyecto), "Detalles.pdf", contenido).status_code == 303
    archivo, = archivos_del_proyecto(db, proyecto)
    return archivo["id"]


def test_worker_indexa_y_la_busqueda_cita_pagina_dos(db_url, mundo, como, directorio_almacen, pdf_indexable):
    subprocess.run(
        [sys.executable, "-m", "app.worker", "--una-vez"], check=True, timeout=35,
        env={**os.environ, "DATABASE_URL": db_url, "ALMACEN_DIR": str(directorio_almacen)},
    )
    respuesta = buscar(como("ana@a.test"), mundo["p1"])
    assert respuesta.status_code == 200
    assert f"/archivos/{pdf_indexable}#page=2" in respuesta.text
    assert "<mark>cimborrio</mark>" in respuesta.text


def test_busqueda_filtra_empresa_proyecto_y_archivo_privado(db, mundo, como, pdf_indexable):
    procesar_pendientes(db)
    assert buscar(como("ana@a.test"), mundo["p2"]).status_code == 404
    for email in ("admin@b.test", "cliente@a.test"):
        respuesta = buscar(como(email), mundo["p1"])
        assert respuesta.status_code == 200
        assert "#page=" not in respuesta.text
    assert f"/archivos/{pdf_indexable}#page=2" in buscar(como("ana@a.test"), mundo["p1"]).text


def test_busqueda_excluye_papelera_y_versiones_anteriores(db, mundo, como, pdf_indexable):
    procesar_pendientes(db)
    admin = como("admin@a.test")
    usuario = mundo["admin_a"]
    proyecto = mundo["p1"]
    url = f"/archivos/{pdf_indexable}"
    assert f"{url}#page=2" in buscar(admin, proyecto).text
    assert accion(admin, usuario, url, "papelera").status_code == 303
    assert "#page=" not in buscar(admin, proyecto).text
    assert accion(admin, usuario, url, "restaurar").status_code == 303
    assert nueva_version(admin, usuario, url, pdf_de_paginas("Detalle sin la frase", "")).status_code == 303
    assert "#page=" not in buscar(admin, proyecto).text
    procesar_pendientes(db)
    assert "#page=" not in buscar(admin, proyecto).text
    assert db.execute(
        """SELECT v.numero FROM chunks c JOIN versiones_archivo v ON v.id = c.version_id
            WHERE c.empresa_id = %s AND c.proyecto_id = %s AND v.archivo_id = %s""",
        (usuario["empresa_id"], proyecto["id"], pdf_indexable),
    ).fetchall() == [{"numero": 2}]
    assert nueva_version(admin, usuario, url, pdf_de_paginas("", "")).status_code == 303
    procesar_pendientes(db)
    assert db.execute(
        """SELECT derivados->>'texto' AS estado FROM versiones_archivo
            WHERE empresa_id = %s AND archivo_id = %s AND numero = 3""",
        (usuario["empresa_id"], pdf_indexable),
    ).fetchone() == {"estado": "sin_texto"}


def test_fragmentos_respetan_palabras_solapamiento_y_pagina(tmp_path):
    from app.services.texto import fragmentos_pdf

    palabras = [f"palabra{i}" for i in range(280)]
    pdf = tmp_path / "paginas.pdf"
    pdf.write_bytes(pdf_de_paginas("", " ".join(palabras)))
    fragmentos = list(fragmentos_pdf(pdf))
    assert len(fragmentos) >= 3
    assert all(pagina == 2 and texto and len(texto) <= 1000 for pagina, _, texto in fragmentos)
    listas = [texto.split() for _, _, texto in fragmentos]
    assert set(palabras) == {palabra for lista in listas for palabra in lista}
    assert 100 <= len(" ".join(palabra for palabra in listas[0] if palabra in listas[1])) <= 170
