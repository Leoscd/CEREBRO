---
id: L-007
titulo: M5 — Redes y Gerencia
hito: M5
estado: abierto
etapa_activa: 0        # se habilita cuando L-006 esté en main
---

# Lote L-007 · M5 Redes y Gerencia

Codex: ejecutá las tareas de la etapa activa con la skill `.agents/skills/ejecutar-tarea/SKILL.md` ("Modo lote").
Con `etapa_activa: 0` no hay nada para hacer todavía.

Reglas del lote:
- Cada etapa es una cadena: la primera tarea sale de `main`; cada una de las siguientes sale de la rama de la anterior, con PR contra esa rama.
- Migraciones en orden: `0017` (T-045), `0018` (T-046, solo si hace falta), y T-050 toma el número libre siguiente.
- **Solo OpenAI** en los agentes (`MODELO_REDES`, `MODELO_GERENCIA`). Sin descargas nuevas: Pillow, PyJWT y el SDK de agentes ya están.
- Fuera de M5 por ahora: el borrador automático de redes desde el cierre de sesión (depende de M4).

## Etapa 1 — Redes (solo si `etapa_activa: 1`)
| Orden | Tarea | Depende de |
|---|---|---|
| 1 | `harness/tareas/T-045-contenidos-de-redes-y-fotos-difundibles.md` | — (sale de `main`) |
| 2 | `harness/tareas/T-046-carrusel-1080x1350-y-kit-de-publicacion.md` | T-045 |
| 3 | `harness/tareas/T-047-agente-redes.md` | T-046 |

**PARADA 1:** PRs de T-045 a T-047 abiertos con CI en verde → pará y reportá.

## Etapa 2 — Gerencia y notificaciones (solo si `etapa_activa: 2`)
| Orden | Tarea | Depende de |
|---|---|---|
| 4 | `harness/tareas/T-048-tablero-de-gerencia.md` | — (etapa 1 en `main`: sale de `main`) |
| 5 | `harness/tareas/T-049-agente-gerencia.md` | T-048 |
| 6 | `harness/tareas/T-050-notificaciones.md` | T-049 |

**PARADA 2 (fin de M5):** PRs de T-048 a T-050 abiertos con CI en verde → pará y reportá.

## Cuándo parar antes
- CI rojo que no lográs arreglar en 3 intentos.
- Una tarea pide tocar algo de su "No tocar" o un archivo protegido.
- Necesitás instalar o descargar algo, o leer archivos fuera del repo que no estén nombrados en la tarea: pedí permiso y esperá.
- Un cuadro de Gerencia o un total no coincide con la cuenta a mano: **no ajustes la prueba**; pará y explicá la diferencia.
- El auditor dejó **CAMBIOS** en un PR: resolvelos primero y traé el arreglo a las ramas siguientes con `git merge`.
