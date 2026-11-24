from datetime import date

import psycopg
import pytest

from app import config
from app.services import cronograma, materiales_obra, notas_obra, partes
from tests.conftest import csrf_de

HOY = date(2026, 2, 6)


def tarea_material(db, proyecto, codigo, inicio, dias, *, critica=False, nombre=None):
    tarea = cronograma.crear_tarea(db, proyecto, {
        "codigo": codigo, "nombre": f"Tarea {codigo}", "rubro": "Obra", "inicio": inicio, "fin": inicio,
        "critica": critica, "item_presupuesto_id": None,
    })
    cronograma.agregar_material(db, proyecto, tarea, {
        "nombre": nombre or codigo, "cantidad": 10, "unidad": "kg", "plazo_dias": dias,
    })
    material = db.execute("SELECT id FROM materiales_tarea WHERE tarea_id=%s", (tarea,)).fetchone()["id"]
    return tarea, material


def test_alertas_con_feriado_calculadas_a_mano_y_suprimidas_por_stock_o_pedido(db, mundo, monkeypatch):
    monkeypatch.setattr(config, "MARGEN_PEDIDO_DIAS", 2)
    p, actor = mundo["p1"], mundo["admin_a"]
    db.execute("INSERT INTO feriados(empresa_id,fecha,nombre) VALUES (%s,'2026-02-05','Feriado de la empresa')",
               (p["empresa_id"],))
    _, critico = tarea_material(db, p, "Crítico", date(2026, 2, 10), 2, critica=True)
    tarea_material(db, p, "Rojo", date(2026, 2, 10), 1)
    tarea_material(db, p, "Amarillo", date(2026, 2, 12), 1)
    tarea_material(db, p, "Verde", date(2026, 2, 20), 1)
    alertas = materiales_obra.alertas(db, p, HOY)
    # Desde el 10/02, al retroceder: 09/02, 06/02, 04/02, 03/02. El jueves 05 es feriado.
    assert [(a["nivel"], a["fecha_limite"]) for a in alertas] == [
        ("critico", date(2026, 2, 3)), ("rojo", date(2026, 2, 4)),
        ("amarillo", date(2026, 2, 9)), ("verde", date(2026, 2, 17)),
    ]
    materiales_obra.guardar_pedido(db, actor, p, critico, "recibido", HOY, HOY)
    parte, _ = partes.crear_borrador(db, actor, p, HOY)
    pid = parte["id"]
    for seccion, campos in (
        ("condiciones", {"confirmado": "1"}), ("jornada", {"tipo": "no_laborable"}), ("hys", {"epp_ok": "1"}),
        ("ingresos", {"material": "rojo", "cantidad": "6", "unidad": "kg"}),
        ("ingresos", {"material": "Rojo", "cantidad": "4", "unidad": "KG"}),
    ):
        partes.actualizar_seccion(db, actor, p, pid, seccion, campos)
    partes.confirmar(db, actor, p, pid)
    assert [a["nivel"] for a in materiales_obra.alertas(db, p, HOY)] == ["amarillo", "verde"]
    assert materiales_obra.stock(db, p, HOY)[0]["cantidad"] == 10
    anterior, _ = partes.crear_borrador(db, actor, p, date(2026, 2, 4))
    for seccion, campos in (
        ("condiciones", {"confirmado": "1"}), ("jornada", {"tipo": "no_laborable"}), ("hys", {"epp_ok": "1"}),
        ("ingresos", {"material": "Rojo", "cantidad": "1", "unidad": "kg"}),
    ):
        partes.actualizar_seccion(db, actor, p, anterior["id"], seccion, campos)
    partes.confirmar(db, actor, p, anterior["id"])
    assert materiales_obra.stock(db, p, HOY)[0]["cantidad"] == 11
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute("UPDATE stock_obra SET cantidad=0 WHERE proyecto_id=%s", (p["id"],))


def test_notas_y_pedidos_pendientes(db, mundo, monkeypatch, como):
    p, actor = mundo["p1"], mundo["admin_a"]
    realizador = como(actor["email"])
    base = f"/proyecto/{p['codigo']}/obra/seguimiento"
    csrf = {"csrf": csrf_de(actor)}
    tarea, ladrillo = tarea_material(db, p, "T-040", date(2026, 2, 20), 2, nombre="ladrillo hueco")
    _, pendiente = tarea_material(db, p, "T-070", date(2026, 2, 23), 1)
    db.commit()
    for tipo, titulo in (("nota_pedido", "Revisar medidas"), ("orden_servicio", "Corregir desagüe")):
        r = realizador.post(f"{base}/notas", data=csrf | {
            "tipo": tipo, "asunto": titulo, "emisor": "DT", "destinatario": "Contratista",
            "texto": "Revisar antes de continuar.", "fecha": "2026-02-02", "plazo": "2026-02-05",
        })
        assert r.status_code == 303, r.text
    notas = notas_obra.abiertas(db, p, HOY)
    assert {n["tipo"] for n in notas} == {"nota_pedido", "orden_servicio"}
    assert all(n["numero"] == 1 and n["vencida"] for n in notas)
    for material, estado in ((ladrillo, "pedido"), (pendiente, "pendiente")):
        r = realizador.post(f"{base}/pedidos/{material}", data=csrf | {
            "estado": estado, "fecha": "2026-02-03", "fecha_entrega": "2026-02-05",
        })
        assert r.status_code == 303, r.text
    grupos = materiales_obra.pedidos(db, p, HOY)
    assert grupos["pedido"][0]["tarea_id"] == tarea and grupos["pedido"][0]["entrega_vencida"]
    assert grupos["pendiente"][0]["codigo"] == "T-070"
    assert "Corregir desagüe" in realizador.get(base).text
    otra = como(mundo["admin_b"]["email"])
    csrf_otra = {"csrf": csrf_de(mundo["admin_b"])}
    ruta_otra = f"/proyecto/{mundo['pb']['codigo']}/obra/seguimiento"
    assert "Corregir desagüe" not in otra.get(ruta_otra).text
    assert otra.post(f"{ruta_otra}/pedidos/{ladrillo}", data=csrf_otra | {"estado": "recibido"}).status_code == 404
    ana = mundo["ana"]
    assert como(ana["email"]).post(f"{base}/pedidos/{ladrillo}",
                                  data={"csrf": csrf_de(ana), "estado": "recibido"}).status_code == 403
    assert como(mundo["cliente"]["email"]).get(base).status_code == 404
