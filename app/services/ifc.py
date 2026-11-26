"""Resumen y cantidades de obra de un IFC STEP, sin construir geometría."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import ifcopenshell
from ifcopenshell.util import element, placement, unit

from app import config

TIPOS = {"IfcWall": ("muro", "muros"), "IfcSlab": ("losa", "losas"), "IfcColumn": ("columna", "columnas"),
         "IfcBeam": ("viga", "vigas"), "IfcDoor": ("puerta", "puertas"), "IfcWindow": ("ventana", "ventanas"),
         "IfcStair": ("escalera", "escaleras"), "IfcRoof": ("cubierta", "cubiertas"), "IfcSpace": ("espacio", "espacios")}
_MEDIDAS = {"NetSideArea": ("area_m2", "AREAUNIT", "IfcQuantityArea"),
            "NetArea": ("area_m2", "AREAUNIT", "IfcQuantityArea"),
            "NetVolume": ("volumen_m3", "VOLUMEUNIT", "IfcQuantityVolume"),
            "Length": ("longitud_m", "LENGTHUNIT", "IfcQuantityLength")}


def _grupo():
    return {"cantidad": 0, "sin_cantidades": 0, "area_m2": None, "volumen_m3": None, "longitud_m": None}


def _juegos_de_cantidades(objeto):
    tipo = element.get_type(objeto)
    if tipo:
        yield from tipo.HasPropertySets or ()
    for rel in getattr(objeto, "IsDefinedBy", ()):
        if rel.is_a("IfcRelDefinesByProperties"):
            juego = rel.RelatingPropertyDefinition
            yield from juego if isinstance(juego, tuple) else (juego,)


def _cantidades(objeto, unidades):
    medidas = {}
    for qto in _juegos_de_cantidades(objeto):
        if not qto.is_a("IfcElementQuantity"):
            continue
        nombre = qto.Name or ""
        if not (nombre == "BaseQuantities" or nombre.startswith("Qto_") and nombre.endswith("BaseQuantities")):
            continue
        for q in qto.Quantities:
            if q.Name not in _MEDIDAS:
                continue
            _, tipo_unidad, clase = _MEDIDAS[q.Name]
            unidad = getattr(q, "Unit", None) or unidades[tipo_unidad]
            if not unidad or not q.is_a(clase):
                continue
            if unidad.UnitType != tipo_unidad or not (unidad.is_a("IfcSIUnit") or unidad.is_a("IfcConversionBasedUnit")):
                continue
            valor_bruto = getattr(q, clase.removeprefix("IfcQuantity") + "Value")
            valor = Decimal(str(valor_bruto)) * Decimal(str(unit.get_unit_scale(unidad)))
            if valor.is_finite():
                medidas[q.Name] = valor
    # NetSideArea y NetArea describen superficies alternativas del mismo elemento.
    resultado = {}
    for nombre, (campo, _, _) in _MEDIDAS.items():
        if nombre in medidas:
            resultado.setdefault(campo, medidas[nombre])
    return resultado


def _acumular(grupo, medidas):
    grupo["cantidad"] += 1
    if not medidas:
        grupo["sin_cantidades"] += 1
    for campo, valor in medidas.items():
        grupo[campo] = (grupo[campo] or Decimal(0)) + valor


def _totales(grupos):
    resultado = {}
    for tipo, grupo in grupos.items():
        valores = grupo.copy()
        for campo, valor in grupo.items():
            if isinstance(valor, Decimal):
                valores[campo] = float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        resultado[tipo] = valores
    return resultado


def _piso(objeto):
    vistos = set()
    padre = element.get_parent(objeto)
    while padre and padre.id() not in vistos:
        if padre.is_a("IfcBuildingStorey"):
            return padre
        vistos.add(padre.id())
        padre = element.get_parent(padre)
    return None


def resumen(ruta: Path) -> dict:
    if ruta.stat().st_size > config.IFC_MAX_MB * 1024**2:
        raise ValueError("El modelo supera IFC_MAX_MB.")
    modelo = ifcopenshell.open(ruta, format=".ifc")
    proyectos = modelo.by_type("IfcProject")
    if not proyectos:
        raise ValueError("Falta el proyecto IFC.")
    unidades = {tipo: unit.get_project_unit(modelo, tipo) for tipo in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")}
    escala = unit.get_unit_scale(unidades["LENGTHUNIT"]) if unidades["LENGTHUNIT"] else None
    totales = defaultdict(_grupo)
    por_piso = defaultdict(lambda: defaultdict(_grupo))
    for tipo in TIPOS:
        for objeto in modelo.by_type(tipo):
            medidas = _cantidades(objeto, unidades)
            _acumular(totales[tipo], medidas)
            piso = _piso(objeto)
            _acumular(por_piso[piso.id() if piso else None][tipo], medidas)
    pisos = []
    for piso in modelo.by_type("IfcBuildingStorey"):
        elevacion = piso.Elevation
        if piso.ObjectPlacement and piso.ObjectPlacement.is_a("IfcLocalPlacement"):
            elevacion = float(placement.get_storey_elevation(piso))
        pisos.append({"nombre": piso.Name or f"Piso #{piso.id()}",
                      "elevacion_m": elevacion * escala if elevacion is not None and escala is not None else None,
                      "tipos": _totales(por_piso[piso.id()])})
    pisos.sort(key=lambda p: (p["elevacion_m"] is None, p["elevacion_m"], p["nombre"]))
    if None in por_piso:
        pisos.append({"nombre": "Sin piso asignado", "elevacion_m": None, "tipos": _totales(por_piso[None])})
    return {"esquema": modelo.schema_identifier, "proyecto": proyectos[0].Name or "Sin nombre",
            "edificios": [e.Name or f"Edificio #{e.id()}" for e in modelo.by_type("IfcBuilding")],
            "pisos": pisos, "tipos": _totales(totales)}


def _numero(valor):
    return f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def frases(datos):
    yield f"Proyecto {datos['proyecto']}. Esquema {datos['esquema']}."
    for edificio in datos["edificios"]:
        yield f"Edificio: {edificio}."
    for zona in [{"nombre": "Total de la obra", "tipos": datos["tipos"]}, *datos["pisos"]]:
        if "elevacion_m" in zona:
            elevacion = zona["elevacion_m"]
            yield (f"{zona['nombre']}. Elevación {_numero(elevacion)} m." if elevacion is not None
                   else f"{zona['nombre']}.")
        for tipo, grupo in zona["tipos"].items():
            cantidad = grupo["cantidad"]
            singular, plural = TIPOS[tipo]
            nombre = singular if cantidad == 1 else plural
            campos = [f"{zona['nombre']}: {cantidad} {nombre}"]
            for clave, titulo, unidad in [("area_m2", "área neta", "m²"), ("volumen_m3", "volumen neto", "m³"),
                                         ("longitud_m", "longitud", "m")]:
                if grupo[clave] is not None:
                    campos.append(f"{titulo} {_numero(grupo[clave])} {unidad}")
            if grupo["sin_cantidades"]:
                campos.append(f"sin cantidades: {grupo['sin_cantidades']}")
            yield ", ".join(campos) + "."
