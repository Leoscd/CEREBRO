---
id: T-043
titulo: Trabajos pesados del worker en proceso aparte
estado: en-revision
rama: codex/T-043-trabajos-pesados-del-worker-en-proceso-a
creada: 2026-11-27
depende: —
pr: #66
---

## Objetivo
Un DXF o IFC que consume demasiada memoria o tiempo no tira el worker ni deja la ficha en "Preparando la vista previa…"
para siempre: el trabajo se corta, la ficha muestra "no disponible" y el worker sigue con lo demás.

## Contexto mínimo
- Candidato del log (2026-11-26, auditorías #54 y #55): `mem_limit: 1g` del worker y sin tope de tiempo ni memoria al dibujar DXF o abrir IFC.
- `app/worker.py` → `procesar_dxf`, `procesar_ifc`, `procesar_uno` (marca `vista`/`vista_ifc = "error"` al agotar intentos) y `_guardar_derivados`.
- Servicios puros: `app/services/dxf.py` (`leer`, `capas`, `textos`, `svg`) y `app/services/ifc.py` (`resumen`, `frases`).
- `docker-compose.yml` → servicio `worker` (`mem_limit: 1g`).

## Alcance
- Tocar: `app/worker.py`, `app/services/proceso_aislado.py` (nuevo), `app/config.py` y `.env.example`
  (`TRABAJO_PESADO_SEGUNDOS`, por defecto 300; `TRABAJO_PESADO_MEMORIA_MB`, por defecto 2048), `docker-compose.yml` (solo `mem_limit` del worker a `3g`),
  `tests/test_proceso_aislado.py` (nuevo).
- No tocar: `app/services/dxf.py` e `ifc.py` (salvo lo mínimo para que la función sea importable por nombre), migraciones, `app/permisos.py`.

## Diseño pedido
- `proceso_aislado.ejecutar(funcion, *args, segundos, memoria_mb)`: corre `funcion` (importable por nombre, a nivel de módulo) en un proceso hijo
  con `multiprocessing` contexto `spawn`; en Linux aplica `resource.setrlimit(RLIMIT_AS, ...)` en el hijo (en Windows se omite el límite de memoria,
  no el de tiempo). Devuelve el resultado (picklable) o levanta `TrabajoAbortado` si vence el tiempo, el hijo muere (código ≠ 0, OOM) o falla con
  `MemoryError`. Los errores de dominio del hijo (`ValueError`, `DXFError`, errores de ifcopenshell) vuelven como `ErrorDelTrabajo` con el mensaje.
- En el worker, la parte pesada pasa al hijo y la escritura en la base sigue en el padre:
  - DXF: el hijo devuelve `(capas, textos, svg_bytes)`; el padre guarda como hoy.
  - IFC: el hijo devuelve el `resumen`; el padre arma frases y chunks como hoy.
- `TrabajoAbortado` o `ErrorDelTrabajo` → `vista="error"` (DXF) o `vista_ifc="error"` (IFC) y el trabajo termina **sin reintento**.
  Logueá el motivo (tiempo, memoria, caída) sin el contenido del archivo.

## Criterios de aceptación
- [x] CA1 Con `TRABAJO_PESADO_SEGUNDOS=1` y una función de prueba que duerme 5 s → `TrabajoAbortado` en menos de 3 s y el hijo no queda vivo.
- [x] CA2 Una función de prueba que termina con `os._exit(137)` → `TrabajoAbortado`; una que levanta `ValueError("x")` → `ErrorDelTrabajo("x")`.
- [x] CA3 Un DXF y un IFC de prueba (los de `tests/test_dxf.py` y `tests/test_ifc.py`) siguen procesándose igual por el proceso hijo.
- [x] CA4 Con `procesar_ifc` forzado a abortar (monkeypatch del ejecutor) → `vista_ifc="error"`, trabajo `hecho` y la ficha dice "no disponible".
- [x] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Aislar Gotenberg (ya es otro contenedor) o los jobs de embeddings.

## Bitácora del ejecutor

- DXF e IFC se leen con `spawn`. El hijo escribe el resultado en un archivo temporal privado para que un SVG grande no bloquee la espera del padre. El padre aplica el plazo, recoge el proceso y conserva las escrituras en la transacción del job.
- Linux limita el espacio virtual con `RLIMIT_AS`; Windows conserva el plazo. Los valores por defecto son 300 segundos y 2048 MiB. El servicio worker dispone de 3 GiB en Compose.
- El worker registra la categoría del fallo y completa el job en el primer intento. Conserva la comprobación de versión vigente antes de publicar chunks o derivados.
- Leo autorizó dos ajustes de alcance: mostrar el error del resumen junto al visor de un IFC válido y conservar la prueba de cambio concurrente de versión moviendo su punto de intercepción al ejecutor. El CI Linux comprueba el límite de memoria.

## Dictamen del auditor
