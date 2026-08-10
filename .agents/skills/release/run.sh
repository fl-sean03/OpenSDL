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
# `uv build` leaves setuptools' `<member>/build/lib/` behind: gitignored, importable, and stale the
# moment the source moves on. Remove it here, where it is created, so the next recursive search of
# the worktree has one answer per symbol. `scripts/validate-repository.py` fails if any survives.
find . -path ./.venv -prune -o -path '*/node_modules' -prune -o -type d -name build -exec rm -rf {} +
echo "distribution candidates are in dist/. Nothing has been published, signed, or tagged."
echo "See docs/development/releasing.md for what publishing would additionally require."
