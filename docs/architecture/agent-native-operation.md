# Agent-native operation

OpenSDL should work through a normal repository conversation in Codex, Claude Code, or another
capable harness. A user can ask one agent to inspect a lab, develop a workflow, run a simulator,
diagnose a failure, or change the platform. CLI, API, SDK, and MCP coverage currently differs. Phase
2 aligns their typed simulator operations.

OpenSDL's default remains the normal conversation supplied by the user's harness. An optional
future custom harness would be an external client of the same typed interfaces, not a required
OpenSDL UI or service.

## Accepted decisions

| Decision | Result |
|---|---|
| One conversational entry point | A user needs no separate development, workflow, monitoring, or maintenance persona. |
| Operator-agnostic platform | Humans, scripts, services, optimizers, and agents use the same contracts. |
| Two shared systems of record | Git holds intended implementation. OpenSDL storage holds execution evidence. |
| Private conversations | Chat history stays with each user and workstation. It is not shared project state. |
| Native harness controls | The active harness owns file, shell, network, Git, and service approvals. |
| OpenSDL laboratory controls | Manifests, policy, leases, runtime state, and provenance govern laboratory actions. |
| Progressive friction | Simulation and reversible changes stay fluid. Consequential actions add controls at the typed boundary. |
| Simulation-first substitution | A physical adapter replaces one simulated capability at a time and retains conformance coverage. |

Harness-specific files exist only to expose the same project instructions and skills.

## User experience

The default experience stays conversational:

1. Start or resume a normal agent in the repository.
2. Ask it to start here, report the current lab state, or pursue a concrete outcome.
3. Let the agent select the relevant repository skill and typed interfaces.
4. Review native harness prompts when the requested action crosses a configured permission boundary.
5. Receive the result with repository changes, run identifiers, tests, and evidence as applicable.

The user can bypass the conversational entry point and call the same interfaces directly. OpenSDL
does not require a dashboard, persistent context strip, shared chat service, or visible operator
taxonomy.

## State and collaboration

| State | Authority | Shared through |
|---|---|---|
| Code, manifests, workflows, policy, tests, shared lab context, and reviewed decisions | Git revision | Branches, commits, pull requests, and releases |
| Runs, tasks, events, resources, leases, interventions, and artifacts | Configured OpenSDL store | One deployed controller and its typed interfaces |
| User intent, preferences, and conversation history | User and active harness | Private local or provider conversation storage |
| Credentials | User, harness, or deployment secret store | Approved secret channels |

Local SQLite state is scratch execution state. Users do not merge it through Git. Multiple users
share operational state when they target the same deployed controller.

### Fresh conversation

A fresh agent reads the nearest `AGENTS.md`, Git state, shared files under `docs/lab/`, the selected
manifest, and the relevant skill. `start-here` establishes missing context; `orient-lab` summarizes
declared status. The agent validates declared configuration before changing the lab. Runtime health
queries remain explicit because current controller-backed reads can initialize or update the store.
The agent can reconstruct shared state without a previous transcript.

### Continuing conversation

A continuing agent can use private conversation context for intent. It refreshes the worktree,
tests, and manifest before acting. It refreshes health and run evidence when the task needs
operational state, with the current query side effects disclosed. Current Git and runtime records
take precedence over stale conversational claims.

### Different users

Each user works through a private conversation and a separate clone or worktree. Git handles
implementation collaboration. A shared controller handles operational concurrency and evidence.
Actor-attributed events will support shared deployments after server-derived identity exists.

## Responsibility boundary

| Agent harness | OpenSDL |
|---|---|
| Conversation and user preferences | Laboratory manifest and capability inventory |
| File edits, shell, Git, branches, and pull requests | Workflow and capability validation |
| Workspace sandbox and command approval | Simulation and adapter execution |
| Network and external-service approval | Environment and risk policy |
| User-provided local secrets | Resource leases and concurrency |
| Repository review | Laboratory provenance and postconditions |

A shell approval permits a local command under the harness policy. Laboratory authorization still
depends on the configured OpenSDL environment and policy. Physical safety also depends on equipment
interlocks and reviewed operating procedures.

## Repository instruction architecture

`AGENTS.md` contains compact rules that apply throughout a directory tree. Repository skills cover
one recurring procedure each. Typed interfaces define exact behavior and consequences. CI enforces
portable rules.

The canonical skills live under `.agents/skills/` and follow the open Agent Skills format. Claude
Code reads the same skills through `.claude/skills/` symlinks. Adjacent `CLAUDE.md` files import each
scoped `AGENTS.md`. See [Agent instructions and skills](../development/agent-skills.md) for the
authoring standard.

Skills can span the full lifecycle. They are capabilities available to one broad agent, not
separate agent roles.

## Capability plan

The skill catalog should grow only after the required typed behavior exists.

| Lifecycle area | Current procedure | Next typed dependency |
|---|---|---|
| Onboard | Record confirmed context and map one useful workflow with `start-here` | Typed inventory and first-workflow planning results after lab pilots |
| Orient | Read Git and the manifest; validate declared configuration; disclose state-touching runtime queries | One genuinely read-only CLI context command and run listing |
| Develop workflows | Edit, validate, test, and run through a simulation manifest | Structured validation and submission parity across interfaces |
| Diagnose runs | Inspect persisted tasks and events; reproduce in simulation; export evidence | Typed intervention, resume, and reconciliation contracts |
| Extend the platform | Add capabilities, adapters, domain packs, tests, and schemas | More conformance profiles as integrations arrive |
| Release | Build and test distribution candidates | Signing, SBOM, publication, and tag automation |
| Operate shared simulation | Available through API and selected CLI commands | Identity, transport parity, polling, and concurrent run controls |
| Operate live equipment | Deferred | Hold, cancel, abort, acknowledgement, safe-state, and postcondition contracts |
| Manage deployments | Deferred | Deployment API, environment identity, health, revision, and rollback contracts |

## Phased execution plan

### Phase 1: repository and skill contract

Deliver the instruction hierarchy, harness compatibility adapters, authoring standard, current
skills, and generated-lab skill baseline. Validate syntax, command accuracy, scaffold output, and
fresh-session behavior.

Exit evidence:

- Codex and Claude Code discover the same canonical skills.
- A generated lab contains enough guidance for orientation and simulator workflow development.
- A local wheelhouse supports a same-workstation generated-lab smoke test.
- Generated CI validates agent contracts without OpenSDL packages and visibly skips full checks.
- A stable registry or committed artifact source makes generated lockfiles and full CI portable.
- Every documented command exists in the current CLI.
- CI detects malformed skills and broken compatibility adapters.

### Phase 2: typed simulator interface parity

Add a machine-readable CLI context command, run listing, structured workflow submission, event
queries, inspection, and export parity across CLI, API, SDK, and MCP. Normalize success, denial,
failure, and intervention responses.

Exit evidence:

- One interface-neutral test completes context, validation, run, inspection, and export.
- Each transport reaches the same controller and runtime paths.
- Skills no longer need to infer run state from human-formatted output.

### Phase 3: fresh-agent and collaboration pilot

Run a full simulator task from a fresh conversation in a generated lab. Modify a workflow, add a
test, execute it, diagnose an injected failure, and export evidence. Repeat from a second user
worktree against shared operational state.

Exit evidence:

- Two fresh conversations reconstruct the same Git and runtime state.
- Git resolves implementation conflicts.
- The controller resolves run and resource concurrency.
- The pilot needs no synchronized chat history or hidden handoff file.

### Phase 4: shared simulator deployment

Deploy one shared controller with persistent storage. Add server-derived actor identity, separate
user or workstation credentials, actor-attributed events, and simple environment policy. Keep local
conversations private.

Exit evidence:

- Two users submit and inspect runs with trustworthy actor attribution.
- Leases control concurrent resource use.
- Restart recovery and artifact export work against shared storage.

### Phase 5: first live equipment capability

Select one low-risk device with independent safeguards. Keep its simulator, add hardware-in-loop
tests, define a narrow capability envelope, and use a separate live manifest. Add typed hold,
cancel, abort, acknowledgement, and intervention behavior before general live operation.

Exit evidence:

- Out-of-range and denied actions dispatch no equipment command.
- Ambiguous acknowledgement creates an intervention and no automatic replay.
- Fault tests cover disconnect, timeout, cancellation, restart, and resource conflict.
- Independent physical interlocks work when OpenSDL is unavailable.

### Phase 6: optional resident harness

Treat a custom harness as a separate optional client only after normal agents expose measured gaps
in persistence or unattended monitoring. Normal Codex, Claude Code, and other harness conversations
remain supported. The optional harness consumes the same API or MCP surface and cannot bypass
runtime policy.

Exit evidence:

- Standard and custom harnesses pass the same interface-neutral tests.
- A harness restart loses no operational state.
- The harness cannot expand its configured policy envelope.

## Current deferrals

The alpha does not claim asynchronous monitoring, alerts, deployment management, authenticated
multi-user identity, or complete live-equipment control. The current CLI has no `context`, run
list, hold, cancel, abort, resume, deploy, or commission command. It can now read a campaign —
`campaign list` and `campaign inspect`, and the same two through the API, the SDK and the tool
catalogue — and start one in the foreground. There is no detached submission and no way to stop
a campaign remotely; both wait on a supervisor design rather than a command. Reconciliation is
reachable as `doctor --reconcile`, which reports what it moved.

Skills for those tasks remain deferred until typed contracts, tests, and evidence exist. This keeps
the conversational surface broad without turning procedure text into an unsupported control plane.

See [lab onboarding](lab-onboarding.md), [lab-specific digital twins](digital-twin.md), and the
[development backlog](../development/backlog.md) for the current framework-wide work list.
