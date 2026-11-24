---
id: T-036
titulo: Números y porcentajes en formato argentino en precios y presupuestos
estado: hecha
rama: codex/T-036-numeros-en-formato-argentino
creada: 2026-11-24
depende: T-035
pr: "#48"
---

## Objetivo
Que alguien del estudio lea y cargue los números como está acostumbrado: porcentajes en % (no "puntos básicos") y decimales con coma.
Detalles encontrados en el recorrido de M2.

## Contexto mínimo
- Hoy se ve: variación de precio "1500" (pb), cantidad "16.0000" y "42.5000", coeficientes "Gastos generales (1500 pb)", y los formularios piden desperdicio y coeficientes **en puntos básicos**.
- Plantillas: `app/templates/precios/*.html`, `app/templates/presupuesto*.html`. Filtros: `app/templates.py` (`pesos`). Dinero: `app/services/dinero.py`.

## Alcance
- Tocar: `app/templates.py` (filtros nuevos), las plantillas de precios, APU y presupuestos, las rutas que reciben porcentajes (convertir % → pb al guardar), pruebas.
- No tocar: el modelo de datos (sigue guardando puntos básicos y `numeric`).

## Diseño pedido
- Filtros `porcentaje` (1500 → "15,00 %"; negativos con signo) y `cantidad` (Decimal → "16", "42,5", "3,3333": sin ceros de más, coma decimal, punto de miles).
- Formularios: desperdicio y coeficientes se cargan en **%** con hasta 2 decimales ("15", "10,5") y se convierten a pb exactos; si no es exacto en pb → 400 con mensaje.
- Cantidades: aceptar "42,5" además de "42.5".

## Criterios de aceptación
- [x] CA1 La pantalla del presupuesto de prueba muestra "15,00 %", "42,5" y los mismos totales que antes.
- [x] CA2 Cargar "15" en gastos generales guarda 1500 pb; "10,555" → 400.
- [x] CA3 Sensores y suite en verde (las pruebas de cuentas a mano no cambian sus totales).

## Fuera de alcance
- Internacionalización a otros idiomas.

## Bitácora del ejecutor

- Los filtros usan Decimal y muestran coma decimal. La cantidad pierde ceros finales y agrupa miles en las vistas. Los campos de edición muestran coma decimal y permiten tanto coma como punto.
- Los formularios M2 usan porcentajes y los convierten a puntos básicos exactos. Se mantiene el formato previo en las rutas para solicitudes ya existentes. El test conserva el total de 11.542 centavos calculado a mano en T-021.
- Incluí la pantalla de certificados por compartir los formularios de porcentajes del módulo de presupuestos. Mantiene los mismos cálculos y los mismos límites de acumulación.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-24). Filtros porcentaje y cantidad en formato argentino; % → pb exacto con rechazo de ambigüedades. Merge: #48.
