---
id: T-015
titulo: Verificar el pdf.js vendorizado contra el paquete oficial
estado: hecha
rama: codex/T-015-verificar-pdfjs-vendorizado
creada: 2026-11-22
depende: —
pr: "#21"
---

## Objetivo
Comprobar, y dejar comprobable en cada CI, que los archivos de `app/static/vendor/pdfjs/` son idénticos a los del
paquete oficial `pdfjs-dist@6.5.438` de npm (más de 100 mil líneas que nadie revisa a mano).

## Contexto mínimo
- `app/static/vendor/pdfjs/` (agregado en el PR #6). Hallazgo de la auditoría (dictamen en `harness/tareas/T-005-pagina-de-archivo-y-visor.md`).
- El harness ya tiene un paso de CI que corre `python -m scripts.verificar_vendor` **si existe** (no edites `.github/`).

## Alcance
- Tocar: `scripts/verificar_vendor.py` (nuevo), `app/static/vendor/pdfjs/ORIGEN.json` (nuevo), `tests/test_verificar_vendor.py` (nuevo).
- No tocar: los archivos de pdf.js (si alguno no coincide, **no lo "arregles"**: pará y reportalo en la Bitácora).

## Diseño pedido
- `ORIGEN.json`: paquete, versión, URL del tarball, `integrity` (sha512 de npm) y el mapa `archivo_local → ruta_en_el_paquete`.
- `python -m scripts.verificar_vendor`: baja el tarball (solo biblioteca estándar: `urllib`), verifica el `integrity`
  sha512 contra `ORIGEN.json`, abre el `.tgz` **en memoria o en un temporal sin ejecutar nada** (sin `extractall`; leé
  los miembros con `tarfile` y rechazá rutas con `..` o absolutas), y compara el sha256 de cada archivo local con el del paquete.
  También falla si hay archivos locales que no figuran en el mapa. Éxito silencioso; falla instructiva (qué archivo, qué esperaba).
- Prueba offline: un `.tgz` chico armado en la prueba, con un archivo igual, uno distinto y uno de más.

## Criterios de aceptación
- [x] CA1 Corrido de verdad (con red) sobre el repo: sin salida y código 0. Anotá en la Bitácora el resultado.
- [x] CA2 La prueba offline detecta: archivo modificado, archivo de más, `integrity` que no coincide y ruta con `..`.
- [x] CA3 El paso de CI "Integridad de vendor" corre y termina en verde.
- [x] CA4 Sensores y suite en verde.

## Fuera de alcance
- Actualizar pdf.js de versión.

## Bitácora del ejecutor
- Se verificó el SHA-512 del tarball oficial de npm contra su metadato y se compararon los 206 archivos en un checkout con los finales LF de Git. Coincidieron 205.
- El único archivo distinto fue `pdf.mjs` frente a `package/build/pdf.mjs`. SHA-256 local: `f1ee2b86d34109a9d3475b23f26882e1c8df38e051a74e4f1e8fd72c9a51885a`. SHA-256 npm: `cbabeebf4df66f3fe736f2fa2792d332e019a878b0aa88d5e2be17d439079de4`.
- Parada de L-002 aplicada por la diferencia de bytes. Quedaron pendientes el manifiesto, el verificador y su paso de CI. Los archivos vendorizados se conservaron tal como están en Git.
- Al retomar, `pdf.mjs` de npm tenía 0 CRLF y 0 CR sueltos. La única diferencia con el artefacto traído del release de GitHub era el UUID de `INTERNAL_EVT` en la línea 2083. El [build de PDF.js v6.5.438](https://github.com/mozilla/pdf.js/blob/v6.5.438/gulpfile.mjs#L113) lo genera con `crypto.randomUUID()` en cada compilación.
- Con autorización de Leo se reemplazó únicamente el `pdf.mjs` existente con los bytes de `package/build/pdf.mjs` de npm. La regla `app/static/vendor/** -text` en `.gitattributes` preserva los bytes en Windows y Linux.
- El tarball se leyó en memoria y su SHA-512 se validó contra el metadato oficial fijado en `ORIGEN.json`. La comprobación final dio **206 de 206** por SHA-256. `python -m scripts.verificar_vendor` terminó sin salida y con código 0.
- Pasaron las 8 pruebas offline de `tests/test_verificar_vendor.py`. Incluyen archivos faltantes y rutas absolutas POSIX y Windows.
- El índice de Git y un checkout nuevo con `core.autocrlf=true` conservaron los bytes de los 206 archivos verificados. Los sensores rápidos terminaron sin salida y pasó la suite completa, incluidas las pruebas de permisos.
- El CI del PR #21 ejecutó y aprobó el paso «Integridad de vendor (pdf.js contra npm)». [Corrida de GitHub Actions](https://github.com/Leoscd/CEREBRO/actions/runs/45085361794)

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-23). 206/206 contra pdfjs-dist@6.5.438 (sha512 fijado, sin redirecciones, tar en memoria). La diferencia de pdf.mjs era INTERNAL_EVT = crypto.randomUUID() por compilación (release de GitHub vs npm); se dejó el de npm. Corre en cada CI. Merge: #21.
