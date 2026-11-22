from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.db import abrir_pool, cerrar_pool
from app.routers import admin, agentes, archivos, auth, busqueda, inicio, proyectos


@asynccontextmanager
async def lifespan(app: FastAPI):
    abrir_pool()
    yield
    cerrar_pool()


# Sin /docs ni /openapi.json: no hace falta publicar el mapa de rutas.
app = FastAPI(
    title="Gestor de proyectos", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

app.include_router(auth.router)
app.include_router(inicio.router)
app.include_router(proyectos.router)
app.include_router(busqueda.router)
app.include_router(archivos.router)
app.include_router(admin.router)
app.include_router(agentes.router)


@app.exception_handler(HTTPException)
async def errores_html(request: Request, exc: HTTPException):
    """Redirecciones tal cual; los errores para personas, como página simple."""
    if exc.status_code in (301, 302, 303, 307, 308):
        from fastapi.responses import Response

        return Response(status_code=exc.status_code, headers=exc.headers)
    if request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-csrf"):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
    from app.templates import templates

    return templates.TemplateResponse(
        request,
        "error.html",
        {"codigo": exc.status_code, "mensaje": exc.detail, "user": None},
        status_code=exc.status_code,
    )


@app.get("/salud", response_class=HTMLResponse)
def salud():
    from app.db import pool

    with pool().connection() as c:
        c.execute("SELECT 1")
    return "ok"
