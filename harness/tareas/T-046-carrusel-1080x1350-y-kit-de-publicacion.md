---
id: T-046
titulo: Carrusel 1080x1350 y kit de publicación
estado: lista
rama: codex/T-046-carrusel-1080x1350-y-kit-de-publicacion
creada: 2026-11-27
depende: T-045
pr:
---

## Objetivo
Desde un contenido de tipo carrusel, el equipo genera las placas en 1080×1350 en el servidor y descarga un kit de
publicación (ZIP con las PNG, el texto y los hashtags) para subirlo a mano a Instagram.

## Contexto mínimo
- Plan: M5 ("carrusel renderizado en el servidor", "kit de publicación") y verificación ("el carrusel sale en 1080×1350").
- T-045: `contenidos_redes` (`fotos`, `slides`), `contenidos.fotos_difundibles`.
- Pillow ya está instalado (lo usan `app/services/pdf_parte.py` y `app/services/dxf.py`). Fuente: la que ya resuelve `dxf._fuente_del_worker`
  o una TTF incluida en Pillow; **no** bajar fuentes de internet.
- Estilo de referencia (no copiar código): placas tipo portada / texto / cierre, fondo oscuro o claro, acento dorado `#C4981F`.
- Almacén por contenido: `almacen.guardar`; los derivados se sirven solo por rutas con control de acceso (convención de T-037).

## Alcance
- Tocar: `app/services/redes/carrusel.py` (nuevo), `app/worker.py` (job `redes.carrusel`), `app/routers/redes.py`, `app/templates/redes/`,
  `app/config.py` y `.env.example` (`REDES_COLOR_ACENTO`, por defecto `#C4981F`; `REDES_TEMA`, `oscuro`|`claro`), `scripts/limpiar_almacen.py`
  (los sha de `contenidos_redes.slides` cuentan como referenciados), `tests/test_carrusel.py` (nuevo).
- No tocar: migraciones existentes (si hace falta una columna nueva, migración `0018`), `app/permisos.py`.

## Diseño pedido
- `carrusel.generar(contenido, fotos) -> list[bytes]`: portada (título + marca `MARCA`), una placa por foto (recorte "cover" a 1080×1350 con
  pie corto), placas de texto si el texto es largo (cortar por párrafos, sin desbordar), y cierre. Máximo 10 placas. PNG RGB, 1080×1350 exactos.
- POST `/proyecto/{codigo}/redes/{id}/carrusel` (CSRF): encola `redes.carrusel`. El job vuelve a comprobar `permite_difusion` y que cada foto siga
  siendo difundible; guarda cada PNG con `almacen.guardar` y escribe `slides = [{"sha256", "orden"}]`. Sin difusión → no genera y deja `estado_carrusel="error"`.
- GET `/proyecto/{codigo}/redes/{id}/slides/{orden}.png` y GET `/proyecto/{codigo}/redes/{id}/kit.zip` (PNGs + `texto.txt` con texto y hashtags):
  mismo control de acceso que T-045; si el proyecto ya no tiene difusión → 404.
- La pantalla del contenido muestra las placas generadas y el botón del kit.

## Criterios de aceptación
- [ ] CA1 Un carrusel con 2 fotos y texto largo → todas las PNG miden exactamente 1080×1350, hay portada y cierre, y son ≤ 10.
- [ ] CA2 `kit.zip` contiene las PNG en orden y `texto.txt` con el texto y los hashtags.
- [ ] CA3 Sin difusión (o quitada después) → el job no genera placas y `slides.png`/`kit.zip` → 404.
- [ ] CA4 Aislamiento: otra empresa y un cliente → 404 en las tres rutas.
- [ ] CA5 `limpiar_almacen` no borra una placa referenciada.
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Video del reel (solo guion, T-047). Publicar automáticamente. Plantillas de diseño editables.

## Bitácora del ejecutor

## Dictamen del auditor
