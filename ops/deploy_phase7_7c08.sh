#!/usr/bin/env sh
# Fixed, scoped deployment of an already qualified source archive.
set -eu
project=/opt/idml-platform
stage=$project/releases/phase7-7c08-v1
cd "$project"
compose() {
  docker compose --env-file "$project/.env" -f "$project/deploy/docker-compose.dev.yml" "$@"
}
healthy() {
  for attempt in $(seq 1 90); do
    api=$(docker inspect idml-development-api-1 --format '{{.State.Health.Status}}')
    worker=$(docker inspect idml-development-worker-1 --format '{{.State.Health.Status}}')
    if [ "$api" = healthy ] && [ "$worker" = healthy ]; then
      curl --fail --silent http://127.0.0.1:18080/health/ready >/dev/null
      return 0
    fi
    sleep 2
  done
  return 1
}
case "${1:?prepare, build, qualify or activate required}" in
  prepare)
    test ! -e "$stage/backup-path.txt"
    python3 "$stage/ops/phase7_7c08_vps.py" before
    # Do not let the legacy restore helper replace an existing database.
    count=$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from pg_database where datname='"'"'idml_restore_test'"'"';"')
    test "$count" = 0
    umask 077
    backup=$(sh ops/backup.sh)
    printf '%s\n' "$backup" > "$stage/backup-path.txt"
    sh ops/restore-test.sh "$backup" > "$stage/restore-test.log" 2>&1
    tar -czf "$stage/rollback-source.tar.gz" src config profiles schemas prompts ops deploy tests docs openclaw migrations benchmarks/agents benchmarks/qualification corpus pyproject.toml requirements.lock requirements-dev.lock alembic.ini README.md
    cp .env "$stage/rollback.env"
    printf 'backup and restore verified\n'
    ;;
  build)
    test -s "$stage/restore-test.log"
    docker build --memory=768m --cpu-period=100000 --cpu-quota=50000 -t idml-foundation:phase7-7c08-v1 -f "$stage/deploy/Dockerfile" "$stage"
    ;;
  qualify)
    docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
      --memory=512m --cpus=0.5 --pids-limit=100 --tmpfs /tmp:rw,nosuid,nodev,size=128m \
      -v "$stage:/qualification:ro" -w /qualification \
      idml-foundation:phase7-7c08-v1 python ops/gate_phase7_7c08.py > "$stage/container-gates.json"
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["approved"]; print("18 isolated gates approved")' "$stage/container-gates.json"
    ;;
  activate)
    python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["approved"]' "$stage/container-gates.json"
    previous=$(docker inspect idml-development-api-1 --format '{{.Config.Image}}')
    test "$previous" = idml-foundation:phase7-v11-robustness-v1
    # Runtime and source rollback are retained; migrations are unchanged in this release.
    tar -xzf "$stage/source.tar.gz" -C "$project"
    restore_previous() {
      IDML_IMAGE_TAG=phase7-v11-robustness-v1 compose up -d --no-deps api worker
    }
    recover() {
      restore_previous
      tar -xzf "$stage/rollback-source.tar.gz" -C "$project"
      cp "$stage/rollback.env" "$project/.env"
      chmod 600 "$project/.env"
    }
    trap 'recover' EXIT INT TERM
    IDML_IMAGE_TAG=phase7-7c08-v1 compose up -d --no-deps api worker
    healthy
    # Exercise rollback before accepting the new image, then reapply it.
    restore_previous
    healthy
    test "$(docker inspect idml-development-api-1 --format '{{.Config.Image}}')" = "$previous"
    test "$(docker inspect idml-development-worker-1 --format '{{.Config.Image}}')" = "$previous"
    printf 'previous image rollback healthy\n' > "$stage/rollback-test.log"
    IDML_IMAGE_TAG=phase7-7c08-v1 compose up -d --no-deps api worker
    healthy
    python3 "$stage/ops/phase7_7c08_vps.py" after
    python3 "$stage/ops/phase7_7c08_vps.py" set-tag
    trap - EXIT INT TERM
    printf 'candidate healthy; rollback tested; persistent tag synchronized\n'
    ;;
  *) exit 2 ;;
esac
