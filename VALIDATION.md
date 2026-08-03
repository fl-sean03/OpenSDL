# Validation report

**Release candidate:** `0.1.0a0`

**Validation date:** 2026-08-03

**Scope:** locked source workspace, simulator and digital-twin checks, and current wheel smoke test

OpenSDL is an executable public alpha. This report records the checks run against the prepared Git
repository. Deployment teams must produce separate evidence for their equipment, infrastructure,
and operating procedures.

## Agent-native extension validation

On 2026-08-03, the repository instruction, skill, and generated-laboratory extension passed on
CPython 3.12.3:

- **72 tests**, including skill metadata and adapters, generated-lab context and cold rendering,
  installed CLI and API version reporting, release-version propagation, plugin-entry-point
  collision checks, and rejection of an unused physical adapter before its lifecycle starts;
- Ruff, Pyright, package boundaries, schema freshness, repository validation, release-version
  consistency, the five-iteration simulation example, and a strict documentation build;
- all ten canonical skills through the Agent Skills validator;
- a wheelhouse-installed generated lab with manifest and workflow validation, doctor, two tests,
  and a completed simulator workflow;
- a pre-twin, isolated `0.1.0a1` release rehearsal that built 21 wheels and 21 source archives,
  reported the synchronized CLI and API version, preserved immutable import evidence, and refused a
  second build into the nonempty artifact directory; and
- a native fresh Codex session that selected orientation and simulation-development skills and
  stopped rather than inventing unsupported physical cancel or resume commands.

The Python 3.13 and 3.14 matrix was not rerun locally for this extension; hosted CI remains the
cross-version evidence source. The upstream Starlette `TestClient` warning described below remains.

## Digital-twin alpha validation

On 2026-08-03, the digital-twin contract, projection path, reference scene, and viewer passed these
focused checks on the source workspace:

- the current CPython 3.12 source suite passed **190 tests**, and the example adapter overlay passed
  **13 tests**;
- `opensdl twin validate` loaded the example definition and matched its declared scene digest;
- targeted package, CLI, and API tests covered model validation, safe scene loading, deterministic
  projection, run-to-twin binding pins, stable run identifiers, twin routes, and viewer-path
  containment;
- the viewer's **30-test** Vitest suite, Biome check, TypeScript typecheck, deterministic static
  build, and dependency audit passed;
- the reference GLB contract check found every required node, covered its authored 960-frame range,
  and received no issues from the Khronos validator;
- viewer tests covered browser-side scene-digest verification, missing-binding failure, authored-motion
  synchronization, and exact-reference demo selection; and
- the generated motion report marked all **70** deck, labware, gripper, tip, liquid, lid, door,
  Stacker, and Heater-Shaker checks as passed.

The GLB digest in `twin.yaml` matched both the generated node inventory and the scene file. This is
contract and visualization evidence. It does not add physical, kinematic, collision, performance,
or safety claims.

## Source workspace

The workspace lock was generated and checked with uv 0.11.32. It records 106 packages for the 22
workspace members. All normal project and CI commands consume the committed lock with `--locked`.

The current complete source suite passed **190 tests** on CPython 3.12.3, with **13** additional
tests in the reference example's editable adapter overlay. Before the twin addition, the complete
suite also passed on the other supported Python versions:

- CPython 3.13.14 in an isolated environment: **49 passed**; and
- CPython 3.14.6 in an isolated environment: **49 passed**.

That suite covers package units, migrations, API and controller integration, adapter conformance, and
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
- all ten repository skills with the Agent Skills validator;
- the three reference-adapter conformance cases;
- the five-iteration simulated color campaign; and
- reruns after the example created persistent local state.

The last check found and fixed an order-dependent test defect. Integration fixtures now exclude the
example's ignored `.opensdl/` runtime state when copying the laboratory definition.

## Distribution smoke test

uv 0.11.32 built **22 wheels and 22 source archives** from the current workspace into a fresh
temporary output directory, including a populated `opensdl-twin` wheel. A clean Python 3.12
environment installed all 22 wheels without importing the source checkout.

That environment passed these checks:

- `opensdl version` returned `0.1.0a0`;
- the twin, controller, API, and SDK public modules imported successfully;
- the wheel-installed CLI validated the reference `twin.yaml` and its scene digest;
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
| Python 3.12, 3.13, and 3.14 | Pre-twin evidence | Locked full suite before the twin addition; current matrix rerun pending |
| Simulator-only local laboratory | Verified | Unit, integration, E2E, conformance, example, and clean wheel-installed run |
| Structured human attestation | Verified as a synchronous reference path | Adapter and generated-workflow tests |
| SQLite metadata and local artifacts | Verified | Storage, migration, controller, API, campaign, and clean-install checks |
| PostgreSQL metadata | Models and migrations implemented | No live PostgreSQL service was exercised |
| HTTP API | Verified | FastAPI lifecycle and endpoint integration test |
| CLI and Python packages | Verified on Python 3.12 | Current source tests, 22 wheels and source archives, clean 22-wheel installation, public imports, CLI version, and twin validation |
| Optional MCP transport | Import boundary tested | The MCP SDK and a live transport were not exercised |
| Container image | Verified | Podman built the pinned Dockerfile; image CLI and `doctor` checks passed |
| Physical equipment | Not validated | No hardware qualification or commissioning was attempted |

## Known warnings and tool limits

All three test runs emit one upstream Starlette warning about its `TestClient` dependency transition.
The tests pass, and OpenSDL emits no project-code deprecation warnings.

The repository validator parsed every workflow as YAML, but `actionlint` was not installed locally.
GitHub Actions provides the final workflow-parser and runner check after the first push.

Before the twin addition, a pre-publication pattern scan found no likely secrets, private keys, or
unfinished-code markers in the then-current 295 nonignored source files. This historical scan is
supporting evidence, not a substitute for a current dedicated secret scan, GitHub secret scanning,
or push protection.

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
