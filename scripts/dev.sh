#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
MANIFEST="${OPENSDL_MANIFEST:-examples/simulated-color-mixing/opensdl.yaml}"
uv run --locked opensdl doctor --manifest "$MANIFEST"
exec uv run --locked opensdl serve-api --manifest "$MANIFEST" --host "${OPENSDL_HOST:-127.0.0.1}" --port "${OPENSDL_PORT:-8000}"
