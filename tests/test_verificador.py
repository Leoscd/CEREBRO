from datetime import datetime

import pytest

from app.services import precios, verificador
from app.services.tiempo import TZ
from tests import test_presupuestos
from tests.conftest import csrf_de
from tests.test_apus import apu_nuevo, material, poner_insumo

presupuesto_muestra = test_presupuestos.presupuesto_muestra


def _caso(db, mundo, p, codigo):
    empresa, pid = p["empresa_id"], p["id"]
    items = db.execute(
        "SELECT id FROM items_presupuesto WHERE empresa_id=%s AND presupuesto_id=%s ORDER BY id", (empresa, pid),
    ).fetchall()
    primero, segundo, tercero = [i["id"] for i in items[:3]]
    cambios = {
        "cantidad_no_positiva": ("cantidad=0", tercero),
        "unidad_distinta": ("unidad='m3'", primero),
        "item_duplicado": ("descripcion='Viga'", tercero),
        "peso_alto": ("precio_unitario_centavos=4000", segundo),
    }
    if codigo in cambios:
        cambio, item_id = cambios[codigo]
        db.execute(f"UPDATE items_presupuesto SET {cambio} WHERE empresa_id=%s AND id=%s", (empresa, item_id))
    elif codigo in {"sin_precio", "precio_viejo"}:
        apu = apu_nuevo(db, empresa, "Auxiliar")
        insumo = material(db, empresa, "Auxiliar")
        poner_insumo(db, empresa, apu, insumo, "1")
        if codigo == "precio_viejo":
            precios.cargar(db, mundo["admin_a"], insumo, 99, datetime(2025, 10, 1, tzinfo=TZ))
        db.execute(
            "UPDATE items_presupuesto SET apu_id=%s,precio_unitario_centavos=NULL WHERE empresa_id=%s AND id=%s",
            (apu, empresa, tercero),
        )
    elif codigo == "rubro_vacio":
        db.execute(
            "INSERT INTO rubros_presupuesto(empresa_id,presupuesto_id,nombre,orden) VALUES (%s,%s,'Otro',9)",
            (empresa, pid),
        )
    elif codigo == "coeficiente_alto":
        db.execute("UPDATE presupuestos SET gastos_generales_pb=5001 WHERE empresa_id=%s AND id=%s", (empresa, pid))


@pytest.mark.parametrize(("codigo", "severidad"), [
    ("sano", None), ("sin_precio", "error"), ("cantidad_no_positiva", "error"), ("unidad_distinta", "error"),
    ("precio_viejo", "aviso"), ("rubro_vacio", "aviso"), ("item_duplicado", "aviso"),
    ("coeficiente_alto", "aviso"), ("peso_alto", "aviso"),
])
def test_cada_defecto_genera_solo_su_hallazgo(db, mundo, presupuesto_muestra, codigo, severidad):
    p = presupuesto_muestra
    _caso(db, mundo, p, codigo)
    lista = verificador.analizar(db, p["empresa_id"], p["id"])
    assert [(h["codigo"], h["severidad"]) for h in lista] == ([] if severidad is None else [(codigo, severidad)])
    assert all(h["mensaje"] for h in lista)


def test_emitir_bloquea_errores_y_acepta_avisos(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    _caso(db, mundo, p, "cantidad_no_positiva")
    _caso(db, mundo, p, "rubro_vacio")
    db.commit()
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    ruta = f"/presupuestos/{p['id']}"
    datos = {"csrf": csrf_de(admin)}
    respuesta = cliente.post(f"{ruta}/emitir", data=datos)
    assert respuesta.status_code == 409
    assert "La cantidad tiene que ser mayor que cero" in respuesta.text
    assert db.execute("SELECT estado FROM presupuestos WHERE id=%s", (p["id"],)).fetchone()["estado"] == "borrador"
    db.execute("UPDATE items_presupuesto SET cantidad=0.75 WHERE presupuesto_id=%s AND cantidad=0", (p["id"],))
    db.commit()
    assert cliente.post(f"{ruta}/emitir", data=datos).status_code == 303
    assert db.execute("SELECT estado FROM presupuestos WHERE id=%s", (p["id"],)).fetchone()["estado"] == "emitido"


def test_hallazgos_repetibles(db, mundo, presupuesto_muestra):
    p = presupuesto_muestra
    for codigo in ("precio_viejo", "unidad_distinta", "peso_alto", "coeficiente_alto"):
        _caso(db, mundo, p, codigo)
    primero = verificador.analizar(db, p["empresa_id"], p["id"])
    assert len(primero) == 4
    assert verificador.analizar(db, p["empresa_id"], p["id"]) == primero
