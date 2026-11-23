---
id: T-018
titulo: Análisis de precios unitarios (APU)
estado: hecha
rama: codex/T-018-apus
creada: 2026-11-23
depende: T-017
pr: "#27"
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
- [x] CA1 Un APU de prueba con 3 insumos da un total **calculado a mano en la prueba** (dejá la cuenta escrita en un comentario).
- [x] CA2 Con un precio nuevo cargado después, `precio_unitario` a la fecha vieja no cambia y a hoy sí.
- [x] CA3 Insumo sin precio → aparece en `faltantes` y la pantalla lo marca.
- [x] CA4 Aislamiento: un APU no puede usar materiales de otra empresa (la base lo impide con FK compuesta, como en T-002) y los ids ajenos dan 404.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- Cargas sociales y coeficientes del presupuesto (T-019).

## Bitácora del ejecutor

- Se resolvió la vigencia con el mismo servicio del catálogo. La cantidad efectiva incluye desperdicio y se redondea por insumo antes de sumar.
- El ejemplo calculado a mano da 504 centavos en la fecha inicial y 603 tras una cotización posterior. Los faltantes quedan identificados y el total se muestra como parcial.
- Las referencias compuestas bloquean materiales de otra empresa. El mismo permiso del catálogo controla altas y edición, con CSRF y auditoría.
- Sensores rápidos sin salida y suite completa en verde, incluido aislamiento.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-23). Cuenta verificada a mano (504 y 603 centavos); insumos sin precio quedan en faltantes. Merge: #27.
