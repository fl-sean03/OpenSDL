# Roadmap

The [agent-native operation plan](docs/architecture/agent-native-operation.md) defines the
repository, simulator, collaboration, live-equipment, and optional external-harness sequence. This
roadmap tracks product releases. The [development backlog](docs/development/backlog.md) is the
running implementation list.

No OpenSDL release exists yet: nothing is tagged and no distribution is published. "v0.1 alpha"
below names the state the workspace reached, not something installable.

## Implemented in v0.1 alpha

- uv Python monorepo with independently packaged members
- laboratory manifest and generated JSON Schemas
- capability, workflow, resource, run, task, event, artifact, and decision models
- plugin registry for adapters, optimizers, and domain packs
- reference policy engine
- durable DAG runtime with retries, timeouts, leases, events, and recovery state
- relational model on SQLite, using portable column types; no PostgreSQL service is exercised
- content-addressed local artifact store
- deterministic simulation and fault injection
- simulated mixer, balance, colorimeter, and labware transport
- local compute adapter with three fixed numerical capabilities and no expression evaluator
- human-task adapter recording a typed outcome and an unverified caller-supplied operator name
- campaign runner that feeds scored results back to an optimizer, and a grid optimizer that ignores them
- CLI, Python SDK, HTTP API, and optional MCP hook
- run bundle export and research-graph projection
- propagation graph implementation
- organization-lab, adapter, and capability generators
- materials, chemistry, and physics packs exposing typed models as JSON Schema, without units, capabilities, or committed schemas
- complete simulator-only closed-loop example
- unit, integration, end-to-end, and adapter-conformance tests

## Unreleased

Merged after the v0.1 alpha and not yet part of a release. See [CHANGELOG.md](CHANGELOG.md).

- versioned, engine-neutral digital-twin scene binding with a digest-pinned scene asset
- deterministic projection of persisted run events into immutable visual cues
- twin commands in the CLI, read-only twin and viewer routes in the HTTP API, and SDK twin methods
- runs pinned to the twin revision, definition digest, and scene digest used for projection
- read-only Three.js viewer with demonstration playback and stored-run replay
- one complete surrogate-cell reference showcase for the binding contract and viewer
- laboratory onboarding guidance and a start-here skill for simulator-first setup planning

Historical replay across twin revisions, general scene validation, and an on-demand
build-digital-twin skill remain open work. See
[lab-specific digital twins](docs/architecture/digital-twin.md).

## v0.2 — real integration and richer human work

- queued human tasks with identity, witness, and configurable evidence requirements
- SiLA 2 reference adapter
- MADSci orchestration backend
- Bluesky event ingestion
- networked balance reference integration
- hardware-in-the-loop test profile
- typed calibration records and validity checks
- explicit cancellation and abort receipts
- PostgreSQL CI and backup/restore tests

## v0.3 — compute and data infrastructure

- local subprocess and container executors
- Slurm backend with job resumption
- S3-compatible artifact store
- Tiled data adapter
- model registry, validity domains, checkpoints, and uncertainty
- materials workflow example combining physical and atomistic computation
- multi-fidelity campaign strategy interface

## v0.4 — production operation

- authentication and scoped service identities
- pluggable policy providers
- signed adapter and skill promotion
- OpenTelemetry traces and metrics
- deployment health and reconciliation dashboard
- PostgreSQL high-availability guidance
- air-gapped package and model promotion
- versioned conformance result registry

## v0.5 — distributed laboratories

- brokered work across multiple sites
- external characterization provider interface
- sample custody across facility boundaries
- federated artifact metadata
- distributed campaign scheduling
- cross-site replay and incident evidence

## Release criterion for 1.0

OpenSDL reaches 1.0 only after multiple independent laboratories run the same public contracts through different physical and computational backends, migrations have been exercised across releases, and the compatibility suite has external adopters.

No compatibility suite exists yet, and no laboratory database can currently be migrated at all.
[Compatibility and versioning](docs/reference/compatibility.md) states what each public surface
guarantees today and what the missing suite would have to cover.
