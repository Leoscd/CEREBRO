from datetime import date

import pytest
from psycopg import DatabaseError

from app.services import precios
from tests.conftest import csrf_de


def test_carga_precio_historial_y_vigencia(db, mundo, como):
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    csrf = csrf_de(admin)
    alta = cliente.post("/precios/materiales", data={
        "csrf": csrf, "codigo": "CEM", "nombre": "Cemento", "unidad": "bolsa", "tipo": "material",
    })
    assert alta.status_code == 303
    historial = alta.headers["location"]
    material = int(historial.rsplit("/", 1)[1])
    for importe, dia in [("$ 100,00", "2026-01-01"), ("$ 115,00", "2026-03-01")]:
        r = cliente.post(f"{historial}/precios", data={"csrf": csrf, "precio": importe, "vigente_desde": dia})
        assert r.status_code == 303
    assert precios.vigente(db, admin["empresa_id"], material, date(2026, 2, 1))["precio_centavos"] == 10000
    assert precios.vigente(db, admin["empresa_id"], material, date(2026, 3, 1))["precio_centavos"] == 11500
    fila = db.execute(
        "SELECT anterior_centavos, actual_centavos, variacion_pb FROM v_cambios_precio "
        "WHERE empresa_id=%s AND material_id=%s ORDER BY vigente_desde DESC LIMIT 1",
        (admin["empresa_id"], material),
    ).fetchone()
    assert dict(fila) == {"anterior_centavos": 10000, "actual_centavos": 11500, "variacion_pb": 1500}
    assert "$ 115,00" in cliente.get(historial).text
    assert db.execute(
        "SELECT count(*) AS n FROM auditoria WHERE empresa_id=%s AND accion='precio.cargado'",
        (admin["empresa_id"],),
    ).fetchone()["n"] == 2


def test_precios_son_inmutables(db, mundo):
    admin = mundo["admin_a"]
    material = db.execute(
        "INSERT INTO materiales(empresa_id,codigo,nombre,unidad,tipo) VALUES (%s,'M','Material','kg','material') RETURNING id",
        (admin["empresa_id"],),
    ).fetchone()
    db.execute(
        "INSERT INTO precios(empresa_id,material_id,precio_centavos,vigente_desde,fuente,cargado_por) "
        "VALUES (%s,%s,100,now(),'manual',%s)", (admin["empresa_id"], material["id"], admin["id"]),
    )
    db.commit()
    for sql in ("UPDATE precios SET precio_centavos=101", "DELETE FROM precios", "TRUNCATE precios"):
        with pytest.raises(DatabaseError, match="inmutable"), db.transaction():
            db.execute(sql)


def test_catalogo_aislado_y_csrf(db, mundo, como):
    a, b = mundo["admin_a"], mundo["admin_b"]
    for tabla, columnas, valores in [
        ("materiales", "codigo,nombre,unidad,tipo", "'B','Material secreto','kg','material'"),
        ("proveedores", "nombre", "'Proveedor secreto'"),
        ("indices_costo", "nombre,periodo,valor", "'Índice secreto','2026-01-01',200"),
    ]:
        db.execute(f"INSERT INTO {tabla}(empresa_id,{columnas}) VALUES (%s,{valores})", (b["empresa_id"],))
    material = db.execute("SELECT id FROM materiales WHERE empresa_id=%s", (b["empresa_id"],)).fetchone()["id"]
    proveedor = db.execute("SELECT id FROM proveedores WHERE empresa_id=%s", (b["empresa_id"],)).fetchone()["id"]
    db.execute(
        "INSERT INTO precios(empresa_id,material_id,precio_centavos,vigente_desde,fuente,cargado_por) "
        "VALUES (%s,%s,998877,now(),'manual',%s)", (b["empresa_id"], material, b["id"]),
    )
    propio = db.execute(
        "INSERT INTO materiales(empresa_id,codigo,nombre,unidad,tipo) VALUES (%s,'A','Material A','kg','material') RETURNING id",
        (a["empresa_id"],),
    ).fetchone()["id"]
    db.commit()
    cliente = como(a["email"])
    pagina = cliente.get("/precios")
    assert pagina.status_code == 200
    assert "Material A" in pagina.text
    assert "secreto" not in pagina.text and "9.988,77" not in pagina.text
    assert "Proveedor secreto" not in cliente.get("/precios/proveedores").text
    assert cliente.get(f"/precios/materiales/{material}").status_code == 404
    datos = {"precio": "10,00", "vigente_desde": "2026-01-01"}
    assert cliente.post(f"/precios/materiales/{propio}/precios", data=datos).status_code == 403
    datos["csrf"] = csrf_de(a)
    assert cliente.post(f"/precios/materiales/{material}/precios", data=datos).status_code == 404
    assert cliente.post(f"/precios/materiales/{propio}/precios", data=datos | {"proveedor_id": proveedor}).status_code == 404
    assert precios.vigente(db, a["empresa_id"], material, date(2026, 12, 1)) is None


def test_gestion_administrativa_y_cliente(db, mundo, como):
    miembro = mundo["ana"]
    cliente = como(miembro["email"])
    datos = {"csrf": csrf_de(miembro), "codigo": "M", "nombre": "Material", "unidad": "kg", "tipo": "material"}
    assert cliente.post("/precios/materiales", data=datos).status_code == 403
    assert cliente.post("/precios/materiales/1/precios", data={
        "csrf": csrf_de(miembro), "precio": "12", "vigente_desde": "2026-01-01",
    }).status_code == 403
    db.execute(
        "INSERT INTO usuario_areas (usuario_id,area_id) SELECT %s,id FROM areas "
        "WHERE empresa_id=%s AND codigo='gestion_administrativa'", (miembro["id"], miembro["empresa_id"]),
    )
    db.commit()
    assert cliente.post("/precios/materiales", data=datos).status_code == 303
    assert como(mundo["cliente"]["email"]).get("/precios").status_code == 404
