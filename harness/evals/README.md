# Evals (regresión del harness)

Dos niveles, del más barato al más caro:

1. **Sensores** — `tests/test_sensores.py`. Cada sensor nuevo trae un caso que lo hace disparar y
   uno que lo deja en silencio. Corre con pytest, sin base de datos.
2. **Tareas de repetición** — cuando un fallo no se puede atrapar con un sensor (p. ej. Codex se
   salió del alcance), se guarda acá `E-NNN-slug.md` con: la tarea original, el síntoma esperado y
   la rúbrica de aceptación. Al cambiar de modelo o de prompt, se re-ejecutan con
   `python -m scripts.harness codex` sobre una rama descartable y se comparan los dictámenes.

Formato de `E-NNN`:
```
---
id: E-NNN
origen: H-NNN
tarea: T-NNN
---
Repetir: (pedido exacto)
Falla si: (comportamiento que no debe volver a pasar)
Pasa si: (criterio observable)
```
