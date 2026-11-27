---
id: L-005
titulo: M1 — visores pendientes (Office, DXF, IFC, 3D, ONLYOFFICE)
hito: M1
estado: abierto
etapa_activa: 3        # etapa 1 (T-037 a T-039, PRs #53-#55) y etapa 2 (T-040, #58) mergeadas el 2026-11-26
---

# Lote L-005 · visores pendientes de M1 (H-012)

Codex: ejecutá las tareas de la etapa activa con la skill `.agents/skills/ejecutar-tarea/SKILL.md` ("Modo lote").

Decisiones de Leo (2026-11-25):
- **v1 sin bundle.** DXF se dibuja en el servidor (ezdxf → SVG) y 3D/IFC usan Online3DViewer + web-ifc vendorizados tal cual desde npm.
  `cad-viewer` y That Open Engine quedan para después: necesitan esbuild y CI no puede verificar un bundle contra npm (H-009).
- ONLYOFFICE entra en una etapa aparte: primero solo lectura y después edición con versión nueva.

Reglas del lote:
- Cada etapa es una cadena: la primera tarea sale de `main`; cada una de las siguientes sale de la rama de la anterior, con PR contra esa rama.
- Sin migraciones: los derivados van en `versiones_archivo.derivados` (convención en T-037).
- **Permisos de descarga:** PyPI para `ezdxf`, `ifcopenshell` y `PyJWT`; npm (`registry.npmjs.org`) para `online-3d-viewer`, `web-ifc` y
  `three` (solo si T-040 lo exige); Docker Hub para `gotenberg/gotenberg` y `onlyoffice/documentserver`, siempre con tag fijo. Nada más.

## Etapa 1 — servidor: Gotenberg, DXF e IFC
| Orden | Tarea | Depende de |
|---|---|---|
| 1 | `harness/tareas/T-037-gotenberg-y-vista-previa-de-office.md` | — (sale de `main`) |
| 2 | `harness/tareas/T-038-dxf-en-el-servidor-y-vista-svg.md` | T-037 |
| 3 | `harness/tareas/T-039-ifc-en-el-servidor.md` | T-038 |

**PARADA 1:** PRs de T-037, T-038 y T-039 abiertos con CI en verde → pará y reportá la lista.

## Etapa 2 — visor 3D e IFC (solo si `etapa_activa: 2`)
| Orden | Tarea | Depende de |
|---|---|---|
| 4 | `harness/tareas/T-040-visor-3d-e-ifc-en-el-navegador.md` | — (etapa 1 en `main`: sale de `main`) |

**PARADA 2:** PR de T-040 abierto con CI en verde → pará y reportá.

## Etapa 3 — ONLYOFFICE (solo si `etapa_activa: 3`)
| Orden | Tarea | Depende de |
|---|---|---|
| 5 | `harness/tareas/T-041-onlyoffice-solo-lectura.md` | — (etapa 2 en `main`: sale de `main`) |
| 6 | `harness/tareas/T-042-onlyoffice-edicion-con-version-nueva.md` | T-041 |

**PARADA 3 (fin del lote):** PRs de T-041 y T-042 abiertos con CI en verde → pará y reportá.

## Cuándo parar antes
- CI rojo que no lográs arreglar en 3 intentos.
- Una tarea pide tocar algo de su "No tocar" o un archivo protegido.
- Una librería necesita algo que no está en los permisos de descarga de arriba (otro paquete, un CDN, un build): pedí permiso y esperá.
- La prueba de humo de Compose se pone roja (T-037 y T-041 tocan `docker-compose.yml`): resolvelo antes de seguir.
- El auditor dejó **CAMBIOS** en un PR: resolvelos primero y traé el arreglo a las ramas siguientes con `git merge`.
