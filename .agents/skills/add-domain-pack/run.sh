#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
NAME="${1:?usage: $0 <name> [destination]}"
DESTINATION="${2:-domain-packs}"
uv run --locked opensdl domain-pack create "$NAME" --destination "$DESTINATION"
