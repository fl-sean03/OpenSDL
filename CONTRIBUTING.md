# Contributing

Contributions should improve interoperability, reproducibility, reliability, adoption, or scientific usefulness without unnecessarily expanding the kernel.

## Start here

```bash
uv sync --all-packages --group dev
uv run pytest
uv run python scripts/check-boundaries.py
uv run python scripts/generate-schemas.py --check
```

Read [DEVELOPMENT.md](DEVELOPMENT.md) and the nearest `AGENTS.md` before editing a subsystem.

## Contribution types

### Core contract

Requires a demonstrated cross-domain need, compatibility analysis, generated schema review, migration guidance, and tests.

### Adapter

Requires typed capability definitions, lifecycle behavior, a simulator or mock, failure and recovery semantics, provenance, dependency and license review, and conformance evidence.

### Domain pack

Requires a namespace, version, scope, JSON Schemas, examples, maintainers, and mappings to relevant community standards where available.

### Documentation or example

Must distinguish implemented behavior, simulation evidence, physical validation, and deployment-specific claims.

## Pull requests

Include the problem, implementation, contract impact, tests, migration or rollback, safety and security impact, and propagation review. Keep changes focused.

## Developer Certificate of Origin

Sign commits to certify that you have the right to contribute the work:

```bash
git commit -s
```

## Data and confidentiality

Use synthetic or intentionally public data in the repository. Do not submit credentials, proprietary data, export-controlled information, personal data, facility security details, or vendor files that cannot be redistributed.

## Safety-sensitive changes

Changes affecting physical execution, policy, resource leases, parameter bounds, cancellation, safe-state behavior, or reconciliation require human review and appropriate deployment-specific validation.
