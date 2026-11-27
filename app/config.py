import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-inseguro-cambiame")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://gsp:gsp@localhost:5432/gsp")
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")

MARCA = os.getenv("MARCA", "Gestor de Proyectos")
URL_PUBLICA = os.getenv("URL_PUBLICA", "http://localhost:8000").rstrip("/")
TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")

SESSION_COOKIE = "gsp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 días
PRE2FA_COOKIE = "gsp_pre2fa"
PRE2FA_MAX_AGE = 5 * 60

# Si está en 1, un admin sin segundo factor es llevado a activarlo antes de seguir.
ADMIN_REQUIERE_2FA = os.getenv("ADMIN_REQUIERE_2FA", "0") == "1"
INVITACION_DIAS = int(os.getenv("INVITACION_DIAS", "14"))

# --- Email (invitaciones y "Olvidé mi contraseña") ---
# Sin SMTP_HOST no se envía nada: el email queda en data/correos/ y el panel muestra el link.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "Gestor de Proyectos <proyectos@example.com>")

ALMACEN_DIR = BASE_DIR / os.getenv("ALMACEN_DIR", "data/archivos")
ARCHIVO_MAX_MB = int(os.getenv("ARCHIVO_MAX_MB", "1024"))
GOTENBERG_URL = os.getenv("GOTENBERG_URL", "").strip().rstrip("/")
GOTENBERG_TIMEOUT = int(os.getenv("GOTENBERG_TIMEOUT", "60"))
GOTENBERG_PDF_MAX_MB = int(os.getenv("GOTENBERG_PDF_MAX_MB", "64"))
DXF_MAX_MB = int(os.getenv("DXF_MAX_MB", "50"))
IFC_MAX_MB = int(os.getenv("IFC_MAX_MB", "200"))
ONLYOFFICE_URL = os.getenv("ONLYOFFICE_URL", "").strip().rstrip("/")
ONLYOFFICE_JWT_SECRET = os.getenv("ONLYOFFICE_JWT_SECRET", "")
APP_URL_INTERNA = os.getenv("APP_URL_INTERNA", "http://app:8000").strip().rstrip("/")
ONLYOFFICE_URL_INTERNA = os.getenv("ONLYOFFICE_URL_INTERNA", "http://onlyoffice").strip().rstrip("/")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDINGS_PROVEEDOR = os.getenv("EMBEDDINGS_PROVEEDOR", "openai").strip().lower()
MODELO_EMBEDDINGS = os.getenv("MODELO_EMBEDDINGS", "").strip()
EMBEDDINGS_DIMENSIONES = int(os.getenv("EMBEDDINGS_DIMENSIONES", "384"))
AGENTES_PROVEEDOR = os.getenv("AGENTES_PROVEEDOR", "openai").strip().lower()
MODELO_DOCUMENTADOR = os.getenv("MODELO_DOCUMENTADOR", "").strip()
MODELO_PRESUPUESTOS = os.getenv("MODELO_PRESUPUESTOS", "").strip()
MODELO_OBRA = os.getenv("MODELO_OBRA", "").strip()
OBRA_CONSULTAS_POR_HORA = int(os.getenv("OBRA_CONSULTAS_POR_HORA", "20"))
TRANSCRIPCION_PROVEEDOR = os.getenv("TRANSCRIPCION_PROVEEDOR", "openai").strip().lower()
MODELO_TRANSCRIPCION = os.getenv("MODELO_TRANSCRIPCION", "").strip()
MARGEN_PEDIDO_DIAS = int(os.getenv("MARGEN_PEDIDO_DIAS", "2"))
PRESUPUESTOS_MAX_RONDAS = int(os.getenv("PRESUPUESTOS_MAX_RONDAS", "8"))
PRESUPUESTOS_CONSULTAS_POR_HORA = int(os.getenv("PRESUPUESTOS_CONSULTAS_POR_HORA", "20"))
