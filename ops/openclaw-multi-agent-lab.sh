#!/usr/bin/env sh
set -eu

mode=${1:-prepare}
run_id=${2:-multi-agent-first-window}
lab_version=${3:-v1}
project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
env_file="$project_dir/.env"
base_compose="$project_dir/deploy/docker-compose.dev.yml"
benchmark_compose="$project_dir/deploy/docker-compose.openclaw-benchmark.yml"
private_root="$project_dir/benchmarks/private"
input_dir="$private_root/input"
output_dir="$private_root/output"
case "$lab_version" in
  v1)
    plan_name=openclaw-multi-agent-lab-v1.json
    dataset_name=dataset-v1.3.json
    manifest_name=multi-agent-manifest-v1.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V1
    ;;
  v2)
    plan_name=openclaw-multi-agent-lab-v2.json
    dataset_name=dataset-full-v1.3.json
    manifest_name=multi-agent-manifest-v2.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V2
    ;;
  v3)
    plan_name=openclaw-multi-agent-lab-v3.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v3.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V3
    ;;
  v4)
    plan_name=openclaw-multi-agent-lab-v4.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v4.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V4
    ;;
  v5)
    plan_name=openclaw-multi-agent-lab-v5.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v5.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V5
    ;;
  v6)
    plan_name=openclaw-multi-agent-lab-v6.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v6.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V6
    ;;
  v7)
    plan_name=openclaw-multi-agent-lab-v7.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v7.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V7
    ;;
  v8)
    plan_name=openclaw-multi-agent-lab-v8.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v8.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V8
    ;;
  v9)
    plan_name=openclaw-multi-agent-lab-v9.json
    dataset_name=dataset-real-domains-v1.0.json
    manifest_name=multi-agent-manifest-v9.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V9
    ;;
  v10)
    plan_name=openclaw-multi-agent-lab-v10.json
    dataset_name=dataset-real-domains-v1.1.json
    manifest_name=multi-agent-manifest-v10.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V10
    ;;
  v11)
    plan_name=openclaw-multi-agent-lab-v11.json
    dataset_name=dataset-real-domains-visual-v1.1.json
    manifest_name=multi-agent-manifest-v11.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V11
    ;;
  v12)
    plan_name=openclaw-multi-agent-lab-v12.json
    dataset_name=dataset-real-domains-visual-v1.1.json
    manifest_name=multi-agent-manifest-v12.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V12
    ;;
  v13)
    plan_name=openclaw-multi-agent-lab-v13.json
    dataset_name=dataset-real-domains-visual-v1.1.json
    manifest_name=multi-agent-manifest-v13.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V13
    ;;
  v14)
    plan_name=openclaw-multi-agent-lab-v14.json
    dataset_name=dataset-real-domains-visual-v1.1.json
    manifest_name=multi-agent-manifest-v14.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V14
    ;;
  v15)
    plan_name=openclaw-multi-agent-lab-v15.json
    dataset_name=dataset-real-domains-visual-v1.2.json
    manifest_name=multi-agent-manifest-v15.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V15
    ;;
  v16)
    plan_name=openclaw-multi-agent-lab-v16.json
    dataset_name=dataset-real-domains-visual-v1.2.json
    manifest_name=multi-agent-manifest-v16.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V16
    ;;
  v17)
    plan_name=openclaw-multi-agent-lab-v17.json
    dataset_name=dataset-real-domains-visual-v1.2.json
    manifest_name=multi-agent-manifest-v17.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V17
    ;;
  v18)
    plan_name=openclaw-multi-agent-lab-v18.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v18.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V18
    ;;
  v19)
    plan_name=openclaw-multi-agent-lab-v19.json
    dataset_name=dataset-full-v1.4.json
    manifest_name=multi-agent-manifest-v19.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V19
    ;;
  v20|v21|v22|v23|v24|v25|v26|v27|v28|v29|v30|v31|v32|v33)
    plan_name="openclaw-multi-agent-lab-$lab_version.json"
    dataset_name=dataset-e20240135-visual-formulas-v1.0.json
    manifest_name="multi-agent-manifest-$lab_version.json"
    version_number=${lab_version#v}
    expected_confirmation="RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V$version_number"
    ;;
  v34)
    plan_name=openclaw-multi-agent-lab-v34.json
    dataset_name=dataset-e20240135-7c07-v1.0.json
    manifest_name=multi-agent-manifest-v34.json
    expected_confirmation=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V34
    ;;
  *)
    echo "lab-version must be between v1 and v34, excluding unsupported versions" >&2
    exit 2
    ;;
esac
dataset="$input_dir/$dataset_name"
prepared_manifest="$input_dir/$manifest_name"
validated_manifest="$output_dir/validated-$manifest_name"
results="$output_dir/multi-agent-results-$run_id.json"
report="$output_dir/multi-agent-report-$run_id.json"

case "$mode" in
  prepare|execute) ;;
  *)
  echo "usage: $0 [prepare|execute] [run-id] [v1..v33]" >&2
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

runner_args="python -m idml_foundation.ai.multi_agent_lab \
--plan /app/config/$plan_name \
--dataset /benchmark/input/$dataset_name \
--manifest-output /benchmark/output/validated-$manifest_name \
--prepared-manifest /benchmark/input/$manifest_name"

benchmark config --quiet
benchmark build openclaw-benchmark-runner
# runner_args contains only fixed paths controlled by this script.
# shellcheck disable=SC2086
benchmark run --rm --no-deps openclaw-benchmark-runner $runner_args
[ -f "$validated_manifest" ]
[ "$(stat -c %a "$validated_manifest")" = 600 ]

if [ "$mode" = prepare ]; then
  printf '%s\n' 'Multi-agent lab prepared; no provider staging or agent execution occurred'
  exit 0
fi

: "${IDML_CONFIRM_AGENT_EXECUTION:?explicit multi-agent execution confirmation is required}"
[ "$IDML_CONFIRM_AGENT_EXECUTION" = "$expected_confirmation" ] || {
  echo "multi-agent execution confirmation is invalid" >&2
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
      echo "WARNING: multi-agent kill switch or state reset failed" >&2
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
  --results-output "/benchmark/output/multi-agent-results-$run_id.json" \
  --report-output "/benchmark/output/multi-agent-report-$run_id.json" \
  --run-id "$run_id" --execute

IDML_RESET_OPENCLAW_STATE=true "$project_dir/ops/openclaw-provider-disable.sh"
cleanup_armed=false
trap - EXIT HUP INT TERM

[ -f "$results" ]
[ -f "$report" ]
[ "$(stat -c %a "$results")" = 600 ]
[ "$(stat -c %a "$report")" = 600 ]
[ "$(docker ps -a --filter name=idml-development-openclaw-egress-proxy-1 -q | wc -l)" = 0 ]
! docker network inspect idml_development_openclaw_provider >/dev/null 2>&1
! docker network inspect idml_development_openclaw_egress >/dev/null 2>&1

printf '%s\n' "Multi-agent lab completed and disabled; private_result=$results private_report=$report backup=$backup_dir"
