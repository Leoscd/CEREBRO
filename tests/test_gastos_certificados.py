import pytest
from psycopg import DatabaseError

from app.services import certificados, presupuestos
from tests import test_presupuestos
from tests.conftest import csrf_de

presupuesto_muestra = test_presupuestos.presupuesto_muestra


def _id_respuesta(r):
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_certifica_incremento_sobre_el_subtotal_emitido(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    pid, empresa = p["id"], p["empresa_id"]
    admin = mundo["admin_a"]
    csrf = csrf_de(admin)
    cliente = como(admin["email"])
    base = f"/presupuestos/{pid}/certificados"
    item = presupuestos.calcular(db, empresa, pid)["rubros"][0]["items"][0]["id"]
    assert cliente.post(base, data={"csrf": csrf, "periodo": "2026-02", f"avance_{item}": "3000"}).status_code == 409
    assert cliente.post(f"/presupuestos/{pid}/emitir", data={"csrf": csrf}).status_code == 303
    assert "Certificados de avance" in cliente.get(f"/presupuestos/{pid}").text
    primero = _id_respuesta(cliente.post(base, data={"csrf": csrf, "periodo": "2026-02", f"avance_{item}": "3000"}))
    assert cliente.post(f"{base}/{primero}/emitir", data={"csrf": csrf}).status_code == 303
    segundo = _id_respuesta(cliente.post(base, data={"csrf": csrf, "periodo": "2026-03", f"avance_{item}": "7500"}))
    assert cliente.post(f"{base}/{segundo}/emitir", data={"csrf": csrf}).status_code == 303
    # Subtotal emitido de excavación: 1680 centavos. Primer período: 1680 × 30 % = 504.
    # Segundo período: 1680 × (75 % − 30 %) = 756 centavos.
    filas = certificados.listar(db, empresa, pid)
    assert [(c["numero"], c["total_centavos"]) for c in filas] == [(1, 504), (2, 756)]
    assert "$ 7,56" in cliente.get(f"{base}/{segundo}").text
    for avance in ("7400", "10001"):
        r = cliente.post(base, data={"csrf": csrf, "periodo": "2026-04", f"avance_{item}": avance})
        assert r.status_code == 400
    assert len(certificados.listar(db, empresa, pid)) == 2
    for sql in (
        "UPDATE certificado_items SET avance_pb=8000 WHERE certificado_id=%s",
        "UPDATE certificados SET periodo='2026-04-01' WHERE id=%s",
    ):
        with pytest.raises(DatabaseError, match="certificado emitido es inmutable"), db.transaction():
            db.execute(sql, (segundo,))
    assert como(mundo["cliente"]["email"]).get(base).status_code == 404
    assert como(mundo["admin_b"]["email"]).get(f"{base}/{segundo}").status_code == 404


def _archivo(db, proyecto, nombre):
    return db.execute(
        """INSERT INTO archivos (empresa_id,proyecto_id,carpeta_id,nombre,mime)
           SELECT empresa_id,proyecto_id,id,%s,'application/pdf' FROM carpetas
            WHERE empresa_id=%s AND proyecto_id=%s ORDER BY id LIMIT 1 RETURNING id""",
        (nombre, proyecto["empresa_id"], proyecto["id"]),
    ).fetchone()["id"]


def test_gasto_comprobante_del_mismo_proyecto_y_aislamiento(db, mundo, como):
    p, otro, pb = mundo["p1"], mundo["p2"], mundo["pb"]
    archivo = _archivo(db, p, "Boleta A")
    ajeno = _archivo(db, otro, "Boleta otro proyecto")
    ajeno_b = _archivo(db, pb, "Boleta otra empresa")
    db.commit()
    a, b = mundo["admin_a"], mundo["admin_b"]
    cliente = como(a["email"])
    ruta = f"/proyecto/{p['codigo']}/gastos"
    datos = {"csrf": csrf_de(a), "fecha": "2026-03-04", "descripcion": "Traslado especial A", "importe": "123,45"}
    assert cliente.post(ruta, data=datos | {"archivo_id": ajeno}).status_code == 404
    assert cliente.post(ruta, data=datos | {"archivo_id": ajeno_b}).status_code == 404
    assert cliente.post(ruta, data=datos | {"archivo_id": archivo}).status_code == 303
    assert "Boleta A" in cliente.get(ruta).text and "$ 123,45" in cliente.get(ruta).text
    assert "Boleta otro proyecto" not in cliente.get(ruta).text
    pagina_b = como(b["email"]).get(f"/proyecto/{pb['codigo']}/gastos")
    assert pagina_b.status_code == 200 and "Traslado especial A" not in pagina_b.text
    assert como(mundo["cliente"]["email"]).get(ruta).status_code == 404
    assert db.execute("SELECT importe_centavos,archivo_id FROM gastos").fetchall() == [
        {"importe_centavos": 12345, "archivo_id": archivo},
    ]
    assert db.execute("SELECT 1 FROM auditoria WHERE accion='gasto.registrado' AND proyecto_id=%s",
                      (p["id"],)).fetchone()
