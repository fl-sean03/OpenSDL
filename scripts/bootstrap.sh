#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
uv sync --all-packages --group dev
uv run python scripts/generate-schemas.py
uv run opensdl validate examples/simulated-color-mixing/opensdl.yaml --workflow examples/simulated-color-mixing/workflow.yaml
