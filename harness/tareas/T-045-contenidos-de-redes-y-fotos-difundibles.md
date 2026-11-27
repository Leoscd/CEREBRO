---
id: T-045
titulo: Contenidos de redes y fotos difundibles
estado: lista
rama: codex/T-045-contenidos-de-redes-y-fotos-difundibles
creada: 2026-11-27
depende: — (L-006 en main)
pr:
---

## Objetivo
Cada proyecto tiene una pantalla "Redes" donde el equipo arma borradores de contenido (carrusel o reel): título, texto,
hashtags y las fotos elegidas. Si el cliente no autorizó la difusión, la pantalla lo dice y **no muestra ninguna foto**.

## Contexto mínimo
- Plan: `docs/PLAN.md` → M5, tabla de agentes fila "Redes" y verificación de M5 ("un proyecto sin difusión nunca muestra fotos").
- `proyectos.permite_difusion` (migración 0001; se edita en `app/routers/proyectos.py` y se muestra en `proyecto.html`).
- Fotos: `fotos_obra` (migración 0014, ligadas a `reportes_obra`; usá solo las de partes `confirmado`) y archivos del proyecto con versión
  de imagen (`_tipo_de_vista` en `app/routers/archivos.py` devuelve `"imagen"`), excluyendo papelera.
- Modelo de router por proyecto: `app/routers/obra.py` (`_obra`, uso de `obtener_proyecto`, plantillas en `app/templates/obra/`).
- Auditoría: `app/services/auditoria.registrar`. Formularios: `<select>` con opción vacía → ver H-013 y `tests/test_formularios_navegador.py`.

## Alcance
- Tocar: `app/db/migraciones/0017_contenidos_redes.sql` (nueva), `app/services/redes/__init__.py` y `app/services/redes/contenidos.py` (nuevos),
  `app/routers/redes.py` (nuevo), `app/main.py` (registrar el router), `app/templates/redes/` (nuevas), `app/templates/proyecto.html` (enlace "Redes"),
  `tests/test_redes.py` (nuevo).
- No tocar: `app/permisos.py`, migraciones existentes, `app/routers/archivos.py`.

## Diseño pedido
- Tabla `contenidos_redes`: `id`, `empresa_id`, `proyecto_id`, `tipo` (`carrusel` | `reel`), `estado` (`borrador` | `listo` | `publicado`),
  `titulo`, `texto`, `hashtags` (text[]), `guion` (jsonb, para reels), `fotos` (jsonb: lista de `{origen: "foto_obra"|"archivo", id, sha256}`),
  `slides` (jsonb, lo llena T-046), `creado_por`, `creado_en`, `actualizado_en`, `publicado_en`. FK compuesta con `(empresa_id, proyecto_id)` como el resto.
- `contenidos.fotos_difundibles(db, user, proyecto)`: lista vacía **siempre** si `permite_difusion` es falso; si no, fotos de partes confirmados y
  archivos de imagen del proyecto, con un enlace que pasa por las rutas con control de acceso que ya existen (`/archivos/{id}/contenido`).
- Rutas bajo `/proyecto/{codigo}/redes`: listado, crear borrador, editar (título, texto, hashtags, fotos elegidas de la lista difundible),
  marcar `listo` y marcar `publicado` (se publica a mano; solo registra la fecha). Todo POST con `check_csrf` y auditoría.
- Permisos: ver y escribir con `puede_escribir_en_proyecto`; cliente o sin acceso → 404. Elegir una foto que no está en `fotos_difundibles` → 400.
- Si `permite_difusion` pasa a falso después, los contenidos guardados **no muestran** sus fotos (se filtran al leer) y no se pueden marcar `listo`.

## Criterios de aceptación
- [ ] CA1 Proyecto con difusión: se crea un borrador con 2 fotos (una de un parte confirmado, una de un archivo), se edita y se marca `listo` y `publicado`; hay filas de auditoría.
- [ ] CA2 Proyecto **sin** difusión: la pantalla no contiene ninguna URL de foto ni sha256, `fotos_difundibles` → `[]`, y un POST con un id de foto → 400.
- [ ] CA3 Quitar la difusión a un proyecto con un contenido que ya tenía fotos → la página del contenido no muestra fotos y "marcar listo" → 409.
- [ ] CA4 Aislamiento: otra empresa y un cliente del proyecto → 404 en todas las rutas; una foto de otro proyecto → 400.
- [ ] CA5 Los formularios con `<select>`/opciones vacías se prueban armando el POST desde el HTML (como `tests/test_formularios_navegador.py`).
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Dibujar el carrusel (T-046), el agente (T-047), publicar automáticamente en redes, borrador desde el cierre de sesión (M4).

## Bitácora del ejecutor

## Dictamen del auditor
