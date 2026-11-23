from datetime import datetime
from decimal import Decimal

import pytest
from psycopg import DatabaseError

from app.services import presupuestos, precios
from app.services.tiempo import TZ
from tests.conftest import csrf_de
from tests.test_apus import apu_nuevo, material, poner_insumo


@pytest.fixture
def presupuesto_muestra(db, mundo):
    admin = mundo["admin_a"]
    empresa = admin["empresa_id"]
    apu = apu_nuevo(db, empresa, "BASE-01")
    for codigo, precio, cantidad, desperdicio in [
        ("Cemento", 880, "0.1250", 1000), ("Jornal", 1050, "0.3550", 0), ("Equipo", 95, "0.1000", 500),
    ]:
        insumo = material(db, empresa, codigo)
        precios.cargar(db, admin, insumo, precio, datetime(2026, 1, 1, tzinfo=TZ))
        poner_insumo(db, empresa, apu, insumo, cantidad, desperdicio)
    presupuesto = db.execute(
        """INSERT INTO presupuestos(empresa_id,proyecto_id,nombre,fecha_precios,gastos_generales_pb,
                                    beneficio_pb,impuestos_pb,creado_por)
           VALUES (%s,%s,'Ensayo','2026-02-01',1500,1000,2100,%s) RETURNING *""",
        (empresa, mundo["p1"]["id"], admin["id"]),
    ).fetchone()
    for orden, (rubro, filas) in enumerate([
        ("Fundaciones", [("Excavación", "3.3333", apu, None), ("Viga", "1.1250", None, 2501),
                          ("Replanteo", "0.7500", None, 99)]),
        ("Estructura", [("Columna", "0.2000", None, 12345), ("Hormigón", "1.0001", apu, None)]),
    ], 1):
        rid = db.execute(
            "INSERT INTO rubros_presupuesto(empresa_id,presupuesto_id,nombre,orden) VALUES (%s,%s,%s,%s) RETURNING id",
            (empresa, presupuesto["id"], rubro, orden),
        ).fetchone()["id"]
        for n, (descripcion, cantidad, apu_id, precio) in enumerate(filas, 1):
            db.execute(
                """INSERT INTO items_presupuesto(empresa_id,presupuesto_id,rubro_id,descripcion,unidad,cantidad,
                                                  apu_id,precio_unitario_centavos,orden)
                   VALUES (%s,%s,%s,%s,'m2',%s,%s,%s,%s)""",
                (empresa, presupuesto["id"], rid, descripcion, Decimal(cantidad), apu_id, precio, n),
            )
    db.commit()
    return presupuesto


def test_presupuesto_cierra_al_centavo(db, presupuesto_muestra):
    p = presupuesto_muestra
    resultado = presupuestos.calcular(db, p["empresa_id"], p["id"])
    # APU: 121 + 373 + 10 = 504. Ítems: 504 × 3,3333 → 1680; 2501 × 1,125 → 2814;
    # 99 × 0,75 → 74; 12345 × 0,2 = 2469; 504 × 1,0001 → 504.
    # Rubros: 1680 + 2814 + 74 = 4568, y 2469 + 504 = 2973. CD = 7541.
    # GG: 7541 × 15% → 1131; B: (7541 + 1131) × 10% → 867;
    # I: (7541 + 1131 + 867) × 21% → 2003. Total: 7541 + 1131 + 867 + 2003 = 11542.
    assert [r["subtotal_centavos"] for r in resultado["rubros"]] == [4568, 2973]
    assert [[i["subtotal_centavos"] for i in r["items"]] for r in resultado["rubros"]] == [
        [1680, 2814, 74], [2469, 504],
    ]
    assert resultado["costo_directo_centavos"] == 7541
    assert resultado["gastos_generales_centavos"] == 1131
    assert resultado["beneficio_centavos"] == 867
    assert resultado["impuestos_centavos"] == 2003
    assert resultado["total_centavos"] == 11542


def test_emitido_congela_importes_y_crea_version(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    ruta = f"/presupuestos/{p['id']}"
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    csrf = csrf_de(admin)
    assert cliente.post(f"{ruta}/emitir", data={"csrf": csrf}).status_code == 303
    antes = presupuestos.calcular(db, p["empresa_id"], p["id"])
    rubro = antes["rubros"][0]
    item = rubro["items"][0]
    datos = {"csrf": csrf, "rubro_id": rubro["id"], "descripcion": "Otro", "unidad": "m2",
             "cantidad": "1.25", "precio": "20,20"}
    assert cliente.post(f"{ruta}/items", data=datos).status_code == 409
    assert cliente.post(f"{ruta}/items/{item['id']}", data=datos).status_code == 409
    cemento = db.execute(
        "SELECT id FROM materiales WHERE empresa_id=%s AND codigo='Cemento'", (p["empresa_id"],),
    ).fetchone()["id"]
    precios.cargar(db, admin, cemento, 99999, datetime(2026, 1, 15, tzinfo=TZ))
    db.commit()
    assert presupuestos.calcular(db, p["empresa_id"], p["id"])["total_centavos"] == 11542
    duplicado = cliente.post(f"{ruta}/nueva-version", data={"csrf": csrf})
    assert duplicado.status_code == 303
    nuevo_id = int(duplicado.headers["location"].rsplit("/", 1)[1])
    copia = presupuestos.calcular(db, p["empresa_id"], nuevo_id)
    assert copia["presupuesto"]["version"] == 2 and copia["presupuesto"]["estado"] == "borrador"
    assert [[i["descripcion"] for i in r["items"]] for r in copia["rubros"]] == [
        ["Excavación", "Viga", "Replanteo"], ["Columna", "Hormigón"],
    ]


def test_presupuesto_a_fecha_no_cambia_con_precio_nuevo(db, mundo, presupuesto_muestra):
    p = presupuesto_muestra
    cemento = db.execute(
        "SELECT id FROM materiales WHERE empresa_id=%s AND codigo='Cemento'", (p["empresa_id"],),
    ).fetchone()["id"]
    precios.cargar(db, mundo["admin_a"], cemento, 99999, datetime(2026, 3, 1, tzinfo=TZ))
    assert presupuestos.calcular(db, p["empresa_id"], p["id"])["total_centavos"] == 11542


def test_rutas_de_presupuesto_respetan_proyecto_y_rol(db, mundo, como, presupuesto_muestra):
    ruta = f"/presupuestos/{presupuesto_muestra['id']}"
    coleccion = f"/proyecto/{mundo['p1']['codigo']}/presupuestos"
    ana, cliente, otro = mundo["ana"], mundo["cliente"], mundo["admin_b"]
    lector = como(ana["email"])
    assert "$ 115,42" in lector.get(ruta).text
    assert lector.get(coleccion).status_code == 200
    assert lector.post(f"{ruta}/rubros", data={"csrf": csrf_de(ana), "nombre": "Otro"}).status_code == 403
    assert como(cliente["email"]).get(ruta).status_code == 404
    assert como(otro["email"]).get(ruta).status_code == 404
    assert como(mundo["beto"]["email"]).get(ruta).status_code == 404


def test_postgres_bloquea_cambios_directos_en_emitidos(db, mundo, presupuesto_muestra):
    p = presupuesto_muestra
    ids = (p["empresa_id"], p["id"])
    inicial = presupuestos.calcular(db, *ids)
    presupuestos.emitir(db, mundo["admin_a"], p, inicial)
    db.commit()
    item = inicial["rubros"][0]["items"][0]["id"]
    for sql, parametros in [
        ("UPDATE items_presupuesto SET cantidad=2 WHERE empresa_id=%s AND presupuesto_id=%s AND id=%s", (*ids, item)),
        ("INSERT INTO rubros_presupuesto (empresa_id,presupuesto_id,nombre,orden) VALUES (%s,%s,'Nuevo',10)", ids),
        ("DELETE FROM rubros_presupuesto WHERE empresa_id=%s AND presupuesto_id=%s", ids),
        ("UPDATE presupuestos SET nombre='Modificado' WHERE empresa_id=%s AND id=%s", ids),
        ("DELETE FROM presupuestos WHERE empresa_id=%s AND id=%s", ids),
        ("TRUNCATE items_presupuesto CASCADE", ()),
    ]:
        with pytest.raises(DatabaseError, match="emitido es inmutable"), db.transaction():
            db.execute(sql, parametros)
    assert db.execute("UPDATE presupuestos SET nombre=nombre WHERE empresa_id=%s AND id=%s", ids).rowcount == 1
    assert presupuestos.calcular(db, *ids)["total_centavos"] == 11542


def test_postgres_bloquea_mover_rubro_a_emitido(db, mundo, presupuesto_muestra):
    p = presupuesto_muestra
    empresa = p["empresa_id"]
    actor = mundo["admin_a"]
    presupuestos.emitir(db, actor, p, presupuestos.calcular(db, empresa, p["id"]))
    copia = presupuestos.nueva_version(db, actor, p)
    rubro = presupuestos.agregar_rubro(db, actor, p | {"id": copia}, "Rubro sin ítems")
    db.commit()
    with pytest.raises(DatabaseError, match="emitido es inmutable"), db.transaction():
        db.execute(
            "UPDATE rubros_presupuesto SET presupuesto_id=%s WHERE empresa_id=%s AND id=%s",
            (p["id"], empresa, rubro),
        )
