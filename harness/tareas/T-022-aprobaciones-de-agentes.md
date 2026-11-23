---
id: T-022
titulo: Aprobaciones para herramientas que escriben (pausar y retomar)
estado: lista
rama: codex/T-022-aprobaciones-de-agentes
creada: 2026-11-23
depende: T-021
pr:
---

## Objetivo
Que un agente web pueda proponer una acción que escribe (cargar un precio, agregar ítems) y que **no se ejecute hasta que
una persona la apruebe** en una tarjeta Aprobar/Rechazar; al aprobar, la ejecución se retoma donde quedó.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Dos formas de ejecutar agentes" (OpenAI Agents SDK, `needs_approval` que pausa y retoma) y Verificación M2
  ("una escritura no corre sin aprobación; se retoma bien después de aprobar").
- Agente existente: `app/agentes/` (documentador, herramientas, `modelo_falso.py`), `app/routers/agentes.py` (patrón de 3 fases sin
  retener conexión, de T-011), tablas `agent_runs` (`estado_sdk jsonb`) y `tool_calls` (0006).
- Agents SDK 0.22.2 (`requirements.txt`): mirá su soporte de `needs_approval`, `RunState` e interrupciones.

## Alcance
- Tocar: `app/db/migraciones/0010_aprobaciones.sql` (nuevo, si hace falta: estados y columnas de aprobación), `app/agentes/aprobaciones.py` (nuevo),
  `app/agentes/modelo_falso.py`, `app/routers/agentes.py`, `app/static/agente.js`, `tests/test_aprobaciones.py` (nuevo).
- No tocar: el comportamiento del Documentador (sigue sin herramientas que escriban).

## Diseño pedido
- Infra genérica para cualquier agente: una herramienta marcada "escribe" pide aprobación. El run queda `esperando_aprobacion` con su
  estado serializado en `agent_runs.estado_sdk`, y el `tool_call` en `pendiente` con los argumentos **tal como se ejecutarían** (lo que se muestra es lo que corre).
- `POST /agentes/runs/{run_id}/tool-calls/{id}/aprobar|rechazar` (JSON + `X-CSRF`): solo la persona que lanzó el run, misma empresa,
  y con el permiso que la herramienta declare (p. ej. `puede_gestionar_precios`). Ajeno → 404.
  Al aprobar: retoma el run (3 fases, sin retener conexión), ejecuta **esa** llamada una sola vez y sigue. Al rechazar: el modelo recibe "rechazado por <persona>".
- Doble clic, dos pestañas o reintento: la llamada se ejecuta **una sola vez** (bloqueo de fila / transición de estado condicionada).
- Panel: tarjeta con qué va a hacer (texto legible + detalle), botones Aprobar / Rechazar.
- Auditoría: `agente.aprobacion` y `agente.rechazo`.
- Modelo falso con guion para pruebas: pide una herramienta de escritura de prueba (registrada solo en tests) y luego responde.

## Criterios de aceptación
- [ ] CA1 Sin aprobar, la herramienta de escritura **no corre** (el efecto no existe en la base) y el run queda `esperando_aprobacion`.
- [ ] CA2 Aprobar → corre una sola vez y el run termina `hecho` con la respuesta final; aprobar de nuevo → 409.
- [ ] CA3 Rechazar → no corre, el modelo recibe el rechazo y el run termina.
- [ ] CA4 Otra persona de la misma empresa, otra empresa o sin el permiso de la herramienta → 404/403; dos aprobaciones simultáneas → un solo efecto.
- [ ] CA5 Ninguna conexión del pool tomada mientras el modelo piensa (mismo estilo de prueba que T-011). Sensores y suite en verde.

## Fuera de alcance
- Aprobaciones de sesiones de trabajo de Codex (M4). Notificaciones.

## Bitácora del ejecutor

## Dictamen del auditor
