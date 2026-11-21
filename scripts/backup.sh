#!/usr/bin/env bash
# Backup diario: base (pg_dump) + archivos, cifrado y FUERA del VPS con restic.
#
# Requisitos en el VPS (una sola vez):
#   apt install restic
#   en /etc/gestor-backup.env (chmod 600, NO en el repo):
#     RESTIC_REPOSITORY=b2:mi-bucket:gestor        (o sftp:usuario@storagebox:/gestor)
#     RESTIC_PASSWORD=...                           (guardala también fuera del VPS)
#     B2_ACCOUNT_ID=... / B2_ACCOUNT_KEY=...        (según el destino)
#   restic init
# Cron: 30 3 * * * /opt/gestor/scripts/backup.sh >> /var/log/gestor-backup.log 2>&1
set -euo pipefail
PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROYECTO"
set -a; . /etc/gestor-backup.env; set +a

DUMPS="$PROYECTO/data/backups"
mkdir -p "$DUMPS"
DUMP="$DUMPS/gsp-$(date +%F-%H%M).dump"

# Formato custom: se restaura con pg_restore y permite restaurar tablas sueltas.
docker compose exec -T postgres pg_dump -U gsp -d gsp -Fc > "$DUMP"
[ -s "$DUMP" ] || { echo "$(date '+%F %T') ERROR: dump vacío"; exit 1; }

restic backup --tag gestor "$DUMP" "$PROYECTO/data/archivos" --exclude-caches
restic forget --tag gestor --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune

# Localmente solo quedan los dumps de la última semana (el resto vive en restic).
find "$DUMPS" -name 'gsp-*.dump' -mtime +7 -delete
echo "$(date '+%F %T') backup OK: $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"
