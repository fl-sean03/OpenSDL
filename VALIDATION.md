# Validation report

**Release candidate:** `0.1.0a0`  
**Validation date:** 2026-08-02  
**Scope:** source repository and clean wheel-installed simulator profile

OpenSDL is an executable alpha. This report records what was actually exercised while preparing the repository and what remains deployment-specific or untested.

## Verified

### Source repository

The complete source workspace passed:

- **39 pytest tests** across package, integration, end-to-end, migration, and conformance suites;
- laboratory manifest and workflow validation;
- generation and freshness checks for **11 public JSON Schemas**;
- configured internal package-dependency boundary checks;
- TOML, YAML, JSON, and relative Markdown-link validation;
- Python bytecode compilation;
- SQLite schema creation and the initial Alembic migration;
- HTTP API lifecycle and representative endpoints;
- controller startup, health checks, workflow execution, persistence, and shutdown;
- restart reconciliation behavior;
- content-addressed artifact writes and verified reads;
- reference adapter conformance;
- complete closed-loop simulated color campaign;
- repository propagation-graph traversal.

### Distribution and generated projects

All **21 independently packaged workspace members** built as Python wheels. A clean validation environment installed those wheels and exercised the public console interface rather than importing the source checkout.

The wheel-installed validation covered:

- `opensdl version`;
- generation of a separate organization laboratory repository;
- inclusion of the generated repository's hidden `.github/workflows/ci.yml` template;
- validation of generated manifests and workflows;
- `opensdl doctor` against the generated laboratory;
- execution of a generated workflow containing simulated labware movement, mixing, color measurement, and numerical analysis;
- execution of a generated structured human-attestation workflow;
- generation of a simulator-first adapter package and passing conformance test;
- generation of an installable scientific domain pack.

## Validated execution profiles

| Profile | Status | Evidence |
|---|---|---|
| Simulator-only local laboratory | Verified | Unit, integration, E2E, conformance, and clean wheel-installed runs |
| Structured human attestation | Verified as a synchronous reference path | Adapter, generated example, and E2E execution |
| SQLite metadata and local artifacts | Verified | Storage tests, migrations, controller/API tests, campaign run |
| PostgreSQL metadata | Model and migration compatibility implemented | Not executed against a live PostgreSQL service in this environment |
| HTTP API | Verified | FastAPI lifecycle and endpoint integration tests |
| CLI and Python packages | Verified | Source and clean wheel-installed execution |
| Optional MCP transport | Implemented behind an optional dependency | MCP SDK was not available in the offline validation environment |
| Docker Compose deployment | Configuration present | Docker was not available in the validation environment |
| Physical equipment | Not validated | No hardware qualification or commissioning was attempted |

## Known release-preparation gap

The repository is configured as one `uv` workspace, but a shared `uv.lock` is not included in this archive. The validation environment could not reach package registries, and generating a trustworthy lockfile requires dependency resolution against a reachable registry. Before the first public release:

```bash
uv lock
uv sync --all-packages --group dev
uv run pytest
```

Commit the resulting lockfile after those checks pass. No synthetic or hand-written lockfile has been substituted.

## Explicit non-claims

This validation does not establish:

- production readiness;
- safety integrity;
- regulatory compliance;
- suitability for hazardous operations;
- correct behavior of arbitrary third-party adapters;
- PostgreSQL, S3, Slurm, Kubernetes, SiLA 2, MADSci, or live robotics compatibility;
- performance or high-availability guarantees.

Those require deployment-specific engineering, testing, commissioning, and evidence. The current artifact is a complete, functioning reference foundation and extension surface—not a qualified control system for every laboratory.
