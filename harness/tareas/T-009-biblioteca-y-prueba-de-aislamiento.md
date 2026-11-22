---
id: T-009
titulo: Biblioteca de criterios y prueba de aislamiento de M1
estado: en-revision
rama: codex/T-009-biblioteca-y-prueba-de-aislamiento
creada: 2026-11-21
depende: T-008
pr: "#11"
---

## Objetivo
Que el admin cargue y apruebe documentos de criterio (normativa, CIRSOC, criterios de oficina) que sirvan a todos
los proyectos de su empresa, y dejar escrita la prueba de aislamiento que exige el plan para M1.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Verificación" (M1: prueba de aislamiento) y "RAG".
- Tablas de T-007 (`biblioteca_documentos`, `chunks.biblioteca_id`); búsqueda de T-008; almacén de T-003; panel admin `app/routers/admin.py` (`_admin_csrf`).
- **Decisión tomada:** la biblioteca es **por empresa** (lleva `empresa_id`); no hay biblioteca global entre empresas.

## Alcance
- Tocar: `app/routers/admin.py`, `app/templates/admin/biblioteca.html` (nuevo), `app/templates/admin/panel.html` (enlace),
  `app/worker.py` (manejador), `tests/test_biblioteca.py` (nuevo), `tests/test_aislamiento_m1.py` (nuevo).

## Diseño pedido
- `/admin/biblioteca`: listar, subir PDF (título, tipo, versión), aprobar, retirar. Todo con `_admin_csrf` y auditoría
  (`biblioteca.subir`, `biblioteca.aprobar`, `biblioteca.retirar`). Al subir: almacén por contenido + trabajo `biblioteca.indexar`
  (mismo partido en fragmentos que T-007, con `biblioteca_id`) y luego embeddings.
- Solo los aprobados entran en la búsqueda (ya lo hace T-008).
- `tests/test_aislamiento_m1.py` — una frase única en un PDF de **p2** (empresa A, ana no es miembro) y otra en **pb** (empresa B).
  Para ana, cliente de A y admin B (según corresponda) comprobá que la frase ajena **no aparece por ningún camino**:
  búsqueda (`/proyectos/{codigo}/buscar` y `busqueda.buscar`), ficha, `/archivos/{id}`, `/contenido`, `/descargar`,
  `/versiones/{n}/descargar`, derivados, y adiviná ids correlativos. Dejá la prueba armada para que T-010 le sume chat y herramientas.

## Criterios de aceptación
- [x] CA1 Admin sube un criterio, lo aprueba → aparece en la búsqueda de p1 y p2 con la etiqueta "Biblioteca" y la página correcta.
- [x] CA2 Retirado → deja de aparecer. Un miembro no admin no puede entrar a `/admin/biblioteca` (403) ni ver borradores.
- [x] CA3 Criterio de B nunca aparece en A.
- [x] CA4 `tests/test_aislamiento_m1.py` pasa y cubre todos los caminos listados; las citas dan la página correcta.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- La carga real de criterios (AUTOCAD-PYTHON, CIRSOC): la hace Leo desde la pantalla. Lecciones propuestas.

## Bitácora del ejecutor
- Los dos casos de biblioteca fallaron antes del cambio. Los casos de aislamiento de rutas existentes ya pasaban y quedaron incorporados a la suite. Pasaron 67 pruebas y el sensor rápido terminó sin salida.
- La publicación sigue borrador → aprobado → retirado. El equipo de la empresa puede abrir el PDF aprobado y el administrador puede revisar borradores. Clientes y otras empresas quedan fuera.
- Se verificaron búsqueda HTTP y directa, ficha, página, contenido y descargas por ID. Los derivados se comprueban detrás del permiso de archivo y la URL directa devuelve 404.

## Dictamen del auditor
