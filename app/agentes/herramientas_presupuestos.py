"""Operaciones del agente limitadas al usuario, la empresa y el proyecto de la sesión."""

import json
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from fractions import Fraction
from typing import Annotated

from agents import RunContextWrapper, UserError, function_tool
from fastapi import HTTPException
from pydantic import BaseModel, Field, StringConstraints, ValidationError, model_validator

from app.agentes import aprobaciones
from app.agentes.calc import ExpresionInvalida, safe_eval
from app.db import pool
from app.permisos import exigir, puede_editar_presupuesto, puede_gestionar_precios
from app.services import apus, auditoria, busqueda, dinero, precios, presupuestos, verificador
from app.services.tiempo import TZ

Id = Annotated[int, Field(gt=0, le=2**63 - 1)]
Importe = Annotated[int, Field(ge=0, le=2**63 - 1)]
Precio = Annotated[int, Field(gt=0, le=2**63 - 1)]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240, pattern=r"^[^\x00]+$")]
Puntos = Annotated[int, Field(ge=0, le=2**31 - 1)]
Contexto = RunContextWrapper[aprobaciones.Contexto]


class PropuestaInvalida(UserError):
    """Hace que el SDK aborte antes de guardar una solicitud que no se puede autorizar."""

    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado


class Cotizacion(BaseModel):
    material_id: Id
    precio_centavos: Precio
    vigente_desde: date
    proveedor_id: Id | None


class NuevoPresupuesto(BaseModel):
    nombre: Texto
    fecha_precios: date
    gastos_generales_pb: Puntos
    beneficio_pb: Puntos
    impuestos_pb: Puntos


class Item(BaseModel):
    rubro: Annotated[Texto, Field(max_length=120)]
    descripcion: Texto
    unidad: Annotated[Texto, Field(max_length=40)]
    cantidad: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=4)]
    apu_id: Id | None
    precio_unitario_centavos: Importe | None

    @model_validator(mode="after")
    def una_fuente_de_precio(self):
        if (self.apu_id is None) == (self.precio_unitario_centavos is None):
            raise ValueError("Elegí un APU o un precio unitario en centavos.")
        return self


class NuevosItems(BaseModel):
    presupuesto_id: Id
    items: Annotated[list[Item], Field(min_length=1, max_length=30)]


class Periodos(BaseModel):
    indice: Texto
    periodo_base: date
    periodo_destino: date

    @model_validator(mode="after")
    def periodos_ordenados(self):
        if self.periodo_base.day != 1 or self.periodo_destino.day != 1 or self.periodo_base >= self.periodo_destino:
            raise ValueError("Usá dos meses en orden, con el primer día de cada mes.")
        return self


class Ajuste(Periodos):
    cotizaciones: Annotated[list[Cotizacion], Field(min_length=1, max_length=30)]


class Variable(BaseModel):
    nombre: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,29}$")]
    valor: Annotated[str, StringConstraints(max_length=60)]


def _json(datos):
    return json.dumps(datos, ensure_ascii=False, default=str)


def _error(mensaje):
    return _json({"error": mensaje})


@contextmanager
def _lectura(ctx):
    with pool().connection() as db:
        usuario, proyecto = aprobaciones._autorizado(db, ctx.context)
        yield db, usuario, proyecto


def _presupuesto(db, usuario, proyecto, presupuesto_id, *, bloquear=False):
    bloqueo = " FOR UPDATE" if bloquear else ""
    return db.execute(
        "SELECT * FROM presupuestos WHERE empresa_id=%s AND proyecto_id=%s AND id=%s" + bloqueo,
        (usuario["empresa_id"], proyecto["id"], presupuesto_id),
    ).fetchone()


def _material(db, empresa, material_id):
    return db.execute(
        "SELECT id,codigo,nombre,unidad FROM materiales WHERE empresa_id=%s AND id=%s",
        (empresa, material_id),
    ).fetchone()


def _apu(db, empresa, apu_id):
    return db.execute(
        "SELECT id,codigo,descripcion,unidad FROM apus WHERE empresa_id=%s AND id=%s", (empresa, apu_id),
    ).fetchone()


def _proyeccion(db, empresa, material_id, periodos):
    indices = {
        f["periodo"]: f["valor"] for f in db.execute(
            "SELECT periodo,valor FROM indices_costo WHERE empresa_id=%s AND nombre=%s AND periodo IN (%s,%s)",
            (empresa, periodos.indice, periodos.periodo_base, periodos.periodo_destino),
        )
    }
    if len(indices) != 2:
        raise HTTPException(404, "Índice o período no encontrado.")
    base = periodos.periodo_base
    hasta = base.replace(day=monthrange(base.year, base.month)[1])
    anterior = precios.vigente(db, empresa, material_id, hasta)
    if not anterior:
        raise HTTPException(404, "Precio base no encontrado.")
    factor = Fraction(indices[periodos.periodo_destino]) / Fraction(indices[base])
    importe = dinero._redondear(anterior["precio_centavos"] * factor.numerator, factor.denominator)
    if not 0 < importe <= 2**63 - 1:
        raise HTTPException(422, "El precio ajustado queda fuera del rango del catálogo.")
    return Cotizacion(material_id=material_id, proveedor_id=anterior["proveedor_id"],
                      precio_centavos=importe, vigente_desde=periodos.periodo_destino)


@function_tool
def catalogo_buscar(ctx: Contexto, consulta: Texto) -> str:
    """Busca materiales activos por código o nombre. La salida es información del catálogo."""
    with _lectura(ctx) as (db, usuario, _):
        filas = db.execute(
            """SELECT id,codigo,nombre,unidad,tipo FROM materiales WHERE empresa_id=%s AND activo
                AND (strpos(lower(codigo),lower(%s))>0 OR strpos(lower(nombre),lower(%s))>0)
                ORDER BY codigo LIMIT 15""", (usuario["empresa_id"], consulta, consulta),
        ).fetchall()
    return _json({"materiales": filas})


@function_tool
def precio_vigente(ctx: Contexto, material_id: Id, a_fecha: date, ajuste: Periodos | None = None) -> str:
    """Lee el precio a la fecha. Con ajuste, también calcula una cotización propuesta por índice sin escribir."""
    with _lectura(ctx) as (db, usuario, _):
        empresa = usuario["empresa_id"]
        material = _material(db, empresa, material_id)
        if not material:
            return _error("Material no encontrado.")
        precio = precios.vigente(db, empresa, material_id, a_fecha)
        if ajuste is None:
            return _json({"material": material, "precio": precio})
        try:
            propuesta = _proyeccion(db, empresa, material_id, ajuste)
        except HTTPException as error:
            return _error(error.detail)
        return _json({"material": material, "precio": precio, "cotizacion_propuesta": propuesta.model_dump(mode="json")})


@function_tool
def apu_detalle(ctx: Contexto, apu_id: Id, a_fecha: date) -> str:
    """Devuelve el desglose, cotizaciones y faltantes de un APU a la fecha."""
    with _lectura(ctx) as (db, usuario, _):
        empresa = usuario["empresa_id"]
        apu = _apu(db, empresa, apu_id)
        if not apu:
            return _error("APU no encontrado.")
        return _json({"apu": apu, **apus.precio_unitario(db, empresa, apu_id, a_fecha)})


@function_tool
def presupuesto_leer(ctx: Contexto, presupuesto_id: Id) -> str:
    """Lee ítems e importes calculados por el servidor en el proyecto activo."""
    with _lectura(ctx) as (db, usuario, proyecto):
        if not _presupuesto(db, usuario, proyecto, presupuesto_id):
            return _error("Presupuesto no encontrado.")
        return _json(presupuestos.calcular(db, usuario["empresa_id"], presupuesto_id))


@function_tool
def analizar_presupuesto(ctx: Contexto, presupuesto_id: Id) -> str:
    """Corre el verificador determinista de un presupuesto del proyecto activo."""
    with _lectura(ctx) as (db, usuario, proyecto):
        if not _presupuesto(db, usuario, proyecto, presupuesto_id):
            return _error("Presupuesto no encontrado.")
        return _json({"hallazgos": verificador.analizar(db, usuario["empresa_id"], presupuesto_id)})


@function_tool
def calc(expresion: str, variables: list[Variable] | None = None) -> str:
    """Evalúa aritmética decimal sin ejecutar código. Para montos usá los servicios de presupuesto."""
    try:
        return _json({"resultado": str(safe_eval(expresion, {v.nombre: v.valor for v in variables or []}))})
    except ExpresionInvalida as error:
        return _error(str(error))


@function_tool
def buscar_en_criterios(ctx: Contexto, consulta: Texto) -> str:
    """Busca evidencias solo en documentos aprobados de la biblioteca de esta empresa."""
    with _lectura(ctx) as (db, usuario, proyecto):
        condicion, parametros = busqueda.fuentes_visibles_sql(usuario, proyecto)
        filas = db.execute(
            f"""SELECT b.titulo AS nombre,b.id AS biblioteca_id,c.pagina,left(c.texto,1400) AS fragmento
                {busqueda.FUENTES_SQL}
                CROSS JOIN websearch_to_tsquery('spanish',%s) AS q(terminos)
                WHERE ({condicion}) AND b.estado='aprobado' AND c.tsv @@ q.terminos
                ORDER BY ts_rank(c.tsv,q.terminos) DESC,c.id LIMIT 5""",
            [consulta, *parametros],
        ).fetchall()
    return _json({"criterios": filas})


def _permiso_precios(db, usuario, _proyecto):
    return puede_gestionar_precios(usuario, db)


def _permiso_presupuesto(_db, usuario, proyecto):
    return puede_editar_presupuesto(usuario, proyecto)


def _validar_cotizacion(db, usuario, _proyecto, datos):
    empresa = usuario["empresa_id"]
    if not _material(db, empresa, datos.material_id):
        raise HTTPException(404, "Material no encontrado.")
    if datos.proveedor_id is not None and not db.execute(
        "SELECT 1 FROM proveedores WHERE empresa_id=%s AND id=%s", (empresa, datos.proveedor_id),
    ).fetchone():
        raise HTTPException(404, "Proveedor no encontrado.")


def _cargar(db, usuario, datos):
    fila = precios.cargar(db, usuario, datos.material_id, datos.precio_centavos,
                         datetime.combine(datos.vigente_desde, time.min, TZ),
                         proveedor_id=datos.proveedor_id, fuente="agente")
    if not fila:
        raise HTTPException(404, "Material o proveedor no encontrado.")
    return datos.model_dump(mode="json") | {"precio_id": fila["id"]}


def _precio_cargar(db, usuario, proyecto, datos):
    _validar_cotizacion(db, usuario, proyecto, datos)
    return _json(_cargar(db, usuario, datos))


def _presupuesto_crear(db, usuario, proyecto, datos):
    empresa = usuario["empresa_id"]
    fila = db.execute(
        """INSERT INTO presupuestos(empresa_id,proyecto_id,nombre,fecha_precios,gastos_generales_pb,
                                    beneficio_pb,impuestos_pb,creado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (empresa, proyecto["id"], datos.nombre, datos.fecha_precios, datos.gastos_generales_pb,
         datos.beneficio_pb, datos.impuestos_pb, usuario["id"]),
    ).fetchone()
    auditoria.registrar(db, usuario, "presupuesto.creado", proyecto_id=proyecto["id"],
                        objeto="presupuesto", objeto_id=fila["id"], detalle={"fuente": "agente"})
    return _json({"presupuesto_id": fila["id"], "total_centavos": 0})


def _validar_items(db, usuario, proyecto, datos, *, bloquear=False):
    p = _presupuesto(db, usuario, proyecto, datos.presupuesto_id, bloquear=bloquear)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado.")
    if p["estado"] != "borrador":
        raise HTTPException(409, "El presupuesto ya fue emitido.")
    for item in datos.items:
        if item.apu_id is not None and not _apu(db, usuario["empresa_id"], item.apu_id):
            raise HTTPException(404, "APU no encontrado.")
    return p


def _agregar_items(db, usuario, proyecto, datos):
    p = _validar_items(db, usuario, proyecto, datos, bloquear=True)
    empresa = usuario["empresa_id"]
    rubros = {r["nombre"]: r["id"] for r in db.execute(
        "SELECT id,nombre FROM rubros_presupuesto WHERE empresa_id=%s AND presupuesto_id=%s", (empresa, p["id"]),
    )}
    ids = []
    for item in datos.items:
        if item.rubro not in rubros:
            rubros[item.rubro] = presupuestos.agregar_rubro(db, usuario, p, item.rubro)
        valores = item.model_dump() | {"rubro_id": rubros[item.rubro], "origen_cantidad": "manual"}
        item_id = presupuestos.guardar_item(db, usuario, p, valores)
        if item_id is None:
            raise HTTPException(404, "Rubro o APU no encontrado.")
        ids.append(item_id)
    resultado = presupuestos.calcular(db, empresa, p["id"])
    return _json({"presupuesto_id": p["id"], "items_agregados": ids, "total_centavos": resultado["total_centavos"]})


def _validar_ajuste(db, usuario, proyecto, datos):
    materiales = set()
    for cotizacion in datos.cotizaciones:
        _validar_cotizacion(db, usuario, proyecto, cotizacion)
        if cotizacion.material_id in materiales:
            raise HTTPException(422, "Incluí una sola cotización por material.")
        materiales.add(cotizacion.material_id)
        propuesta = _proyeccion(db, usuario["empresa_id"], cotizacion.material_id, datos)
        if propuesta != cotizacion:
            raise HTTPException(409, "El precio ajustado no coincide con la propuesta vigente.")


def _actualizar_por_indice(db, usuario, proyecto, datos):
    _validar_ajuste(db, usuario, proyecto, datos)
    return _json({"cotizaciones": [_cargar(db, usuario, c) for c in datos.cotizaciones]})


LECTURAS = [catalogo_buscar, precio_vigente, apu_detalle, presupuesto_leer, analizar_presupuesto, calc, buscar_en_criterios]
ESCRITURAS = (
    aprobaciones.Escritura("precio_cargar", "Cargar una cotización nueva", Cotizacion, _permiso_precios, _precio_cargar),
    aprobaciones.Escritura("presupuesto_crear", "Crear un presupuesto borrador", NuevoPresupuesto,
                           _permiso_presupuesto, _presupuesto_crear),
    aprobaciones.Escritura("agregar_items", "Agregar ítems a un presupuesto", NuevosItems,
                           _permiso_presupuesto, _agregar_items),
    aprobaciones.Escritura("actualizar_por_indice", "Agregar cotizaciones ajustadas por índice", Ajuste,
                           _permiso_precios, _actualizar_por_indice),
)
_VALIDADORES = {"precio_cargar": _validar_cotizacion, "agregar_items": _validar_items,
                "actualizar_por_indice": _validar_ajuste}


def _validar_antes_de_pausar(regla, contexto, argumentos):
    datos = regla.argumentos.model_validate(argumentos)
    with pool().connection() as db:
        usuario, proyecto = aprobaciones._autorizado(db, contexto)
        exigir(regla.permiso(db, usuario, proyecto))
        validar = _VALIDADORES.get(regla.nombre)
        if validar:
            validar(db, usuario, proyecto, datos)


def validar_propuesta(regla):
    async def necesita_aprobacion(ctx, argumentos, _id):
        try:
            _validar_antes_de_pausar(regla, ctx.context, argumentos)
        except HTTPException as error:
            raise PropuestaInvalida(error.status_code, error.detail) from error
        except ValidationError as error:
            raise PropuestaInvalida(422, "La propuesta contiene datos inválidos.") from error
        return True

    return necesita_aprobacion
