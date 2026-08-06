# Lab-specific digital twins

OpenSDL has an alpha contract for binding a laboratory scene to semantic resources and persisted
run events. The framework also includes one complete surrogate-cell showcase that tests the
contract, projection path, and viewer.

A user or their agent still builds each real laboratory scene on demand. That source belongs in the
laboratory repository. OpenSDL does not ship an equipment-model catalog or accumulate user scenes.

## Current alpha

The current implementation provides:

- a versioned, engine-neutral `twin.yaml` definition;
- a safe relative scene path with a required SHA-256 digest;
- stable entity and anchor bindings;
- an optional `animationTimeline` that maps visual cues to authored GLB frame ranges;
- rules that project persisted task events into immutable visual cues;
- CLI commands to validate a definition and project one stored run;
- API endpoints for the definition, verified GLB, and projected run; and
- a read-only Three.js viewer with local demo playback and stored-run replay.

The framework's reference scene proves this integration path. It does not establish an automated
modeling service for arbitrary laboratories.

The reference is an original, real-scale Flex-class reconstruction based on published dimensions
and operating behavior. Its 49-second sequence spans 1176 frames at 24 frames per second and covers
Stacker presentation, gripper transfers, pipetting, orbital mixing, plate reading, and output.

## Authoring and runtime formats

Blender is the default 3D authoring pipeline. It supports headless scripting, deterministic naming,
custom properties, animation, and render-based review. See the
[Blender glTF documentation](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html).

[glTF](https://www.khronos.org/gltf/) is the runtime delivery format. A binary GLB packages the
scene for the viewer. It is neither the semantic twin nor the editable source of truth.

Manufacturing CAD can supply source geometry when a laboratory has the files and reuse rights.
OpenSDL does not require a specific CAD system. The laboratory repository records the source,
license, confidentiality, scale, and registration evidence for every imported asset.

## Ownership model

| Layer | Authority | Examples |
|---|---|---|
| Semantic laboratory | OpenSDL contracts and runtime records | Resources, capabilities, workflows, runs, tasks, events |
| Visual source | Laboratory-repository Blender files and scripts | Geometry, materials, rigs, paths, cameras |
| Binding | Versioned `twin.yaml` | Coordinate frame, scene digest, entities, anchors, projection rules |
| Viewer projection | Verified GLB and immutable visual cues | Highlights, transfers, semantic motion, displayed properties |

The visual source derives from laboratory evidence. It cannot create a capability, commission an
instrument, or report physical state. The viewer has no equipment-command endpoint.

## Repository boundary

The OpenSDL framework contains exactly one reference showcase under
`examples/digital-twin-surrogate/`. It exists to test and explain the public contract end to end.
It is not a reusable model catalog.

Each laboratory keeps its tailored model in its own repository, for example:

```text
digital-twin/
├── twin.yaml
├── src/
│   └── build_scene.py
├── source/
│   └── lab.blend
├── exports/
│   └── lab.glb
├── renders/
├── readback/
└── tests/
```

Git stores scripts, mappings, and approved source files. A lab can use artifact storage or Git LFS
for larger assets. Credentials, private endpoints, and unapproved facility details stay outside the
public framework.

## Binding contract

The v0alpha1 definition contains:

- `version` and a scene `revision`;
- coordinate unit, handedness, up axis, and origin;
- a definition-relative GLB path and SHA-256 digest;
- stable entities with glTF node names and optional OpenSDL resource identifiers;
- named anchors with coordinates and optional scene nodes;
- an optional authored-animation frame rate, frame range, and cue bindings; and
- event matches with restricted visual actions and parameters.

The current actions are `highlight`, `transfer`, `play_clip`, and `set_property`. Projection rules
can read values from a persisted event envelope through validated JSON Pointers.

Each animation binding selects one visual action and a nonempty parameter match. It maps the cue to
an absolute frame range in the authored GLB timeline. The viewer scrubs the GLB animation clock to
that range as the cue advances.

The model rejects duplicate stable references and ambiguous animation matches. It also rejects
unknown projection targets, invalid static transfer anchors, unsafe scene paths, invalid pointers,
and incomplete action parameters. The loader confines the scene path to the definition directory.
It recalculates the scene digest on every scene read. The browser calculates the digest again before
it parses the GLB.

The viewer stops loading when a declared entity or anchor node is absent. It does not silently run
the reference animation against an incomplete binding.

The reference build checks its required nodes and writes a machine-readable node inventory. Its
tests also check the GLB structure and authored animation range. General validation for arbitrary
laboratory scenes and resource-to-manifest validation remain open work. Typed provenance,
dimensions, fidelity, registration error, joints, and paths also remain contract extensions.

## Build flow for one laboratory

1. Read the lab context, inventory, setup plan, manifest, and target workflow.
2. Collect approved dimensions, photographs, scans, manuals, CAD, and layout evidence.
3. Record each source and its evidence state, license, confidentiality, and confidence.
4. Build a low-detail layout at the declared scale.
5. Bind scene entities and anchors to stable OpenSDL identifiers.
6. Render a cheap preview and inspect it.
7. Fix scale, placement, occlusion, identity, and motion defects.
8. Add detail only where the intended preview or review needs it.
9. Export the GLB, preview, animation, and scene inventory.
10. Validate the binding, scene digest, required nodes, motion checkpoints, and output files.

OpenSDL does not yet automate this full procedure. A user or agent can perform it with Blender now.
The planned `build-digital-twin` skill will make the procedure repeatable across laboratory repos.

## Persisted-run projection

OpenSDL sorts stored events deterministically and applies matching projection rules. Each output cue
records its source event, run, task, capability, time, phase, action, target, and parameters. Cue
identifiers include the definition revision, so a scene revision produces a distinct projection.

When a configured controller creates a run, its `RunCreated` event records the current twin
revision, canonical definition digest, and scene digest. Projection compares that binding with the
currently configured twin and refuses a mismatch or missing pin.

This alpha does not retain historical twin definitions or scene bytes. A stored run can be replayed
only while its exact definition and scene binding remains current. Content-addressed definition and
scene snapshots are required for replay across later twin revisions.

### What a projection cannot show

Projection is task-shaped. A cue carries a task and the capability that ran it, so a projection rule
can only match an event type that has a task identifier. Those are the `Task*` events. The
`Campaign*` and `Run*` types have none, and `project_events` raises rather than emitting a task-less
cue if a rule is written against one. The reference twin's rules all match `Task*` types for that
reason.

The consequence is worth stating plainly, because the name invites the opposite assumption. **The
twin shows the execute half of a closed loop and not the decide half.** A campaign converging, an
optimizer proposing the next point, an objective improving, and a run's own lifecycle are outside
what a scene can display today. A user who expects to watch the laboratory think will see only the
laboratory act.

This is a property of the cue contract rather than a missing feature, so widening it is a contract
change and not a scene change.

The CLI exposes the current path:

```bash
opensdl twin validate digital-twin/twin.yaml
opensdl twin project RUN_ID --manifest opensdl.yaml
```

The API exposes equivalent read-only data:

```text
GET /twin
GET /twin/scene.glb
GET /twin/runs/{run_id}
GET /viewer
GET /viewer/{asset_path}
```

The viewer can play, pause, reset, scrub, orbit, and zoom. It displays the current capability,
visual action, cue sequence, and projected sample properties. Without a run identifier, the exact
included reference revision and scene digest use the deterministic demonstration. Another
configured twin opens without cues until the user selects a compatible stored run.

## Conversational use

The workflow stays inside a normal agent conversation:

1. The user describes a laboratory operation or asks to preview a workflow.
2. The agent builds or updates the laboratory-specific scene when needed.
3. OpenSDL validates and runs the workflow through a simulation adapter.
4. OpenSDL projects the stored run events through the registered twin definition.
5. The user inspects the viewer and revises the workflow or layout.
6. A physical request uses a separate typed submission through normal policy and adapter controls.

Future conversational planning can generate a candidate workflow and preview it. Preview must stay
separate from equipment dispatch.

## Evidence limits

Blender and the viewer provide visual evidence only. They do not prove:

- robot reachability, collision clearance, force limits, or kinematics;
- liquid-transfer accuracy, thermal behavior, mixing performance, or measurement quality;
- equipment identity, calibration, commissioning, connectivity, or acknowledgement;
- safe placement, guarding, ventilation, electrical service, or regulatory compliance; or
- agreement between a live laboratory and the displayed state.

Use robotics simulation, engineering analysis, equipment tests, and commissioning records for those
claims. Keep the Blender scene useful as a workflow surrogate without treating appearance as
physical evidence.

## Next work

1. Retain content-addressed twin definitions and scene bytes for historical replay.
2. Add a lab-local `build-digital-twin` skill and generated-lab test.
3. Extend provenance, geometry, registration, joint, and path metadata.
4. Cross-check arbitrary GLB nodes and manifest resources during validation.
5. Add entity selection and explicit proposed, simulated, live, disconnected, and stale states.
6. Add scan and CAD ingestion with scale and confidentiality checks.
7. Add read-only live projection after event identity and staleness contracts mature.
8. Evaluate a robotics simulator for kinematic and collision evidence.
