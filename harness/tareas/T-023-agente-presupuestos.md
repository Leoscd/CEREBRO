---
id: T-023
titulo: Agente Presupuestos
estado: lista
rama: codex/T-023-agente-presupuestos
creada: 2026-11-23
depende: T-022
pr:
---

## Objetivo
Un agente en el panel del presupuesto que consulta el catálogo, arma y corrige presupuestos y revisa su calidad;
todo lo que escribe pasa por aprobación (T-022).

## Contexto mínimo
- Plan: `docs/PLAN.md` → Agentes web → fila "Presupuestos/Excel" (catalogo_buscar, precio_cargar ✎, norma_buscar, calc,
  presupuesto_crear/agregar_items/actualizar_por_indice ✎, analizar_presupuesto) y "Límites".
- Infra: aprobaciones (T-022), Documentador como ejemplo (`app/agentes/`), búsqueda en criterios (`busqueda.buscar`, biblioteca).
- Servicios: precios (T-017), apus (T-018), presupuestos (T-019), verificador (T-020), excel (T-021).
- `safe_eval` de referencia: `D:\APLICACIONES\excel-wrapper\src\apu\tools\python_calc.py` (portalo con sus pruebas; nada de `eval`).

## Alcance
- Tocar: `app/agentes/presupuestos.py` (nuevo), `app/agentes/herramientas_presupuestos.py` (nuevo), `app/agentes/calc.py` (nuevo),
  `app/routers/agentes.py` (ruta del agente), plantilla del presupuesto (panel), `app/config.py`, `.env.example` (`MODELO_PRESUPUESTOS`),
  `tests/test_agente_presupuestos.py` (nuevo).

## Diseño pedido
- Lectura (sin aprobación): `catalogo_buscar`, `precio_vigente`, `apu_detalle`, `presupuesto_leer`, `analizar_presupuesto`, `calc` (safe_eval), `buscar_en_criterios`.
- Escritura ✎ (con aprobación y permiso): `precio_cargar` (fila nueva, fuente `agente`), `presupuesto_crear`, `agregar_items`,
  `actualizar_por_indice` (propone nuevos precios según `indices_costo` entre dos períodos; cada uno es una fila nueva).
- Empresa, usuario y proyecto **del contexto de sesión**, nunca de argumentos. Montos que vuelve el agente: siempre de los servicios, no calculados por el modelo.
- Instrucciones: rioplatense, explica cada número con su origen (APU, precio y fecha), propone y espera aprobación, corre el verificador antes de sugerir emitir.
- Límites: rondas por run y consultas por hora configurables en `.env`.

## Criterios de aceptación
- [ ] CA1 Guion con modelo falso: buscar material → proponer `agregar_items` → queda pendiente; aprobar → los ítems existen y el total recalculado coincide al centavo.
- [ ] CA2 `calc` rechaza `__import__`, atributos y llamadas no permitidas (pruebas portadas de excel-wrapper).
- [ ] CA3 Aislamiento: herramientas con ids de otra empresa o de un proyecto sin acceso → "no encontrado"; nada ajeno en respuestas ni en `tool_calls`.
- [ ] CA4 Sin `MODELO_PRESUPUESTOS` con proveedor `openai` → 503 claro. Sensores y suite en verde (sin red).

## Fuera de alcance
- Cómputos desde Revit/AutoCAD (M4). Leer planillas de formato libre con IA.

## Bitácora del ejecutor

## Dictamen del auditor
