---
id: T-001
titulo: Logout con CSRF
estado: lista
rama: codex/T-001-logout-con-csrf
creada: 2026-11-21
pr:
---

## Objetivo
Que cerrar sesión exija el token CSRF, para que otro sitio no pueda desloguear al usuario con un formulario oculto.

## Contexto mínimo
- `app/routers/auth.py` → `logout()` (hoy POST sin dependencias).
- `app/security.py` → `check_csrf`, `csrf_token(usuario_id)`; la plantilla tiene `csrf_token` como global (`app/templates.py`).
- `app/templates/base.html:18` → formulario "Salir".
- Patrón de prueba con sesión y CSRF: `tests/test_auth.py`, fixtures en `tests/conftest.py`.

## Alcance
- Tocar: `app/routers/auth.py` (solo `logout`), `app/templates/base.html` (formulario Salir), `tests/test_auth.py`.
- No tocar: el resto de las rutas de auth, `scripts/checks/` (la excepción la saca el auditor).

## Criterios de aceptación
- [ ] CA1 `POST /logout` con sesión y token válido → 303 a `/login` y la cookie de sesión se borra.
- [ ] CA2 `POST /logout` con sesión y **sin** token (o token inválido) → 403 y la sesión sigue activa.
- [ ] CA3 El botón "Salir" de `base.html` manda el campo `csrf` y funciona desde cualquier página logueada.
- [ ] CA4 Pruebas nuevas en `tests/test_auth.py` para CA1 y CA2; `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Cambiar el mecanismo de sesión o el formato del token.

## Bitácora del ejecutor

## Dictamen del auditor
