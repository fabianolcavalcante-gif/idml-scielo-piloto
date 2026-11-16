#!/usr/bin/env sh
set -eu

mode=${1:-prepare}
run_id=${2:-controlled-first-window}
project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
env_file="$project_dir/.env"
base_compose="$project_dir/deploy/docker-compose.dev.yml"
benchmark_compose="$project_dir/deploy/docker-compose.openclaw-benchmark.yml"
private_root="$project_dir/benchmarks/private"
input_dir="$private_root/input"
output_dir="$private_root/output"
dataset="$input_dir/dataset-v1.3.json"
prepared_manifest="$input_dir/prepared-manifest-v1.json"
validated_manifest="$output_dir/validated-manifest-v1.json"
results="$output_dir/results-$run_id.json"

case "$mode" in
  prepare|execute) ;;
  *)
    echo "usage: $0 [prepare|execute] [run-id]" >&2
    exit 2
    ;;
esac
case "$run_id" in
  ""|*[!a-z0-9-]*)
    echo "run-id must contain only lowercase letters, digits and hyphens" >&2
    exit 2
    ;;
esac
[ ${#run_id} -ge 8 ] && [ ${#run_id} -le 80 ] || {
  echo "run-id length must be between 8 and 80 characters" >&2
  exit 2
}

if [ -f "$env_file" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$env_file"
  set +a
fi

: "${IDML_OPENCLAW_GATEWAY_TOKEN:?IDML_OPENCLAW_GATEWAY_TOKEN is required}"
[ -f "$dataset" ]
[ ! -L "$dataset" ]
[ -f "$prepared_manifest" ]
[ ! -L "$prepared_manifest" ]
install -d -m 0700 -o 10001 -g 10001 "$input_dir" "$output_dir"
chown 10001:10001 "$dataset" "$prepared_manifest"
chmod 0600 "$dataset" "$prepared_manifest"

benchmark() {
  docker compose --profile benchmark --env-file "$env_file" \
    -f "$base_compose" -f "$benchmark_compose" "$@"
}

base() {
  docker compose --env-file "$env_file" -f "$base_compose" "$@"
}

runner_args="python -m idml_foundation.ai.benchmark \
--plan /app/config/openclaw-controlled-benchmark-v1.json \
--dataset /benchmark/input/dataset-v1.3.json \
--manifest-output /benchmark/output/validated-manifest-v1.json \
--prepared-manifest /benchmark/input/prepared-manifest-v1.json"

benchmark config --quiet
benchmark build openclaw-benchmark-runner
# runner_args contains only fixed paths controlled by this script.
# shellcheck disable=SC2086
benchmark run --rm --no-deps openclaw-benchmark-runner $runner_args
[ -f "$validated_manifest" ]
[ "$(stat -c %a "$validated_manifest")" = 600 ]

if [ "$mode" = prepare ]; then
  printf '%s\n' 'Controlled benchmark prepared; no provider staging or agent execution occurred'
  exit 0
fi

: "${IDML_CONFIRM_AGENT_EXECUTION:?explicit benchmark execution confirmation is required}"
[ "$IDML_CONFIRM_AGENT_EXECUTION" = RUN_IDML_OPENCLAW_BENCHMARK_V1 ] || {
  echo "controlled benchmark execution confirmation is invalid" >&2
  exit 1
}

run_count=$(base exec -T api python -c '
from sqlalchemy import create_engine,text
import os
c=create_engine(os.environ["IDML_DATABASE_URL"]).connect()
print(c.scalar(text("select count(*) from agent_runs")))
')
proposal_count=$(base exec -T api python -c '
from sqlalchemy import create_engine,text
import os
c=create_engine(os.environ["IDML_DATABASE_URL"]).connect()
print(c.scalar(text("select count(*) from agent_proposals")))
')
[ "$run_count" = 0 ]
[ "$proposal_count" = 0 ]

backup_dir=$("$project_dir/ops/backup.sh")
"$project_dir/ops/restore-test.sh" "$backup_dir"

cleanup_armed=true
cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$cleanup_armed" = true ]; then
    if ! IDML_RESET_OPENCLAW_STATE=true "$project_dir/ops/openclaw-provider-disable.sh"; then
      echo "WARNING: benchmark kill switch or state reset failed" >&2
      status=1
    fi
  fi
  exit "$status"
}
trap 'exit 1' HUP INT TERM
trap cleanup EXIT

"$project_dir/ops/openclaw-provider-stage.sh"
# runner_args and run_id contain no credentials; run_id is validated again by Python.
# shellcheck disable=SC2086
benchmark run --rm --no-deps openclaw-benchmark-runner $runner_args \
  --results-output "/benchmark/output/results-$run_id.json" \
  --run-id "$run_id" --execute

IDML_RESET_OPENCLAW_STATE=true "$project_dir/ops/openclaw-provider-disable.sh"
cleanup_armed=false
trap - EXIT HUP INT TERM

[ -f "$results" ]
[ "$(stat -c %a "$results")" = 600 ]
[ "$(docker ps -a --filter name=idml-development-openclaw-egress-proxy-1 -q | wc -l)" = 0 ]
! docker network inspect idml_development_openclaw_provider >/dev/null 2>&1
! docker network inspect idml_development_openclaw_egress >/dev/null 2>&1

printf '%s\n' "Controlled benchmark completed and disabled; private_result=$results backup=$backup_dir"
