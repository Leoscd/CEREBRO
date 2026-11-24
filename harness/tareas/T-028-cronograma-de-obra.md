---
id: T-028
titulo: Cronograma de obra con avance previsto y real
estado: en-curso
rama: codex/T-028-cronograma-de-obra
creada: 2026-11-24
depende: —
pr:
---

## Objetivo
Cargar el cronograma de una obra (tareas con fechas, días hábiles y materiales que necesitan), registrar el avance real
y ver cuánto debería ir (previsto) contra cuánto va (real), por tarea y para toda la obra.

## Contexto mínimo
- Plan: `docs/PLAN.md` → M3 ("Cronograma, hitos y bitácora"), Modelo de datos → Obra (`tareas`, `avances_tarea`).
- **Portar** (no copiar a ciegas): `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\cronograma.py`
  (`cargar`, `es_habil`/feriados, `proximo_habil`, `restar_habiles`, `pct_previsto`, `activas`, `avance_obra`, `buscar`, `normalizar`).
- `hitos` ya existe (0001) y se usa en la ficha. Presupuestos e ítems emitidos (`app/services/presupuestos.py`).
- Permisos: `obtener_proyecto`, roles de proyecto (`director`, `dt`, …) en `app/permisos.py`.

## Alcance
- Tocar: `app/db/migraciones/0013_cronograma.sql` (nuevo), `app/services/cronograma.py` (nuevo), `app/routers/obra.py` (nuevo), `app/main.py`,
  `app/permisos.py` (permiso de obra), `app/templates/obra/` (nuevas), `app/templates/proyecto.html` (enlace), `tests/test_cronograma.py` (nuevo).

## Diseño pedido
- `tareas_obra`: empresa_id, proyecto_id, codigo (único por proyecto), nombre, rubro, inicio (date), fin (date), critica (bool),
  `item_presupuesto_id` (nullable, FK compuesta, para el avance económico), orden.
- `materiales_tarea`: tarea_id, nombre, `cantidad numeric(14,4)`, unidad, `plazo_dias` (hábiles de entrega).
- `avances_tarea`: tarea_id, fecha, `avance_pb` acumulado (0..10000), registrado_por, creado_en. **Solo inserción** (trigger como `precios`); el avance vigente es el último por fecha.
- `feriados`: empresa_id, fecha, nombre (la empresa carga los suyos; los fijos de obra-report-w como semilla en la migración para cada empresa existente y en el alta de empresa).
- Servicio: días hábiles con feriados de la empresa; `previsto(tarea, dia)` lineal en días hábiles; avance de obra ponderado por **días hábiles de cada tarea**; atraso = previsto − real; tarea crítica atrasada se marca.
- **Avance económico**: para tareas con ítem de presupuesto emitido, `multiplicar(subtotal_emitido, avance)`; total de obra en centavos y en %.
- Importar cronograma desde `.xlsx` con plantilla fija (reusá `app/services/excel.py`: mismas defensas, vista previa y confirmación firmada).
- Permiso `puede_registrar_obra(u, proyecto)` = admin o `mi_rol` en (`director`, `dt`). Ver: miembros. Cliente: 404 en M3.
- Pantalla `/proyecto/{codigo}/obra`: tabla tipo Gantt simple (barra previsto/real por tarea), avance físico y económico, tareas atrasadas arriba.

## Criterios de aceptación
- [x] CA1 Días hábiles: casos con fin de semana y feriado de la empresa (portá los casos de calendario de obra-report-w si existen).
- [x] CA2 Avance de obra ponderado y avance económico **calculados a mano en la prueba**, y la suma de las partes da el total (H-011).
- [x] CA3 Avances inmutables en la base; el vigente es el último.
- [x] CA4 Aislamiento y roles: otra empresa 404; colaborador ve y no registra (403); cliente 404.
- [x] CA5 Sensores y suite en verde.

## Fuera de alcance
- Dependencias entre tareas y camino crítico calculado. Reprogramación automática.

## Bitácora del ejecutor

- Porté de obra-report-w/obra_bot/cronograma.py el calendario, los feriados fijos, la normalización, la búsqueda y el avance previsto. No encontré casos unitarios directos para el calendario. Agregué tests/test_cronograma.py::test_calendario_con_fin_de_semana_y_feriado para cubrir fin de semana, feriados de empresa y la semilla en el alta.
- Separé avance físico ponderado y avance económico. La prueba deriva a mano 4.286/5.714 pb previstos/reales y 2.079 centavos sobre 4.494 de base emitida.
- La importación usa la planilla y la firma del repositorio. El avance se agrega por fecha, con el ID como desempate. Los clientes quedan fuera del módulo.

## Dictamen del auditor
