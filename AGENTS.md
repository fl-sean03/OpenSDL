# Repository instructions

## Project

OpenSDL is a modular framework for computational and autonomous laboratories.

## Layout

- reusable packages: `packages/`
- deployable applications: `apps/`
- integrations: `adapters/`
- scientific extensions: `domain-packs/`
- complete examples: `examples/`
- cross-package tests: `tests/`

## Commands

- install: `uv sync --locked --all-packages --group dev`
- test: `uv run --locked pytest`
- lint: `uv run --locked ruff check .`
- format: `uv run --locked ruff format .`
- typecheck: `uv run --locked pyright`
- boundaries: `uv run --locked python scripts/check-boundaries.py`
- schemas: `uv run --locked python scripts/generate-schemas.py`
- versions: `uv run --locked python scripts/check-version.py`
- example: `uv run --locked python examples/simulated-color-mixing/run_campaign.py`

## Architecture rules

- `core` imports no internal package.
- Applications compose packages; business logic stays in packages.
- Vendor or facility behavior belongs in adapters.
- Every operational adapter needs simulation and conformance coverage.
- Public models are typed and exported as versioned schemas.
- Database access goes through repository interfaces.
- A change is complete when code, tests, schemas, examples, and documentation agree.

Use the nearest nested `AGENTS.md` when working inside a specialized subsystem.

## Working state

- In a fresh session, inspect Git state before editing. Read the relevant manifest, subsystem
  instructions, and repository skill before acting.
- In a continuing session, refresh Git, tests, and the selected manifest. Query runtime evidence
  only when the task requires it, account for query side effects, preserve unrelated work, and do
  not repeat completed setup.
- Git records intended implementation. The configured OpenSDL store records runs, events, and
  artifacts. Conversation history remains private and has no authority over shared project state.
- The active agent harness controls workspace, shell, network, and source-control permissions.
  OpenSDL manifests, policy, and runtime contracts control laboratory actions.
- Repository skills live in `.agents/skills/`. Use them for recurring procedures and keep durable
  rules in `AGENTS.md`.
