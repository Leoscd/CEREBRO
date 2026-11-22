---
id: T-003
titulo: Subir y bajar archivos
estado: en-curso
rama: codex/T-003-subir-y-bajar-archivos
creada: 2026-11-21
depende: T-002
pr:
---

## Objetivo
Que el equipo del proyecto pueda subir archivos a una carpeta desde la ficha y descargarlos, guardados por contenido.

## Contexto mínimo
- Modelo y permisos de T-002: `archivos_visibles_sql`, `obtener_archivo`, `puede_escribir_en_proyecto` (`app/permisos.py`).
- Patrón de ruta con CSRF + permisos + auditoría: `app/routers/proyectos.py` → `agregar_hito` (líneas ~161-185).
- Auditoría: `app/services/auditoria.registrar` (no hace commit; va en la misma transacción).
- Config: `app/config.py` → `ALMACEN_DIR`. Ficha: `app/templates/proyecto.html`.
- Registro de routers: `app/main.py`.

## Alcance
- Tocar: `app/services/almacen.py` (nuevo), `app/routers/archivos.py` (nuevo), `app/main.py`, `app/config.py`, `.env.example`,
  `app/routers/proyectos.py` (solo `ficha`, para pasar carpetas y archivos), `app/templates/proyecto.html`, `app/static/style.css`, `tests/test_subida.py` (nuevo).
- No tocar: migraciones existentes, `app/permisos.py` salvo que falte algo (si falta, explicalo en la Bitácora).

## Diseño pedido
- `almacen.guardar(stream) -> (sha256, tamano)`: escribe en un temporal dentro de `ALMACEN_DIR` leyendo de a bloques,
  calcula sha256 al vuelo, corta con 413 si supera `ARCHIVO_MAX_MB` (nuevo en `.env.example`, por defecto 1024),
  y mueve a `ALMACEN_DIR/ab/abcdef…` (dos primeros caracteres como subcarpeta). Si ya existe, no duplica.
  `almacen.ruta(sha256) -> Path`.
- `POST /proyectos/{codigo}/carpetas/{carpeta_id}/archivos` (multipart, campo `archivo`): `check_csrf`, `obtener_proyecto`,
  carpeta del mismo proyecto (si no → 404), `exigir(puede_escribir_en_proyecto)`. Crea archivo + versión 1 (`origen='subida'`),
  setea `version_actual_id`, `auditoria.registrar(..., "archivo.subir", ...)` en la misma transacción. Redirige a la ficha.
- Nombre: solo el nombre base (sin rutas), sin caracteres de control, máximo 200; extensión en minúscula.
- `GET /archivos/{archivo_id}/descargar`: `obtener_archivo` → `FileResponse` de la versión actual con `Content-Disposition: attachment` y el nombre original.
- Ficha: lista de carpetas con sus archivos (nombre, versión, tamaño legible, fecha con filtro `fecha`) y, si puede escribir,
  un formulario de subida por carpeta (`enctype="multipart/form-data"`, campo `csrf`).

## Criterios de aceptación
- [x] CA1 Ana sube un archivo a una carpeta de p1 → aparece en la ficha y se descarga con el mismo contenido y nombre.
- [x] CA2 Ana intentando subir a p2 → 404; el cliente subiendo a p1 → 403; carpeta de otro proyecto en la URL → 404.
- [x] CA3 Descargar un archivo de A siendo admin B → 404; siendo cliente con `visible_cliente=false` → 404.
- [x] CA4 Subir dos veces el mismo contenido deja un solo blob en `ALMACEN_DIR` (dos archivos, mismo sha256).
- [x] CA5 Nombre `../../etc/passwd` queda como `passwd`; un archivo que supera el máximo → 413 y no queda blob ni fila.
- [x] CA6 La subida deja una fila `archivo.subir` en `auditoria`.
- [x] CA7 `ALMACEN_DIR` en las pruebas apunta a un directorio temporal (no ensuciar `data/`). Sensores y suite en verde.

## Fuera de alcance
- Versiones nuevas, papelera, visibilidad para el cliente (T-004). Vista previa (T-005).

## Bitácora del ejecutor
- Los cinco casos fallaron antes del cambio. Pasaron las 41 pruebas y el sensor rápido terminó sin salida.
- El almacén publica el blob desde un temporal en el mismo volumen y lo identifica por SHA-256. Si una transacción posterior falla, un blob ya publicado puede quedar sin referencia para que se recolecte por separado.
- La ficha usa el contexto del router de archivos para consultar por proyecto sin una consulta por carpeta.

## Dictamen del auditor
