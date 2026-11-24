---
id: T-035
titulo: Formularios con opción vacía responden 422
estado: en-revision
rama: codex/T-035-formularios-con-opcion-vacia
creada: 2026-11-24
depende: —
pr: "#47"
---

## Objetivo
Arreglar un error encontrado en el recorrido de M2 en el navegador: cuando un `<select>` tiene una opción vacía ("Sin proveedor",
"Sin APU") el navegador manda `""`, y las rutas que esperan `int | None = Form(None)` responden **422 crudo de FastAPI**.
Hoy es imposible, desde la pantalla: cargar un precio sin proveedor, agregar un ítem manual (sin APU) y cargar un gasto sin proveedor o sin comprobante.

## Contexto mínimo
- `app/routers/precios.py:99` (`proveedor_id`), `app/routers/presupuestos.py:69` (`apu_id`), `app/routers/presupuestos.py:304-305` (`proveedor_id`, `archivo_id` en gastos).
- Las pruebas existentes no lo detectaron porque nunca mandan el campo vacío como lo hace un navegador (H-013 en `harness/log.md`).

## Alcance
- Tocar: esas rutas (y cualquier otra con el mismo patrón que encuentres; listalas en la Bitácora), un helper chico para leer enteros opcionales de formularios,
  pruebas nuevas en `tests/test_formularios_navegador.py`.
- No tocar: la lógica de negocio.

## Diseño pedido
- Recibir esos campos como `str = Form("")` y convertir con un helper (`""` → `None`; número inválido → 400 con mensaje en castellano, no 422 crudo).
- Pruebas que **imiten al navegador**: mandar exactamente los campos del formulario renderizado, incluidos los vacíos
  (leé el HTML de la pantalla y armá el POST con todos sus `name`, como en la prueba de "Salir" de T-001).

## Criterios de aceptación
- [x] CA1 Desde los formularios renderizados: precio sin proveedor, ítem manual sin APU y gasto sin proveedor ni comprobante → 303 y se guardan.
- [x] CA2 Un id inválido (`"abc"`) → 400 con mensaje claro; un id de otra empresa → 404.
- [x] CA3 Sensores y suite en verde.
- Nota: después del merge, el auditor agrega un sensor que impide volver a usar `int | None = Form(...)` en rutas.

## Fuera de alcance
- Rediseño de formularios.

## Bitácora del ejecutor

- Relevé todos los `int | None` recibidos por `Form`: `proveedor_id` de precios, `apu_id` del alta/edición de ítems, y `proveedor_id` y `archivo_id` de gastos. No encontré otros casos.
- La prueba sigue el patrón de T-001: extrae los campos del formulario renderizado, incluidos los valores iniciales de cada select, y los reenvía con los datos ingresados. Los identificadores inválidos producen 400 y el aislamiento existente devuelve 404.

## Dictamen del auditor
