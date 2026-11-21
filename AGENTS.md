# Gestor Sistemático de Proyectos (GSP)

Plataforma integral para un estudio de arquitectura/construcción: tipos de proyecto (como los
"cursos" del RAG de `D:\APLICACIONES\CURSO-ATENCION-IA-RAG`) → proyectos → fases/carpetas →
archivos con visor y un agente IA especializado al lado. Plan completo y por hitos: `docs/PLAN.md`.

## Reglas
- Responder en español rioplatense (voseo).
- **Solo OpenAI** como proveedor de IA. Modelos configurables por agente en `.env`, nunca fijos en el código.
- **Aislamiento ante todo**: toda consulta de negocio filtra por `empresa_id` del usuario de la
  sesión y por proyecto con `app/permisos.py` (`proyectos_visibles_sql`, `obtener_proyecto`).
  Nunca tomar `empresa_id` ni ids de usuario del pedido. Proyecto ajeno → 404, no 403.
- Todo POST que escribe pasa por `check_csrf` (campo `csrf` en formularios, header `X-CSRF` en fetch).
- Todo cambio relevante se registra con `app/services/auditoria.registrar` dentro de la misma
  transacción. La tabla `auditoria` es inmutable (trigger).
- Migraciones: archivos nuevos numerados en `app/db/migraciones/`; nunca editar uno ya aplicado.
- Dinero en `*_centavos bigint`. Fechas en `timestamptz` (UTC) y se muestran con los filtros `fecha`/`solo_fecha`.
- Cada hito trae sus pruebas; `tests/test_permisos.py` (aislamiento) tiene que pasar siempre.

## Cómo trabajamos (harness) — leé `harness/README.md`
- Codex **ejecuta** tareas de `harness/tareas/` con la skill `.agents/skills/ejecutar-tarea/SKILL.md`,
  en ramas `codex/T-NNN-slug`, y abre PR. Claude **audita** contra `harness/rubricas/general.md`. Leo **mergea**.
- Antes de dar algo por terminado: `python -m scripts.checks.fast` (no imprime nada si está bien) y `python -m pytest -q`.
- Los agentes no editan el harness (AGENTS.md, CLAUDE.md, `.agents/`, `.claude/`, `.github/`, `scripts/checks/`,
  `scripts/hooks/`, rúbricas, log): proponen en `harness/candidatos/`. CI lo hace cumplir.

## Stack
FastAPI + Jinja2 + JS vanilla (como el curso), PostgreSQL 16 + pgvector (psycopg 3 con pool),
sesión por cookie firmada (itsdangerous) versionada, bcrypt, TOTP (pyotp). Docker + Caddy en un
VPS Hostinger (8 vCPU / 32 GB / 400 GB). Backups `pg_dump` + restic fuera del VPS.

## Comandos
- Instalar: `python -m venv .venv` y `.venv\Scripts\pip install -r requirements-dev.txt`
- Desarrollo sin Docker (Postgres embebido + datos demo): `.venv\Scripts\python -m scripts.dev --puerto 8010`
  (credenciales demo en `data/demo-credenciales.txt`). Config de preview: `.claude/launch.json` ("gestor").
- Pruebas: `.venv\Scripts\python -m pytest` (levanta un Postgres embebido; ~2 min).
- Migrar: `python -m app.db.migrar` · Alta de empresa: `python -m scripts.crear_empresa "Nombre" slug email "Nombre admin"`
- VPS: `./scripts/deploy.sh`, `./scripts/backup.sh`, `./scripts/probar_restauracion.sh`

## Estructura
- `app/routers/` auth, inicio (tipos), proyectos (ficha, equipo, hitos), admin (personas, clientes, tipos, alta, auditoría)
- `app/services/` auditoria, correo, limitador, tiempo, proyectos (códigos PR-AAAA-NNN), empresa (alta con áreas y tipos base)
- `app/permisos.py` reglas de acceso (portadas de GESTION-OBRAS) · `app/security.py` sesión, CSRF, 2FA
- `harness/` + `scripts/checks/` + `scripts/harness.py`: cómo se desarrolla ESTE repo con agentes
- `kit-agentes/` (M4, producto) instrucciones y skills para las sesiones de trabajo del estudio en la PC (Codex)
- `conector/` (M4) app de bandeja Windows · `spikes/s0-codex/` prueba de riesgo de Codex

## Estado
- M0 Fundaciones: hecho (auth, 2FA, invitaciones, permisos, proyectos, equipo, hitos, auditoría, deploy).
- Próximo: M1 archivos + visores + RAG de dos niveles + agente Documentador. Ver `docs/PLAN.md`.
