---
id: T-044
titulo: Ajustes de despliegue y ficha IFC
estado: en-curso
rama: codex/T-044-ajustes-de-despliegue-y-ficha-ifc
creada: 2026-11-27
depende: T-043
pr:
---

## Objetivo
Tres arreglos chicos que salieron de las auditorías de L-005: `deploy.sh` levanta ONLYOFFICE cuando está configurado,
el contenedor de ONLYOFFICE no llena el disco con logs, y la tabla del IFC habla en castellano.

## Contexto mínimo
- `scripts/deploy.sh`: arma `PERFIL` solo con `dominio` (si el `Caddyfile` ya no dice `proyectos.tudominio.com`).
- `docker-compose.yml` → servicio `onlyoffice` (no usa el ancla `&endurecido`, así que no tiene `logging`).
- `app/templates/archivo.html` → tabla del IFC muestra `tipo_ifc` (`IfcWall`); `app/services/ifc.py` → `TIPOS` tiene singular y plural en castellano.
- `docs/RECORRIDO-VPS.md` paso 1.3 (hoy dice que `deploy.sh` no levanta ONLYOFFICE).

## Alcance
- Tocar: `scripts/deploy.sh`, `docker-compose.yml` (solo el servicio `onlyoffice`), `app/templates/archivo.html`, `app/routers/archivos.py` (solo si hace falta pasar
  los nombres a la plantilla), `docs/RECORRIDO-VPS.md` (paso 1.3), `tests/test_ifc.py`.
- No tocar: el resto de servicios de Compose, `app/services/ifc.py` (salvo exponer los nombres), migraciones.

## Diseño pedido
- `deploy.sh`: si `.env` tiene `ONLYOFFICE_URL=` con valor no vacío, suma `--profile onlyoffice` a `PERFIL`. Avisá en la salida qué perfiles levantó.
- `onlyoffice`: agregá el mismo bloque `logging` que el ancla `endurecido` (json-file, `max-size: "10m"`, `max-file: "5"`) y `security_opt: ["no-new-privileges:true"]`.
  Si `no-new-privileges` impide arrancar el Document Server (lo verifica la prueba de Compose en CI solo a nivel config), dejalo y anotalo en la Bitácora.
- `archivo.html`: la columna "Tipo" muestra el plural en castellano ("muros", "puertas"); si el tipo no está en `TIPOS`, el nombre IFC.
- `RECORRIDO-VPS.md` paso 1.3: con `ONLYOFFICE_URL` en `.env`, `./scripts/deploy.sh` ya levanta ONLYOFFICE.

## Criterios de aceptación
- [ ] CA1 La ficha de un IFC de prueba muestra "muros" y "puertas" y no muestra `IfcWall` (prueba sobre el HTML).
- [ ] CA2 `docker compose --profile onlyoffice config` incluye `logging` con `max-size: 10m` para `onlyoffice` (la prueba de Compose existente, que corre en CI).
- [ ] CA3 `bash -n scripts/deploy.sh` sin errores, y con un `.env` de prueba con `ONLYOFFICE_URL=https://docs.test` el script arma `--profile onlyoffice`
  (extraé la lógica a una función que se pueda probar con `bash`, o probala con una prueba de pytest que la ejecute con `bash -c` si hay `bash`).
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Mensaje dentro del editor de ONLYOFFICE cuando un guardado se rechaza.

## Bitácora del ejecutor

- Rama desde el commit verde de T-043 (#66). La tabla consulta los plurales de `ifc.TIPOS` y conserva la clase original cuando falta una traducción.
- `deploy.sh` arma los perfiles de dominio y ONLYOFFICE de forma independiente. Lee la última asignación de `ONLYOFFICE_URL` sin ejecutar el archivo de entorno. Los perfiles se imprimen al arrancar y se aplican también a `--logs`.
- Prueba de Bash con un directorio temporal, cuatro combinaciones de perfiles y dobles de Docker y curl. También se verifica la sintaxis y que el script termine con éxito en el uso normal.
- El perfil de ONLYOFFICE rota los logs de Docker (cinco archivos de 10 MB) y usa `no-new-privileges:true`. La prueba de Compose en Linux comprueba la configuración efectiva. El arranque real de Document Server con esa opción queda para el recorrido del VPS.

## Dictamen del auditor
