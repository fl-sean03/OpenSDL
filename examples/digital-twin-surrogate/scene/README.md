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
| the single transport carriage | **mover** | `Mover`, `Mover*` | `Mover`, `MoverRail`, `MoverBridge`, `MoverGantry`, `MoverTruck`, `MoverCoupler`, `MoverChain` |
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
| Cell | `build_stations`, `build_transport`, the module builders | The transport runway landed straight on the end towers, the bridge, the one mover and its changer, the two interchangeable heads and the two docks they wait in, the drag chain that follows the mover, and the plate hotels, mixer, reader, tip rack, reservoir and labware on the deck. The X drive — rail, bearing truck, vertical way, slide and bracket — is carried on the **rear** face of the bridge beam, behind `MOVER_DRIVE_SIDE`, so nothing in the drive train stands between the front aisle and the arm it carries |
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
| `renders/opensdl-surrogate-cell.mp4` | Committed H.264 animation of the authored 49-second sequence |

The animation spans frames 1–1176 at 24 frames per second. Its duration is 49 seconds.

## Build the source and GLB

Run this command from the OpenSDL repository root:

```bash
blender -b --factory-startup -noaudio \
  -P examples/digital-twin-surrogate/scene/build_scene.py
```

The default build uses Eevee render settings, saves frame 548 in the Blender file, and exports the
GLB. A failed motion check stops the build before any of that. Both reports are written after the
export, so each one records the digest of the GLB it describes.

The current validation covers 107 conditions. Eighty-four of them are scalar checks in
`build_scene.py`: slot pitch, required labware counts, plate and reader-door checkpoints, grip
alignment, head dock poses and head-to-mover tracking, tip attachment, liquid fill state, hotel
shuttles, clamp clearance, a 1 mm mixer orbit radius, and zero plate yaw. One more measures the
machine's stillness either side of the single cut, off the built animation. The remaining twenty-two come
from `check_scene.py` and compare bodies to each other rather than to a number.

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

Blender first writes the 1176 PNG frames under `renders/frames/`. The script then encodes H.264 with
a YUV 4:2:0 pixel format and fast-start metadata. It removes the temporary frames after a successful
encode.

Use `--no-export` during render-only iteration when the checked GLB must remain unchanged.

## Camera choreography

The 49-second cycle is shot rather than watched. `CAMERA_SHOTS` in `build_scene.py` is two moving
takes that tile frames 1–1176 exactly, and the single cut between them lands where the machine both
finishes something and has stopped moving:

| Frames | Length | Ends on | Shot | What it is |
|---|---|---|---|---|
| 1–752 | 31.33 s | `mix_place_settle` | `establish-load-dispense-and-to-mix` | Wide from the front right of the aisle, then straight to the station the gripper is working: left and in as the plate comes out of the hotel and lands on the dispense stage, a frame that holds both head docks through head change A, back left with the pipetting head for tips, reservoir, both fills and the tip change between them — and then, across the two-second hold the machine takes at `dispense_end`, a continuous reposition out to a wider framing that carries head change B and the transfer to the mixer without a cut |
| 753–1176 | 17.67 s | `rest_hold` | `mix-read-out-and-rest` | Tight on the Heater-Shaker from the left through the clamp close and the orbit, arcing right and travelling a station along with the plate; the whole characterization on one developing arc around the reader — door off the caddy, lowered home, the read, lifted away, returned — then right with the plate to the output hotel, and out through the park and the travel home to a closing wide centred on the machine |

The camera moves when the **subject** changes location, and holds while the machine works inside one
area even when it is moving a great deal in there. A camera that tracks every approach, lift and
traverse reads as nervous and makes a competent machine look frantic; a frame that contains the work
and lets the machine move through it reads as deliberate, and it is what makes the pans that remain
mean something.

### Cut where the work moves, not where a beat ends

The edit began with thirteen cuts, went to five, then to two, and is now one. Each reduction came
from the same observation: a legal cut frame is permission, not an obligation. Cuts at
`transfer_in_end` and `fill_a_end` were on completions and still wrong, because the machine went
straight on working the same end of the deck through both; the cut at `door_close_clear` was on a
completion in the middle of one continuous characterization. The last to go was the cut at
`dispense_end`, which was legal by every measure and still read as a jolt, because the machine on
both sides of it is the same machine at the same deck — so the camera now repositions across the
two-second hold instead, arriving at the new framing while nothing is moving. What survives is the
stronger rule: **when the work continues in the same place, the camera continues too, and a cut is
earned only when something genuinely changes.** The one remaining cut coincides with the plate
leaving one station for another.

### What makes a cut legal here

Four standards decide where a cut may fall. `validate_camera_shots` computes three of them from the
authored data before any geometry is built, and `validate_cut_stillness` measures the fourth off the
built animation. They refuse the build on any failure, because a shot list that cuts in the middle of
a dispense is a defect in the edit rather than something to discover at the end of a forty-minute
render. A fifth check, `validate_eye_trace`, governs the frame between the cuts rather than the cuts
themselves and is described below.

**Stillness, which is the governing constraint.** A cut may only land on a frame where the machine
has actually stopped: `validate_cut_stillness` walks the built animation and requires the mover, the
bridge, both heads and the carrier to sit within 1 mm of their cut-frame pose for **12 frames before**
the cut and **6 frames after** it. The two numbers differ because the two failures differ. Cutting
away from a machine still in motion reads as the edit interrupting the work, so the run before a cut
is half a second and is the hard one; opening a shot on motion already under way reads as the cut
having caused it, which a quarter of a second breaks. This rule is measured off the animation rather
than off beat names, and it caught what the name rule could not: `mix_place_clear` **is** a
completion, and the mover is still moving 3 mm per frame into its lift-away on the frame that beat
completes on. The fix was a 24-frame held beat after it, with the cut at the end of the hold.

**Motivation, which decides where a cut may go at all.** A cut may land only where an action
completes: a station changes, a tool changes, or an operation finishes. Never inside a continuous
motion, and never inside a sustained dwell. An earlier cut of this sequence met every number below
and was still wrong, because two of its five cuts fell in the middle of a dispensing pass and a third
fell between a grip and the lift that followed it. A cut there reads as a jump for no reason however
well it is framed. The stillness rule subsumes this one, but both run: the name rule is free, and it
names the operation a bad cut would have interrupted.

The legal frames are derived from `_BEATS`, not written down. A beat finishes something when its
last name word is one of `end`, `clear`, `ready`, `lock`, `settle`, `stored`, `up` or `front` — a
state the machine has arrived at, rather than a step inside an operation such as `approach`, `down`,
`grip`, `lift`, `cross`, `seat`, `release` or `unlock`. `hold` is deliberately excluded: the same
word names the 22-frame plate read and the 3-frame pause at the reservoir, and a rule that cannot
tell those apart would licence a cut in the middle of an aspiration. At the authored timing that
leaves 29 legal frames out of 1176. Re-timing the workflow moves them with it, so the check cannot
go stale. Every cut also has to clear the sustained beats — the two 96-frame dispenses, the 48-frame
dispense hold, the 36-frame orbital mix, the 22-frame read and the 48-frame rest hold — which no cut
may fall strictly inside.

**Shot length, which follows from motivation rather than driving it.** Five seconds is a floor with
no exceptions. Eight seconds is a ceiling with two doors through it, and neither is opened by an
authoring note. A take passes it silently when no completion inside it splits it into two takes that
both clear the floor, which the validator checks by trying every legal frame. A take that *declines*
legal cut frames passes it only by declaring `sustains`, and a declared long take is then held to
more, not less:

- past **24 seconds** (`SHOT_DECLARED_MAX_SECONDS`) a declared take has to show it was *composed*
  rather than merely long. It must never coast — no gap between authored keys wider than one
  development window — and it must *resolve*, delivering end to end at least the framing change a cut
  would have had to deliver: two steps of shot size or 20 mm of lens. The 30° half of the cut rule is
  deliberately not applied, because thirty degrees exists to stop a jump cut and nothing is being cut
  here. A wall at a fixed number of seconds would have protected nothing once a take legitimately ran
  past it; these two tests catch what the wall was aiming at, which is a take that sprawls without
  going anywhere. The merge accident — two shots joined by deleting the boundary between them — fails
  the first test, and a busy camera that ends framed exactly as it opened fails the second;
- a **share** ceiling instead of a second count: `SHOT_MAX_TIMELINE_SHARE` of 0.70 is the wall nothing
  opens. A share does not go stale when the workflow is re-timed, and the property actually worth
  guaranteeing is that this is still an edit; and
- a **development rate**: over every rolling 48-frame window inside the take, the authored camera has
  to travel at least 150 mm along its path or change at least 4 mm of lens. Both figures are measured
  along the path rather than end to end, because an arc that goes out and comes back has developed
  the frame even though its two ends are close together. Windows are formed over the take's
  *working* frames — a beat authored as a stopped machine is not dead air, it is the point — and they
  step one frame at a time, so a dead stretch cannot hide by straddling two of them.

Both long takes are declared, and both report zero dead windows. A long take with a lazy camera is
worse than the cuts it replaced, and that pair of checks is what refuses one.

**Cut quality.** Every cut has to change the camera angle by **at least 30°** *and* change the
framing by either **two steps of shot size** or **at least 20 mm of focal length**. Both numbers are
computed, not judged. The angle is the thirty-degree rule read literally, as the angle the two eyes
subtend at the subject rather than the angle between the two view axes, which a pair of parallel
cameras a metre apart would pass. Shot size is the horizontal field width at the look point, banded
on a seven-step ladder from extreme close to extreme long at a ratio of about 1.6 a step, so "two
steps" is the same claim a director makes when they say a cut goes from a medium to a close-up.

The cut as built. It is on a completion, it is where the plate leaves one station for another, and it
is measured still on the animation itself. Both sides look at the mixer, so the point of interest
does not move across it either. All of it is printed with the edit report at build time:

| Cut | Lands on | Angle | Lens | Shot size | Still before | Still after |
|---|---|---|---|---|---|---|
| 752 → 753 | `mix_place_settle` — plate down on the mixer, jaws away, carriage stopped | 54.4° | 44 → 66 mm (22) | medium long → medium close (2 steps) | 24 frames | 8 frames |

### Where the viewer is looking

A cut is not the only way to strain an audience. When the subject of interest jumps from one side of
the frame to the other, the eye has to cross the whole screen, and it registers as effort even inside
one continuous take. The ending had exactly this: the plate was placed at the output hotel on frame
right, and the arm then parked and came to rest on frame left, while the camera simultaneously
retreated rightward and widened. Three motions compounded and drove the point of interest from centre
frame to the edge.

`validate_eye_trace` measures it rather than leaving it to taste. `EYE_TRACE_SUBJECTS` maps a beat
prefix to the body the viewer should be watching — longest prefix wins, so `door_` is the reader door
while `door_row_front` is the empty mover — and every frame the subject's centre is projected through
the camera into normalized screen coordinates. Four things are then required:

- the subject stays inside a **safe region** and is never pinned to an edge;
- the camera does not **drag** the frame faster than a threshold *on its own* — isolated by
  re-projecting the previous frame's world point through this frame's camera, so a subject hopping a
  well column does not score against a stationary camera. The rule that falls out is the useful one:
  the camera may move as fast as it likes while carrying the subject, and no faster than this without
  it;
- over any rolling window the frame must not **work against** the subject: if the subject crosses a
  large fraction of the frame, the camera has to have absorbed that crossing rather than added to it.
  This is the compound that produced the strained ending, and stating it this way permits both a held
  frame with a machine moving through it and a camera panning with a transit; and
- at a **handoff** from one subject to the next, the outgoing and incoming screen positions must be
  close.

Fixing the ending meant giving up the bookend. Returning to the exact opening pose was a nice idea
that could not work: that pose was composed for a machine-wide establish from the front right, where
the subject is the whole machine, and the closing subject is one arm at the centre of the deck. The
film now closes on a wide centred on the machine instead, the pull-back finishes before the mover
starts for home, and the aim then follows the carriage in. The point of interest ends at 0.50 across
the frame and holds there, dead centre, for the last two seconds.

Where a cut could not have passed, or was not earned, the shots were merged into one moving take
instead of being forced. That is why a transfer and the operation after it share a shot here: the
camera travels with the carrier and settles on the work, which is the continuity of motion the same
standards recommend and which removes a cut for free. It is also what gets the camera close to the
mechanism without spending a cut on it, so all three head changes and both dispensing passes are seen
close and working rather than at establishing distance.

The head changes are the machine's most interesting mechanism and none of them falls between shots.
Head change A is a slight pan right inside the opening take; head change B opens the middle take
after its held beat; the park at the end lives inside the closing take, and the camera keeps pulling
back through it rather than completing early and waiting for the machine.

### Held frames, in both directions

Seven beats last twenty frames or more. Four of them are the machine working — the two 96-frame
dispensing passes, the 36-frame orbital mix and the 22-frame plate read — and a camera that sits
still through one of those turns the operation into dead air. Three of them are the machine
deliberately stopped, and on those the test is **inverted rather than waived**: a camera that travels
across a held beat puts the motion back into the frame and hides the thing the beat exists to show.

| Beat | Frames | Requires | Eye travel | Lens change |
|---|---|---|---|---|
| `fill_a_end` | 263–358 | movement — ≥200 mm or ≥10 mm | 727 mm | 15.8 mm |
| `fill_b_end` | 433–528 | movement | 791 mm | 9.9 mm |
| `dispense_hold` | 561–608 | stillness — ≤220 mm and ≤6 mm | 42 mm | 1.0 mm |
| `mix_place_settle` | 729–752 | stillness | 110 mm | 4.0 mm |
| `mix_orbit_end` | 759–794 | movement | 340 mm | — |
| `read_hold` | 907–928 | movement | 342 mm | 6.0 mm |
| `rest_hold` | 1129–1176 | stillness | 0 mm | 0.0 mm |

The two beats that carry a picture change still allow a drift, because a frozen frame is not the
same claim as a still machine. `dispense_hold` is where the camera makes its one large reposition,
and it does it across a stopped machine precisely so the move reads as composition rather than as
the machine being chased. `rest_hold` allows none: the closing take's last two keys are identical, so
the film ends on a genuinely settled frame — machine at rest, camera at rest — for two full seconds.

The dispensing itself is not static either: the head steps twelve columns across the plate, dipping
83 mm into the wells and rising again every eight frames, so the camera's push-in runs against a
visible working rhythm rather than against a held pose.

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
  plane. That is a coarse rule on authored keys, so `validate_camera_path` then flies all 1176
  frames and measures the eye against the world bounds of 1924 bodies: every static body in the cell,
  plus the moving bridge re-measured on every frame. The built path's closest approach is **455 mm**,
  to `FrameRailDeck_-0.538` at frame 753; the floor is 222 mm.
- The input hand-off cannot be shot low from the front. The transfer-port guard stands directly in
  front of it at grip height, so the input end is shot from above it, which is why the establishing
  take ends high rather than at deck level.

Lens is a shot property. Establishing and re-establishing is 26–44 mm, a station that has to read as
a working mechanism is 46–66 mm, and the end of the first dispensing pass is at 70 mm. Past about
60 mm the pipetting head's body crops, which is right when the shot is about the nozzles and wrong
when it is about the head.

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
window follows, and the table refuses to build unless the durations still total 1176 frames.

| Frames | Phase | Binding |
|---|---|---|
| 1-150 | transfer input to dispense | `input-to-dispense` |
| 150-208 | **head change: gripper out, pipetting head in** | none |
| 208-560 | dispense | `dispense-cycle` |
| 560-608 | **held: the machine is stopped while the camera repositions** | none |
| 608-668 | **head change: pipetting head out, gripper in** | none |
| 668-728 | transfer dispense to mix | `dispense-to-mix` |
| 728-752 | **held: the machine is stopped either side of the cut** | none |
| 728-804 | mix | `mix-cycle` |
| 804-850 | transfer mix to characterize | `mix-to-characterize` |
| 856-972 | characterize | `characterize-cycle` |
| 978-1040 | transfer characterize to output | `characterize-to-output` |
| 1040-1176 | **return to rest: park the head, travel home, hold** | none |

A head change is a real beat rather than a cut: the mover travels to the dock at the front row,
steps back over the cradle, lowers until the collar takes on the bars, unlocks, rises away empty,
crosses to the other dock, lowers, locks, and lifts. Roughly sixty frames each. No cue covers those
frames, which is correct - a head change is the cell's own housekeeping, not a commanded operation.

The tail is the same kind of thing at larger scale. After `cycle_end` the mover carries the gripper
back to `HeadDock_Gripper`, seats it, unlocks, rises away, travels to a home position midway between
the two docks on the changer row, and stops for two seconds. Those 136 frames carry no binding, and
that is deliberate: `animationTimeline` bindings only have to stay inside the frame range, not tile
it, and a machine putting itself away is not a workflow step to be projected as one. It is also a
correctness fix rather than only a pacing one — the cycle previously ended with the gripper still
coupled and the carriage stopped wherever the last transfer had left it, which is not a state a
machine would sit in.

The GLB keeps this authored 1176-frame motion. `twin.yaml` maps each projected transfer or operation
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
- **carriage mechanism continuity** — the same claim, one joint up, and the reason it exists is that
  the jaw check was written for the jaws and generalised to nothing. The mover reaches the bridge
  rail through an unbroken chain: body, slide bracket, column slide, vertical way, bearing block,
  rail. Each link stays in contact at every frame and therefore at every height in the 117 mm
  stroke, and each of the two sliding joints stays *inside* the member it rides rather than running
  off its end. The mover had the identical defect the jaws had — correct pose, no geometry — and it
  additionally passed 45 mm through the bridge beam at travel height while every spatial check stayed
  green. Nothing was suppressing that: `MoverBridge` was in neither `MOVERS` nor `STATICS`, so the
  pair was never formed and nothing was looking. The structural fix is `MoverGantry`, a root under
  the bridge that carries the beam, the cover, the rail and the truck but not the mover, so the two
  are different assemblies and the question can be asked at all;
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
