---
id: T-032
titulo: Notas de obra, pedidos, stock y alertas de materiales
estado: en-curso
rama: codex/T-032-notas-pedidos-y-alertas
creada: 2026-11-24
depende: T-031
pr:
---

## Objetivo
Llevar las notas de obra (órdenes de servicio, notas de pedido) con plazo y estado, los pedidos de materiales y el stock,
y avisar con anticipación qué hay que pedir para no frenar una tarea.

## Contexto mínimo
- **Portar**: `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\cronograma.py` → `alertas_materiales` (límite = inicio − plazo − margen, en días hábiles;
  niveles verde/amarillo/rojo/crítico) y `db.py` (notas, pedidos, stock). Pruebas de `tests/test_consultas.py` sobre notas y pedidos.
- Cronograma y `materiales_tarea` (T-028), parte diario (T-029: ingresos y faltantes de materiales).

## Alcance
- Tocar: `app/db/migraciones/0016_notas_pedidos_stock.sql` (nuevo), `app/services/materiales_obra.py` (nuevo), `app/services/notas_obra.py` (nuevo),
  `app/routers/obra.py`, plantillas, `app/config.py` (`MARGEN_PEDIDO_DIAS`), `tests/test_materiales_obra.py` (nuevo).

## Diseño pedido
- `notas_obra`: tipo (`orden_servicio`|`nota_pedido`), numero por tipo y proyecto, fecha, emisor, destinatario, asunto, texto, plazo (date), estado (`abierta`|`respondida`|`cerrada`), reporte_id (nullable).
- `pedidos_material`: tarea_id, material, estado (`pendiente`|`pedido`|`recibido`|`no_aplica`), fecha, fecha_entrega. `stock_obra`: material, fecha, cantidad, unidad (solo inserción; el vigente es el último).
- `alertas(db, proyecto, hoy)` portado; el parte confirmado actualiza stock con sus ingresos de materiales.
- Pantalla de obra: tablero de alertas (rojo/crítico arriba), notas abiertas con días de plazo, pedidos por estado.

## Criterios de aceptación
- [x] CA1 Alertas: casos verde, amarillo, rojo y crítico con fechas **calculadas a mano** en días hábiles (con un feriado en el medio).
- [x] CA2 Un pedido `recibido` o stock suficiente apaga la alerta.
- [x] CA3 Pruebas portadas de notas y pedidos (listalas en la Bitácora con su origen).
- [x] CA4 Aislamiento y roles. Sensores y suite en verde.

## Fuera de alcance
- Compras y órdenes de compra a proveedores. Notificaciones push.

## Bitácora del ejecutor

- Porté `obra-report-w/tests/test_consultas.py::test_notas_y_pedidos_pendientes` a `tests/test_materiales_obra.py::test_notas_y_pedidos_pendientes`. Adapté `obra_bot/cronograma.py::alertas_materiales` y las consultas de `obra_bot/db.py`. La prueba de cuatro niveles usa fechas derivadas a mano con feriado intermedio.
- El límite usa días hábiles. Los niveles usan la distancia en días calendario al límite, igual que la referencia. El stock se coteja por material y unidad, y los ingresos de un parte se agregan en la misma transición auditada de confirmación.
- El saldo vigente se reconstruye con el último conteo declarado y los ingresos posteriores. Probé un parte de fecha anterior confirmado tarde para verificar que su ingreso quede contado. El margen predeterminado es de dos días hábiles desde MARGEN_PEDIDO_DIAS.

## Dictamen del auditor
