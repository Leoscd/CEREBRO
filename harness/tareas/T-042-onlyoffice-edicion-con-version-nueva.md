---
id: T-042
titulo: ONLYOFFICE edición con versión nueva
estado: lista
rama: codex/T-042-onlyoffice-edicion-con-version-nueva
creada: 2026-11-25
depende: T-041
pr:
---

## Objetivo
Quien puede escribir en el proyecto edita el DOCX, XLSX o PPTX en ONLYOFFICE; al guardar, el gestor crea una **versión nueva**
del archivo (con auditoría) y la vista previa y la búsqueda se actualizan solas.

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Visores" (callback de guardado en FastAPI que crea una versión nueva) y "Verificación de M1"
  (al guardar en ONLYOFFICE se crea una versión nueva).
- T-041: `app/services/onlyoffice.py` (`config_editor`, tokens) y la ruta de descarga.
- Crear versiones: `app/routers/archivos.py` → `_crear_version` (hoy recibe un `UploadFile`) y `subir_version` (auditoría y encolados).
- Permiso: `app/permisos.py` → `puede_escribir_en_proyecto`.
- `versiones_archivo.origen` admite `subida`, `agente`, `sesion` (migración 0002): usá `subida`.

## Alcance
- Tocar: `app/services/onlyoffice.py`, `app/routers/archivos.py` (sacar de `_crear_version` una función que reciba un stream ya guardado,
  sin cambiar su comportamiento), `app/config.py` y `.env.example` (`ONLYOFFICE_URL_INTERNA`, por defecto `http://onlyoffice`),
  `tests/test_onlyoffice.py`.
- No tocar: `app/permisos.py`, `app/security.py`, migraciones, `scripts/checks/**`.
- **Excepción de CSRF:** el callback es un POST sin sesión. El auditor ya la dejó en `scripts/checks/post_sin_csrf.txt`
  como `archivos.py:callback_onlyoffice`: la función tiene que llamarse exactamente así y estar en `app/routers/archivos.py`.

## Diseño pedido
- `config_editor`: `mode="edit"` y `permissions.edit=True` solo si `puede_escribir_en_proyecto`; si no, queda como en T-041.
  Agregá `editorConfig.callbackUrl` = `APP_URL_INTERNA` + `/onlyoffice/callback/{token}`, con un token firmado propio
  (`salt="onlyoffice-callback"`, 7 días) que lleva empresa, archivo, versión base y usuario.
- Ruta `POST /onlyoffice/callback/{token}` (función `callback_onlyoffice`):
  - Exige el JWT de ONLYOFFICE (campo `token` del cuerpo o header `Authorization: Bearer`) válido con `ONLYOFFICE_JWT_SECRET`
    y usa **los datos del JWT**, no los del cuerpo sin firmar. Token de la URL inválido o JWT inválido → `{"error": 1}` y nada cambia.
  - `status` 2 o 6: descarga `url` **solo** si el esquema y el host coinciden con `ONLYOFFICE_URL_INTERNA` (si no → `{"error": 1}`),
    con el mismo tope de tamaño que las subidas; guarda en el almacén y crea la versión siguiente con `creado_por` = usuario del token,
    vuelve a comprobar `puede_escribir_en_proyecto` para ese usuario, encola lo mismo que una subida (analizar, vista PDF, indexar)
    y registra `auditoria.registrar(..., "archivo.version_onlyoffice", ...)` en la misma transacción.
  - Si el sha descargado es igual al de la versión actual → no crea nada. Otros `status` → `{"error": 0}` sin cambios.
  - Respuesta siempre `{"error": 0}` cuando terminó bien.

## Criterios de aceptación
- [ ] CA1 Callback con JWT válido y `status=2` (descarga reemplazada por una falsa) → versión `numero+1`, `origen="subida"`, fila de auditoría,
  y jobs de analizar y vista PDF encolados.
- [ ] CA2 JWT inválido, token de URL alterado o `url` con otro host → `{"error": 1}` y ninguna versión nueva.
- [ ] CA3 Aislamiento: un token de callback de la empresa A nunca escribe en un archivo de B; un usuario que perdió el permiso de escritura → sin versión nueva.
- [ ] CA4 `config_editor` da `mode="view"` a quien no puede escribir (por ejemplo, el cliente con acceso) y `mode="edit"` al equipo.
- [ ] CA5 Mismo contenido que la versión actual → no se crea versión.
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- `forcesave` desde el agente y aviso dentro del editor (plan: "Agente y ONLYOFFICE a la vez"). Coedición con presencia. Historial de versiones dentro de ONLYOFFICE.

## Bitácora del ejecutor

## Dictamen del auditor
