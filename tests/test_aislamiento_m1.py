"""La documentación solo aparece para quien tiene permiso sobre esa fuente."""
import pytest
from fastapi import HTTPException

from app.permisos import obtener_archivo
from app.services import busqueda
from tests.test_busqueda import buscar, procesar_pendientes
from tests.test_hibrida import subir_pdf_de_busqueda
from tests.test_subida import directorio_almacen as directorio_almacen
from tests.test_versiones import accion


@pytest.fixture()
def documentos_m1(db, mundo, como, directorio_almacen):
    documentos = {}
    for proyecto, autor, email, frase in [
        ("p1", "admin_a", "admin@a.test", "sello pergamino celeste"),
        ("p2", "admin_a", "admin@a.test", "sello quetzal magenta"),
        ("pb", "admin_b", "admin@b.test", "sello brújula obsidiana"),
    ]:
        nombre = f"Detalles {proyecto}.pdf"
        archivo_id = subir_pdf_de_busqueda(
            db, como(email), mundo[autor], mundo[proyecto], nombre, "Portada de control", frase,
        )
        documentos[proyecto] = {"id": archivo_id, "nombre": nombre, "frase": frase}
    propio = documentos["p1"]["id"]
    assert accion(como("admin@a.test"), mundo["admin_a"], f"/archivos/{propio}",
                  "visibilidad", visible_cliente="1").status_code == 303
    procesar_pendientes(db)
    return documentos


@pytest.mark.parametrize(("rol", "correo", "propio"), [
    ("ana", "ana@a.test", "p1"),
    ("cliente", "cliente@a.test", "p1"),
    ("admin_b", "admin@b.test", "pb"),
])
def test_cada_acceso_de_m1_aplica_aislamiento(db, mundo, como, documentos_m1, rol, correo, propio):
    persona = como(correo)
    usuario, proyecto = mundo[rol], mundo[propio]
    permitido = documentos_m1[propio]
    resultados = buscar(persona, proyecto, "sello")
    assert resultados.status_code == 200
    assert f"/archivos/{permitido['id']}#page=2" in resultados.text
    filas = busqueda.buscar(db, usuario, proyecto, "sello")
    assert [(fila["archivo_id"], fila["pagina"]) for fila in filas] == [(permitido["id"], 2)]
    assert permitido["frase"] in filas[0]["texto"]
    ficha = persona.get(f"/proyecto/{proyecto['codigo']}")
    assert permitido["nombre"] in ficha.text

    for clave, doc in documentos_m1.items():
        if clave == propio:
            continue
        assert doc["frase"] not in resultados.text and doc["nombre"] not in resultados.text
        assert f"/archivos/{doc['id']}#page=" not in resultados.text
        assert doc["nombre"] not in ficha.text
        assert busqueda.buscar(db, usuario, mundo[clave], "sello") == []
        respuesta_ajena = buscar(persona, mundo[clave], "sello")
        assert doc["nombre"] not in respuesta_ajena.text and doc["frase"] not in respuesta_ajena.text
        if mundo[clave]["codigo"] != proyecto["codigo"]:
            assert respuesta_ajena.status_code == 404
        for sufijo in ("", "/contenido", "/descargar", "/versiones/1/descargar", "/derivados"):
            respuesta = persona.get(f"/archivos/{doc['id']}{sufijo}")
            assert respuesta.status_code == 404
            assert doc["frase"].encode() not in respuesta.content
        with pytest.raises(HTTPException) as error:
            obtener_archivo(db, usuario, doc["id"])
        assert error.value.status_code == 404

    for archivo_id in range(min(d["id"] for d in documentos_m1.values()), max(d["id"] for d in documentos_m1.values()) + 1):
        estado = 200 if archivo_id == permitido["id"] else 404
        assert persona.get(f"/archivos/{archivo_id}/contenido").status_code == estado
