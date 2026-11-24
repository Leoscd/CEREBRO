---
id: T-033
titulo: Bitácora del proyecto y resumen de obra
estado: hecha
rama: codex/T-033-bitacora-y-resumen-de-obra
creada: 2026-11-24
depende: T-032
pr: "#46"
---

## Objetivo
Una línea de tiempo única de lo que pasa en la obra (partes, notas, hitos, avances, pedidos) y un resumen de una pantalla
con lo importante: avance físico y económico, atrasos, alertas y notas abiertas.

## Contexto mínimo
- Plan: Modelo de datos → Obra (`bitacora`). **Portar** `resumen_obra` y las consultas de `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\herramientas.py`
  y sus pruebas en `tests/test_consultas.py` ("resumen marca atraso crítico y notas", "últimos reportes del más nuevo al más viejo", "buscar en reportes ignora acentos").
- Servicios de T-028 a T-032. Auditoría (`app/services/auditoria.py`).

## Alcance
- Tocar: `app/db/migraciones/0017_bitacora.sql` (si hace falta una tabla; si alcanza con una vista o consulta, mejor), `app/services/bitacora.py` (nuevo),
  `app/services/resumen_obra.py` (nuevo), `app/routers/obra.py`, plantillas, `tests/test_bitacora.py` (nuevo).

## Diseño pedido
- `bitacora(db, usuario, proyecto, desde, hasta, tipos)` → eventos ordenados (más nuevo primero) con tipo, fecha, título y enlace. Filtros por tipo y fechas.
- `resumen_obra(db, usuario, proyecto, hoy)` → avance físico y económico, previsto vs real, tareas atrasadas (críticas primero), alertas de materiales, notas abiertas con plazo vencido, último parte.
- `buscar_en_partes(texto)` sin distinguir acentos ni mayúsculas.
- Estos servicios son los que va a usar el agente Obra (T-034): devuelven datos, no HTML.

## Criterios de aceptación
- [x] CA1 Pruebas portadas del resumen y de la búsqueda (listalas con su origen).
- [x] CA2 La bitácora de un proyecto nunca trae eventos de otro proyecto o empresa (prueba con datos en ambos).
- [x] CA3 Sensores y suite en verde.

## Fuera de alcance
- Informe semanal automático (Documentador, más adelante).

## Bitácora del ejecutor

- Porté de `obra-report-w/tests/test_consultas.py` los casos `test_resumen_obra_marca_atraso_critico_y_notas`, `test_ultimos_reportes_del_mas_nuevo_al_mas_viejo` y `test_buscar_en_reportes_ignora_acentos` a `tests/test_bitacora.py`. La última pareja comparte un caso de prueba.
- La bitácora reúne partes confirmados, notas, hitos, avances y pedidos mediante una consulta con ámbito de empresa y proyecto. Los servicios comprueban visibilidad incluso cuando se llaman fuera de la ruta.
- La búsqueda conserva la puntuación por palabras de `obra_bot/herramientas.py` y ordena por fecha. No hizo falta una migración.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-24). Pruebas portadas (resumen, últimos partes, búsqueda sin acentos); bitácora aislada por obra. Merge: #46.
