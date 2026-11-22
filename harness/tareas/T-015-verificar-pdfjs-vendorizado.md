---
id: T-015
titulo: Verificar el pdf.js vendorizado contra el paquete oficial
estado: lista
rama: codex/T-015-verificar-pdfjs-vendorizado
creada: 2026-11-22
depende: —
pr:
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
- [ ] CA1 Corrido de verdad (con red) sobre el repo: sin salida y código 0. Anotá en la Bitácora el resultado.
- [ ] CA2 La prueba offline detecta: archivo modificado, archivo de más, `integrity` que no coincide y ruta con `..`.
- [ ] CA3 El paso de CI "Integridad de vendor" corre y termina en verde.
- [ ] CA4 Sensores y suite en verde.

## Fuera de alcance
- Actualizar pdf.js de versión.

## Bitácora del ejecutor

## Dictamen del auditor
