# Candidatos (reglas, skills y sensores propuestos)

Acá los agentes **proponen**; nunca editan `AGENTS.md`, skills ni sensores directamente.

Un archivo por propuesta: `C-NNN-slug.md`
```
---
id: C-NNN
tipo: regla | skill | sensor | hook | poda
propone: codex | claude | leo
evidencia: [H-NNN, PR #N]      # episodios reales que la justifican
estado: propuesto              # propuesto → validado → promovido | descartado
---
Problema: qué salió mal o qué se repite.
Propuesta: el texto exacto de la regla / el pseudocódigo del sensor / el contenido de la skill.
Cómo se valida: la prueba que falla sin esto, o los episodios donde se repitió.
```

**Puerta de validación:** se promueve solo si tiene ≥2 episodios en `harness/log.md` o una prueba que
falla sin la medida, y Leo lo aprueba en una rama `harness/...`. Al promover: mover el contenido a su
lugar oficial, marcar `estado: promovido` y enlazar el commit.
