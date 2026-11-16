#!/usr/bin/env sh
set -eu

project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
if [ -f "$project_dir/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$project_dir/.env"
  set +a
fi
: "${IDML_POSTGRES_USER:?IDML_POSTGRES_USER is required}"
: "${IDML_POSTGRES_DB:?IDML_POSTGRES_DB is required}"
cd "$project_dir"
docker compose --env-file .env -f deploy/docker-compose.dev.yml ps
python_url="http://127.0.0.1:${IDML_API_PORT:-18080}/health/ready"
python3 -c "import json,urllib.request; data=json.load(urllib.request.urlopen('$python_url', timeout=5)); assert data['status']=='ok', data; print(data)"
docker compose --env-file .env -f deploy/docker-compose.dev.yml exec -T openclaw-idml \
  node -e "fetch('http://127.0.0.1:47716/readyz').then(async r=>{if(!r.ok)throw new Error(await r.text());console.log(await r.text())})"
docker compose --env-file .env -f deploy/docker-compose.dev.yml exec -T postgres \
  psql -U "$IDML_POSTGRES_USER" -d "$IDML_POSTGRES_DB" -Atc "select version_num from alembic_version;"
