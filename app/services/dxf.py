"""Lectura de planos DXF y dibujo vectorial del espacio modelo."""
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory

from ezdxf import recover
from ezdxf.addons import acadctb
from ezdxf.addons.drawing import Frontend, RenderContext, layout
from ezdxf.addons.drawing.config import Configuration, ImagePolicy
from ezdxf.addons.drawing.svg import SVGBackend
from ezdxf.fonts import fonts
from PIL import ImageFont

from app import config


def leer(ruta: Path):
    if ruta.stat().st_size > config.DXF_MAX_MB * 1024**2:
        raise ValueError("El plano supera DXF_MAX_MB.")
    doc, _ = recover.readfile(ruta)
    return doc


def capas(doc):
    return [{"nombre": capa.dxf.name, "color": capa.color, "encendida": capa.is_on(),
             "congelada": capa.is_frozen()} for capa in doc.layers]


def textos(doc):
    for entidad in doc.modelspace():
        tipo = entidad.dxftype()
        if tipo == "INSERT":
            for atributo in entidad.attribs:
                if valor := atributo.plain_text().strip():
                    yield atributo.dxf.layer, valor
        elif tipo in ("TEXT", "MTEXT"):
            if valor := entidad.plain_text().strip():
                yield entidad.dxf.layer, valor


@cache
def _fuente_del_worker():
    # python:slim puede carecer de tipografías. Pillow incluye una fuente vectorial.
    nombre = fonts.font_manager.fallback_font_name()
    if fonts.font_manager.has_font(nombre):
        return None
    temporal = TemporaryDirectory(prefix="fuente-dxf-")
    (Path(temporal.name) / nombre).write_bytes(ImageFont.load_default().font_bytes)
    fonts.font_manager.build([temporal.name], support_dirs=False)
    return temporal  # mantiene la fuente disponible mientras viva el worker


def svg(doc) -> bytes:
    _fuente_del_worker()
    # Los estilos y los rásteres externos al archivo no forman parte del plano subido.
    contexto = RenderContext(doc, ctb=acadctb.new_ctb())
    backend = SVGBackend()
    Frontend(contexto, backend, config=Configuration(image_policy=ImagePolicy.IGNORE)).draw_layout(doc.modelspace())
    return backend.get_string(layout.Page(0, 0)).encode("utf-8")
