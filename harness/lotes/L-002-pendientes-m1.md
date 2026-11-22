---
id: L-002
titulo: Pendientes de la auditoría de M1
hito: M1
estado: abierto
etapa_activa: 1
---

# Lote L-002 · pendientes de la auditoría de M1

Codex: ejecutá las tareas de la etapa activa con la skill `.agents/skills/ejecutar-tarea/SKILL.md` ("Modo lote").
**Son independientes entre sí:** cada una sale de `main` y abre su PR **contra `main`** (no encadenes ramas).
Hacelas en el orden de la tabla (la primera es la más importante).

## Etapa 1
| Orden | Tarea | Depende de |
|---|---|---|
| 1 | `harness/tareas/T-011-documentador-sin-retener-conexion.md` | — |
| 2 | `harness/tareas/T-012-almacen-sin-huerfanos.md` | — |
| 3 | `harness/tareas/T-013-router-de-busqueda.md` | — |
| 4 | `harness/tareas/T-014-prueba-de-humo-compose.md` | — |
| 5 | `harness/tareas/T-015-verificar-pdfjs-vendorizado.md` | — |

**PARADA:** cuando las 5 tengan su PR abierto con CI en verde, pará y reportá la lista de PRs.

## Cuándo parar antes
- CI rojo que no lográs arreglar en 3 intentos.
- Una tarea pide tocar algo de su "No tocar" o un archivo protegido.
- T-015 encuentra un archivo de pdf.js que **no** coincide con el paquete oficial: pará todo y reportalo (posible manipulación).
- El auditor dejó **CAMBIOS** en un PR: resolvelos primero y después seguí.
