# Validation

The repository root contains the maintained [validation report](../../VALIDATION.md). It distinguishes source-tested behavior, clean package-install tests, configuration-only integrations, and deployment-specific work that has not been exercised.

For a local verification run:

```bash
uv sync --all-packages --group dev
uv run pytest
uv run python scripts/check-boundaries.py
uv run python scripts/generate-schemas.py --check
uv run python scripts/validate-repository.py
```

Run database-specific, hardware-in-the-loop, and facility acceptance tests in the deployment repository rather than treating simulator conformance as equipment qualification.
