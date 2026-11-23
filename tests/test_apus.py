from datetime import date, datetime, time
from decimal import Decimal

import pytest
from psycopg.errors import ForeignKeyViolation

from app.services import apus, precios
from app.services.tiempo import TZ
from tests.conftest import csrf_de


def material(db, empresa, codigo):
    return db.execute(
        "INSERT INTO materiales(empresa_id,codigo,nombre,unidad,tipo) VALUES (%s,%s,%s,'kg','material') RETURNING id",
        (empresa, codigo, codigo),
    ).fetchone()["id"]


def apu_nuevo(db, empresa, codigo):
    return db.execute(
        "INSERT INTO apus(empresa_id,codigo,descripcion,unidad) VALUES (%s,%s,%s,'m2') RETURNING id",
        (empresa, codigo, codigo),
    ).fetchone()["id"]


def poner_insumo(db, empresa, apu, material_id, cantidad, desperdicio=0):
    db.execute(
        "INSERT INTO apu_insumos(empresa_id,apu_id,material_id,cantidad,desperdicio_pb) VALUES (%s,%s,%s,%s,%s)",
        (empresa, apu, material_id, Decimal(cantidad), desperdicio),
    )


def test_apu_redondea_cada_insumo_y_reconstruye_a_fecha(db, mundo):
    admin = mundo["admin_a"]
    empresa = admin["empresa_id"]
    apu = apu_nuevo(db, empresa, "Mampostería")
    enero = datetime(2026, 1, 1, tzinfo=TZ)
    for codigo, centavos, cantidad, desperdicio in [
        ("Cemento", 880, "0.1250", 1000),
        ("Jornal", 1050, "0.3550", 0),
        ("Equipo", 95, "0.1000", 500),
    ]:
        insumo = material(db, empresa, codigo)
        precios.cargar(db, admin, insumo, centavos, enero)
        poner_insumo(db, empresa, apu, insumo, cantidad, desperdicio)
    # 880 × 0,1250 × 1,10 = 121. 1050 × 0,3550 = 372,75 → 373.
    # 95 × 0,1000 × 1,05 = 9,975 → 10. Total: 121 + 373 + 10 = 504 centavos.
    vieja = date(2026, 2, 1)
    resultado = apus.precio_unitario(db, empresa, apu, vieja)
    assert resultado["total_centavos"] == 504
    assert sorted(fila["subtotal_centavos"] for fila in resultado["detalle"]) == [10, 121, 373]
    assert not resultado["faltantes"]
    cemento = db.execute(
        "SELECT id FROM materiales WHERE empresa_id=%s AND codigo='Cemento'", (empresa,),
    ).fetchone()["id"]
    precios.cargar(db, admin, cemento, 1600, datetime.combine(date(2026, 3, 1), time.min, TZ))
    assert apus.precio_unitario(db, empresa, apu, vieja)["total_centavos"] == 504
    # 1600 × 0,1250 × 1,10 = 220. Total nuevo: 220 + 373 + 10 = 603.
    assert apus.precio_unitario(db, empresa, apu, date(2026, 3, 1))["total_centavos"] == 603


def test_apu_faltante_visible_y_edicion(db, mundo, como):
    admin = mundo["admin_a"]
    empresa = admin["empresa_id"]
    insumo = material(db, empresa, "Arena")
    db.commit()
    cliente = como(admin["email"])
    csrf = csrf_de(admin)
    alta = cliente.post("/precios/apus", data={
        "csrf": csrf, "codigo": "AL-01", "descripcion": "Albañilería", "unidad": "m2",
    })
    assert alta.status_code == 303
    ruta = alta.headers["location"]
    guardar = cliente.post(f"{ruta}/insumos", data={
        "csrf": csrf, "material_id": insumo, "cantidad": "0.2500", "desperdicio_pb": 0,
    })
    assert guardar.status_code == 303
    apu = int(ruta.rsplit("/", 1)[1])
    resultado = apus.precio_unitario(db, empresa, apu, date.today())
    assert resultado["total_centavos"] == 0 and not resultado["detalle"]
    assert resultado["faltantes"][0]["nombre"] == "Arena"
    assert "Sin precio vigente" in cliente.get(ruta).text
    assert "Albañilería" in cliente.get("/precios/apus").text


def test_apu_aislado_por_base_y_rutas(db, mundo, como):
    a, b = mundo["admin_a"], mundo["admin_b"]
    apu_a = apu_nuevo(db, a["empresa_id"], "A")
    apu_b = apu_nuevo(db, b["empresa_id"], "B")
    ajeno = material(db, b["empresa_id"], "Material B")
    db.commit()
    with pytest.raises(ForeignKeyViolation), db.transaction():
        poner_insumo(db, a["empresa_id"], apu_a, ajeno, "1")
    cliente = como(a["email"])
    assert cliente.get(f"/precios/apus/{apu_b}").status_code == 404
    datos = {"csrf": csrf_de(a), "material_id": ajeno, "cantidad": "1.0000"}
    assert cliente.post(f"/precios/apus/{apu_a}/insumos", data=datos).status_code == 404
