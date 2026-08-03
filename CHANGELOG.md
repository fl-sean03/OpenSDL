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
  40-second, 960-frame H.264 animation path;
- a read-only Three.js viewer with local demonstration data, stored-run replay, timeline controls,
  semantic highlights, transfers, authored-motion synchronization, browser-side scene-digest
  checks, required-binding failures, and projected sample properties; and
- lab onboarding guidance and a `start-here` skill for durable shared context and simulator-first
  setup planning.

### Changed

- laboratory manifests can declare a twin definition and optional viewer root;
- generated laboratory repositories include shared context files and onboarding guidance;
- the digital-twin architecture now fixes the framework boundary at one reference showcase while
  each laboratory owns its tailored scene;
- configured runs record the twin revision, definition digest, and scene digest used for projection;
  projection refuses a run when that binding differs from the current twin; and
- the included viewer demonstration applies only to the exact bundled revision and scene digest.

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
