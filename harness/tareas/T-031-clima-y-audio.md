---
id: T-031
titulo: Clima automático y dictado por audio en el parte
estado: en-revision
rama: codex/T-031-clima-y-audio
creada: 2026-11-24
depende: T-030
pr: "#44"
---

## Objetivo
Que el parte traiga solo el clima del día en la obra y que el DT pueda dictar por audio desde el celular y reciba el texto transcripto para revisar.

## Contexto mínimo
- **Portar**: `D:\APLICACIONES\SAEZ-SANCHEZ\obra-report-w\obra_bot\clima.py` (Open-Meteo, sin clave) y `transcripcion.py` — **solo el camino de OpenAI**
  (el repo también tiene Groq/Anthropic/local: no se portan; regla del proyecto: solo OpenAI).
- Parte diario (T-029), cola de trabajos (T-006). Config por `.env` (modelos nunca fijos en el código).

## Alcance
- Tocar: `app/db/migraciones/0015_ubicacion_obra.sql` (nuevo: `lat`, `lon` en proyectos), `app/services/clima.py` (nuevo), `app/services/transcripcion.py` (nuevo),
  `app/worker.py`, `app/routers/obra.py`, `app/routers/proyectos.py` (editar ubicación), plantillas, `app/config.py`, `.env.example`, `tests/test_clima_audio.py` (nuevo).

## Diseño pedido
- Ubicación del proyecto (lat/lon) editable en la ficha por quien puede editar el proyecto.
- Clima: trabajo `parte.clima` al crear el borrador; llama a Open-Meteo con lat/lon y fecha, guarda resumen (código de tiempo, mín/máx, lluvia) en el parte.
  Sin ubicación o si falla la red → el parte sigue y el clima queda "sin datos". Tiempo de espera corto y sin reintentos infinitos.
- Audio: subir audio (m4a/ogg/webm/mp3, ≤ 20 MB, firma verificada) → trabajo `parte.transcribir` → texto propuesto que el DT acepta o edita antes de que entre al parte.
  `TRANSCRIPCION_PROVEEDOR` (`openai`|`falso`) y `MODELO_TRANSCRIPCION` en `.env`. El audio se guarda en el almacén.
- **Las pruebas nunca salen a la red**: clima y transcripción con dobles.

## Criterios de aceptación
- [x] CA1 Con un doble de Open-Meteo, el parte muestra el clima del día; sin ubicación o con error → "sin datos" y el parte se puede confirmar igual.
- [x] CA2 Audio con proveedor falso → texto propuesto; no entra al parte hasta que el DT lo acepta.
- [x] CA3 Archivo que no es audio o > 20 MB → 400/413. Sin `MODELO_TRANSCRIPCION` con proveedor `openai` → mensaje claro.
- [x] CA4 Sensores y suite en verde (sin red).

## Fuera de alcance
- Transcripción local (faster-whisper). Pronóstico extendido.

## Bitácora del ejecutor

- Porté la consulta meteorológica de `obra-report-w/obra_bot/clima.py` y la llamada a OpenAI de `obra-report-w/obra_bot/transcripcion.py`. Los casos automatizados de `tests/test_clima_audio.py` son nuevos y usan respuestas HTTP de prueba o el proveedor falso.
- El clima consultado corresponde a la fecha local del parte y queda como propuesta. El worker evita alterar un parte ya confirmado. El dictado se incorpora a observaciones solo al aceptar la propuesta editable.
- La ficha admite ambas coordenadas juntas o las dos vacías. El audio se conserva como versión interna para que no lo descarte el limpiador del almacén.
- Reutilicé lat/lon de 0001_base.sql, que ya existían como double precision. Validé pares y rangos en la ficha y en la consulta de clima. La migración 0015 agrega las propuestas de dictado.

## Dictamen del auditor
