#!/usr/bin/env bash
set -euo pipefail
path=${1:?destination required}
name=${2:-$(basename "$path")}
owner=${3:-your-organization}
uv run opensdl init "$path" --name "$name" --owner "$owner"
