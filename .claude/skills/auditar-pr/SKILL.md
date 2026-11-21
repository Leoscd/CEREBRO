---
name: auditar-pr
description: Audita un PR de Codex contra la tarea y la rúbrica del harness, gastando pocos tokens, y emite APROBAR / CAMBIOS / RECHAZAR. Usala cuando Leo diga "revisá el PR N", "auditá lo de Codex" o llegue un PR de una rama codex/.
---

# Auditar un PR de Codex

Sos el **evaluador**, no el autor: no reescribas el código, juzgalo. El merge es de Leo.

## Paso 1 — paquete compacto (una sola llamada)
`python -m scripts.harness auditar <N>`
Trae: tarea, estado de CI, archivos tocados, violaciones de alcance y el diff recortado (primero lo sensible).
**No** leas archivos enteros ni corras la suite: CI ya lo hizo. Abrí un archivo completo solo si un
fragmento del diff es ambiguo, y solo esa zona (`Read` con offset/limit).

## Paso 2 — juicio
- Si CI está rojo o pendiente: no audites. Respondé "esperando CI" o pasá el error tal cual a Codex.
- Evaluá **solo los ítems `[juez]`** de `harness/rubricas/general.md` y los CA de la tarea.
  Los `[sensor]` ya los garantiza CI.
- Revisá "Notas para el auditor" y la Bitácora: ahí está lo que el ejecutor duda.

## Paso 3 — dictamen
Escribí en el chat (y en "Dictamen del auditor" de la tarea):
```
DICTAMEN: APROBAR | CAMBIOS | RECHAZAR
Bloqueantes: (o "ninguno")
1. archivo:línea → qué hacer
Calidad (no bloquea):
- ...
Para el harness: (fallo repetible → H-NNN propuesto, o "nada")
```
Publicarlo en GitHub (`gh pr review <N> --comment -F archivo` o `--request-changes`) solo si Leo lo pide.
Nunca `gh pr merge`.

## Paso 4 — trinquete
Si el fallo fue de un tipo que una máquina podría atrapar o que ya pasó antes:
1. Agregá una fila a `harness/log.md` (síntoma, causa raíz, medida, supuesto).
2. Si la medida es un sensor: escribilo en `scripts/checks/fast.py` + su caso en `tests/test_sensores.py`,
   en una rama `harness/...` (no en la rama de Codex). Si es una regla de prosa: candidato en `harness/candidatos/`.
3. Después del merge con migraciones nuevas: `python -m scripts.harness sellar`.
   Si la tarea tenía una excepción temporal (p. ej. en `post_sin_csrf.txt`), sacala.
