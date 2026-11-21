---
id: T-005
titulo: Página del archivo con visor de PDF e imágenes
estado: lista
rama: codex/T-005-pagina-de-archivo-y-visor
creada: 2026-11-21
depende: T-004
pr:
---

## Objetivo
Abrir un archivo en una página de dos columnas redimensionables: el visor a la izquierda y, a la
derecha, el panel donde después va a vivir el agente (por ahora: datos y versiones).

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Visores" (archivo.html con dos columnas; PDF e imágenes primero).
- Router de archivos: `app/routers/archivos.py`. Base de plantillas: `app/templates/base.html`. Estilos: `app/static/style.css`.
- JS vanilla, sin bundler (como el resto del proyecto).

## Alcance
- Tocar: `app/routers/archivos.py`, `app/templates/archivo.html` (nuevo), `app/static/archivo.js` (nuevo),
  `app/static/vendor/pdfjs/` (nuevo), `app/static/style.css`, `app/templates/proyecto.html` (enlace al archivo), `tests/test_visor.py` (nuevo).
- No tocar: lógica de permisos.

## Diseño pedido
- `GET /archivos/{id}`: `obtener_archivo` → `archivo.html`.
- `GET /archivos/{id}/contenido`: versión actual **inline** con su mime y `X-Content-Type-Options: nosniff`.
  Solo inline para PDF y `image/png|jpeg|webp|gif`. **SVG, HTML y todo lo demás → attachment** (evita XSS desde archivos subidos).
- Visor PDF: **pdf.js** (Apache-2.0), versión fija, copiada en `app/static/vendor/pdfjs/` con su LICENSE (sin CDN).
  Navegación de páginas, zoom, y respeto de `#page=N` en la URL (lo van a usar las citas del RAG).
- Visor de imagen: `<img>` con zoom y arrastre en JS propio (sin dependencias).
- Otros tipos: tarjeta "Sin vista previa todavía" + botón Descargar.
- Columna derecha: nombre, carpeta, versión actual, historial con descarga, y un bloque vacío "Agente (próximamente)" con id `panel-agente`.
- Divisor arrastrable; el ancho se recuerda en `localStorage` (envuelto en try/catch). En pantallas angostas, columnas apiladas.

## Criterios de aceptación
- [ ] CA1 Ana abre un PDF de p1 → 200 y la página referencia el visor de pdf.js local (sin URLs externas en la plantilla).
- [ ] CA2 `/contenido` de un PDF → `Content-Disposition: inline` y `nosniff`; de un `.svg` o `.html` → `attachment`.
- [ ] CA3 `/archivos/{id}` y `/contenido` de un archivo ajeno → 404 (admin B; cliente sin `visible_cliente`).
- [ ] CA4 Probado a mano con el servidor de desarrollo (`python -m scripts.dev --puerto 8010`): PDF navega y salta a `#page=2`; imagen hace zoom; el divisor recuerda el ancho. Anotalo en la Bitácora.
- [ ] CA5 Sensores y suite en verde.

## Fuera de alcance
- DXF, IFC, 3D, ONLYOFFICE (tareas propias después de T-010). Anotaciones sobre el PDF.

## Bitácora del ejecutor

## Dictamen del auditor
