---
id: T-037
titulo: Gotenberg y vista previa de Office
estado: hecha
rama: codex/T-037-gotenberg-y-vista-previa-de-office
creada: 2026-11-25
depende: —
pr: 53
---

## Objetivo
Al abrir un DOCX, XLSX o PPTX del proyecto se ve una vista previa en PDF dentro del visor que ya existe, y su texto
entra en la búsqueda y en el Documentador con cita de página. La conversión la hace Gotenberg en un contenedor aparte.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Visores", fila "Vista previa y texto para el RAG" (Gotenberg, MIT).
- Subida: `app/routers/archivos.py` → `_crear_version` (encola `archivo.analizar` y, si es PDF, `archivo.indexar`).
- Visor: `_tipo_de_vista` y `pagina_archivo` en el mismo router; plantilla `app/templates/archivo.html` (bloque `tipo == 'pdf'`); `app/static/archivo.js` → `iniciarPdf`.
- Worker: `app/worker.py` → `indexar_archivo` (extrae con `texto.fragmentos_pdf`) y `MANEJADORES`.
- Almacén por contenido: `app/services/almacen.py` → `guardar(stream, validar)` devuelve `(sha256, tamano)`. Ejemplo de uso: `app/services/pdf_parte.py:133`.
- Limpieza de huérfanos: `scripts/limpiar_almacen.py` → `_referenciado` (hoy mira `versiones_archivo.sha256` y `biblioteca_documentos.sha256`).
- `versiones_archivo.derivados` es `jsonb` (migración 0002). No hace falta una migración nueva.

## Convención de derivados (vale para T-037, T-038 y T-039)
- Cada derivado guardado en el almacén va en `derivados -> '<tipo>'` como `{"sha256": ..., "tamano": ...}` (tipos: `pdf`, `svg`).
- El estado del proceso va en `derivados -> 'vista'`: `"pendiente" | "lista" | "sin_conversor" | "error"`.
- Todo derivado se sirve **solo** por una ruta que pasa por `obtener_archivo` (aislamiento); nunca por sha.

## Alcance
- Tocar: `docker-compose.yml` (servicio `gotenberg`), `.env.example` (`GOTENBERG_URL`), `app/config.py`,
  `app/services/gotenberg.py` (nuevo), `app/worker.py`, `app/routers/archivos.py`, `app/templates/archivo.html`,
  `app/static/archivo.js` (solo si hace falta para la URL del PDF), `scripts/limpiar_almacen.py`,
  `tests/test_vista_office.py` (nuevo), `tests/test_almacen.py` (caso de derivado referenciado).
- No tocar: `app/static/vendor/**`, migraciones existentes, `app/permisos.py`, `Caddyfile` (Gotenberg no se expone).

## Diseño pedido
- Compose: servicio `gotenberg` con imagen `gotenberg/gotenberg:8` **con tag fijo de versión** (no `latest`), sin `ports`,
  con el mismo bloque `<<: *endurecido` que el resto si la imagen lo tolera, `mem_limit` y `pids_limit`. `app` y `worker`
  reciben `GOTENBERG_URL=http://gotenberg:3000`. Si `read_only` rompe Gotenberg, sacalo **solo** para ese servicio y anotalo en la Bitácora.
- `app/services/gotenberg.py`: `a_pdf(ruta: Path, nombre: str) -> bytes` con `httpx` contra `/forms/libreoffice/convert`,
  timeout (config) y tope de tamaño de respuesta. Si `GOTENBERG_URL` está vacío → excepción propia `SinConversor`.
- Extensiones Office: `docx, xlsx, pptx, odt, ods, odp, doc, xls, ppt, rtf`. Al crear la versión, si la extensión está en esa
  lista, encolá `archivo.vista_pdf` y marcá `derivados.vista = "pendiente"`.
- Job `archivo.vista_pdf` (worker): convierte, guarda con `almacen.guardar(..., validar=texto.es_pdf)`, escribe `derivados.pdf`
  y `vista="lista"`, y encola `archivo.indexar`. Sin conversor → `vista="sin_conversor"` y el job termina bien (no reintenta).
  Error de conversión → `vista="error"` después de los reintentos normales.
- `indexar_archivo`: si la versión no es PDF pero tiene `derivados.pdf`, extrae el texto del derivado. Las citas siguen
  apuntando al archivo original con su página.
- Ruta `GET /archivos/{archivo_id}/vista.pdf`: `obtener_archivo` + versión actual + `derivados.pdf` → `FileResponse` inline,
  `application/pdf`, `nosniff`, `private, no-store`. Sin derivado → 404.
- `archivo.html`: para Office con vista lista, el mismo visor PDF con `data-contenido` apuntando a `vista.pdf`; pendiente →
  "Preparando la vista previa…"; `sin_conversor` o `error` → "La vista previa no está disponible. Descargá el archivo."
- `limpiar_almacen._referenciado`: también cuenta como referenciado un sha que aparezca en `derivados -> <tipo> ->> 'sha256'`
  de cualquier versión (por ejemplo con `jsonb_each`).

## Criterios de aceptación
- [ ] CA1 Con `gotenberg.a_pdf` reemplazado por uno falso que devuelve `tests/fixtures/pdf.py` (PDF con una frase única),
  subir un `.docx` → job → `derivados.pdf` y `vista="lista"`; `GET vista.pdf` → 200 `application/pdf`; la búsqueda encuentra la frase con página.
- [ ] CA2 Aislamiento: `vista.pdf` de un archivo de otra empresa o de un proyecto sin acceso → 404; la frase no aparece para un usuario de B
  (sumá el caso a la idea de `tests/test_aislamiento_m1.py`: búsqueda, descarga y derivado).
- [ ] CA3 Sin `GOTENBERG_URL` → `vista="sin_conversor"`, el job no queda en reintento y la ficha muestra el mensaje de "no disponible".
- [ ] CA4 `limpiar_almacen` no borra un blob que solo está referenciado como derivado.
- [ ] CA5 `docker compose config` válido y la prueba de humo de Compose en verde.
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- ONLYOFFICE (T-041, T-042). Conversión de DWG. Vista previa de versiones anteriores (solo la actual).

## Bitácora del ejecutor

- Sensores rápidos y suite local en verde; el conversor se reemplazó en las pruebas de contenido.

- Gotenberg 8.32.0 en red interna, sin puertos publicados, con raíz de solo lectura y tmpfs para el perfil de LibreOffice y los temporales. El worker limita tiempo y tamaño de respuesta.
- La vista, los chunks y las citas usan la versión vigente. La descarga sigue entregando el original. La prueba de búsqueda convierte con un PDF de dos páginas conocido.
- Docker no está instalado en Windows ni en Ubuntu/WSL de esta PC. La validación de Compose se ejecuta en CI.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-26). Gotenberg en red interna, sin descarga por URL y con deny list de LibreOffice; vista.pdf por obtener_archivo; limpieza respeta derivados. Pendiente: conversión con un DOCX real en el VPS (CI solo levanta el contenedor). Merge: #53.
