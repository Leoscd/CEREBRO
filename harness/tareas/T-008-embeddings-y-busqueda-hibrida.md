---
id: T-008
titulo: Embeddings y búsqueda híbrida
estado: lista
rama: codex/T-008-embeddings-y-busqueda-hibrida
creada: 2026-11-21
depende: T-007
pr:
---

## Objetivo
Buscar por significado además de por palabras, combinando las dos listas, con el filtro de acceso aplicado
antes de comparar vectores.

## Contexto mínimo
- `chunks.embedding vector(384)` y `busqueda.buscar_palabras` (T-007). Cola: `app/services/jobs.py`.
- Regla: **solo OpenAI** y **modelo desde `.env`** (el sensor `modelo-fijo` rechaza nombres de modelo escritos en `app/`).

## Alcance
- Tocar: `app/services/embeddings.py` (nuevo), `app/services/busqueda.py`, `app/worker.py`, `app/config.py`, `.env.example`,
  `app/db/migraciones/0005_indice_vectorial.sql` (nuevo), `requirements.txt` (`openai`, versión fija), `tests/test_hibrida.py` (nuevo),
  `tests/conftest.py` (solo para forzar el proveedor falso).

## Diseño pedido
- Config (`.env.example` documentado): `EMBEDDINGS_PROVEEDOR` (`openai` | `falso`), `MODELO_EMBEDDINGS` (sin valor por defecto en el código),
  `EMBEDDINGS_DIMENSIONES=384`. Si el proveedor es `openai` y falta el modelo o la clave → error claro al usarlo, no al arrancar.
- `embeddings.embeber(textos) -> list[list[float]]`: con OpenAI usa el parámetro `dimensions`; lotes de hasta 100; reintento ante 429/5xx.
  `falso`: vector determinístico (hash de palabras normalizadas) para que textos parecidos queden cerca. **Las pruebas nunca salen a la red.**
- Manejador `chunks.embeber`: toma chunks de una versión sin embedding y los completa. Se encola al terminar `archivo.indexar`.
- `0005`: índice HNSW `vector_cosine_ops` sobre `chunks.embedding`.
- `busqueda.buscar(db, u, proyecto, consulta, limite=10)`: palabras + vectores, fusión por rango recíproco (RRF, k=60).
  Mismo filtro de acceso que T-007 **en el WHERE de cada subconsulta**. Suma chunks de `biblioteca_documentos` aprobados
  **de la misma empresa**, marcados como "Biblioteca". La ruta `/buscar` de T-007 pasa a usar esta función.

## Criterios de aceptación
- [ ] CA1 Con el proveedor falso, una consulta con sinónimo/variación encuentra el fragmento que la búsqueda por palabras sola no encuentra (armá el caso a propósito).
- [ ] CA2 Un chunk de la empresa B con **el mismo vector exacto** que la consulta nunca aparece para A (prueba del filtro previo).
- [ ] CA3 Chunks de biblioteca aprobados de A aparecen para ana y beto; borradores o retirados, no; los de B, nunca.
- [ ] CA4 Sin `MODELO_EMBEDDINGS` y proveedor `openai`, `embeber` lanza un error con mensaje que dice qué variable falta.
- [ ] CA5 Sensores y suite en verde (sin red).

## Fuera de alcance
- Re-ranking con un modelo. Embeddings de imágenes.

## Bitácora del ejecutor

## Dictamen del auditor
