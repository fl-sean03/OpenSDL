#!/usr/bin/env bash
set -euo pipefail
version=${1:?version required}
uv run python scripts/release.py "$version"
make test lint example
