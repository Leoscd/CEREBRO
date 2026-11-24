---
id: T-034
titulo: Agente Obra
estado: lista
rama: codex/T-034-agente-obra
creada: 2026-11-24
depende: T-033
pr:
---

## Objetivo
Un agente en la pantalla de obra que responde sobre el cronograma, atrasos, materiales y partes, y que ayuda a armar el
parte del día: lo que escribe en el borrador pasa por aprobación, y cerrar el parte también.

## Contexto mínimo
- Plan: Agentes web → fila "Obra" (consultar_cronograma, registrar_avance/personal/nota/pedido ✎ en el borrador del parte, alertas_materiales, cerrar_reporte ✎, resumen_obra).
- Infra de aprobaciones (`app/agentes/aprobaciones.py`, T-022) y el agente Presupuestos como modelo (`app/agentes/presupuestos.py`, `herramientas_presupuestos.py`).
- Referencia de conducta (prompt y herramientas): `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\agente.py` y `herramientas.py` — **solo OpenAI**.
- Servicios de obra (T-028 a T-033).

## Alcance
- Tocar: `app/agentes/obra.py` (nuevo), `app/agentes/herramientas_obra.py` (nuevo), `app/routers/agentes.py`, plantilla de obra (panel), `app/config.py`, `.env.example` (`MODELO_OBRA`),
  `tests/test_agente_obra.py` (nuevo).

## Diseño pedido
- Lectura: `consultar_cronograma`, `resumen_obra`, `alertas_materiales`, `buscar_en_partes`, `ultimos_partes`.
- Escritura ✎ (aprobación + `puede_registrar_obra`): `registrar_avance`, `registrar_personal`, `registrar_nota`, `registrar_pedido` (todas sobre el **borrador** del parte de hoy) y `cerrar_reporte` (confirma, T-029).
- Sobre un parte confirmado, las herramientas de escritura responden que el parte está cerrado (portá "reporte confirmado solo permite consultas").
- Contexto de sesión, nunca de argumentos. Instrucciones en rioplatense, breve, pensado para el celular.

## Criterios de aceptación
- [ ] CA1 Guion con modelo falso: registrar un avance → pendiente; aprobar → queda en el borrador; cerrar el parte → número asignado y PDF encolado.
- [ ] CA2 Con el parte confirmado, cualquier escritura → "parte cerrado" y nada cambia.
- [ ] CA3 Aislamiento: ids de otra obra o empresa → "no encontrado". Sin `MODELO_OBRA` con proveedor `openai` → 503 claro.
- [ ] CA4 Sensores y suite en verde (sin red).

## Fuera de alcance
- Canales de WhatsApp/Telegram (después del plan). Fotos por el agente.

## Bitácora del ejecutor

## Dictamen del auditor
