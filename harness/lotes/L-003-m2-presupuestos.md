---
id: L-003
titulo: M2 — presupuestos y precios
hito: M2
estado: abierto
etapa_activa: 1
---

# Lote L-003 · M2 presupuestos y precios

Codex: ejecutá las tareas de la etapa activa con la skill `.agents/skills/ejecutar-tarea/SKILL.md` ("Modo lote").
**Cadena lineal:** cada tarea sale de la rama de la anterior y abre su PR con base en esa rama (salvo T-016, que sale de `main`).
Las migraciones van en orden: 0007 (T-017), 0008 (T-018), 0009 (T-019), 0010 (T-022, solo si hace falta).

## Etapa 1 — dinero, catálogo, APU, presupuestos, verificador, Excel y aprobaciones
| Orden | Tarea | Depende de |
|---|---|---|
| 1 | `harness/tareas/T-016-dinero-en-centavos.md` | — |
| 2 | `harness/tareas/T-017-catalogo-y-precios-con-historial.md` | T-016 |
| 3 | `harness/tareas/T-018-apus.md` | T-017 |
| 4 | `harness/tareas/T-019-presupuestos.md` | T-018 |
| 5 | `harness/tareas/T-020-verificador-de-presupuestos.md` | T-019 |
| 6 | `harness/tareas/T-021-excel-de-presupuestos.md` | T-020 |
| 7 | `harness/tareas/T-022-aprobaciones-de-agentes.md` | T-021 |

**PARADA 1:** cuando el PR de T-022 esté abierto con CI en verde, pará y reportá la lista de PRs con su estado.

## Etapa 2 — agente (solo si `etapa_activa: 2`)
| Orden | Tarea | Depende de |
|---|---|---|
| 8 | `harness/tareas/T-023-agente-presupuestos.md` | T-022 |

**PARADA 2 (fin de M2):** PR de T-023 abierto con CI en verde → pará y reportá.

## Cuándo parar antes
- CI rojo que no lográs arreglar en 3 intentos.
- Una tarea pide tocar algo de su "No tocar" o un archivo protegido.
- Un total "calculado a mano" no coincide con el sistema y no encontrás por qué: **no ajustes la prueba para que pase**; pará y explicá la diferencia.
- Necesitás instalar algo o descargar de internet que no esté en la tarea: pedí permiso y esperá.
- El auditor dejó **CAMBIOS** en un PR: resolvelos primero y traé el arreglo a las ramas siguientes con `git merge`.
