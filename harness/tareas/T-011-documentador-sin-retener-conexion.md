---
id: T-011
titulo: Documentador sin retener la conexión durante la llamada al modelo
estado: lista
rama: codex/T-011-documentador-sin-retener-conexion
creada: 2026-11-22
depende: —
pr:
---

## Objetivo
Que una consulta al Documentador no ocupe una conexión del pool ni mantenga una transacción abierta mientras
el modelo piensa (hasta decenas de segundos), para que varias personas puedan consultar a la vez sin agotar el pool.

## Contexto mínimo
- `app/routers/agentes.py` → `preguntar_documentador`: hoy usa `Depends(db_dependency)` durante todo el pedido,
  abre la conversación con `FOR UPDATE`, inserta `agent_runs` y recién hace commit después de `asyncio.run(...)`.
- `app/agentes/herramientas.py` → `ContextoDocumentador.db` (las herramientas usan esa misma conexión).
- `app/agentes/documentador.py` → `ejecutar` (al final revalida con `ids_visibles(contexto.db, ...)`).
- Pool: `app/db/__init__.py` → `pool()` (`max_size=10`).
- Hallazgo de la auditoría del PR #12 (ver dictamen en `harness/tareas/T-010-agente-documentador.md`).

## Alcance
- Tocar: `app/routers/agentes.py`, `app/agentes/herramientas.py`, `app/agentes/documentador.py`, `tests/test_documentador.py`.
- No tocar: migraciones, `app/db/__init__.py`, `app/services/busqueda.py`, el panel (`app/static/agente.js`).

## Diseño pedido
Tres fases, cada una con su conexión corta tomada de `pool()` (`with pool().connection() as db:`):
1. **Preparar** (transacción corta + commit): `obtener_proyecto`, abrir/validar conversación, leer historial, insertar `agent_runs` en `en_curso`.
2. **Ejecutar el agente sin conexión tomada.** Cada herramienta toma su propia conexión corta del pool para
   consultar y registrar su `tool_call`, y hace commit. El usuario y el proyecto siguen viniendo del contexto de sesión
   (nunca de argumentos del modelo). `ContextoDocumentador` deja de guardar una conexión.
3. **Cerrar** (transacción corta + commit): revalidar el proyecto y las fuentes (`ids_visibles`), guardar mensajes,
   actualizar `agent_runs` a `hecho` con tokens y estado del SDK, `auditoria.registrar`.
- Si el modelo falla: nueva conexión corta que marca el run como `fallido` (no queda `en_curso` colgado) y 503 como hoy.
- La ruta deja de depender de `db_dependency` para la fase 2 (puede usarla para la 1 si la libera antes; lo más simple es no usarla).

## Criterios de aceptación
- [ ] CA1 Con el modelo falso, mientras corre la fase 2 **no hay ninguna conexión del pool tomada por el pedido**
      (probalo con un modelo falso que, dentro de `get_response`, verifique `pool().get_stats()` o que pueda tomar
      todas las conexiones del pool sin bloquear).
- [ ] CA2 Un error del modelo deja el `agent_run` en `fallido` y responde 503 sin traza.
- [ ] CA3 Siguen pasando `tests/test_documentador.py` y `tests/test_aislamiento_m1.py` sin cambiar sus expectativas
      (citas verificadas, ids ajenos "no encontrado", 404 sin acceso).
- [ ] CA4 Si el usuario pierde acceso al proyecto entre la fase 1 y la 3, no se guarda la respuesta y se responde 404.
- [ ] CA5 Sensores y suite en verde.

## Fuera de alcance
- Streaming. Mover el agente a la cola de trabajos.

## Bitácora del ejecutor

## Dictamen del auditor
