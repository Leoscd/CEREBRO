---
id: T-026
titulo: El servidor de desarrollo detecta un Postgres trabado
estado: hecha
rama: codex/T-026-dev-detecta-postgres-trabado
creada: 2026-11-23
depende: —
pr: "#36"
---

## Objetivo
Que `python -m scripts.dev` no se cuelgue en silencio cuando el Postgres embebido de `data/pgdev` quedó cortado, y que
diga qué pasó y cómo seguir (hallazgo H-010 de `harness/log.md`).

## Contexto mínimo
- `scripts/dev.py` → `pgserver.get_server(data/pgdev, cleanup_mode=None)`.
- H-010: `postmaster.pid` viejo apuntaba a un PID que Windows reusó (otro programa), y después la recuperación tardó más que el tope de 10 s de pgserver.
- Formato de `postmaster.pid`: línea 1 = PID, línea 4 = puerto.

## Alcance
- Tocar: `scripts/dev.py`, `tests/test_dev.py` (nuevo).
- No tocar: `data/` del usuario salvo lo que diga el diseño, pgserver.

## Diseño pedido
- Antes de llamar a pgserver: si existe `data/pgdev/postmaster.pid` y (a) el PID no existe, o (b) existe pero **no es un proceso de Postgres**
  (nombre del ejecutable), o (c) nada escucha en el puerto de la línea 4 → es un candado viejo: renombrarlo a `postmaster.pid.viejo-<fecha>` (nunca borrarlo) y avisar.
- Si pgserver falla por tiempo al arrancar, reintentar una vez después de esperar a que el log diga `ready to accept connections` (tope 90 s), y si no, terminar con un mensaje claro.
- Sin dependencias nuevas si se puede (en Windows, `tasklist /FI "PID eq N"`; en Linux, `/proc/N/comm`); si hace falta `psutil`, explicalo en la Bitácora.

## Criterios de aceptación
- [x] CA1 Prueba con un `postmaster.pid` falso cuyo PID es del propio proceso de la prueba (no es Postgres) → se renombra y se avisa.
- [x] CA2 Con un PID inexistente → se renombra. Con un Postgres de verdad (el de las pruebas) → no se toca.
- [x] CA3 Nunca se borra nada de `data/`.
- [x] CA4 Sensores y suite en verde.

## Fuera de alcance
- Cambiar de motor o de forma de levantar la base en desarrollo.

## Bitácora del ejecutor

- Se revisan el proceso y la escucha TCP en Windows o el socket Unix en Linux. Los candados viejos se renombran con fecha y el Postgres activo se deja intacto.
- Al superar el plazo, solo una marca nueva de disponibilidad en el log habilita el reintento. Cada arranque se ejecuta en un proceso breve para evitar la instancia incompleta que pgserver conserva tras un timeout.
- Las pruebas usaron archivos temporales y el PostgreSQL embebido de la suite. Pasaron los sensores y pytest, sin agregar dependencias.
- Se verificó en un pgdata temporal el arranque desde cero, la detención y el reinicio con un candado viejo. SELECT 1 funcionó antes y después del reinicio.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-24). Solo renombra el candado viejo, nunca borra; subprocess sin shell; Postgres real intacto. Merge: #36.
