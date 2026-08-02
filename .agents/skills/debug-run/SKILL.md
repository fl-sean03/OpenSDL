---
name: debug-run
description: Diagnose a failed OpenSDL run, reproduce it in simulation, and validate the smallest correct fix. Use when a workflow or task has failed or requires intervention.
---

# Debug a failed run

1. Inspect the run: `uv run --locked opensdl inspect RUN_ID --manifest MANIFEST`.
2. Identify the first failed task and its policy, lease, adapter, and error events.
3. Reproduce against the simulator or replay adapter.
4. Fix the smallest correct layer.
5. Add a regression test and, when relevant, a conformance case.
6. Re-run the workflow and export the evidence bundle.
7. Check propagation impact before completion.
