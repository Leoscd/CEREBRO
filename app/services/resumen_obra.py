"""Resumen del avance y los pendientes para el tablero de obra."""

from app.services import bitacora, cronograma, materiales_obra, notas_obra


def resumen_obra(db, usuario, proyecto, hoy):
    visible = bitacora.proyecto_de_obra(db, usuario, proyecto)
    avance = cronograma.avance_obra(db, visible, hoy)
    notas = notas_obra.abiertas(db, visible, hoy)
    ultimo = bitacora.ultimos_partes(db, usuario, visible, hoy, cantidad=1)
    return {
        "obra": visible["nombre"], "fecha": hoy,
        "real_pb": avance["real_pb"], "previsto_pb": avance["previsto_pb"],
        "economico_centavos": avance["economico_centavos"], "economico_pb": avance["economico_pb"],
        "tareas_atrasadas": [t for t in avance["tareas"] if t["atraso_pb"] > 0],
        "alertas_materiales": materiales_obra.alertas(db, visible, hoy),
        "notas_abiertas": notas, "notas_vencidas": [n for n in notas if n["vencida"]],
        "ultimo_parte": ultimo[0] if ultimo else None,
    }
