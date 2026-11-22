# Registro del harness (trinquete)

Cada fallo real de un agente se anota acá. Solo se agrega una regla, sensor o hook cuando hay
una entrada que lo justifica. La columna **Supuesto** dice qué limitación del modelo cubre la
medida: al cambiar de modelo se revisa y se poda lo que ya no haga falta.

Formato: `H-NNN · fecha · tarea/PR · síntoma · causa raíz · medida (sensor/regla/hook/eval/ninguna) · supuesto · estado`

| ID | Fecha | Origen | Síntoma | Causa raíz | Medida | Supuesto | Estado |
|---|---|---|---|---|---|---|---|
| H-001 | 2026-11-21 | arranque | `POST /logout` sin CSRF; cualquier sitio puede cerrar la sesión del usuario | M0 se escribió sin sensor de CSRF | sensor `csrf` en `fast.py` + excepción temporal + tarea T-001 | El modelo olvida dependencias de seguridad en rutas nuevas | cerrado (T-001, PR #1) |
| H-002 | 2026-11-21 | arranque | Import sin usar en `app/services/correo.py` | Sin lint en el ciclo | sensor `ruff` (reglas F/E9 mínimas) | El modelo deja restos al refactorizar | cerrado |
| H-003 | 2026-11-21 | arranque (preventivo, reglas de CLAUDE.md) | — | Reglas de dominio solo en prosa | sensores `migracion-*`, `dinero`, `fecha`, `modelo-fijo`, `solo-openai`, `aislamiento` | Las reglas en prosa se olvidan con contexto largo | vigilar: si en 10 tareas no disparan, evaluar poda |
| H-004 | 2026-11-21 | T-001 (Codex local) | La carpeta compartida quedó en la rama `codex/T-001`; una rama nueva de Claude nació encima de trabajo sin mergear | Codex trabaja en la misma carpeta y no vuelve a `main` al terminar | regla en skill `ejecutar-tarea` (volver a `main`); preferir `harness codex` (worktree aparte) | El agente no considera que la carpeta es compartida | vigilar: si se repite, hook/sensor que avise rama ≠ main al empezar |
| H-005 | 2026-11-22 | Claude, limpieza tras merge | El hook `guardia` bloqueó el borrado seguro de ramas (`-d`) | Los patrones se evalúan sin distinguir mayúsculas y `-d` coincidía con `-D` | patrón con `(?-i:-D)` + prueba `test_guardia_distingue_borrado_seguro_de_forzado` | — (error del harness, no del modelo) | cerrado |
| H-006 | 2026-11-22 | Auditoría #4 y #12 | `auditar` marcó "fuera de 'Tocar'" archivos que sí estaban permitidos | La lista "Tocar" ocupa varios renglones y se leía solo el primero | `rutas_tocar()` lee hasta "- No tocar:" + prueba `test_rutas_tocar_multilinea` | — (error del harness) | cerrado |
| H-007 | 2026-11-22 | Merge del lote L-001 | Al mergear #3 y borrar su rama, GitHub **cerró** #4 en vez de re-apuntarlo | Borrar por API la base de un PR abierto lo cierra | procedimiento en `harness/README.md` (merge común, re-apuntar antes, borrar ramas al final); se restauró la rama y se reabrió #4 | — (proceso) | cerrado |
| — | 2026-11-22 | Lote L-001 (9 PRs) | Ningún sensor disparó en CI; ninguna violación de protegidos; Codex respetó paradas y volvió a `main` (H-004 no se repitió) | — | ninguna | Evidencia para H-003: los sensores de dominio todavía no atraparon nada (1 de 10 tareas) | registro |
| H-008 | 2026-11-22 | Auditoría #16 (T-011) | Codex definió en `agentes.py` una función local `check_csrf` (legítima, envuelve a la de `app.security`); el sensor la habría aceptado igual si no validara nada | El sensor `csrf` confiaba en el **nombre** de la dependencia | `_dependencias_csrf`: solo vale el `check_csrf` importado de `app.security` o funciones que dependan de él o lo llamen + prueba `test_csrf_no_se_engana_con_el_nombre` | El modelo puede envolver o sombrear funciones de seguridad | cerrado |
| — | 2026-11-22 | Lote L-002 (4 de 5 PRs) | T-015 no se empezó (sin rama ni PR); el resto, CI verde y sin protegidos | Probable: necesitaba permiso de descarga (npm) | ninguna todavía: preguntar a Codex el motivo | — | abierto |
