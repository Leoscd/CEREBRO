---
id: T-039
titulo: IFC en el servidor
estado: hecha
rama: codex/T-039-ifc-en-el-servidor
creada: 2026-11-25
depende: T-038
pr: 55
---

## Objetivo
Al subir un IFC exportado de Revit, el sistema saca un resumen del modelo (pisos, cantidad de elementos por tipo y cantidades
base como áreas y volúmenes), lo muestra en la ficha del archivo y lo deja en la búsqueda para que el Documentador lo cite.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Visores", fila IFC (IfcOpenShell en el servidor: cantidades y propiedades para el agente).
- Convención de derivados y estados: T-037. Esta tarea agrega `derivados.meta.ifc`; el visor 3D es T-040.
- Patrón de job con chunks y versión vigente: `app/worker.py` → `indexar_archivo`, y el job `archivo.dxf` de T-038.

## Alcance
- Tocar: `requirements.txt` (`ifcopenshell`, versión fija de PyPI; LGPL, se usa como librería sin modificar), `app/services/ifc.py` (nuevo),
  `app/worker.py`, `app/routers/archivos.py` (encolar), `app/templates/archivo.html` (resumen), `app/config.py` y `.env.example` (`IFC_MAX_MB`),
  `docker-compose.yml` (solo si el worker necesita más `mem_limit`; justificalo en la Bitácora), `tests/test_ifc.py` (nuevo).
- No tocar: `app/static/vendor/**`, migraciones, `app/permisos.py`.

## Diseño pedido
- Al crear una versión con extensión `ifc`: encolá `archivo.ifc`.
- `app/services/ifc.py` → `resumen(ruta) -> dict`:
  - `esquema`, nombre del proyecto, edificios y pisos (`IfcBuildingStorey`, con elevación).
  - Conteo por tipo para `IfcWall`, `IfcSlab`, `IfcColumn`, `IfcBeam`, `IfcDoor`, `IfcWindow`, `IfcStair`, `IfcRoof`, `IfcSpace`, total y por piso.
  - Cantidades base (`Qto_*BaseQuantities`: `NetSideArea`/`NetArea`, `NetVolume`, `Length`) sumadas por tipo y por piso, con unidades del modelo
    convertidas a m, m² y m³. Si un elemento no trae cantidades, no se inventan: se cuenta aparte como "sin cantidades".
- Job `archivo.ifc`: `derivados.meta.ifc = resumen`, chunks con frases legibles ("Planta baja: 24 muros, área neta 312,50 m²",
  con el formato argentino de T-036), versión vigente como en `indexar_archivo`. Más grande que `IFC_MAX_MB` (por defecto 200)
  o ilegible → `derivados.vista_ifc="error"` sin reintentos infinitos.
- `archivo.html`: si hay `meta.ifc`, una tabla corta con pisos y conteos (debajo del visor o en lugar del mensaje de "sin vista").

## Criterios de aceptación
- [x] CA1 Un IFC armado en la prueba con `ifcopenshell.api` (proyecto, un piso, dos muros con `Qto_WallBaseQuantities` y un nombre
  de proyecto con frase única) → job → `meta.ifc` con 2 muros y el área sumada al centésimo; la búsqueda encuentra la frase.
- [x] CA2 Aislamiento: la ficha y la búsqueda de un usuario de otra empresa no muestran nada del resumen (404 / vacío).
- [x] CA3 IFC ilegible → error registrado, el job no queda reintentando.
- [x] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Visor 3D (T-040). Precalcular `.frag` de That Open. Herramienta del agente para consultar el IFC (después; por ahora va por la búsqueda).

## Bitácora del ejecutor

- Los sensores rápidos, la puerta de archivos protegidos y la suite completa pasaron. La comprobación local de Compose se omite cuando Docker no está instalado; se ejecuta en CI.

- Rama creada desde `main` en `7b6c269`, que integra T-037 y T-038. Se fijó IfcOpenShell 0.9.0.post1, ya instalado localmente. Se lee el IFC STEP directamente del almacén.
- Las cantidades netas se convierten a m, m² y m³ antes de acumular por tipo y piso. Se respeta la unidad explícita de la cantidad y se redondea al centésimo después de sumar. La ficha distingue los elementos sin cantidades. Los elementos sin piso quedan identificados en su propio grupo.
- El worker reutiliza la comprobación de versión vigente al publicar el resumen y los fragmentos. Un IFC ilegible o que supera el límite configurable de 200 MB deja un estado de error en la ficha.
- Pruebas con modelos IFC4 generados mediante la API de IfcOpenShell. Cubren unidades, pisos, búsqueda, aislamiento y cambio de versión durante el cálculo. La validación con una exportación real de Revit queda fuera de esta prueba.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-26). Unidades convertidas antes de sumar y redondeo al final; pisos y "sin piso"; versión vigente con prueba de carrera; aislamiento cubierto. Calidad: worker con 1 GB para IFC de hasta 200 MB; tipos en la tabla con nombre IFC en vez de castellano; falta probar con una exportación real de Revit. Merge: #55.
