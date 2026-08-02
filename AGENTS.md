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

- install: `uv sync --all-packages --group dev`
- test: `uv run pytest`
- lint: `uv run ruff check .`
- format: `uv run ruff format .`
- typecheck: `uv run pyright`
- boundaries: `uv run python scripts/check-boundaries.py`
- schemas: `uv run python scripts/generate-schemas.py`
- example: `uv run python examples/simulated-color-mixing/run_campaign.py`

## Architecture rules

- `core` imports no internal package.
- Applications compose packages; business logic stays in packages.
- Vendor or facility behavior belongs in adapters.
- Every operational adapter needs simulation and conformance coverage.
- Public models are typed and exported as versioned schemas.
- Database access goes through repository interfaces.
- A change is complete when code, tests, schemas, examples, and documentation agree.

Use the nearest nested `AGENTS.md` when working inside a specialized subsystem.
