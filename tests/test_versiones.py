"""Ciclo de versiones, papelera y archivos compartidos."""
import pytest

from tests.conftest import csrf_de
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


@pytest.fixture()
def plano(db, mundo, como, directorio_almacen):
    proyecto = mundo["p1"]
    admin = como("admin@a.test")
    respuesta = subir(admin, mundo["admin_a"], proyecto, primera_carpeta(db, proyecto),
                      nombre="Plano inicial.pdf", contenido=b"%PDF-1.7 original")
    assert respuesta.status_code == 303
    archivo, = archivos_del_proyecto(db, proyecto)
    return f"/archivos/{archivo['id']}", f"/proyecto/{proyecto['codigo']}", archivo["id"]


def accion(cliente, usuario, url, ruta, **datos):
    return cliente.post(f"{url}/{ruta}", data={"csrf": csrf_de(usuario), **datos})


def nueva_version(cliente, usuario, url, contenido=b"%PDF-1.7 nueva"):
    return cliente.post(f"{url}/versiones", data={"csrf": csrf_de(usuario)},
                        files={"archivo": ("Plano.pdf", contenido, "application/pdf")})


def test_nueva_version_conserva_historial_y_audita(db, mundo, como, plano):
    url, ficha, archivo_id = plano
    ana = como("ana@a.test")
    assert nueva_version(ana, mundo["ana"], url).status_code == 303
    assert ana.get(f"{url}/descargar").content == b"%PDF-1.7 nueva"
    assert ana.get(f"{url}/versiones/1/descargar").content == b"%PDF-1.7 original"
    assert f'href="{url}/versiones/1/descargar"' in ana.get(ficha).text
    assert db.execute(
        """SELECT usuario_id FROM auditoria
            WHERE empresa_id = %s AND proyecto_id = %s AND objeto_id = %s AND accion = 'archivo.version'""",
        (mundo["ea"]["id"], mundo["p1"]["id"], str(archivo_id)),
    ).fetchone() == {"usuario_id": mundo["ana"]["id"]}


def test_papelera_restauracion_y_visibilidad(db, mundo, como, plano):
    url, ficha, archivo_id = plano
    admin, usuario = como("admin@a.test"), mundo["admin_a"]
    cliente = como("cliente@a.test")
    assert accion(admin, usuario, url, "visibilidad", visible_cliente="1").status_code == 303
    assert "Plano inicial.pdf" in cliente.get(ficha).text
    assert cliente.get(f"{url}/descargar").status_code == 200

    assert accion(admin, usuario, url, "papelera").status_code == 303
    ficha_admin = admin.get(ficha).text
    assert f'href="{url}/descargar"' not in ficha_admin
    assert f'action="{url}/restaurar"' in ficha_admin
    assert admin.get(f"{url}/descargar").status_code == 404
    assert cliente.get(f"{url}/versiones/1/descargar").status_code == 404
    assert "Plano inicial.pdf" not in cliente.get(ficha).text
    assert accion(admin, usuario, url, "restaurar").status_code == 303
    assert cliente.get(f"{url}/descargar").status_code == 200
    assert accion(admin, usuario, url, "visibilidad").status_code == 303
    assert cliente.get(f"{url}/descargar").status_code == 404

    filas = db.execute(
        """SELECT accion FROM auditoria WHERE empresa_id = %s AND proyecto_id = %s AND objeto_id = %s
            ORDER BY id""",
        (mundo["ea"]["id"], mundo["p1"]["id"], str(archivo_id)),
    ).fetchall()
    assert [fila["accion"] for fila in filas] == [
        "archivo.subir", "archivo.visibilidad", "archivo.papelera", "archivo.restaurar", "archivo.visibilidad",
    ]


def test_cliente_y_colaborador_no_pueden_compartir(db, mundo, como, plano):
    url, _, archivo_id = plano
    db.execute("UPDATE archivos SET visible_cliente = true WHERE empresa_id = %s AND id = %s",
               (mundo["ea"]["id"], archivo_id))
    db.commit()
    cliente, usuario = como("cliente@a.test"), mundo["cliente"]
    assert nueva_version(cliente, usuario, url).status_code == 403
    assert accion(cliente, usuario, url, "papelera").status_code == 403
    assert accion(cliente, usuario, url, "visibilidad").status_code == 403
    assert accion(como("ana@a.test"), mundo["ana"], url, "visibilidad").status_code == 403


def test_otra_empresa_no_ve_ni_edita_versiones(mundo, como, plano):
    url, _, _ = plano
    admin, usuario = como("admin@b.test"), mundo["admin_b"]
    assert nueva_version(admin, usuario, url).status_code == 404
    assert admin.get(f"{url}/versiones/1/descargar").status_code == 404
    for ruta in ("papelera", "restaurar", "visibilidad"):
        assert accion(admin, usuario, url, ruta).status_code == 404
    assert como("admin@a.test").get(f"{url}/versiones/1/descargar").status_code == 200
