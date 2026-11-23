---
id: T-018
titulo: Análisis de precios unitarios (APU)
estado: lista
rama: codex/T-018-apus
creada: 2026-11-23
depende: T-017
pr:
---

## Objetivo
Armar APUs (precio unitario de un ítem, p. ej. "m² de mampostería") a partir de insumos del catálogo con su
cantidad por unidad, y calcular el precio unitario con los precios vigentes a una fecha, al centavo.

## Contexto mínimo
- Plan: `docs/PLAN.md` → Modelo de datos → Presupuestos (`apus`, `apu_insumos`).
- Referencia de cálculo: `D:\APLICACIONES\excel-wrapper\src\apu\domain\apu.py` (Resource / APUItem / APU; ahí usa Decimal
  con 4 decimales: acá el resultado final va en centavos con `dinero.multiplicar`).
- Catálogo y `precios.vigente` (T-017). Dinero (T-016).

## Alcance
- Tocar: `app/db/migraciones/0008_apus.sql` (nuevo), `app/services/apus.py` (nuevo), `app/routers/precios.py` (pantallas de APU),
  `app/templates/precios/` (nuevas), `tests/test_apus.py` (nuevo).
- No tocar: migraciones existentes, `precios` (solo leerla).

## Diseño pedido
- `apus`: empresa_id, codigo (único por empresa), descripcion, unidad, rubro, activo.
- `apu_insumos`: empresa_id, apu_id, material_id, `cantidad numeric(14,4)` (> 0) por unidad del APU, `desperdicio_pb integer` (puntos básicos, ≥ 0).
- `apus.precio_unitario(db, empresa_id, apu_id, a_fecha) -> {total_centavos, detalle:[{insumo, cantidad, precio_centavos, subtotal_centavos}], faltantes:[...]}`:
  subtotal = `multiplicar(precio_vigente, cantidad × (1 + desperdicio))`, redondeado **por insumo**; total = suma de subtotales.
  Un insumo sin precio vigente va a `faltantes` y no suma (no inventa cero).
- Pantallas: listado de APUs con precio unitario a hoy; alta/edición de APU con sus insumos; detalle con el desglose.
  Mismo permiso que precios para editar. POST con `check_csrf` y auditoría.

## Criterios de aceptación
- [ ] CA1 Un APU de prueba con 3 insumos da un total **calculado a mano en la prueba** (dejá la cuenta escrita en un comentario).
- [ ] CA2 Con un precio nuevo cargado después, `precio_unitario` a la fecha vieja no cambia y a hoy sí.
- [ ] CA3 Insumo sin precio → aparece en `faltantes` y la pantalla lo marca.
- [ ] CA4 Aislamiento: un APU no puede usar materiales de otra empresa (la base lo impide con FK compuesta, como en T-002) y los ids ajenos dan 404.
- [ ] CA5 Sensores y suite en verde.

## Fuera de alcance
- Cargas sociales y coeficientes del presupuesto (T-019).

## Bitácora del ejecutor

## Dictamen del auditor
