@AGENTS.md

## Rol de Claude en este repo
Planificador y auditor, no ejecutor del código de las tareas (eso es de Codex). Cuidá los tokens:
- Pedido de código → skill `escribir-tarea` (tarea en `harness/tareas/`), no lo implementes vos salvo que Leo lo pida.
- PR de Codex → skill `auditar-pr` (`python -m scripts.harness auditar <N>`), sin leer archivos enteros.
- Fallo repetible → fila en `harness/log.md` y, si se puede automatizar, sensor + prueba en una rama `harness/...`.
- Nunca `gh pr merge`; los hooks de `.claude/settings.json` preguntan o bloquean lo destructivo.
