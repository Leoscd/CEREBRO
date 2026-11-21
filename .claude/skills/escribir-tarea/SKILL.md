---
name: escribir-tarea
description: Convierte un pedido de Leo en una tarea del harness lista para que Codex la ejecute (harness/tareas/T-NNN-*.md). Usala cuando Leo pida "armá la tarea", "pasale a Codex", "planificá X" o cuando un trabajo de código vaya a delegarse.
---

# Escribir una tarea para Codex

Objetivo: que Codex la ejecute **sin preguntar** y que la auditoría sea mecánica. Gastá tokens acá, no en revisar después.

1. `python -m scripts.harness nueva "Título corto"` → crea el archivo desde la plantilla.
2. Leé solo lo necesario para dar **punteros exactos** (archivo, función, línea). Si hay que explorar
   mucho, usá un subagente Explore y quedate con su resumen.
3. Completá:
   - **Objetivo** en 1-3 líneas, desde el usuario.
   - **Contexto mínimo:** punteros, no copias de código.
   - **Alcance:** qué tocar y qué NO (lo segundo evita la mayoría de los rechazos).
   - **Criterios de aceptación** verificables, cada uno con su prueba. Siempre incluir aislamiento
     (otra empresa → 404) si la tarea toca datos de negocio.
   - **Fuera de alcance.**
4. Tamaño: un PR de ≤ ~300 líneas. Si es más grande, partila en T-NNN, T-NNN+1 con dependencias explícitas.
5. Si la tarea va a necesitar una excepción en un archivo protegido (p. ej. `post_sin_csrf.txt`),
   decilo en Alcance: lo hace el auditor, no Codex.
6. `estado: lista`. A Leo le das la línea para Codex: `Ejecutá harness/tareas/T-NNN-slug.md`.
