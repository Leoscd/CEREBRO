#!/usr/bin/env bash
# Prueba mensual: restaura el último dump en un Postgres temporal y cuenta filas clave.
# Un backup que nunca se probó restaurar no es un backup.
# Cron: 0 5 1 * * /opt/gestor/scripts/probar_restauracion.sh >> /var/log/gestor-backup.log 2>&1
set -euo pipefail
PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ULTIMO="$(ls -1t "$PROYECTO"/data/backups/gsp-*.dump | head -1)"
NOMBRE="gsp-restore-test-$$"

docker run -d --rm --name "$NOMBRE" -e POSTGRES_PASSWORD=prueba pgvector/pgvector:pg16 >/dev/null
trap 'docker stop "$NOMBRE" >/dev/null 2>&1 || true' EXIT
for i in $(seq 1 30); do docker exec "$NOMBRE" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done

docker exec -i "$NOMBRE" createdb -U postgres gsp
docker exec -i "$NOMBRE" pg_restore -U postgres -d gsp --no-owner < "$ULTIMO"
CUENTAS="$(docker exec "$NOMBRE" psql -U postgres -d gsp -tAc \
  "SELECT 'empresas='||count(*) FROM empresas UNION ALL SELECT 'usuarios='||count(*) FROM usuarios
   UNION ALL SELECT 'proyectos='||count(*) FROM proyectos UNION ALL SELECT 'auditoria='||count(*) FROM auditoria" | tr '\n' ' ')"
echo "$(date '+%F %T') restauración OK de $(basename "$ULTIMO"): $CUENTAS"
