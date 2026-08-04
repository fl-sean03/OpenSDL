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

- the reference scene depicted lab automation placed in a human room rather than a self-driving
  laboratory. It was first an enclosed cell that hid the work, then an open bench with standing-height
  casework, a chair, a desktop workstation, waste bins and dispensers — a space whose every dimension
  served a person. A self-driving laboratory is a closed loop whose plant is designed around that
  loop, so the scene is now a purpose-built 45-series T-slot machine frame on levelling feet: five
  tied working planes, the transport runway carried on the frame's own end towers, plate hotels
  holding a visible queue rather than one ceremonial plate, and a rack-mounted compute node whose
  display shows the campaign as state — a parameter space converging, a flattening residual, the last
  measured responses. The human layer is gone apart from one interlocked load port. Slot identifiers
  are named for their role rather than borrowed from a vendor deck grid, and the build emits a named
  camera rig with per-pose hide lists, so stills frame the work deliberately instead of auto-framing;
- the animation held one fixed wide pose for all 960 frames, so no component was ever seen closely
  and nothing read as active. It is now a six-shot edit averaging 6.7 seconds, cut to the standards
  the form actually uses: shots sit inside the 5–8 second band architectural visualisation works to,
  and every cut changes the camera angle about the subject by more than the 30 degrees that separates
  a cut from a jump cut, as well as changing framing by at least two size steps. Those figures are
  computed by the build and printed, and `validate_camera_shots` refuses to build a list that misses
  the band, the angle or the framing change, so pacing cannot regress quietly. The camera aims
  through a constraint on an animated target rather than keyframed Euler rotation, which cannot flip
  on an arcing move. Cameras are excluded from the export, so the edit does not touch the scene
  digest; and
- EEVEE was silently dropping shadow maps. Twenty area lights over a 2300-node scene overflow the
  default shadow pool on the close shots, and the only symptom is a line on stderr, so a render can
  look finished and be wrong. Raising the pool took a full pass from 5568 overflow reports to none;
- the reference cell drove two independent carriages along one rail, which is a collision hazard and
  forced every spatial check to keep testing the two against each other. There is now a single mover
  carrying interchangeable heads: a gripper and a pipetting head that couple to it and rest in docks
  when idle, with two head changes in the sequence. A coupled head's pose is written from the mover's,
  so a head cannot move under its own power, and a new invariant asserts that at every frame each head
  is either coupled or docked — never both, never neither — with no two heads coupled at once;
- the scene used four different words for the reader station: the anchor called it `characterize`, the
  node called it `Colorimeter`, the entity called it `plate-reader`, and the capability driving it is
  `cell-characterize`. Hardware vocabulary is now defined once and applied throughout — cell, mover,
  head, dock, station, slot, hotel, carrier, anchor — with stations and anchors taking the capability
  verb, and the table is published in the scene README rather than left implied. Renaming the anchors
  reached further than the scene, because an anchor identifier is also a transfer cue's source and
  destination: the workflow, the transfer capability's location enum, and the example adapter moved
  with it, or the viewer could not have resolved a transfer;
- the gripper jaws had no geometry connecting them to the wrist, so they read as floating bars even
  though they tracked the carriage exactly and gripped the plate correctly. There is now a
  continuous actuator, cross-rail, finger-carrier and paddle chain, and a jaw-mechanism invariant
  requires each consecutive link to stay in contact at every authored jaw width;
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
