---
id: T-006
titulo: Cola de trabajos y worker
estado: en-curso
rama: codex/T-006-cola-de-trabajos-y-worker
creada: 2026-11-21
depende: T-005
pr:
---

## Objetivo
Tener una cola de trabajos en Postgres y un proceso worker para tareas pesadas (análisis, texto, embeddings),
sin sumar Redis ni otro servicio.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Modelo de datos" (Transversales: `jobs`) y M1 (worker).
- Conexión y pool: `app/db/__init__.py`. Despliegue: `docker-compose.yml` (comentario "el worker se suma en M1").
- Subida y versiones: `app/routers/archivos.py` (T-003/T-004).

## Alcance
- Tocar: `app/db/migraciones/0003_jobs.sql` (nuevo), `app/services/jobs.py` (nuevo), `app/worker.py` (nuevo),
  `app/routers/archivos.py` (encolar), `docker-compose.yml` (servicio `worker`), `tests/test_jobs.py` (nuevo).
- No tocar: migraciones existentes.

## Diseño pedido
- `jobs`: id, empresa_id, tipo, payload jsonb, estado ('pendiente','en_curso','hecho','fallido'), intentos, max_intentos (def. 3),
  error text, disponible_desde timestamptz, tomado_en, terminado_en, creado_en. Índice parcial para pendientes por `disponible_desde`.
- `jobs.encolar(db, empresa_id, tipo, payload)` — **sin commit**, en la transacción de quien llama.
- `jobs.tomar(db)` con `SELECT … FOR UPDATE SKIP LOCKED`; `completar` y `fallar` (reintento con espera creciente; al agotar → 'fallido').
  Un trabajo 'en_curso' hace más de 15 min se considera abandonado y vuelve a pendiente.
- `python -m app.worker` con registro `{tipo: función}`, corte limpio con Ctrl+C/SIGTERM, y `--una-vez` (procesa lo pendiente y sale) para pruebas.
- Primer manejador `archivo.analizar`: confirma el tipo por los primeros bytes (PDF, PNG, JPEG, ZIP/Office) y guarda
  `{"meta": {"mime_real", "tamano"}}` en `versiones_archivo.derivados`. Se encola al subir archivo y al subir versión.
- Los manejadores reciben `empresa_id` del trabajo y filtran por él: nunca leen datos de otra empresa.
- `docker-compose.yml`: servicio `worker` con la misma imagen y `command: python -m app.worker`.

## Criterios de aceptación
- [x] CA1 Subir un PDF encola `archivo.analizar`; `--una-vez` lo procesa y `derivados.meta.mime_real` = `application/pdf`.
- [x] CA2 Un manejador que lanza excepción reintenta y queda 'fallido' con el error al agotar `max_intentos`.
- [x] CA3 Dos conexiones tomando a la vez nunca obtienen el mismo trabajo.
- [x] CA4 Un trabajo abandonado en 'en_curso' vuelve a tomarse.
- [x] CA5 Si falla la subida (p. ej. 413), no queda trabajo encolado (misma transacción). Sensores y suite en verde.

## Fuera de alcance
- Texto e índices (T-007). Miniaturas de imágenes. Panel de trabajos en la interfaz.

## Bitácora del ejecutor
- Los seis casos fallaron antes del cambio. Pasaron 54 pruebas y el sensor rápido terminó sin salida.
- La subida y el encolado se confirman juntos. Las reservas vencidas consumen un intento y un worker anterior no puede confirmar una reserva recuperada.
- El análisis guarda tamaño real y MIME por firma. DOCX, XLSX y PPTX comparten firma y se registran como application/zip.
- Se probó el worker como proceso con PostgreSQL real y se validó la estructura de Compose. Queda por verificar el arranque en Docker.

## Dictamen del auditor
