# Lab onboarding and durable context

OpenSDL onboarding starts as a normal agent conversation. The `start-here` skill helps a user
describe a laboratory, preserve shared context, and choose the first simulator-backed outcome.
It does not add a wizard, a separate persona, or a second runtime.

## User experience

A user can begin with a fresh conversation or continue an existing one. The first request can be
short:

- “Start setting up our existing characterization lab.”
- “Plan an automated electrolyte formulation cell.”
- “We added a liquid handler. Continue the lab build.”
- “Show me what this workflow would look like before we run it.”

The agent reads the repository before asking questions. It asks for the smallest amount of missing
information needed to define one useful outcome. It can return to broader discovery later.

The conversation follows this sequence:

1. Inspect the current repository, Git state, instructions, and existing lab context.
2. Classify the setup as an existing lab, a new design, or a hybrid.
3. Identify the first workflow or decision the user wants to make.
4. Record confirmed facts, evidence, unknowns, and shared decisions in Git.
5. Map the first workflow to resources, capabilities, simulators, and implementation gaps.
6. Validate executable files that changed.
7. Hand the next task to the narrow skill that owns it.

The agent does not require a complete equipment inventory before useful work begins. A single
workflow can establish the first vertical slice.

## Durable context in a laboratory repository

Generated laboratory repositories contain four shared files:

```text
docs/lab/
├── context.md
├── inventory.md
├── setup-plan.md
└── decisions.md
```

These files are small working records. They remain readable by people and agents. OpenSDL can add
typed forms after real laboratory pilots establish stable fields and lifecycle rules.

| File | Contents | Excludes |
|---|---|---|
| `context.md` | Purpose, users, outcomes, scope, constraints, shared preferences, assumptions, and open questions | Credentials, private chat history, mutable run state |
| `inventory.md` | Reported or planned equipment, compute, locations, evidence, readiness, integration, and visual-twin status | Claims that an item is executable without supporting evidence |
| `setup-plan.md` | Desired workflows, capability gaps, dependencies, simulation stages, acceptance checks, and the lab-specific work list | Product-wide OpenSDL work |
| `decisions.md` | Confirmed choices whose reasons matter to future contributors | Unconfirmed agent guesses or personal notes |

Other authorities remain distinct:

| Information | Authority |
|---|---|
| Executable laboratory configuration | `opensdl.yaml`, workflow files, policy, adapters, and tests |
| Product-wide development work | [Development backlog](../development/backlog.md) |
| Runs, tasks, events, leases, interventions, and artifacts | Configured OpenSDL store |
| Personal preferences and conversation history | User and active agent harness |
| Credentials and private endpoints | Approved secret store or local environment |

Promote a personal preference into `context.md` only when the user confirms it as shared laboratory
practice. Keep sensitive facility details in a private laboratory repository.

## Inventory states

An inventory entry tracks three separate dimensions. This avoids treating a visual model or a
reported instrument as proof of operational readiness.

### Evidence state

- `planned`: the lab may acquire or design the item.
- `reported`: a user states that the item exists.
- `verified`: a person or source confirms identity, location, and relevant specifications.

### Integration state

- `not-started`: no OpenSDL integration exists.
- `simulated`: a simulator covers the intended capability.
- `integrated`: an adapter and conformance evidence exist.
- `commissioned`: the deployment has approved the item for its defined live envelope.

### Visual-twin state

- `none`: no visual representation exists.
- `planned`: the setup plan defines the intended model.
- `draft`: a user-specific scene exists and awaits registration or review.
- `registered`: scene entities map to stable OpenSDL identifiers.
- `validated`: scale, placement, mappings, and declared provenance pass the lab’s checks.

These labels are planning vocabulary in the alpha. A future typed inventory contract will define
their allowed transitions and evidence requirements.

## The `start-here` contract

### Inputs

- the intended outcome or laboratory concept;
- whether the setup exists, is planned, or combines both;
- known equipment, compute, manual work, samples, data, and locations;
- constraints or hazards that affect planning;
- the preferred first workflow;
- available evidence, such as manuals, photographs, layouts, or CAD; and
- repository name, owner, and destination when a new laboratory repository is required.

The agent can begin with partial input. It marks facts as confirmed, assumed, or unknown.

### Outputs

- a situation classification;
- updated shared context files;
- a first-workflow capability map;
- a simulator-first setup sequence;
- named gaps and dependencies;
- validation evidence for executable changes; and
- a clear handoff to the next repository skill.

### Current actions

The current release can:

- create a laboratory repository with `opensdl init`;
- validate manifests and workflows with `opensdl validate`;
- generate capability cards, adapter packages, and domain packs;
- develop and execute workflows through the reviewed simulation helper; and
- inspect declared configuration without opening the runtime store;
- validate a versioned twin definition and its scene digest with `opensdl twin validate`;
- project persisted run events into deterministic visual cues with `opensdl twin project`; and
- serve a verified GLB and read-only viewer through the OpenSDL API.

Typed equipment inventory, automated custom-scene authoring, commissioning, live control, and
read-only live twin projection remain future work. A user or agent can author a custom Blender scene
in the laboratory repository and bind it through the current alpha twin contract.

OpenSDL includes one reference surrogate-cell scene to test this path. Generated laboratory
repositories do not receive a model catalog or generic equipment assets. The reference is an
original, real-scale Flex-class reconstruction with a full authored workflow sequence.

### Stop conditions

Stop before mutation when the destination or repository owner is unclear. Stop when facts conflict
or a required source is missing. Keep secrets and unintended facility details out of Git. Do not
turn an inventory claim into a live adapter binding without integration and commissioning evidence.
Do not perform a physical action through the onboarding procedure.

## Skill handoffs

| Need | Skill |
|---|---|
| Create a separate laboratory repository | `create-lab` |
| Inspect declared state in an existing lab | `orient-lab` |
| Scope the physical and interface design | `design-lab` |
| Define a new semantic operation | `add-capability` |
| Connect or simulate an executor | `add-adapter` |
| Build and test the first workflow | `develop-workflow` |
| Add scientific data contracts | `add-domain-pack` |
| Diagnose persisted execution evidence | `debug-run` |

The same agent can use these skills in sequence. The names describe procedures rather than separate
operators.

## Example journeys

### Existing laboratory

The user lists a balance, liquid handler, spectrometer, and workstation. The agent records each item
as `reported`. It selects one workflow and identifies the simulator, adapter, calibration, and data
gaps. It does not mark the physical instruments as executable.

### New cell

The user describes an intended formulation and characterization loop. The agent records the target
outcome, creates a separate lab repository after destination confirmation, and maps the loop to
simulated capabilities. Equipment choices can remain planned while workflow logic develops.

### Continuing work

A fresh agent reads the shared context and learns that sample identifiers must come from the LIMS.
It reads the decision reason, records a newly reported robot, and updates the setup plan. No prior
conversation transcript is required.

### Visual planning

The user asks to see the cell operate before construction. The agent records the model purpose,
available dimensions, evidence sources, desired workflow preview, and missing measurements. A user
or agent builds one custom Blender scene in that laboratory repository. The current twin contract
binds its stable entities and anchors, projects a simulated run, and serves the read-only replay.
Automated scene generation and engineering-grade robotics validation remain separate work.
