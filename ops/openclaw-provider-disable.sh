#!/usr/bin/env sh
set -eu

project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
env_file="$project_dir/.env"
base_compose="$project_dir/deploy/docker-compose.dev.yml"

if [ -f "$env_file" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$env_file"
  set +a
fi

: "${IDML_OPENCLAW_GATEWAY_TOKEN:?IDML_OPENCLAW_GATEWAY_TOKEN is required}"
reset_state=${IDML_RESET_OPENCLAW_STATE:-false}
case "$reset_state" in
  true|false) ;;
  *)
    echo "IDML_RESET_OPENCLAW_STATE must be true or false" >&2
    exit 1
    ;;
esac

base() {
  docker compose --env-file "$env_file" -f "$base_compose" "$@"
}

recovery_armed=false
recover_gateway_on_failure() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$status" -ne 0 ] && [ "$recovery_armed" = true ]; then
    echo "Provider disable failed during state reset; recovering the base gateway" >&2
    base run --rm --no-deps openclaw-config-init >/dev/null 2>&1 || true
    base up -d --no-deps openclaw-idml >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap 'exit 1' HUP INT TERM
trap recover_gateway_on_failure EXIT

docker rm -f idml-development-openclaw-egress-proxy-1 >/dev/null 2>&1 || true

if [ "$reset_state" = true ]; then
  recovery_armed=true
  base stop openclaw-idml
  base rm -f openclaw-idml
  for init_id in $(base ps -a -q openclaw-config-init); do
    docker inspect "$init_id" --format '{{json .Config.Labels}}' |
      python3 -c '
import json,sys
labels=json.load(sys.stdin)
assert labels["com.docker.compose.project"] == "idml-development"
assert labels["com.docker.compose.service"] == "openclaw-config-init"
'
    docker rm -f "$init_id" >/dev/null
  done
  volume=idml_development_openclaw_state
  docker volume inspect "$volume" --format '{{json .Labels}}' |
    python3 -c '
import json,sys
labels=json.load(sys.stdin)
assert labels["com.docker.compose.project"] == "idml-development"
assert labels["com.docker.compose.volume"] == "idml_openclaw_state"
'
  docker volume rm "$volume" >/dev/null
  base run --rm --no-deps openclaw-config-init
  base up -d --no-deps openclaw-idml
else
  base up -d --no-deps --force-recreate openclaw-idml
fi

openclaw_id=$(base ps -q openclaw-idml)
[ -n "$openclaw_id" ]
openclaw_health=starting
for attempt in $(seq 1 45); do
  openclaw_health=$(docker inspect "$openclaw_id" --format '{{.State.Health.Status}}')
  [ "$openclaw_health" = healthy ] && break
  sleep 2
done
[ "$openclaw_health" = healthy ]

if docker inspect "$openclaw_id" --format '{{range .Config.Env}}{{println .}}{{end}}' |
  sed 's/=.*//' | grep -q '^OPENAI_API_KEY$'; then
  echo "OPENAI_API_KEY remained in the disabled gateway" >&2
  exit 1
fi
docker inspect "$openclaw_id" --format '{{json .NetworkSettings.Networks}}' |
  python3 -c 'import json,sys; assert set(json.load(sys.stdin)) == {"idml_development_openclaw"}'

session_count=$(base exec -T openclaw-idml node - <<'JS'
const fs = require('fs');
const path = '/home/node/.openclaw/agents/idml-evaluator/sessions/sessions.json';
if (!fs.existsSync(path)) console.log(0);
else {
  const value = JSON.parse(fs.readFileSync(path, 'utf8'));
  console.log(Array.isArray(value) ? value.length : Object.keys(value).length);
}
JS
)
[ "$session_count" = 0 ]

docker network rm idml_development_openclaw_provider >/dev/null 2>&1 || true
docker network rm idml_development_openclaw_egress >/dev/null 2>&1 || true
! docker network inspect idml_development_openclaw_provider >/dev/null 2>&1
! docker network inspect idml_development_openclaw_egress >/dev/null 2>&1

recovery_armed=false
trap - EXIT HUP INT TERM
printf '%s\n' "OpenAI provider disabled; credential and provider network detached; state_reset=$reset_state"
