#!/usr/bin/env bash
set -euo pipefail
name=${1:?adapter name required}
capability=${2:?capability id required}
uv run opensdl adapter create "$name" --capability-id "$capability" --destination adapters
