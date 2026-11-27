import multiprocessing
import os
import sys
import time

import pytest

from app.services import proceso_aislado as aislado


def error_de_dominio():
    raise ValueError("x")


def sin_memoria():
    raise MemoryError


def limite_virtual():
    import resource
    return resource.getrlimit(resource.RLIMIT_AS)[0]


def test_tiempo_limite_recoge_el_hijo():
    previos = {p.pid for p in multiprocessing.active_children()}
    inicio = time.monotonic()
    with pytest.raises(aislado.TrabajoAbortado, match="tiempo"):
        aislado.ejecutar(time.sleep, 5, segundos=1, memoria_mb=512)
    assert time.monotonic() - inicio < 3
    assert {p.pid for p in multiprocessing.active_children()} <= previos


def test_distingue_caida_memoria_y_dominio():
    with pytest.raises(aislado.TrabajoAbortado, match="137"):
        aislado.ejecutar(os._exit, 137, segundos=10, memoria_mb=512)
    with pytest.raises(aislado.TrabajoAbortado, match="memoria"):
        aislado.ejecutar(sin_memoria, segundos=10, memoria_mb=512)
    with pytest.raises(aislado.ErrorDelTrabajo, match="^x$"):
        aislado.ejecutar(error_de_dominio, segundos=10, memoria_mb=512)


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS se aplica en Linux")
def test_limite_de_memoria_en_el_hijo():
    assert aislado.ejecutar(limite_virtual, segundos=10, memoria_mb=512) == 512 * 1024**2


def test_ifc_abortado_queda_hecho_y_el_visor_informa(db, mundo, como, monkeypatch, tmp_path):
    from app import config
    from tests.test_busqueda import procesar_pendientes
    from tests.test_ifc import _modelo, _subir_ifc

    def abortar(*args, **kwargs):
        raise aislado.TrabajoAbortado("tiempo agotado")

    monkeypatch.setattr(config, "ALMACEN_DIR", tmp_path)
    monkeypatch.setattr(aislado, "ejecutar", abortar)
    ruta = _subir_ifc(db, mundo, como, _modelo())
    procesar_pendientes(db)
    assert db.execute("SELECT derivados FROM versiones_archivo").fetchone()["derivados"]["vista_ifc"] == "error"
    assert db.execute("SELECT estado, intentos FROM jobs WHERE tipo='archivo.ifc'").fetchone() == {
        "estado": "hecho", "intentos": 1,
    }
    html = como("admin@a.test").get(ruta).text
    assert 'id="visor-modelo3d"' in html and "no está disponible" in html
