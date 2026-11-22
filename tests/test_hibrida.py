"""Variaciones de consulta, filtro previo y biblioteca en la búsqueda híbrida."""
import pytest

from app import config
from app.services import busqueda
from tests.fixtures.pdf import pdf_de_paginas
from tests.test_busqueda import buscar, procesar_pendientes
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


def subir_pdf_de_busqueda(db, cliente, usuario, proyecto, nombre, *paginas):
    carpeta = primera_carpeta(db, proyecto)
    assert subir(cliente, usuario, proyecto, carpeta, nombre, pdf_de_paginas(*paginas)).status_code == 303
    return archivos_del_proyecto(db, proyecto)[-1]["id"]


def test_variacion_solo_aparece_en_busqueda_hibrida(db, mundo, como, directorio_almacen):
    p1, usuario = mundo["p1"], mundo["ana"]
    ana = como("ana@a.test")
    archivo_id = subir_pdf_de_busqueda(db, ana, usuario, p1, "Tabiques.pdf", "particiones resistentes")
    procesar_pendientes(db)
    consulta = "partisiones"
    assert busqueda.buscar_palabras(db, usuario, p1, consulta) == []
    respuesta = buscar(ana, p1, consulta)
    assert respuesta.status_code == 200
    assert f"/archivos/{archivo_id}#page=1" in respuesta.text


def test_vector_identico_de_otra_empresa_queda_fuera(db, mundo, como, directorio_almacen):
    consulta = "partisiones"
    p1, ana = mundo["p1"], mundo["ana"]
    pb, admin_b = mundo["pb"], mundo["admin_b"]
    propio = subir_pdf_de_busqueda(db, como("ana@a.test"), ana, p1, "Propio.pdf", "particiones")
    ajeno = subir_pdf_de_busqueda(db, como("admin@b.test"), admin_b, pb, "Ajeno.pdf", consulta)
    procesar_pendientes(db)
    # La coincidencia exacta se encuentra en B, incluso con tope de un resultado.
    assert [fila["archivo_id"] for fila in busqueda.buscar(db, admin_b, pb, consulta, limite=1)] == [ajeno]
    assert [fila["archivo_id"] for fila in busqueda.buscar(db, ana, p1, consulta, limite=1)] == [propio]
    assert busqueda.buscar(db, ana, pb, consulta) == []


def test_biblioteca_aprobada_solo_de_la_empresa_y_para_equipo(db, mundo, como):
    from app.services.embeddings import embeber, vector_sql

    frase = "arriostramiento modular"
    vector = vector_sql(embeber([frase])[0])
    for empresa, estado, titulo in [
        ("ea", "aprobado", "Criterio A"),
        ("ea", "borrador", "Borrador A"),
        ("ea", "retirado", "Retirado A"),
        ("eb", "aprobado", "Criterio B"),
    ]:
        empresa_id = mundo[empresa]["id"]
        doc = db.execute(
            """INSERT INTO biblioteca_documentos (empresa_id, titulo, tipo, version, estado, sha256, nombre_archivo)
               VALUES (%s, %s, 'criterio', '1', %s, %s, 'criterio.pdf') RETURNING id""",
            (empresa_id, titulo, estado, "0" * 64),
        ).fetchone()
        db.execute(
            """INSERT INTO chunks (empresa_id, biblioteca_id, pagina, orden, texto, embedding)
               VALUES (%s, %s, 2, 0, %s, %s::vector)""",
            (empresa_id, doc["id"], frase, vector),
        )
    db.commit()
    for usuario, proyecto in [("ana", "p1"), ("beto", "p2")]:
        fila, = busqueda.buscar(db, mundo[usuario], mundo[proyecto], frase)
        assert fila["nombre"] == "Criterio A" and fila["biblioteca_id"] and fila["pagina"] == 2
    assert busqueda.buscar(db, mundo["cliente"], mundo["p1"], frase) == []
    assert "Biblioteca" in buscar(como("ana@a.test"), mundo["p1"], frase).text


def test_openai_sin_modelo_devuelve_error_claro(monkeypatch):
    from app.services.embeddings import embeber

    monkeypatch.setattr(config, "EMBEDDINGS_PROVEEDOR", "openai", raising=False)
    monkeypatch.setattr(config, "MODELO_EMBEDDINGS", "", raising=False)
    with pytest.raises(RuntimeError, match="MODELO_EMBEDDINGS"):
        embeber(["prueba"])
