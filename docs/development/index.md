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
make test          # unit, integration, E2E, and conformance tests, plus the surrogate overlay
make lint          # lockfile, Ruff lint and format, Pyright, boundaries, schemas, repository, versions
make format        # apply Ruff formatting and safe fixes
make viewer        # surrogate viewer: npm lint, typecheck, tests, build, and static/ drift
make docs          # strict MkDocs build
make example       # run the complete simulated campaign
make schemas       # regenerate checked-in JSON Schemas
make api           # serve the reference API
make clean         # remove local generated state
```

Together `make test`, `make lint`, `make viewer`, `make docs`, and `make example` cover every
check the pull-request CI job enforces. `make scene` covers the one that runs separately: the
headless Blender rebuild that proves the committed scene bytes are reproducible from source.
It needs the exact Blender version the scene records and takes several minutes, which is why it
is not in the pull-request path. Details worth knowing:

- `make test` depends on `make surrogate`, which installs the example adapter with `--with-editable`,
  runs `examples/digital-twin-surrogate/tests`, and runs `opensdl twin validate` against the twin
  manifest. `testpaths` in `pyproject.toml` excludes `examples/`, so a bare `uv run --locked pytest`
  skips those tests.
- `make lint` begins with `uv lock --check` and ends with `scripts/validate-repository.py` and
  `scripts/check-version.py`. It also runs `ruff format --check`, so formatting is enforced rather
  than advisory; run `make format` before committing.
- `make viewer` needs Node 22.12 or later and runs `npm ci`, so it replaces
  `examples/digital-twin-surrogate/viewer/node_modules`.
- `make docs` installs the `docs` dependency group alongside `dev` so the workspace keeps its test
  and lint tooling. CI installs the `docs` group on its own.

`scripts/bootstrap.sh`, `scripts/test.sh`, and `scripts/lint.sh` cover the common subset for
environments without Make.

One workflow enforces nothing: [the pull request reviewer](pull-request-reviewer.md) reviews a pull
request against the rules in `AGENTS.md` and posts a comment. It is off until `ANTHROPIC_API_KEY`
exists, it cannot push, merge, or block a merge, and no gate above depends on it.

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

Application code uses SQLAlchemy models in `packages/storage/src/opensdl_storage/db_models.py`. The
migration history lives beside them, in
`packages/storage/src/opensdl_storage/migrations/versions/`, so it ships inside the `opensdl-storage`
distribution and a generated laboratory can migrate its store with no checkout of this repository.
`database/alembic.ini` is the authoring entry point and points at that packaged environment.

**Alembic is the only writer of the schema.** `Database.initialize()` runs the migration history;
it used to call `create_all()` and hand-write a `schema_versions` row, which could never alter an
existing table and diverged from the migrations by 23 indexes without any check noticing. A store
created before that change carries no `alembic_version`, so `initialize()` adopts it — stamping it
at `ADOPTION_REVISION` and upgrading from there — rather than failing on `table schema_versions
already exists`. Never call `Base.metadata.create_all()` in application code.

```bash
uv run --locked opensdl migrate --manifest opensdl.yaml --check   # report, write nothing
uv run --locked opensdl migrate --manifest opensdl.yaml           # apply
uv run --locked alembic -c database/alembic.ini revision --autogenerate -m "describe change"
uv run --locked alembic -c database/alembic.ini upgrade head      # by hand, without a manifest
```

`opensdl migrate` is a thin wrapper over `opensdl_controller.migrate.plan` and
`opensdl_controller.migrate.upgrade`. Call those directly, or use the Alembic commands above, when
the CLI is not installed; the schema upgrade itself does not depend on it.

Set `OPENSDL_DATABASE_URL` before running the Alembic commands against a non-default database.
`opensdl migrate` reads the manifest's `spec.storage.database.url` and honours the same override.

Schema changes require:

1. SQLAlchemy model change;
2. a new migration — append a revision, never edit a shipped one;
3. repository conversion update;
4. tests against SQLite;
5. PostgreSQL CI when the change is database-specific;
6. documentation and propagation review.

`tests/integration/test_migrations.py` compares the database Alembic builds against
`Base.metadata` using the same comparison `--autogenerate` uses. A model change without a matching
revision fails there, which is the check that did not exist while the two paths were diverging.
A revision that must serve both a store built by Alembic and one adopted from the pre-Alembic path
has to be idempotent; revision `0002` is the worked example.

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
- example tests: complete examples that ship their own adapter, run through `make surrogate`;
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

OpenSDL has never been released: no tag exists and no distribution has been published to any package
index. `.agents/skills/release/run.sh VERSION` and the manual **Build distribution candidates**
workflow both end at wheels and sdists — one in a local `dist/`, one in an expiring Actions
artifact. Neither publishes, signs, tags, or generates an SBOM.

A candidate is ready when all tests and conformance pass, `uv lock --check` passes against the
committed lockfile, generated schemas are current, migrations are present, every package carries the
selected version, and public changes have release notes and migration guidance.

Publishing is a separate, deliberate act with irreversible parts — a package-index name is claimed
by its first upload and a published version can never be re-uploaded. What it would take is written
out in [releasing and publishing](releasing.md). Do not improvise it.

The workspace remains pre-1.0; compatibility changes still require explicit notes.
