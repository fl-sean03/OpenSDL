# Governance

OpenSDL begins as a maintainer-led project. Governance should become more distributed after there is a real contributor and deployment community.

## Roles

- **Maintainers** review changes, approve releases, handle security reports, and enforce project scope.
- **Package maintainers** own a stable subsystem and its compatibility.
- **Adapter maintainers** own version support, conformance evidence, and operational boundaries.
- **Domain-pack maintainers** own scientific schemas and mappings for a domain.
- **Contributors** submit code, schemas, tests, examples, issues, and reviews.

## Decisions

Routine compatible changes use pull requests. Public schema changes, architecture boundaries, licensing, governance, or security model changes require a written design proposal in the issue or RFC process before implementation. Accepted durable choices are recorded as architecture decisions when the project reaches the contributor scale that justifies a formal ADR directory.

## Releases

Semantic versioning applies after 1.0; before it, the version communicates ordering only. Pre-1.0 releases may change, but migrations and release notes are still required. Compatibility claims must name the framework, schema, adapter, backend, test-suite, and relevant hardware or simulator versions.

[Compatibility and versioning](docs/reference/compatibility.md) is the operative policy: it lists the public surfaces, what each guarantees today, how a breaking change is announced, what a deprecation requires, and which of those mechanisms are not yet implemented. Amending it is a governance decision and follows the design-proposal path above.

The project does not use “certified safe” language unless a real certification program exists.
