import re
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.services import excel, precios, presupuestos
from app.services.tiempo import TZ
from tests import test_presupuestos
from tests.conftest import csrf_de
from tests.test_apus import material

presupuesto_muestra = test_presupuestos.presupuesto_muestra


def _xlsx(encabezado, *filas):
    wb = Workbook()
    wb.active.append(encabezado)
    for fila in filas:
        wb.active.append(fila)
    archivo = BytesIO()
    wb.save(archivo)
    return archivo.getvalue()


def _confirmacion(respuesta):
    return re.search(r'name="confirmacion" value="([^"]+)"', respuesta.text)[1]


def test_exportar_excel_reproduce_valores_y_formulas(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    respuesta = como(mundo["admin_a"]["email"]).get(f"/presupuestos/{p['id']}.xlsx")
    assert respuesta.status_code == 200 and "attachment" in respuesta.headers["content-disposition"]
    assert como(mundo["cliente"]["email"]).get(f"/presupuestos/{p['id']}.xlsx").status_code == 404
    wb = load_workbook(BytesIO(respuesta.content), read_only=True, data_only=False)
    assert wb.sheetnames == ["Presupuesto", "Datos"]
    resultado = presupuestos.calcular(db, p["empresa_id"], p["id"])
    datos = dict(wb["Datos"].iter_rows(min_row=2, max_row=6, max_col=2, values_only=True))
    assert datos == {campo: resultado[campo] for campo in (
        "costo_directo_centavos", "gastos_generales_centavos", "beneficio_centavos", "impuestos_centavos",
        "total_centavos",
    )}
    hoja = wb["Presupuesto"]
    assert "[$-2C0A]" in hoja["E4"].number_format
    assert hoja["F4"].value == '=IF(ISNUMBER(E4),ROUND(D4*E4,2),"")'
    assert hoja["F3"].value == "=ROUND(SUM(F4:F6),2)"
    assert hoja["F7"].value == "=ROUND(SUM(F8:F9),2)"
    assert hoja["F10"].value == '=ROUND(SUMIF(A3:A9,"Rubro",F3:F9),2)'
    assert hoja["F11"].value == "=ROUND(F10*E11,2)"
    assert hoja["F12"].value == "=ROUND(SUM(F10:F11)*E12,2)"
    assert hoja["F13"].value == "=ROUND(SUM(F10:F12)*E13,2)"
    assert hoja["F14"].value == "=ROUND(SUM(F10:F13),2)"
    wb.close()


def test_importar_items_tiene_vista_previa_y_confirma_en_bloque(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    csrf = csrf_de(admin)
    base = f"/presupuestos/{p['id']}/excel"
    entrada = ("Otro rubro", "Mortero", "m2", "1,2500", "", "2,10")
    error = ("Otro rubro", "Carpeta", "m2", "0,10", "APU-AJENO", "")
    antes = db.execute("SELECT count(*) AS n FROM items_presupuesto WHERE presupuesto_id=%s", (p["id"],)).fetchone()["n"]
    plantilla = cliente.get(f"{base}/plantilla.xlsx")
    assert plantilla.status_code == 200
    primera = cliente.post(f"{base}/vista-previa", data={"csrf": csrf}, files={
        "archivo": ("items.xlsx", _xlsx(excel.COLUMNAS_ITEMS, entrada, error)),
    })
    assert primera.status_code == 200 and "Fila 3" in primera.text and "APU no encontrado" in primera.text
    assert 'name="confirmacion"' not in primera.text
    assert db.execute("SELECT count(*) AS n FROM items_presupuesto WHERE presupuesto_id=%s", (p["id"],)).fetchone()["n"] == antes
    segunda = cliente.post(f"{base}/vista-previa", data={"csrf": csrf}, files={
        "archivo": ("items.xlsx", _xlsx(excel.COLUMNAS_ITEMS, entrada, ("Otro rubro", "Carpeta", "m2", "0,10", "BASE-01", ""))),
    })
    assert segunda.status_code == 200
    assert db.execute("SELECT count(*) AS n FROM items_presupuesto WHERE presupuesto_id=%s", (p["id"],)).fetchone()["n"] == antes
    assert cliente.post(f"{base}/confirmar", data={"csrf": csrf, "confirmacion": _confirmacion(segunda)}).status_code == 303
    assert db.execute("SELECT count(*) AS n FROM items_presupuesto WHERE presupuesto_id=%s", (p["id"],)).fetchone()["n"] == antes + 2


def test_importar_precios_agrega_y_aisla(db, mundo, como):
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    csrf = csrf_de(admin)
    propio = material(db, admin["empresa_id"], "PROPIO")
    ajeno = material(db, mundo["eb"]["id"], "AJENO")
    precios.cargar(db, admin, propio, 100, datetime(2026, 1, 1, tzinfo=TZ))
    db.commit()
    filas = [("PROPIO", "$ 2,50", "2026-02-01", ""), ("AJENO", "6,00", "2026-02-01", "")]
    ruta = "/precios/excel"
    previo = cliente.post(f"{ruta}/vista-previa", data={"csrf": csrf}, files={
        "archivo": ("precios.xlsx", _xlsx(excel.COLUMNAS_PRECIOS, *filas)),
    })
    assert "Fila 3" in previo.text and "Material no encontrado" in previo.text
    assert 'name="confirmacion"' not in previo.text
    previo = cliente.post(f"{ruta}/vista-previa", data={"csrf": csrf}, files={
        "archivo": ("precios.xlsx", _xlsx(excel.COLUMNAS_PRECIOS, filas[0])),
    })
    confirmacion = _confirmacion(previo)
    otro = mundo["admin_b"]
    assert como(otro["email"]).post(f"{ruta}/confirmar", data={
        "csrf": csrf_de(otro), "confirmacion": confirmacion,
    }).status_code == 400
    assert cliente.post(f"{ruta}/confirmar", data={"csrf": csrf, "confirmacion": confirmacion}).status_code == 303
    historial = db.execute(
        "SELECT material_id,precio_centavos,fuente FROM precios WHERE material_id IN (%s,%s) ORDER BY id",
        (propio, ajeno),
    ).fetchall()
    assert [(h["material_id"], h["precio_centavos"], h["fuente"]) for h in historial] == [
        (propio, 100, "manual"), (propio, 250, "excel"),
    ]


def test_archivos_invalidos_no_escriben(db, mundo, como, presupuesto_muestra):
    p = presupuesto_muestra
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    for nombre, contenido, esperado in [
        ("macros.xlsm", b"abc", 400), ("dañado.xlsx", b"abc", 400),
        ("grande.xlsx", b"a" * (10 * 1024 * 1024 + 1), 413),
    ]:
        respuesta = cliente.post(f"/presupuestos/{p['id']}/excel/vista-previa",
                                 data={"csrf": csrf_de(admin)}, files={"archivo": (nombre, contenido)})
        assert respuesta.status_code == esperado
    n = db.execute("SELECT count(*) AS n FROM items_presupuesto WHERE presupuesto_id=%s", (p["id"],)).fetchone()["n"]
    assert n == 5
