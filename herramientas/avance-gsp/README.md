# avance-gsp — barra de avance del proyecto

Mod de Claude Code que dibuja, arriba del prompt, una barra horizontal con el avance del plan del GSP:

```
Avance GSP ████▓░░░░░░░░░░░░░░░░░░░  19% del plan
Ahora: M1 Archivos, visores… › L-002 Pendientes de la auditoría de M1 › T-011 Documentador… (lista)
✓ 10 aprobadas · ◐ 0 en revisión · ○ 5 por hacer · faltan S0, M2, M3, M4, M5
```

- **Verde** (█): hecho y aprobado. **Amarillo** (▓): en revisión o en curso. **Gris** (░): lo que falta.
- **Porcentaje:** semanas de los hitos `hecho` + la parte hecha del hito `en-curso` (sus tareas `hecha` sobre el total
  de las tareas de los lotes con `hito: <ID>`), sobre el total de semanas del plan.
- **Fuentes:** `harness/hitos.md` (hitos, peso y estado), `harness/lotes/*.md` (`hito`, `estado`, tareas del lote) y
  `harness/tareas/T-*.md` (`estado`). Se relee al empezar la sesión, al mandar cada mensaje y al terminar cada turno.
- Fuera de este repo (sin `harness/hitos.md`) no dibuja nada.

## Cómo se carga en todas las sesiones
`~/.claude/settings.json` → `"env": { "CLAUDE_CODE_PLUGIN_DIRS": "<ruta a esta carpeta>" }`. Toma efecto en las
sesiones nuevas. Para quitarla: borrar esa entrada (o plegar la banda con `[-]` / ctrl+x ctrl+a).

## Para mover la barra
Cambiá el `Estado` de un hito en `harness/hitos.md` (en una rama `harness/...`) cuando se cierre o arranque.
Las tareas y lotes ya los actualizan Codex y el auditor en el flujo normal.

Pruebas: `claude plugin test herramientas/avance-gsp` (con un Claude Code 2.1.330 o más nuevo).
