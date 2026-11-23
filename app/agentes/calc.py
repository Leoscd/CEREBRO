"""Calculadora decimal con una lista cerrada de nodos y operaciones."""

import ast
import operator
from decimal import Decimal, DecimalException, localcontext

_BINARIAS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CONSTANTES = {
    "pi": Decimal("3.141592653589793238462643383279502884197"),
    "e": Decimal("2.718281828459045235360287471352662497757"),
}


class ExpresionInvalida(ValueError):
    pass


def _acotar(numero):
    if not numero.is_finite() or abs(numero) > Decimal("1e40"):
        raise ExpresionInvalida("El resultado supera el rango de la calculadora.")
    return numero


def _binaria(op, izquierda, derecha):
    if op in _BINARIAS:
        return _BINARIAS[op](izquierda, derecha)
    if op is ast.Pow:
        if derecha != derecha.to_integral_value() or abs(derecha) > 64:
            raise ExpresionInvalida("El exponente debe ser un entero entre −64 y 64.")
        return izquierda ** int(derecha)
    if op in (ast.FloorDiv, ast.Mod):
        cociente, resto = divmod(izquierda, derecha)
        if resto and izquierda.is_signed() != derecha.is_signed():
            cociente -= 1
            resto += derecha
        return cociente if op is ast.FloorDiv else resto
    raise ExpresionInvalida("Operador no permitido.")


def _numero(nodo, expresion, variables):
    if isinstance(nodo, ast.Constant) and type(nodo.value) in (int, float):
        literal = ast.get_source_segment(expresion, nodo).replace("_", "")
        return _acotar(Decimal(literal))
    if isinstance(nodo, ast.Name) and nodo.id in variables:
        return _acotar(Decimal(str(variables[nodo.id])))
    if isinstance(nodo, ast.BinOp):
        izquierda = _numero(nodo.left, expresion, variables)
        derecha = _numero(nodo.right, expresion, variables)
        return _acotar(_binaria(type(nodo.op), izquierda, derecha))
    if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, (ast.UAdd, ast.USub)):
        valor = _numero(nodo.operand, expresion, variables)
        return -valor if isinstance(nodo.op, ast.USub) else valor
    raise ExpresionInvalida("La expresión contiene una constante, variable u operación no permitida.")


def safe_eval(expresion: str, variables: dict | None = None) -> Decimal:
    if not isinstance(expresion, str) or not expresion.strip() or len(expresion) > 320:
        raise ExpresionInvalida("Ingresá una expresión matemática de hasta 320 caracteres.")
    expresion = expresion.strip()
    try:
        arbol = ast.parse(expresion, mode="eval")
        if sum(1 for _ in ast.walk(arbol)) > 90:
            raise ExpresionInvalida("La expresión es demasiado larga.")
        with localcontext() as contexto:
            contexto.prec = 40
            contexto.Emax = 100
            contexto.Emin = -100
            return _numero(arbol.body, expresion, _CONSTANTES | (variables or {}))
    except (DecimalException, SyntaxError, RecursionError) as error:
        raise ExpresionInvalida("No se pudo calcular esa expresión.") from error
