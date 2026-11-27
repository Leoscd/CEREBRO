---
id: T-041
titulo: ONLYOFFICE solo lectura
estado: en-revision
rama: codex/T-041-onlyoffice-solo-lectura
creada: 2026-11-25
depende: — (etapa 2 en main)
pr: #60
---

## Objetivo
Si el servidor tiene ONLYOFFICE configurado, un DOCX, XLSX o PPTX se abre en el editor de ONLYOFFICE en modo lectura dentro
de la ficha del archivo. Si no está configurado, se sigue viendo la vista PDF de Gotenberg (T-037).

## Contexto mínimo
- Plan: `docs/PLAN.md` → "Visores", fila XLSX/DOCX/PPTX (ONLYOFFICE Docs Community, AGPL, contenedor aparte sin modificar, JWT),
  y "Infraestructura" (límite de unos 6 GB). Base de referencia: ejemplos Python de `ONLYOFFICE/document-server-integration`.
- Vista PDF de Office y extensiones: T-037 (`archivo.html`, `_tipo_de_vista`, `/archivos/{id}/vista.pdf`).
- Firmas con `itsdangerous`: `app/security.py` (mismo `SECRET_KEY` de `app/config.py`, con un `salt` propio).
- `Caddyfile`: un solo sitio `proyectos.tudominio.com` → `app:8000`.

## Alcance
- Tocar: `docker-compose.yml` (servicio `onlyoffice` en el **perfil** `onlyoffice`, para que la prueba de humo no lo levante),
  `Caddyfile` (sitio nuevo `docs.tudominio.com` → `onlyoffice:80`), `.env.example` y `app/config.py`
  (`ONLYOFFICE_URL`, `ONLYOFFICE_JWT_SECRET`, `APP_URL_INTERNA`), `requirements.txt` (`PyJWT`, versión fija),
  `app/services/onlyoffice.py` (nuevo), `app/routers/archivos.py`, `app/templates/archivo.html`, `app/static/archivo.js`,
  `tests/test_onlyoffice.py` (nuevo).
- No tocar: `app/permisos.py`, `app/security.py`, migraciones, `scripts/checks/**`.

## Diseño pedido
- Compose: `onlyoffice/documentserver` con **tag fijo**, `profiles: ["onlyoffice"]`, `JWT_ENABLED=true`, `JWT_SECRET=${ONLYOFFICE_JWT_SECRET}`,
  `mem_limit: 6g`, volúmenes con nombre para datos y logs, sin `ports`. Imagen sin modificar.
- `app/services/onlyoffice.py`:
  - `token_descarga(empresa_id, archivo_id, version_id) -> str` y `leer_token_descarga(token)` con `URLSafeTimedSerializer`
    (`salt="onlyoffice-descarga"`, 10 minutos).
  - `config_editor(user, archivo, version) -> dict`: `document` (`fileType`, `key` = id de archivo + id de versión + 12 caracteres del sha,
    `title`, `url` = `APP_URL_INTERNA` + ruta de descarga con token, `permissions.edit=False`), `documentType` (word/cell/slide),
    `editorConfig` (`mode="view"`, `lang="es"`, `user` con id y nombre). Agregá `token` = JWT HS256 de toda la config con `ONLYOFFICE_JWT_SECRET`.
- Ruta `GET /onlyoffice/descarga/{token}` (sin sesión: la pide el contenedor): valida el token, busca la versión **con `empresa_id` del token**
  y comprueba que el archivo no esté en la papelera. Token vencido, alterado o que no coincide → 404. Respuesta `attachment`, `private, no-store`.
- `archivo.html`: si la extensión es Office y `ONLYOFFICE_URL` está configurado, un contenedor del editor que carga
  `{ONLYOFFICE_URL}/web-apps/apps/api/documents/api.js` y `new DocsAPI.DocEditor(...)` con la config (pasala en un `<script type="application/json">`,
  no interpolada en JS). Si no hay `ONLYOFFICE_URL`, queda el visor PDF de T-037.

## Criterios de aceptación
- [x] CA1 `config_editor` decodifica con `ONLYOFFICE_JWT_SECRET` (PyJWT) y trae `mode="view"`, `edit=False` y la `url` de descarga con token.
- [x] CA2 `GET /onlyoffice/descarga/{token}` válido → 200 con los bytes de la versión; vencido (reloj adelantado), alterado o de un archivo en papelera → 404.
- [x] CA3 Aislamiento: un token firmado para la empresa A con el id de un archivo de B → 404; la página del archivo para un usuario sin acceso → 404.
- [x] CA4 Sin `ONLYOFFICE_URL` la página sigue mostrando la vista PDF de T-037 (prueba sobre el HTML).
- [x] CA5 `docker compose config` y `docker compose --profile onlyoffice config` válidos; la prueba de humo sigue en verde sin levantar ONLYOFFICE.
- [x] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Edición y guardado (T-042). Coedición, comentarios y formularios PDF.

## Bitácora del ejecutor

- La ficha sirve ONLYOFFICE para DOCX, XLSX y PPTX cuando están configurados URL y secreto. Las demás configuraciones conservan la vista previa existente.
- PyJWT 2.15.1 ya estaba instalado. Imagen oficial sin modificar `onlyoffice/documentserver:10.0.0.1`, tag verificado en Docker Hub. El perfil dispone de 6 GiB, volúmenes de datos y logs y una red interna compartida con la app y Caddy para intercambiar documentos.
- La URL firmada identifica la versión exacta y caduca a los 10 minutos. La descarga vuelve a comprobar empresa, archivo y papelera. El JWT cubre toda la configuración entregada al editor.
- Las pruebas cubren los tres formatos, el PDF alternativo y las restricciones de descarga. La CLI de Docker no está instalada en esta PC. El CI verifica ambas configuraciones de Compose y ejecuta el humo del perfil normal. El editor gráfico requiere un Document Server configurado.

## Dictamen del auditor
