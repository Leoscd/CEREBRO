---
id: T-040
titulo: Visor 3D e IFC en el navegador
estado: en-revision
rama: codex/T-040-visor-3d-e-ifc-en-el-navegador
creada: 2026-11-25
depende: — (etapa 1 en main)
pr: #58
---

## Objetivo
Al abrir un modelo GLB, glTF, OBJ, STL o IFC se ve en 3D en el visor del archivo (orbitar, zoom, encuadrar), con el panel
del agente al lado como en el PDF.

## Contexto mínimo
- Decisión de Leo (2026-11-25): v1 **sin bundle**: Online3DViewer (MIT) y web-ifc (MPL-2.0) vendorizados **tal cual desde npm**.
  That Open Engine queda para más adelante.
- H-009 (`harness/log.md`): archivos de terceros **solo desde el tarball de npm**, con `ORIGEN.json` y verificación en CI.
- Verificador: `scripts/verificar_vendor.py` (hoy acepta solo `pdfjs-dist` en `app/static/vendor/pdfjs`) y `tests/test_verificar_vendor.py`.
- Visor actual: `_tipo_de_vista` en `app/routers/archivos.py`, `app/templates/archivo.html`, `app/static/archivo.js` (`iniciarPdf` como modelo).

## Alcance
- Tocar: `scripts/verificar_vendor.py`, `tests/test_verificar_vendor.py`, `app/static/vendor/o3dv/**` (nuevo), `app/static/vendor/web-ifc/**` (nuevo),
  `app/routers/archivos.py`, `app/templates/archivo.html`, `app/static/archivo.js`, `app/static/style.css`, `tests/test_visor.py`.
- No tocar: `app/static/vendor/pdfjs/**`, `.github/` (el paso de CI ya corre `python -m scripts.verificar_vendor`), `.gitattributes`
  (si hace falta `-text` para el vendor nuevo, pedilo en la Bitácora: lo agrega el auditor).
- Permiso de descarga: podés bajar de `registry.npmjs.org` los tarballs de `online-3d-viewer` y `web-ifc` (y `three` solo si el punto siguiente lo exige). Nada más.

## Diseño pedido
- `verificar_vendor`: recorre **cada** `app/static/vendor/*/ORIGEN.json`. Para cada uno exige `url ==
  https://registry.npmjs.org/<paquete>/-/<nombre-sin-scope>-<version>.tgz`, el mismo control de "sin declarar / faltantes" y
  hashes iguales al tarball. Mantené el caso de pdf.js y sumá uno que falle con un paquete de otro host.
- `app/static/vendor/o3dv/`: `build/engine/o3dv.min.js` y `LICENSE` de la última versión de `online-3d-viewer`.
- `app/static/vendor/web-ifc/`: **los archivos exactos** que Online3DViewer carga para IFC (leé en su código el nombre que pide su
  importador IFC y la versión de `web-ifc` de su `package.json`), con su `LICENSE`. Configurá la ubicación de librerías externas de
  o3dv para que apunte a `/static/vendor/...`: **ninguna carga desde CDN** (la prueba busca `cdn`, `unpkg` y `jsdelivr` en `archivo.js` y la plantilla).
  Si `o3dv.min.js` necesita `three` aparte, vendorizalo igual desde npm. Si necesita algo que no está como archivo en un tarball de npm → **pará y reportá**.
- `_tipo_de_vista` → `"modelo3d"` para `glb, gltf, obj, stl, ply, 3ds, off, ifc` con control liviano de cabecera donde exista
  (`glTF` para GLB, `ISO-10303-21` para IFC, `solid`/binario para STL). `/contenido` sigue sirviendo estos como `attachment` (el visor usa `fetch`).
- `archivo.js` → `iniciarModelo3d`: hace `fetch` del contenido y se lo pasa a o3dv como archivo **con el nombre original** (o3dv detecta el
  formato por la extensión). glTF con `.bin` o texturas externas → mensaje "Subí el modelo como GLB o glTF embebido".
- Cargá los scripts del vendor con `?v={{ static_version }}`.

## Criterios de aceptación
- [x] CA1 `python -m scripts.verificar_vendor` pasa con los tres directorios y falla si se altera un byte de `o3dv.min.js` (prueba).
- [x] CA2 `_tipo_de_vista` devuelve `modelo3d` para un GLB y un IFC de prueba y `None` para un `.glb` que en realidad es texto.
- [x] CA3 La página de un GLB renderiza el contenedor del visor 3D con la ruta del vendor local, sin URLs de CDN.
- [x] CA4 Aislamiento: `/contenido` de un modelo de otra empresa → 404 (sumá el caso a `tests/test_visor.py`).
- [x] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.
- [x] En la Bitácora: versión de cada paquete, licencia y la lista de archivos vendorizados.

## Fuera de alcance
- Modelos de varios archivos (glTF con `.bin` aparte, OBJ con `.mtl`). FBX y SKP. That Open y `.frag`. Medir o cortar en el visor.

## Bitácora del ejecutor

- Rama desde `origin/codex/T-039-ifc-en-el-servidor` (`2af6373`), base pedida para el PR. El #55 quedó integrado con ese mismo commit.
- `online-3d-viewer@0.18.0` (MIT): `o3dv.min.js` y `LICENSE` (nombre publicado: `LICENSE.md`). Three está incluido en el motor.
- `web-ifc@0.0.68` (MPL-2.0): `web-ifc-api-iife.js` y `web-ifc.wasm` del tarball. La versión se lee en el importador distribuido por o3dv. El tarball omite la licencia. Leo autorizó incorporar únicamente `LICENSE.md` del commit oficial `d7225478eb552ecc052bbad2f4ecf3a835d535fd` como `LICENSE`. Su URL y SHA-256 constan en `ORIGEN.json`.
- El importador IFC reutiliza la API inicializada con WASM local de un hilo. El visor conserva las cantidades por piso y la descarga del original. Para glTF se indican los recursos externos y la compresión Draco que requiere un decodificador adicional.
- Humo en Chrome con modelos generados localmente: cargaron los ocho formatos y se habilitó Encuadrar. El caso glTF con un `.bin` aparte mostró el mensaje solicitado. Se comprobó la petición local de WASM y cero peticiones a otros orígenes.

## Dictamen del auditor
