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
| M2 | Presupuestos y precios | 3.5 | en-curso |
| M3 | Seguimiento de obra | 2.5 | en-curso |
| M4 | Conector y sesiones de trabajo | 3.5 | pendiente |
| M5 | Redes y Gerencia | 2.0 | en-curso |

## Notas de cierre
- **M1 (2026-11-23):** 14 tareas aprobadas (L-001, L-002). Recorrido en el navegador con datos demo: subida, visor en `#page=2`,
  búsqueda con cita, Documentador (modelo falso) con cita `[archivo, pág. 2]`, cliente sin acceso (404 y búsqueda vacía).
  **Pendiente:** una prueba del Documentador y los embeddings con la clave real de OpenAI (falta `.env` con la clave).
- **M1 reabierto (2026-11-24):** el plan incluye visores de DXF, IFC, 3D y ONLYOFFICE y Gotenberg, que no se hicieron; se marcó `hecho` antes de tiempo (error del auditor, H-012). Vuelve a `en-curso` hasta que se haga ese lote.
- **M1 (2026-11-27):** código completo con L-005 (T-037 a T-042, PRs #53-#55, #58, #60, #62): Gotenberg, DXF, IFC, visor 3D/IFC y ONLYOFFICE (lectura y edición con versión nueva). No se cierra todavía: falta probar en el VPS un DOCX real en Gotenberg, un IFC exportado de Revit, editar y guardar en un Document Server real, y el Documentador y los embeddings con la clave real de OpenAI.
- **M3 (2026-11-25):** código completo (L-004, 10 tareas, PRs #40-#48 y #50). Verificación del plan: pruebas portadas de obra-report-w, parte confirmado inmodificable y PDF numerado, con prueba. Recorrido: panel del Agente de Obra en el cronograma responde (modelo falso) y conserva el historial al recargar. No se cierra todavía: falta ver la tarjeta de aprobación del agente con la clave real de OpenAI (el modelo falso de desarrollo solo consulta).
- **M2 (2026-11-24):** código completo (L-003). No se cierra todavía: falta T-035 (formularios con opción vacía, 422) y ver la tarjeta de aprobación con la clave real de OpenAI.
