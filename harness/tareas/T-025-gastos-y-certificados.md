---
id: T-025
titulo: Esqueleto de gastos y certificados
estado: lista
rama: codex/T-025-gastos-y-certificados
creada: 2026-11-23
depende: T-024
pr:
---

## Objetivo
Registrar gastos reales de la obra y emitir certificados de avance contra un presupuesto emitido, en su forma mínima,
para que M3 (obra) y Gerencia tengan de dónde leer "presupuestado vs. gastado".

## Contexto mínimo
- Plan: `docs/PLAN.md` → Modelo de datos → Presupuestos ("Esqueleto de `gastos` y `certificados`") y "Después" (completos más adelante).
- Presupuestos emitidos e ítems (`app/services/presupuestos.py`, T-019, T-024). Archivos para comprobantes: `archivos` (T-002) y `obtener_archivo`.
- Dinero: `app/services/dinero.py`. Permiso: `puede_editar_presupuesto` (`app/permisos.py`).

## Alcance
- Tocar: `app/db/migraciones/0012_gastos_certificados.sql` (nuevo), `app/services/gastos.py` (nuevo), `app/services/certificados.py` (nuevo),
  `app/routers/presupuestos.py` (o un router nuevo), plantillas nuevas, `tests/test_gastos_certificados.py` (nuevo).

## Diseño pedido
- `gastos`: empresa_id, proyecto_id, fecha (date), descripcion, `importe_centavos bigint` (> 0), proveedor_id (nullable, FK compuesta),
  rubro (texto libre), archivo_id del comprobante (nullable, **del mismo proyecto**), cargado_por, creado_en. Auditoría.
- `certificados`: empresa_id, presupuesto_id (**solo emitidos**), numero (correlativo por presupuesto), periodo (date, primer día del mes),
  estado (`borrador`|`emitido`), creado_en. `certificado_items`: certificado_id, item_presupuesto_id, `avance_pb` (avance **acumulado** en puntos básicos, 0..10000).
- Monto de un ítem certificado en el período = `multiplicar(subtotal_emitido_del_item, avance_acumulado − avance_acumulado_anterior)`; total = suma.
  El avance acumulado no puede bajar respecto del certificado anterior ni pasar 100 %.
- Pantallas mínimas: listado y alta de gastos en el proyecto; listado de certificados de un presupuesto emitido, alta con avances por ítem, total al centavo.
- Permisos: editar = `puede_editar_presupuesto`; ver = miembros (no cliente). Certificado emitido = inmutable (mismo criterio que T-024).

## Criterios de aceptación
- [ ] CA1 Dos certificados consecutivos (30 % y luego 75 % acumulado de un ítem) dan montos **calculados a mano en la prueba**.
- [ ] CA2 Avance que baja o supera 100 % → 400; certificar un presupuesto en borrador → 409.
- [ ] CA3 Un gasto con comprobante de otro proyecto → 404; aislamiento por empresa en todo.
- [ ] CA4 Sensores y suite en verde.

## Fuera de alcance
- Retenciones, anticipos, redeterminaciones de precio, PDF del certificado. Integración contable.

## Bitácora del ejecutor

## Dictamen del auditor
