#!/usr/bin/env sh
set -eu

project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
env_file="$project_dir/.env"
base_compose="$project_dir/deploy/docker-compose.dev.yml"
provider_compose="$project_dir/deploy/docker-compose.openclaw-provider.yml"
config_file="$project_dir/config/openclaw-idml-dedicated.json"
disable_script="$project_dir/ops/openclaw-provider-disable.sh"

fail_closed() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$status" -ne 0 ]; then
    echo "Provider staging failed; invoking the kill switch" >&2
    "$disable_script" >/dev/null 2>&1 ||
      echo "WARNING: automatic kill switch failed; run $disable_script immediately" >&2
  fi
  exit "$status"
}

trap 'exit 1' HUP INT TERM
trap fail_closed EXIT

if [ -f "$env_file" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$env_file"
  set +a
fi

: "${IDML_OPENCLAW_GATEWAY_TOKEN:?IDML_OPENCLAW_GATEWAY_TOKEN is required}"
: "${IDML_OPENAI_API_KEY:?IDML_OPENAI_API_KEY is required}"
[ ${#IDML_OPENAI_API_KEY} -ge 20 ] || {
  echo "IDML_OPENAI_API_KEY is not usable" >&2
  exit 1
}

python3 - "$config_file" <<'PY'
import json
import sys

config = json.load(open(sys.argv[1], encoding="utf-8"))
agent = config["agents"]["list"][0]
provider = config["models"]["providers"]["openai"]
assert config["agents"]["defaults"]["heartbeat"]["every"] == "0m"
assert agent["heartbeat"]["every"] == "0m"
assert agent["tools"]["allow"] == []
assert agent["tools"]["deny"] == ["*"]
assert provider["agentRuntime"]["id"] == "openclaw"
assert provider["request"] == {"allowPrivateNetwork": False}
assert "apiKey" not in provider
PY

provider() {
  docker compose --env-file "$env_file" \
    -f "$base_compose" -f "$provider_compose" "$@"
}

base() {
  docker compose --env-file "$env_file" -f "$base_compose" "$@"
}

provider config --quiet
provider config --format json | python3 -c '
import json, sys
data = json.load(sys.stdin)
assert data["services"]["api"]["environment"]["IDML_FEATURE_OPENCLAW"] == "false"
assert data["services"]["api"]["environment"]["IDML_FEATURE_AI_SWARM"] == "false"
assert "OPENAI_API_KEY" not in data["services"]["api"]["environment"]
assert "OPENAI_API_KEY" not in data["services"]["worker"]["environment"]
assert data["services"]["openclaw-idml"]["environment"]["NODE_USE_ENV_PROXY"] == "1"
assert data["services"]["openclaw-idml"]["environment"]["HTTPS_PROXY"] == "http://openclaw-egress-proxy:3128"
'

provider build openclaw-egress-proxy
base stop openclaw-idml
base run --rm --no-deps openclaw-config-init
provider up -d openclaw-egress-proxy
provider up -d --no-deps --force-recreate openclaw-idml

openclaw_id=$(provider ps -q openclaw-idml)
proxy_id=$(provider ps -q openclaw-egress-proxy)
[ -n "$openclaw_id" ]
[ -n "$proxy_id" ]

openclaw_health=starting
proxy_health=starting
for attempt in $(seq 1 45); do
  openclaw_health=$(docker inspect "$openclaw_id" --format '{{.State.Health.Status}}')
  proxy_health=$(docker inspect "$proxy_id" --format '{{.State.Health.Status}}')
  [ "$openclaw_health" = healthy ] && [ "$proxy_health" = healthy ] && break
  sleep 2
done
[ "$openclaw_health" = healthy ]
[ "$proxy_health" = healthy ]

docker inspect "$openclaw_id" --format '{{range .Config.Env}}{{println .}}{{end}}' |
  awk -F= '$1=="OPENAI_API_KEY" {found=length(substr($0,index($0,"=")+1))>=20} END{exit found?0:1}'
docker inspect "$openclaw_id" --format '{{json .NetworkSettings.Networks}}' |
  python3 -c 'import json,sys; assert set(json.load(sys.stdin)) == {"idml_development_openclaw", "idml_development_openclaw_provider"}'
docker inspect "$proxy_id" --format '{{json .NetworkSettings.Networks}}' |
  python3 -c 'import json,sys; assert set(json.load(sys.stdin)) == {"idml_development_openclaw_provider", "idml_development_openclaw_egress"}'
[ "$(docker inspect "$openclaw_id" --format '{{json .HostConfig.PortBindings}}')" = '{}' ]
[ "$(docker inspect "$proxy_id" --format '{{json .HostConfig.PortBindings}}')" = '{}' ]

allowed_connect=$(docker exec "$proxy_id" sh -c \
  "printf 'CONNECT api.openai.com:443 HTTP/1.1\r\nHost: api.openai.com:443\r\n\r\n' | nc -w 5 127.0.0.1 3128" || true)
printf '%s' "$allowed_connect" | grep -q ' 200 '

denied_connect=$(docker exec "$proxy_id" sh -c \
  "printf 'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n' | nc -w 5 127.0.0.1 3128" || true)
printf '%s' "$denied_connect" | grep -q ' 403 '

provider exec -T openclaw-idml node - <<'JS'
const net = require('net');
const socket = net.connect({host: 'api.openai.com', port: 443});
let done = false;
const finish = (blocked) => {
  if (done) return;
  done = true;
  socket.destroy();
  process.exit(blocked ? 0 : 1);
};
socket.setTimeout(3000, () => finish(true));
socket.on('error', () => finish(true));
socket.on('connect', () => finish(false));
JS

session_count=$(provider exec -T openclaw-idml node - <<'JS'
const fs = require('fs');
const path = '/home/node/.openclaw/agents/idml-evaluator/sessions/sessions.json';
if (!fs.existsSync(path)) console.log(0);
else {
  const value = JSON.parse(fs.readFileSync(path, 'utf8'));
  console.log(Array.isArray(value) ? value.length : Object.keys(value).length);
}
JS
)
if [ "${1:-}" != "--web-pilot" ]; then
  [ "$session_count" = 0 ]
fi

provider exec -T openclaw-idml openclaw models list --json |
  python3 -c '
import json, sys

data = json.load(sys.stdin)
models = data.get("models", data if isinstance(data, list) else [])
selected = next(
    (model for model in models if model.get("key") == "openai/gpt-5.4-mini"),
    None,
)
assert selected is not None, "configured OpenAI model is missing"
modalities = selected.get("input")
if isinstance(modalities, str):
    modalities = [part.strip() for part in modalities.replace("+", ",").split(",")]
assert {"text", "image"}.issubset(set(modalities or [])), (
    "configured OpenAI model is not image-capable"
)
'

trap - EXIT HUP INT TERM
printf '%s\n' 'OpenAI provider staged; application agent flags remain disabled'
