# Plan: Gestor Sistemático de Proyectos (GSP) con agentes IA por rubro

> revisado: 2026-11-21

## Contexto
Queremos una plataforma integral para la empresa (arquitectura y construcción) con la misma estructura que el curso RAG (`D:\APLICACIONES\CURSO-ATENCION-IA-RAG`):
- **Curso → Tipo de proyecto**: Revit, AutoCAD, SketchUp, Presupuestos/Excel.
- **Módulo → Fase o carpeta**.
- **Clase → Archivo**: al abrirlo se ve el visor con el agente especializado al lado.

Cada agente tiene que poder **hacer el trabajo como una sesión de Claude Code**, con todas las herramientas que ya armamos en AUTOCAD-PYTHON, REVIT-ADD-INS, REVIT-MCP y SketchUp. Al terminar, **sube los avances y documenta lo hecho**. También genera contenido para redes, cierra presupuestos y hace el seguimiento de obra.

Habrá un administrador y usuarios con acceso por proyecto. Más adelante se suman administración y gerencia (precios, materiales, gestión de obra). Todo queda en un VPS propio.

**Decisiones tomadas:**
- Stack FastAPI, como el curso.
- **Solo OpenAI** como proveedor de IA.
- Un conector local en cada PC Windows.
- Una sola empresa, pero con `empresa_id` en todas las tablas por si se suman otras.
- La v1 trae los 4 módulos (proyectos+archivos+agente, presupuestos+precios, seguimiento de obra, redes), ordenados en hitos.
- **VPS Hostinger de 8 vCPU, 32 GB de RAM y 400 GB NVMe.**

El proyecto va en `D:\APLICACIONES\GESTION-SISTEMATICA-PROYECTOS`, que hoy está vacía.

## Hallazgos que condicionan el diseño
- El `rag.search()` del curso (`app/services/rag.py:91-104`) filtra por curso *después* de buscar en toda la base. Con proyectos privados el filtro tiene que ir *dentro* de la consulta.
- Revit MCP (LuDattilo) escucha solo en loopback, y AutoCAD se maneja por COM, que necesita la sesión del usuario. El trabajo CAD/BIM tiene que correr **en la PC**, con una app de bandeja (no un servicio de Windows).
- **Codex CLI de OpenAI** (Apache-2.0) es el equivalente a Claude Code con OpenAI:
  - Corre nativo en Windows y se puede manejar por programa (`codex app-server` por JSON-RPC sobre stdio, o el SDK Python `openai-codex`).
  - Usa MCP por stdio, y `disabled_tools` bloquea herramientas de verdad (el modelo ni las ve).
  - Lee `AGENTS.md` y puede tomar también `CLAUDE.md` (`project_doc_fallback_filenames`).
  - Lee skills en formato SKILL.md compatible, desde `.agents/skills`.
  - Tiene aprobaciones por evento, eventos en streaming y un `outputSchema` para el informe final.
  - Ya tenés `~\.codex\skills` con 22 skills.
- Lo que hoy usan tus sesiones: el MCP `revit-mcp`, 5 skills `revit-*`, 3 skills de AutoCAD (estructura-fundaciones, instalacion-electrica, presentar), los criterios y la SPEC de AUTOCAD-PYTHON, los parsers ezdxf y PDF, los fragmentos C# y el generador `.dyn`.
  - Hay además un puente con SketchUp por archivos (`puente_claude.rb`) y **reglas críticas que viven solo en las memorias de Claude** (borrador antes de modelar, verificar mirando, bugs del MCP, no guardar el archivo del usuario). Esas reglas hay que pasarlas a AGENTS.md.
- **Riesgo n.º 1, todavía sin probar:** el sandbox de Codex en Windows podría bloquear COM (AutoCAD) y el acceso a localhost del plugin de Revit. Se prueba primero (Spike S0).

## Arquitectura
```
Navegador (Jinja2 + JS vanilla) ─HTTPS/SSE─► Caddy ─► app FastAPI ─► PostgreSQL16 + pgvector
                                                │  hub WebSocket del conector
                                                ├─► worker (conversiones, ingesta, PDFs)
                                                ├─► ONLYOFFICE Docs (xlsx/docx en el gestor)
                                                └─► Gotenberg (Office→PDF para previsualizar e indexar)
Conector Local (PC Windows) ─WSS saliente─┘
  └─ codex app-server (cwd = carpeta del proyecto)
       ├─ MCP revit-mcp (node index.js) → Revit
       ├─ MCP motor-autocad (nuevo, envuelve python -m motor.*) → AutoCAD por COM
       ├─ puente SketchUp (archivos .rb) → SketchUp
       └─ AGENTS.md + .agents/skills (kit de agentes)
```

**Base de datos: Postgres + pgvector.** Lo elegimos por cuatro razones:
- Varios procesos escriben a la vez y hay sesiones largas en curso.
- Deja preparado el aislamiento por empresa con RLS.
- Guarda en JSONB las llamadas a herramientas y los eventos de sesión.
- La cola de trabajos usa `SKIP LOCKED`, sin Redis.

Los embeddings siguen locales con fastembed MiniLM (`vector(384)`), como en el curso, para que los documentos no salgan del VPS cuando se indexan.

### Dos formas de ejecutar agentes
| | **Agente web** (en el servidor) | **Sesión de trabajo** (en la PC, con Codex) |
|---|---|---|
| Para qué | Preguntas sobre el proyecto, presupuestos, obra, documentación, redes, gerencia | Tareas reales en Revit, AutoCAD y SketchUp, y trabajo con scripts y archivos locales |
| Motor | **OpenAI Agents SDK (Python)** dentro de FastAPI: herramientas, `needs_approval` que pausa y retoma, sesiones, streaming | **Codex app-server** lanzado por el conector |
| Herramientas | Funciones del servidor (búsqueda, planillas, catálogo de precios, cronograma, parte diario…) | Todas las de tus sesiones: MCP Revit (138, menos las bloqueadas), motor AutoCAD, puente SketchUp, shell y archivos en la carpeta del proyecto, skills |
| Aprobaciones | Tarjeta Aprobar/Rechazar en el panel | Cada `requestApproval` de Codex pasa al panel web; el conector responde según tu decisión y la lista de herramientas permitidas |
| Cierre | Queda guardado en la conversación | **Cierre automático**: sube los archivos de salida, escribe el informe y la bitácora (ver abajo) |

Un agente web puede **delegar** en una sesión de trabajo. Por ejemplo, el agente de Presupuestos pide "computo de muros del modelo Revit", eso abre una sesión, y el resultado vuelve como ítems de presupuesto para aprobar.

## RAG: proyecto + conocimiento y criterios
Hay dos niveles, con filtro antes de buscar:
1. **RAG del proyecto.** Lo que se sube a la obra: planos, pliegos, actas, presupuestos, partes e informes de sesión. Solo lo ven los miembros del proyecto.
2. **Biblioteca de conocimiento y criterios de la empresa.** Normativa (CIRSOC, código de edificación), criterios de la oficina (los `criterios\*.md` de AUTOCAD-PYTHON, las reglas de las skills, los estándares de láminas, capas y rótulos), pliegos tipo, APUs de referencia y **lecciones aprendidas** de obras cerradas.
   - La cura el admin y queda versionada.
   - Al cerrar una sesión o una obra, el agente *propone* lecciones nuevas y un humano las aprueba.

**Qué gana con esto:**
- Todos los agentes trabajan con los mismos criterios.
- Las respuestas citan su fuente.
- Los prompts son más cortos y baratos.
- La empresa acumula aprendizaje.
- Hace de inducción para la gente nueva.

Además, los criterios se publican como skills y AGENTS.md del kit para las sesiones de la PC. Así hay **una sola fuente de criterios** para web y escritorio.

## Kit de agentes (`kit-agentes/` en el repo, se sincroniza con cada PC)
Pasa todo lo que hoy usa Claude Code al formato de Codex:
- **`AGENTS.md` global** con las reglas comunes:
  - español con voseo;
  - trabajar siempre sobre copias;
  - borrador y OK antes de dibujar o modelar;
  - verificar mirando (PDF→PNG);
  - no guardar el archivo del usuario.
- **`AGENTS.md` por disciplina**, armado desde:
  - AutoCAD: `AUTOCAD-PYTHON/CLAUDE.md`, `SPEC.md`, `PLAN.md`, `criterios/*.md` y memorias.
  - Revit: memorias de REVIT-ADD-INS y REVIT-MCP, más bugs del MCP como `place_viewport` (que devuelve la respuesta anterior) o `.Value` en lugar de `IntegerValue`.
  - SketchUp: `chat gpt-sketchup/engine/README.md` y el puente.
- **Skills** en `.agents/skills/`:
  - las 5 `revit-*`, las 3 de AutoCAD y las de documentación (informe de visita, reportes de obra);
  - se reemplaza lo que es propio de Claude: `AskUserQuestion` pasa a una pregunta en el panel, `SendUserFile` pasa a subir el archivo al proyecto, y el scratchpad pasa a una carpeta temporal fija.
- **`config.toml`** generado por el conector en cada sesión:
  - `mcp_servers.revit-mcp` con `disabled_tools = ["send_code_to_revit"]` (salvo que se habilite a mano en esa PC);
  - `mcp_servers.motor-autocad`;
  - `project_doc_fallback_filenames = ["CLAUDE.md"]`;
  - modelo según el agente;
  - un `CODEX_HOME` aislado del conector.
- **`motor-autocad` (servidor MCP nuevo, chico).** Expone `analizar`, `generar`, `verificar`, `presentar`, `estructura`, `acotar`, `locales`, `computo` y `electrica_proceso` como herramientas tipadas que llaman al venv `D:\APLICACIONES\AUTOCAD-PYTHON\.venv`.
  - Las herramientas MCP corren como proceso aparte, lo que debería evitar el sandbox del shell para COM (a verificar en S0).
  - La carpeta de AUTOCAD-PYTHON **no se mueve**: hay rutas fijas en `acaddoc.lsp`.

### Cierre de sesión (documentar el trabajo)
Cada sesión termina con un `outputSchema` fijo:
```
{ resumen, pasos[], archivos_salida[{ruta, tipo, descripcion}], verificaciones[], pendientes[], lecciones_propuestas[] }
```
Con eso, el conector y el servidor:
1. Suben los archivos de salida como **nuevas versiones** de los archivos del proyecto (DWG, PDF, RVT exportado a IFC, PNG).
2. Generan el **informe de sesión** (markdown → PDF) en la carpeta "Bitácora" y una entrada en la bitácora del proyecto.
3. Actualizan el avance de la tarea o el hito vinculado, si corresponde.
4. Indexan el informe en el RAG del proyecto.
5. Dejan las `lecciones_propuestas` en una cola para que el admin las apruebe y pasen a la biblioteca de criterios.
6. Opcionalmente, generan un borrador de contenido para redes con las imágenes de salida, solo si `permite_difusion`.

## Estructura del repo
```
app/  main.py config.py security.py permisos.py conector_hub.py worker.py
      db/ (psycopg3, migraciones/*.sql)
      routers/ auth inicio tipos proyectos carpetas archivos visor agente sesiones
               presupuestos precios obra redes gerencia biblioteca conector onlyoffice admin
      services/ openai_cliente embeddings busqueda almacen procesar/{pdf,imagen,planilla,dxf,dwg,ifc,skp}
                jobs auditoria correo limitador dinero cronograma reporte_pdf clima transcripcion
                redes/carrusel onlyoffice gotenberg
      agentes/ registro.py herramientas/*.py prompts/*.md catalogo/{documentador,presupuestos,obra,redes,gerencia}.py
      sesiones/ orquestador.py cierre.py esquema_informe.json
      templates/  static/js/{panel_agente.js, visores/*}  static/vendor/*
conector/ conector_gsp/{bandeja,vinculacion,canal,codex_app_server,aprobaciones,seguridad,archivos,kit_sync}.py
          mcp_motor_autocad/  build/pyinstaller.spec  instalar.ps1
kit-agentes/ AGENTS.md  disciplinas/{autocad,revit,sketchup,presupuestos}/AGENTS.md  skills/*/SKILL.md
pipeline/ fragmentar.py extraer_pdf.py reindexar.py
frontend-vendor/ (esbuild de una sola vez: cad-viewer, @thatopen, online-3d-viewer, embedpdf)
scripts/ deploy.sh backup.sh restaurar.sh probar_restauracion.sh crear_admin.py seed_demo.py
tests/   docker-compose.yml Dockerfile Caddyfile .env.example CLAUDE.md AGENTS.md docs/PLAN.md
```

### Qué se reutiliza
| Pieza | Origen |
|---|---|
| Sesiones, bcrypt, invitaciones, reset, correo, limitador, SSE con tope por hora, panel del tutor (pasa a dos columnas), fragmentado y embeddings, RRF híbrido | curso: `app/security.py`, `routers/auth.py`, `routers/chat.py`, `class.html:292-433`, `pipeline/ingest.py`, `services/apuntes.py`, `services/embeddings.py`, `services/rag.py` |
| PDF por página con citas | MIGUEL-RAG `rag/ingest.py:48` |
| Permisos por área y obra, documentos con versiones y 3 niveles de acceso, papelera, auditoría inmutable | GESTION-OBRAS `apps/cuentas/permisos.py`, `apps/documentos/`, `apps/auditoria` |
| Herramientas APU (planilla, catálogo, normas, `safe_eval`, verificador) | excel-wrapper `src/apu/tools/*`, `db/schema.py` |
| Parte diario, cronograma, clima, transcripción, PDF | obra-report-w `obra_bot/*` |
| Precios en centavos con historial | PEDIDOS-M14 `src/dominio/dinero.ts`, `precios.ts` |
| Compose endurecido y backups | aulas-fua, PEDIDOS-M14 `despliegue/`, curso `scripts/backup.sh` |
| Carruseles y guiones de reel | carousel-generator, `editor-contenido/skills/*.json` |
| Instrucciones y skills de las sesiones | AUTOCAD-PYTHON, REVIT-ADD-INS, REVIT-MCP, chat gpt-sketchup y las memorias de Claude de cada uno |

## Modelo de datos
Todas las tablas llevan `empresa_id`. Los montos van como `*_centavos bigint`.

- **Acceso:**
  - `empresas`, `usuarios` (admin, miembro o cliente, con TOTP para admin), `invitaciones`, `password_resets`.
  - `areas` (las 6 de GESTION-OBRAS), `usuario_areas`, `clientes`.
- **Estructura:**
  - `tipos_proyecto`: agente por defecto, `agent_context`, herramientas, disciplina del kit, plantilla de carpetas.
  - `proyectos`: código PR-AAAA-NNN, etapa, estado, avance, `permite_difusion`, carpeta local esperada y documento Revit esperado.
  - `proyecto_miembros`: director, colaborador, DT, administración o lector.
  - `carpetas`.
  - `archivos`: tipo, acceso, estado del plano, papelera.
  - `versiones_archivo`: revisión, sha256, almacenamiento por contenido, `derivados` (pdf, dxf, frag, glb, png), origen (subida, agente o sesión).
- **RAG:**
  - `chunks`: `proyecto_id` o `biblioteca_id`, página u hoja, `vector(384)`, tsv.
  - `biblioteca_documentos`: normativa, criterio, pliego tipo o lección, con versión, estado y quién aprobó.
  - `lecciones_propuestas`.
- **Agentes web:**
  - `conversaciones` (con resumen como memoria) y `mensajes`.
  - `agent_runs` y `tool_calls` (argumentos, estado, quién aprobó). Guardan también el estado serializado del Agents SDK para retomar después de una aprobación.
- **Sesiones de trabajo:**
  - `sesiones_trabajo`: proyecto, archivo, usuario, dispositivo, disciplina, pedido, estado, `thread_id` de Codex, tokens e informe en jsonb.
  - `sesion_eventos`: stream de items y aprobaciones.
  - `dispositivos`: hash del token, capacidades, herramientas permitidas, carpetas vinculadas, revocado.
  - `codigos_vinculacion`.
- **Obra:** `tareas`, `avances_tarea`, `hitos`, `bitacora`, `reportes_obra`, `fotos_obra`, `notas_obra`, `pedidos_material`, `stock_obra`.
- **Presupuestos:**
  - `materiales`, `proveedores`.
  - `precios`: solo se agregan filas, nunca se editan; la vista `v_cambios_precio` muestra las variaciones.
  - `indices_costo`, `apus`, `apu_insumos`.
  - `presupuestos`, `rubros_presupuesto`, `items_presupuesto` (con origen de la cantidad: manual, cómputo Revit o cómputo AutoCAD).
  - Esqueleto de `gastos` y `certificados`.
- **Transversales:** `contenidos_redes`, `auditoria` (solo se insertan filas; un trigger bloquea UPDATE y DELETE), `notificaciones`, `jobs`.
- **Permisos** (`app/permisos.py`): `proyectos_visibles`, `archivos_visibles`, `puede_editar_proyecto`, `puede_aprobar_planos`, `puede_ejecutar_herramienta`, `puede_lanzar_sesion`. El `empresa_id` y el `usuario_id` salen **siempre de la sesión**, nunca del pedido.

## Agentes web (OpenAI Agents SDK)
| Agente | Herramientas (✎ = escritura con aprobación) |
|---|---|
| Comunes | buscar_en_proyecto, buscar_en_criterios, leer_archivo, listar_archivos, ficha_proyecto, **lanzar_sesion_trabajo** ✎ |
| Documentador | resumen_actividad (auditoría, sesiones y partes), crear_documento ✎ (md → PDF o DOCX como versión nueva), memoria_descriptiva, informe_semanal |
| Presupuestos/Excel | planilla_leer/escribir ✎, catalogo_buscar, precio_cargar ✎, norma_buscar, calc, presupuesto_crear/agregar_items/actualizar_por_indice ✎, analizar_presupuesto (verificador determinista), exportar a xlsx y pdf |
| Obra | consultar_cronograma, registrar_avance/personal/nota/pedido ✎ (borrador del parte diario), alertas_materiales, cerrar_reporte ✎, resumen_obra |
| Redes | fotos_difundibles (solo si `permite_difusion`), generar_carrusel ✎ (1080×1350), guion_reel, copy_y_hashtags, kit_publicacion |
| Gerencia (admin) | solo lectura: proyectos_atrasados, presupuesto_vs_gastado, precios_que_subieron, uso_ia, actividad_equipo |

- **Límites:** máximo de rondas por ejecución, consultas por hora y tokens. La salida de las herramientas se marca como *datos, no instrucciones*. Desde unos 12 mensajes, la conversación se resume.
- **Modelos:** se configuran por agente en `.env`, sin IDs fijos en el código. Hay que confirmar cuáles habilita tu organización con clave de API. De referencia: uno "sol" para el uso diario, uno "luna" para tareas masivas (clasificar, resumir) y el modelo de Codex para las sesiones.

## Conector Local (Windows)
- **Qué es:** una app de bandeja en Python 3.12 (pystray, websockets, keyring), empaquetada con PyInstaller, que arranca al iniciar sesión.
  - Trae Codex CLI con versión fija (vía `openai-codex`, que incluye el binario) y el `mcp_motor_autocad`.
- **Vinculación:**
  1. Desde `/cuenta/dispositivos` se genera un código de 8 caracteres que dura 10 minutos.
  2. El conector lo canjea en `POST /conector/vincular` y recibe un token: el servidor guarda solo el hash y la PC lo guarda en el Credential Manager.
  3. El token se puede revocar desde la web.
- **Canal:** `wss://…/conector/ws`, siempre saliente.
  - Mensajes: `hola` con capacidades (si Revit, AutoCAD y SketchUp están disponibles, documento abierto, versión del kit), `sesion_iniciar`, `evento`, `aprobacion_pedida`/`aprobacion_respuesta`, `sesion_fin`.
  - Los archivos pesados van por `POST /conector/subir`.
- **Orquestación de una sesión:**
  1. Sincroniza el kit (`kit_sync.py`).
  2. Resuelve la carpeta local del proyecto (vinculada en la PC).
  3. Escribe `config.toml` y `AGENTS.md` de la disciplina.
  4. Lanza `codex app-server` con `thread/start` (`cwd`, sandbox `workspace-write`, política de aprobación) y después `turn/start` (pedido + contexto del proyecto bajado del servidor + `outputSchema`).
  5. Reenvía al panel los deltas y los items.
  6. Permite interrumpir la sesión desde la web.
- **Seguridad:**
  - La lista local de herramientas permitidas tiene la última palabra.
  - `send_code_to_revit` está en `disabled_tools` por defecto.
  - Un hook `PreToolUse` deniega todo lo que esté fuera de la lista.
  - Los borrados (`delete_*`, `purge_unused`) piden además una **confirmación local** con diálogo nativo.
  - Solo trabaja en las carpetas vinculadas.
  - Las sesiones solo se mandan a dispositivos **del mismo usuario**.
  - Deja log local y se puede pausar desde la bandeja.

## Visores (archivo.html con dos columnas redimensionables: visor | panel del agente o de la sesión)
| Formato | 1.ª opción (licencia) | Alternativa |
|---|---|---|
| PDF | **EmbedPDF** (web component, Apache-2.0, con anotaciones y comentarios) | pdf.js (Apache-2.0) |
| Imágenes | **viewer.js** (MIT) + Annotorious (BSD) | OpenSeadragon para láminas enormes |
| DXF | **mlightcad/cad-viewer** (MIT, vanilla TS). ezdxf en el servidor para capas y textos que lee el agente | vagran/dxf-viewer (MPL) |
| DWG | Conversión en el servidor a DXF con **ACadSharp** (MIT, .NET) o `dwg2dxf` de LibreDWG (GPL, como proceso aparte). La preferida es la exportación local con AutoCAD en la sesión | ODA File Converter (revisar licencia) |
| IFC (Revit) | **That Open Engine** (MIT/MPL) con `.frag` precalculado + IfcOpenShell en el servidor (cantidades y propiedades para el agente) | ifc-lite (trae MCP para IA, pide WebGPU), xeokit (AGPL) |
| RVT | Exportar a IFC durante la sesión de Revit. Miniatura con phi-ag/rvt (MIT) | rvt-rs (Apache-2.0, experimental) |
| SKP | **OpenSKP** (MIT) en el servidor → GLB, validar con modelos reales | Exportar glTF desde SketchUp |
| glTF/OBJ/FBX | **Online3DViewer** (MIT) | model-viewer (Apache) |
| XLSX / DOCX / PPTX | **ONLYOFFICE Docs Community** (AGPL, contenedor aparte sin modificar) con JWT y callback de guardado en FastAPI, que crea una versión nueva. Base: ejemplos Python de `ONLYOFFICE/document-server-integration` | Collabora CODE (WOPI) |
| Vista previa y texto para el RAG | **Gotenberg** (MIT): Office → PDF, ezdxf, IfcOpenShell, openpyxl, mammoth | — |

- **Agente y ONLYOFFICE a la vez:** el agente no edita en vivo dentro de ONLYOFFICE (la Automation API sería de pago, falta verificar). Edita con openpyxl y crea una versión nueva. Si el archivo está abierto, primero fuerza el guardado (`forcesave`) y después avisa en el editor.
- **Más adelante:** Speckle Server (Apache-2.0) para versionar modelos y comentar en 3D, y BCF para incidencias BIM vinculadas a tareas (idea de OpenProject).

## Hitos
0. **S0 Spike de riesgo (3-5 días, antes de todo lo demás).** En tu PC, probar Codex app-server con:
   - el MCP de Revit: `get_project_info` y una escritura chica con aprobación;
   - `motor-autocad` como MCP: `analizar` por COM bajo sandbox `workspace-write`;
   - el puente de SketchUp;
   - una skill `revit-laminas-vistas` cargada desde `.agents/skills`;
   - el `outputSchema` del informe.

   **Hay que decidir** si el sandbox alcanza o si hace falta `danger-full-access` con la lista de permitidas y hooks. Si Codex no sirve, el plan B es un bucle propio con el Agents SDK y `MCPServerStdio` en el conector.
1. **M0 Fundaciones (1-2 semanas).**
   - Esqueleto del curso, Postgres con migraciones, entidades de acceso y estructura, permisos portados, auditoría, TOTP.
   - Compose endurecido en el VPS de Hostinger, Caddy y backups fuera del VPS.
   - Resultado: login, inicio con tarjetas por tipo y proyectos con equipo.
2. **M1 Archivos + visores + RAG de dos niveles + Documentador (2-3 semanas).**
   - Versiones, papelera y accesos; worker; visores de PDF, imágenes, DXF, 3D, IFC y ONLYOFFICE; Gotenberg.
   - Ingesta e índice híbrido con filtro previo; biblioteca de criterios con su primera carga (criterios de AUTOCAD-PYTHON, CIRSOC).
   - Panel en dos columnas y agente web Documentador.
3. **M2 Presupuestos y precios (3-4 semanas).**
   - Agents SDK con aprobaciones; materiales, precios con historial e índices; pantalla de presupuestos; importar y exportar Excel.
   - Agente Presupuestos con las herramientas de excel-wrapper y el verificador.
4. **M3 Seguimiento de obra (2-3 semanas).**
   - Cronograma, hitos y bitácora; parte diario desde el celular (fotos y audio); PDF del parte.
   - Notas de obra, pedidos y alertas de materiales, clima; avance vinculado al presupuesto.
5. **M4 Conector + sesiones de trabajo (3-4 semanas).**
   - Kit de agentes (AGENTS.md y skills migradas, `motor-autocad` MCP), conector con vinculación y orquestación de Codex.
   - Aprobaciones en el panel, **cierre de sesión con informe, versiones y bitácora**.
   - Cómputo de Revit o AutoCAD → ítems de presupuesto. Piloto en tu PC.
6. **M5 Redes + Gerencia (2 semanas).**
   - Flujo de contenidos, carrusel renderizado en el servidor, guiones de reel, borrador automático desde el cierre de sesión, kit de publicación (se publica a mano).
   - Agente y tablero de Gerencia, notificaciones.

**Después:** Speckle/BCF, canales de Telegram y WhatsApp (adaptadores de obra_bot), RLS por empresa, gastos y certificados completos, portal del cliente.

## Despliegue (VPS Hostinger: 8 vCPU / 32 GB / 400 GB NVMe)
- **Compose:**
  - `app`, `worker` y `postgres` (pgvector:pg16, sin puertos expuestos);
  - `onlyoffice` (con límite de unos 6 GB), `gotenberg` y `caddy`.
  - Endurecido como aulas-fua: read_only, cap_drop ALL, no-new-privileges, mem_limit, healthcheck.
  - La app queda en `127.0.0.1:8000`. Sobra margen para sumar Speckle más adelante, o para mudar el curso a este VPS.
- **Caddy:** `proyectos.<dominio>`, subidas de hasta 1 GB, WebSocket del conector, ONLYOFFICE en una subruta o subdominio interno con JWT, y `/plataforma` solo accesible por Tailscale.
- **Disco:** 400 GB alcanza para unos 2-3 años de CAD, IFC y fotos. Alerta al 80 % con `salud.py`.
- **Backups:** `pg_dump -Fc` cada noche + restic cifrado de los archivos **fuera del VPS** (Backblaze B2 o similar). Retención 7/4/12 y una prueba de restauración por mes.
- **Privacidad:** los archivos y los embeddings quedan en el VPS. A OpenAI solo van los fragmentos y resúmenes necesarios, desde una organización con retención de datos mínima.

## Verificación
- **En todos los hitos:**
  - pytest contra un Postgres de prueba, con un modelo falso para el SDK que sigue un guion fijo;
  - en cada hito, levantar la app con `preview_start` y recorrer el flujo en el navegador.
- **S0:** checklist manual en tu PC, con los resultados documentados en `docs/SPIKE-S0.md`.
- **M0:** matriz de permisos; una empresa o un proyecto ajeno no se ve por ninguna URL; un UPDATE sobre auditoría falla; backup y restauración.
- **M1:** **prueba de aislamiento**. Una frase única de un PDF del proyecto A no aparece para un usuario de B por búsqueda, chat, descarga, derivado ni herramienta.
  - Los criterios de la biblioteca sí aparecen para los dos.
  - Las citas dan la página correcta.
  - Al guardar en ONLYOFFICE se crea una versión nueva.
- **M2:** una escritura no corre sin aprobación; se retoma bien después de aprobar; un presupuesto de prueba cierra al centavo; el verificador detecta errores; el historial de precios no se puede editar.
- **M3:** tests portados de obra-report-w; un parte confirmado no se puede modificar; el PDF sale numerado.
- **M4:**
  - Un conector falso en los tests (vinculación, revocación, ruteo por usuario, aprobaciones que van y vuelven).
  - Piloto real: una sesión "armá la lámina de plantas" con la skill de Revit termina con PDF y PNG subidos como versión, informe en la bitácora y lección propuesta.
  - `send_code_to_revit` no está disponible; un borrado pide confirmación local.
- **M5:** un proyecto sin difusión nunca muestra fotos; el carrusel sale en 1080×1350; Gerencia rechaza a quien no es admin.

## Riesgos principales
1. Que el sandbox de Codex no permita COM o el localhost de Revit. Se ve en S0; las salidas son el MCP propio fuera del sandbox o acceso completo con lista de permitidas.
2. El MCP de Revit es de un tercero (versión 2026, bugs conocidos). Hay que fijar la versión y verificar con una consulta independiente, como dicen las skills.
3. Codex cambia rápido y tuvo regresiones en Windows. Se fija la versión dentro del conector y se actualiza a mano después de probarla.
4. Instrucciones inyectadas desde documentos. Se controla con aprobaciones, lista de permitidas, confirmación local y la regla de que la salida de una herramienta es dato, no instrucción.
5. Fuga entre proyectos. Se controla con helpers obligatorios, la prueba de aislamiento en cada cambio y RLS más adelante.
6. Licencias: ONLYOFFICE (AGPL) y LibreDWG (GPL) se usan solo como contenedores o procesos aparte y sin modificar. Hay que revisar los términos de ODA si se usa.
7. Costo de tokens en sesiones largas. Topes por sesión, modelo económico para las tareas masivas y uso visible en Gerencia.
8. Alcance grande. Cada hito tiene que poder usarse por su cuenta.

## Primer paso al aprobar
1. **S0** en `D:\APLICACIONES\GESTION-SISTEMATICA-PROYECTOS\spikes\s0-codex\`: un script Python que lanza `codex app-server`, con el `config.toml` y un `motor-autocad` MCP mínimo.
2. En paralelo, **M0**: `git init`, `docs/PLAN.md` (este plan), `CLAUDE.md` y `AGENTS.md`, el esqueleto copiado del curso, el compose con Postgres + pgvector, la migración `0001_base.sql`, auth, permisos y los tests de aislamiento.
