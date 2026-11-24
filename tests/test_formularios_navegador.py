from html.parser import HTMLParser

from tests import test_presupuestos
from tests.test_apus import material

presupuesto_muestra = test_presupuestos.presupuesto_muestra


class _ValoresFormulario(HTMLParser):
    def __init__(self, pagina, destino):
        super().__init__()
        self.pagina, self.destino = pagina, destino
        self.en_formulario = False
        self.select = None
        self.campos = {}

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "form":
            self.en_formulario = atributos.get("method") == "post" and (atributos.get("action") or self.pagina) == self.destino
        if not self.en_formulario or "disabled" in atributos:
            return
        nombre = atributos.get("name")
        if tag == "input" and nombre:
            if atributos.get("type") not in {"submit", "file", "checkbox", "radio", "button"} or "checked" in atributos:
                self.campos[nombre] = atributos.get("value", "")
        elif tag == "select" and nombre:
            self.select = nombre
        elif tag == "option" and self.select and (self.select not in self.campos or "selected" in atributos):
            self.campos[self.select] = atributos["value"]

    def handle_endtag(self, tag):
        if tag == "form":
            self.en_formulario = False
        elif tag == "select":
            self.select = None


def formulario(cliente, pagina, destino=None, **llenar):
    respuesta = cliente.get(pagina)
    assert respuesta.status_code == 200
    parser = _ValoresFormulario(pagina, destino or pagina)
    parser.feed(respuesta.text)
    assert "csrf" in parser.campos and llenar.keys() <= parser.campos.keys()
    return parser.campos | llenar


def test_precio_con_formulario_de_navegador_y_proveedor_opcional(db, mundo, como):
    admin = mundo["admin_a"]
    cliente = como(admin["email"])
    mid = material(db, admin["empresa_id"], "Precio de prueba")
    ajeno = db.execute("INSERT INTO proveedores(empresa_id,nombre) VALUES (%s,'Proveedor de B') RETURNING id",
                       (mundo["eb"]["id"],)).fetchone()["id"]
    db.commit()
    pagina = f"/precios/materiales/{mid}"
    destino = f"{pagina}/precios"
    campos = formulario(cliente, pagina, destino, precio="123,45", vigente_desde="2026-01-10")
    assert campos["proveedor_id"] == ""
    assert cliente.post(destino, data=campos).status_code == 303
    fila = db.execute("SELECT precio_centavos,proveedor_id FROM precios WHERE material_id=%s", (mid,)).fetchone()
    assert fila == {"precio_centavos": 12345, "proveedor_id": None}
    invalido = cliente.post(destino, data=campos | {"proveedor_id": "abc"})
    assert invalido.status_code == 400 and "identificador válido para el proveedor" in invalido.text
    assert cliente.post(destino, data=campos | {"proveedor_id": str(ajeno)}).status_code == 404


def test_item_manual_y_gasto_con_todos_los_campos_del_navegador(db, mundo, como, presupuesto_muestra):
    cliente = como(mundo["admin_a"]["email"])
    pid = presupuesto_muestra["id"]
    pagina = f"/presupuestos/{pid}"
    destino = f"{pagina}/items"
    item = formulario(cliente, pagina, destino, descripcion="Tirante manual", unidad="u", cantidad="2", precio="15,00")
    assert item["apu_id"] == ""
    assert cliente.post(destino, data=item).status_code == 303
    fila = db.execute("SELECT apu_id,precio_unitario_centavos FROM items_presupuesto WHERE descripcion='Tirante manual'").fetchone()
    assert fila == {"apu_id": None, "precio_unitario_centavos": 1500}
    invalido = cliente.post(destino, data=item | {"apu_id": "abc"})
    assert invalido.status_code == 400 and "identificador válido para el APU" in invalido.text
    ruta = f"/proyecto/{mundo['p1']['codigo']}/gastos"
    gasto = formulario(cliente, ruta, descripcion="Gasto manual", importe="2,50")
    assert gasto["proveedor_id"] == gasto["archivo_id"] == ""
    assert cliente.post(ruta, data=gasto).status_code == 303
    fila = db.execute("SELECT proveedor_id,archivo_id,importe_centavos FROM gastos WHERE descripcion='Gasto manual'").fetchone()
    assert fila == {"proveedor_id": None, "archivo_id": None, "importe_centavos": 250}
    invalido = cliente.post(ruta, data=gasto | {"archivo_id": "abc"})
    assert invalido.status_code == 400 and "identificador válido para el comprobante" in invalido.text
