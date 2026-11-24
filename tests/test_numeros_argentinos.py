from decimal import Decimal

from app.services import dinero, presupuestos
from app.templates import templates
from tests import test_presupuestos
from tests.test_apus import apu_nuevo, material
from tests.test_formularios_navegador import formulario

presupuesto_muestra = test_presupuestos.presupuesto_muestra


def test_presupuesto_formato_argentino_y_mismo_total(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    cliente = como(mundo["admin_a"]["email"])
    pagina = f"/presupuestos/{p['id']}"
    destino = f"{pagina}/items"
    datos = formulario(cliente, pagina, destino, unidad="u", descripcion="Muestra sin cargo", cantidad="42,5", precio="0")
    r = cliente.post(destino, data=datos)
    assert r.status_code == 303, r.text
    r = cliente.get(pagina)
    assert "42,5" in r.text and "15,00 %" in r.text and "3,3333" in r.text
    assert dinero.formatear(11542) in r.text
    assert presupuestos.calcular(db, p["empresa_id"], p["id"])["total_centavos"] == 11542
    editado = f"{pagina}/editar"
    campos = formulario(cliente, pagina, editado, gastos_generales_pct="15")
    assert cliente.post(editado, data=campos).status_code == 303
    assert cliente.post(editado, data=campos | {"gastos_generales_pct": "10,555"}).status_code == 400
    assert db.execute("SELECT gastos_generales_pb FROM presupuestos WHERE id=%s", (p["id"],)).fetchone() == {
        "gastos_generales_pb": 1500,
    }


def test_apu_cantidad_con_punto_o_coma_y_desperdicio_exacto(db, mundo, como):
    actor = mundo["admin_a"]
    cliente = como(actor["email"])
    aid = apu_nuevo(db, actor["empresa_id"], "Formato")
    mid = material(db, actor["empresa_id"], "Listón")
    db.commit()
    pagina = f"/precios/apus/{aid}"
    destino = f"{pagina}/insumos"
    datos = formulario(cliente, pagina, destino, material_id=str(mid), cantidad="42.5", desperdicio_pct="10,5")
    assert cliente.post(destino, data=datos).status_code == 303
    assert cliente.post(destino, data=datos | {"cantidad": "42,5"}).status_code == 303
    assert cliente.post(destino, data=datos | {"desperdicio_pct": "10,501"}).status_code == 400
    fila = db.execute("SELECT cantidad,desperdicio_pb FROM apu_insumos WHERE apu_id=%s AND material_id=%s",
                      (aid, mid)).fetchone()
    assert fila == {"cantidad": Decimal("42.5"), "desperdicio_pb": 1050}
    pantalla = cliente.get(pagina)
    assert "42,5" in pantalla.text and "10,50 %" in pantalla.text


def test_filtros_de_cantidad_y_porcentaje():
    filtros = templates.env.filters
    assert filtros["porcentaje"](-1500) == "-15,00 %"
    assert filtros["cantidad"](Decimal("16.0000")) == "16"
    assert filtros["cantidad"](Decimal("1234.5000")) == "1.234,5"


def test_certificado_recibe_avance_en_porcentaje(db, mundo, como, presupuesto_muestra):
    cliente = como(mundo["admin_a"]["email"])
    pagina = f"/presupuestos/{presupuesto_muestra['id']}"
    datos = formulario(cliente, pagina, f"{pagina}/emitir")
    assert cliente.post(f"{pagina}/emitir", data=datos).status_code == 303
    ruta = f"{pagina}/certificados"
    datos = formulario(cliente, ruta)
    campo = next(nombre for nombre in datos if nombre.startswith("avance_pct_"))
    assert datos[campo] == "0,00"
    respuesta = cliente.post(ruta, data=datos | {campo: "12,5"})
    assert respuesta.status_code == 303, respuesta.text
    detalle = cliente.get(respuesta.headers["location"])
    assert "12,50 %" in detalle.text
    item = int(campo.removeprefix("avance_pct_"))
    assert db.execute("SELECT avance_pb FROM certificado_items WHERE item_presupuesto_id=%s", (item,)).fetchone() == {
        "avance_pb": 1250,
    }
