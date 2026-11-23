"""Planillas de presupuesto y vista previa de importaciones sin persistencia."""

import base64
import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from itsdangerous import BadData, URLSafeTimedSerializer
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException

from app import config
from app.services import dinero
from app.services.tiempo import TZ

MAX_ARCHIVO = 10 * 1024 * 1024
MAX_CONFIRMACION = 2 * MAX_ARCHIVO
TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNAS_ITEMS = ("Rubro", "Descripción", "Unidad", "Cantidad", "Código APU", "Precio unitario")
COLUMNAS_PRECIOS = ("Código de material", "Precio", "Vigente desde", "Proveedor")
CAMPOS_TOTALES = (
    ("costo_directo_centavos", "Costo directo"),
    ("gastos_generales_centavos", "Gastos generales"),
    ("beneficio_centavos", "Beneficio"),
    ("impuestos_centavos", "Impuestos"),
    ("total_centavos", "Total"),
)
_MONEDA = '[$-2C0A] #,##0.00;-[$-2C0A] #,##0.00'
_TITULO = Font(bold=True, color="FFFFFF")
_FONDO = PatternFill("solid", fgColor="243B53")
_FIRMA = URLSafeTimedSerializer(config.SECRET_KEY, salt="vista-previa-excel")


class ExcelInvalido(ValueError):
    def __init__(self, mensaje: str, estado: int = 400):
        super().__init__(mensaje)
        self.estado = estado


def _grabar(wb):
    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()


def _agregar(hoja, valores):
    hoja.append(valores)
    fila = hoja.max_row
    for columna, valor in enumerate(valores, 1):
        if isinstance(valor, str):
            # Las etiquetas de la base deben viajar como texto, incluso si empiezan con "=".
            hoja.cell(fila, columna).data_type = "s"
    return fila


def _encabezado(hoja, fila):
    for celda in hoja[fila]:
        celda.font = _TITULO
        celda.fill = _FONDO
        celda.alignment = Alignment(wrap_text=True)


def _pesos(centavos):
    return None if centavos is None else Decimal(centavos) / 100


def plantilla(columnas):
    wb = Workbook()
    hoja = wb.active
    hoja.title = "Importación"
    _agregar(hoja, columnas)
    _encabezado(hoja, 1)
    hoja.freeze_panes = "A2"
    for celda in hoja[1]:
        hoja.column_dimensions[celda.column_letter].width = max(18, len(celda.value) + 3)
    return _grabar(wb)


def exportar(calculo):
    p = calculo["presupuesto"]
    wb = Workbook()
    hoja = wb.active
    hoja.title = "Presupuesto"
    datos = wb.create_sheet("Datos")
    _agregar(hoja, (f"{p['nombre']} · v{p['version']} · {p['fecha_precios']:%d/%m/%Y}",))
    hoja.merge_cells("A1:F1")
    _agregar(hoja, ("Tipo", "Descripción", "Unidad", "Cantidad", "P. U.", "Subtotal"))
    _encabezado(hoja, 2)
    hoja.freeze_panes = "D3"
    for columna, ancho in zip("ABCDEF", (14, 48, 14, 15, 18, 18)):
        hoja.column_dimensions[columna].width = ancho
    _agregar(datos, ("Campo", "Valor (centavos)"))
    _encabezado(datos, 1)
    for campo, _ in CAMPOS_TOTALES:
        _agregar(datos, (campo, calculo[campo]))
    datos.append(())
    _agregar(datos, ("Tipo", "Descripción", "Unidad", "Cantidad", "PU (centavos)", "Subtotal (centavos)"))
    _encabezado(datos, datos.max_row)
    datos.column_dimensions["A"].width = 29
    datos.column_dimensions["B"].width = 45
    for rubro in calculo["rubros"]:
        inicio = _agregar(hoja, ("Rubro", rubro["nombre"]))
        _encabezado(hoja, inicio)
        _agregar(datos, ("Rubro", rubro["nombre"], None, None, None, rubro["subtotal_centavos"]))
        for item in rubro["items"]:
            fila = _agregar(hoja, (
                None, item["descripcion"], item["unidad"], item["cantidad"], _pesos(item["unitario_centavos"]),
            ))
            hoja[f"E{fila}"].number_format = _MONEDA
            hoja[f"F{fila}"] = f'=IF(ISNUMBER(E{fila}),ROUND(D{fila}*E{fila},2),"")'
            hoja[f"F{fila}"].number_format = _MONEDA
            _agregar(datos, ("Ítem", item["descripcion"], item["unidad"], item["cantidad"],
                            item["unitario_centavos"], item["subtotal_centavos"]))
        fin = hoja.max_row
        hoja[f"F{inicio}"] = f"=ROUND(SUM(F{inicio + 1}:F{fin}),2)" if fin > inicio else "=0"
        hoja[f"F{inicio}"].number_format = _MONEDA
    fin = hoja.max_row
    directo = _agregar(hoja, (None, "Costo directo"))
    hoja[f"F{directo}"] = f'=ROUND(SUMIF(A3:A{fin},"Rubro",F3:F{fin}),2)' if fin >= 3 else "=0"
    for campo, etiqueta in (
        ("gastos_generales_pb", "Gastos generales"), ("beneficio_pb", "Beneficio"), ("impuestos_pb", "Impuestos"),
    ):
        fila = _agregar(hoja, (None, etiqueta, None, None, Decimal(p[campo]) / 10_000))
        base = f"F{directo}" if fila == directo + 1 else f"SUM(F{directo}:F{fila - 1})"
        hoja[f"E{fila}"].number_format = "0.00%"
        hoja[f"F{fila}"] = f"=ROUND({base}*E{fila},2)"
    total = _agregar(hoja, (None, "Total"))
    hoja[f"F{total}"] = f"=ROUND(SUM(F{directo}:F{total - 1}),2)"
    _encabezado(hoja, total)
    for fila in range(directo, total + 1):
        hoja[f"F{fila}"].number_format = _MONEDA
    return _grabar(wb)


def subir(archivo):
    if PurePath(archivo.filename or "").suffix.lower() != ".xlsx":
        raise ExcelInvalido("Subí una planilla .xlsx sin macros.")
    contenido = archivo.file.read(MAX_ARCHIVO + 1)
    if len(contenido) > MAX_ARCHIVO:
        raise ExcelInvalido("La planilla supera los 10 MB.", 413)
    return contenido


def _huella_filas(filas):
    argumentos = json.dumps(filas, default=str, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(argumentos).hexdigest()


def firmar(contenido, usuario, destino, filas):
    alcance = [usuario["empresa_id"], usuario["id"], destino]
    return _FIRMA.dumps([alcance, base64.b64encode(contenido).decode("ascii"), _huella_filas(filas)])


def abrir_confirmacion(confirmacion, usuario, destino):
    try:
        alcance, codificado, huella = _FIRMA.loads(confirmacion, max_age=900)
        contenido = base64.b64decode(codificado, validate=True)
        if alcance != [usuario["empresa_id"], usuario["id"], destino] or len(contenido) > MAX_ARCHIVO:
            raise ValueError("Vista previa fuera de alcance")
    except (BadData, TypeError, ValueError) as error:
        raise ExcelInvalido("La vista previa venció o no corresponde. Volvé a subir la planilla.") from error
    return contenido, huella


def comprobar_filas(filas, huella):
    if not any("error" in fila for fila in filas) and _huella_filas(filas) != huella:
        raise ExcelInvalido("El catálogo cambió desde la vista previa. Volvé a subir la planilla.", 409)


def _validar_paquete(contenido):
    with ZipFile(BytesIO(contenido)) as paquete:
        miembros = paquete.infolist()
        if sum(miembro.file_size for miembro in miembros) > 64 * 1024 * 1024:
            raise ExcelInvalido("La planilla contiene más datos de los que se pueden procesar.", 413)
        for miembro in miembros:
            nombre = miembro.filename.lower()
            if "vbaproject" in nombre or nombre.startswith("xl/macrosheets/"):
                raise ExcelInvalido("La planilla contiene macros.")
            if nombre.endswith((".xml", ".rels")):
                xml = paquete.read(miembro).replace(b"\x00", b"").lower()
                if b"<!doctype" in xml:
                    raise ExcelInvalido("La planilla contiene una declaración XML no admitida.")
                if nombre == "[content_types].xml" and b"macroenabled" in xml:
                    raise ExcelInvalido("La planilla contiene macros.")


def _leer(contenido, columnas, interpretar):
    try:
        _validar_paquete(contenido)
        wb = load_workbook(BytesIO(contenido), read_only=True, data_only=True, keep_links=False)
        try:
            filas = wb.worksheets[0].values
            encabezado = tuple(str(v or "").strip() for v in next(filas, ()))
            if encabezado[:len(columnas)] != columnas or any(encabezado[len(columnas):]):
                raise ExcelInvalido("El encabezado no coincide con la plantilla de importación.")
            resultado = []
            for numero, fila in enumerate(filas, 2):
                if not any(v is not None and v != "" for v in fila):
                    continue
                try:
                    if any(v is not None and v != "" for v in fila[len(columnas):]):
                        raise ValueError("Hay datos fuera de las columnas de la plantilla.")
                    valores = (*fila[:len(columnas)], *([None] * max(0, len(columnas) - len(fila))))
                    datos = interpretar(valores)
                except ValueError as error:
                    resultado.append({"numero": numero, "error": str(error)})
                else:
                    resultado.append({"numero": numero, "datos": datos})
            if not resultado:
                raise ExcelInvalido("La planilla no tiene filas para importar.")
            return resultado
        finally:
            wb.close()
    except ExcelInvalido:
        raise
    except (BadZipFile, InvalidFileException, OSError, SyntaxError, KeyError, IndexError, ValueError, RuntimeError) as error:
        raise ExcelInvalido("No se pudo leer la planilla .xlsx.") from error


def _texto(valor, nombre, limite, *, opcional=False):
    texto = str(valor).strip() if valor is not None else ""
    if "\x00" in texto or len(texto) > limite or (not opcional and not texto):
        raise ValueError(f"Revisá {nombre}.")
    return texto


def _decimal(valor, nombre):
    try:
        cantidad = Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Revisá {nombre}.") from error
    if not cantidad.is_finite():
        raise ValueError(f"Revisá {nombre}.")
    return cantidad


def _centavos(valor, minimo):
    if isinstance(valor, str):
        centavos = dinero.leer_pesos(valor)
    else:
        pesos = _decimal(valor, "el precio")
        if abs(pesos) >= Decimal(10**17):
            raise ValueError("El precio no cabe en el catálogo.")
        exacto = pesos * 100
        if exacto != exacto.to_integral_value():
            raise ValueError("El precio admite hasta dos decimales.")
        centavos = int(exacto)
    if not minimo <= centavos <= 2**63 - 1:
        raise ValueError("El precio no está dentro del rango admitido.")
    return centavos


def filas_items(db, empresa_id, contenido):
    apus = {fila["codigo"]: fila["id"] for fila in db.execute(
        "SELECT id,codigo FROM apus WHERE empresa_id=%s AND activo", (empresa_id,),
    )}

    def interpretar(fila):
        rubro, descripcion, unidad, cantidad, codigo_apu, precio = fila
        codigo = _texto(codigo_apu, "el código de APU", 80, opcional=True)
        if bool(codigo) == (precio is not None and str(precio).strip() != ""):
            raise ValueError("Indicá un código de APU o un precio unitario.")
        if codigo and codigo not in apus:
            raise ValueError("APU no encontrado.")
        cantidad = _decimal(cantidad, "la cantidad")
        if not 0 < cantidad < 10**10 or cantidad != cantidad.quantize(Decimal("0.0001")):
            raise ValueError("La cantidad debe ser positiva y tener hasta cuatro decimales.")
        return {"rubro": _texto(rubro, "el rubro", 120), "descripcion": _texto(descripcion, "la descripción", 240),
                "unidad": _texto(unidad, "la unidad", 40), "cantidad": cantidad,
                "apu_id": apus.get(codigo), "codigo_apu": codigo,
                "precio_unitario_centavos": None if codigo else _centavos(precio, 0), "origen_cantidad": "manual"}

    return _leer(contenido, COLUMNAS_ITEMS, interpretar)


def filas_precios(db, empresa_id, contenido):
    materiales = {fila["codigo"]: fila for fila in db.execute(
        "SELECT id,codigo,nombre FROM materiales WHERE empresa_id=%s AND activo", (empresa_id,),
    )}
    proveedores = db.execute(
        "SELECT id,nombre,cuit FROM proveedores WHERE empresa_id=%s AND activo", (empresa_id,),
    ).fetchall()

    def interpretar(fila):
        codigo, precio, vigencia, proveedor = fila
        material = materiales.get(_texto(codigo, "el código del material", 80))
        if material is None:
            raise ValueError("Material no encontrado.")
        proveedor = _texto(proveedor, "el proveedor", 240, opcional=True).casefold()
        ids = [p["id"] for p in proveedores
               if proveedor and proveedor in (p["nombre"].casefold(), p["cuit"].casefold())]
        if proveedor and len(ids) != 1:
            raise ValueError("El proveedor no existe o hay más de una coincidencia.")
        try:
            dia = vigencia.date() if isinstance(vigencia, datetime) else date.fromisoformat(str(vigencia))
        except ValueError as error:
            raise ValueError("Ingresá «Vigente desde» como fecha o AAAA-MM-DD.") from error
        return {"material_id": material["id"], "descripcion": material["nombre"],
                "precio_centavos": _centavos(precio, 1), "vigente_desde": datetime.combine(dia, time.min, TZ),
                "proveedor_id": ids[0] if ids else None, "proveedor": proveedor}

    return _leer(contenido, COLUMNAS_PRECIOS, interpretar)
