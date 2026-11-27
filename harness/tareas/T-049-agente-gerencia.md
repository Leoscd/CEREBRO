---
id: T-049
titulo: Agente Gerencia
estado: lista
rama: codex/T-049-agente-gerencia
creada: 2026-11-27
depende: T-048
pr:
---

## Objetivo
En la página de Gerencia hay un agente de **solo lectura** que responde preguntas del administrador ("¿qué obras vienen atrasadas?",
"¿cuánto gastamos en IA este mes?") usando los mismos cuadros del tablero, y que nunca escribe nada.

## Contexto mínimo
- Plan: tabla de agentes fila "Gerencia (admin)", todas de solo lectura.
- T-048: `app/services/gerencia.py` (las cinco funciones) y `app/routers/gerencia.py`.
- Modelo de agente: el de Obra (`app/agentes/obra.py`) y en `app/routers/agentes.py` `_preguntar_agente` / `_historial_agente`
  (historial por empresa, usuario y agente). Este agente no tiene proyecto: el alcance de la conversación es la empresa.
- **Solo OpenAI**; modelo en `MODELO_GERENCIA`.

## Alcance
- Tocar: `app/agentes/gerencia.py` y `app/agentes/herramientas_gerencia.py` (nuevos), `app/routers/agentes.py` (rutas `/gerencia/agente`),
  `app/templates/gerencia.html` (panel), `app/config.py` y `.env.example` (`MODELO_GERENCIA`, `GERENCIA_CONSULTAS_POR_HORA`), `tests/test_agente_gerencia.py` (nuevo).
- No tocar: `app/agentes/aprobaciones.py`, `app/permisos.py`, migraciones (si `conversaciones` exige `proyecto_id`, pará y reportá antes de cambiar el esquema).

## Diseño pedido
- Herramientas de lectura, una por cuadro (`proyectos_atrasados`, `presupuesto_vs_gastado`, `precios_que_subieron`, `uso_ia`, `actividad_equipo`),
  con parámetros acotados (días 1-365, umbral ≥ 0) y `empresa_id` de la sesión. **Ninguna** herramienta de escritura.
- Las rutas exigen admin (`require_admin`) en GET y POST; el POST además `check_csrf`.
- Instrucciones en rioplatense, breve, citando números con el formato argentino y aclarando el período.

## Criterios de aceptación
- [ ] CA1 Con modelo falso, una pregunta llama a `uso_ia` y la respuesta trae los tokens de la empresa de la sesión.
- [ ] CA2 El agente no tiene herramientas de escritura (prueba sobre su lista de tools) y no crea filas en `tool_calls` pendientes.
- [ ] CA3 No admin → 403 en GET y POST; sin `MODELO_GERENCIA` con proveedor `openai` → 503 claro.
- [ ] CA4 Aislamiento: con datos en dos empresas, las respuestas solo usan los de la empresa de la sesión.
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Recomendaciones automáticas, envíos por correo, cualquier escritura.

## Bitácora del ejecutor

## Dictamen del auditor
