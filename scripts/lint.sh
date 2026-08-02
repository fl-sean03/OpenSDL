#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check .
uv run pyright
uv run python scripts/check-boundaries.py
uv run python scripts/generate-schemas.py --check
