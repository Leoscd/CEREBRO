---
id: T-020
titulo: Verificador determinista de presupuestos
estado: hecha
rama: codex/T-020-verificador-de-presupuestos
creada: 2026-11-23
depende: T-019
pr: "#29"
---

## Objetivo
Una revisión automática, **sin IA**, que encuentre errores típicos de un presupuesto antes de emitirlo. Es la
herramienta `analizar_presupuesto` que después usa el agente (T-023).

## Contexto mínimo
- Plan: `docs/PLAN.md` → Agentes web (Presupuestos: "analizar_presupuesto (verificador determinista)") y Verificación M2 ("el verificador detecta errores").
- `presupuestos.calcular` (T-019), `apus.precio_unitario` (T-018), `precios` (T-017).
- El verificador de `excel-wrapper` (`src/apu/llm/prompts/verifier.md`) es con LLM: tomalo solo como lista de ideas de chequeos.

## Alcance
- Tocar: `app/services/verificador.py` (nuevo), `app/routers/presupuestos.py` (mostrar hallazgos y bloquear la emisión con errores), plantilla del presupuesto, `tests/test_verificador.py` (nuevo).

## Diseño pedido
- `analizar(db, empresa_id, presupuesto_id) -> list[Hallazgo]`, cada uno `{codigo, severidad: error|aviso, item_id?, mensaje}` en castellano.
- Chequeos mínimos: ítem sin precio (APU con faltantes o manual vacío) **error**; cantidad ≤ 0 **error**; unidad del ítem ≠ unidad del APU **error**;
  precio vigente más viejo que 90 días respecto de `fecha_precios` **aviso**; rubro vacío **aviso**; ítems duplicados (misma descripción y unidad en el rubro) **aviso**;
  coeficiente fuera de rango (GG o beneficio > 50 %, impuestos > 40 %) **aviso**; un ítem que pesa > 40 % del costo directo **aviso**.
- Emitir un presupuesto con algún **error** → 409 con la lista. Los avisos no bloquean.

## Criterios de aceptación
- [x] CA1 Un caso por chequeo: el presupuesto con ese defecto produce exactamente ese hallazgo, y uno sano produce **cero**.
- [x] CA2 Emitir con un error → 409 y no cambia de estado; con solo avisos → se emite.
- [x] CA3 Determinista: correrlo dos veces da la misma lista en el mismo orden.
- [x] CA4 Sensores y suite en verde.

## Fuera de alcance
- Comparar contra presupuestos de otros proyectos. Chequeos con IA.

## Bitácora del ejecutor

- El verificador usa el mismo resultado que se congela al emitir. Los mensajes y el orden dependen del presupuesto y de su fecha de precios.
- Los errores devuelven 409 y dejan el borrador tal como estaba. Se muestran en la ficha o como JSON. Los avisos permiten emitir.
- Un caso aislado por chequeo confirma que el presupuesto sano da cero hallazgos. También se verificaron repetibilidad, emisión y la suite completa.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-23). Un caso por chequeo con hallazgo único; emisión bloqueada por errores; determinista. Merge: #29.
