#!/usr/bin/env bash
# Levanta o actualiza el gestor en el VPS.
#   ./scripts/deploy.sh            construye y levanta (con Caddy si el Caddyfile ya tiene dominio)
#   ./scripts/deploy.sh --logs     además muestra los logs
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[ -f .env ] || { echo "Falta .env (copiá .env.example y completá SECRET_KEY y POSTGRES_PASSWORD)."; exit 1; }
grep -q '^SECRET_KEY=cambiame' .env && { echo "Cambiá SECRET_KEY en .env."; exit 1; }

mkdir -p data/postgres data/archivos data/correos data/backups
# La app corre como uid 10001 con el sistema de archivos de solo lectura: estas carpetas son su lugar de escritura.
chown -R 10001:10001 data/archivos data/correos 2>/dev/null || true

PERFIL=""
if ! grep -q "proyectos.tudominio.com" Caddyfile; then PERFIL="--profile dominio"; fi

echo "==> Construyendo"
docker compose build
echo "==> Levantando"
docker compose $PERFIL up -d

echo "==> Esperando a que la app responda"
for i in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:${APP_PORT:-8000}/salud" >/dev/null 2>&1; then echo "    responde"; break; fi
    [ "$i" = 40 ] && { echo "    no respondió; revisá: docker compose logs app"; exit 1; }
    sleep 2
done
docker stats --no-stream --format '    {{.Name}}: {{.MemUsage}}'

cat <<'TXT'

Si es la primera vez:
  docker compose exec app python -m scripts.crear_empresa "Nombre" slug admin@email "Tu Nombre"
y programá el backup diario:
  crontab -e   ->   30 3 * * * /opt/gestor/scripts/backup.sh >> /var/log/gestor-backup.log 2>&1
TXT
[ "${1:-}" = "--logs" ] && docker compose logs -f
