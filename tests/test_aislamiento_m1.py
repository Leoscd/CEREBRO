"""La documentación solo aparece para quien tiene permiso sobre esa fuente."""
import pytest
from fastapi import HTTPException

from app import config
from app.permisos import obtener_archivo
from app.services import busqueda
from tests.conftest import csrf_de
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


def test_documentador_revalida_ids_de_chunks_ajenos(db, mundo, como, documentos_m1, monkeypatch):
    from app.agentes import documentador
    from app.agentes.modelo_falso import ModeloFalso

    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "falso")
    ana = mundo["ana"]
    cliente = como("ana@a.test")
    ruta = f"/proyectos/{mundo['p1']['codigo']}/documentador"
    for clave in ("p2", "pb"):
        doc = documentos_m1[clave]
        chunk = db.execute(
            """SELECT c.id FROM chunks c JOIN archivos a ON a.version_actual_id = c.version_id
                WHERE c.empresa_id = %s AND c.proyecto_id = %s AND a.id = %s AND c.pagina = 2""",
            (mundo[clave]["empresa_id"], mundo[clave]["id"], doc["id"]),
        ).fetchone()["id"]
        monkeypatch.setattr(
            documentador, "crear_modelo_falso", lambda: ModeloFalso("leer_fragmento", {"chunk_id": chunk}),
        )
        respuesta = cliente.post(ruta, headers={"X-CSRF": csrf_de(ana)}, json={"mensaje": "Buscá el fragmento"})
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["citas"] == []
        assert doc["frase"] not in respuesta.text
        llamada = db.execute(
            """SELECT tc.herramienta, tc.argumentos, tc.resultado_resumen, tc.estado
                 FROM tool_calls tc JOIN agent_runs ar ON ar.id = tc.agent_run_id AND ar.empresa_id = tc.empresa_id
                WHERE tc.empresa_id = %s AND ar.conversacion_id = %s ORDER BY tc.id DESC LIMIT 1""",
            (ana["empresa_id"], respuesta.json()["conversacion_id"]),
        ).fetchone()
        assert llamada == {"herramienta": "leer_fragmento", "argumentos": {"chunk_id": chunk},
                           "resultado_resumen": "no encontrado", "estado": "no encontrado"}
        assert doc["frase"] not in str(llamada)
