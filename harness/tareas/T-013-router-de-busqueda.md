---
id: T-013
titulo: Router propio para la búsqueda
estado: hecha
rama: codex/T-013-router-de-busqueda
creada: 2026-11-22
depende: —
pr: "#18"
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
- [x] CA1 `app/routers/proyectos.py` vuelve a exportar un único `router` con prefijo `/proyecto`, sin reasignaciones.
- [x] CA2 `/proyectos/{codigo}/buscar` vive en `app/routers/busqueda.py` y se registra en `app/main.py`.
- [x] CA3 `tests/test_busqueda.py`, `tests/test_hibrida.py` y `tests/test_aislamiento_m1.py` pasan **sin modificarse**.
- [x] CA4 Sensores y suite en verde.

## Fuera de alcance
- Cualquier cambio en la lógica de búsqueda.

## Bitácora del ejecutor
- La comprobación de registro falló antes del cambio y pasó después. Hay una sola ruta de búsqueda registrada y el router de la ficha mantiene su prefijo /proyecto.
- Se movió la ruta completa. Pasaron las 73 pruebas existentes sin modificaciones y el sensor rápido terminó sin salida.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-22). Ruta movida a app/routers/busqueda.py sin cambiar lógica; pruebas existentes sin modificar. Merge: #18.
