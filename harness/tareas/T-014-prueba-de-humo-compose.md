---
id: T-014
titulo: Prueba de humo de docker compose (app + worker)
estado: hecha
rama: codex/T-014-prueba-de-humo-compose
creada: 2026-11-22
depende: —
pr: "#19"
---

## Objetivo
Comprobar automáticamente que la imagen arranca con `docker compose`, que la app responde `/salud`, que se
aplican las migraciones y que el worker procesa un trabajo, antes del primer deploy al VPS.

## Contexto mínimo
- `docker-compose.yml` (servicios `postgres`, `app`, `worker`; `read_only`, `tmpfs`, volúmenes), `Dockerfile`, `scripts/deploy.sh`.
- Hallazgo de la auditoría del PR #7 (dictamen en `harness/tareas/T-006-cola-de-trabajos-y-worker.md`): el arranque en Docker no se probó.
- **En esta PC no hay Docker.** El script corre en GitHub Actions: el harness ya tiene un paso de CI que lo ejecuta
  **si existe** `scripts/probar_compose.sh` (no edites `.github/`).

## Alcance
- Tocar: `scripts/probar_compose.sh` (nuevo), `.env.ci` (nuevo, solo valores de prueba), y lo mínimo de `docker-compose.yml`/`Dockerfile` si la prueba revela un error real (explicalo en la Bitácora).
- No tocar: `.github/` (protegido), código de la app salvo que la prueba revele un error real.

## Diseño pedido
- `scripts/probar_compose.sh` (bash, `set -euo pipefail`): copia `.env.ci` a `.env` si no hay `.env`, `docker compose build`,
  `docker compose up -d`, espera a que `app` esté `healthy` (tope 120 s), corre las migraciones y la alta de una empresa de prueba,
  encola un trabajo `archivo.analizar` sobre un archivo subido por HTTP o por SQL y comprueba que el worker lo deja en `hecho` (tope 60 s).
  Siempre `docker compose down -v` al salir (`trap`). En caso de falla, imprime `docker compose logs --tail 80` de cada servicio.
- `.env.ci`: `SECRET_KEY` y `POSTGRES_PASSWORD` de prueba (sin secretos reales), `EMBEDDINGS_PROVEEDOR=falso`, `AGENTES_PROVEEDOR=falso`.

## Criterios de aceptación
- [x] CA1 En el CI del PR, el paso "Prueba de humo de docker compose" corre y termina en verde.
- [x] CA2 Si el worker no puede leer el almacén (montaje `:ro`) o falla la migración, el script falla con un mensaje claro y los logs.
- [x] CA3 `.env.ci` no contiene nada que parezca una clave real.
- [x] CA4 Sensores y suite en verde.

## Fuera de alcance
- Caddy y HTTPS (perfil `dominio`). Deploy real al VPS.

## Bitácora del ejecutor
- La prueba crea un proyecto Compose temporal con credenciales ficticias, un volumen de Postgres descartable y los bind mounts de app y worker aislados.
- Git Bash verificó la sintaxis. Un simulador de Docker confirmó los mensajes, los logs y down -v ante fallas de migración y del worker. Pasaron las 73 pruebas y el sensor rápido terminó sin salida.
- GitHub Actions #45078879201 confirmó /salud, todas las migraciones, el PDF analizado y la eliminación del volumen de prueba.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-22). Proyecto Compose aislado y descartable; corrió en Actions: /salud, migraciones y PDF analizado por el worker. Merge: #19.
