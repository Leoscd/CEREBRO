"""Validación previa a la publicación y limpieza global de blobs."""
import os
import subprocess
import sys
import time
from io import BytesIO

from app.services import almacen
from tests.conftest import csrf_de
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


def _hace_horas(ruta, horas):
    instante = time.time() - horas * 3600
    os.utime(ruta, (instante, instante))


def _limpiar(db_url, directorio, *opciones):
    corrida = subprocess.run(
        [sys.executable, "-m", "scripts.limpiar_almacen", "--horas", "24", *opciones],
        env={**os.environ, "DATABASE_URL": db_url, "ALMACEN_DIR": str(directorio)},
        capture_output=True, text=True, timeout=30,
    )
    assert corrida.returncode == 0, corrida.stderr
    return corrida.stdout


def test_biblioteca_rechaza_no_pdf_sin_publicar_blob(mundo, como, directorio_almacen):
    admin = como("admin@a.test")
    respuesta = admin.post(
        "/admin/biblioteca",
        data={"csrf": csrf_de(mundo["admin_a"]), "titulo": "Criterio", "tipo": "criterio", "version": "1"},
        files={"archivo": ("falso.pdf", b"Esto no es un PDF", "application/pdf")},
    )
    assert respuesta.status_code == 400
    assert not list(directorio_almacen.rglob("*"))


def test_limpieza_conserva_referencias_de_otra_empresa_en_ambas_tablas(db, db_url, mundo, como, directorio_almacen):
    proyecto, admin_b = mundo["pb"], mundo["admin_b"]
    respuesta = subir(como("admin@b.test"), admin_b, proyecto, primera_carpeta(db, proyecto),
                      "Texto.txt", b"referencia empresa B", "text/plain")
    assert respuesta.status_code == 303
    archivo, = archivos_del_proyecto(db, proyecto)
    criterio, _ = almacen.guardar(BytesIO(b"criterio empresa B"))
    db.execute(
        """INSERT INTO biblioteca_documentos (empresa_id, titulo, tipo, version, sha256, nombre_archivo)
           VALUES (%s, 'Criterio B', 'criterio', '1', %s, 'criterio.pdf')""",
        (admin_b["empresa_id"], criterio),
    )
    db.commit()
    rutas = [almacen.ruta(archivo["sha256"]), almacen.ruta(criterio)]
    for ruta in rutas:
        _hace_horas(ruta, 25)
    salida = _limpiar(db_url, directorio_almacen, "--borrar")
    assert all(ruta.exists() and ruta.name not in salida for ruta in rutas)


def test_limpieza_lista_y_borra_solo_huerfanos_y_temporales_viejos(db_url, directorio_almacen):
    viejo, _ = almacen.guardar(BytesIO(b"sin referencias"))
    nuevo, _ = almacen.guardar(BytesIO(b"subido hace un segundo"))
    reutilizado, _ = almacen.guardar(BytesIO(b"por reutilizar"))
    _hace_horas(almacen.ruta(viejo), 26)
    _hace_horas(almacen.ruta(reutilizado), 26)
    assert almacen.guardar(BytesIO(b"por reutilizar"))[0] == reutilizado
    temporal_viejo = directorio_almacen / ".subida-vieja"
    temporal_nuevo = directorio_almacen / ".subida-nueva"
    temporal_viejo.write_bytes(b"temporal viejo")
    temporal_nuevo.write_bytes(b"temporal nuevo")
    _hace_horas(temporal_viejo, 26)
    extra = directorio_almacen / "archivo-que-no-es-un-blob"
    extra.write_bytes(b"guardar")
    _hace_horas(extra, 26)
    salida = _limpiar(db_url, directorio_almacen)
    assert viejo in salida and temporal_viejo.name in salida
    assert nuevo not in salida and reutilizado not in salida and temporal_nuevo.name not in salida
    assert almacen.ruta(viejo).exists() and temporal_viejo.exists()
    salida = _limpiar(db_url, directorio_almacen, "--borrar")
    assert "2 archivos" in salida and "29 bytes" in salida
    assert not almacen.ruta(viejo).exists() and not temporal_viejo.exists()
    assert almacen.ruta(nuevo).exists() and almacen.ruta(reutilizado).exists()
    assert temporal_nuevo.exists() and extra.exists()
