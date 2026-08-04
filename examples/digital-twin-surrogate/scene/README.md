# Surrogate-cell scene

`build_scene.py` creates the complete reference laboratory in Blender background mode. The script
builds the geometry from scratch, animates one workflow, checks motion checkpoints, runs the spatial
invariants in `check_scene.py`, saves the editable source, and exports the viewer asset. A failed
check stops the build before the export.

The scene uses real scale and published equipment behavior. It remains a visualization surrogate;
read [SOURCES.md](SOURCES.md) for provenance and reuse boundaries.

## Naming conventions

These are the definitive terms. Every node name, entity id and anchor id in this scene and in
`../twin.yaml` is built from them, and a new part is named by finding its row here rather than by
inventing a word for it.

| Concept | Term | Node naming | In this scene |
|---|---|---|---|
| the whole machine | **cell** | `CellRoot` | `CellRoot` |
| the single transport carriage | **mover** | `Mover`, `Mover*` | `Mover`, `MoverRail`, `MoverBridge`, `MoverCoupler`, `MoverChain` |
| interchangeable tooling | **head** | `<Tool>Head` | `GripperHead`, `PipetteHead` |
| where an idle head parks | **dock** | `HeadDock_<Tool>` | `HeadDock_Gripper`, `HeadDock_Pipette` |
| a work location | **station** | `Station_<Verb>` | `Station_Input`, `Station_Dispense`, `Station_Mix`, `Station_Characterize`, `Station_Output` |
| a labware position in a station | **slot** | `Slot_<Name>` | `Slot_Stage`, `Slot_Tips`, `Slot_Reader`, `Slot_DoorDock` |
| a plate magazine | **hotel** | `Hotel_<Role>` | `Hotel_Input`, `Hotel_Output` |
| the labware being processed | **carrier** | `<Kind>Carrier` | `SampleCarrier` |
| a semantic workflow point | **anchor** | `Anchor_<Verb>` | `Anchor_Input`, `Anchor_Dispense`, `Anchor_Mix`, `Anchor_Characterize`, `Anchor_Output` |

Three rules go with the table:

- **Stations, anchors and workflow locations take the capability verb**, not a device noun:
  `transfer`, `dispense`, `mix`, `characterize`. The reader station used to be called `characterizer`
  by its anchor id, `Anchor_Colorimeter` by its node, `plate-reader` by its entity id and
  `ColorimeterHousing` by its geometry - four words for one station. The capability that drives it is
  `cell-characterize`, so **characterize** is the word, and the equipment that performs it is the
  `characterizer`.
- **Node names are `PascalCase`; ids are `lower-kebab-case`.** `Anchor_Dispense` is the node,
  `dispense` is the anchor id and the workflow location. `Slot_TipWaste` is the node, `tip-waste` is
  the slot id.
- **"Bit" is not a word in this repository.** Interchangeable tooling is a *head*. The term was
  chosen against `bit` because this is a software repository and `bit` is already taken.

## What is built

The build has four layers, in this order:

| Layer | Function | What it is |
|---|---|---|
| Plant space | `build_room`, `build_service_door` | Sealed resin floor with saw-cut movement joints, four plain panel walls, an exposed soffit carrying linear battens, a cable ladder and a duct run, a wall panel board, and one flush steel service door |
| Frame | `build_frame`, `build_decks`, `build_service_deck` | The machine itself: nine 45-series T-slot uprights on levelling feet through anchored floor plates, five tied working planes, corner gussets and end-tower diagonals, the hard-anodised process plate at 1135 mm on its own carriers, the fluid service plate with its bund, and the work-light bars on the top tie |
| Cell | `build_stations`, `build_transport`, the module builders | The transport runway landed straight on the end towers, the bridge, the one mover and its changer, the two interchangeable heads and the two docks they wait in, the drag chain that follows the mover, and the plate hotels, mixer, reader, tip rack, reservoir and labware on the deck |
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
| `assets/preview.png` | Still image from the `still` pose at the requested frame and resolution |
| `assets/node-inventory.json` | Exported node names, coordinate frame, required bindings, source basis, generating Blender version, and GLB digest |
| `assets/motion-validation.json` | Machine-readable motion and placement check results, and GLB digest |
| `assets/camera-poses.json` | The named still poses and the animation shot list: eye, look point, lens, aperture, frame, and per-pose hide list |
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

The current validation covers 103 conditions. Eighty-four of them are scalar checks in
`build_scene.py`: slot pitch, required labware counts, plate and reader-door checkpoints, grip
alignment, head dock poses and head-to-mover tracking, tip attachment, liquid fill state, hotel
shuttles, clamp clearance, a 1 mm mixer orbit radius, and zero plate yaw. The remaining nineteen
come from `check_scene.py` and compare bodies to each other rather than to a number.

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

The preview is a portrait of the machine rather than a frame of the film, so it is shot from the
`still` pose with the choreography suspended and restored afterwards. `--frame` chooses which state
of the workflow it catches, not where the camera stands.

## Render the named camera poses

The scene carries a named camera rig rather than auto-framing itself: an establishing view of the
machine from the aisle, a raised square-on view that makes the closed loop legible end to end, the
whole-machine `still` the preview is shot from, a view of the compute rack and the campaign state on
its display, a view of the controls cabinet and of the open drive bank, one detail pose per station,
a view of the transfer port, two gripper poses, and three poses on the head docks and the change
itself. Each pose states its eye, look point, lens, aperture, the frame it
reads at, and the object-name prefixes it hides. Every pose stands inside the room, so the walls
behind the camera cull themselves and a hide list is only ever used to clear a near object out of a
detail view; hiding a wall a pose can see would render the void behind it.
Renders land in `renders/poses/`, which is not committed.

These are still poses. The animation is shot by a separate list, `CAMERA_SHOTS`, described under
[Camera choreography](#camera-choreography) below. Rendering the poses suspends the choreography and
rebuilds it afterwards, so the two cannot fight over the camera.

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

## Camera choreography

The 40-second cycle is shot rather than watched. `CAMERA_SHOTS` in `build_scene.py` is six moving
takes that tile frames 1–960 exactly. Every one of them moves inside itself, so no framing is ever a
held still, and every one of them is between five and eight seconds long:

| Frames | Length | Shot | What it is |
|---|---|---|---|
| 1–150 | 6.25 s | `establish-and-load` | Wide from the front right of the aisle, trucking left across the machine and zooming in, arriving on the input end as the plate comes out of the hotel and goes to the dispense stage |
| 151–330 | 7.50 s | `head-change-and-tips` | Head change A, close: the mover flies into the gripper dock, seats the head, rises away empty and crosses to the pipette dock; the camera tracks it, then follows the pipetting head to the tip rack, the reservoir and the first fill |
| 331–498 | 7.00 s | `reverse-and-fill` | Reverse angle down the length of the machine from the output end, travelling the whole aisle and pushing in through the tip drop and the second tip pickup until the nozzles entering the wells fill the frame |
| 499–672 | 7.25 s | `head-change-b-and-to-mix` | Head change B and the transfer after it in one travelling take from the right: the mover parks the pipetting head, picks the gripper back up, lifts the plate off the dispense stage and lands it on the mixer |
| 673–800 | 5.33 s | `mix-and-cross` | Tight on the Heater-Shaker from the left through the clamp close and the orbit, arcing right as it runs, then travelling one station along with the plate and settling on the reader |
| 801–960 | 6.67 s | `read-and-out` | Wide from the right while the door crosses between the reader rows, in to the longest lens in the film while the reader indicates, out again with the plate to the output hotel, then a pull back to the closing wide |

Six shots over 40 s is a mean of 6.67 s. That number is the point of the list. An earlier cut of the
same sequence ran thirteen shots averaging 3.1 s, and it read as jittery while the moves inside the
shots read as fine, so the moves were kept and the edit was rebuilt against the
architectural-visualisation convention of five to eight seconds a shot. The band is enforced on
every shot with no exception for the closing one, because none was needed.

### What makes a cut legal here

`validate_camera_shots` runs before any geometry is built and refuses the build unless the shot list
tiles 1–960 exactly, every shot is inside the 5–8 s band, every shot's first and last key sit on its
first and last frame, and every cut passes both film rules: **at least 30° of camera angle**, *and*
either **two steps of shot size** or **at least 20 mm of focal length**. Both numbers are computed,
not judged. The angle is the thirty-degree rule read literally, as the angle the two eyes subtend at
the subject rather than the angle between the two view axes, which a pair of parallel cameras a
metre apart would pass. Shot size is the horizontal field width at the look point, banded on a
seven-step ladder from extreme close to extreme long at a ratio of about 1.6 a step, so "two steps"
is the same claim a director makes when they say a cut goes from a medium to a close-up.

The five cuts as built:

| Cut | Angle | Lens | Shot size | Passes on |
|---|---|---|---|---|
| 150 → 151 | 41.7° | 52 → 62 mm (10) | long → medium (2 steps) | angle + size |
| 330 → 331 | 51.7° | 52 → 34 mm (18) | medium → extreme long (3 steps) | angle + size |
| 498 → 499 | 58.1° | 75 → 34 mm (41) | medium close → long (3 steps) | angle + size + lens |
| 672 → 673 | 60.2° | 38 → 66 mm (28) | medium long → medium close (2 steps) | angle + size + lens |
| 800 → 801 | 61.2° | 58 → 38 mm (20) | medium → extreme long (3 steps) | angle + size + lens |

Where a cut could not have passed, the two shots were merged into one moving take instead of being
forced. That is why a transfer and the operation after it share a shot here: the camera travels with
the carrier and settles on the work, which is the continuity of motion the same standards recommend
and which removes a cut for free. It is also what gets the camera close to the mechanism without
spending a cut on it, so both head changes and both dispensing passes are seen close and working
rather than at establishing distance.

The two head changes are the machine's most interesting mechanism and neither falls between shots.
Head change A opens shot two and gets three keys of its own; head change B sits inside shot four,
with a key on the mover reaching its dock and another on the gripper locking back on.

### How it is built

Aim is a tracked empty, `CameraTarget`, not a keyed rotation: Euler interpolation flips and gimbals
on an arcing move and a `TRACK_TO` constraint cannot. The same empty is the depth-of-field focus
object, so focus sits on the subject by construction rather than on a second animated number that
can drift away from it. Aperture is not authored per key either: `shot_aperture` derives it from the
shot size, f/11 below 1.02 m of field width, f/16 to 1.64 m and f/22 beyond, so mild depth of field
on the close beats only is true by construction. Neither the camera nor the empty is exported, so
none of this reaches the GLB; the digest is unchanged by camera work, and a change in it means one
of them leaked into the export.

Interpolation carries the edit. Each shot's first and last key has flat handles, which is what makes
a move start and end at zero velocity so the cut lands on a settled frame; keys inside a shot stay
automatic so a multi-leg travel reads as one continuous move. The key that ends a shot is
`CONSTANT`, so the value holds to the last frame and changes on the next one. That is the cut.

Two spatial constraints produced the numbers, and both came out of looking at renders:

- The camera stays in the front aisle at `y <= -880 mm`. The machine's front-most body is the
  transfer-port guard handle at `y = -829 mm` and its frame feet reach `y = -613 mm`, both measured
  from the built scene. `validate_camera_shots` refuses a shot that authors an eye behind that
  plane. That is a coarse rule on authored keys, so `validate_camera_path` then flies all 960 frames
  and measures the eye against the world bounds of 1867 bodies: every static body in the cell, plus
  the moving bridge re-measured on every frame. The built path's closest approach is **427 mm**, to
  `FrameRailDeck_-0.538` at frame 673; the floor is 222 mm, which is what the previous edit reported.
- The input hand-off cannot be shot low from the front. The transfer-port guard stands directly in
  front of it at grip height, so the input end is shot from above it, which is why the establishing
  take ends high rather than at deck level.

Lens is a shot property. Establishing and re-establishing is 26–38 mm, a station that has to read as
a working mechanism is 42–66 mm, and the tips entering the wells are at 75 mm. Past about 60 mm the
pipetting head's body crops, which is right when the shot is about the tips and wrong when it is
about the head.

`assets/camera-poses.json` publishes the shot list next to the still poses, so a later render or a
downstream consumer can reproduce the same edit.

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

The viewer binds these required nodes, one per twin entity and one per anchor:

```text
CellRoot
SampleCarrier
Mover
GripperHead
PipetteHead
MixerRotor
CharacterizerHousing
CharacterizerDoor
Anchor_Input
Anchor_Dispense
Anchor_Mix
Anchor_Characterize
Anchor_Output
```

Do not rename them without updating `twin.yaml`, the viewer bindings and `viewer/src/demo.ts`, the
inventory check, and the related tests. The names come from the table under
[Naming conventions](#naming-conventions); a rename that does not follow it is a rename to reject.

## Motion represented

The authored animation includes:

- input and output hotel shuttle motion;
- gripper pickup, safe-Z travel, placement, and release;
- two head changes, at frames 150-208 and 552-612;
- two 8-channel tip-pickup, dispense, and tip-drop cycles;
- synchronized liquid fill state;
- plate transfer to and from the mixer;
- a clockwise 2 mm-diameter orbital mixing translation without plate yaw; and
- reader door staging, closure, read indication, and reopening.

`_BEATS` in `build_scene.py` is the single ordered table of named marks the whole timeline is built
from, and `PHASE_RANGES` derives the seven workflow phases published to `twin.yaml` from it. A
re-timing changes durations in `_BEATS`; every keyframe, every motion checkpoint and every contact
window follows, and the table refuses to build unless the durations still total 960 frames.

| Frames | Phase | Binding |
|---|---|---|
| 1-150 | transfer input to dispense | `input-to-dispense` |
| 150-208 | **head change: gripper out, pipetting head in** | none |
| 208-552 | dispense | `dispense-cycle` |
| 552-612 | **head change: pipetting head out, gripper in** | none |
| 612-672 | transfer dispense to mix | `dispense-to-mix` |
| 672-724 | mix | `mix-cycle` |
| 724-770 | transfer mix to characterize | `mix-to-characterize` |
| 776-892 | characterize | `characterize-cycle` |
| 898-960 | transfer characterize to output | `characterize-to-output` |

A head change is a real beat rather than a cut: the mover travels to the dock at the front row,
steps back over the cradle, lowers until the collar takes on the bars, unlocks, rises away empty,
crosses to the other dock, lowers, locks, and lifts. Roughly sixty frames each. No cue covers those
frames, which is correct - a head change is the cell's own housekeeping, not a commanded operation.

The GLB keeps this authored 960-frame motion. `twin.yaml` maps each projected transfer or operation
cue to its matching frame range through `animationTimeline`.

`validate_motion` confirms authored transforms and timing. `check_scene.py` adds the relationships
between bodies:

- **carry rigidity** — whenever the plate or the reader door moves, it moves with the body carrying
  it: the gripper head, the shaker platform, or a hotel shuttle. Carried keyframes are derived from
  the carrier pose in `build_scene.py`, so the two cannot drift apart;
- **grip contact** — while the jaws hold a closed width, both jaw assemblies bracket that payload
  within 2 mm on every axis, and no payload rides the gripper head with the jaws open;
- **interpenetration** — moving assemblies are tested against the casework, the workstation chassis
  and its deck, the mover rail, the head docks, the modules, and the labware with a 0.25 mm per-body
  contact margin. Legitimate contact is declared per pair, per frame window, and where useful per body, in
  `ALLOWED_CONTACTS`;
- **gripper mechanism continuity** — each paddle reaches the head's collar through an unbroken chain
  of bodies (pad, paddle, finger, carrier, cross-rail) that stays in contact at every frame and
  therefore at every authored jaw width, and neither carrier runs off the end of its rail. Carry
  rigidity and grip contact both pass for a gripper whose paddles are correctly parented and
  correctly placed while nothing at all spans the distance between them and the arm; that is the
  state this scene shipped in, and it read as two bars floating beside the mover;
- **head ownership** — every head is at every frame either coupled to `MoverCoupler`, with bounds
  overlapping on all three axes, or resting at its own dock's authored pose with bounds overlapping
  that dock. Never both, never neither. A head moves only while coupled and only by the mover's own
  displacement, and no two heads are ever coupled on the same frame. This scene previously ran two
  independently driven carriages on one bridge, which every scalar check accepted because neither
  carriage was ever wrong about its own pose; this is the check that refuses that shape.

Run the invariants against a built file without rebuilding it:

```bash
blender -b examples/digital-twin-surrogate/scene/assets/surrogate-cell.blend \
  --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/check_scene.py -- --step 2
```

They still do not test forces, liquid physics, or equipment safety.
