---
id: T-047
titulo: Agente Redes
estado: lista
rama: codex/T-047-agente-redes
creada: 2026-11-27
depende: T-046
pr:
---

## Objetivo
En la pantalla de un contenido de redes hay un agente que propone el texto y los hashtags, arma el guion de un reel y
genera el carrusel. Todo lo que escribe pasa por la tarjeta de aprobación, y nunca ve fotos de un proyecto sin difusión.

## Contexto mínimo
- Plan: tabla de agentes fila "Redes" (fotos_difundibles, generar_carrusel ✎ 1080×1350, guion_reel, copy_y_hashtags, kit_publicacion).
- Modelo a copiar: el agente de Obra (T-034): `app/agentes/obra.py`, `app/agentes/herramientas_obra.py`, y en `app/routers/agentes.py`
  `_preguntar_agente` / `_historial_agente`. Aprobaciones: `app/agentes/aprobaciones.py`.
- T-045 y T-046: `contenidos_redes`, `contenidos.fotos_difundibles`, job `redes.carrusel`, ruta del kit.
- Formato de guion de referencia (leer, no copiar): `D:\APLICACIONES\editor-contenido\skills\reel-clase-revit.json` y `short-dato-rapido.json`.
- **Solo OpenAI**; modelo en `MODELO_REDES`.

## Alcance
- Tocar: `app/agentes/redes.py` y `app/agentes/herramientas_redes.py` (nuevos), `app/routers/agentes.py` (rutas GET/POST `/proyecto/{codigo}/redes/{id}/agente`),
  `app/templates/redes/` (panel del agente), `app/config.py` y `.env.example` (`MODELO_REDES`, `REDES_CONSULTAS_POR_HORA`), `tests/test_agente_redes.py` (nuevo).
- No tocar: `app/agentes/aprobaciones.py` (salvo registrar el agente como los otros), `app/permisos.py`, migraciones existentes.

## Diseño pedido
- Lectura: `fotos_difundibles` (descripciones y ids, **nunca** bytes ni URLs firmadas; `[]` sin difusión), `ver_contenido`, `kit_publicacion` (devuelve la ruta del kit o "todavía no hay placas").
- Escritura ✎ (aprobación + `puede_escribir_en_proyecto`): `actualizar_texto` (texto y hashtags), `guardar_guion_reel` (escenas con duración en segundos,
  texto en pantalla y locución; total ≤ 90 s; se guarda en `contenidos_redes.guion`), `elegir_fotos` (solo ids difundibles) y `generar_carrusel` (encola el job de T-046).
- Contexto de sesión (empresa, proyecto, contenido) nunca de argumentos. Instrucciones en rioplatense, tono de estudio de arquitectura, sin inventar datos del proyecto.
- Sin `MODELO_REDES` con proveedor `openai` → 503 claro, como Obra.

## Criterios de aceptación
- [ ] CA1 Guion con modelo falso: `actualizar_texto` → pendiente; aprobar → el contenido cambia; rechazar → no cambia.
- [ ] CA2 `guardar_guion_reel` con 100 s en total → la propuesta se rechaza (422) sin crear aprobación pendiente.
- [ ] CA3 Proyecto sin difusión: `fotos_difundibles` → `[]`, `elegir_fotos` con cualquier id → error, `generar_carrusel` → error y nada encolado.
- [ ] CA4 Aislamiento: contenido de otra empresa o de otro proyecto → "no encontrado"; cliente → 404.
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Generar video o audio. Leer métricas de Instagram. Borrador automático desde el cierre de sesión (M4).

## Bitácora del ejecutor

## Dictamen del auditor
