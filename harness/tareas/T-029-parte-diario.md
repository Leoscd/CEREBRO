---
id: T-029
titulo: Parte diario de obra (borrador, confirmación inmutable y numeración)
estado: lista
rama: codex/T-029-parte-diario
creada: 2026-11-24
depende: T-028
pr:
---

## Objetivo
Que el DT cargue desde el celular el parte del día (jornada, personal, avances, materiales, equipos, seguridad e higiene,
fotos y observaciones) y lo confirme; al confirmarlo recibe un **número correlativo por obra** y ya **no se puede modificar**.

## Contexto mínimo
- Plan: `docs/PLAN.md` → M3 y Verificación M3 ("un parte confirmado no se puede modificar; el PDF sale numerado").
- **Portar**: `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\reporte.py` (`datos_iniciales`, `faltantes`, `confirmar`),
  `db.py` (`siguiente_numero`, fotos del reporte) y las pruebas de `tests/test_consultas.py` que apliquen (ej.: "reporte confirmado solo permite consultas").
- Cronograma y avances (T-028). Almacén por contenido (`app/services/almacen.py`) para las fotos.

## Alcance
- Tocar: `app/db/migraciones/0014_partes.sql` (nuevo), `app/services/partes.py` (nuevo), `app/routers/obra.py`, `app/templates/obra/` (vistas para celular),
  `app/static/` (JS mínimo para cargar fotos desde la cámara), `tests/test_partes.py` (nuevo).

## Diseño pedido
- `reportes_obra`: empresa_id, proyecto_id, fecha, dt_id, estado (`borrador`|`confirmado`), numero (null en borrador; único por proyecto),
  `datos jsonb` (las secciones de `datos_iniciales`), confirmado_en. Un borrador por proyecto, fecha y DT.
- `fotos_obra`: reporte_id, sha256 (almacén), descripcion, tarea_id (nullable), hora. Solo imágenes (verificá la firma como en T-005).
- **Confirmar** en una transacción: toma el siguiente número con bloqueo (sin huecos ni repetidos con confirmaciones simultáneas),
  inserta los avances del parte en `avances_tarea`, cambia el estado. Auditoría `parte.confirmado`.
- **Trigger**: un parte confirmado y sus fotos no admiten UPDATE/DELETE (mismo patrón que T-024).
- `faltantes(parte)`: lo que falta completar antes de confirmar (portado), mostrado en la pantalla; confirmar con faltantes → 409.
- Pantalla para celular (`/proyecto/{codigo}/obra/partes/hoy`): secciones plegables, cámara del celular para fotos (`<input type=file accept=image/* capture>`),
  guardado parcial. Listado de partes con número, fecha y DT.
- Permisos: `puede_registrar_obra` (T-028). Cliente: 404.

## Criterios de aceptación
- [ ] CA1 Confirmar dos partes a la vez (dos conexiones) → números 1 y 2, sin repetir.
- [ ] CA2 UPDATE de un parte confirmado o de sus fotos por SQL → error de la base; editar por la ruta → 409.
- [ ] CA3 Confirmar registra los avances en el cronograma y el avance de obra cambia.
- [ ] CA4 Pruebas portadas de obra-report-w que apliquen (listalas en la Bitácora con su origen).
- [ ] CA5 Aislamiento y roles; foto que no es imagen → 400. Sensores y suite en verde.

## Fuera de alcance
- PDF (T-030), clima y audio (T-031), notas y pedidos (T-032).

## Bitácora del ejecutor

## Dictamen del auditor
