#!/usr/bin/env sh
set -eu
project_dir=${IDML_PROJECT_DIR:-/opt/idml-platform}
# Uses the API's existing environment without printing credentials or copying code into it.
exec docker exec -i idml-development-api-1 python - \
  --max-entries 10000 --max-records 10000 --timeout 15 \
  < "$project_dir/ops/audit_storage.py"
