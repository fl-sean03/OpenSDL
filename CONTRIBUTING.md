# Contributing

Contributions should improve interoperability, reproducibility, reliability, adoption, or scientific usefulness without unnecessarily expanding the kernel.

## Start here

```bash
uv sync --locked --all-packages --group dev
make test lint
```

`make test`, `make lint`, `make viewer`, `make docs`, and `make example` together are what the
pull-request CI job enforces, so running them locally is the way to know a change passes before you
open one. A bare `uv run --locked pytest` is narrower than it looks — see
the [development guide](docs/development/index.md) for what each target runs, and read the nearest
`AGENTS.md` before editing a subsystem.

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

## Governance

OpenSDL is maintainer-led. Maintainers review changes, approve releases, handle security reports,
and enforce project scope; a package, adapter, or domain-pack maintainer owns that subsystem's
compatibility, conformance evidence, and scientific schemas. Governance should become more
distributed once a real contributor and deployment community exists.

Routine compatible changes go through pull requests. Public schema changes, architecture boundaries,
licensing, governance, and security-model changes need a written design proposal in an issue before
implementation. [Compatibility and versioning](docs/reference/compatibility.md) is the operative
release policy: it lists the public surfaces, what each guarantees today, how a breaking change is
announced, and which of those mechanisms are not yet implemented. Amending it follows the same
design-proposal path. Semantic versioning applies after 1.0; before it the version communicates
ordering only, and migrations and release notes are still required.

The project does not use “certified safe” language unless a real certification program exists.

## Developer Certificate of Origin

Sign commits to certify that you have the right to contribute the work:

```bash
git commit -s
```

## Data and confidentiality

Use synthetic or intentionally public data in the repository. Do not submit credentials, proprietary data, export-controlled information, personal data, facility security details, or vendor files that cannot be redistributed.

## Safety-sensitive changes

Changes affecting physical execution, policy, resource leases, parameter bounds, cancellation, safe-state behavior, or reconciliation require human review and appropriate deployment-specific validation.
