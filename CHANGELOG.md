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
  published equipment dimensions, Blender source, GLB output, provenance, 107 scene checks, and a
  committed 49-second, 1176-frame H.264 animation of the authored sequence;
- a read-only Three.js viewer with local demonstration data, stored-run replay, timeline controls,
  semantic highlights, transfers, authored-motion synchronization, browser-side scene-digest
  checks, required-binding failures, and projected sample properties; and
- lab onboarding guidance and a `start-here` skill for durable shared context and simulator-first
  setup planning;
- a laboratory design guide and a `design-lab` skill covering how to decompose a laboratory, find the
  requirement that actually drives a design, judge whether a pattern borrowed from another field
  transfers to a given material system, separate reversible decisions from irreversible ones, and
  keep safety functions outside the orchestration layer;
- a twin-scene authoring guide covering the node vocabulary as a published interface, procedural and
  byte-reproducible builds, the three tiers of checking, and the four ways a passing check misleads —
  the unconstructed pair, the invariant written for one chain, the check that has never failed, and
  the failure reported only on stderr — together with deriving carried motion from its carrier so a
  class of defect cannot be expressed at all;
- a compatibility and versioning policy stating, per public surface, what stability it carries today.
  It records the specific defects rather than an intention: both `apiVersion` fields are literal pins
  on models that forbid extra keys, so a newer document cannot be read by an older reader even when
  the only difference is an added optional field and `v0alpha2` cannot be introduced additively;
  generated schemas carry no `$id`, `$schema` or version and the drift gate compares bytes, so it
  answers whether the schemas were regenerated rather than whether the contract changed; the version
  check compares strings across the workspace without parsing a version at all; and no package has
  ever been published or tagged, so a laboratory cannot install from an index. It also names a surface
  the audit missed — `CapabilityDefinition.version` has no readers and a workflow step cannot request
  a version, so a capability contract can change under a workflow already using it;
- generated JSON Schemas for the twin definition and cue contracts, produced by a single composed
  generator that both `scripts/generate-schemas.py` and `opensdl schema generate` consume; and
- an enforced Ruff formatting gate in `make lint` and CI; and
- a scene workflow that runs the headless Blender rebuild in CI, pinned to the version the scene
  itself records so the two cannot drift, with a pytest plugin that turns a skip into a failure. The
  reproducibility claim was the strongest check the repository owned and the only one that had never
  run: Blender is not installed on the runners, so the test took its skip path and reported green.

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

### Breaking

- `spec.capabilities[].config` is removed from the laboratory manifest. It was accepted and never
  read, and a per-capability `config:` is exactly where an operator would write the operating limits
  `SAFETY.md` asks a deployment to enforce. Silently ignored safety configuration is worse than an
  absent field. A manifest that sets it is refused by name, pointing at `spec.adapters[].config`,
  which is the channel that works. There is no operating-envelope mechanism to move operating limits
  to; that remains open design work.
- `PolicyDecision` carries a required `policy_digest`. A third-party evaluator that constructs a
  decision must supply one; `PolicyEngine.digest` computes it.
- `OpenSDLSystem.start()` no longer reconciles incomplete runs by default and returns the runs it
  moved. It used to move every running run to `intervention_required` and release its leases on every
  call, including the call behind `opensdl doctor`. Pass `reconcile=True` where crash recovery is
  wanted — a controller or server starting up — and report what comes back.
- `CampaignRunner.run` requires `environment` and `operator_id` rather than defaulting them, and no
  longer injects a `sample_id` input. Pass `iteration_id_input` to name an input to fill.

### Fixed

- a declared timeout did not bind an adapter that blocks. `asyncio.wait_for` can only interrupt at an
  await point, so a synchronous call inside an `async def` — the shape a vendor SDK forces — ran to
  completion whatever `timeout_seconds` said, and held the event loop while it did, which made
  `max_concurrency` a fiction and stalled every other run's timeout and lease handling with it.
  Adapter code now runs on a worker thread with its own event loop, one per adapter, and the runtime
  waits on a handle it can abandon. Measured: a 0.1 second timeout against a two-second blocking
  adapter went from 2.01 seconds and no error to 0.12 seconds and a recorded timeout; a concurrent run
  went from 2.01 seconds to 0.47. The timeout bounds how long the runtime waits and nothing else —
  abandoned work keeps running, cancellation is requested rather than guaranteed, and an adapter with
  no await point cannot receive it. One loop per adapter rather than one per call, because an adapter
  may hold a lock or a connection across its own lifecycle and splitting `execute` from `close` binds
  it to two loops;
- campaigns were unreachable from every interface. The headline closed-loop feature could only be
  started by writing bespoke asyncio Python, so no operator, agent or remote client could start one,
  see one, or read what it did. There are now `campaign start`, `list` and `inspect` commands,
  `list_campaigns` and `inspect_campaign` in the tool catalogue and over MCP, `GET /campaigns` and
  `GET /events?campaign_id=`, SDK methods, and `active_campaigns` in the context pack, so an agent
  asking a laboratory to describe itself learns that it is mid-campaign. A campaign is projected from
  its own events rather than from a table, because a record kept beside the events could disagree with
  them. Starting is deliberately foreground and CLI-only: submitting a days-long campaign through a
  handler that awaits it would repeat the mistake that already makes `POST /runs` unable to carry a
  real run;
- a manifest could not name a credential. Documentation said credentials came from the environment or
  a secret provider; neither existed, so the only way to configure a real instrument was to type its
  token into the file the documentation designates as belonging in Git. A manifest value may now
  contain `${env:NAME}`, resolved before validation and refused when it resolves to nothing, so a
  missing credential fails at the loader rather than at an instrument. References are refused in
  mapping keys, because the environment must not choose which field is configured, and anywhere under
  `spec.policy`, because that would make an environment variable an authorization decision. A resolved
  value is written back as its reference when a manifest is dumped and in the operator context pack —
  which was carrying domain-pack configuration verbatim to an unauthenticated route;
- an existing laboratory's database could never be upgraded. The schema was created by `create_all`,
  which is `CREATE TABLE IF NOT EXISTS` and will never add a column, while Alembic sat unreachable
  beside it and the documented recovery command failed against any laboratory that had ever run.
  Alembic is now the only writer, its migrations ship inside the wheel so a generated laboratory can
  migrate without a checkout, and a store created the old way is adopted rather than rejected. The
  drift this had already produced — 23 declared indexes the initial migration never created — is
  closed, and a test now compares the migrated schema against the declared models with the same
  comparison `--autogenerate` uses, so the divergence cannot recur silently;
- the campaign claimed an environment its laboratory had not declared. `CampaignRunner` defaulted to
  `simulation`, so a laboratory running in `production` with policy permitting only `simulation` had
  its direct submissions denied and its campaign — the one unattended path in the framework —
  executed, then recorded runs saying the work happened somewhere it did not. Both fields are now
  required, so a caller that omits them fails at type-check time rather than at a policy boundary
  that let them through;
- one failed run ended the campaign, discarded every successful iteration before it, emitted no
  terminal event, and never told the optimizer, which then proposed the same failing candidate
  forever. A failed attempt is now a typed observation with a reason, the optimizer sees it, and the
  loop stops on sustained failure rather than on the first one. A campaign also records why it
  stopped, so exhausting a budget and converging are no longer indistinguishable in the log;
- a campaign's runs were unreachable from the campaign. Every run and task event now carries the
  campaign that launched it, so one query returns the execution history rather than three campaign
  events and a list of identifiers to chase;
- reading a laboratory wrote to it. Composing a manifest initialized the store and seeded every
  capability and resource, so `opensdl inspect` against a laboratory that had never run created a
  database to report on. Worse, `doctor` called the recovery path: it moved every running run to
  `intervention_required`, released their leases, and exited reporting success without mentioning it,
  so a health check during a live campaign destroyed the record of the experiment in flight. Reads
  now compose read-only and refuse to create a store; reconciliation is asked for and reported;
- the artifact-store health check read a directory its own constructor had just created, so it
  reported on its own side effect and could not fail. It now separates a laboratory that has recorded
  nothing, which is healthy, from a root that cannot hold artifacts, which is not;
- an arbitrary installed package could be bound by a one-line manifest edit and executed at startup.
  The provenance check that catches a third party squatting a reference adapter name existed but was
  called only from a skill helper, so a squatted `simulated-lab` was loaded. It now runs on the
  composition path, and `OPENSDL_PLUGIN_ALLOWLIST` lets a deployment constrain what a manifest may
  bind. The channel is the environment rather than the manifest, because the threat is a manifest an
  agent edited and a control a manifest can grant itself is not a control;
- policy evidence could not be checked. The recorded `policy_version` was a free-form label, so every
  rule could change while the evidence stayed identical. Decisions now carry a digest of the effective
  ruleset, computed the way the twin already pins its scene;
- generated laboratories would have committed `.env.production`: the template ignored `.env` but not
  `.env.*`, while environment variables are the only sanctioned credential channel. The generated lock
  is also ignored now, because it pins a wheelhouse path that exists only on the machine that
  generated it, and a lock a colleague cannot resolve is worse than no lock — the reversal is
  documented where the ignore is. Generated dependency floors are capped at the next minor, which
  first required fixing the release tooling: its rewrite pattern would have silently deleted an upper
  bound on every version bump;
- the CLI reported ordinary mistakes as framework tracebacks — 24 to 164 lines through `asyncio`,
  SQLAlchemy and Pydantic internals, with absolute virtualenv paths in them, and exit 1 whether the
  cause was a typo, a policy denial or a defect. Every command now reports one line with an exit code
  that distinguishes them, and the traceback stays one flag away. The classifier walks the cause chain,
  because the runtime wraps a timeout and an unknown capability in a workflow error and the cause is
  the only place the specific failure survives. The runtime's carefully written refusals reach the
  operator whole rather than being flattened;
- `opensdl validate` certified configurations that could not run: a manifest naming a plugin that does
  not exist, a workflow naming a capability the laboratory does not expose. Both now resolve, and `run`
  performs the same check before dispatch, so a misspelled capability no longer costs a created run and
  a failure event. An unknown capability also says what the laboratory does expose, rather than
  repeating the identifier the author already knows they typed;
- the HTTP API answered every failure with 400 and the exception's own text. A denial is now 403 and
  names the rule and policy revision that refused it, an unregistered or leased resource is 409, a
  timeout 504, an unknown capability 404, and a malformed body 422 — and no adapter text reaches the
  wire, because an adapter's message can carry an endpoint or a credential and the API is
  unauthenticated. The error responses are declared in OpenAPI, so a generated client can see them;
- `GET /tools` advertised five tool names that existed nowhere else in the repository, with schemas
  that declared required fields and no properties, while the MCP transport served five different
  names. The catalogue is now the same one MCP registers, dispatches through the operator gateway, and
  is callable over HTTP, so an agent that reads it can use it. The transport's own tests had never
  run — the optional dependency was not installed anywhere, so its smoke test skipped, which is the
  same green-without-running failure as the scene rebuild. It is installed now, and `opensdl serve-mcp`
  gives the transport a way to be started;
- several checks reported green while constraining nothing. The propagation graph, which exists to
  answer what a change affects, was invoked by no workflow, target or validator; 17% of tracked files
  matched no node at all, including every skill, every script and most root documents; it reported an
  empty result for a path that does not exist, so a typo was indistinguishable from no impact; and it
  filed `packages/capabilities` under conformance alone, omitting the runtime, controller and CLI that
  import it directly. It is now wired into `make lint`, covers every tracked file with a validator
  that fails when coverage rots, and exits non-zero on a path that is not there. The boundary checker
  silently skipped any package missing from its map, so a new package shipped unchecked — it now fails,
  and checks 23 packages including one that had been invisible. The SDK suite stubbed the client's own
  transport, so renaming an API route passed every test; it now runs against the real application, and
  four separate route renames were confirmed to fail it and to have been missed before. The policy
  suite was a single test reporting full branch coverage because the matcher is one `and`-joined
  return; it is now fourteen, and six mutations of the engine that all slipped past the original are
  each caught;
- the runtime replayed physical actions it had recorded as ambiguous. Resuming a run rebuilt its
  completed work from succeeded tasks only, so a task left `intervention_required` by a restart or a
  cancellation — carrying the error string "physical outcome is unknown" — fell back into the pending
  set and was dispatched again. The system recorded that it did not know whether the action had
  happened, and then repeated it. Resume now refuses any run holding a task in an active or ambiguous
  state, writes nothing, and explains what a human has to establish. No acknowledgement operation was
  invented to close this: `intervention_required` remains a legal origin in the declared machine so
  the typed acknowledgement has somewhere to land, and the runtime simply declines to make that move
  on its own;
- a result that violated its declared output schema was retried, so bad data repeated the action that
  produced it. Validation sat inside the retried block, where the generic handler caught it and
  dispatched again. The retry region now covers only the adapter call: a transport failure or timeout
  retries as before, and an invalid result fails the task immediately, because the adapter has already
  reported that the action completed;
- the declared run and task lifecycles were enforced nowhere. `validate_run_transition` and
  `validate_task_transition` existed, were unit-tested, and had no production callers, so the
  persistence layer wrote any state over any state. Over the unauthenticated API that made a completed
  run mutable: resubmitting its identifier passed the only guard, forced it back to running, executed
  new steps attributed to the original operator, and overwrote its outputs while the workflow of
  record stayed unchanged. Both machines are now checked on every state write. Enforcing them revealed
  the machines themselves were wrong in four places, two of which were already contradicted by passing
  tests — a retried attempt could not succeed and could not be left ambiguous by a restart, though the
  suite demonstrated both. A specification nothing consults does not stay correct;
- an unregistered resource raised before the task was touched, leaving it pending under a failed run
  rather than recording why it stopped;
- several statements described the target rather than the system. `SECURITY.md` presented nine
  "secure defaults" in the present tense when four had no implementation; each now carries its
  verified status, prefaced by the observation that an unimplemented requirement is one the operator
  carries. The API reference said nothing about authentication for an API that has none on any of its
  fifteen routes, two of which execute capabilities. `PolicyRule.operators` looked like per-operator
  authorization while `operator_id` is a caller-asserted string, so a deny rule scoped to an operator
  is bypassed by sending a different one. Adapter `abort` was listed as part of the implemented
  contract when it has no callers, so an adapter author would have written a method that never fires.
  Claims about PostgreSQL support, sandboxing, human attestation, closed-loop optimization and the
  domain packs now say what the code does. No disclaimer was weakened; the corrections all run
  toward less assurance, not more;
- the adapter guide stopped at generation. `opensdl adapter create` produces a working package that
  nothing installs, so the first real extension step ended in `unknown adapter plugin` — while
  `opensdl validate` reported the same manifest valid. The guide now carries the path through
  installation and registration, every command in it was executed and then replayed from a fresh
  `opensdl init` to confirm it works verbatim, and it resolves the conflict between the two documented
  adapter locations by explaining that a generated adapter is its own distribution and cannot live
  inside the laboratory's import package;
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
  and nothing read as active. It is now a two-shot edit with one cut, and the standards that
  place those cuts are measured by the build rather than judged by eye. A cut may land only where an
  action completes, which is derived from the beat table rather than written down, so re-timing the
  workflow moves the cuts with it. That proved necessary and not sufficient: a beat boundary marks
  the end of a labelled step, not the moment the machine stopped, and the earlier cut on a completion
  still had the mover 3 mm into its lift-away on the next frame. Cuts are now additionally required
  to land where the mover, bridge, heads and carrier are all measurably still, for longer before the
  cut than after it, because cutting away from a moving machine reads as the edit interrupting the
  work while opening on motion reads as the cut having caused it. Every cut still changes the camera
  angle about the subject by more than the 30 degrees that separates a cut from a jump cut and
  changes framing by at least two size steps. A legal cut frame is permission rather than obligation,
  so a take that declines one holds, and a take that runs past the eight-second ceiling passes only
  by declaring itself sustained — after which it is held to more, not less: a hard 24-second ceiling
  and a camera-development rate measured over every rolling two-second window, so a long take cannot
  buy its length and then sit still inside it. The camera aims through a constraint on an animated
  target rather than keyframed Euler rotation, which cannot flip on an arcing move. Cameras are
  excluded from the export, so the edit does not touch the scene digest; and
- EEVEE was silently dropping shadow maps. Twenty area lights over a 2300-node scene overflow the
  default shadow pool on the close shots, and the only symptom is a line on stderr, so a render can
  look finished and be wrong. Raising the pool took a full pass from 5568 overflow reports to none;
- the reference cell drove two independent carriages along one rail, which is a collision hazard and
  forced every spatial check to keep testing the two against each other. There is now a single mover
  carrying interchangeable heads: a gripper and a pipetting head that couple to it and rest in docks
  when idle, with three head changes in the sequence. A coupled head's pose is written from the mover's,
  so a head cannot move under its own power, and a new invariant asserts that at every frame each head
  is either coupled or docked — never both, never neither — with no two heads coupled at once;
- the drive train stood between the camera and the arm. The rail, bearing truck, vertical way, slide
  and bracket were all carried on the front face of the bridge beam, so the mechanism that moves the
  arm occluded the arm in every front-aisle framing — which is every framing the film uses. The whole
  X drive now sits on the rear face behind one sign, both ends of the slide bracket are derived from
  the bodies they join rather than one being a literal that stops meaning what its name says when the
  assembly reverses, and the way and slide were widened so the mechanism still reads through the slot
  that opens as the arm descends instead of disappearing behind the carriage;
- the camera chased the machine. It followed every approach, lift and traverse, so a competent
  machine read as frantic and the pans that mattered were indistinguishable from the ones that did
  not. The rule is now that the camera moves when the subject changes location and holds while the
  machine works inside one area, however much it moves in there. Applying it removed the second cut
  as a side effect: the machine either side of `dispense_end` is the same machine at the same deck, so
  the camera repositions across the two-second hold instead, arriving at the new framing while nothing
  is moving;
- a cut is not the only way to strain a viewer. At the end the plate was placed at the output hotel on
  frame right and the arm then parked and rested on frame left, while the camera simultaneously
  retreated rightward and widened, so three motions compounded and drove the point of interest to the
  edge of the frame. `validate_eye_trace` now projects the active subject through the camera every
  frame and requires that it stays out of the frame edges, that the camera does not drag the frame on
  its own faster than a threshold — isolated by re-projecting the previous frame's world point through
  this frame's camera, so a subject hopping a well column does not score against a stationary camera —
  that a frame never adds to a subject's crossing instead of absorbing it, and that consecutive
  subjects hand off close together. The subject is resolved from a beat-prefix table rather than a
  hardcoded chain, which is the generalisation the jaw-mechanism check failed to make twice. The film
  gives up its bookend to satisfy this: the opening pose was composed for a machine-wide establish and
  cannot also serve one arm at the centre of the deck;
- the long-take ceiling was a wall at a number of seconds, justified only by catching an accidental
  thirty-second shot. Moving the wall would have protected nothing once a take legitimately ran past
  it, so it is replaced by what it was aiming at: past twenty-four seconds a declared take must never
  coast between authored keys and must resolve by at least the framing change a cut would have had to
  deliver, with a share of the timeline rather than a duration as the wall nothing opens. Both tests
  were confirmed to reject a merge accident and a busy camera that ends framed as it opened;
- the mover had no vertical axis. Its carriage was a fixed-height body whose top sat 45.5 mm inside
  the bridge beam and passed through the rail at travel height, and at the bottom of its stroke the
  nearest bridge body was 66.5 mm above it with no geometry in between, so the same missing part read
  as clipping at one end of the travel and floating at the other. The interpenetration check had not
  been suppressed for that pair by an allowlist or a tolerance: it forms its pairs from movers against
  fixed bodies, the bridge assembly belonged to neither set, and the pair was therefore never
  constructed. The gantry is now a separate assembly from the mover so the question can be asked at
  all, the carriage ceiling is derived from the beam rather than hardcoded, and a truck of two bearing
  blocks with end wipers rides the rail and carries a vertical way, a slide and the drag umbilical.
  A mover-mechanism invariant now walks the carriage-to-track chain at every frame with no gap
  permitted, holds both sliding joints inside the member they ride, and declares the one running fit
  as a documented contact; and
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
- the viewer's demonstration data sat outside every consistency check. The asset tests closed a ring
  around the GLB, the node inventory, the motion report and `twin.yaml`, but nothing compared the
  scene digest and frame ranges the viewer ships against the ones the twin declares, so a scene
  change that updated the definition and not the viewer produced a viewer that refuses its own scene
  in the browser and says so nowhere else. A test now compares both, and it is written so a parse
  that finds nothing fails rather than agreeing with everything;
- the digital-twin architecture described what projection does without stating what it cannot do. A
  cue carries a task and its capability, so only the `Task*` event types can carry a projection rule
  and the twin shows the execute half of a closed loop rather than the decide half. That is a
  property of the cue contract, and the documentation now says so instead of leaving a reader to
  infer that a campaign could be visualised;
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
