# Harness del GSP

Cómo trabajamos con dos agentes sin perder el control: **Codex ejecuta, Claude audita, Leo decide.**

```
Leo ── pedido ──▶ Claude (planifica)  ──▶ harness/tareas/T-NNN.md  (estado: lista)
                                              │
                         Codex (cloud o local) ▼  rama codex/T-NNN-slug
                     implementa · prueba · sensores · abre PR
                                              │
                       GitHub Actions ◀───────┘  protegidos + fast + pytest
                                              │ (verde)
                     Claude audita el paquete del PR contra la rúbrica
                                              │ APROBAR / CAMBIOS / RECHAZAR
                               Leo mergea ◀───┘  (nadie más puede)
                                              │
                  fallo real → harness/log.md → sensor / regla / candidato
```

## Roles (separación generador / evaluador)
| Rol | Quién | Puede | No puede |
|---|---|---|---|
| Decide | Leo | priorizar, mergear, promover reglas | — |
| Planifica y audita | Claude (`.claude/skills/`) | escribir tareas, auditar PRs, registrar fallos | mergear, escribir el código de la tarea |
| Ejecuta | Codex (`.agents/skills/ejecutar-tarea`) | código, pruebas, su archivo de tarea, candidatos | tocar el harness (lo frena `scripts/checks/protegidos.py` en CI) |

## Ciclo de una tarea
1. `python -m scripts.harness nueva "Título"` → Claude completa la tarea con la skill `escribir-tarea` y la pasa a `lista`.
2. A Codex se le da **una sola línea**: `Ejecutá harness/tareas/T-NNN-....md` (en Codex cloud) o
   `python -m scripts.harness codex T-NNN` (en la PC). El resto lo lee del repo.
3. CI corre los sensores. Rojo → Codex corrige solo, sin intervención.
4. Verde → Claude corre `python -m scripts.harness auditar <PR>` (paquete compacto) y dictamina con la skill `auditar-pr`.
5. Leo mergea. Si había migración nueva: `python -m scripts.harness sellar`.

## Los cinco bloques y dónde viven
1. **Contexto (feedforward):** `AGENTS.md` corto = mapa de punteros. Skills con divulgación progresiva en
   `.agents/skills/` (Codex) y `.claude/skills/` (Claude). La tarea trae punteros, no copias.
   Exploración pesada → subagentes. Nada de MCPs para lo que una CLI corta resuelve (`gh`, `scripts.harness`).
2. **Sensores (feedback):** `scripts/checks/fast.py` (segundos, silencioso si pasa), `full.py` (+pytest),
   `protegidos.py` (puerta). Hooks de Claude en `.claude/settings.json` → `scripts/hooks/`.
   CI en `.github/workflows/ci.yml`. El juicio humano/LLM va solo a los ítems `[juez]` de la rúbrica.
3. **Trinquete:** `harness/log.md`. Solo se agrega regla/sensor/hook después de un fallo real.
   Cada fallo que se puede automatizar se vuelve prueba en `tests/test_sensores.py` o caso en `harness/evals/`.
4. **Memoria en 4 capas:**
   - *Trabajo:* el archivo de la tarea (sección Bitácora) y la descripción del PR.
   - *Episódica:* PRs y revisiones en GitHub; corridas locales en `.harness-runs/` (no versionado, TTL 30 días: `harness podar`).
   - *Semántica:* `docs/` (plan, decisiones). Cada doc lleva `revisado: AAAA-MM-DD`; `harness estado` avisa si pasó de 90 días.
   - *Procedimental:* `AGENTS.md`, skills y esta carpeta. Versionado, editado solo por humanos vía PR.
5. **Promoción:** los agentes proponen en `harness/candidatos/`. Un candidato pasa a oficial cuando
   (a) lo respalda ≥2 episodios del log o una prueba que falla sin él, y (b) Leo lo aprueba en una rama `harness/...`.
   **Poda:** al cambiar de modelo, se recorre la columna "Supuesto" del log y se retira lo que el modelo ya resuelve solo.

## Comandos
```
python -m scripts.harness estado            # tareas, candidatos, docs vencidos, migraciones sin sellar
python -m scripts.harness nueva "Título"    # crea T-NNN desde la plantilla
python -m scripts.harness codex T-NNN       # corre Codex en la PC en un worktree y abre el PR
python -m scripts.harness auditar 12        # paquete compacto del PR #12 para el auditor
python -m scripts.harness sellar            # sella migraciones tras el merge
python -m scripts.harness podar             # borra corridas locales viejas
python -m scripts.checks.fast               # sensores rápidos
```
