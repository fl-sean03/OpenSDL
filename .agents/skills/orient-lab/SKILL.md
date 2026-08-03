---
name: orient-lab
description: Inspect the current OpenSDL repository and declared laboratory state. Use when a user asks for current status or needs a declared-state baseline before a concrete task; use start-here for setup planning, inventory changes, or new equipment.
---

# Orient to a laboratory

## Inputs

- manifest path
- optional run identifier or workflow path that defines the current task

Use `start-here` instead when the user is establishing the lab, changing its setup plan, or adding
newly reported equipment.

## Procedure

1. Read the nearest `AGENTS.md` and inspect `git status --short`, the branch, and recent commits.
2. Read the shared laboratory context under `docs/lab/` when present. Treat facts, assumptions,
   decisions, inventory evidence, and lab-specific work as planning context rather than runtime
   evidence.
3. Read the selected manifest and identify its environment, storage, adapters, capabilities,
   resources, and policy version.
4. Run `.agents/skills/orient-lab/run.sh MANIFEST` to validate files without opening the runtime
   store.
5. Read only the architecture and workflow files needed for the user's task.
6. Explain that `doctor`, capability listing, run inspection, and event queries currently initialize
   or update the configured store. `doctor` can also reconcile incomplete runs.
7. Run those commands only when the user requests operational evidence and accepts that behavior.
8. Report current evidence, mismatches, active assumptions, and commands that are unavailable.

## Completion

The user receives an on-demand summary tied to the current Git revision, validated manifest,
declared environment, adapters, capabilities, resources, and policy. Any runtime evidence is marked
as a state-touching query.

## Stop conditions

Stop if the manifest is missing or validation fails. Do not infer health, active runs, or physical
state from declared configuration.
