#!/usr/bin/env bash
set -euo pipefail
id=${1:?capability id required}
name=${2:?display name required}
uv run opensdl capability create "$id" --name "$name" --destination capabilities
