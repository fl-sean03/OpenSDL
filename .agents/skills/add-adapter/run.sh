#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
name=${1:?adapter name required}
capability=${2:?capability id required}
destination=${3:-adapters}
uv run --locked opensdl adapter create "$name" --capability-id "$capability" --destination "$destination"
