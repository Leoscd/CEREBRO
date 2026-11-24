---
id: T-031
titulo: Clima automático y dictado por audio en el parte
estado: lista
rama: codex/T-031-clima-y-audio
creada: 2026-11-24
depende: T-030
pr:
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
- [ ] CA1 Con un doble de Open-Meteo, el parte muestra el clima del día; sin ubicación o con error → "sin datos" y el parte se puede confirmar igual.
- [ ] CA2 Audio con proveedor falso → texto propuesto; no entra al parte hasta que el DT lo acepta.
- [ ] CA3 Archivo que no es audio o > 20 MB → 400/413. Sin `MODELO_TRANSCRIPCION` con proveedor `openai` → mensaje claro.
- [ ] CA4 Sensores y suite en verde (sin red).

## Fuera de alcance
- Transcripción local (faster-whisper). Pronóstico extendido.

## Bitácora del ejecutor

## Dictamen del auditor
