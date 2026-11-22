---
id: T-005
titulo: Página del archivo con visor de PDF e imágenes
estado: en-revision
rama: codex/T-005-pagina-de-archivo-y-visor
creada: 2026-11-21
depende: T-004
pr: "#6"
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
- [x] CA1 Ana abre un PDF de p1 → 200 y la página referencia el visor de pdf.js local (sin URLs externas en la plantilla).
- [x] CA2 `/contenido` de un PDF → `Content-Disposition: inline` y `nosniff`; de un `.svg` o `.html` → `attachment`.
- [x] CA3 `/archivos/{id}` y `/contenido` de un archivo ajeno → 404 (admin B; cliente sin `visible_cliente`).
- [x] CA4 Probado a mano con el servidor de desarrollo (`python -m scripts.dev --puerto 8010`): PDF navega y salta a `#page=2`; imagen hace zoom; el divisor recuerda el ancho. Anotalo en la Bitácora.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- DXF, IFC, 3D, ONLYOFFICE (tareas propias después de T-010). Anotaciones sobre el PDF.

## Bitácora del ejecutor
- Se fijó PDF.js 6.5.438 y se copiaron los módulos, recursos y licencias del paquete oficial de Mozilla. El visor se sirve desde el proyecto.
- La vista previa exige que el MIME admitido coincida con la firma del archivo. HTML y SVG se sirven como adjuntos; las respuestas de archivos incluyen nosniff.
- Verificación funcional con Chromium contra `python -m scripts.dev --puerto 8010`, con archivos de prueba. Un PDF real de dos páginas abrió en `#page=2` y navegó y amplió correctamente. El PNG amplió y se desplazó, el divisor retuvo el ancho tras recargar y la vista angosta apiló las columnas.
- Los tres casos HTTP fallaron antes del cambio. Pasaron 48 pruebas y el sensor rápido terminó sin salida.

## Dictamen del auditor
