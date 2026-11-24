import json
from datetime import timedelta
from io import BytesIO

import pytest

from app import config
from app.agentes import obra
from app.agentes.modelo_falso import ModeloFalso
from app.services import cronograma, partes
from app.services.tiempo import hoy_local
from tests.conftest import csrf_de
from tests.test_partes import PNG


def _tarea(db, proyecto):
    hoy = hoy_local()
    return cronograma.crear_tarea(db, proyecto, {
        "codigo": "T", "nombre": "Replanteo", "inicio": hoy, "fin": hoy, "critica": True,
        "rubro": "", "item_presupuesto_id": None,
    })


def _guion(monkeypatch, herramienta, argumentos):
    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "falso")
    monkeypatch.setattr(obra, "crear_modelo_falso",
                        lambda: ModeloFalso(herramienta, argumentos, responder=lambda salida: salida))


def _sesion(como, usuario, proyecto):
    return (como(usuario["email"]), f"/proyecto/{proyecto['codigo']}/obra/agente",
            {"X-CSRF": csrf_de(usuario)})


def _proponer(cliente, ruta, headers):
    respuesta = cliente.post(ruta, headers=headers, json={"mensaje": "Revisá mi parte."})
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["estado"] == "esperando_aprobacion"
    assert cliente.get(ruta).json()["aprobaciones"] == datos["aprobaciones"]
    llamada, = datos["aprobaciones"]
    return f"/agentes/runs/{datos['run_id']}/tool-calls/{llamada['id']}"


def test_avance_y_cierre_con_aprobacion(db, mundo, como, monkeypatch, tmp_path):
    usuario, proyecto = mundo["admin_a"], mundo["p1"]
    cliente, ruta, headers = _sesion(como, usuario, proyecto)
    tarea = _tarea(db, proyecto)
    db.commit()
    hoy = hoy_local()
    _guion(monkeypatch, "registrar_avance", {"fecha": hoy.isoformat(), "tarea_id": tarea,
                                             "avance_pb": 2500, "detalle": "Eje A"})
    assert 'data-agente="Obra"' in cliente.get(ruta.removesuffix("/agente")).text
    assert cliente.post(ruta, json={"mensaje": "Hola"}).status_code == 403
    llamada = _proponer(cliente, ruta, headers)
    assert partes.buscar_dia(db, proyecto, usuario, hoy) is None
    assert cliente.post(llamada + "/aprobar", headers=headers).status_code == 200
    parte = partes.buscar_dia(db, proyecto, usuario, hoy)
    assert parte["estado"] == "borrador" and parte["datos"]["avances"][0]["avance_pb"] == 2500
    _guion(monkeypatch, "cerrar_reporte", {"fecha": hoy.isoformat()})
    incompleto = cliente.post(ruta, headers=headers, json={"mensaje": "Cerrá el parte."})
    assert incompleto.status_code == 409 and "Fotos" in incompleto.text
    monkeypatch.setattr(config, "ALMACEN_DIR", tmp_path)
    for seccion, datos in [("condiciones", {"confirmado": "1"}), ("jornada", {"tipo": "completa"}),
                           ("personal", {"empresa": "Estudio", "categoria": "Oficial", "cantidad": "3"}),
                           ("hys", {"epp_ok": "1"})]:
        partes.actualizar_seccion(db, usuario, proyecto, parte["id"], seccion, datos)
    for indice in range(partes.MIN_FOTOS):
        partes.agregar_foto(db, usuario, proyecto, parte["id"], BytesIO(PNG), f"Vista {indice}", tarea)
    db.commit()
    llamada = _proponer(cliente, ruta, headers)
    assert partes.obtener(db, proyecto, parte["id"])["numero"] is None
    assert cliente.post(llamada + "/aprobar", headers=headers).status_code == 200
    assert partes.obtener(db, proyecto, parte["id"])["numero"] == 1
    assert db.execute("SELECT payload FROM jobs WHERE tipo='parte.pdf'").fetchall() == [
        {"payload": {"proyecto_id": proyecto["id"], "parte_id": parte["id"]}}]


def test_reporte_confirmado_solo_permite_consultas(db, mundo, como, monkeypatch):
    usuario, proyecto = mundo["admin_a"], mundo["p1"]
    hoy = hoy_local()
    parte, _ = partes.crear_borrador(db, usuario, proyecto, hoy)
    for seccion, datos in [("condiciones", {"confirmado": "1"}), ("jornada", {"tipo": "no_laborable"}),
                           ("hys", {"epp_ok": "1"})]:
        partes.actualizar_seccion(db, usuario, proyecto, parte["id"], seccion, datos)
    cerrado = partes.confirmar(db, usuario, proyecto, parte["id"])
    db.commit()
    cliente, ruta, headers = _sesion(como, usuario, proyecto)
    for nombre, args in [
        ("registrar_avance", {"tarea_id": 1, "avance_pb": 500, "detalle": ""}),
        ("registrar_personal", {"empresa": "A", "categoria": "Oficial", "cantidad": 2}),
        ("registrar_nota", {"texto": "Esperar revisión"}),
        ("registrar_pedido", {"material": "Cal", "cantidad": "2", "unidad": "bolsas", "detalle": ""}),
        ("cerrar_reporte", {}),
    ]:
        _guion(monkeypatch, nombre, {"fecha": hoy.isoformat(), **args})
        r = cliente.post(ruta, headers=headers, json={"mensaje": "Actualizá."})
        assert r.status_code == 409 and "parte cerrado" in r.text.lower()
    assert partes.obtener(db, proyecto, parte["id"]) == cerrado
    assert not db.execute("SELECT 1 FROM tool_calls WHERE estado='pendiente'").fetchone()
    _guion(monkeypatch, "resumen_obra", {})
    r = cliente.post(ruta, headers=headers, json={"mensaje": "Resumen"})
    assert json.loads(r.json()["respuesta"])["ultimo_parte"]["numero"] == 1


@pytest.mark.parametrize("otro", ["p2", "pb"])
def test_tarea_de_otra_obra_es_inaccesible(db, mundo, como, monkeypatch, otro):
    tarea = _tarea(db, mundo[otro])
    db.commit()
    _guion(monkeypatch, "registrar_avance", {"fecha": hoy_local().isoformat(), "tarea_id": tarea,
                                             "avance_pb": 500, "detalle": ""})
    cliente, ruta, headers = _sesion(como, mundo["admin_a"], mundo["p1"])
    r = cliente.post(ruta, headers=headers, json={"mensaje": "Cargá el avance."})
    assert r.status_code == 404 and "no encontrad" in r.text
    assert not db.execute("SELECT 1 FROM tool_calls").fetchone()


def test_modelo_y_permisos(mundo, como, monkeypatch):
    cliente, ruta, headers = _sesion(como, mundo["admin_a"], mundo["p1"])
    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "openai")
    monkeypatch.setattr(config, "MODELO_OBRA", "")
    r = cliente.post(ruta, headers=headers, json={"mensaje": "Hola"})
    assert r.status_code == 503 and "MODELO_OBRA" in r.text
    _guion(monkeypatch, "registrar_nota", {"fecha": hoy_local().isoformat(), "texto": "Replanteo"})
    for rol, estado in [("ana", 403), ("cliente", 404)]:
        cliente, ruta, headers = _sesion(como, mundo[rol], mundo["p1"])
        assert cliente.post(ruta, headers=headers, json={"mensaje": "Anotá."}).status_code == estado


def test_personal_notas_y_pedidos_quedan_en_el_borrador(db, mundo, como, monkeypatch):
    usuario, proyecto = mundo["admin_a"], mundo["p1"]
    cliente, ruta, headers = _sesion(como, usuario, proyecto)
    hoy = hoy_local()
    for nombre, args, decision in [
        ("registrar_nota", {"texto": "Descartar"}, "rechazar"),
        ("registrar_nota", {"texto": "Primera visita"}, "aprobar"),
        ("registrar_nota", {"texto": "Revisar eje A"}, "aprobar"),
        ("registrar_personal", {"empresa": "Estudio", "categoria": "Oficial", "cantidad": 3}, "aprobar"),
        ("registrar_pedido", {"material": "Cal", "cantidad": "2,5", "unidad": "kg", "detalle": "Muro"}, "aprobar"),
    ]:
        _guion(monkeypatch, nombre, {"fecha": hoy.isoformat(), **args})
        llamada = _proponer(cliente, ruta, headers)
        assert cliente.post(f"{llamada}/{decision}", headers=headers).status_code == 200
    datos = partes.buscar_dia(db, proyecto, usuario, hoy)["datos"]
    assert datos["resumen"] == "Primera visita\nRevisar eje A"
    assert datos["personal"] == [{"empresa": "Estudio", "categoria": "Oficial", "cantidad": 3}]
    assert datos["materiales"]["faltantes"] == [{"material": "Cal", "cantidad": "2.5", "unidad": "kg", "detalle": "Muro"}]


def test_aprobacion_de_ayer_no_escribe_en_el_nuevo_dia(db, mundo, como, monkeypatch):
    usuario, proyecto = mundo["admin_a"], mundo["p1"]
    cliente, ruta, headers = _sesion(como, usuario, proyecto)
    hoy = hoy_local()
    _guion(monkeypatch, "registrar_nota", {"fecha": hoy.isoformat(), "texto": "Visita de obra"})
    llamada = _proponer(cliente, ruta, headers)
    monkeypatch.setattr(obra.herramientas_obra, "hoy_local", lambda: hoy + timedelta(days=1))
    r = cliente.post(llamada + "/aprobar", headers=headers)
    assert r.status_code == 409 and "parte de hoy" in r.text
    assert not db.execute("SELECT 1 FROM reportes_obra").fetchone()
