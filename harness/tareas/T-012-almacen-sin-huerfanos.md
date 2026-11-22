---
id: T-012
titulo: Almacén sin blobs huérfanos
estado: en-curso
rama: codex/T-012-almacen-sin-huerfanos
creada: 2026-11-22
depende: —
pr:
---

## Objetivo
Que no se acumulen archivos en `ALMACEN_DIR` que ninguna fila referencia: validar antes de publicar el blob
y tener un comando de limpieza seguro.

## Contexto mínimo
- `app/services/almacen.py` → `guardar` (temporal → `os.replace` al destino por sha256).
- `app/routers/admin.py` → `subir_criterio`: hoy guarda el blob y **después** valida `texto.es_pdf`; si no es PDF, el blob queda.
- `app/routers/archivos.py` → `_crear_version`: si falla la base después de `guardar`, el blob queda.
- Referencias a blobs: `versiones_archivo.sha256` y `biblioteca_documentos.sha256`.
- **Ojo:** los blobs se deduplican por contenido **entre empresas**. Un blob solo es huérfano si ninguna fila de
  **ninguna** empresa lo referencia. Nunca borrar un blob mirando una sola empresa.

## Alcance
- Tocar: `app/services/almacen.py`, `app/routers/admin.py`, `scripts/limpiar_almacen.py` (nuevo), `tests/test_almacen.py` (nuevo).
- No tocar: migraciones, `app/routers/archivos.py` salvo para pasar un validador si hace falta.

## Diseño pedido
- `almacen.guardar(stream, validar=None)`: si `validar` está, se llama con la ruta del **temporal** antes de publicar;
  si devuelve False → se borra el temporal y se lanza 400 con mensaje. `subir_criterio` pasa `texto.es_pdf`.
- `python -m scripts.limpiar_almacen [--borrar] [--horas 24]`:
  - Recorre `ALMACEN_DIR`, ignora temporales `.subida-*` de menos de `--horas` y borra los más viejos.
  - Un blob es huérfano si su sha256 no aparece en `versiones_archivo` ni en `biblioteca_documentos` (consulta global, sin filtro de empresa) **y** su archivo tiene más de `--horas` (evita carreras con una subida en curso).
  - Por defecto **solo lista** (modo prueba). Con `--borrar` borra e imprime un resumen (cantidad y bytes).
  - Salida corta; código 0.
- Documentá en el docstring cómo correrlo en el VPS (`docker compose exec app python -m scripts.limpiar_almacen --borrar`).

## Criterios de aceptación
- [x] CA1 Subir a la biblioteca algo que no es PDF → 400 y **no** queda blob ni temporal.
- [x] CA2 Un blob referenciado solo por la empresa B no se borra aunque A no lo use.
- [x] CA3 Un blob sin referencias y viejo se lista sin `--borrar` y se borra con `--borrar`; uno sin referencias pero reciente no se toca.
- [x] CA4 Un temporal `.subida-*` viejo se borra; uno reciente no.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- Programar el cron en el VPS (lo hace Leo). Borrar versiones o archivos de la papelera.

## Bitácora del ejecutor
- Los tres casos nuevos fallaron antes del cambio. Pasaron 76 pruebas y el sensor rápido terminó sin salida.
- El validador recibe el temporal antes de publicar. La limpieza consulta ambas tablas sin filtrar por empresa y solo considera archivos regulares en las rutas del almacén.
- Publicación y borrado se coordinan por almacén. Reutilizar un blob renueva su antigüedad, y el borrado vuelve a comprobar edad y referencias bajo el bloqueo. Se verificó el comando con un almacén y una base temporales.

## Dictamen del auditor
