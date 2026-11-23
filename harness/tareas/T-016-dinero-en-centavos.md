---
id: T-016
titulo: Servicio de dinero en centavos
estado: lista
rama: codex/T-016-dinero-en-centavos
creada: 2026-11-23
depende: —
pr:
---

## Objetivo
Una sola forma de leer, calcular, redondear y mostrar dinero en todo el sistema, en centavos enteros, para que
un presupuesto cierre al centavo (requisito de verificación de M2).

## Contexto mínimo
- Regla del proyecto: dinero en `*_centavos bigint` (AGENTS.md; lo hace cumplir el sensor `dinero`).
- Referencia a portar (no copiar tal cual, es TypeScript): `D:\APLICACIONES\PEDIDOS-M14\my-project\app\src\dominio\dinero.ts`
  (`pesosACentavos`, `sumarCentavos`, `formatearPesos`) y su prueba `.../tests/unit/dinero.test.ts`.
- Filtros de plantilla existentes: `app/templates.py` (`fecha`, `solo_fecha`).

## Alcance
- Tocar: `app/services/dinero.py` (nuevo), `app/templates.py` (filtro `pesos`), `tests/test_dinero.py` (nuevo).
- No tocar: migraciones, routers.

## Diseño pedido
- Todo con `int` (centavos) y `Decimal` para cantidades; **nunca `float`** en dinero.
- `leer_pesos("1.234,56") -> 123456`: formato argentino (punto de miles, coma decimal), acepta `$`, espacios y signo;
  rechaza más de 2 decimales, texto basura y vacío con `ValueError` y mensaje en castellano.
- `multiplicar(centavos: int, cantidad: Decimal) -> int` con **redondeo half-up a centavo** (una sola regla, documentada).
- `aplicar_coeficiente(centavos: int, puntos_basicos: int) -> int` (p. ej. 1500 = 15 %), mismo redondeo.
- `sumar(iterable[int]) -> int`; `formatear(123456) -> "$ 1.234,56"`, negativos `"-$ 1.234,56"`.
- Filtro Jinja `pesos` que usa `formatear`.

## Criterios de aceptación
- [ ] CA1 Ida y vuelta: `formatear(leer_pesos(x))` es estable para una tabla de casos (miles, negativos, cero, `0,05`).
- [ ] CA2 Redondeo half-up probado en los bordes (`x,xx5`), y `multiplicar` de cantidades con 4 decimales.
- [ ] CA3 `leer_pesos` rechaza `"1,234.56"` ambiguo, `"12,345"` (3 decimales), `""`, `"abc"`.
- [ ] CA4 El módulo no importa ni usa `float` (comprobalo en la prueba leyendo el fuente o con `ast`).
- [ ] CA5 Sensores y suite en verde.

## Fuera de alcance
- Monedas que no sean pesos. Inflación/índices (T-017).

## Bitácora del ejecutor

## Dictamen del auditor
