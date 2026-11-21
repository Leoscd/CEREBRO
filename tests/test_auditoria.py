"""La auditoría registra y no se puede alterar; los códigos de proyecto son correlativos."""
import psycopg
import pytest

from tests.conftest import csrf_de


def test_auditoria_no_se_modifica_ni_se_borra(mundo, como, db):
    como("ana@a.test")  # el ingreso queda registrado
    fila = db.execute("SELECT id FROM auditoria WHERE accion = 'ingreso' LIMIT 1").fetchone()
    assert fila
    for sql in ("UPDATE auditoria SET accion = 'x' WHERE id = %s", "DELETE FROM auditoria WHERE id = %s"):
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute(sql, (fila["id"],))
        db.rollback()
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("TRUNCATE auditoria")
    db.rollback()


def test_cambios_de_proyecto_quedan_registrados(mundo, como, db):
    beto = como("beto@a.test")
    beto.post(f"/proyecto/{mundo['p2']['codigo']}/editar",
              data={"csrf": csrf_de(mundo["beto"]), "nombre": "Local nuevo", "etapa": "ejecucion",
                    "estado": "activo", "avance": 40})
    fila = db.execute(
        "SELECT * FROM auditoria WHERE accion = 'proyecto_editado' AND proyecto_id = %s", (mundo["p2"]["id"],)
    ).fetchone()
    assert fila["usuario_id"] == mundo["beto"]["id"]
    assert fila["detalle"]["nombre"] == "Local nuevo" and fila["detalle"]["avance"] == "40"


def test_codigos_correlativos_por_empresa(mundo, como, db):
    import datetime

    anio = datetime.date.today().year
    assert mundo["p1"]["codigo"] == f"PR-{anio}-001"
    assert mundo["p2"]["codigo"] == f"PR-{anio}-002"
    assert mundo["pb"]["codigo"] == f"PR-{anio}-001"  # la otra empresa arranca su propia serie
    admin = como("admin@a.test")
    tipo = db.execute("SELECT id FROM tipos_proyecto WHERE empresa_id=%s AND slug='autocad'",
                      (mundo["ea"]["id"],)).fetchone()
    r = admin.post("/admin/proyectos/nuevo", data={"csrf": csrf_de(mundo["admin_a"]),
                                                    "tipo_proyecto_id": tipo["id"], "nombre": "Tercero"})
    assert r.headers["location"] == f"/proyecto/PR-{anio}-003"
    # Quien crea queda como director.
    assert "Director/a" in admin.get(f"/proyecto/PR-{anio}-003").text
