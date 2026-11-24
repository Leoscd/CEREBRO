---
id: T-032
titulo: Notas de obra, pedidos, stock y alertas de materiales
estado: lista
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
- [ ] CA1 Alertas: casos verde, amarillo, rojo y crítico con fechas **calculadas a mano** en días hábiles (con un feriado en el medio).
- [ ] CA2 Un pedido `recibido` o stock suficiente apaga la alerta.
- [ ] CA3 Pruebas portadas de notas y pedidos (listalas en la Bitácora con su origen).
- [ ] CA4 Aislamiento y roles. Sensores y suite en verde.

## Fuera de alcance
- Compras y órdenes de compra a proveedores. Notificaciones push.

## Bitácora del ejecutor

## Dictamen del auditor
