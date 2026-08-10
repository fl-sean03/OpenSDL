# Validation

The repository root contains the maintained
[validation report](https://github.com/fl-sean03/OpenSDL/blob/main/VALIDATION.md). It distinguishes
source-tested behavior, clean package-install tests, configuration-only integrations, and
deployment-specific work that has not been exercised.

For a local verification run:

```bash
uv sync --locked --all-packages --group dev
make test lint example
```

`make lint` covers the lockfile, Ruff lint and format, Pyright, package boundaries, propagation
coverage, generated-schema drift, repository structure, and version agreement. Add `make viewer` and
`make docs` to match the full pull-request gate. See
[testing](testing.md) for what each target runs and why a bare `pytest` is narrower than it looks.

Run database-specific, hardware-in-the-loop, and facility acceptance tests in the deployment repository rather than treating simulator conformance as equipment qualification.
