#!/usr/bin/env bash
set -euo pipefail

repositorio="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base_tmp="$(cd "${TMPDIR:-/tmp}" && pwd -P)"
aislado="$(mktemp -d "$base_tmp/gsp-compose.XXXXXXXX")"
proyecto="gsp-humo-$$-$RANDOM"
paso="preparación del proyecto temporal"
compose=(env -u COMPOSE_PROJECT_NAME -u COMPOSE_PROFILES -u POSTGRES_PASSWORD -u APP_PORT docker compose
    --project-name "$proyecto" --project-directory "$aislado" --env-file "$aislado/.env"
    -f "$aislado/docker-compose.yml" -f "$aislado/compose.humo.yml")

terminar() {
    local salida=$?
    if (( salida != 0 )); then
        printf 'Falló la prueba de humo de Compose durante %s.\n' "$paso" >&2
        "${compose[@]}" logs --tail 80 postgres app worker >&2 || true
    fi
    if "${compose[@]}" down -v --remove-orphans; then
        case "$aislado" in
            "$base_tmp"/gsp-compose.*) rm -rf -- "$aislado" ;;
        esac
    else
        printf 'No se pudo desmontar el proyecto temporal %s en %s.\n' "$proyecto" "$aislado" >&2
        if (( salida == 0 )); then salida=1; fi
    fi
    exit "$salida"
}
trap terminar EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cp -R "$repositorio/app" "$repositorio/scripts" "$aislado/"
cp "$repositorio/docker-compose.yml" "$repositorio/Dockerfile" "$repositorio/requirements.txt" "$aislado/"
if [[ ! -f "$aislado/.env" ]]; then
    cp "$repositorio/.env.ci" "$aislado/.env"
fi

# El volumen de prueba de Postgres se elimina con down -v. App y worker usan
# los mismos bind mounts que en producción, dentro del directorio temporal.
cat > "$aislado/compose.humo.yml" <<'YAML'
services:
  postgres:
    volumes:
      - postgres_humo:/var/lib/postgresql/data
volumes:
  postgres_humo:
YAML
mkdir -p "$aislado/data/archivos" "$aislado/data/correos"
chmod 777 "$aislado/data/archivos" "$aislado/data/correos"

paso="la construcción de la imagen"
"${compose[@]}" build
paso="el arranque, las migraciones iniciales y la espera de /salud (120 s)"
timeout 120s "${compose[@]}" up -d --wait --wait-timeout 115
"${compose[@]}" exec -T app python -c \
    'import urllib.request; assert urllib.request.urlopen("http://127.0.0.1:8000/salud", timeout=5).read() == b"ok"'

paso="la comprobación de las migraciones"
"${compose[@]}" exec -T app python -m app.db.migrar

paso="el alta de la empresa de prueba y el encolado del análisis"
trabajo="$("${compose[@]}" exec -T app python - <<'PY'
import os
from io import BytesIO

import psycopg
from psycopg.rows import dict_row
from pypdf import PdfWriter

from app import config
from app.db.migrar import CARPETA
from app.services import almacen, jobs
from app.services.empresa import crear_empresa
from app.services.proyectos import crear_proyecto

with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as db:
    esperadas = {archivo.name for archivo in CARPETA.glob("*.sql")}
    aplicadas = {fila["nombre"] for fila in db.execute("SELECT nombre FROM schema_migrations")}
    assert esperadas and aplicadas == esperadas, f"Migraciones pendientes: {esperadas - aplicadas}"
    empresa, admin = crear_empresa(
        db, nombre="Estudio Humo", slug="humo", admin_email="admin@humo.test",
        admin_nombre="Admin Humo", admin_password="solo-para-humo",
    )
    tipo = db.execute("SELECT id FROM tipos_proyecto WHERE empresa_id = %s ORDER BY id LIMIT 1",
                      (empresa["id"],)).fetchone()
    proyecto = crear_proyecto(db, admin, tipo_proyecto_id=tipo["id"], nombre="Obra de prueba")
    carpeta = db.execute(
        "SELECT id FROM carpetas WHERE empresa_id = %s AND proyecto_id = %s ORDER BY id LIMIT 1",
        (empresa["id"], proyecto["id"]),
    ).fetchone()
    # El runner debe poder retirar el directorio de prueba creado por el UID del contenedor.
    os.umask(0)
    contenido = BytesIO()
    pdf = PdfWriter()
    pdf.add_blank_page(width=200, height=200)
    pdf.write(contenido)
    contenido.seek(0)
    sha, tamano = almacen.guardar(contenido)
    archivo = db.execute(
        """INSERT INTO archivos (empresa_id, proyecto_id, carpeta_id, nombre, extension, mime, creado_por)
           VALUES (%s, %s, %s, 'prueba.pdf', 'pdf', 'application/pdf', %s) RETURNING id""",
        (empresa["id"], proyecto["id"], carpeta["id"], admin["id"]),
    ).fetchone()
    version = db.execute(
        """INSERT INTO versiones_archivo (empresa_id, archivo_id, numero, sha256, tamano_bytes, mime, origen, subida_por)
           VALUES (%s, %s, 1, %s, %s, 'application/pdf', 'subida', %s) RETURNING id""",
        (empresa["id"], archivo["id"], sha, tamano, admin["id"]),
    ).fetchone()
    db.execute("UPDATE archivos SET version_actual_id = %s WHERE empresa_id = %s AND id = %s",
               (version["id"], empresa["id"], archivo["id"]))
    trabajo = jobs.encolar(db, empresa["id"], "archivo.analizar", {"version_id": version["id"]})
print(trabajo)
PY
)"
[[ "$trabajo" =~ ^[0-9]+$ ]]

paso="el análisis del PDF por el worker y la lectura del volumen compartido (60 s)"
fin=$((SECONDS + 60))
while (( SECONDS < fin )); do
    restante=$((fin - SECONDS))
    estado="$(timeout "${restante}s" "${compose[@]}" exec -T postgres \
        psql -X -U gsp -d gsp -v ON_ERROR_STOP=1 -Atq -c \
        "SELECT j.estado || '|' || coalesce(v.derivados->'meta'->>'mime_real', '')
           FROM jobs j JOIN versiones_archivo v ON v.empresa_id = j.empresa_id
                           AND v.id = (j.payload->>'version_id')::bigint
          WHERE j.id = $trabajo")"
    case "$estado" in
        'hecho|application/pdf')
            echo 'Compose OK. /salud responde, migraciones completas y PDF analizado por el worker.'
            exit 0
            ;;
        fallido\|*|hecho\|*)
            printf 'El trabajo %s terminó con estado o MIME inesperado: %s\n' "$trabajo" "$estado" >&2
            exit 1
            ;;
    esac
    sleep 2
done
printf 'El worker no completó el trabajo %s antes de 60 segundos.\n' "$trabajo" >&2
exit 1
