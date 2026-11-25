---
id: L-004
titulo: M3 — seguimiento de obra (+ T-027 de M2)
hito: M3
estado: cerrado
etapa_activa: 2        # etapa 1 mergeada el 2026-11-24 (PRs #40-#48); etapa 2 (T-034) mergeada el 2026-11-25 (#50)
---

# Lote L-004 · M3 seguimiento de obra

Codex: ejecutá las tareas de la etapa activa con la skill `.agents/skills/ejecutar-tarea/SKILL.md` ("Modo lote").
- **T-027 es independiente:** sale de `main` y abre su PR contra `main`. Hacela primero (es chica).
- **T-028 a T-033 son una cadena:** T-028 sale de `main`; cada una de las siguientes sale de la rama de la anterior con PR contra esa rama.
- Migraciones en orden: 0013 (T-028), 0014 (T-029), 0015 (T-031), 0016 (T-032), 0017 (T-033, solo si hace falta).
- **obra-report-w** (`D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w`) es referencia para portar lógica y pruebas. **Solo OpenAI**: lo de Anthropic, Groq o Telegram no se porta.
  En cada tarea, listá en la Bitácora qué pruebas portaste y de qué archivo (lo pide la verificación de M3 del plan).

## Etapa 1 — certificados exactos, cronograma, parte diario, PDF, clima/audio, materiales y bitácora
| Orden | Tarea | Depende de |
|---|---|---|
| 1 | `harness/tareas/T-027-certificados-cierran-exacto.md` | — |
| 2 | `harness/tareas/T-028-cronograma-de-obra.md` | — |
| 3 | `harness/tareas/T-029-parte-diario.md` | T-028 |
| 4 | `harness/tareas/T-030-pdf-del-parte.md` | T-029 |
| 5 | `harness/tareas/T-031-clima-y-audio.md` | T-030 |
| 6 | `harness/tareas/T-032-notas-pedidos-y-alertas.md` | T-031 |
| 7 | `harness/tareas/T-033-bitacora-y-resumen-de-obra.md` | T-032 |
| 8 | `harness/tareas/T-035-formularios-con-opcion-vacia.md` | — (sale de `main`, PR contra `main`) |
| 9 | `harness/tareas/T-036-numeros-en-formato-argentino.md` | T-035 |

T-035 y T-036 salieron del recorrido de M2 en el navegador (agregadas el 2026-11-24). Si ya estás en la cadena de M3, terminala y después hacé estas dos.

**PARADA 1:** cuando T-027, T-028 a T-033, T-035 y T-036 tengan su PR abierto con CI en verde, pará y reportá la lista de PRs.

## Etapa 2 — agente (solo si `etapa_activa: 2`)
| Orden | Tarea | Depende de |
|---|---|---|
| 10 | `harness/tareas/T-034-agente-obra.md` | — (etapa 1 en `main`: sale de `main`, PR contra `main`) |

**PARADA 2 (fin de M3):** PR de T-034 abierto con CI en verde → pará y reportá.

## Cuándo parar antes
- CI rojo que no lográs arreglar en 3 intentos.
- Una tarea pide tocar algo de su "No tocar" o un archivo protegido.
- Un total "calculado a mano" no coincide y no encontrás por qué: **no ajustes la prueba**; pará y explicá la diferencia.
- Necesitás instalar algo o descargar de internet que no esté en la tarea: pedí permiso y esperá.
- La prueba de humo de Compose se pone roja (T-030 toca el montaje del worker): resolvelo antes de seguir.
- El auditor dejó **CAMBIOS** en un PR: resolvelos primero y traé el arreglo a las ramas siguientes con `git merge`.
