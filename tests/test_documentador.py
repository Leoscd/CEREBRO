"""Panel, ejecución del Agents SDK con modelo falso y persistencia del chat."""
import pytest

from app import config
from tests.conftest import csrf_de
from tests.test_busqueda import FRASE, procesar_pendientes
from tests.test_busqueda import pdf_indexable as pdf_indexable
from tests.test_subida import directorio_almacen as directorio_almacen
from tests.test_versiones import accion


@pytest.fixture()
def proveedor_falso(monkeypatch):
    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "falso", raising=False)


def test_documentador_cita_y_guarda_conversacion_sdk(db, mundo, como, pdf_indexable, proveedor_falso):
    procesar_pendientes(db)
    proyecto, usuario = mundo["p1"], mundo["ana"]
    cliente = como("ana@a.test")
    ruta = f"/proyectos/{proyecto['codigo']}/documentador"
    headers = {"X-CSRF": csrf_de(usuario)}
    assert 'id="panel-agente"' in cliente.get(f"/proyecto/{proyecto['codigo']}").text
    assert "/static/agente.js" in cliente.get(f"/archivos/{pdf_indexable}").text
    respuesta = cliente.post(ruta, headers=headers, json={"mensaje": FRASE})
    assert respuesta.status_code == 200, respuesta.text
    resultado = respuesta.json()
    cita, = resultado["citas"]
    assert (cita["archivo_id"], cita["pagina"], cita["url"]) == (pdf_indexable, 2, f"/archivos/{pdf_indexable}#page=2")
    assert "[Detalles.pdf, pág. 2]" in resultado["respuesta"]
    conv = resultado["conversacion_id"]
    historial = cliente.get(ruta).json()
    assert historial["conversacion_id"] == conv
    assert [mensaje["rol"] for mensaje in historial["mensajes"]] == ["user", "assistant"]
    assert historial["mensajes"][1]["citas"] == resultado["citas"]

    empresa_id = usuario["empresa_id"]
    assert db.execute(
        "SELECT usuario_id FROM conversaciones WHERE empresa_id = %s AND id = %s AND proyecto_id = %s",
        (empresa_id, conv, proyecto["id"]),
    ).fetchone() == {"usuario_id": usuario["id"]}
    assert db.execute(
        "SELECT count(*) AS n FROM mensajes WHERE empresa_id = %s AND conversacion_id = %s",
        (empresa_id, conv),
    ).fetchone()["n"] == 2
    run = db.execute(
        """SELECT id, estado, tokens_entrada, estado_sdk FROM agent_runs
            WHERE empresa_id = %s AND conversacion_id = %s""",
        (empresa_id, conv),
    ).fetchone()
    assert run["estado"] == "hecho" and run["tokens_entrada"] > 0 and run["estado_sdk"]
    assert "password_hash" not in str(run["estado_sdk"])
    llamada = db.execute(
        "SELECT herramienta, estado FROM tool_calls WHERE empresa_id = %s AND agent_run_id = %s",
        (empresa_id, run["id"]),
    ).fetchone()
    assert llamada == {"herramienta": "buscar_documentacion", "estado": "ok"}
    audit = db.execute(
        "SELECT detalle FROM auditoria WHERE empresa_id = %s AND proyecto_id = %s AND accion = 'agente.consulta'",
        (empresa_id, proyecto["id"]),
    ).fetchone()
    assert audit is not None and FRASE not in str(audit["detalle"])


def test_cliente_solo_cita_archivo_compartido_y_no_accede_a_conversacion_ajena(
    db, mundo, como, pdf_indexable, proveedor_falso,
):
    procesar_pendientes(db)
    p1, p2 = mundo["p1"], mundo["p2"]
    ruta = f"/proyectos/{p1['codigo']}/documentador"
    cliente = como("cliente@a.test")
    headers = {"X-CSRF": csrf_de(mundo["cliente"])}
    privada = cliente.post(ruta, headers=headers, json={"mensaje": FRASE})
    assert privada.status_code == 200
    assert privada.json()["citas"] == []
    assert FRASE not in privada.json()["respuesta"]
    admin = como("admin@a.test")
    usuario = mundo["admin_a"]
    archivo = f"/archivos/{pdf_indexable}"
    assert accion(admin, usuario, archivo, "visibilidad", visible_cliente="1").status_code == 303
    compartida = cliente.post(ruta, headers=headers, json={"mensaje": FRASE})
    assert compartida.status_code == 200
    assert compartida.json()["citas"][0]["archivo_id"] == pdf_indexable
    assert accion(admin, usuario, archivo, "visibilidad").status_code == 303
    assert all(not mensaje["citas"] for mensaje in cliente.get(ruta).json()["mensajes"])
    ajena = admin.post(ruta, headers={"X-CSRF": csrf_de(usuario)}, json={"mensaje": FRASE})
    assert ajena.status_code == 200
    conversacion = ajena.json()["conversacion_id"]
    assert cliente.post(ruta, headers=headers, json={"mensaje": FRASE, "conversacion_id": conversacion}).status_code == 404
    assert cliente.post(f"/proyectos/{p2['codigo']}/documentador", headers=headers, json={"mensaje": FRASE}).status_code == 404


def test_documentador_exige_csrf_y_explica_modelo_faltante(mundo, como, monkeypatch):
    cliente = como("ana@a.test")
    ruta = f"/proyectos/{mundo['p1']['codigo']}/documentador"
    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "openai", raising=False)
    monkeypatch.setattr(config, "MODELO_DOCUMENTADOR", "", raising=False)
    assert cliente.post(ruta, json={"mensaje": FRASE}).status_code == 403
    respuesta = cliente.post(ruta, headers={"X-CSRF": csrf_de(mundo["ana"])}, json={"mensaje": FRASE})
    assert respuesta.status_code == 503 and "MODELO_DOCUMENTADOR" in respuesta.json()["detail"]
