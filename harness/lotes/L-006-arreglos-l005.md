---
id: L-006
titulo: Arreglos que salieron de L-005 (worker, despliegue, ficha IFC)
hito: M1
estado: abierto
etapa_activa: 1
---

# Lote L-006 · arreglos de L-005

Codex: ejecutá las tareas con la skill `.agents/skills/ejecutar-tarea/SKILL.md` ("Modo lote"). Es una cadena:
T-043 sale de `main` con PR contra `main`; T-044 sale de la rama de T-043 con PR contra esa rama.
Sin descargas nuevas: todo lo que hace falta ya está en `requirements.txt` y en las imágenes de Compose.

| Orden | Tarea | Depende de |
|---|---|---|
| 1 | `harness/tareas/T-043-trabajos-pesados-del-worker-en-proceso-a.md` | — (sale de `main`) |
| 2 | `harness/tareas/T-044-ajustes-de-despliegue-y-ficha-ifc.md` | T-043 |

**PARADA:** PRs de T-043 y T-044 abiertos con CI en verde → pará y reportá. Después seguí con `harness/lotes/L-007-m5-redes-y-gerencia.md` solo si el auditor lo habilita.

## Cuándo parar antes
- CI rojo que no lográs arreglar en 3 intentos.
- Una tarea pide tocar algo de su "No tocar" o un archivo protegido.
- Necesitás instalar o descargar algo: pedí permiso y esperá.
- La prueba de humo de Compose se pone roja (las dos tareas tocan `docker-compose.yml`).
