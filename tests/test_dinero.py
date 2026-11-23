import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import dinero
from app.templates import templates


@pytest.mark.parametrize(("entrada", "centavos", "salida"), [
    ("1.234,56", 123456, "$ 1.234,56"),
    ("  -$ 1.234,56  ", -123456, "-$ 1.234,56"),
    ("$ -1,2", -120, "-$ 1,20"),
    ("+1234567", 123456700, "$ 1.234.567,00"),
    ("0", 0, "$ 0,00"),
    ("0,05", 5, "$ 0,05"),
])
def test_pesos_ida_y_vuelta(entrada, centavos, salida):
    assert dinero.leer_pesos(entrada) == centavos
    assert dinero.formatear(centavos) == salida
    assert dinero.leer_pesos(salida) == centavos
    assert templates.env.from_string("{{ valor | pesos }}").render(valor=centavos) == salida


@pytest.mark.parametrize(("centavos", "cantidad", "resultado"), [
    (125, "0.5000", 63),
    (-125, "0.5000", -63),
    (1, "0.4999", 0),
    (875, "0.1234", 108),
    (9999, "1.2500", 12499),
])
def test_multiplicar_redondea_half_up(centavos, cantidad, resultado):
    assert dinero.multiplicar(centavos, Decimal(cantidad)) == resultado


def test_coeficiente_y_suma():
    assert dinero.aplicar_coeficiente(10, 1500) == 2
    assert dinero.aplicar_coeficiente(-10, 1500) == -2
    assert dinero.sumar(iter((999, -2, 3))) == 1000


@pytest.mark.parametrize("entrada", ["1,234.56", "12,345", "", "abc", "1.23", "$$ 1", "1,", "--1"])
def test_pesos_invalidos(entrada):
    with pytest.raises(ValueError, match="Importe inválido"):
        dinero.leer_pesos(entrada)


def test_dinero_sin_float():
    arbol = ast.parse(Path(dinero.__file__).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            assert nodo.id != "float"
        if isinstance(nodo, ast.Constant):
            assert not isinstance(nodo.value, float)
        if isinstance(nodo, ast.alias):
            assert nodo.name != "float" and nodo.asname != "float"
