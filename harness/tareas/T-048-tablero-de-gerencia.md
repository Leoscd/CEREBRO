---
id: T-048
titulo: Tablero de Gerencia
estado: lista
rama: codex/T-048-tablero-de-gerencia
creada: 2026-11-27
depende: — (etapa 1 de L-007 en main)
pr:
---

## Objetivo
El administrador del estudio tiene una página "Gerencia" con cinco cuadros de solo lectura: obras atrasadas, presupuesto
contra gastado, precios que subieron, uso de IA y actividad del equipo. Nadie que no sea admin la puede ver.

## Contexto mínimo
- Plan: tabla de agentes fila "Gerencia (admin)" (proyectos_atrasados, presupuesto_vs_gastado, precios_que_subieron, uso_ia, actividad_equipo),
  riesgo 7 ("uso visible en Gerencia") y verificación de M5 ("Gerencia rechaza a quien no es admin").
- Admin: `app/security.py` → `require_admin` (403). Panel de admin existente: `app/routers/admin.py`.
- Datos: `cronograma.avance_obra(db, proyecto, dia)` (atrasos), presupuestos emitidos y `gastos.listar` / certificados (`app/services/certificados.py`),
  `precios` con historial (migración 0007, `app/services/precios.py`), `agent_runs` con `tokens_entrada`/`tokens_salida` (migración 0006),
  `auditoria` (acciones por usuario). Dinero en centavos y formato con los filtros de T-036.

## Alcance
- Tocar: `app/services/gerencia.py` (nuevo), `app/routers/gerencia.py` (nuevo), `app/main.py`, `app/templates/gerencia.html` (nueva),
  `app/templates/base.html` (enlace "Gerencia" solo para admin), `tests/test_gerencia.py` (nuevo).
- No tocar: `app/permisos.py`, migraciones (si un cuadro necesita un índice, proponelo en la Bitácora), servicios existentes salvo lectura.

## Diseño pedido
- `gerencia.py`, todas las funciones reciben `empresa_id` de la sesión y devuelven datos listos para mostrar:
  - `proyectos_atrasados(db, empresa_id, dia)`: proyectos con tareas atrasadas (cantidad y la más atrasada), ordenados por atraso.
  - `presupuesto_vs_gastado(db, empresa_id)`: por proyecto con presupuesto emitido, total presupuestado, gastado y certificado, y el % gastado.
  - `precios_que_subieron(db, empresa_id, dias=30, umbral_pb=500)`: materiales cuyo precio vigente subió más que el umbral (en puntos básicos) en el período.
  - `uso_ia(db, empresa_id, dias=30)`: corridas y tokens por agente y por usuario.
  - `actividad_equipo(db, empresa_id, dias=7)`: acciones de auditoría por usuario y las 5 más frecuentes.
- `GET /gerencia` con `require_admin`; cada cuadro con un mensaje claro si no hay datos. Sin N+1 (una consulta por cuadro o por proyecto acotado).

## Criterios de aceptación
- [ ] CA1 Con datos de prueba: una obra con una tarea atrasada aparece primera; un presupuesto de $ 100.000 con $ 25.000 gastados muestra 25 %;
  un material que pasó de 1000 a 1100 centavos aparece con +10 %; las corridas y los tokens de `agent_runs` suman bien.
- [ ] CA2 Usuario no admin → 403; cliente → 403; sin sesión → login.
- [ ] CA3 Aislamiento: los cinco cuadros de la empresa A no incluyen nada de la empresa B (prueba con datos en ambas).
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Agente de Gerencia (T-049). Gráficos interactivos (alcanza con tablas y barras simples en CSS). Exportar a Excel.

## Bitácora del ejecutor

## Dictamen del auditor
