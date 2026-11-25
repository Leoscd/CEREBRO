---
id: T-038
titulo: DXF en el servidor y vista SVG
estado: lista
rama: codex/T-038-dxf-en-el-servidor-y-vista-svg
creada: 2026-11-25
depende: T-037
pr:
---

## Objetivo
Al abrir un DXF se ve el plano (zoom y paneo, como una imagen), al lado se listan sus capas, y los textos del plano entran
en la búsqueda y en el Documentador. Todo se procesa en el servidor con ezdxf; no se suma JS de terceros.

## Contexto mínimo
- Decisión de Leo (2026-11-25): v1 **sin bundle**. El DXF se dibuja en el servidor a SVG; `cad-viewer` queda para más adelante.
- Plan: `docs/PLAN.md` → "Visores", fila DXF (ezdxf en el servidor para capas y textos).
- Convención de derivados y estados: ver T-037 ("Convención de derivados"). Esta tarea agrega el derivado `svg` y `derivados.meta.dxf`.
- Visor de imágenes existente: `archivo.html` bloque `tipo == 'imagen'` y `app/static/archivo.js`.
- Chunks: tabla `chunks` (`app/db/migraciones/0004_rag.sql`): `pagina` es NOT NULL ≥ 1 → usá `pagina=1`.

## Alcance
- Tocar: `requirements.txt` (`ezdxf`, versión fija, la última 1.x de PyPI), `app/services/dxf.py` (nuevo), `app/worker.py`,
  `app/routers/archivos.py`, `app/templates/archivo.html`, `app/config.py` y `.env.example` (`DXF_MAX_MB`),
  `tests/test_dxf.py` (nuevo).
- No tocar: `app/static/vendor/**`, migraciones, `app/permisos.py`.

## Diseño pedido
- Al crear una versión con extensión `dxf`: encolá `archivo.dxf` y `derivados.vista="pendiente"`.
- `app/services/dxf.py`:
  - `leer(ruta)` con `ezdxf.recover.readfile` (tolera archivos con errores). Más grande que `DXF_MAX_MB` (por defecto 50) → no se procesa.
  - `capas(doc)` → lista de `{nombre, color, encendida, congelada}`.
  - `textos(doc)` → textos de `TEXT`, `MTEXT` (`plain_text()`) y atributos de bloques en el espacio modelo, con su capa.
  - `svg(doc) -> bytes` con `ezdxf.addons.drawing` (`Frontend` + `SVGBackend`, sin matplotlib), página automática.
- Job `archivo.dxf`: guarda el SVG en el almacén (`derivados.svg`), `derivados.meta.dxf = {capas, cantidad_textos}`, inserta chunks
  ("Capa X: texto", agrupados con `texto._partir` o equivalente), `vista="lista"` y encola `chunks.embeber` si hubo texto.
  Mismo cuidado que `indexar_archivo`: borrar chunks previos del archivo y comprobar que la versión sigue vigente.
  DXF ilegible o demasiado grande → `vista="error"` sin reintentos infinitos.
- Ruta `GET /archivos/{archivo_id}/vista.svg`: `obtener_archivo` + versión actual + `derivados.svg`. Respuesta `image/svg+xml`,
  `nosniff`, `private, no-store` y **`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`**.
- `archivo.html`: para DXF con vista lista, el visor de imágenes con `<img src=".../vista.svg">` (nunca `<object>`, `<embed>`
  ni SVG inline) y debajo una lista de capas (nombre y si está apagada). Pendiente o error → mismos mensajes que T-037.

## Criterios de aceptación
- [ ] CA1 Un DXF armado en la prueba con ezdxf (una capa "COTAS", un TEXT y un MTEXT con una frase única) → job →
  `derivados.svg` y `meta.dxf.capas` incluye "COTAS"; `GET vista.svg` → 200 con el CSP pedido; la búsqueda encuentra la frase.
- [ ] CA2 Aislamiento: `vista.svg` de otra empresa o de un proyecto sin acceso → 404; la frase no aparece para un usuario de B.
- [ ] CA3 Un `.dxf` con basura → `vista="error"`, el job no queda reintentando y la ficha muestra "no disponible".
- [ ] CA4 La página del archivo usa `<img>` para el SVG (la prueba lo comprueba en el HTML renderizado).
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- DWG (el plan prefiere exportar a DXF en la sesión de AutoCAD). Prender y apagar capas en el dibujo. Herramienta del agente para DXF.

## Bitácora del ejecutor

## Dictamen del auditor
