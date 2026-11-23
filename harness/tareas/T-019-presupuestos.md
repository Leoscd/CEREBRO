---
id: T-019
titulo: Presupuestos del proyecto (rubros, ítems y totales al centavo)
estado: en-revision
rama: codex/T-019-presupuestos
creada: 2026-11-23
depende: T-018
pr: "#28"
---

## Objetivo
Que cada proyecto tenga presupuestos con rubros e ítems (cantidad × precio unitario, desde un APU o manual),
coeficientes de gastos generales, beneficio e impuestos, y un total que **cierra al centavo** siempre igual.

## Contexto mínimo
- Plan: `docs/PLAN.md` → Modelo de datos → Presupuestos (`presupuestos`, `rubros_presupuesto`, `items_presupuesto` con origen
  de la cantidad: manual, cómputo Revit o cómputo AutoCAD) y Verificación M2 ("un presupuesto de prueba cierra al centavo").
- APUs (T-018), dinero (T-016). Ficha del proyecto: `app/routers/proyectos.py` → `ficha`, `app/templates/proyecto.html`.
- Permisos: `obtener_proyecto`, `ROLES_ESCRITURA` (`app/permisos.py`).

## Alcance
- Tocar: `app/db/migraciones/0009_presupuestos.sql` (nuevo), `app/services/presupuestos.py` (nuevo), `app/routers/presupuestos.py` (nuevo),
  `app/main.py`, `app/permisos.py`, `app/templates/presupuesto*.html` (nuevas), `app/templates/proyecto.html` (enlace), `tests/test_presupuestos.py` (nuevo).
- No tocar: migraciones existentes.

## Diseño pedido
- `presupuestos`: empresa_id, proyecto_id (FK compuesta), nombre, version int, estado (`borrador`|`emitido`), `fecha_precios date`,
  `gastos_generales_pb`, `beneficio_pb`, `impuestos_pb` (integer, puntos básicos), creado_por, creado_en, emitido_en.
- `rubros_presupuesto`: presupuesto_id, nombre, orden. `items_presupuesto`: rubro_id, descripcion, unidad, `cantidad numeric(14,4)`,
  `apu_id` (nullable) **o** `precio_unitario_centavos bigint` manual (uno de los dos, CHECK), `origen_cantidad` (`manual`|`revit`|`autocad`), orden.
- `presupuestos.calcular(db, empresa_id, presupuesto_id)` — **regla única y documentada en el docstring**:
  1. precio unitario del ítem: el del APU a `fecha_precios` (o el manual);
  2. subtotal ítem = `multiplicar(pu, cantidad)` redondeado a centavo;
  3. costo directo = suma de subtotales; rubros = suma de sus ítems;
  4. GG = `aplicar_coeficiente(costo_directo, gg_pb)`; beneficio sobre (CD + GG); impuestos sobre (CD + GG + B);
  5. total = CD + GG + B + I.
- Emitido = congelado: no se editan ítems; "Nueva versión" copia el presupuesto a borrador con version+1. Auditoría en cada cambio.
- Permiso `puede_editar_presupuesto(u, proyecto)` = admin o `mi_rol` en (`director`, `administracion`). Ver: miembros del proyecto. **Cliente: no ve presupuestos en M2.**
- Pantalla `/proyecto/{codigo}/presupuestos` y `/presupuestos/{id}`: rubros, ítems, subtotales, coeficientes y total con el filtro `pesos`.

## Criterios de aceptación
- [x] CA1 **Presupuesto de prueba al centavo**: un fixture con 2 rubros, 5 ítems (con APU y manuales, cantidades con decimales) y
      coeficientes; el total esperado está **calculado a mano y escrito en la prueba**, paso por paso, y coincide exacto.
- [x] CA2 Emitido: agregar o editar ítems → 409; "Nueva versión" crea borrador v2 con los mismos ítems.
- [x] CA3 Cambiar un precio en el catálogo no altera un presupuesto con `fecha_precios` anterior.
- [x] CA4 Aislamiento y roles: otra empresa → 404; colaborador ve pero no edita (403); cliente → 404.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- Verificador (T-020), Excel (T-021), agente (T-023), gastos y certificados.

## Bitácora del ejecutor

- La prueba fija la cuenta manual de dos rubros y cinco ítems, con un total esperado de 11.542 centavos. El servicio comparte la fórmula de coeficientes con todas las rutas.
- La emisión conserva el precio unitario de cada ítem en bigint y bloquea edición bajo el mismo bloqueo del presupuesto. Una versión nueva copia estructura y referencias a un borrador numerado.
- Un presupuesto anterior conserva la fecha de cotización. Los emitidos mantienen además sus importes aunque luego se agregue una cotización retroactiva.
- Se verificaron lectura de miembros del proyecto, 403 del colaborador al escribir y 404 para clientes o proyectos ajenos. Sensores y suite completa pasaron.

## Dictamen del auditor
