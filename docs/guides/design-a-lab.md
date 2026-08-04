# Designing a laboratory

OpenSDL is a framework, not a laboratory. It supplies typed capabilities, adapters, provenance, and a
closed campaign loop. It does not decide what your plant looks like, which mechanisms it uses, or
which hazards govern it. Those decisions follow from the material system, the throughput, and the
safety case, and they differ in every deployment. OpenSDL ships no equipment catalog for that reason.

This page is the method for making those decisions: how to decompose a laboratory into parts that can
be decided separately, how to tell which requirement actually drives a design, and how to spend
engineering effort where it cannot be recovered. It applies to a synthesis cell, a characterization
line, a formulation loop, or a single instrument with an autosampler.

## Start from the decision, not the equipment

The common failure is to inventory equipment first and derive workflows from what is available. A
self-driving laboratory is defined by the loop, so begin there:

1. What decision does the loop make?
2. What measurement informs that decision?
3. What is the shortest sequence of operations that produces that measurement?
4. What is the cycle time, and how many cycles before the decision is trustworthy?

Answering the fourth question early is what keeps a design honest. A loop that needs two hundred
cycles to converge and runs one cycle a day is a three-year experiment, and no amount of automation
inside the cycle fixes that. Either the cycle gets faster, the sample count per cycle grows, or the
decision needs a different measurement.

### The minimum viable loop

Build the smallest sequence that closes the loop end to end, even when most of its steps are manual
or simulated. One complete cycle that closes is worth more than a fully automated open loop, because
only a closed loop reveals which step actually limits it.

Then automate in order of what limits you: the slowest step, the least reliable step, or the step
whose variability dominates the measurement. Automate the most impressive step last. OpenSDL is
built for this order — a workflow can bind a simulator, a compute step, or a structured human task
for any capability that has no adapter yet, and the loop runs regardless.

## Separate the four layers

Decompose the laboratory so each decision lands where it belongs and changes at its own rate.

| Layer | Question it answers | Rate of change |
|---|---|---|
| Plant | Physical machine, containment, zoning, utilities, environment | Years, largely irreversible |
| Interfaces | What connects to what, mechanically, electrically, and in data | Years, once conforming parts exist |
| Capabilities | Typed semantic operations and their contracts | Months |
| Campaigns | Workflows, objectives, optimizers, policy | Days |

OpenSDL owns the lower two layers and gives them versioned contracts. The upper two are yours, and
they are the expensive ones. A decision that belongs in the plant layer but gets made in the campaign
layer becomes permanent by accident.

The framework's own architecture rules mirror this split. Vendor and facility behavior belongs in
adapters, business logic stays in packages, and applications only compose. A physical constraint that
leaks into workflow logic is the same category of mistake.

## Name the functions before the parts

Any component does several jobs at once. Write them down separately before choosing a mechanism.

A joint locates, preloads, transmits, transitions between states, and reports which state it is in. A
station contains, positions, actuates, measures, cleans, and verifies. A transfer moves, holds,
releases, and proves it released.

Most weak designs come from one feature serving several functions, so improving one degrades another.
When requirements conflict inside a single part, that conflict is the signal to look for an
architectural split rather than a more clever part. Separating the zone that sees the material from
the zone that carries the precision is usually cheaper than a component that survives both.

## Find the binding constraint

Requirements are not equal. One binds and the rest have slack, and the design belongs to the one that
binds. For each requirement, estimate the margin between what you need and what the obvious solution
delivers. The smallest margin is the design driver.

This matters most when borrowing a design from another field. A mechanism perfected where structural
load binds will be optimized for stiffness and mass, and it will carry that optimization into a
laboratory where the payload is a few hundred grams and the real constraints are repeatability,
cleanability, and cycle life. The mechanism still works. It is simply solving a problem you do not
have, at a cost you do pay.

State the binding constraint explicitly in `docs/lab/decisions.md`. It is the fact most likely to be
forgotten and most likely to invalidate the design when the material system changes.

## Best practice is conditional on the material system

A design that is correct in one laboratory can be actively hazardous in another. This is the single
most important idea on this page.

Exact-constraint couplings, open precision surfaces, magnetic preload, pneumatic actuation, and
elastomer seals are all standard practice somewhere, and each of them fails badly in at least one
common laboratory environment. Maturity in another field is not transferability.

Before adopting any pattern, list the environmental assumptions it silently makes. If your material
system violates one, the pattern does not transfer.

| If the material system | Reconsider |
|---|---|
| Holds or generates static charge | Insulating surfaces, make-and-break electrical contact, dry atmospheres, ungrounded conductors |
| Is particulate | Exposed precision surfaces, sliding and rolling contacts, crevices and threads, magnets, upward-facing ledges |
| Is corrosive or solvent-bearing | Seals, elastomers, coatings, adhesives, and the compatibility of the cleaning agent itself |
| Is air or moisture sensitive | The enclosure atmosphere becomes part of the plant rather than an accessory |
| Is biologically active | Cleanability, single-use paths, and containment level dominate mechanism choice |
| Is thermally or shock sensitive | Actuator placement, heat sources, acceleration limits, dwell time |
| Is toxic, energetic, or radiological | Containment, inventory limits, remote operation, and an independent safety system become primary |
| Is viscous, sticky, or hygroscopic | Transfer method, dosing accuracy, and residue carried between samples |

Several rows can apply at once, and when they conflict, that conflict is a plant-layer decision, not
a component-layer one.

For any material system with a recognized hazard class, treat this table as a prompt for a qualified
review rather than a substitute for one. Hazard analysis, material compatibility determination, and
the safety case require domain engineers and the governing standards for your jurisdiction.

## What a mature field declines to do is evidence

Survey adjacent fields for what they build. Then pay closer attention to what they consistently do
not build.

When an obvious approach is absent from a mature market, a reason is usually encoded in that absence:
a cleaning burden, a wear surface, a contamination path, an error mode that only appears after ten
thousand cycles. Find the reason before you take that road. You may still take it — the constraint
may not apply to you, or may be worth accepting — but take it knowingly and record why in
`decisions.md`.

## Spend effort on one-way doors

This is the mechanism for avoiding over-engineering without under-building. Classify every decision
by whether it can be revised later.

| Irreversible | Reversible |
|---|---|
| Structural stiffness and geometry | Mechanism internals |
| Motion envelope, payload, and reach | Tooling and consumable details |
| Containment, zoning, and environmental control | Scheduling and orchestration |
| Utility routing capacity | Optimizer and objective |
| Published interfaces, once parts conform to them | Adapters and simulators |
| Safety architecture | Analysis and reporting |
| Sample and run identity | Almost all software |

Over-engineering is effort spent on reversible decisions. Under-engineering is skipping the
irreversible ones. Most projects do both at the same time: an elaborate scheduler on a frame that
cannot carry the second-generation tool.

Decide reversible things quickly and revise them with evidence. Give irreversible things deliberate
design time and outside review.

### Over-provision the irreversible axes

Headroom on an irreversible axis is cheap at design time and impossible afterward. Size payload,
stroke, working area, power, data bandwidth, and slot or dock count for the laboratory you expect in
five years, not for the first workflow.

Do not size the plant for the first workflow. The first workflow is the one you understand best and
the one least representative of what the laboratory eventually does.

## The interface is the extensibility mechanism

Extensibility comes from specified interfaces, not from flexible implementations. This is why OpenSDL
publishes versioned capability contracts and generates JSON Schemas from them, and the same
discipline applies to the physical layer.

Write down the interface a new instrument, tool, or module must conform to: mounting geometry and
datums, mass and envelope limits, power budget, data bus, service connections, and the states each
side must report. Version it. Keep it in the laboratory repository beside the manifest so it is
reviewed like any other contract.

Then over-specify it relative to today's need, and prefer standard buses and connectors over bespoke
ones. A conforming instrument is built against a document instead of negotiated against a machine,
and that difference is what lets a laboratory grow without a redesign.

## Unattended operation changes what must be verified

A person standing at a bench is a sensor, a supervisor, and a recovery mechanism. Removing them turns
every implicit check into one that must be made explicit.

- The machine must know its state, not infer it from the last command it sent.
- Anything whose silent failure ends a campaign or creates a hazard deserves two sensors on different
  physical principles, because a single sensor failing into a plausible reading is the case that
  costs you a week.
- For every error path, ask what physical state the machine is left in, not only how it reports.
- Record enough evidence to reconstruct a failure without a witness. OpenSDL's event history,
  artifacts, and provenance exports exist for this.

The same principle produced the reference digital twin's spatial invariants: a check the machine runs
against itself is worth more than a check a person remembers to perform.

## Keep the orchestration layer out of the safety path

Safety functions belong in an independent, rated system that the orchestration layer cannot outvote.
Interlocks, emergency stop, and access control are decided by that system; OpenSDL commands within an
envelope it enforces.

This is not only a safety argument, it is what keeps the flexible layer flexible. Any system inside
the safety path must be revalidated whenever it changes, which is incompatible with a campaign layer
that changes daily. [Validation](../development/validation.md) records that OpenSDL is not qualified
for hazardous physical control. The architecture above is how that stays true rather than becoming a
gap to close.

## Record the decision, not only the choice

`docs/lab/decisions.md` exists so a future contributor can tell whether a decision still holds. A
choice without its reason cannot be re-evaluated, so it either survives past its usefulness or gets
reversed without anyone knowing what it was protecting.

For each decision worth keeping, record:

- what was chosen;
- what was rejected, and what it would have cost;
- which constraint drove it; and
- what would change your mind.

The last item is the most useful and the most often omitted. A design constraint that names its own
expiry condition — a different material system, a payload above some limit, a throughput target —
tells the next contributor exactly when to revisit it.

## A working sequence

1. State the decision the loop makes and the measurement that informs it.
2. Define the minimum viable loop and close it, with simulated or manual steps where needed.
3. Separate plant, interface, capability, and campaign decisions.
4. For each component, name its functions before choosing a mechanism.
5. Identify the binding constraint and design for it.
6. Check every borrowed pattern against your material system's properties.
7. Classify decisions as reversible or irreversible; over-provision the irreversible axes.
8. Write and version the interface specification.
9. Make state observable, and give unattended failure modes diverse verification.
10. Put safety functions in an independent rated system.
11. Record decisions with their driving constraint and their expiry condition.

## What OpenSDL decides and what you decide

| OpenSDL provides | Your laboratory decides |
|---|---|
| Typed capability contracts and versioned schemas | Which operations your science needs |
| Adapter and simulation structure with conformance tests | The equipment, mechanisms, and vendors |
| Runs, events, artifacts, and provenance | Which evidence proves a result |
| Campaign loop, optimizers, and policy | The objective and the stopping rule |
| A digital-twin contract for a lab-specific scene | The plant, its layout, and its geometry |
| Repository structure and agent skills | Hazard analysis, the safety case, and commissioning |

Start with [Create a laboratory](create-lab.md) to make the repository, and
[Onboard a laboratory](../architecture/lab-onboarding.md) to record the context this method produces.
