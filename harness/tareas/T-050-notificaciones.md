---
id: T-050
titulo: Notificaciones
estado: lista
rama: codex/T-050-notificaciones
creada: 2026-11-27
depende: T-049
pr:
---

## Objetivo
Cada usuario ve en el encabezado cuántas notificaciones sin leer tiene y una página con la lista. Por ahora llegan por
tres eventos: un parte de obra confirmado, una aprobación de agente que espera y un contenido de redes marcado "listo".

## Contexto mínimo
- Plan: entidades transversales (`notificaciones`) y M5 ("notificaciones").
- Eventos: `app/services/partes.py` → `confirmar`; `app/agentes/aprobaciones.py` (cuando una corrida queda `esperando_aprobacion`);
  `app/services/redes/contenidos.py` (T-045, marcar `listo`). Equipo de un proyecto: `proyecto_miembros`; admins: `usuarios.rol_empresa='admin'`.
- Encabezado: `app/templates/base.html`. Auditoría: `app/services/auditoria.registrar` (leer una notificación no se audita).

## Alcance
- Tocar: `app/db/migraciones/0018_notificaciones.sql` (o el número libre siguiente; nueva), `app/services/notificaciones.py` (nuevo),
  `app/routers/notificaciones.py` (nuevo), `app/main.py`, `app/templates/base.html`, `app/templates/notificaciones.html` (nueva),
  `app/services/partes.py`, `app/agentes/aprobaciones.py` y `app/services/redes/contenidos.py` (solo la llamada a `notificar`), `tests/test_notificaciones.py` (nuevo).
- No tocar: `app/permisos.py`, migraciones existentes, la lógica de los servicios que emiten (solo agregar la llamada dentro de su transacción).

## Diseño pedido
- Tabla `notificaciones`: `id`, `empresa_id`, `usuario_id`, `tipo`, `texto`, `enlace` (ruta interna relativa), `creada_en`, `leida_en`. Índice por `(empresa_id, usuario_id, leida_en)`.
- `notificar(db, empresa_id, usuario_ids, tipo, texto, enlace)` en la misma transacción del evento; nunca notifica al usuario que causó el evento.
- Destinatarios:
  - parte confirmado → miembros del proyecto que pueden ver obra (y admins), enlace a la bitácora;
  - aprobación esperando → el usuario que inició la consulta, enlace a la pantalla del agente;
  - contenido de redes `listo` → miembros del proyecto con escritura, enlace al contenido.
- Encabezado: contador de sin leer (una consulta, `count` acotado a 99+). Página `/notificaciones`: lista paginada (20), marcar una o todas como leídas (POST con CSRF).
- Un usuario solo ve y marca **sus** notificaciones (filtro por `empresa_id` y `usuario_id` de la sesión). El enlace se valida como ruta relativa (empieza con `/`, sin `//`).

## Criterios de aceptación
- [ ] CA1 Confirmar un parte → notificación para un miembro del proyecto y para el admin, no para quien lo confirmó; el contador del encabezado muestra 1.
- [ ] CA2 Una consulta al agente de Obra que queda esperando aprobación → notificación para quien preguntó.
- [ ] CA3 Marcar todas como leídas → contador 0; marcar la notificación de otro usuario por id → 404 y no cambia.
- [ ] CA4 Aislamiento: un usuario de otra empresa no ve ni cuenta notificaciones de la empresa A.
- [ ] `tests/test_permisos.py` sigue pasando y `python -m scripts.checks.fast` no imprime nada.

## Fuera de alcance
- Correo, push o WhatsApp. Preferencias por tipo. Notificaciones en tiempo real (alcanza con recargar).

## Bitácora del ejecutor

## Dictamen del auditor
