---
id: T-002
titulo: Carpetas y archivos (modelo y permisos)
estado: hecha
rama: codex/T-002-carpetas-y-archivos-modelo
creada: 2026-11-21
depende: —
pr: "#3"
---

## Objetivo
Que cada proyecto tenga carpetas (creadas desde la plantilla de su tipo) y que exista el modelo de
archivos y versiones con reglas de visibilidad, todavía sin pantallas.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Modelo de datos" (Estructura: `carpetas`, `archivos`, `versiones_archivo`).
- `tipos_proyecto.plantilla_carpetas` (jsonb, lista de nombres): `app/db/migraciones/0001_base.sql:109`, ejemplos en `app/services/empresa.py:16-38`.
- Alta de proyecto: `app/services/proyectos.py` → `crear_proyecto`.
- Reglas de acceso: `app/permisos.py` → `proyectos_visibles_sql`, `obtener_proyecto`, `ROLES_ESCRITURA`.
- Fixture con dos empresas y roles: `tests/conftest.py` → `mundo` (A: admin, ana en p1, beto director de p2, cliente de p1; B: pb).

## Alcance
- Tocar: `app/db/migraciones/0002_archivos.sql` (nuevo), `app/services/proyectos.py`, `app/permisos.py`, `tests/test_archivos.py` (nuevo).
- No tocar: routers, plantillas, `0001_base.sql`.

## Diseño pedido
- `carpetas`: id, empresa_id, proyecto_id, padre_id (nullable, misma tabla), nombre, posicion, creada_en timestamptz. Único (proyecto_id, padre_id, nombre).
- `archivos`: id, empresa_id, proyecto_id, carpeta_id, nombre, extension, mime, `visible_cliente boolean default false`,
  `estado_plano` ('borrador','en_revision','aprobado') default 'borrador', `en_papelera_en timestamptz null`,
  `version_actual_id` (nullable, FK diferida o sin FK), creado_por, creado_en.
- `versiones_archivo`: id, empresa_id, archivo_id, numero int, sha256 text, tamano_bytes bigint, mime,
  `origen` ('subida','agente','sesion'), `derivados jsonb default '{}'`, subida_por, creada_en. Único (archivo_id, numero).
- Índices por (empresa_id, proyecto_id) en carpetas y archivos.
- La migración crea las carpetas de los proyectos que ya existen, desde la plantilla de su tipo.
- `crear_proyecto` crea las carpetas de la plantilla en la misma transacción.
- En `app/permisos.py`:
  - `archivos_visibles_sql(u, alias="a")` → condición + params: proyecto visible (reusar `proyectos_visibles_sql`),
    misma empresa, fuera de papelera, y si es cliente solo `visible_cliente`.
  - `obtener_archivo(db, u, archivo_id) -> dict` → 404 si no lo ve (con `mi_rol` del proyecto, como `obtener_proyecto`).

## Criterios de aceptación
- [x] CA1 Un proyecto nuevo trae las carpetas de la plantilla de su tipo, en orden.
- [x] CA2 Un proyecto existente antes de la migración también las tiene (probalo aplicando la migración sobre datos ya cargados o con una prueba directa de la sentencia).
- [x] CA3 Visibilidad (insertando archivos directo en la base): admin A ve los de p1 y p2; ana ve p1 y no p2; el cliente ve solo los `visible_cliente` de p1; admin B no ve ninguno de A.
- [x] CA4 `obtener_archivo` de un archivo ajeno o en papelera → 404 (`HTTPException` 404).
- [x] CA5 `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Subir, bajar, versiones nuevas, papelera desde la interfaz (T-003, T-004).

## Bitácora del ejecutor
- La plantilla se copia en la transacción del alta. Si repite un nombre, se conserva su primera posición, tanto al migrar como al crear un proyecto.
- Las claves foráneas compuestas impiden asociar carpetas, archivos y versiones a otro proyecto o empresa.
- Los cuatro casos fallaron antes del cambio. Para el retrocompletado se aplicó la migración sobre un proyecto creado con el esquema de M0.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-22). Claves foráneas compuestas por empresa; visibilidad reusa proyectos_visibles_sql; 4 roles probados. Merge: #3.
