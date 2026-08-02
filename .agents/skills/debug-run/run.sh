#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
run_id=${1:?run id required}
manifest=${2:-opensdl.yaml}
uv run --locked opensdl inspect "$run_id" --manifest "$manifest"
