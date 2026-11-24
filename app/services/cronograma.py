"""Calendario, avance y carga del cronograma de obra."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from psycopg.errors import UniqueViolation

from app.services import auditoria, dinero, excel

COLUMNAS = ("Código", "Rubro", "Tarea", "Inicio", "Fin", "Crítica", "Ítem presupuesto",
            "Material", "Cantidad", "Unidad", "Plazo hábil")


@dataclass(frozen=True)
class Calendario:
    feriados: frozenset[date]
    fijos: frozenset[tuple[int, int]]

    def es_habil(self, dia):
        return dia.weekday() < 5 and dia not in self.feriados and (dia.month, dia.day) not in self.fijos

    def proximo_habil(self, dia):
        dia += timedelta(days=1)
        while not self.es_habil(dia):
            dia += timedelta(days=1)
        return dia

    def restar_habiles(self, dia, cantidad):
        while cantidad > 0:
            dia -= timedelta(days=1)
            if self.es_habil(dia):
                cantidad -= 1
        return dia

    def habiles(self, inicio, fin):
        if fin < inicio:
            return 0
        semanas, resto = divmod((fin - inicio).days + 1, 7)
        total = semanas * 5 + sum((inicio.weekday() + n) % 7 < 5 for n in range(resto))
        dias = {d for d in self.feriados if inicio <= d <= fin}
        for anio in range(inicio.year, fin.year + 1):
            for mes, dia in self.fijos:
                fijo = date(anio, mes, dia)
                if inicio <= fijo <= fin:
                    dias.add(fijo)
        return total - sum(d.weekday() < 5 for d in dias)


def calendario(db, empresa_id):
    feriados = db.execute("SELECT fecha FROM feriados WHERE empresa_id=%s", (empresa_id,)).fetchall()
    fijos = db.execute("SELECT mes,dia FROM obra_feriados_fijos()").fetchall()
    return Calendario(frozenset(f["fecha"] for f in feriados), frozenset((f["mes"], f["dia"]) for f in fijos))


def normalizar(texto):
    letras = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in letras if not unicodedata.combining(c))


def activas(tareas, dia):
    return [t for t in tareas if t["inicio"] <= dia <= t["fin"]]


def buscar(tareas, texto, dia):
    palabras = set(re.findall(r"\w+", normalizar(texto)))
    coincidencias = []
    for t in tareas:
        terminos = set(re.findall(r"\w+", normalizar(f"{t['codigo']} {t['nombre']} {t['rubro']}")))
        puntos = len(palabras & terminos)
        if puntos:
            coincidencias.append((puntos * 2 + int(t["inicio"] <= dia <= t["fin"]), t))
    return [t for _, t in sorted(coincidencias, key=lambda fila: (-fila[0], fila[1]["orden"], fila[1]["id"]))[:5]]


def previsto(tarea, dia, cal):
    """Puntos básicos: transcurridos sobre duración, en hábiles e incluyendo el día."""
    if dia < tarea["inicio"]:
        return 0
    if dia >= tarea["fin"]:
        return 10000
    total = cal.habiles(tarea["inicio"], tarea["fin"])
    return _ratio(cal.habiles(tarea["inicio"], dia) * 10000, total)


def _ratio(numerador, denominador):
    return dinero._redondear(numerador, denominador) if denominador else 0


def avance_obra(db, proyecto, dia):
    empresa, pid = proyecto["empresa_id"], proyecto["id"]
    cal = calendario(db, empresa)
    filas = db.execute(
        """SELECT t.*,coalesce(v.avance_pb,0) AS real_pb,i.cantidad,i.precio_emitido_centavos
             FROM tareas_obra t
             LEFT JOIN presupuestos p ON p.empresa_id=t.empresa_id AND p.proyecto_id=t.proyecto_id
                 AND p.id=t.presupuesto_id AND p.estado='emitido'
             LEFT JOIN items_presupuesto i ON i.empresa_id=p.empresa_id AND i.presupuesto_id=p.id
                 AND i.id=t.item_presupuesto_id
             LEFT JOIN LATERAL (
                 SELECT avance_pb FROM avances_tarea a WHERE a.empresa_id=t.empresa_id AND a.proyecto_id=t.proyecto_id
                      AND a.tarea_id=t.id AND a.fecha<=%s ORDER BY a.fecha DESC,a.id DESC LIMIT 1
             ) v ON true
            WHERE t.empresa_id=%s AND t.proyecto_id=%s ORDER BY t.orden,t.id""",
        (dia, empresa, pid),
    ).fetchall()
    dias_total = dias_transcurridos = real_dias = total_economico = base_economica = 0
    for fila in filas:
        dias = cal.habiles(fila["inicio"], fila["fin"])
        dias_total += dias
        dias_transcurridos += cal.habiles(fila["inicio"], min(dia, fila["fin"]))
        real_dias += fila["real_pb"] * dias
        fila["previsto_pb"] = previsto(fila, dia, cal)
        fila["atraso_pb"] = max(0, fila["previsto_pb"] - fila["real_pb"])
        precio = fila["precio_emitido_centavos"]
        subtotal = dinero.multiplicar(precio, fila["cantidad"]) if precio is not None else 0
        fila["economico_centavos"] = dinero.aplicar_coeficiente(subtotal, fila["real_pb"])
        base_economica += subtotal
        total_economico += fila["economico_centavos"]
    filas.sort(key=lambda t: (not bool(t["atraso_pb"]), not t["critica"], -t["atraso_pb"], t["orden"], t["id"]))
    return {"tareas": filas, "real_pb": _ratio(real_dias, dias_total),
            "previsto_pb": _ratio(dias_transcurridos * 10000, dias_total), "economico_centavos": total_economico,
            "economico_pb": _ratio(total_economico * 10000, base_economica),
            "base_economica_centavos": base_economica}


def items_emitidos(db, proyecto):
    return db.execute(
        """SELECT i.id,i.descripcion,p.id AS presupuesto_id,p.nombre AS presupuesto
             FROM items_presupuesto i JOIN presupuestos p ON p.empresa_id=i.empresa_id AND p.id=i.presupuesto_id
            WHERE p.empresa_id=%s AND p.proyecto_id=%s AND p.estado='emitido'
              AND i.precio_emitido_centavos IS NOT NULL ORDER BY p.id,i.orden,i.id""",
        (proyecto["empresa_id"], proyecto["id"]),
    ).fetchall()


def crear_tarea(db, proyecto, datos):
    empresa, pid = proyecto["empresa_id"], proyecto["id"]
    if datos["fin"] < datos["inicio"]:
        raise HTTPException(400, "La fecha fin debe ser igual o posterior al inicio.")
    item = datos["item_presupuesto_id"]
    presupuesto_id = None
    if item is not None:
        vinculo = next((i for i in items_emitidos(db, proyecto) if i["id"] == item), None)
        if vinculo is None:
            raise HTTPException(404, "Ítem emitido no encontrado en el proyecto.")
        presupuesto_id = vinculo["presupuesto_id"]
    try:
        fila = db.execute(
            """INSERT INTO tareas_obra(empresa_id,proyecto_id,codigo,nombre,rubro,inicio,fin,critica,
                                       item_presupuesto_id,presupuesto_id,orden)
               SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,coalesce(max(orden),0)+1
                 FROM tareas_obra WHERE empresa_id=%s AND proyecto_id=%s RETURNING id""",
            (empresa, pid, datos["codigo"], datos["nombre"], datos["rubro"], datos["inicio"], datos["fin"],
             datos["critica"], item, presupuesto_id, empresa, pid),
        ).fetchone()
    except UniqueViolation as error:
        raise HTTPException(409, "El código o el ítem emitido ya está vinculado a una tarea.") from error
    return fila["id"]


def _tarea(db, proyecto, tarea_id):
    fila = db.execute(
        "SELECT * FROM tareas_obra WHERE empresa_id=%s AND proyecto_id=%s AND id=%s",
        (proyecto["empresa_id"], proyecto["id"], tarea_id),
    ).fetchone()
    if not fila:
        raise HTTPException(404, "Tarea no encontrada.")
    return fila


def registrar_avance(db, usuario, proyecto, tarea_id, fecha, avance_pb, *, request=None):
    empresa, pid = usuario["empresa_id"], proyecto["id"]
    _tarea(db, proyecto, tarea_id)
    fila = db.execute(
        """INSERT INTO avances_tarea(empresa_id,proyecto_id,tarea_id,fecha,avance_pb,registrado_por)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""", (empresa, pid, tarea_id, fecha, avance_pb, usuario["id"]),
    ).fetchone()
    auditoria.registrar(db, usuario, "obra.avance_registrado", proyecto_id=pid, objeto="tarea_obra",
                        objeto_id=tarea_id, detalle={"avance_id": fila["id"], "avance_pb": avance_pb}, request=request)
    return fila["id"]


def agregar_material(db, proyecto, tarea_id, datos):
    _tarea(db, proyecto, tarea_id)
    try:
        db.execute(
            """INSERT INTO materiales_tarea(empresa_id,proyecto_id,tarea_id,nombre,cantidad,unidad,plazo_dias)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (proyecto["empresa_id"], proyecto["id"], tarea_id, datos["nombre"], datos["cantidad"],
             datos["unidad"], datos["plazo_dias"]),
        )
    except UniqueViolation as error:
        raise HTTPException(409, "Ese material ya está cargado para la tarea.") from error


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    return date.fromisoformat(str(valor).strip())


def _entero(valor, minimo, maximo):
    numero = excel._decimal(valor, "el entero")
    if not minimo <= numero <= maximo or numero != numero.to_integral_value():
        raise ValueError("El número entero está fuera del rango permitido.")
    return int(numero)


def planilla(db, proyecto, contenido):
    emitidos = {i["id"] for i in items_emitidos(db, proyecto)}
    usados = {f["codigo"] for f in db.execute(
        "SELECT codigo FROM tareas_obra WHERE empresa_id=%s AND proyecto_id=%s",
        (proyecto["empresa_id"], proyecto["id"]),
    )}
    leidos = {}
    materiales = set()

    def interpretar(fila):
        codigo, rubro, nombre, inicio, fin, critica, item, material, cantidad, unidad, plazo = fila
        codigo = excel._texto(codigo, "el código", 80)
        if codigo in usados:
            raise ValueError("La tarea ya existe en el cronograma.")
        inicio, fin = _fecha(inicio), _fecha(fin)
        if fin < inicio:
            raise ValueError("El fin es anterior al inicio de la tarea.")
        crit = normalizar(str(critica or "")).strip()
        if crit not in {"", "si", "s", "true", "1", "no", "false", "0"}:
            raise ValueError("Indicá sí o no en Crítica.")
        item_id = None if item is None or item == "" else _entero(item, 1, 2**63 - 1)
        if item_id is not None and item_id not in emitidos:
            raise ValueError("Ítem emitido no encontrado en el proyecto.")
        datos = {"codigo": codigo, "rubro": excel._texto(rubro, "el rubro", 120, opcional=True),
                 "nombre": excel._texto(nombre, "la tarea", 240), "inicio": inicio, "fin": fin,
                 "critica": crit in {"si", "s", "true", "1"}, "item_presupuesto_id": item_id}
        if codigo in leidos and leidos[codigo] != datos:
            raise ValueError("Las filas de una tarea deben repetir sus datos.")
        insumo = None
        if material is not None and material != "":
            material = excel._texto(material, "el material", 200)
            cantidad = excel._decimal(cantidad, "la cantidad")
            if not 0 < cantidad < 10**10 or cantidad != cantidad.quantize(Decimal("0.0001")):
                raise ValueError("Ingresá una cantidad positiva de hasta cuatro decimales.")
            if (codigo, material) in materiales:
                raise ValueError("El material está repetido para esa tarea.")
            insumo = {"nombre": material, "cantidad": cantidad, "unidad": excel._texto(unidad, "la unidad", 40),
                      "plazo_dias": _entero(plazo, 0, 3650)}
            materiales.add((codigo, material))
        elif any(v is not None and v != "" for v in (cantidad, unidad, plazo)):
            raise ValueError("Completá el nombre del material.")
        leidos[codigo] = datos
        return {"tarea": datos, "material": insumo}

    return excel._leer(contenido, COLUMNAS, interpretar)
