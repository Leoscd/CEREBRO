---
id: T-010
titulo: Agente Documentador en el panel
estado: hecha
rama: codex/T-010-agente-documentador
creada: 2026-11-21
depende: T-009
pr: "#12"
---

## Objetivo
Que en la ficha y en la página del archivo el usuario le pregunte al Documentador sobre la documentación del
proyecto y la biblioteca, y reciba respuestas con citas (archivo + página) que abren el visor en esa página.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Agentes web (OpenAI Agents SDK)" y "Modelo de datos" (Agentes web: `conversaciones`, `mensajes`, `agent_runs`, `tool_calls`).
- Búsqueda: `busqueda.buscar` (T-008). Panel vacío `#panel-agente` en `archivo.html` (T-005). Prueba de aislamiento: `tests/test_aislamiento_m1.py` (T-009).
- Verificación del plan: pruebas "con un modelo falso para el SDK que sigue un guion fijo".

## Alcance
- Tocar: `app/db/migraciones/0006_agentes.sql` (nuevo), `app/agentes/` (nuevo: `documentador.py`, `herramientas.py`, `modelo_falso.py`),
  `app/routers/agentes.py` (nuevo), `app/main.py`, `app/config.py`, `.env.example`, `app/templates/archivo.html`, `app/templates/proyecto.html`,
  `app/static/agente.js` (nuevo), `requirements.txt` (`openai-agents`, versión fija), `tests/test_documentador.py` (nuevo), `tests/test_aislamiento_m1.py`.

## Diseño pedido
- Tablas: `conversaciones` (empresa_id, proyecto_id, usuario_id, agente, resumen, creada_en), `mensajes` (conversacion_id, rol, contenido, citas jsonb),
  `agent_runs` (empresa_id, conversacion_id, modelo, estado, tokens_entrada, tokens_salida, estado_sdk jsonb, creado_en),
  `tool_calls` (agent_run_id, herramienta, argumentos jsonb, resultado_resumen, estado, creado_en). Todas con `empresa_id`.
- Modelo desde `MODELO_DOCUMENTADOR` (`.env`); `AGENTES_PROVEEDOR` = `openai` | `falso`.
- Herramientas **solo de lectura**: `buscar_documentacion(consulta)`, `leer_fragmento(chunk_id)`, `listar_archivos(carpeta?)`.
  El usuario y el proyecto se **capturan del contexto de la sesión** (contexto del runner), nunca de argumentos que elija el modelo.
  `leer_fragmento` revalida visibilidad: un id ajeno responde "no encontrado".
- Instrucciones del agente: responder en español rioplatense, citar siempre `[archivo, pág. N]`, decir "no lo encontré en la documentación" si no hay fuente.
- `POST /proyectos/{codigo}/documentador` (JSON, header `X-CSRF`, `check_csrf`): mensaje → respuesta + citas. Guarda conversación, mensajes, run, tool calls.
  Auditoría `agente.consulta` (sin el texto completo). Sin streaming en esta tarea.
- Panel (`agente.js`): historial de la conversación, caja de texto, citas como enlaces a `/archivos/{id}#page=N`.
- `modelo_falso.py`: implementa la interfaz de modelo del SDK con un guion (llama a `buscar_documentacion` y responde con la cita).

## Criterios de aceptación
- [x] CA1 Con el modelo falso: preguntar por la frase única de p1 → respuesta con cita al archivo y página correctos; quedan filas en las 4 tablas.
- [x] CA2 `tests/test_aislamiento_m1.py` suma chat y herramientas: un guion que pide `leer_fragmento` con el id de un chunk de B o de p2 → "no encontrado"; la frase ajena nunca está en la respuesta ni en `tool_calls`.
- [x] CA3 Cliente: solo ve citas de archivos `visible_cliente`. Usuario sin acceso al proyecto → 404 en la ruta.
- [x] CA4 Sin `MODELO_DOCUMENTADOR` con proveedor `openai` → error claro (503 con mensaje), sin trazas.
- [x] CA5 Sensores y suite en verde (sin red). Probado a mano una vez con la clave real si Leo la cargó en `.env` (anotalo; si no, decilo).

## Fuera de alcance
- Herramientas que escriben y aprobaciones (`needs_approval`, M2). Streaming. Memoria por resumen entre conversaciones.

## Bitácora del ejecutor
- Los cuatro casos fallaron antes del cambio. Pasaron 71 pruebas y el sensor rápido terminó sin salida.
- El historial tiene una conversación por persona y proyecto. Las herramientas toman su alcance de la sesión. Una cita retirada se excluye del historial visible y del próximo prompt.
- El Agents SDK 0.22.2 es compatible con FastAPI 0.115 y el cliente OpenAI de T-008. Se guarda el estado del SDK sin serializar la sesión ni la conexión y se desactivan las trazas del proveedor.
- Chromium con datos demo y proveedor falso confirmó pregunta, historial en ambos paneles y cita que abre el PDF en la página 2. El checkout no tiene .env y la prueba con OpenAI real quedó pendiente.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-22). Citas armadas por el servidor desde ids revalidados; herramientas con contexto de sesión; panel con textContent. Pendiente: no retener conexión/transacción durante la llamada al modelo. Merge: #12.
