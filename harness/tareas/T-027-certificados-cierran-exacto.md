---
id: T-027
titulo: Certificados que cierran exacto al 100 %
estado: hecha
rama: codex/T-027-certificados-cierran-exacto
creada: 2026-11-24
depende: —
pr: "#40"
---

## Objetivo
Que la suma de todos los certificados de un ítem, al llegar al 100 %, dé **exactamente** el subtotal emitido del ítem,
sin desvíos de un centavo por redondear cada período por separado (H-011 en `harness/log.md`; el error fue de la tarea T-025).

## Contexto mínimo
- `app/services/certificados.py` → `_con_montos`: hoy `aplicar_coeficiente(subtotal, avance_pb − anterior_pb)`.
- Prueba existente: `tests/test_gastos_certificados.py` (504 y 756 centavos).

## Alcance
- Tocar: `app/services/certificados.py`, `tests/test_gastos_certificados.py`.
- No tocar: migraciones (los certificados emitidos guardan avances, no montos; si alguno guarda montos, explicalo en la Bitácora antes de seguir).

## Diseño pedido
- Monto del período = `aplicar_coeficiente(subtotal, avance_acumulado)` − `aplicar_coeficiente(subtotal, avance_acumulado_anterior)`.
  Así la suma de los períodos es siempre el acumulado redondeado una sola vez, y al 100 % es el subtotal exacto.

## Criterios de aceptación
- [x] CA1 Un ítem con subtotal que fuerce desvío con la fórmula vieja (p. ej. 1001 centavos certificado en 3 períodos de 33,33 %, 33,33 % y 33,34 %):
      la suma de los tres montos es **1001** exacto. Dejá la cuenta a mano en la prueba, mostrando que la fórmula vieja daba otro número.
- [x] CA2 Los casos existentes (504 y 756) siguen dando lo mismo.
- [x] CA3 Sensores y suite en verde.

## Fuera de alcance
- Retenciones, anticipos, redeterminaciones.

## Bitácora del ejecutor

- El monto del período es la diferencia entre acumulados ya redondeados. En la prueba, la fórmula anterior daba 1002 y la nueva dio 334 + 333 + 334 = 1001 centavos.
- Los certificados guardan avances, por lo que la corrección se aplica también a lo emitido. No hizo falta migración.
- Se conservan los importes de 504 y 756 centavos del caso existente. Esta tarea parte de H-011 y no porta pruebas de obra-report-w.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-24). Período = acumulado redondeado − anterior; prueba muestra 1002 con la fórmula vieja y 1001 con la nueva. Merge: #40.
