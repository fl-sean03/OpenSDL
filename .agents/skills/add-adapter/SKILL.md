---
name: add-adapter
description: Add an OpenSDL adapter with simulation and conformance evidence. Use when integrating an instrument, robot, compute service, human task, or other capability executor.
---

# Add an adapter

## Inputs

- adapter name
- first capability identifier
- destination directory, default `adapters`

## Procedure

1. Inspect the nearest `AGENTS.md` and the capability contract.
2. Run `.agents/skills/add-adapter/run.sh NAME CAPABILITY_ID [DESTINATION]`.
3. Implement typed transport, health, lifecycle, timeout, retry, and failure behavior.
4. Keep a deterministic simulator or mock beside the operational transport.
5. Add conformance cases, package tests, and one runnable simulation fixture.
6. Add the package to the workspace only when it belongs in this coordinated repository.
7. Run the package tests, `uv run --locked pytest -m conformance`, and repository validation.

## Completion

The adapter is discoverable by entry point, passes conformance, and executes its declared capability
against simulation. Report the tested transport or equipment version without claiming untested
hardware behavior.

## Stop conditions

Stop if the semantic capability, equipment limits, safe failure behavior, or simulator contract is
unclear. Do not connect physical equipment as part of scaffolding.
