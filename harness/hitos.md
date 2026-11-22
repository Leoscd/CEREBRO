# Hitos del plan (fuente de la barra de avance)

Lo lee la barra de avance (mod `avance-gsp`) para calcular el porcentaje del proyecto. Lo edita solo Leo
(o Claude a pedido de Leo, en una rama `harness/...`); los agentes no lo tocan.

- **Semanas:** el punto medio de la estimación de `docs/PLAN.md` → "Hitos". Es el peso de cada hito en el total.
- **Estado:** `hecho` (cuenta entero), `en-curso` (cuenta según sus tareas hechas), `pendiente` (no cuenta).
- Un hito `en-curso` mide su avance con las tareas de los lotes que dicen `hito: <ID>` en `harness/lotes/`.

| ID | Hito | Semanas | Estado |
|---|---|---|---|
| S0 | Spike de riesgo de Codex (app-server, Revit, AutoCAD) | 0.8 | pendiente |
| M0 | Fundaciones (auth, permisos, proyectos, auditoría, deploy) | 1.5 | hecho |
| M1 | Archivos, visores, RAG de dos niveles y Documentador | 2.5 | en-curso |
| M2 | Presupuestos y precios | 3.5 | pendiente |
| M3 | Seguimiento de obra | 2.5 | pendiente |
| M4 | Conector y sesiones de trabajo | 3.5 | pendiente |
| M5 | Redes y Gerencia | 2.0 | pendiente |
