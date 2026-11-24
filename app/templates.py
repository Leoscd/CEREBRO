from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import config
from app.security import csrf_token
from app.services import dinero
from app.services.tiempo import formatear

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _static_version() -> str:
    """Sella los assets con su fecha de modificación para que el navegador no use el CSS viejo."""
    css = BASE_DIR / "static" / "style.css"
    return str(int(css.stat().st_mtime)) if css.exists() else "0"


_SEPARADORES = str.maketrans(",.", ".,")


def _porcentaje(pb: int, unidad: bool = True) -> str:
    valor = Decimal(pb).scaleb(-2)
    if unidad:
        return f"{valor:,.2f}".translate(_SEPARADORES) + " %"
    return f"{valor:.2f}".replace(".", ",")


def _cantidad(valor: Decimal, agrupar: bool = True) -> str:
    texto = format(valor, ",f" if agrupar else "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.translate(_SEPARADORES)


templates.env.globals["static_version"] = _static_version()
templates.env.globals["marca"] = config.MARCA
templates.env.globals["csrf_token"] = csrf_token
templates.env.filters["fecha"] = formatear
templates.env.filters["solo_fecha"] = lambda v: formatear(v, con_hora=False)
templates.env.filters["pesos"] = dinero.formatear
templates.env.filters["porcentaje"] = _porcentaje
templates.env.filters["cantidad"] = _cantidad

ETAPAS = {
    "anteproyecto": "Anteproyecto",
    "proyecto": "Proyecto",
    "documentacion": "Documentación",
    "licitacion": "Licitación",
    "ejecucion": "En ejecución",
    "entrega": "Entrega",
}
ESTADOS = {"activo": "Activo", "pausado": "Pausado", "finalizado": "Finalizado"}
ROLES_PROYECTO = {
    "director": "Director/a",
    "colaborador": "Colaborador/a",
    "dt": "Dirección técnica",
    "administracion": "Administración",
    "lector": "Solo lectura",
}
ROLES_EMPRESA = {"admin": "Administrador/a", "miembro": "Equipo", "cliente": "Cliente"}

templates.env.globals.update(
    ETAPAS=ETAPAS, ESTADOS=ESTADOS, ROLES_PROYECTO=ROLES_PROYECTO, ROLES_EMPRESA=ROLES_EMPRESA
)
