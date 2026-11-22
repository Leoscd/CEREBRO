"""Aprobación, retiro y acceso por empresa a los criterios."""
from tests.conftest import csrf_de
from tests.fixtures.pdf import pdf_de_paginas
from tests.test_busqueda import buscar, procesar_pendientes
from tests.test_subida import directorio_almacen as directorio_almacen


def subir_criterio(db, cliente, usuario, titulo, *paginas):
    pdf = pdf_de_paginas(*paginas)
    respuesta = cliente.post(
        "/admin/biblioteca",
        data={"csrf": csrf_de(usuario), "titulo": titulo, "tipo": "criterio", "version": "1"},
        files={"archivo": ("Criterio.pdf", pdf, "application/pdf")},
    )
    assert respuesta.status_code == 303
    doc = db.execute(
        "SELECT id FROM biblioteca_documentos WHERE empresa_id = %s AND titulo = %s",
        (usuario["empresa_id"], titulo),
    ).fetchone()
    return doc["id"], pdf


def transicion(cliente, usuario, doc_id, accion):
    return cliente.post(f"/admin/biblioteca/{doc_id}/{accion}", data={"csrf": csrf_de(usuario)})


def test_admin_publica_criterio_para_ambos_proyectos_y_puede_retirarlo(db, mundo, como, directorio_almacen):
    admin = como("admin@a.test")
    ana, beto = como("ana@a.test"), como("beto@a.test")
    autor = mundo["admin_a"]
    consulta = "arriostramiento colibrí"
    assert admin.get("/admin/biblioteca").status_code == 200
    assert ana.get("/admin/biblioteca").status_code == 403
    doc_id, pdf = subir_criterio(db, admin, autor, "Criterio de obra", "Índice general", consulta)
    procesar_pendientes(db)
    ruta = f"/admin/biblioteca/{doc_id}/contenido"
    assert ruta not in buscar(ana, mundo["p1"], consulta).text
    assert ana.get(ruta).status_code == 404
    assert admin.get(ruta).content == pdf
    assert transicion(ana, mundo["ana"], doc_id, "aprobar").status_code == 403
    assert transicion(admin, autor, doc_id, "aprobar").status_code == 303
    for cliente, proyecto in [(ana, mundo["p1"]), (beto, mundo["p2"])]:
        html = buscar(cliente, proyecto, consulta).text
        assert ruta + "#page=2" in html
        assert "Criterio de obra" in html and "Biblioteca" in html
        assert cliente.get(ruta).content == pdf
    assert db.execute(
        """SELECT embedding IS NOT NULL AS embebido FROM chunks
            WHERE empresa_id = %s AND biblioteca_id = %s AND pagina = 2""",
        (autor["empresa_id"], doc_id),
    ).fetchone() == {"embebido": True}
    assert transicion(admin, autor, doc_id, "retirar").status_code == 303
    assert ruta not in buscar(ana, mundo["p1"], consulta).text
    assert ana.get(ruta).status_code == 404
    eventos = db.execute(
        """SELECT accion FROM auditoria WHERE empresa_id = %s AND objeto = 'biblioteca' AND objeto_id = %s
           ORDER BY id""",
        (autor["empresa_id"], str(doc_id)),
    ).fetchall()
    assert [fila["accion"] for fila in eventos] == ["biblioteca.subir", "biblioteca.aprobar", "biblioteca.retirar"]


def test_documento_de_otra_empresa_no_se_puede_leer_ni_publicar(db, mundo, como, directorio_almacen):
    admin_b = como("admin@b.test")
    usuario_b = mundo["admin_b"]
    doc_id, _ = subir_criterio(db, admin_b, usuario_b, "Criterio de B", "hormigón nacarado")
    procesar_pendientes(db)
    assert transicion(admin_b, usuario_b, doc_id, "aprobar").status_code == 303
    ruta = f"/admin/biblioteca/{doc_id}/contenido"
    assert ruta in buscar(admin_b, mundo["pb"], "hormigón").text
    admin_a = como("admin@a.test")
    assert admin_a.get(ruta).status_code == 404
    assert transicion(admin_a, mundo["admin_a"], doc_id, "retirar").status_code == 404
    assert ruta not in buscar(admin_a, mundo["p1"], "hormigón").text
    assert "Criterio de B" not in admin_a.get("/admin/biblioteca").text
