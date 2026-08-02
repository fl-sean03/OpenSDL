#!/usr/bin/env bash
set -euo pipefail
NAME="${1:?usage: $0 <name> [destination]}"
DESTINATION="${2:-domain-packs}"
uv run opensdl domain-pack create "$NAME" --destination "$DESTINATION"
