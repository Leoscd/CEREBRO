---
id: T-019
titulo: Presupuestos del proyecto (rubros, ítems y totales al centavo)
estado: lista
rama: codex/T-019-presupuestos
creada: 2026-11-23
depende: T-018
pr:
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
- [ ] CA1 **Presupuesto de prueba al centavo**: un fixture con 2 rubros, 5 ítems (con APU y manuales, cantidades con decimales) y
      coeficientes; el total esperado está **calculado a mano y escrito en la prueba**, paso por paso, y coincide exacto.
- [ ] CA2 Emitido: agregar o editar ítems → 409; "Nueva versión" crea borrador v2 con los mismos ítems.
- [ ] CA3 Cambiar un precio en el catálogo no altera un presupuesto con `fecha_precios` anterior.
- [ ] CA4 Aislamiento y roles: otra empresa → 404; colaborador ve pero no edita (403); cliente → 404.
- [ ] CA5 Sensores y suite en verde.

## Fuera de alcance
- Verificador (T-020), Excel (T-021), agente (T-023), gastos y certificados.

## Bitácora del ejecutor

## Dictamen del auditor
