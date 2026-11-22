---
id: T-007
titulo: Texto de los PDF e índice por palabras
estado: hecha
rama: codex/T-007-texto-e-indice-por-palabras
creada: 2026-11-21
depende: T-006
pr: "#9"
---

## Objetivo
Extraer el texto de los PDF del proyecto, partirlo en fragmentos con su página y poder buscar por palabras
desde la ficha, respetando quién ve qué.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "RAG: proyecto + conocimiento y criterios" y "Modelo de datos" (RAG: `chunks`, `biblioteca_documentos`).
- Cola y worker: `app/services/jobs.py`, `app/worker.py` (T-006). Visibilidad: `archivos_visibles_sql` (`app/permisos.py`).

## Alcance
- Tocar: `app/db/migraciones/0004_rag.sql` (nuevo), `app/services/texto.py` (nuevo), `app/services/busqueda.py` (nuevo),
  `app/worker.py` (registrar manejador), `app/routers/archivos.py` (encolar), `app/routers/proyectos.py` (ruta de búsqueda),
  `app/templates/buscar.html` (nuevo), `app/templates/proyecto.html` (caja de búsqueda), `requirements.txt` (`pypdf`, versión fija),
  `tests/fixtures/` (PDF de prueba), `tests/test_busqueda.py` (nuevo).

## Diseño pedido
- `biblioteca_documentos`: id, empresa_id, titulo, tipo ('normativa','criterio','pliego','leccion'), version text,
  estado ('borrador','aprobado','retirado'), sha256, nombre_archivo, subido_por, aprobado_por, aprobado_en, creado_en.
- `chunks`: id, empresa_id, `proyecto_id` null, `version_id` null (→ versiones_archivo), `biblioteca_id` null, pagina int, orden int,
  texto, `tsv tsvector GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED`, `embedding vector(384)` null, creado_en.
  CHECK: o (proyecto_id y version_id) o biblioteca_id, nunca ambos. Índice GIN en tsv; índice por (empresa_id, proyecto_id).
- Manejador `archivo.indexar` (se encola junto con `archivo.analizar` cuando el archivo es PDF): texto por página con pypdf,
  fragmentos de ~1000 caracteres con solapamiento ~150 sin cortar palabras, cada uno con su página.
  Al indexar una versión nueva se borran los chunks de las versiones anteriores de ese archivo. PDF sin texto → derivados `{"texto": "sin_texto"}`.
- `busqueda.buscar_palabras(db, u, proyecto, consulta, limite=20)`: el filtro de empresa, proyecto y visibilidad del archivo
  (cliente / papelera) va **en el WHERE**, antes de ordenar. Devuelve archivo_id, nombre, página, fragmento resaltado (`ts_headline`).
- `GET /proyectos/{codigo}/buscar?q=` → resultados con enlace a `/archivos/{id}#page=N`.
- PDF de prueba: generalo con un script chico en `tests/fixtures/` (sin dependencias nuevas de prueba) o commitealo; 2 páginas,
  una frase única en la página 2.

## Criterios de aceptación
- [x] CA1 Subir el PDF de prueba a p1 y correr el worker `--una-vez` → la búsqueda de la frase única devuelve ese archivo, página 2.
- [x] CA2 La misma búsqueda como admin B, como ana sobre p2, o como cliente con el archivo no visible → sin resultados (o 404 si el proyecto no es suyo).
- [x] CA3 Archivo en papelera → no aparece. Versión nueva sin la frase → la frase ya no aparece.
- [x] CA4 Fragmentos: ninguno vacío, ninguno corta una palabra al medio, todos con página ≥ 1.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- Embeddings y búsqueda híbrida (T-008). Pantalla de biblioteca (T-009). Office/DXF/IFC como texto.

## Bitácora del ejecutor
- Los cuatro casos iniciales fallaron antes de implementar. Pasaron 58 pruebas y el sensor rápido terminó sin salida.
- Se detecta PDF por cabecera y marcador de final. La migración encola también versiones PDF vigentes preexistentes.
- El índice y la búsqueda conservan la página. Se valida la versión vigente al escribir y al buscar. Los resaltados escapan el texto extraído antes de insertar las etiquetas mark.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-22). Filtro de acceso en el WHERE, resaltado escapado, revalida versión vigente con bloqueo. Calidad: ruta /buscar agregada reemplazando el router. Merge: #9.
