# Development guide

## Prerequisites

- Python 3.12+
- `uv`
- Git
- Docker only for the optional PostgreSQL deployment

## Set up

```bash
uv sync --locked --all-packages --group dev
uv run --locked opensdl validate examples/simulated-color-mixing/opensdl.yaml \
  --workflow examples/simulated-color-mixing/workflow.yaml
uv run --locked pytest
```

The workspace uses one committed `uv.lock` across independently packaged members. Normal setup and
CI use `--locked` so dependency metadata cannot silently rewrite the lockfile. Update dependencies
with uv 0.11.32, which CI and the container pin. Review the lock diff and rerun the full validation
matrix. Every member has its own `pyproject.toml`, source tree, and tests.

## Common commands

```bash
make sync          # install all workspace packages and dev tools
make test          # unit, integration, E2E, and conformance tests
make lint          # Ruff, Pyright, boundaries, schemas, repository, and version checks
make schemas       # regenerate checked-in JSON Schemas
make example       # run the complete simulated campaign
make api           # serve the reference API
make clean         # remove local generated state
```

Equivalent scripts are in `scripts/` for environments without Make.

## Run the local stack

SQLite-only:

```bash
uv run --locked opensdl doctor --manifest examples/simulated-color-mixing/opensdl.yaml
uv run --locked opensdl serve-api --manifest examples/simulated-color-mixing/opensdl.yaml
```

PostgreSQL:

```bash
cp .env.example .env
docker compose up --build
```

## Database

Application code uses SQLAlchemy models in `packages/storage`. Alembic configuration and migration history live in `database/`.

```bash
uv run --locked alembic -c database/alembic.ini upgrade head
uv run --locked alembic -c database/alembic.ini revision --autogenerate -m "describe change"
```

Set `OPENSDL_DATABASE_URL` before running migrations against a non-default database.

Schema changes require:

1. SQLAlchemy model change;
2. migration;
3. repository conversion update;
4. tests against SQLite;
5. PostgreSQL CI when the change is database-specific;
6. documentation and propagation review.

## Add a capability

```bash
uv run --locked opensdl capability create instrument.measure_temperature \
  --name "Measure temperature" \
  --destination capabilities
```

A public capability needs typed inputs and outputs, units where applicable, resource requirements, side effects, risk class, timeout, retries, simulator status, and provenance expectations.

## Add an adapter

```bash
uv run --locked opensdl adapter create networked-balance \
  --capability-id instrument.measure_mass \
  --destination adapters
```

Complete the generated package with:

- transport and lifecycle implementation;
- deterministic simulator or mock;
- typed errors;
- health and reconnect behavior;
- idempotency and retry analysis;
- conformance cases;
- operational validation notes.

Then add it to the workspace or publish it independently.

## Add a domain pack

```bash
uv run --locked opensdl domain-pack create electrochemistry --destination domain-packs
```

Domain packs attach namespaced scientific models without changing the runtime lifecycle. Follow the implemented materials, chemistry, and physics packages. A pack exports a callable under `opensdl.domain_packs` and returns a name, version, and JSON Schemas.

## Add a workflow

Workflows are YAML or JSON representations of `WorkflowDefinition`. References support:

```text
${inputs.parameter}
${steps.step_id.output.field}
```

Dependencies must be explicit. The runtime executes independent steps in the same topological layer concurrently.

## Test layers

- package tests: local contracts and behavior;
- integration tests: composition across packages or API boundaries;
- end-to-end tests: complete scientific loop;
- conformance tests: extension compatibility;
- future hardware tests: separate, deployment-controlled suites.

Every behavior change should be tested at the lowest useful layer and at one representative composed layer.

## Source schemas

Pydantic models are the Python source. Checked-in language-neutral schemas are generated:

```bash
uv run --locked python scripts/generate-schemas.py
```

CI fails when generated schemas differ from committed files.

Release versions must also agree across workspace packages, citation metadata, and generated
dependency floors:

```bash
uv run --locked python scripts/check-version.py
```

## Dependency boundaries

Run:

```bash
uv run --locked python scripts/check-boundaries.py
```

Do not solve a boundary violation by adding a broad common package. Move behavior to the correct layer or introduce a narrow protocol.

## Organization repository workflow

Generate a separate lab repository with `opensdl init`. That repository should carry its own lockfile, tests, deployment configuration, and release process. It may pin OpenSDL packages and adapters independently from this monorepo.

## Releases

1. all tests and conformance pass;
2. `uv lock --check` passes and CI consumes the committed lockfile;
3. generated schemas are current;
4. migrations are present;
5. public changes have release notes and migration guidance;
6. artifacts and SBOM are built;
7. packages share the selected release version;
8. signed tags are preferred for public releases.

The workspace remains pre-1.0; compatibility changes still require explicit notes.
