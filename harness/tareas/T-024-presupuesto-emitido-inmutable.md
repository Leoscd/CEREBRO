---
id: T-024
titulo: Presupuesto emitido inmutable en la base
estado: lista
rama: codex/T-024-presupuesto-emitido-inmutable
creada: 2026-11-23
depende: T-023
pr:
---

## Objetivo
Que un presupuesto emitido no se pueda modificar **por ningún camino** (ruta, agente, script o SQL directo), igual que
el historial de precios. Hoy lo cuida solo la aplicación (hallazgo de la auditoría del PR #28).

## Contexto mínimo
- `app/db/migraciones/0009_presupuestos.sql` (tablas `presupuestos`, `rubros_presupuesto`, `items_presupuesto`; columna `precio_emitido_centavos`).
- Emisión y nueva versión: `app/services/presupuestos.py` (fijate en qué orden escribe al emitir: congela los PU y después cambia el estado).
- Patrón de trigger inmutable: `precios_inmutables` en `0007_catalogo_precios.sql`.

## Alcance
- Tocar: `app/db/migraciones/0011_presupuesto_emitido_inmutable.sql` (nuevo), `app/services/presupuestos.py` (solo si el orden de la emisión lo exige), `tests/test_presupuestos.py`.
- No tocar: migraciones existentes.

## Diseño pedido
- Triggers que rechazan INSERT/UPDATE/DELETE de `rubros_presupuesto` e `items_presupuesto` cuando el presupuesto padre está `emitido`,
  y cualquier UPDATE/DELETE de un `presupuestos` emitido (salvo que no cambie nada). Mensaje claro en castellano.
- La emisión tiene que seguir funcionando: congelar PU con el presupuesto todavía en `borrador` y cambiar el estado al final, en la misma transacción.
- "Nueva versión" sigue creando un borrador nuevo (no toca el emitido).

## Criterios de aceptación
- [ ] CA1 SQL directo: UPDATE de un ítem, INSERT de un rubro y DELETE de un presupuesto emitidos → error de la base.
- [ ] CA2 Emitir y crear nueva versión siguen funcionando (las pruebas existentes de T-019/T-020/T-021 pasan sin cambiar expectativas).
- [ ] CA3 El total del presupuesto de prueba (11542) no cambia.
- [ ] CA4 Sensores y suite en verde.

## Fuera de alcance
- Anular presupuestos emitidos.

## Bitácora del ejecutor

## Dictamen del auditor
