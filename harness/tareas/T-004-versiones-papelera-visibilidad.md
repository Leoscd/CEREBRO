---
id: T-004
titulo: Versiones, papelera y visibilidad para el cliente
estado: hecha
rama: codex/T-004-versiones-papelera-visibilidad
creada: 2026-11-21
depende: T-003
pr: "#5"
---

## Objetivo
Subir una versión nueva de un archivo sin perder las anteriores, mandar a la papelera y restaurar,
y decidir qué archivos ve el cliente.

## Contexto mínimo
- Router y almacén de T-003: `app/routers/archivos.py`, `app/services/almacen.py`.
- Permisos: `obtener_archivo`, `puede_escribir_en_proyecto`, `puede_editar_proyecto` (`app/permisos.py`).
- Ojo: `obtener_archivo` excluye la papelera; para restaurar hace falta una variante que la incluya (solo para quien puede escribir).

## Alcance
- Tocar: `app/routers/archivos.py`, `app/permisos.py` (solo si hace falta la variante con papelera), `app/templates/proyecto.html`, `tests/test_versiones.py` (nuevo).
- No tocar: migraciones (el modelo de T-002 alcanza; si no alcanza, explicalo antes en la Bitácora).

## Diseño pedido
- `POST /archivos/{id}/versiones` (multipart): `puede_escribir_en_proyecto`; crea versión `numero+1` y actualiza `version_actual_id`. Auditoría `archivo.version`.
- `GET /archivos/{id}/versiones/{numero}/descargar`: cualquier versión del archivo visible.
- `POST /archivos/{id}/papelera` y `POST /archivos/{id}/restaurar`: `puede_escribir_en_proyecto`. Auditoría `archivo.papelera` / `archivo.restaurar`. No se borra ningún blob.
- `POST /archivos/{id}/visibilidad` (campo `visible_cliente`): `puede_editar_proyecto`. Auditoría `archivo.visibilidad`.
- Ficha: por archivo, "Nueva versión", historial desplegable, "A la papelera", tilde "Visible al cliente" (solo quien puede editar).
  Sección "Papelera" con "Restaurar", visible solo para quien puede escribir.

## Criterios de aceptación
- [x] CA1 Subir versión 2 → la descarga normal trae la 2 y `/versiones/1/descargar` trae la 1 intacta.
- [x] CA2 Archivo en papelera: no aparece en la ficha ni se descarga (404) ni lo ve el cliente; restaurado vuelve a verse.
- [x] CA3 El cliente no puede subir versiones, mandar a papelera ni cambiar visibilidad (403); ana (colaboradora) no puede cambiar visibilidad (403) pero sí subir versión.
- [x] CA4 Marcar `visible_cliente` hace que el cliente lo vea y lo descargue; desmarcarlo → 404 para el cliente.
- [x] CA5 Usuario de B sobre cualquiera de estas rutas con ids de A → 404.
- [x] CA6 Cada acción deja su fila en `auditoria`. Sensores y suite en verde.

## Fuera de alcance
- Borrado definitivo y vaciado de papelera. Estados de plano (aprobación) — M posterior.

## Bitácora del ejecutor
- Los cuatro casos fallaron antes del cambio. Pasaron 45 pruebas y el sensor rápido terminó sin salida.
- El bloqueo de la fila del archivo serializa nuevas versiones y cambios de estado. Las acciones conservan el historial y los blobs.
- Un cliente recibe 403 al intentar escribir en un archivo compartido con él. Para archivos privados, ajenos o en papelera se conserva el 404.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-22). FOR UPDATE antes de numerar versión; papelera vedada al cliente en SQL; auditoría verificada en orden. Merge: #5.
