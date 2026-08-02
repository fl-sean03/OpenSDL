#!/usr/bin/env bash
set -euo pipefail
run_id=${1:?run id required}
manifest=${2:-opensdl.yaml}
uv run opensdl inspect "$run_id" --manifest "$manifest"
