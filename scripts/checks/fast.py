"""Sensores rápidos y deterministas del harness (segundos, sin base de datos).

Uso: python -m scripts.checks.fast
- Éxito: no imprime nada y sale con 0 (no gasta contexto del agente).
- Falla: imprime cada problema con QUÉ pasó, DÓNDE y CÓMO arreglarlo, y sale con 1.

Cada sensor tiene un origen en harness/log.md (principio del trinquete). Si un sensor
ya no aporta (el modelo lo resuelve solo), se poda ahí, no se desactiva en silencio.
"""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CHECKS = Path(__file__).resolve().parent
MIGRACIONES = RAIZ / "app" / "db" / "migraciones"
LOCK_MIGRACIONES = CHECKS / "migraciones.lock"
POST_SIN_CSRF = CHECKS / "post_sin_csrf.txt"
CARPETAS_PY = ("app", "scripts", "tests")


class Falla:
    def __init__(self, regla: str, donde: str, que: str, como: str):
        self.regla, self.donde, self.que, self.como = regla, donde, que, como

    def __str__(self) -> str:
        return f"FALLA [{self.regla}] {self.donde}\n  Qué:  {self.que}\n  Cómo: {self.como}"


def _rel(p: Path) -> str:
    return p.relative_to(RAIZ).as_posix()


def _py(carpetas=CARPETAS_PY):
    for c in carpetas:
        yield from sorted((RAIZ / c).rglob("*.py"))


# ---------- 1. sintaxis + lint mínimo ----------

def sensor_sintaxis() -> list[Falla]:
    fallas = []
    for f in _py():
        try:
            ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as e:
            fallas.append(Falla("sintaxis", f"{_rel(f)}:{e.lineno}", str(e.msg), "Corregí la sintaxis."))
    return fallas


def sensor_ruff() -> list[Falla]:
    reglas = "E9,F63,F7,F82,F401,F811,F841"
    cmd = [sys.executable, "-m", "ruff", "check", "--quiet", "--select", reglas,
           "--output-format", "concise", *CARPETAS_PY]
    try:
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        r = None
    if r is None or "No module named ruff" in (r.stderr or ""):
        return [Falla("ruff", "entorno", "ruff no está instalado.",
                      "pip install -r requirements-dev.txt")]
    if r.returncode == 0:
        return []
    return [Falla("ruff", linea.split(" ")[0].rstrip(":"), linea, "Arreglalo o corré `python -m ruff check --fix`.")
            for linea in r.stdout.strip().splitlines() if linea.strip() and not linea.startswith("Found")]


# ---------- 2. migraciones: selladas = intocables, nuevas = numeradas ----------

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def leer_lock() -> dict[str, str]:
    if not LOCK_MIGRACIONES.exists():
        return {}
    sellos = {}
    for linea in LOCK_MIGRACIONES.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            nombre, sha = linea.split()
            sellos[nombre] = sha
    return sellos


def sensor_migraciones() -> list[Falla]:
    fallas = []
    sellos = leer_lock()
    archivos = sorted(MIGRACIONES.glob("*.sql"))
    nombres = {a.name for a in archivos}
    for nombre, sha in sellos.items():
        f = MIGRACIONES / nombre
        if nombre not in nombres:
            fallas.append(Falla("migracion-sellada", _rel(f), "Se borró o renombró una migración ya aplicada.",
                                "Restaurala. Para deshacer algo, agregá una migración nueva."))
        elif _sha(f) != sha:
            fallas.append(Falla("migracion-sellada", _rel(f), "Se editó una migración ya aplicada.",
                                "Volvé el archivo atrás (git checkout) y poné el cambio en una migración NUEVA "
                                "con el número siguiente."))
    esperado = 1
    for a in archivos:
        m = re.fullmatch(r"(\d{4})_[a-z0-9_]+\.sql", a.name)
        if not m:
            fallas.append(Falla("migracion-nombre", _rel(a), "Nombre inválido.",
                                "Usá NNNN_descripcion_en_minusculas.sql (ej. 0002_archivos.sql)."))
            continue
        if int(m.group(1)) != esperado:
            fallas.append(Falla("migracion-numero", _rel(a), f"Se esperaba el número {esperado:04d}.",
                                "Numerá las migraciones de forma consecutiva, sin saltos ni repetidos."))
        esperado = int(m.group(1)) + 1
    return fallas


# ---------- 3. reglas de dominio en SQL: dinero en centavos, fechas con zona ----------

_DINERO = re.compile(r"^\s*(\w*(monto|precio|importe|costo|total|saldo|honorario)\w*)\s+"
                     r"(numeric|decimal|real|double|float|money|int\b|integer)", re.I)
_TIMESTAMP = re.compile(r"\btimestamp\b(?!tz)(?!\s+with\s+time\s+zone)", re.I)


def sensor_sql_dominio() -> list[Falla]:
    fallas = []
    for a in sorted(MIGRACIONES.glob("*.sql")):
        for n, linea in enumerate(a.read_text(encoding="utf-8").splitlines(), 1):
            codigo = linea.split("--", 1)[0]
            m = _DINERO.search(codigo)
            if m and not m.group(1).lower().endswith("_centavos"):
                fallas.append(Falla("dinero", f"{_rel(a)}:{n}", f"Columna de dinero `{m.group(1)}` no es *_centavos.",
                                    "Guardá dinero como `<nombre>_centavos bigint`."))
            if _TIMESTAMP.search(codigo):
                fallas.append(Falla("fecha", f"{_rel(a)}:{n}", "timestamp sin zona horaria.",
                                    "Usá `timestamptz` (UTC); se muestra con los filtros fecha/solo_fecha."))
    return fallas


# ---------- 4. IA: solo OpenAI y modelos desde .env ----------

_MODELO_FIJO = re.compile(r"""["'](gpt-[\w.\-]+|chatgpt-[\w.\-]+|o[1-9](-mini|-pro)?|text-embedding-[\w\-]+|"""
                          r"""codex-[\w.\-]+)["']""")
_OTRO_PROVEEDOR = re.compile(r"^\s*(import|from)\s+(anthropic|google\.generativeai|google\.genai|mistralai|"
                             r"cohere|ollama|langchain_anthropic)\b")


def sensor_ia() -> list[Falla]:
    fallas = []
    for f in _py(("app",)):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _OTRO_PROVEEDOR.search(linea):
                fallas.append(Falla("solo-openai", f"{_rel(f)}:{n}", "Se importa un proveedor de IA que no es OpenAI.",
                                    "El proyecto usa solo OpenAI. Quitá esa dependencia."))
            m = _MODELO_FIJO.search(linea.split("#", 1)[0])
            if m:
                fallas.append(Falla("modelo-fijo", f"{_rel(f)}:{n}", f"Modelo fijo en el código: {m.group(0)}.",
                                    "Leé el modelo de una variable en `.env` vía app/config.py y "
                                    "documentala en .env.example."))
    return fallas


# ---------- 5. rutas: CSRF en todo POST y nada de empresa_id del pedido ----------

_METODOS_ESCRITURA = {"post", "put", "patch", "delete"}


def _depends(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    nombres = set()
    for d in [*fn.args.defaults, *fn.args.kw_defaults]:
        if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "Depends" and d.args:
            a = d.args[0]
            nombres.add(a.id if isinstance(a, ast.Name) else getattr(a, "attr", ""))
    return nombres


def _es_ruta_escritura(fn) -> bool:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in _METODOS_ESCRITURA:
            return True
    return False


def _es_ruta(fn) -> bool:
    return any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
               and d.func.attr in _METODOS_ESCRITURA | {"get"} for d in fn.decorator_list)


def _excepciones_csrf() -> set[str]:
    if not POST_SIN_CSRF.exists():
        return set()
    return {ln.split("#", 1)[0].strip() for ln in POST_SIN_CSRF.read_text(encoding="utf-8").splitlines()
            if ln.split("#", 1)[0].strip()}


def _form_opcionales(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Parámetros `X | None = Form(...)` u `Optional[X] = Form(...)` con X distinto de str (H-013)."""
    nombres = []
    argumentos = [*fn.args.args, *fn.args.kwonlyargs]
    defaults = [None] * (len(fn.args.args) - len(fn.args.defaults)) + [*fn.args.defaults, *fn.args.kw_defaults]
    def tipos(nodo) -> list[ast.AST]:
        if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.BitOr):
            return tipos(nodo.left) + tipos(nodo.right)
        if isinstance(nodo, ast.Subscript) and getattr(nodo.value, "id", None) == "Optional":
            return [nodo.slice, ast.Constant(None)]
        return [nodo]

    def es_none(nodo) -> bool:
        return isinstance(nodo, ast.Constant) and nodo.value is None or getattr(nodo, "id", None) == "None"

    for arg, default in zip(argumentos, defaults, strict=False):
        es_form = isinstance(default, ast.Call) and getattr(default.func, "id", None) == "Form"
        if not es_form or arg.annotation is None:
            continue
        partes = tipos(arg.annotation)
        if any(es_none(p) for p in partes) and any(not es_none(p) and getattr(p, "id", None) != "str" for p in partes):
            nombres.append(arg.arg)
    return nombres


def _llama_csrf(fn: ast.FunctionDef | ast.AsyncFunctionDef, nombres: set[str]) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in nombres:
                return True
            if (isinstance(f, ast.Attribute) and f.attr == "check_csrf"
                    and isinstance(f.value, ast.Name) and f.value.id == "security"):
                return True
    return False


def _dependencias_csrf(arbol: ast.Module, funcs: list) -> set[str]:
    """Nombres que de verdad exigen CSRF (H-008: no alcanza con llamarse `check_csrf`).

    Vale el `check_csrf` importado de `app.security` y toda función del archivo que dependa de él
    (`Depends`) o lo llame (`check_csrf(...)`, `security.check_csrf(...)`). Una función local con ese
    nombre que no hace nada de eso no cuenta.
    """
    importados = {a.asname or a.name for n in ast.walk(arbol)
                  if isinstance(n, ast.ImportFrom) and n.module == "app.security"
                  for a in n.names if a.name == "check_csrf"}
    locales = {fn.name: fn for fn in funcs}
    con = {nombre for nombre in importados if nombre not in locales}
    cambio = True
    while cambio:
        cambio = False
        for nombre, fn in locales.items():
            if nombre not in con and ((_depends(fn) & con) or _llama_csrf(fn, con)):
                con.add(nombre)
                cambio = True
    return con


def sensor_rutas() -> list[Falla]:
    fallas = []
    excepciones = _excepciones_csrf()
    for f in sorted((RAIZ / "app" / "routers").glob("*.py")):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        con_csrf = _dependencias_csrf(arbol, funcs)
        for fn in funcs:
            donde = f"{_rel(f)}:{fn.lineno} {fn.name}"
            if _es_ruta(fn):
                params = [a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]]
                if "empresa_id" in params:
                    fallas.append(Falla("aislamiento", donde, "La ruta recibe `empresa_id` del pedido.",
                                        "Tomá la empresa de la sesión (`user['empresa_id']`) y validá el proyecto "
                                        "con app/permisos.py (obtener_proyecto)."))
                for nombre in _form_opcionales(fn):
                    fallas.append(Falla("form-opcional", f"{donde} ({nombre})",
                                        "Campo de formulario opcional tipado (`X | None = Form(...)`): un <select> con "
                                        "opción vacía manda \"\" y FastAPI responde 422 crudo (H-013).",
                                        "Recibilo como `str = Form(\"\")` y convertilo con app/formularios.py "
                                        "(`id_opcional`, `porcentaje_a_pb`)."))
            if _es_ruta_escritura(fn) and not (_depends(fn) & con_csrf) and f"{f.name}:{fn.name}" not in excepciones:
                fallas.append(Falla("csrf", donde, "Ruta de escritura sin CSRF.",
                                    "Agregá `user=Depends(check_csrf)` (o `_admin_csrf`). Si es una ruta pública "
                                    "previa a la sesión, pedile a un humano que la sume a "
                                    "scripts/checks/post_sin_csrf.txt."))
        texto = f.read_text(encoding="utf-8")
        for n, linea in enumerate(texto.splitlines(), 1):
            if re.search(r"""(form|query_params|json)\w*\.get\(\s*["']empresa_id["']""", linea):
                fallas.append(Falla("aislamiento", f"{_rel(f)}:{n}", "Se lee `empresa_id` del pedido.",
                                    "Usá la empresa de la sesión, nunca la del formulario o la URL."))
    return fallas


SENSORES = [sensor_sintaxis, sensor_ruff, sensor_migraciones, sensor_sql_dominio, sensor_ia, sensor_rutas]


def correr() -> list[Falla]:
    fallas: list[Falla] = []
    for s in SENSORES:
        fallas.extend(s())
    return fallas


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fallas = correr()
    if not fallas:
        return 0
    print(f"{len(fallas)} problema(s) encontrados por los sensores rápidos:\n")
    print("\n\n".join(str(f) for f in fallas))
    return 1


if __name__ == "__main__":
    sys.exit(main())
