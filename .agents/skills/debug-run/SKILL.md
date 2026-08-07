---
name: debug-run
description: Diagnose a failed OpenSDL run, reproduce it in simulation, and validate the smallest correct fix. Use when a workflow or task has failed or requires intervention.
---

# Debug a failed run

## Inputs

- persisted run identifier
- manifest path
- workflow and inputs when a simulation reproduction is possible

## Procedure

1. Run `.agents/skills/debug-run/run.sh RUN_ID [MANIFEST]`.
2. Run `uv run --locked opensdl events --manifest MANIFEST --run-id RUN_ID` and identify the first
   failed task.
3. Trace the policy decision, lease, adapter call, timeout, retry, and error events.
4. Reproduce with a simulation manifest when the workflow and inputs are available.
5. Fix the smallest correct contract, adapter, runtime, storage, or configuration layer.
6. Add a regression test and a conformance case when an adapter contract changed.
7. Re-run the simulation and export it with `uv run --locked opensdl export RUN_ID --manifest MANIFEST`.
8. Submit a repaired workflow as a new run with `opensdl run WORKFLOW --supersedes RUN_ID`. A run
   records the workflow it was asked to execute, so `--run-id RUN_ID` resumes only the identical
   definition and is refused for any other; superseding leaves the failed run's record intact and
   names the replacement on both.
9. Check propagation impact before completion.

## Completion

The cause is tied to persisted evidence, the regression test fails before the fix and passes after
it, and the simulation rerun has an exported evidence bundle.

## Stop conditions

Stop on ambiguous physical state or when safe recovery needs hold, abort, resume, or reconciliation
behavior that the typed interface does not expose. Do not infer physical reversal from database
state.
