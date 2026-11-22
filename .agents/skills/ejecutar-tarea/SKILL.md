---
name: ejecutar-tarea
description: Ejecuta una tarea del harness (harness/tareas/T-NNN-*.md) de punta a punta - rama, implementación, pruebas, sensores y PR. Usala siempre que te pidan "ejecutá T-NNN" o te pasen la ruta de una tarea.
---

# Ejecutar una tarea del harness

Sos el **ejecutor**. Otro agente audita tu PR contra `harness/rubricas/general.md` y Leo decide el merge.
Tu trabajo es dejar un PR chico, verde y fácil de auditar.

## Pasos
1. **Leé la tarea** completa y solo los archivos de "Contexto mínimo". No explores el repo entero.
   Si falta información para cumplir un criterio, anotalo en la Bitácora y seguí con lo demás.
2. **Rama:** `codex/T-NNN-slug` (la que dice el frontmatter) desde `main`. Si ya estás en una rama
   creada por la plataforma (Codex cloud), usala.
3. En el archivo de la tarea: `estado: en-curso`.
4. **Primero la prueba:** escribí la prueba de cada criterio de aceptación y verificá que falla.
5. **Implementá lo mínimo** para que pase. Respetá el Alcance: si tenés que tocar algo de "No tocar",
   pará y explicalo en la Bitácora.
6. **Sensores**, en este orden, hasta que estén limpios:
   - `python -m scripts.checks.fast` → tiene que no imprimir nada.
   - `python -m pytest -q` → todo verde (incluye `tests/test_permisos.py`).
   Si un sensor falla, su mensaje dice QUÉ y CÓMO: seguilo. No desactives ni "arregles" el sensor.
7. **Bitácora** (en la tarea): decisiones, supuestos, dudas y lo que no hiciste. Corto.
8. `estado: en-revision` y `pr: #N` cuando lo abras.
9. **PR** con la plantilla `.github/pull_request_template.md`. Título: `T-NNN: <titulo>`.
   En "Notas para el auditor" decí qué mirar con lupa: eso ahorra la revisión.
   Commits chicos con mensajes en español (`T-001: logout exige CSRF`).

## Prohibido (CI te frena igual)
- Editar `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/`, `.github/`, `scripts/checks/`, `scripts/hooks/`,
  `scripts/harness.py`, `harness/README.md`, `harness/rubricas/`, `harness/log.md`, `harness/evals/`.
- Editar una migración ya existente: siempre una nueva con el número siguiente.
- Agregar dependencias que la tarea no pide.
- Mergear o pushear a `main`.

## Si aprendiste algo
Si tropezaste con algo que una regla o un sensor habría evitado, escribí una propuesta en
`harness/candidatos/C-NNN-slug.md` (formato en `harness/candidatos/README.md`). No la apliques vos.

## Si te piden cambios
El auditor deja una lista numerada en el PR. Resolvé cada punto en la misma rama, respondé
punto por punto en el PR y volvé a correr los sensores. Si hay ramas que dependen de esa, traé el
arreglo con `git merge` (nunca push forzado ni rebase de ramas ya publicadas).

## Modo lote (`harness/lotes/L-NNN-*.md`)
Cuando te pidan "ejecutá el lote L-NNN":
1. Antes de empezar: `git switch main && git pull`. Leé el lote y ejecutá **solo la etapa activa**, en el orden de la tabla.
2. Cada tarea va en su rama y su PR. **No esperes la auditoría** entre tareas de la misma etapa: encadenalas.
   - Si la tarea anterior ya está mergeada en `main`: rama nueva desde `main`, PR contra `main`.
   - Si todavía no: rama nueva **desde la rama de la anterior** y PR con **base = la rama de la anterior**
     (`gh pr create --base codex/T-ANTERIOR-...`), así cada PR muestra solo su diff. En el cuerpo: "Depende de #N".
3. Antes de abrir cada PR, sensores y suite en verde. Después de abrirlo, esperá el CI; si falla, arreglalo en esa rama.
4. Respetá las **PARADAS** y los motivos de "parar antes" del lote. Al parar, reportá: tarea · PR · estado de CI · dudas.
5. Nunca cambies el lote (es del harness): la etapa la habilita Leo.
6. Al parar o terminar: `git switch main`. La carpeta se comparte con Leo y con Claude; no la dejes en tu rama.
