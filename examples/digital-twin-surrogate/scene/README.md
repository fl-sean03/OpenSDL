# Surrogate-cell scene

`build_scene.py` creates the complete reference laboratory in Blender background mode. The script
builds the geometry from scratch, animates one workflow, checks motion checkpoints, runs the spatial
invariants in `check_scene.py`, saves the editable source, and exports the viewer asset. A failed
check stops the build before the export.

The scene uses real scale and published equipment behavior. It remains a visualization surrogate;
read [SOURCES.md](SOURCES.md) for provenance and reuse boundaries.

## What is built

The build has four layers, in this order:

| Layer | Function | What it is |
|---|---|---|
| Plant space | `build_room`, `build_service_door` | Sealed resin floor with saw-cut movement joints, four plain panel walls, an exposed soffit carrying linear battens, a cable ladder and a duct run, a wall panel board, and one flush steel service door |
| Frame | `build_frame`, `build_decks`, `build_service_deck` | The machine itself: nine 45-series T-slot uprights on levelling feet through anchored floor plates, five tied working planes, corner gussets and end-tower diagonals, the hard-anodised process plate at 1135 mm on its own carriers, the fluid service plate with its bund, and the work-light bars on the top tie |
| Cell | `build_stations`, `build_gantry`, the module builders | The transport runway landed straight on the end towers, the bridge, gripper and pipetting head, the drag chain that follows the carriage, and the plate hotels, Heater-Shaker, reader, tip rack, reservoir and labware on the deck |
| Machine services | `build_controls`, `build_compute`, `build_fluidics`, `build_waste_column`, `build_transfer_port`, `build_machine_services` | Everything packed into the volume under the deck: the controls cabinet with its louvred door and main isolator, the open drive bank on galvanised backplate, the rack running the campaign with its state on one display, bulk reagent supply and pump, the tip chute and waste column, the single interlocked load and unload port, and the trunking, conduit, beacon and emergency stops |

There is no casework, no worktop, no operator position and no room dressing. Every height in the
machine is set by the transport: 1135 mm is where the bridge can put a plate down, and the mounting
plane at 920 mm exists only so the tall hotels present their nests level with that deck. The frame
is open on the front and both ends; the only panels are the splash guard behind the liquid handling
and the surround at the transfer port, both of which a process needs.

Two rules hold this together and are worth keeping. Equipment sits on its own feet at its real
height; nothing is raised on a plinth for the camera. And the only text in the scene is the text a
real machine carries - the nameplate and asset tag, the emergency-stop marking, the load port tag,
and the barcode on the plate. Which station is which is the twin viewer's job, through anchors and
cues, not baked signage.

The machine lights its own work, the way a real workcell does. `build_camera_and_lighting` places
one area light per ceiling batten at that fixture's own size and aperture, and one matched to every
fixture on the frame: the two work-light bars on the top tie, the strip under the deck lip, the
strip under the front mounting rail, the four vertical bay strips on the front uprights, and the
magazine lighting in both hotels. Fixture and lamp are declared from the same constants, so they
cannot drift apart.

Two decisions carry the mood. The room is lit **cool** and the machine is lit **warm**, which is
what gives the frame its own light instead of leaving it a grey object in a grey volume. And the
room ambient is deliberately below the machine's own level: a cell that runs unattended has no
reason to be lit for an occupant, so the machine is the brightest thing in the volume and the
polished resin floor returns it. The world background is a soft cool grey rather than black,
because a black world has no ambient at all and every shadow crushes. `configure_eevee` turns on the raytraced passes this needs -
screen-space raytracing, fast global illumination, and multi-ray shadows - because a volume lit only
by its own fixtures has no ambient occlusion or contact shadow without them, and objects without
contact shadows read as placed near the floor rather than standing on it. Every property is assigned
in its own `try` and read back on stderr as `EEVEE APPLIED`, so a rejected value is visible rather
than silently producing a differently-rendered scene.

## Reproducibility

The glTF export is byte-reproducible for a given Blender version. Rebuilding with the version
recorded in `assets/node-inventory.json` under `generator.blender` reproduces `surrogate-cell.glb`,
`node-inventory.json`, and `motion-validation.json` exactly, so the committed digests are a
reproducibility claim rather than a self-assertion.

`tests/test_scene_reproducibility.py` performs that rebuild in a temporary directory and compares
the bytes. It skips, with the reason reported, when Blender is absent or its version differs from
the recorded generator. A different Blender version is expected to produce different bytes;
regenerate the assets and commit the new digests when the toolchain moves.

`assets/surrogate-cell.blend` is excluded from the comparison. Blender embeds session state in a
saved file, so it is not byte-stable across runs.

## Outputs

| Path | Contents |
|---|---|
| `assets/surrogate-cell.blend` | Editable Blender source generated by the script |
| `assets/surrogate-cell.glb` | Binary glTF scene for the read-only viewer |
| `assets/preview.png` | Still image at the requested frame and resolution |
| `assets/node-inventory.json` | Exported node names, coordinate frame, required bindings, source basis, generating Blender version, and GLB digest |
| `assets/motion-validation.json` | Machine-readable motion and placement check results, and GLB digest |
| `assets/camera-poses.json` | The named camera rig: eye, look point, lens, aperture, frame, and per-pose hide list |
| `renders/opensdl-surrogate-cell.mp4` | Committed H.264 animation of the authored 40-second sequence |

The animation spans frames 1–960 at 24 frames per second. Its duration is 40 seconds.

## Build the source and GLB

Run this command from the OpenSDL repository root:

```bash
blender -b --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/build_scene.py
```

The default build uses Eevee render settings, saves frame 548 in the Blender file, and exports the
GLB. A failed motion check stops the build before any of that. Both reports are written after the
export, so each one records the digest of the GLB it describes.

The current validation covers 85 conditions. Seventy-one of them are scalar checks in
`build_scene.py`: slot pitch, required labware counts, plate and reader-lid checkpoints, gripper
coupling, tip attachment, liquid fill state, Stacker shuttles, clamp clearance, a 1 mm
Heater-Shaker orbit radius, and zero plate yaw. The remaining fourteen come from `check_scene.py`
and compare bodies to each other rather than to a number.

## Render a still

Use Cycles for the presentation still:

```bash
blender -b --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/build_scene.py -- \
  --render-still \
  --engine cycles \
  --samples 64 \
  --resolution 1280x720 \
  --frame 548
```

Use `--engine eevee` for a faster review render. The command writes `assets/preview.png`.

## Render the named camera poses

The scene carries a named camera rig rather than auto-framing itself: an establishing view of the
machine from the aisle, a raised square-on view that makes the closed loop legible end to end, a
fixed pose for the animation, a view of the compute rack and the campaign state on its display, a
view of the controls cabinet and of the open drive bank, one detail pose per station, a view of the
transfer port, and two gripper poses. Each pose states its eye, look point, lens, aperture, the
frame it reads at, and the object-name prefixes it hides. Every pose stands inside the room, so the
walls behind the camera cull themselves and a hide list is only ever used to clear a near object out
of a detail view; hiding a wall a pose can see would render the void behind it.
Renders land in `renders/poses/`, which is not committed.

```bash
blender -b --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/build_scene.py -- \
  --render-poses --engine eevee --resolution 1280x720
```

Pass `--poses hero,gripper-closed` to render a subset. `assets/camera-poses.json` publishes the same
rig so the docs and any later render frame the line the same way.

## Render the animation

`ffmpeg` must be available on `PATH`:

```bash
blender -b --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/build_scene.py -- \
  --render-animation \
  --engine eevee \
  --resolution 1280x720
```

Blender first writes the 960 PNG frames under `renders/frames/`. The script then encodes H.264 with
a YUV 4:2:0 pixel format and fast-start metadata. It removes the temporary frames after a successful
encode.

Use `--no-export` during render-only iteration when the checked GLB must remain unchanged.

## Check the binding after a rebuild

The twin definition pins the GLB digest. Both build reports record the digest of the exported GLB,
so a report left over from an earlier scene cannot pass review. After an intentional scene rebuild:

1. Inspect `assets/preview.png` and the animation.
2. Inspect `assets/motion-validation.json` and require `passed: true`.
3. Review `assets/node-inventory.json` for required nodes and source basis.
4. Compute the GLB digest.
5. Update `../twin.yaml` with the reviewed digest.
6. Run the OpenSDL twin validator.

```bash
sha256sum examples/digital-twin-surrogate/scene/assets/surrogate-cell.glb
uv run --locked opensdl twin validate \
  examples/digital-twin-surrogate/twin.yaml
```

The viewer binds these required nodes:

```text
CellRoot
SampleCarrier
RobotCarriage
DispenserHead
MixerRotor
ColorimeterHousing
ColorimeterDoor
Anchor_Input
Anchor_Dispenser
Anchor_Mixer
Anchor_Colorimeter
Anchor_Output
```

Do not rename them without updating `twin.yaml`, the viewer bindings, the inventory check, and the
related tests.

## Motion represented

The authored animation includes:

- input and output Stacker shuttle motion;
- gripper pickup, safe-Z travel, placement, and release;
- two 8-channel tip-pickup, dispense, and tip-drop cycles;
- synchronized liquid fill state;
- plate transfer to and from the Heater-Shaker;
- a clockwise 2 mm-diameter orbital mixing translation without plate yaw;
- plate-reader lid staging, closure, read indication, and reopening; and
- a carriage that steps clear along the bridge while the pipetting head owns the dispensing station.

The animation camera is fixed at the `animation` pose in `assets/camera-poses.json`. It does not
move or zoom, so the whole line stays in frame for the full cycle.

The GLB keeps this authored 960-frame motion. `twin.yaml` maps each projected transfer or operation
cue to its matching frame range through `animationTimeline`.

`validate_motion` confirms authored transforms and timing. `check_scene.py` adds the relationships
between bodies:

- **carry rigidity** — whenever the plate or the reader lid moves, it moves with the body carrying
  it: the gripper carriage, the shaker platform, or a Stacker shuttle. Carried keyframes are derived
  from the carrier pose in `build_scene.py`, so the two cannot drift apart;
- **grip contact** — while the jaws hold a closed width, both jaw assemblies bracket that payload
  within 2 mm on every axis, and no payload rides the carriage with the jaws open;
- **interpenetration** — moving assemblies are tested against the casework, the workstation chassis
  and its deck, the gantry portal, the modules, and the labware with a 0.25 mm per-body contact
  margin. Legitimate contact is declared per pair, per frame window, and where useful per body, in
  `ALLOWED_CONTACTS`;
- **gripper mechanism continuity** — each paddle reaches the carriage through an unbroken chain of
  bodies (pad, paddle, finger, carrier, cross-rail) that stays in contact at every frame and
  therefore at every authored jaw width, and neither carrier runs off the end of its rail. Carry
  rigidity and grip contact both pass for a gripper whose paddles are correctly parented and
  correctly placed while nothing at all spans the distance between them and the arm; that is the
  state this scene shipped in, and it read as two bars floating beside the carriage.

Run the invariants against a built file without rebuilding it:

```bash
blender -b examples/digital-twin-surrogate/scene/assets/surrogate-cell.blend \
  --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/check_scene.py -- --step 2
```

They still do not test forces, liquid physics, or equipment safety.
