# Development backlog

This page is the maintained list of framework work that remains.
[ROADMAP.md](https://github.com/fl-sean03/OpenSDL/blob/main/ROADMAP.md) keeps the release view. A
laboratory repository keeps its own work in `docs/lab/setup-plan.md`.

The [2026-08-05 repository audit](audit-2026-08-05.md) stress-tested the framework against its own
stated vision and records the gaps this page does not yet track, with evidence for each. Its
findings have not been folded into the sections below and nothing in it has been acted on.

Update this page when a design changes, an implementation lands, or new evidence changes the order.
Check an item only when its stated evidence exists in the repository or a linked deployment record.

## Product guardrails

- Keep the default experience inside a normal agent conversation or direct programmatic interface.
- Keep one broad agent entry point. Skills describe procedures rather than separate operator roles.
- Keep the framework general. Laboratory repositories own equipment, workflows, private
  integrations, and custom 3D scenes.
- Keep chat history private. Promote only confirmed shared context into Git.
- Keep Git configuration, runtime evidence, secrets, and visual assets in their correct authorities.
- Use native harness controls for files, shell, network, and Git.
- Use OpenSDL contracts for laboratory policy, execution, evidence, and concurrency.
- Begin with simulation. Add physical authority only after typed control and commissioning evidence
  exist.
- Do not add a required dashboard, persistent context strip, model catalog, or custom harness.

## Foundation delivered

- [x] Public simulator-first framework, packages, CLI, API, SDK, MCP hook, tests, and example.
- [x] Agent-native operating model for fresh, continuing, and multi-user work.
- [x] Canonical Agent Skills tree with Codex and Claude Code discovery adapters.
- [x] Generated laboratory repository with agent instructions and simulator workflows.
- [x] `start-here` intake procedure and generated shared lab-context files.
- [x] Skill-authoring procedure and repository validation for skill and instruction structure.
- [x] Blender selected as the single 3D authoring pipeline.
- [x] Versioned digital-twin binding, deterministic event projection, and read-only viewer alpha.
- [x] One complete reference showcase for contract and viewer testing.
- [x] User-specific digital-twin boundary documented without a shared equipment-model catalog.

## 1. Distribution and generated-repository portability

- [ ] Publish all alpha packages to one stable package source. Generated repositories must resolve
  dependencies without a path to a developer checkout.
- [ ] Generate a portable lockfile for a new lab. A clean clone must install and test from the stable
  source.
- [ ] Turn on the full generated-lab CI job by default after package publication.
- [ ] Define offline and air-gapped package promotion, including integrity metadata and rollback.
- [ ] Add release SBOMs, artifact signing, package-license checks, and verified publication.

## 2. Onboarding and durable laboratory context

- [ ] Forward-test `start-here` across greenfield, existing, hybrid, continuing, and dirty-worktree
  conversations in each supported harness.
- [ ] Add a typed equipment-inventory contract after pilot labs confirm the fields and state model.
  It must keep evidence, integration, and visual-twin state separate.
- [ ] Add inventory validation. A reported item must not become an executable physical capability
  without an adapter, conformance evidence, policy, and commissioning record.
- [ ] Build a first-workflow planner that maps a desired outcome to typed capability gaps without
  dispatching equipment.
- [ ] Add evidence ingestion for manuals, layouts, photographs, vendor data, and existing CAD. Record
  source, date, confidentiality, and confidence.
- [ ] Add context freshness checks. The agent must identify conflicting or stale shared facts before
  it changes executable configuration.
- [ ] Pilot onboarding with two independent users and two different laboratory types. A fresh agent
  must reconstruct the same shared state from the repository.

## 3. Read-only context and interface parity

- [ ] Add `opensdl context --json` without storage initialization, writes, reconciliation, or adapter
  startup.
- [ ] Add a read-only run-list command with state, workflow, revision, environment, and update time.
- [ ] Add structured capability, resource, event, and intervention queries with explicit consistency
  semantics.
- [ ] Align context, validation, submission, inspection, event query, and export across CLI, API, SDK,
  and MCP.
- [ ] Define one response envelope for success, denial, failure, timeout, cancellation, and
  intervention.
- [ ] Add interface-neutral tests that exercise the same controller and runtime path through each
  transport.
- [ ] Add stable revision and deployment identity to operational context.

## 4. Workflow development, simulation, and audit

- [ ] Add a machine-readable workflow planning result with capability gaps, resource needs, risks,
  assumptions, and test requirements.
- [ ] Add dry-run validation that resolves bindings, policy, resources, inputs, and side effects
  without dispatch.
- [ ] Expand deterministic fault plans for disconnects, bad data, delayed acknowledgement, resource
  contention, and restart.
- [ ] Add workflow fixtures for manual work, physical-compute combinations, sample custody, and
  characterization.
- [ ] Add simulation trace comparison so workflow changes can detect behavioral drift.
- [ ] Add typed run annotations, review findings, and audit exports.
- [ ] Add bounded background monitoring through current harness mechanisms after read-only run and
  event queries exist.
- [ ] Add typed intervention acknowledgement, resume, reconcile, hold, cancel, and abort behavior.
- [ ] Add campaign checkpoints, validity domains, uncertainty, and multi-fidelity strategy contracts.

## 5. User-specific digital twins and visualization

- [x] Define the `twin.yaml` v0alpha1 contract for coordinates, scene revision and digest, stable
  entities, anchors, and event-to-visual projection rules.
- [x] Reject duplicate stable references, unknown projection targets, unsafe scene paths, digest
  mismatches, invalid JSON pointers, ambiguous animation matches, unknown static transfer anchors,
  and incomplete action parameters.
- [ ] Retain content-addressed twin definitions and scene bytes with each run binding. Historical
  replay must not depend on the currently configured twin files.
- [ ] Extend the contract with typed provenance, dimensions, fidelity, registration error, joints,
  paths, and declared visual states.
- [x] Check the reference GLB's digest, required nodes, authored animation range, and Khronos
  validator result. Make its viewer stop when a declared scene-node binding is missing.
- [ ] Generalize GLB checks for custom laboratory scenes. Cross-check entity resources against the
  laboratory manifest and add a constrained unit vocabulary with actionable diagnostics.
- [ ] Build an on-demand `build-digital-twin` skill. It must generate one tailored Blender scene in
  the laboratory repository and must not pull from a framework model catalog.
- [x] Add a deterministic headless Blender build for the sole reference showcase. It writes Blender
  source, GLB, preview, animation, node inventory, motion checks, and the GLB digest.
- [x] Add required-node, deck-pitch, labware-count, pose-coupling, tip-state, liquid-state, reader-
  lid, Stacker-shuttle, access-door, and Heater-Shaker motion checks to the reference scene.
- [ ] Generalize render-inspect and geometry checks for generated laboratory scenes. Cover identity,
  bounds, scale, occlusion, placement, and declared provenance.
- [ ] Validate the binding against an on-demand scene in a generated test laboratory. Keep model
  assets in that laboratory repository. The framework's one reference showcase is the test fixture,
  not the start of an equipment catalog.
- [x] Project persisted run events into immutable, deterministic visual cues with stable
  identifiers.
- [x] Pin each configured run to its twin revision, canonical definition digest, and scene digest.
  Refuse projection when the current binding differs from the recorded binding.
- [x] Serve the verified scene, twin definition, projected run, and read-only viewer through the
  API.
- [x] Add a read-only Three.js viewer with orbit, zoom, play, pause, reset, timeline scrubbing, cue
  metadata, semantic highlights, transfers, authored GLB motion, and an exact-reference demo.
- [x] Rebuild the sole showcase as an original, real-scale Flex-class reconstruction with published
  equipment dimensions, a complete authored sequence, and spatial checks that run before export.
- [ ] Add entity selection and explicit proposed, simulated, live, disconnected, and stale states.
- [ ] Add scan and CAD ingestion with scale calibration, coordinate registration, decimation,
  confidentiality review, and unmapped-entity reporting.
- [ ] Add read-only live event projection after event-query and identity contracts mature.
- [ ] Add conversational plan-to-preview flow. Keep live execution as a separate typed submission.
- [ ] Evaluate robotics simulation for collision and kinematics. Treat Blender visualization as
  presentation rather than robotics proof.

## 6. Human work and physical integration

- [ ] Add queued human tasks with server-derived identity, witness, configurable evidence, expiry,
  reassignment, and acknowledgement.
- [ ] Add typed calibration records, validity intervals, traceability, and pre-run checks.
- [ ] Add a SiLA 2 reference adapter and conformance profile.
- [ ] Add a MADSci orchestration backend through the same capability contract.
- [ ] Add Bluesky event ingestion with durable event identity and replay behavior.
- [ ] Add a low-risk networked balance reference integration.
- [ ] Add hardware-in-the-loop tests that retain the simulator and public workflow contract.
- [ ] Define commissioning records for capability envelope, device revision, calibration, operator
  approval, and rollback.
- [ ] Test disconnect, timeout, cancellation, restart, resource conflict, ambiguous acknowledgement,
  and independent safe-state behavior before broad live use.

## 7. Compute, models, and scientific data

- [ ] Add bounded local subprocess execution with declared inputs, outputs, environment, and limits.
- [ ] Add a container executor with image digest, resource bounds, artifact capture, and cancellation.
- [ ] Add a Slurm backend with durable job identity, resumption, cancellation, and accounting.
- [ ] Add an S3-compatible artifact store with integrity, retention, and failure tests.
- [ ] Add a Tiled data adapter and define dataset identity across run exports.
- [ ] Add a model registry with version, training evidence, validity domain, uncertainty, and
  checkpoint lineage.
- [ ] Add a materials workflow that combines physical work with atomistic or continuum compute.
- [ ] Add reusable interfaces for external characterization providers.

## 8. Shared operation and deployment

- [ ] Deploy one shared simulator controller with persistent PostgreSQL storage.
- [ ] Add authentication, scoped service identities, and server-derived actor attribution.
- [ ] Add trustworthy multi-user leases, run ownership, and concurrent submission tests.
- [ ] Add pluggable policy providers and signed policy revision evidence.
- [ ] Add PostgreSQL CI, migrations across released versions, backup, restore, and disaster tests.
- [ ] Add OpenTelemetry traces and metrics tied to run, task, adapter, and deployment identity.
- [ ] Add typed deployment inspect, health, revision, reconcile, rollback, and audit operations.
- [ ] Add a deployment view only when the typed operations exist. Keep it optional.
- [ ] Add high-availability guidance and failure tests for supported deployment profiles.
- [ ] Add a signed adapter, skill, and conformance-result promotion process.

## 9. Distributed laboratories

- [ ] Broker work across multiple sites without losing actor, sample, or artifact identity.
- [ ] Add sample custody and transfer evidence across facility boundaries.
- [ ] Add federated artifact metadata and controlled replication.
- [ ] Add distributed scheduling with site policy, resource availability, and recovery.
- [ ] Add cross-site replay and incident evidence.
- [ ] Demonstrate one public workflow across two independent laboratories and different backends.

## 10. Optional custom harness

- [ ] Measure gaps in normal Codex, Claude Code, and other repository-agent workflows before building
  a custom client.
- [ ] Define the custom harness as a client of the same API or MCP contracts.
- [ ] Keep user conversations private and outside shared operational authority.
- [ ] Pass the same interface-neutral tests through standard and custom harnesses.
- [ ] Prove that a harness restart loses no operational state and cannot expand policy authority.

## Laboratory-repository work

Framework tasks stay on this page. Each laboratory repository records its own equipment, workflows,
context, integration gaps, model work, and deployment choices in `docs/lab/setup-plan.md`. This
split keeps OpenSDL small while each laboratory grows around its real requirements.
