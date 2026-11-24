"""Condiciones meteorológicas de un día usando Open-Meteo."""

import logging
from math import isfinite

import httpx
from psycopg.types.json import Jsonb

from app.services import auditoria
from app.services.tiempo import TZ

log = logging.getLogger(__name__)
_WMO = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Niebla", 48: "Niebla", 51: "Llovizna", 53: "Llovizna", 55: "Llovizna intensa",
    61: "Lluvia débil", 63: "Lluvia", 65: "Lluvia fuerte", 80: "Chaparrones", 81: "Chaparrones",
    82: "Chaparrones fuertes", 95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo",
}


def del_dia(lat, lon, fecha):
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    dia = fecha.isoformat()
    try:
        respuesta = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=4.0, params={
            "latitude": f"{lat:.6f}", "longitude": f"{lon:.6f}", "timezone": str(TZ),
            "daily": "weather_code,temperature_2m_min,temperature_2m_max,precipitation_sum",
            "start_date": dia, "end_date": dia,
        })
        respuesta.raise_for_status()
        diario = respuesta.json()["daily"]
        indice = diario["time"].index(dia)
        codigo = int(diario["weather_code"][indice])
        minima = float(diario["temperature_2m_min"][indice])
        maxima = float(diario["temperature_2m_max"][indice])
        lluvia = float(diario["precipitation_sum"][indice])
        if not all(map(isfinite, (minima, maxima, lluvia))):
            return None
    except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        log.info("No se obtuvo el clima de obra (%s)", type(error).__name__)
        return None
    estado = _WMO.get(codigo, f"Código WMO {codigo}")
    resumen = f"{estado} · {minima:g} a {maxima:g} °C · Lluvia {lluvia:g} mm"
    return {"fuente": "Open-Meteo", "codigo": codigo, "minima": minima, "maxima": maxima,
            "lluvia_mm": lluvia, "resumen": resumen}


def guardar_en_parte(db, empresa_id, payload):
    parametros = (empresa_id, payload["proyecto_id"], payload["parte_id"])
    parte = db.execute(
        """SELECT r.fecha,p.lat,p.lon FROM reportes_obra r
             JOIN proyectos p ON p.empresa_id=r.empresa_id AND p.id=r.proyecto_id
            WHERE r.empresa_id=%s AND r.proyecto_id=%s AND r.id=%s AND r.estado='borrador'""",
        parametros,
    ).fetchone()
    if parte is None or parte["lat"] is None or parte["lon"] is None:
        return
    clima = del_dia(parte["lat"], parte["lon"], parte["fecha"])
    if clima is None:
        return
    actualizado = db.execute(
        """UPDATE reportes_obra SET datos=jsonb_set(datos,'{condiciones,propuesto}',%s)
            WHERE empresa_id=%s AND proyecto_id=%s AND id=%s AND estado='borrador'""",
        (Jsonb(clima), *parametros),
    ).rowcount
    if actualizado:
        auditoria.registrar(db, None, "parte.clima_obtenido", empresa_id=empresa_id, proyecto_id=parametros[1],
                            objeto="parte_obra", objeto_id=parametros[2], detalle={"fuente": clima["fuente"]})
