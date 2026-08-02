---
name: add-adapter
description: Scaffold and implement an OpenSDL adapter with simulation and conformance coverage. Use when adding support for an instrument, robot, compute service, human task, or other capability executor.
---

# Add an adapter

## Inputs

- adapter name
- first capability identifier
- target directory

## Procedure

1. Run `uv run --locked opensdl adapter create NAME --capability-id ID --destination adapters`.
2. Implement transport, health, lifecycle, and typed failure behavior.
3. Add a deterministic simulator or mock.
4. Add conformance cases and package tests.
5. Add the workspace member or publish the package independently.
6. Add one runnable example or integration fixture.
7. Run `uv run --locked pytest -m conformance` and the propagation check.

## Completion

The adapter is discoverable by entry point, passes conformance, and can run against simulation without physical equipment.
