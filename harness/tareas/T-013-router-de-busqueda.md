---
id: T-013
titulo: Router propio para la búsqueda
estado: lista
rama: codex/T-013-router-de-busqueda
creada: 2026-11-22
depende: —
pr:
---

## Objetivo
Sacar el truco que reemplaza el `router` de `proyectos.py` para colgar `/proyectos/{codigo}/buscar`, y dejar
la búsqueda en su propio router, sin cambiar el comportamiento.

## Contexto mínimo
- `app/routers/proyectos.py` líneas ~200-212: `rutas_busqueda = APIRouter(); rutas_busqueda.include_router(router); router = rutas_busqueda` + ruta `buscar`.
- Registro: `app/main.py`. Hallazgo de la auditoría del PR #9 (dictamen en `harness/tareas/T-007-texto-e-indice-por-palabras.md`).

## Alcance
- Tocar: `app/routers/proyectos.py`, `app/routers/busqueda.py` (nuevo), `app/main.py`.
- No tocar: `app/services/busqueda.py`, plantillas, pruebas existentes (tienen que pasar sin cambios).

## Criterios de aceptación
- [ ] CA1 `app/routers/proyectos.py` vuelve a exportar un único `router` con prefijo `/proyecto`, sin reasignaciones.
- [ ] CA2 `/proyectos/{codigo}/buscar` vive en `app/routers/busqueda.py` y se registra en `app/main.py`.
- [ ] CA3 `tests/test_busqueda.py`, `tests/test_hibrida.py` y `tests/test_aislamiento_m1.py` pasan **sin modificarse**.
- [ ] CA4 Sensores y suite en verde.

## Fuera de alcance
- Cualquier cambio en la lógica de búsqueda.

## Bitácora del ejecutor

## Dictamen del auditor
