# Digital-twin surrogate laboratory

This is OpenSDL's complete digital-twin reference example. A deterministic simulation adapter runs
one formulation workflow, persisted events become visual cues, and a read-only viewer applies those
cues to a detailed 3D laboratory cell.

![OpenSDL Flex-class surrogate cell](scene/assets/preview.png)

The scene is a full-scale, original reconstruction of a real Flex-class liquid-handling setup. It
uses published dimensions and operating behavior for the robot, gripper, 8-channel pipette,
Stackers, Heater-Shaker, plate reader, and labware. It includes no manufacturer CAD, product images,
textures, logos, or copied meshes. See [scene/SOURCES.md](scene/SOURCES.md) for provenance.

This is the framework's only complete scene. It proves the public contracts and viewer path; it is
not the first entry in an equipment-model catalog. Each laboratory builds its own tailored scene in
its own repository.

## What the cell does

The adapter-neutral workflow uses four semantic capabilities:

1. `cell.transfer_labware` moves the plate from input to dispensing.
2. `cell.dispense` adds 40 µL of reagent A and 60 µL of reagent B to each of 96 wells.
3. `cell.transfer_labware` moves the plate to mixing.
4. `cell.mix` applies the declared 800 rpm, 20-second operation.
5. `cell.transfer_labware` moves the plate to characterization.
6. `cell.characterize` returns a deterministic normalized response.
7. `cell.transfer_labware` moves the plate to output.

The 40-second scene animation expands those tasks into visible equipment actions. The input Stacker
presents the plate, the gripper transfers it, and the 8-channel head illustrates two pipetting
passes. The Heater-Shaker uses a 2 mm-diameter orbital translation with no plate yaw. The gripper
moves the reader lid between the reader and its caddy in D2, then sends the plate to the output
Stacker.

The animation timing illustrates the sequence. It does not reproduce device cycle times.

## Deck layout

Rows run from A at the rear to D at the front. Columns 1–3 form the working deck. Column 4 sits
outside the gantry crossbeam and the side glazing, so only the Stacker shuttles reach it.

| Slot | Reference-scene use |
|---|---|
| A1 | 12-well reagent reservoir |
| A2 | 200 µL tip rack |
| A3 | Input presentation position |
| A4 | Input Stacker and shuttle |
| B1 | 96-well formulation plate during dispensing |
| B3 | Output presentation position |
| B4 | Output Stacker and shuttle |
| C1 | Heater-Shaker GEN1 with flat-plate adapter |
| D1 | Movable trash bin |
| D2 | Plate-reader lid caddy |
| D3 | Absorbance plate reader |

The scene uses 164 mm horizontal slot pitch, 107 mm vertical pitch, and ANSI/SLAS labware scale.

## Prerequisites

Install the locked Python workspace from the repository root:

```bash
uv sync --locked --all-packages --group dev
```

Scene generation uses Blender in background mode. MP4 output also requires `ffmpeg`. The viewer's
development workflow requires Node.js 22.12 or newer. The checked-in scene was built with Blender
5.2.

The example adapter is not a root workspace member. Commands that load the laboratory manifest add
it as a temporary editable overlay and leave `uv.lock` unchanged.

## Build and check the 3D scene

Generate the Blender source, GLB, node inventory, and motion report:

```bash
blender -b --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/build_scene.py
```

The script checks required nodes and 70 motion, placement, labware, tip, liquid, lid, and Stacker
conditions before it writes the final outputs. Read [scene/README.md](scene/README.md) for render
options and file details.

A deliberate rebuild can change the GLB digest. Review the new output, then update `scene.sha256` in
`twin.yaml` to the value reported by:

```bash
sha256sum examples/digital-twin-surrogate/scene/assets/surrogate-cell.glb
```

Validate the twin definition and digest:

```bash
uv run --locked opensdl twin validate \
  examples/digital-twin-surrogate/twin.yaml
```

## Validate and run the workflow

Validate the manifest and workflow schemas:

```bash
uv run --locked opensdl validate \
  examples/digital-twin-surrogate/opensdl.yaml \
  --workflow examples/digital-twin-surrogate/workflow.yaml
```

Run the formulation with a stable identifier:

```bash
uv run --locked \
  --with-editable ./examples/digital-twin-surrogate/adapter \
  opensdl run examples/digital-twin-surrogate/workflow.yaml \
  --manifest examples/digital-twin-surrogate/opensdl.yaml \
  --inputs @examples/digital-twin-surrogate/inputs.json \
  --operator-id operator/showcase \
  --run-id surrogate-showcase-001
```

The run finishes with `showcase-plate-001` at `output`, `100.0 µL` per well (`9,600.0 µL`
aggregate), and a deterministic dimensionless characterization value of `0.56`. OpenSDL writes
runtime records and artifacts below `examples/digital-twin-surrogate/.opensdl/`.

Project the persisted events into visual cues:

```bash
uv run --locked \
  --with-editable ./examples/digital-twin-surrogate/adapter \
  opensdl twin project surrogate-showcase-001 \
  --manifest examples/digital-twin-surrogate/opensdl.yaml
```

The run records the current twin revision, definition digest, and scene digest in its `RunCreated`
event. Projection refuses a run whose recorded binding differs from the configured twin. The alpha
does not retain historical definition or scene snapshots, so replay requires that exact binding to
remain current.

Run the example tests:

```bash
uv run --locked \
  --with-editable ./examples/digital-twin-surrogate/adapter \
  pytest examples/digital-twin-surrogate/tests
```

These tests cover adapter conformance, deterministic state and failures, the complete workflow,
semantic parity with a fake physical adapter, and the manifest swap boundary.

## Open the viewer

Build the checked-in viewer:

```bash
cd examples/digital-twin-surrogate/viewer
npm ci
npm test
npm run lint
npm run typecheck
npm run build
cd ../../..
```

Start the API with the example adapter available:

```bash
uv run --locked \
  --with-editable ./examples/digital-twin-surrogate/adapter \
  opensdl serve-api \
  --manifest examples/digital-twin-surrogate/opensdl.yaml \
  --host 127.0.0.1 \
  --port 8000
```

Open `http://127.0.0.1:8000/viewer?run=surrogate-showcase-001`. The viewer reads the twin definition,
GLB, and projected cue sequence from the API. The API recalculates the GLB digest for every scene
request. The browser checks the downloaded bytes again before parsing them. Missing declared scene
nodes stop loading.

Playback scrubs the authored 960-frame GLB timeline through the frame ranges declared in
`animationTimeline`. The viewer can orbit, zoom, play, pause, reset, and scrub. It cannot send
equipment commands or change runtime state.

For a scene-only demonstration, run `npm run dev` from `viewer/` and open the displayed `/viewer/`
URL. If the API is unavailable, the development server uses the included reference definition,
scene, and deterministic cue sequence. An API-hosted twin receives these reference cues only when
its revision and scene digest match the included showcase. Any other configured twin opens with no
run cues until the URL names a compatible persisted run.

## Physical adapter swap

[`opensdl.physical-example.yaml`](opensdl.physical-example.yaml) documents the deployment boundary.
Compared with [`opensdl.yaml`](opensdl.yaml), only the environment and adapter binding change. The
workflow, capability identifiers, logical adapter name, resources, and policy shape remain stable.

The repository does not supply the `qualified-physical-cell` plugin. A deployment must implement
and qualify that adapter, review limits and failure semantics, commission its equipment, and apply
site policy before physical execution.

## Limits

The simulation adapter is a deterministic state machine. The Blender scene and viewer are workflow
visualizations. Together they do not establish:

- reachability, collision avoidance, kinematics, force limits, or guarding;
- pipetting accuracy, mixing performance, thermal response, or reader accuracy;
- equipment calibration, connectivity, commissioning, or physical readiness; or
- safety integrity, regulatory compliance, or live-state agreement.

Use equipment tests, robotics simulation, engineering analysis, and commissioning evidence for
those claims.

## Files

- `capabilities/`: vendor-neutral capability cards;
- `adapter/`: deterministic example-local simulation plugin;
- `workflow.yaml` and `inputs.json`: representative operation and inputs;
- `opensdl.yaml`: runnable simulation manifest;
- `opensdl.physical-example.yaml`: non-runnable physical binding example;
- `twin.yaml`: scene binding and event projection rules;
- `scene/`: procedural source, generated assets, validation output, and renders;
- `viewer/`: read-only Three.js client and built static site; and
- `tests/`: focused conformance, parity, manifest, and end-to-end tests.
