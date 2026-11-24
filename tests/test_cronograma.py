from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook
from psycopg import DatabaseError

from app.services import cronograma, presupuestos
from tests import test_presupuestos
from tests.conftest import csrf_de

presupuesto_muestra = test_presupuestos.presupuesto_muestra


def test_calendario_con_fin_de_semana_y_feriado(db, mundo):
    empresa = mundo["ea"]["id"]
    db.execute("INSERT INTO feriados(empresa_id,fecha,nombre) VALUES (%s,'2026-07-10','Feriado propio')", (empresa,))
    cal = cronograma.calendario(db, empresa)
    otro = cronograma.calendario(db, mundo["eb"]["id"])
    assert not cal.es_habil(date(2026, 7, 9))
    assert not cal.es_habil(date(2026, 7, 10)) and otro.es_habil(date(2026, 7, 10))
    assert cal.proximo_habil(date(2026, 7, 8)) == date(2026, 7, 13)
    assert cal.restar_habiles(date(2026, 7, 13), 1) == date(2026, 7, 8)


def _tarea(db, proyecto, codigo, fin, item=None):
    return cronograma.crear_tarea(db, proyecto, {
        "codigo": codigo, "nombre": codigo, "rubro": "Obra", "inicio": date(2026, 2, 2),
        "fin": fin, "critica": codigo == "Larga", "item_presupuesto_id": item,
    })


def test_avance_ponderado_e_importes_exactos(db, mundo, presupuesto_muestra):
    p, proy = presupuesto_muestra, mundo["p1"]
    empresa = p["empresa_id"]
    calculo = presupuestos.calcular(db, empresa, p["id"])
    presupuestos.emitir(db, mundo["admin_a"], p, calculo)
    a, b = [f["id"] for f in calculo["rubros"][0]["items"][:2]]
    larga = _tarea(db, proy, "Larga", date(2026, 2, 6), a)
    corta = _tarea(db, proy, "Corta", date(2026, 2, 3), b)
    hoy = date(2026, 2, 3)
    actor = mundo["admin_a"]
    cronograma.registrar_avance(db, actor, proy, larga, hoy, 4000)
    cronograma.registrar_avance(db, actor, proy, corta, hoy, 5000)
    cronograma.registrar_avance(db, actor, proy, larga, date(2026, 2, 4), 9000)
    resultado = cronograma.avance_obra(db, proy, hoy)
    # (5 × 40 + 2 × 50) / 7 = 42,86 %. Transcurrieron 2 + 2 hábiles de 7: 57,14 %.
    assert (resultado["real_pb"], resultado["previsto_pb"]) == (4286, 5714)
    # 1680 × 40 % = 672. 2814 × 50 % = 1407. Total = 2079; 2079/4494 = 46,26 %.
    assert resultado["economico_centavos"] == 2079 and resultado["economico_pb"] == 4626
    assert sum(t["economico_centavos"] for t in resultado["tareas"]) == 2079
    assert cronograma.avance_obra(db, proy, date(2026, 2, 4))["tareas"]
    assert next(t["real_pb"] for t in cronograma.avance_obra(db, proy, date(2026, 2, 4))["tareas"]
                if t["id"] == larga) == 9000
    for sql in ("UPDATE avances_tarea SET avance_pb=20", "DELETE FROM avances_tarea"):
        with pytest.raises(DatabaseError, match="inmutable"), db.transaction():
            db.execute(sql)


def test_cronograma_roles_y_empresa(db, mundo, como):
    p = mundo["p1"]
    tarea = _tarea(db, p, "Excavación", date(2026, 2, 5))
    db.commit()
    ruta = f"/proyecto/{p['codigo']}/obra"
    ana = mundo["ana"]
    cliente = como(ana["email"])
    assert "Excavación" in cliente.get(ruta).text
    datos = {"csrf": csrf_de(ana), "fecha": "2026-02-03", "avance_pb": 4000}
    assert cliente.post(f"{ruta}/tareas/{tarea}/avance", data=datos).status_code == 403
    assert como(mundo["cliente"]["email"]).get(ruta).status_code == 404
    admin_b = mundo["admin_b"]
    ruta_b = f"/proyecto/{mundo['pb']['codigo']}/obra"
    datos["csrf"] = csrf_de(admin_b)
    assert como(admin_b["email"]).post(f"{ruta_b}/tareas/{tarea}/avance", data=datos).status_code == 404


def test_importar_cronograma_vista_previa_y_confirmacion(db, mundo, como):
    p, actor = mundo["p1"], mundo["admin_a"]
    ruta = f"/proyecto/{p['codigo']}/obra"
    cliente, csrf = como(actor["email"]), csrf_de(actor)
    wb = Workbook()
    wb.active.append(cronograma.COLUMNAS)
    wb.active.append(("T1", "Ejecución", "Excavar", "2026-02-02", "2026-02-03", "sí", None,
                      "Hormigón", "2,25", "m3", 5))
    archivo = BytesIO()
    wb.save(archivo)
    r = cliente.post(ruta + "/excel/vista-previa", data={"csrf": csrf},
                     files={"archivo": ("cronograma.xlsx", archivo.getvalue())})
    assert r.status_code == 200 and "Excavar" in r.text
    assert not db.execute("SELECT 1 FROM tareas_obra WHERE proyecto_id=%s", (p["id"],)).fetchone()
    token = r.text.split('name="confirmacion" value="', 1)[1].split('"', 1)[0]
    assert cliente.post(ruta + "/excel/confirmar", data={"csrf": csrf, "confirmacion": token}).status_code == 303
    assert db.execute("SELECT nombre,unidad FROM materiales_tarea WHERE proyecto_id=%s", (p["id"],)).fetchone() == {
        "nombre": "Hormigón", "unidad": "m3",
    }
