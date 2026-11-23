"""Chequeos deterministas sobre el mismo cálculo que usa el presupuesto."""

from datetime import date
from typing import Literal, NotRequired, TypedDict

from psycopg import Connection

from app.services import presupuestos


class Hallazgo(TypedDict):
    codigo: str
    severidad: Literal["error", "aviso"]
    mensaje: str
    item_id: NotRequired[int]


def analizar(db: Connection, empresa_id: int, presupuesto_id: int) -> list[Hallazgo]:
    calculo = presupuestos.calcular(db, empresa_id, presupuesto_id)
    if calculo is None:
        raise ValueError("Presupuesto no encontrado")
    return analizar_calculo(calculo)


def analizar_calculo(calculo: dict) -> list[Hallazgo]:
    p = calculo["presupuesto"]
    fecha_base = p["fecha_precios"]
    directo = calculo["costo_directo_centavos"]
    hallazgos: list[Hallazgo] = []
    for rubro in calculo["rubros"]:
        if not rubro["items"]:
            hallazgos.append({"codigo": "rubro_vacio", "severidad": "aviso",
                              "mensaje": f"El rubro «{rubro['nombre']}» está vacío."})
        vistos = set()
        for item in rubro["items"]:
            unidad = item["unidad"].strip().casefold()
            clave = item["descripcion"].strip().casefold(), unidad
            unidad_apu = item["unidad_apu"]
            comprobaciones = (
                (item["unitario_centavos"] is None or bool(item["faltantes"]), "sin_precio", "error",
                 "Falta un precio vigente para completar el ítem."),
                (item["cantidad"] <= 0, "cantidad_no_positiva", "error", "La cantidad tiene que ser mayor que cero."),
                (unidad_apu is not None and unidad != unidad_apu.strip().casefold(), "unidad_distinta", "error",
                 f"La unidad del ítem difiere de la del APU ({unidad_apu})."),
                (any((fecha_base - date.fromisoformat(fecha)).days > 90 for fecha in item["fechas_cotizaciones"]), "precio_viejo", "aviso",
                 "Al menos una cotización tiene más de 90 días."),
                (clave in vistos, "item_duplicado", "aviso", "Ya hay un ítem con esa descripción y unidad en el rubro."),
                (directo > 0 and (item["subtotal_centavos"] or 0) * 100 > directo * 40, "peso_alto", "aviso",
                 "El ítem supera el 40 % del costo directo."),
            )
            for aplica, codigo, severidad, mensaje in comprobaciones:
                if aplica:
                    hallazgos.append({"codigo": codigo, "severidad": severidad, "item_id": item["id"],
                                      "mensaje": f"{item['descripcion']}. {mensaje}"})
            vistos.add(clave)
    for campo, etiqueta, limite in (
        ("gastos_generales_pb", "Gastos generales", 50), ("beneficio_pb", "Beneficio", 50),
        ("impuestos_pb", "Impuestos", 40),
    ):
        if p[campo] > limite * 100:
            hallazgos.append({"codigo": "coeficiente_alto", "severidad": "aviso",
                              "mensaje": f"{etiqueta} supera el {limite} %."})
    return hallazgos
