---
id: T-030
titulo: PDF numerado del parte diario
estado: en-revision
rama: codex/T-030-pdf-del-parte
creada: 2026-11-24
depende: T-029
pr: "#43"
---

## Objetivo
Al confirmar un parte se genera su PDF numerado (con fotos) y queda guardado como archivo del proyecto en la carpeta
"Bitácora", visible en el visor de PDF existente.

## Contexto mínimo
- **Portar** el armado del PDF de `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\salidas.py` (usa `fpdf2`).
- Parte confirmado (T-029). Archivos y versiones (`app/routers/archivos.py`, `_crear_version`), carpeta "Bitácora" de la plantilla de tipos (`app/services/empresa.py`).
- Cola de trabajos (`app/services/jobs.py`, `app/worker.py`).

## Alcance
- Tocar: `app/services/pdf_parte.py` (nuevo), `app/worker.py` (manejador), `app/services/partes.py` (encolar al confirmar), `requirements.txt` (`fpdf2`, versión fija),
  `app/static/fonts/` (fuente libre con tildes, si hace falta, con su licencia), `tests/test_pdf_parte.py` (nuevo).

## Diseño pedido
- Trabajo `parte.pdf` encolado en la misma transacción de la confirmación. El worker arma el PDF y lo guarda como archivo
  `Parte NNN - AAAA-MM-DD.pdf` en la carpeta "Bitácora" del proyecto (si no existe, la crea), `origen='agente'`, y lo indexa (T-007) para el RAG.
- Encabezado con número, obra, fecha, DT y clima; secciones del parte; fotos reducidas con su descripción; pie con "Parte N.º NNN · página X de Y".
- **Idempotente**: si el trabajo corre dos veces, no crea dos archivos.
- El worker monta el almacén en solo lectura en Docker: para escribir el PDF, el manejador **no** escribe en disco del worker; mirá cómo resolverlo
  (p. ej. que el trabajo lo ejecute la app, o cambiar el montaje del worker con justificación en la Bitácora) y que la prueba de humo de Compose siga verde.

## Criterios de aceptación
- [x] CA1 Confirmar un parte → aparece "Parte 001 - …pdf" en Bitácora; el texto extraído del PDF tiene el número, la fecha y una frase del parte.
- [x] CA2 Tildes y ñ se ven bien (extraé el texto y compará).
- [x] CA3 Correr el trabajo dos veces → un solo archivo.
- [x] CA4 La búsqueda del proyecto encuentra una frase del parte con su página.
- [x] CA5 Sensores, suite y prueba de humo de Compose en verde.

## Fuera de alcance
- Firma digital del parte. Envío por mail o WhatsApp.

## Bitácora del ejecutor

- Porté de `obra-report-w/obra_bot/salidas.py` la estructura por secciones, el tratamiento de caracteres y los epígrafes. La prueba de integración es nueva en `tests/test_pdf_parte.py`: verifica extracción con tildes y ñ, imagen embebida, número, fecha, búsqueda por página y ejecución duplicada.
- Fijé fpdf2 2.8.5. El PDF y las fotos reducidas se generan en memoria. Helvetica cubre el español con Latin-1. Los caracteres fuera de ese repertorio se sustituyen.
- Habilité la escritura del worker en el bind mount compartido `data/archivos` para publicar ahí con el almacén existente. El resto del sistema de archivos del contenedor conserva su restricción. El bloqueo por obra y la auditoría transaccional identifican un trabajo repetido.

## Dictamen del auditor
