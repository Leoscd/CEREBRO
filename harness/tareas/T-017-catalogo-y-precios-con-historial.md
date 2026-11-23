---
id: T-017
titulo: Catálogo de materiales, proveedores y precios con historial
estado: lista
rama: codex/T-017-catalogo-y-precios-con-historial
creada: 2026-11-23
depende: T-016
pr:
---

## Objetivo
Que la empresa tenga su catálogo de materiales (y mano de obra/equipos), proveedores y un historial de precios que
**nunca se edita**: cada cambio de precio es una fila nueva, y se puede ver cuánto subió cada cosa.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Modelo de datos" → Presupuestos (`materiales`, `proveedores`, `precios` solo inserción,
  vista `v_cambios_precio`, `indices_costo`) y "Verificación" M2 ("el historial de precios no se puede editar").
- Patrón de tabla inmutable con trigger: `auditoria` en `app/db/migraciones/0001_base.sql`.
- Referencia de dominio: `D:\APLICACIONES\excel-wrapper\src\apu\domain\catalog.py` y `src\apu\db\schema.py`.
- Dinero: `app/services/dinero.py` (T-016). Panel admin: `app/routers/admin.py` (`_admin_csrf`), `app/templates/admin/panel.html`.

## Alcance
- Tocar: `app/db/migraciones/0007_catalogo_precios.sql` (nuevo), `app/services/precios.py` (nuevo), `app/routers/precios.py` (nuevo),
  `app/main.py`, `app/permisos.py` (permiso nuevo), `app/templates/precios/` (nuevas), `app/templates/admin/panel.html` (enlace), `tests/test_precios.py` (nuevo).
- No tocar: migraciones existentes.

## Diseño pedido
- `materiales`: empresa_id, codigo (único por empresa), nombre, unidad, tipo (`material`|`mano_obra`|`equipo`), rubro, activo.
- `proveedores`: empresa_id, nombre, cuit, contacto, activo.
- `precios`: empresa_id, material_id, proveedor_id (nullable), `precio_centavos bigint` (> 0), `vigente_desde timestamptz`,
  fuente (`manual`|`excel`|`agente`), cargado_por, creado_en. **Trigger que rechaza UPDATE y DELETE** (como `auditoria`).
- `v_cambios_precio`: por material, precio anterior, actual, variación en puntos básicos y fecha.
- `indices_costo`: empresa_id, nombre (p. ej. "CAC mano de obra"), periodo (date, primer día del mes), `valor numeric(12,4)`.
- `precios.vigente(db, empresa_id, material_id, a_fecha)` → el último precio con `vigente_desde <= a_fecha`.
- Permiso `puede_gestionar_precios(u)` = admin o integrante del área de administración (mirá `usuario_areas`/`areas` en 0001; si no alcanza, solo admin y anotalo).
- Pantallas `/precios`: listado de materiales con precio vigente y última variación; alta de material; cargar precio (crea fila);
  historial por material; proveedores. Todo POST con `check_csrf` y `auditoria.registrar`.
- Ojo con el sensor `dinero`: toda columna con monto/precio/costo/total/importe/saldo va como `*_centavos bigint`.

## Criterios de aceptación
- [ ] CA1 Cargar dos precios para un material → el vigente es el más nuevo y `v_cambios_precio` muestra la variación correcta en puntos básicos.
- [ ] CA2 `UPDATE` o `DELETE` sobre `precios` falla en la base (prueba directa con SQL).
- [ ] CA3 `precios.vigente` respeta la fecha: con un precio de enero y otro de marzo, a febrero devuelve el de enero.
- [ ] CA4 Aislamiento: materiales, precios e índices de B no aparecen para A por ninguna ruta (404 en ids ajenos).
- [ ] CA5 Un miembro sin permiso recibe 403 al cargar precios; el cliente no ve `/precios`.
- [ ] CA6 Sensores y suite en verde.

## Fuera de alcance
- Importar precios desde Excel (T-021). Actualizar por índice (lo hace el agente en T-023).

## Bitácora del ejecutor

## Dictamen del auditor
