---
name: develop-workflow
description: Design, change, validate, and test an OpenSDL workflow through a simulation manifest. Use when building or iterating on a laboratory workflow without live equipment.
---

# Develop a simulated workflow

## Inputs

- simulation manifest path
- workflow path
- intended inputs, outputs, and failure behavior
- representative JSON inputs

## Procedure

1. Read the manifest, capability contracts, and a nearby tested workflow.
2. Confirm that `spec.environment` is `simulation`, review every enabled adapter, and trace every
   selected capability through its enabled binding to the intended adapter plugin.
3. Define typed inputs, step dependencies, value bindings, resources, timeouts, retries, and outputs.
4. Add or update focused workflow validation and execution tests.
5. Run `uv run --locked opensdl validate MANIFEST --workflow WORKFLOW`.
6. Run `.agents/skills/develop-workflow/run.sh WORKFLOW MANIFEST 'INPUTS_JSON'`. Before the runtime
   starts any adapter, the helper permits only the reviewed OpenSDL reference `simulated-lab`,
   `local-compute`, and `human-task` entry points and verifies every enabled plugin's module and
   distribution provenance. Qualify and review any addition before changing that allowlist.
7. Inspect failure events when the run does not complete. Use `debug-run` for a persisted failure.
8. Export the run when the user needs portable execution evidence.

## Completion

The workflow validates, its tests pass, and a representative simulation run produces the expected
outputs and persisted evidence.

## Stop conditions

Stop before execution when the manifest environment is not `simulation`, a binding is missing or
ambiguous, any enabled plugin is outside the reviewed simulation allowlist, or the workflow needs
an operation that no typed capability provides.
