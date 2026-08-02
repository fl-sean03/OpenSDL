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

## Agent model routing

- Use GPT-5.6 Sol with ultra reasoning for orchestration, analysis, architecture, debugging,
  brainstorming, decisions, implementation judgment, review, and user-facing synthesis.
- Use GPT-5.6 Luna with ultra reasoning only for bounded mechanical bulk work such as inventories,
  deterministic scans, extraction, and explicitly specified repetitive edits.
- Luna returns evidence or executes a fixed specification; Sol reviews that evidence and owns every
  conclusion, scope change, and release decision.
- Do not use GPT-5.6 Terra or any model outside Sol and Luna for repository work.
