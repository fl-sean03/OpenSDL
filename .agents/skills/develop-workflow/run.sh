#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
cd -- "$REPO_ROOT"
workflow=${1:?workflow path required}
manifest=${2:?manifest path required}
inputs=${3-}
if [[ -z "$inputs" ]]; then
  inputs='{}'
fi
uv run --locked python - "$manifest" "$workflow" <<'PY'
from collections import Counter
from pathlib import Path
import sys

from opensdl_capabilities import validate_reference_adapter_plugins
from opensdl_schemas import load_manifest, validate_workflow_file

manifest = load_manifest(Path(sys.argv[1]))
workflow = validate_workflow_file(Path(sys.argv[2]))
if manifest.spec.environment != "simulation":
    raise SystemExit("develop-workflow only executes a simulation manifest")

allowed_plugins = {"human-task", "local-compute", "simulated-lab"}
adapters = [adapter for adapter in manifest.spec.adapters if adapter.enabled]
bindings = [binding for binding in manifest.spec.capabilities if binding.enabled]

duplicate_adapters = sorted(
    name for name, count in Counter(adapter.name for adapter in adapters).items() if count > 1
)
duplicate_bindings = sorted(
    capability
    for capability, count in Counter(binding.capability for binding in bindings).items()
    if count > 1
)
if duplicate_adapters or duplicate_bindings:
    details = []
    if duplicate_adapters:
        details.append(f"duplicate adapters: {', '.join(duplicate_adapters)}")
    if duplicate_bindings:
        details.append(f"duplicate bindings: {', '.join(duplicate_bindings)}")
    raise SystemExit("develop-workflow refuses ambiguous configuration: " + "; ".join(details))

adapter_by_name = {adapter.name: adapter for adapter in adapters}
binding_by_capability = {binding.capability: binding for binding in bindings}
problems = []
enabled_plugins = set()
for adapter in adapters:
    if adapter.plugin not in allowed_plugins:
        problems.append(
            f"enabled adapter {adapter.name} resolves to plugin {adapter.plugin}; "
            f"allowed plugins are {', '.join(sorted(allowed_plugins))}"
        )
    else:
        enabled_plugins.add(adapter.plugin)
for capability in sorted({step.capability for step in workflow.steps}):
    binding = binding_by_capability.get(capability)
    if binding is None:
        problems.append(f"{capability} has no enabled binding")
        continue
    adapter = adapter_by_name.get(binding.adapter)
    if adapter is None:
        problems.append(f"{capability} uses missing or disabled adapter {binding.adapter}")
if problems:
    raise SystemExit("develop-workflow refuses execution:\n- " + "\n- ".join(problems))
try:
    validate_reference_adapter_plugins(enabled_plugins)
except LookupError as error:
    raise SystemExit(f"develop-workflow refuses plugin provenance: {error}") from None
PY
uv run --locked opensdl validate "$manifest" --workflow "$workflow"
uv run --locked opensdl run "$workflow" --manifest "$manifest" --inputs "$inputs"
