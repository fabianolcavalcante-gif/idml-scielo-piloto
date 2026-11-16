#!/usr/bin/env sh
set -eu

project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
backup_dir=${1:?backup directory required}
compose_file="$project_dir/deploy/docker-compose.dev.yml"
restore_db="idml_restore_test"
restore_dir=$(mktemp -d /tmp/idml-restore-test.XXXXXX)
restore_db_created=false

cleanup() {
  set +e
  if [ "$restore_db_created" = true ]; then
    docker compose --env-file "$project_dir/.env" -f "$compose_file" exec -T postgres \
      dropdb -U "$IDML_POSTGRES_USER" --if-exists "$restore_db" >/dev/null
  fi
  case "$restore_dir" in
    /tmp/idml-restore-test.*) rm -rf -- "$restore_dir" ;;
    *) echo "refusing to remove unexpected restore path" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

if [ -f "$project_dir/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$project_dir/.env"
  set +a
fi
: "${IDML_POSTGRES_USER:?IDML_POSTGRES_USER is required}"

case "$backup_dir" in
  /opt/idml-platform/backups/*) ;;
  *) echo "backup path is outside the approved directory" >&2; exit 1 ;;
esac

cd "$project_dir"
cd "$backup_dir"
sha256sum -c SHA256SUMS

cd "$project_dir"
docker compose --env-file .env -f "$compose_file" exec -T postgres \
  dropdb -U "$IDML_POSTGRES_USER" --if-exists "$restore_db"
docker compose --env-file .env -f "$compose_file" exec -T postgres \
  createdb -U "$IDML_POSTGRES_USER" "$restore_db"
restore_db_created=true
docker compose --env-file .env -f "$compose_file" exec -T postgres \
  pg_restore -U "$IDML_POSTGRES_USER" -d "$restore_db" --no-owner --no-privileges \
  < "$backup_dir/database.dump"
table_count=$(docker compose --env-file .env -f "$compose_file" exec -T postgres \
  psql -U "$IDML_POSTGRES_USER" -d "$restore_db" -Atc \
  "select count(*) from information_schema.tables where table_schema='public';")
test "$table_count" -ge 10

docker run --rm --read-only \
  -v "$backup_dir:/backup:ro" \
  -v "$restore_dir:/restore" \
  alpine:3.21 sh -c 'mkdir -p /restore/artifacts && cd /restore/artifacts && tar -xzf /backup/artifacts.tar.gz'
artifact_count=$(find "$restore_dir/artifacts" -type f | wc -l)
test "$artifact_count" -ge 1

docker run --rm --read-only \
  -v "$backup_dir:/backup:ro" \
  -v "$restore_dir:/restore" \
  alpine:3.21 sh -c 'mkdir -p /restore/openclaw && cd /restore/openclaw && tar -xzf /backup/openclaw-state.tar.gz'
test -f "$restore_dir/openclaw/openclaw.json"
test -f "$restore_dir/openclaw/state/openclaw.sqlite"
python3 - "$restore_dir/openclaw/state/openclaw.sqlite" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    result = connection.execute("PRAGMA integrity_check").fetchone()
    assert result == ("ok",), result
finally:
    connection.close()
PY
openclaw_file_count=$(find "$restore_dir/openclaw" -type f | wc -l)
test "$openclaw_file_count" -ge 1

printf 'restore test passed with %s public tables, %s artifact files and %s OpenClaw state files\n' \
  "$table_count" "$artifact_count" "$openclaw_file_count"
