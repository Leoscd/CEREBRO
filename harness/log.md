# Registro del harness (trinquete)

Cada fallo real de un agente se anota acá. Solo se agrega una regla, sensor o hook cuando hay
una entrada que lo justifica. La columna **Supuesto** dice qué limitación del modelo cubre la
medida: al cambiar de modelo se revisa y se poda lo que ya no haga falta.

Formato: `H-NNN · fecha · tarea/PR · síntoma · causa raíz · medida (sensor/regla/hook/eval/ninguna) · supuesto · estado`

| ID | Fecha | Origen | Síntoma | Causa raíz | Medida | Supuesto | Estado |
|---|---|---|---|---|---|---|---|
| H-001 | 2026-11-21 | arranque | `POST /logout` sin CSRF; cualquier sitio puede cerrar la sesión del usuario | M0 se escribió sin sensor de CSRF | sensor `csrf` en `fast.py` + excepción temporal + tarea T-001 | El modelo olvida dependencias de seguridad en rutas nuevas | abierto (T-001) |
| H-002 | 2026-11-21 | arranque | Import sin usar en `app/services/correo.py` | Sin lint en el ciclo | sensor `ruff` (reglas F/E9 mínimas) | El modelo deja restos al refactorizar | cerrado |
| H-003 | 2026-11-21 | arranque (preventivo, reglas de CLAUDE.md) | — | Reglas de dominio solo en prosa | sensores `migracion-*`, `dinero`, `fecha`, `modelo-fijo`, `solo-openai`, `aislamiento` | Las reglas en prosa se olvidan con contexto largo | vigilar: si en 10 tareas no disparan, evaluar poda |
| H-004 | 2026-11-21 | T-001 (Codex local) | La carpeta compartida quedó en la rama `codex/T-001`; una rama nueva de Claude nació encima de trabajo sin mergear | Codex trabaja en la misma carpeta y no vuelve a `main` al terminar | regla en skill `ejecutar-tarea` (volver a `main`); preferir `harness codex` (worktree aparte) | El agente no considera que la carpeta es compartida | vigilar: si se repite, hook/sensor que avise rama ≠ main al empezar |
