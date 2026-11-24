from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config
from app.services import cronograma, partes
from tests.conftest import csrf_de

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII="
)


def test_confirmaciones_simultaneas_numeran_sin_huecos(db, db_url, mundo):
    proyecto, usuario = mundo["p1"], mundo["admin_a"]
    datos = partes.datos_iniciales()
    datos.update(condiciones={"confirmado": True}, jornada={"tipo": "no_laborable"}, hys={"epp_ok": True})
    ids = []
    for dia in (23, 24):
        parte, _ = partes.crear_borrador(db, usuario, proyecto, date(2026, 11, dia))
        ids.append(parte["id"])
    db.execute("UPDATE reportes_obra SET datos=%s WHERE proyecto_id=%s", (Jsonb(datos), proyecto["id"]))
    db.commit()
    barrera = Barrier(2)

    def confirmar(parte_id):
        with psycopg.connect(db_url, row_factory=dict_row) as conexion:
            barrera.wait(10)
            return partes.confirmar(conexion, usuario, proyecto, parte_id)["numero"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirmar, ids)) == [1, 2]


def test_parte_confirmado_solo_permite_consultas_y_registra_el_avance(db, mundo, como, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ALMACEN_DIR", tmp_path)
    proyecto, usuario = mundo["p1"], mundo["admin_a"]
    tarea = cronograma.crear_tarea(db, proyecto, {
        "codigo": "A", "nombre": "Replanteo", "inicio": date(2026, 11, 23),
        "fin": date(2026, 11, 25), "critica": True, "rubro": "", "item_presupuesto_id": None,
    })
    db.commit()
    cliente = como(usuario["email"])
    base = f"/proyecto/{proyecto['codigo']}/obra/partes"
    formulario = {"csrf": csrf_de(usuario)}
    assert cliente.post(f"{base}/hoy").status_code == 403
    creado = cliente.post(f"{base}/hoy", data=formulario)
    assert creado.status_code == 303
    url = creado.headers["location"]
    assert cliente.post(f"{url}/confirmar", data=formulario).status_code == 409
    for seccion, campos in [
        ("condiciones", {"texto": "Suelo seco", "confirmado": "1"}),
        ("jornada", {"tipo": "completa"}),
        ("personal", {"empresa": "Capataz SRL", "categoria": "Oficial", "cantidad": "2"}),
        ("avances", {"tarea_id": str(tarea), "avance_pb": "2500"}),
        ("hys", {"epp_ok": "1"}),
    ]:
        r = cliente.post(f"{url}/secciones/{seccion}", data=formulario | campos)
        assert r.status_code == 303, r.text
    invalida = cliente.post(f"{url}/fotos", data=formulario, files={"foto": ("falsa.png", b"texto", "image/png")})
    assert invalida.status_code == 400
    for indice in range(3):
        r = cliente.post(f"{url}/fotos", data=formulario | {"descripcion": f"Vista {indice}"},
                         files={"foto": ("obra.png", PNG, "image/png")})
        assert r.status_code == 303, r.text
    assert cliente.post(f"{url}/confirmar", data=formulario).status_code == 303
    assert cliente.post(f"{url}/secciones/jornada", data=formulario | {"tipo": "parcial"}).status_code == 409
    assert cliente.post(f"{url}/fotos", data=formulario, files={"foto": ("otra.png", PNG)}).status_code == 409
    assert cliente.get(url).status_code == 200
    assert "Admin A" in cliente.get(base).text
    parte = db.execute("SELECT * FROM reportes_obra WHERE proyecto_id=%s", (proyecto["id"],)).fetchone()
    assert parte["numero"] == 1
    assert cronograma.avance_obra(db, proyecto, parte["fecha"])["real_pb"] == 2500
    for tabla, alcance in [("reportes_obra", "id"), ("fotos_obra", "reporte_id")]:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"UPDATE {tabla} SET {alcance}={alcance} WHERE {alcance}=%s", (parte["id"],))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"DELETE FROM {tabla} WHERE {alcance}=%s", (parte["id"],))
    assert db.execute(
        "SELECT 1 FROM auditoria WHERE accion='parte.confirmado' AND proyecto_id=%s AND objeto_id=%s",
        (proyecto["id"], str(parte["id"])),
    ).fetchone()


def test_cliente_colaborador_y_empresa_ajena(db, mundo, como):
    proyecto = mundo["p1"]
    base = f"/proyecto/{proyecto['codigo']}/obra/partes"
    externo = mundo["cliente"]
    cliente = como(externo["email"])
    assert cliente.get(base).status_code == 404
    assert cliente.post(f"{base}/hoy", data={"csrf": csrf_de(externo)}).status_code == 404
    colaborador = mundo["ana"]
    assert como(colaborador["email"]).post(f"{base}/hoy", data={"csrf": csrf_de(colaborador)}).status_code == 403
    actor = mundo["admin_a"]
    borrador, _ = partes.crear_borrador(db, actor, proyecto, date(2026, 11, 24))
    db.commit()
    otra_empresa = como(mundo["admin_b"]["email"])
    otro = mundo["pb"]["codigo"]
    assert otra_empresa.get(f"/proyecto/{otro}/obra/partes/{borrador['id']}").status_code == 404
    assert como(colaborador["email"]).get(f"/proyecto/{mundo['p2']['codigo']}/obra/partes").status_code == 404
