from datetime import date

from app.services import bitacora, cronograma, materiales_obra, notas_obra, partes, resumen_obra
from tests.test_materiales_obra import tarea_material

HOY = date(2026, 2, 10)


def _parte(db, p, actor, dia, texto):
    parte, _ = partes.crear_borrador(db, actor, p, dia)
    for seccion, datos in (
        ("condiciones", {"confirmado": "1"}), ("hys", {"epp_ok": "1"}),
        ("jornada", {"tipo": "no_laborable", "detalle": "Falta de material"}),
        ("resumen", {"texto": texto}),
    ):
        partes.actualizar_seccion(db, actor, p, parte["id"], seccion, datos)
    return partes.confirmar(db, actor, p, parte["id"])


def _nota(db, p, u, asunto, plazo):
    return notas_obra.crear(db, u, p, {
        "tipo": "nota_pedido", "fecha": date(2026, 2, 2), "plazo": plazo, "asunto": asunto,
        "texto": "Registrar en la bitácora", "emisor": "DT", "destinatario": "Contratista", "reporte_id": None,
    })


def test_resumen_obra_marca_atraso_critico_y_notas(db, mundo):
    p, u = mundo["p1"], mundo["admin_a"]
    fecha = date(2026, 2, 9)
    critica, _ = tarea_material(db, p, "T-040", fecha, 2, critica=True)
    normal, _ = tarea_material(db, p, "T-050", fecha, 2)
    cronograma.registrar_avance(db, u, p, critica, fecha, 4000)
    cronograma.registrar_avance(db, u, p, normal, fecha, 0)
    ultimo = _parte(db, p, u, HOY, "Revisión de carpinterías")
    _nota(db, p, u, "Nota vencida", fecha)
    _nota(db, p, u, "Todavía en plazo", date(2026, 2, 11))
    resumen = resumen_obra.resumen_obra(db, u, p, HOY)
    assert resumen["real_pb"] == 2000 < resumen["previsto_pb"] == 10000
    atrasada = resumen["tareas_atrasadas"][0]
    assert atrasada["id"] == critica and atrasada["critica"] and atrasada["real_pb"] == 4000
    assert resumen["ultimo_parte"]["id"] == ultimo["id"] and resumen["ultimo_parte"]["dt_nombre"] == "Admin A"
    assert len(resumen["notas_abiertas"]) == 2 and len(resumen["notas_vencidas"]) == 1


def test_ultimos_partes_del_mas_nuevo_al_mas_viejo_y_busqueda_sin_acentos(db, mundo):
    p, u = mundo["p1"], mundo["admin_a"]
    anterior = _parte(db, p, u, date(2026, 2, 8), "Se consultó al Corralón por caños.")
    nuevo = _parte(db, p, u, date(2026, 2, 9), "Por la ventana llegó ladrillo del Corralón.")
    borrador, _ = partes.crear_borrador(db, u, p, HOY)
    partes.actualizar_seccion(db, u, p, borrador["id"], "resumen", {"texto": "corralón ladrillo sin confirmar"})
    recientes = bitacora.ultimos_partes(db, u, p, HOY, cantidad=2)
    assert [r["id"] for r in recientes] == [nuevo["id"], anterior["id"]]
    assert "ventana" in recientes[0]["datos"]["resumen"]
    assert recientes[1]["datos"]["jornada"]["detalle"] == "Falta de material"
    hallazgos = bitacora.buscar_en_partes(db, u, p, "CORRALON ladrillo")
    assert [h["id"] for h in hallazgos] == [nuevo["id"]] and "Corralón" in hallazgos[0]["texto"]
    assert bitacora.buscar_en_partes(db, u, p, "xilofón") == []


def test_bitacora_filtra_tipos_fechas_y_aisla_obras(db, mundo, como):
    p, u = mundo["p1"], mundo["admin_a"]
    otra, externo = mundo["pb"], mundo["admin_b"]
    propia = _parte(db, p, u, HOY, "Propia")
    _parte(db, mundo["p2"], u, HOY, "Otra del estudio")
    _parte(db, otra, externo, HOY, "Otra empresa")
    _nota(db, otra, externo, "Nota de otra empresa", HOY)
    _nota(db, p, u, "Nota de esta obra", HOY)
    tareas, material = tarea_material(db, p, "OB1", date(2026, 2, 12), 2)
    materiales_obra.guardar_pedido(db, u, p, material, "pedido", HOY, None)
    cronograma.registrar_avance(db, u, p, tareas, HOY, 3000)
    db.execute("INSERT INTO hitos(empresa_id,proyecto_id,titulo,fecha) VALUES (%s,%s,'Hito propio',%s)",
               (p["empresa_id"], p["id"], HOY))
    todos = bitacora.bitacora(db, u, p)
    assert len(todos) == 5 and {e["tipo"] for e in todos} == {"parte", "nota", "hito", "avance", "pedido"}
    assert all("otra" not in e["titulo"].lower() for e in todos)
    filtrados = bitacora.bitacora(db, u, p, desde=HOY, hasta=HOY, tipos=["parte", "nota"])
    assert [(e["tipo"], e["id"]) for e in filtrados] == [("parte", propia["id"])]
    db.commit()
    ruta = f"/proyecto/{p['codigo']}/obra/bitacora"
    respuesta = como(u["email"]).get(ruta)
    assert respuesta.status_code == 200 and "Hito propio" in respuesta.text and "Nota de otra empresa" not in respuesta.text
    ruta_otra = f"/proyecto/{otra['codigo']}/obra/bitacora"
    assert "Hito propio" not in como(externo["email"]).get(ruta_otra).text
    assert como(mundo["cliente"]["email"]).get(ruta).status_code == 404
