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
- test: `make test` — workspace suite and the digital-twin surrogate overlay
- lint: `make lint` — lockfile, Ruff lint and format, Pyright, boundaries, schema drift, repository,
  and versions
- viewer: `make viewer` — surrogate viewer lint, typecheck, tests, build, and committed asset drift
- docs: `make docs` — `mkdocs build --strict`
- example: `make example` — the complete simulated campaign
- format: `make format` — applies Ruff formatting and safe fixes; `make lint` enforces it
- schemas: `uv run --locked python scripts/generate-schemas.py`

`make test`, `make lint`, `make viewer`, `make docs`, `make example`, and `make showcase` together
cover every check the pull-request CI job enforces. `make showcase` re-derives the campaign the
README frame is rendered from, which takes about a minute and is why CI runs it as its own job.
`make scene` covers the one that runs separately: the headless
Blender rebuild proving the committed scene is reproducible from source. It needs the exact Blender
version recorded in the scene's node inventory and takes several minutes. A bare
`uv run --locked pytest` is not the full suite: `testpaths` excludes `examples/`, so the surrogate
tests are reachable only through `make test` or `make surrogate`, and the showcase campaign only
through `make showcase`. Narrower targets (`unit`, `integration`, `e2e`, `conformance`,
`typecheck`, `boundaries`, `validate`, `showcase`, `surrogate`, `propagation`, `scene`) and the raw
command behind each target are in the `Makefile`.

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
