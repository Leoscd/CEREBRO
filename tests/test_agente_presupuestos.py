import json
import math
from datetime import datetime
from decimal import Decimal

import pytest
from agents import ModelResponse, Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from app import config
from app.agentes import calc, presupuestos as agente
from app.agentes.modelo_falso import ModeloFalso
from app.services import precios, presupuestos
from app.services.tiempo import TZ
from tests import test_presupuestos
from tests.conftest import csrf_de

presupuesto_muestra = test_presupuestos.presupuesto_muestra


def test_calc_aritmetica_y_variables():
    assert calc.safe_eval("2 + 3 * 4") == 14
    assert calc.safe_eval("(2 + 3) * 4") == 20
    assert calc.safe_eval("2 ** 10 + 13 // 5 + 13 % 5") == 1029
    assert calc.safe_eval("10 / 4") == Decimal("2.5")
    assert calc.safe_eval("precio * cantidad", {"precio": 100, "cantidad": Decimal("5.001")}) == Decimal("500.1")
    assert float(calc.safe_eval("pi * 2")) == pytest.approx(math.pi * 2)
    assert float(calc.safe_eval("e")) == pytest.approx(math.e)


@pytest.mark.parametrize("expr", ["__import__('os')", "(2).real", "open('archivo')", "'a' + 'b'",
                                  "", "9 ** 99999", "[x for x in (1,)]", "1/0", "True + 1"])
def test_calc_rechaza_expresiones_no_admitidas(expr):
    with pytest.raises(calc.ExpresionInvalida):
        calc.safe_eval(expr)


def _respuesta(herramienta, argumentos, call):
    salida = ResponseFunctionToolCall(
        type="function_call", name=herramienta, arguments=json.dumps(argumentos), call_id=call,
    )
    return ModelResponse(output=[salida], usage=Usage(requests=1), response_id=None)


def _texto(texto):
    mensaje = ResponseOutputMessage(
        type="message", role="assistant", status="completed", id="mensaje-t023",
        content=[ResponseOutputText(type="output_text", text=texto, annotations=[])],
    )
    return ModelResponse(output=[mensaje], usage=Usage(requests=1), response_id=None)


def _salidas(input_modelo):
    return [json.loads(i["output"]) for i in input_modelo if i.get("type") == "function_call_output"]


def _sesion(como, mundo, p, monkeypatch):
    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "falso")
    usuario = mundo["admin_a"]
    return como(usuario["email"]), f"/presupuestos/{p['id']}/agente", {"X-CSRF": csrf_de(usuario)}


def test_agente_catalogo_aprobacion_y_total(db, mundo, como, presupuesto_muestra, monkeypatch):
    p = presupuesto_muestra

    class Guion(ModeloFalso):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            salidas = _salidas(input)
            if not salidas:
                return _respuesta("catalogo_buscar", {"consulta": "Cemento"}, "catalogo-t023")
            if len(salidas) == 1:
                assert salidas[0]["materiales"][0]["codigo"] == "Cemento"
                return _respuesta("agregar_items", {
                    "presupuesto_id": p["id"], "items": [{"rubro": "Fundaciones", "descripcion": "Material adicional",
                    "unidad": "kg", "cantidad": "1.0000", "apu_id": None, "precio_unitario_centavos": 100}],
                }, "items-t023")
            return _texto(f"Total del cálculo: {salidas[-1]['total_centavos']} centavos.")

    monkeypatch.setattr(agente, "crear_modelo_falso", Guion)
    cliente, ruta, headers = _sesion(como, mundo, p, monkeypatch)
    assert 'data-agente="Presupuestos"' in cliente.get(f"/presupuestos/{p['id']}").text
    r = cliente.post(ruta, headers=headers, json={"mensaje": "Agregá un ítem."})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["estado"] == "esperando_aprobacion"
    llamada, = datos["aprobaciones"]
    assert llamada["herramienta"] == "agregar_items"
    assert presupuestos.calcular(db, p["empresa_id"], p["id"])["total_centavos"] == 11542
    assert cliente.get(ruta).json()["aprobaciones"] == datos["aprobaciones"]
    r = cliente.post(f"/agentes/runs/{datos['run_id']}/tool-calls/{llamada['id']}/aprobar", headers=headers, json={})
    assert r.status_code == 200, r.text
    # Nuevo CD 7641. GG 1146, beneficio 879, impuestos 2030. Total 11696 centavos.
    assert "11696 centavos" in r.json()["respuesta"]
    assert presupuestos.calcular(db, p["empresa_id"], p["id"])["total_centavos"] == 11696
    assert db.execute("SELECT 1 FROM items_presupuesto WHERE presupuesto_id=%s AND descripcion='Material adicional'",
                      (p["id"],)).fetchone()


def test_agente_rechaza_ids_ajenos_antes_de_guardar_aprobacion(db, mundo, como, presupuesto_muestra, monkeypatch):
    p = presupuesto_muestra
    b = mundo["admin_b"]
    ajeno = db.execute(
        """INSERT INTO materiales(empresa_id,codigo,nombre,unidad,tipo)
           VALUES (%s,'OCULTO','Material de B','kg','material') RETURNING id""", (b["empresa_id"],),
    ).fetchone()["id"]
    precios.cargar(db, b, ajeno, 777, datetime(2026, 2, 1, tzinfo=TZ))
    otro = db.execute(
        """INSERT INTO presupuestos(empresa_id,proyecto_id,nombre,fecha_precios,creado_por)
           VALUES (%s,%s,'PDF privado','2026-02-01',%s) RETURNING id""",
        (p["empresa_id"], mundo["p2"]["id"], mundo["admin_a"]["id"]),
    ).fetchone()["id"]
    db.commit()

    class Guion(ModeloFalso):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            salidas = _salidas(input)
            if not salidas:
                return _respuesta("presupuesto_leer", {"presupuesto_id": otro}, "lee-ajeno")
            assert salidas == [{"error": "Presupuesto no encontrado."}]
            return _respuesta("precio_cargar", {"material_id": ajeno, "precio_centavos": 600,
                                               "vigente_desde": "2026-03-01", "proveedor_id": None}, "precio-ajeno")

    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "falso")
    monkeypatch.setattr(agente, "crear_modelo_falso", Guion)
    usuario = mundo["ana"]
    db.execute(
        """INSERT INTO usuario_areas(usuario_id,area_id) SELECT %s,id FROM areas
            WHERE empresa_id=%s AND codigo='gestion_administrativa'""", (usuario["id"], p["empresa_id"]),
    )
    db.commit()
    cliente = como(usuario["email"])
    r = cliente.post(f"/presupuestos/{p['id']}/agente", headers={"X-CSRF": csrf_de(usuario)}, json={"mensaje": "Revisá."})
    assert r.status_code == 404 and "no encontrado" in r.json()["detail"]
    assert "Material de B" not in r.text and "PDF privado" not in r.text
    assert db.execute("SELECT 1 FROM tool_calls").fetchone() is None


def test_agente_sin_modelo_devuelve_503(como, mundo, presupuesto_muestra, monkeypatch):
    cliente, ruta, headers = _sesion(como, mundo, presupuesto_muestra, monkeypatch)
    monkeypatch.setattr(config, "AGENTES_PROVEEDOR", "openai")
    monkeypatch.setattr(config, "MODELO_PRESUPUESTOS", "")
    r = cliente.post(ruta, headers=headers, json={"mensaje": "Revisá."})
    assert r.status_code == 503 and "MODELO_PRESUPUESTOS" in r.json()["detail"]


def test_agente_indexa_el_precio_propuesto_solo_al_aprobar(db, mundo, como, presupuesto_muestra, monkeypatch):
    p = presupuesto_muestra
    insumo = db.execute("SELECT id FROM materiales WHERE empresa_id=%s AND codigo='Cemento'",
                        (p["empresa_id"],)).fetchone()["id"]
    db.execute("""INSERT INTO indices_costo(empresa_id,nombre,periodo,valor)
                  VALUES (%s,'CAC','2026-01-01',100),(%s,'CAC','2026-02-01',115)""",
               (p["empresa_id"], p["empresa_id"]))
    db.commit()
    periodos = {"indice": "CAC", "periodo_base": "2026-01-01", "periodo_destino": "2026-02-01"}

    class Guion(ModeloFalso):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            salidas = _salidas(input)
            if not salidas:
                return _respuesta("precio_vigente", {"material_id": insumo, "a_fecha": "2026-01-31",
                                                     "ajuste": periodos}, "lee-indice")
            if len(salidas) == 1:
                cotizacion = salidas[0]["cotizacion_propuesta"]
                # 880 × 115 / 100 = 1012 centavos.
                assert cotizacion["precio_centavos"] == 1012
                return _respuesta("actualizar_por_indice", periodos | {"cotizaciones": [cotizacion]}, "ajusta")
            return _texto(str(salidas[-1]["cotizaciones"][0]["precio_centavos"]))

    monkeypatch.setattr(agente, "crear_modelo_falso", Guion)
    cliente, ruta, headers = _sesion(como, mundo, p, monkeypatch)
    r = cliente.post(ruta, headers=headers, json={"mensaje": "Ajustá por el índice."})
    assert r.status_code == 200, r.text
    datos = r.json()
    llamada, = datos["aprobaciones"]
    assert llamada["argumentos"]["cotizaciones"][0]["precio_centavos"] == 1012
    assert db.execute("SELECT 1 FROM precios WHERE material_id=%s AND fuente='agente'", (insumo,)).fetchone() is None
    r = cliente.post(f"/agentes/runs/{datos['run_id']}/tool-calls/{llamada['id']}/aprobar", headers=headers, json={})
    assert r.status_code == 200 and r.json()["respuesta"] == "1012", r.text
    assert db.execute("SELECT precio_centavos FROM precios WHERE material_id=%s ORDER BY id", (insumo,)).fetchall() == [
        {"precio_centavos": 880}, {"precio_centavos": 1012},
    ]


def test_limites_de_consultas_y_rondas(como, mundo, presupuesto_muestra, monkeypatch):
    cliente, ruta, headers = _sesion(como, mundo, presupuesto_muestra, monkeypatch)
    monkeypatch.setattr(config, "PRESUPUESTOS_MAX_RONDAS", 1)
    monkeypatch.setattr(config, "PRESUPUESTOS_CONSULTAS_POR_HORA", 1)
    primera = cliente.post(ruta, headers=headers, json={"mensaje": "Buscá cemento."})
    assert primera.status_code == 429 and "rondas" in primera.json()["detail"]
    segunda = cliente.post(ruta, headers=headers, json={"mensaje": "Buscá cemento otra vez."})
    assert segunda.status_code == 429 and "por hora" in segunda.json()["detail"]
