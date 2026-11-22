---
id: T-001
titulo: Logout con CSRF
estado: hecha
rama: codex/T-001-logout-con-csrf
creada: 2026-11-21
pr: "#1"
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
- [x] CA1 `POST /logout` con sesión y token válido → 303 a `/login` y la cookie de sesión se borra.
- [x] CA2 `POST /logout` con sesión y **sin** token (o token inválido) → 403 y la sesión sigue activa.
- [x] CA3 El botón "Salir" de `base.html` manda el campo `csrf` y funciona desde cualquier página logueada.
- [x] CA4 Pruebas nuevas en `tests/test_auth.py` para CA1 y CA2; `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Cambiar el mecanismo de sesión o el formato del token.

## Bitácora del ejecutor
- Los cuatro casos fallaron antes del cambio. Se probó el formulario de Inicio y Mi cuenta, el borrado de la cookie y la conservación de la sesión ante ambos rechazos.
- Se reutilizó check_csrf en la firma de logout. La excepción del sensor queda para el auditor.
- El sensor rápido terminó sin salida y pasaron las 32 pruebas con PostgreSQL temporal, incluidas las de permisos.

## Dictamen del auditor
DICTAMEN: APROBAR (Claude, 2026-11-21). Bloqueantes: ninguno. Alcance respetado (3 archivos), CA con pruebas que
fallaban antes, reusa `check_csrf`, CI verde. Excepción `auth.py:logout` retirada de `post_sin_csrf.txt`. Merge: Leo (#1).
