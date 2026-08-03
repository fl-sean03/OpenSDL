#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
version=${1:?version required}
if [[ -n "$(git status --porcelain)" ]]; then
  echo "release preparation requires a clean worktree" >&2
  exit 1
fi
if [[ -L dist ]] || [[ -e dist && ! -d dist ]]; then
  echo "release preparation requires dist/ to be a real directory" >&2
  exit 1
fi
if [[ -d dist ]] && [[ -n "$(find dist -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "release preparation requires dist/ to be absent or empty" >&2
  exit 1
fi
uv run --locked python scripts/release.py "$version"
uv lock
make test lint example
uv build --all-packages --out-dir dist
