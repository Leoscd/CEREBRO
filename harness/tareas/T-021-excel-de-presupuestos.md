---
id: T-021
titulo: Exportar e importar presupuestos en Excel
estado: hecha
rama: codex/T-021-excel-de-presupuestos
creada: 2026-11-23
depende: T-020
pr: "#30"
---

## Objetivo
Bajar un presupuesto a una planilla `.xlsx` prolija (con fórmulas que den el mismo total) y cargar ítems y precios
desde una planilla con un formato fijo, con vista previa antes de confirmar.

## Contexto mínimo
- `presupuestos.calcular` (T-019), catálogo y `precios` (T-017), dinero (T-016).
- Referencia: `D:\APLICACIONES\excel-wrapper\src\apu\tools\spreadsheet_tools.py`.
- Subidas: patrón de `app/routers/archivos.py` (límite de tamaño, nombres saneados).

## Alcance
- Tocar: `app/services/excel.py` (nuevo), `app/routers/presupuestos.py`, `app/routers/precios.py`, plantillas, `requirements.txt` (`openpyxl`, versión fija),
  `tests/test_excel.py` (nuevo).

## Diseño pedido
- **Exportar** `/presupuestos/{id}.xlsx`: hoja "Presupuesto" (rubros, ítems, unidad, cantidad, P.U., subtotal con **fórmula**,
  CD, GG, B, I, total con fórmulas) y hoja "Datos" con los valores calculados por el servidor. Formato de moneda argentino.
- **Importar ítems** a un presupuesto borrador: plantilla descargable con columnas fijas (rubro, descripción, unidad, cantidad, código APU o P.U.).
  Paso 1 sube y muestra la vista previa con errores por fila (no escribe); paso 2 confirma y escribe todo en una transacción, con auditoría.
- **Importar precios** al catálogo: código de material, precio, vigente desde, proveedor. Cada fila válida = fila nueva en `precios` (fuente `excel`).
- Solo `.xlsx`; rechazar macros (`.xlsm`) y archivos > 10 MB. Leer con `openpyxl` en modo `read_only` y `data_only`.

## Criterios de aceptación
- [x] CA1 Exportar el presupuesto de prueba de T-019: los valores de la hoja "Datos" coinciden al centavo con `calcular`,
      y las fórmulas de "Presupuesto" referencian las celdas correctas (verificalo leyendo las fórmulas con openpyxl).
- [x] CA2 Importar una planilla con 1 fila mala → la vista previa marca esa fila y no escribe nada; corregida, confirma y crea los ítems.
- [x] CA3 Importar precios crea filas nuevas (no edita) y respeta el aislamiento por empresa.
- [x] CA4 `.xlsm`, archivo corrupto o > 10 MB → 400/413 sin escribir.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- Exportar a PDF. Leer planillas con formato libre (eso lo hará el agente).

## Bitácora del ejecutor

- Se fijó openpyxl 3.1.5. La hoja Presupuesto usa fórmulas de fila, rubro, coeficientes y total. La hoja Datos deja a la vista los importes del cálculo servidor en centavos.
- La vista previa devuelve números de fila y errores sin persistir cambios. La confirmación firmada está ligada a usuario, empresa y destino, y revalida todo dentro de la transacción.
- Se rechazaron macros, archivos corruptos y archivos de más de 10 MB. La importación de precios agrega historial con fuente excel y reutiliza su auditoría.
- Sensores y suite completa en verde, incluidas las pruebas de aislamiento.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-23). Celdas de texto sin fórmulas; rechaza macros, DOCTYPE (XXE) y zips > 64 MB; vista previa firmada y atada a empresa/usuario/destino. Merge: #30.
