# Build a twin scene

A laboratory owns its own scene. OpenSDL ships no equipment catalog and no generic assets, so
building a twin means authoring geometry for your laboratory and binding it to the contract in
`twin.yaml`. This page is the procedure and, more usefully, the failure modes — every defect
described here shipped in the reference scene first and passed a full checking pass while doing it.

The reference under `examples/digital-twin-surrogate/` is a worked example of everything below. Read
its `scene/README.md` for the commands; read this for the reasoning.

## The contract comes before the geometry

A twin definition names nodes, and the viewer refuses to load when a declared node is absent. Those
names are a published interface, so decide them before modelling rather than renaming afterwards.

Fix the vocabulary once and apply it everywhere. The reference scene used four different words for
one station — the anchor said `characterize`, the node said `Colorimeter`, the entity said
`plate-reader`, and the driving capability was `cell-characterize`. Renaming afterwards reached much
further than the scene, because an anchor identifier is also a transfer cue's source and
destination: the workflow, the capability's location enum, and the adapter all had to move with it.

Publish the vocabulary in the scene README. A convention that lives only in the modeller's head is
not a convention.

## Author the build as a program

Model procedurally, in a script the repository can re-run, rather than by hand in a saved file.
That is what makes the scene reviewable in a diff, reproducible from source, and checkable before
export.

The exported GLB is byte-reproducible from a deterministic build. A `.blend` file is not — it
carries session state. Enforce the reproducible artifact with a test that rebuilds headlessly and
compares exported bytes, and confirm that test can fail by changing a source dimension slightly.

## Validate in three tiers, and do not skip the third

### Scalar checks

Positions, pitches, counts, fill states. Necessary and badly insufficient on their own. The
reference scene passed seventy scalar checks while the gripper carriage travelled through the
enclosure glazing, the jaw paddles intersected the deck on every pick, and the pipette dispensed
between well rows.

### Relational checks

Bodies compared against other bodies, run before the export so a bad scene never becomes an asset:

- **Carry rigidity** — a payload moves only with whatever is carrying it.
- **Grip contact** — the jaws actually bracket what they claim to hold.
- **Interpenetration** — a mesh-level test, with a small contact margin and an explicit allowlist
  for the contacts that are real.
- **Mechanism continuity** — each link in a kinematic chain touches the next one, at every authored
  pose.

### Look at a render

**A data pass cannot see what a render can.** This is the rule that matters most, because every
expensive defect in the reference scene passed the numeric checks and was found by eye.

The gripper jaws tracked the carriage exactly and gripped the plate correctly, and carry rigidity
and grip contact both passed — but no geometry connected the jaws to the wrist, so they read as two
bars floating beside the arm. Nothing numeric was wrong. Only a picture showed it.

Render cheaply, look at every image, fix one thing, re-render.

## Four ways a passing check lies to you

**The pair you never construct is the defect you never find.** Later, the same floating defect
appeared one joint higher, at the mover-to-rail carriage: the mover had no vertical axis, its body
occupied the rail's own volume at travel height, and at the bottom of its stroke nothing connected
it to anything. The interpenetration check did not miss this through a tolerance or an allowlist
entry. It builds its pairs from movers against fixed bodies, the bridge assembly was in neither
list, and the pair was therefore never formed. Nothing suppressed the overlap; nothing was looking.

Audit the **sets** a check iterates, not only its thresholds. Ask what pairs exist, not whether the
ones you thought of pass.

**An invariant written for one chain generalises to nothing.** The jaw-mechanism check was written
after the floating jaws, walking one specific wrist-to-pad chain. It fixed the jaws and covered
nothing else, which is why the identical defect sat one joint higher untouched. Write the check
over the chain as data, so a new assembly can declare its own.

**A check that has never failed proves nothing.** Perturb the source and confirm each check goes
red. A regex, a threshold, or a lookup that silently matches nothing agrees with everything.

**Silent failures are the worst kind.** A shadow-buffer overflow reported only on stderr made a
full render look finished and be wrong. Read the build's own error stream and treat repeated
warnings as failures.

## Derive carried motion from the carrier

Author one pose and compute everything that rides on it from that pose. Do not keyframe a payload
alongside its carrier and trust them to agree — they drift, and the drift is invisible until a
close shot.

The same principle makes a whole class of error unrepresentable. In the reference scene a coupled
tool has no pose of its own; it is written from the mover's, so a tool physically cannot travel
under its own power. An invariant then asserts the remaining question at every frame: each tool is
either coupled or docked, never both, never neither.

Prefer a structure that cannot express the defect over a check that detects it.

## Probe the renderer, never hardcode it

Engine identifiers, feature flags, and enum names drift between versions. Query what the running
build supports and report what was applied rather than assuming a capability exists. Record the
build version in the generated inventory so a report is bound to the toolchain that produced it.

## Bind it up

The scene digest binds the definition to the geometry, so changing the scene changes several files
at once. In this repository the ring is enforced: the GLB, the node inventory, the motion report,
`twin.yaml`, and the viewer's demonstration data are compared against each other by tests, and any
one of them left behind fails the suite.

Set the same enforcement up in your laboratory repository. A cascade that is documented as a
checklist will be performed partially; the reference change that added this guidance updated four
of eight files on the first pass. Keep camera work out of the export so the edit cannot move the
digest.

## Where this stops

A twin is a visualization bound to persisted evidence. It is not a kinematic simulator, a collision
authority, or a safety case, and passing checks are geometric claims rather than engineering ones.
See [what a projection cannot show](../architecture/digital-twin.md#what-a-projection-cannot-show)
for the contract boundary, and [Designing a laboratory](design-a-lab.md) for deciding what to build
before you model it.
