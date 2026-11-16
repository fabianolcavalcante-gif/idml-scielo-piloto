#!/usr/bin/env sh
set -eu

project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
backup_root=${IDML_BACKUP_ROOT:-/opt/idml-platform/backups}
compose_file="$project_dir/deploy/docker-compose.dev.yml"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="$backup_root/$timestamp"
openclaw_paused=false

cleanup() {
  if [ "$openclaw_paused" = true ]; then
    docker compose --env-file "$project_dir/.env" -f "$compose_file" \
      unpause openclaw-idml >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

umask 077
if [ -f "$project_dir/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$project_dir/.env"
  set +a
fi
: "${IDML_POSTGRES_USER:?IDML_POSTGRES_USER is required}"
: "${IDML_POSTGRES_DB:?IDML_POSTGRES_DB is required}"
mkdir -p "$destination"
cd "$project_dir"

docker compose --env-file .env -f "$compose_file" exec -T postgres \
  pg_dump -U "$IDML_POSTGRES_USER" -d "$IDML_POSTGRES_DB" -Fc > "$destination/database.dump"

docker run --rm --read-only \
  -v idml_development_artifacts:/source:ro \
  -v "$destination:/backup" \
  alpine:3.21 sh -c 'cd /source && tar -czf /backup/artifacts.tar.gz .'

docker volume inspect idml_development_openclaw_state >/dev/null
docker compose --env-file .env -f "$compose_file" pause openclaw-idml >/dev/null
openclaw_paused=true
docker run --rm --read-only \
  -v idml_development_openclaw_state:/source:ro \
  -v "$destination:/backup" \
  alpine:3.21 sh -c 'cd /source && tar -czf /backup/openclaw-state.tar.gz .'
docker compose --env-file .env -f "$compose_file" unpause openclaw-idml >/dev/null
openclaw_paused=false
openclaw_container=$(docker compose --env-file .env -f "$compose_file" ps -q openclaw-idml)
openclaw_health=starting
for attempt in $(seq 1 30); do
  openclaw_health=$(docker inspect "$openclaw_container" --format '{{.State.Health.Status}}')
  [ "$openclaw_health" = healthy ] && break
  sleep 1
done
if [ "$openclaw_health" != healthy ]; then
  echo "OpenClaw did not return to healthy after backup" >&2
  exit 1
fi

sha256sum \
  "$destination/database.dump" \
  "$destination/artifacts.tar.gz" \
  "$destination/openclaw-state.tar.gz" \
  > "$destination/SHA256SUMS"
chmod 600 "$destination"/*
printf '%s\n' "$destination"
