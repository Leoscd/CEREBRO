from io import StringIO
from xml.etree import ElementTree

import ezdxf
import pytest

from app import config
from tests.test_busqueda import buscar, procesar_pendientes
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


def _plano():
    doc = ezdxf.new()
    doc.layers.add("COTAS", color=3)
    doc.layers.add("AUXILIAR").off()
    modelo = doc.modelspace()
    modelo.add_line((0, 0), (10, 10))
    modelo.add_text("Cota empilastrada", dxfattribs={"layer": "COTAS"})
    modelo.add_mtext("Moldura turquesina", dxfattribs={"layer": "COTAS"})
    bloque = doc.blocks.new("Marca")
    bloque.add_line((0, 0), (1, 1))
    referencia = modelo.add_blockref("Marca", (5, 5))
    referencia.add_attrib("ID", "Pilastra singular", dxfattribs={"layer": "COTAS"})
    salida = StringIO()
    doc.write(salida)
    return salida.getvalue().encode(doc.output_encoding)


def _subir_plano(db, mundo, como, contenido):
    p = mundo["p2"]
    assert subir(como("admin@a.test"), mundo["admin_a"], p, primera_carpeta(db, p),
                 "Plano.dxf", contenido, "application/dxf").status_code == 303
    archivo, = archivos_del_proyecto(db, p)
    return f"/archivos/{archivo['id']}"


def test_vista_capas_textos_y_aislamiento(db, mundo, como, directorio_almacen):
    ruta = _subir_plano(db, mundo, como, _plano())
    admin = como("admin@a.test")
    assert "Preparando la vista previa" in admin.get(ruta).text
    procesar_pendientes(db)
    datos = db.execute("SELECT derivados FROM versiones_archivo").fetchone()["derivados"]
    assert datos["vista"] == "lista" and datos["meta"]["dxf"]["cantidad_textos"] == 3
    assert {"nombre": "COTAS", "color": 3, "encendida": True, "congelada": False} in datos["meta"]["dxf"]["capas"]
    r = admin.get(ruta + "/vista.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    assert r.headers["cache-control"] == "private, no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert ElementTree.fromstring(r.content).tag.endswith("}svg")
    pagina = admin.get(ruta).text
    assert f'<img src="{ruta}/vista.svg"' in pagina and "AUXILIAR" in pagina and "apagada" in pagina
    for palabra in ["empilastrada", "turquesina", "singular"]:
        assert ruta + "#page=1" in buscar(admin, mundo["p2"], palabra).text
    for email, proyecto in [("ana@a.test", "p1"), ("admin@b.test", "pb")]:
        otro = como(email)
        assert otro.get(ruta + "/vista.svg").status_code == 404
        assert ruta + "#page=" not in buscar(otro, mundo[proyecto], "turquesina").text


@pytest.mark.parametrize("contenido,limite", [(b"basura", 50), (b"grande", 0)])
def test_plano_invalido_o_grande(db, mundo, como, directorio_almacen, monkeypatch, contenido, limite):
    monkeypatch.setattr(config, "DXF_MAX_MB", limite, raising=False)
    ruta = _subir_plano(db, mundo, como, contenido)
    procesar_pendientes(db)
    fila = db.execute("SELECT derivados FROM versiones_archivo").fetchone()
    assert fila["derivados"].get("vista") == "error" and "svg" not in fila["derivados"]
    assert db.execute("SELECT estado FROM jobs WHERE tipo='archivo.dxf'").fetchone()["estado"] == "hecho"
    assert "La vista previa no está disponible" in como("admin@a.test").get(ruta).text
