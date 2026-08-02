#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
path=${1:?destination required}
name=${2:-$(basename "$path")}
owner=${3:-your-organization}
uv run --locked opensdl init "$path" --name "$name" --owner "$owner"
