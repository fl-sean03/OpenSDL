# Validation report

**Release candidate:** `0.1.0a0`  
**Validation date:** 2026-08-02  
**Scope:** locked source workspace, simulator profile, and clean wheel-installed smoke test

OpenSDL is an executable public alpha. This report records the checks run against the prepared Git
repository. Deployment teams must produce separate evidence for their equipment, infrastructure,
and operating procedures.

## Source workspace

The workspace lock was generated and checked with uv 0.11.32. It resolves 105 packages for the 21
workspace members. All normal project and CI commands consume the committed lock with `--locked`.

The complete suite passed on all supported Python versions:

- CPython 3.12.3: **49 passed**;
- CPython 3.13.14 in an isolated environment: **49 passed**; and
- CPython 3.14.6 in an isolated environment: **49 passed**.

The suite covers package units, migrations, API and controller integration, adapter conformance, and
the complete simulated color campaign. Focused runtime cases cover policy denial, retries, timeout
diagnostics, lease release, cancellation intervention, and restart reconciliation. Provenance tests
cover exports with more than 500 events, artifact metadata, unique bundle members, and RO-Crate
entries.

The following checks also passed:

- Ruff and Pyright with zero errors or warnings;
- internal package-dependency boundaries;
- freshness of 11 public JSON Schemas;
- TOML, YAML, JSON, repository-skill metadata, and relative Markdown links;
- strict MkDocs build;
- Python bytecode compilation;
- shell syntax for project scripts and skill helpers;
- all six repository skills with Codex's skill validator;
- the three reference-adapter conformance cases;
- the five-iteration simulated color campaign; and
- reruns after the example created persistent local state.

The last check found and fixed an order-dependent test defect. Integration fixtures now exclude the
example's ignored `.opensdl/` runtime state when copying the laboratory definition.

## Distribution smoke test

uv 0.11.32 built one wheel and one source archive for each workspace member: **21 wheels and 21
source archives**. A clean Python 3.12 environment installed all 21 wheels without importing the
source checkout.

That environment passed these checks:

- `opensdl version` returned `0.1.0a0`;
- the SDK exposed its public core contracts;
- `opensdl init` generated a separate laboratory repository;
- the generated manifest and first workflow validated;
- `opensdl doctor` reported healthy simulated, compute, database, and artifact-store components; and
- the generated workflow completed with four successful tasks and a zero distance score.

These files are build-validation artifacts. This report does not approve a tagged package release or
publication to a registry. SBOM generation, artifact signing, internal dependency constraints, and
package-license-file review remain release work.

## Validated execution profiles

| Profile | Status | Evidence |
|---|---|---|
| Python 3.12, 3.13, and 3.14 | Verified | Locked full suite on all three versions |
| Simulator-only local laboratory | Verified | Unit, integration, E2E, conformance, example, and clean wheel-installed run |
| Structured human attestation | Verified as a synchronous reference path | Adapter and generated-workflow tests |
| SQLite metadata and local artifacts | Verified | Storage, migration, controller, API, campaign, and clean-install checks |
| PostgreSQL metadata | Models and migrations implemented | No live PostgreSQL service was exercised |
| HTTP API | Verified | FastAPI lifecycle and endpoint integration test |
| CLI and Python packages | Verified | Source tests and clean installation of all 21 wheels |
| Optional MCP transport | Import boundary tested | The MCP SDK and a live transport were not exercised |
| Container image | Verified | Podman built the pinned Dockerfile; image CLI and `doctor` checks passed |
| Physical equipment | Not validated | No hardware qualification or commissioning was attempted |

## Known warnings and tool limits

All three test runs emit one upstream Starlette warning about its `TestClient` dependency transition.
The tests pass, and OpenSDL emits no project-code deprecation warnings.

The repository validator parsed every workflow as YAML, but `actionlint` was not installed locally.
GitHub Actions provides the final workflow-parser and runner check after the first push.

A pre-publication pattern scan found no likely secrets, private keys, or unfinished-code markers in
295 nonignored source files. This scan is supporting evidence, not a substitute for GitHub secret
scanning and push protection.

## Explicit non-claims

This validation does not establish:

- production readiness or high availability;
- safety integrity or regulatory compliance;
- suitability for hazardous operations;
- correct behavior of arbitrary third-party adapters;
- live PostgreSQL, S3, Slurm, Kubernetes, SiLA 2, MADSci, or robotics compatibility;
- an end-to-end cancellation or equipment-abort protocol;
- performance guarantees; or
- package-registry release readiness.

Those outcomes require deployment-specific engineering, testing, commissioning, and evidence. The
current repository is a simulator-first reference foundation and extension surface.
