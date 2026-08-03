# Changelog

All notable changes to OpenSDL will be documented here. The project follows semantic versioning after the first stable release; pre-1.0 compatibility changes remain explicitly documented.

## Unreleased

### Added

- `opensdl-twin`, with a versioned scene-binding contract, digest-checked loading, and deterministic
  projection of persisted run events into immutable visual cues;
- digital-twin commands in the CLI and read-only definition, scene, run-projection, and viewer
  routes in the HTTP API;
- SDK methods for twin definitions, verified scene bytes, and projected runs, plus caller-supplied
  stable run identifiers;
- one complete, real-scale Flex-class surrogate-cell reference with original procedural geometry,
  published equipment dimensions, Blender source, GLB output, provenance, 70 scene checks, and a
  committed 40-second, 960-frame H.264 animation of the authored sequence;
- a read-only Three.js viewer with local demonstration data, stored-run replay, timeline controls,
  semantic highlights, transfers, authored-motion synchronization, browser-side scene-digest
  checks, required-binding failures, and projected sample properties; and
- lab onboarding guidance and a `start-here` skill for durable shared context and simulator-first
  setup planning;
- generated JSON Schemas for the twin definition and cue contracts, produced by a single composed
  generator that both `scripts/generate-schemas.py` and `opensdl schema generate` consume; and
- an enforced Ruff formatting gate in `make lint` and CI.

### Changed

- laboratory manifests can declare a twin definition and optional viewer root;
- generated laboratory repositories include shared context files and onboarding guidance;
- the digital-twin architecture now fixes the framework boundary at one reference showcase while
  each laboratory owns its tailored scene;
- configured runs record the twin revision, definition digest, and scene digest used for projection;
  projection refuses a run when that binding differs from the current twin; and
- the included viewer demonstration applies only to the exact bundled revision and scene digest;
- cue `occurredAt` is normalized to UTC before publication, so a store that cannot persist an offset
  no longer yields an ambiguous timestamp and ordering no longer disagrees with the emitted value;
- `TwinCue` rejects blank identifiers, matching every other model in the twin contract; and
- the scene motion report carries the scene digest, so its checks are bound to the geometry they
  describe; and
- the node inventory records the Blender version that produced the scene, and a test rebuilds the
  reference scene headlessly and compares the exported bytes, so the committed digests are a
  reproducibility claim rather than a self-assertion.

### Fixed

- the reference scene was not physically plausible. The gripper carriage passed through the
  enclosure glazing because the reader-lid dock stood in a deck column the carriage cannot reach;
  the jaw paddles hung below the payload and intersected the deck, the shaker, the reader and the
  Stacker shuttles on every pick; the friction pads protruded through the plate skirt; the pipette
  was commanded from the carriage origin while its nozzles hang forward of it, so tips were picked
  off-column and dispensed between well rows; and the carriage descended through the plate while it
  was shaking. Carried motion is now derived from the carrier pose rather than authored alongside
  it, and `scene/check_scene.py` verifies carry rigidity, grip contact, and mesh interpenetration
  before the export;
- `opensdl schema generate` emitted only the pre-twin schema set while the repository script emitted
  the full set;
- the reference viewer presented stylized playback pacing and a synthetic demonstration timestamp
  as if they were elapsed and recorded time, and labelled a one-shot read of a persisted run as
  live; and
- the reference viewer's cue validator rejected an absent `runId` that the published contract
  declares optional, and accepted unknown keys the contract forbids.

## 0.1.0a0 — 2026-08-02

Initial executable alpha.

### Added

- 21-package `uv` monorepo with enforced package boundaries;
- versioned laboratory, capability, workflow, run, task, event, artifact, and campaign contracts;
- SQLite/PostgreSQL-compatible metadata layer and Alembic migration;
- content-addressed local artifact store;
- durable reference runtime with DAG scheduling, retries, leases, timeouts, event history, and restart reconciliation;
- deterministic simulation, fault injection, and replay primitives;
- simulated laboratory, numerical compute, structured human task, and grid optimizer extensions;
- materials, chemistry, and physics domain packs;
- CLI, Python SDK, HTTP API, typed operator gateway, and optional MCP transport;
- laboratory, adapter, capability, and domain-pack generators;
- generated JSON Schemas, conformance tests, closed-loop example, run exports, and propagation graph;
- CI, release, documentation, container, and development-environment configuration.

### Status

This release is suitable for evaluation, extension development, and simulator-based laboratory prototyping. It is not qualified for production or hazardous physical control. See [VALIDATION.md](VALIDATION.md).
