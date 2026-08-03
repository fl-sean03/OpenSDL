#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
id=${1:?capability id required}
name=${2:?display name required}
destination=${3:-capabilities}
uv run --locked opensdl capability create "$id" --name "$name" --destination "$destination"
