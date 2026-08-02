#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --locked ruff check .
uv run --locked pyright
uv run --locked python scripts/check-boundaries.py
uv run --locked python scripts/generate-schemas.py --check
uv run --locked python scripts/validate-repository.py
