# Rúbrica general de aceptación

`[sensor]` = lo verifica una máquina (CI); el auditor **no** lo revisa a mano, solo mira que CI esté verde.
`[juez]` = requiere criterio; es lo único que el auditor evalúa leyendo el diff.

## Bloqueantes (uno solo en falla → CAMBIOS o RECHAZAR)
- [sensor] CI verde: protegidos, fast, pytest (incluye `tests/test_permisos.py`).
- [sensor] Migraciones selladas intactas; nuevas numeradas; dinero `*_centavos bigint`; fechas `timestamptz`.
- [sensor] Todo POST con `check_csrf`; ninguna ruta recibe `empresa_id`; solo OpenAI; modelos desde `.env`.
- [juez] **Aislamiento:** cada consulta nueva de negocio filtra por `empresa_id` de la sesión y el proyecto
  se obtiene con `app/permisos.py`. Recurso ajeno → 404, no 403. ¿Hay prueba de "otra empresa no lo ve"?
- [juez] **Auditoría:** cada escritura relevante llama a `auditoria.registrar` dentro de la misma transacción.
- [juez] **Alcance:** el PR hace lo que pide la tarea y nada más. Sin refactors ni dependencias no pedidas.
- [juez] **Criterios:** cada CA de la tarea tiene su prueba o comprobación y esa prueba falla sin el cambio.
- [juez] **Secretos:** nada de claves, `.env`, datos reales ni credenciales en el diff.

## Calidad (no bloquean solos; se anotan)
- [juez] Textos de la interfaz en español rioplatense (voseo), claros para un estudio de arquitectura.
- [juez] Nombres y estructura coherentes con el código vecino; sin código muerto.
- [juez] Errores al usuario con mensaje útil; sin trazas expuestas.
- [juez] Consultas sin N+1 evidentes en listados.

## Dictamen
- **APROBAR:** bloqueantes OK. Se pueden anotar mejoras de calidad para otra tarea.
- **CAMBIOS:** lista numerada, concreta y accionable (archivo:línea → qué hacer). Codex la recibe tal cual.
- **RECHAZAR:** enfoque equivocado; se reescribe la tarea.
