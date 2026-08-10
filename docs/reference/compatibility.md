# Compatibility and versioning

This page states what OpenSDL guarantees across releases, which surfaces are public contracts, how a
breaking change is announced, what a deprecation looks like, and what a laboratory should pin.

It is written against the code as it exists. Where the honest answer is that no guarantee exists yet,
this page says so and names the work that guarantee would require. Nothing here is enforced by CI
except workspace version equality.

## Version numbering

Every distribution in the workspace carries one version and releases together. The current version is
`0.1.0a0`.

`scripts/check-version.py` enforces that the root `pyproject.toml` version, all workspace member
versions, `CITATION.cff`, and the `opensdl-*` dependency floors written into generator templates are
the same string. It does not parse the version, so it checks neither PEP 440 validity nor
monotonicity, and it relates the version to neither the changelog nor a Git tag. It detects a typo,
not a breaking change.

No Git tag exists in the repository, and the release workflow is manually triggered, builds the 22
distributions, and uploads them as a workflow artifact without publishing or tagging. The version has
so far identified a working tree rather than a release, and a laboratory cannot install OpenSDL from
an index at all. [Releasing and publishing](../development/releasing.md) states what changing that
would require and which parts of it cannot be undone.

Semantic versioning applies after 1.0. Before 1.0 the version communicates ordering only.

## What pre-1.0 guarantees are

- Changes are recorded in [`CHANGELOG.md`](https://github.com/fl-sean03/OpenSDL/blob/main/CHANGELOG.md)
  under `Unreleased` until a release is cut. No check enforces the entry.
- Generated JSON Schemas are regenerated and committed in the same change that alters a model, and
  `make lint` fails if they are stale.
- The reference campaign and the digital-twin surrogate overlay execute in CI on every change, so
  the shipped examples work at the commit that ships them.
- Known gaps are recorded in the [development backlog](../development/backlog.md) and the
  [repository audit](../development/audit-2026-08-05.md) rather than omitted.

## What pre-1.0 guarantees are not

- No contract on this page is stable between releases. A manifest field, a capability identifier, a
  CLI flag, an HTTP response body, an SDK method, or a database column may change or disappear in
  the next release.
- There is no deprecation window. Nothing in the repository emits a `DeprecationWarning`, and no
  deprecation has been issued.
- No migration is guaranteed to exist for any contract change other than the database schema,
  which does upgrade in place. See below.
- There is no cross-version test suite. Nothing verifies that a release reads data written by its
  predecessor. [`ROADMAP.md`](https://github.com/fl-sean03/OpenSDL/blob/main/ROADMAP.md) makes 1.0
  conditional on a compatibility suite with external adopters; that suite does not exist and is not
  yet designed.
- No version is supported for production operation. See
  [`SECURITY.md`](https://github.com/fl-sean03/OpenSDL/blob/main/SECURITY.md).

## Public surfaces

These are the contracts a laboratory can depend on, and what each carries today.

| Surface | Defined by | Stability today |
|---|---|---|
| Manifest `apiVersion` | `LabManifest` in `opensdl-schemas` | Pinned to `opensdl.dev/v0alpha1`. No second version exists. |
| Manifest secret references | `${env:NAME}` resolved by `load_manifest` | The `${provider:name}` form is stable. Only `env:` is implemented; another prefix is refused by name. |
| Twin `apiVersion` | `TwinDefinition` in `opensdl-twin` | Pinned to `opensdl.dev/v0alpha1`. No second version exists. |
| Generated JSON Schemas | `packages/schemas/jsonschema/`, 16 files | Regenerated on every model change. No identity, no version, no compatibility check. |
| Capability contracts | `CapabilityDefinition` and the identifiers adapters declare | No guarantee. Identifiers are plain strings and there is no registry. |
| Adapter plugin interface | `CapabilityAdapter`, entry-point group `opensdl.adapters` | No guarantee. Abstract methods may be added. |
| Optimizer plugin interface | `Optimizer` protocol in `opensdl-core`, group `opensdl.optimizers` | No guarantee. `suggest(history)` and `observe(observation)` are still the whole requirement; `BatchOptimizer`, `ConfigurableOptimizer`, `StatefulOptimizer` and `ResumableOptimizer` are optional and detected by `isinstance`, so adding a member to any of them silently stops matching every plugin that implements the others. It moved out of `opensdl-runtime` so a plugin depends on the contract rather than the execution stack; `opensdl-runtime` re-exports every name. |
| Optimizer contract documents | `CampaignProblem`, `Suggestion`, `CampaignObservation` in `opensdl-core` | No guarantee on the fields, but each is now a typed model with a generated schema and its own serialisation, so what a plugin exchanges and what the event stream records are one document. See below. |
| Workflow of record | `RunCreated.payload.workflowDigest` | The digest is the canonical-JSON SHA-256 of `RunCreated.payload.workflow`, recomputable by any reader. A resume presenting any other workflow is refused. |
| Domain-pack interface | `get_pack()`, group `opensdl.domain_packs` | No guarantee. The return value is an untyped mapping. |
| CLI | `opensdl` commands and options | No guarantee. Output is human-readable text and JSON with no declared shape. |
| HTTP API | 18 routes in `opensdl-api` | No guarantee. No version prefix, no content negotiation, no authentication. |
| Python SDK | `OpenSDLClient` in `opensdl` | No guarantee. It is a thin wrapper over the HTTP routes and moves with them. |
| Database schema | `opensdl-storage` models and `opensdl_storage/migrations/versions/` | No guarantee on the shape. Every change ships an Alembic revision that upgrades in place. See below. |

### Both `apiVersion` fields are hard pins

`LabManifest.api_version` and `TwinDefinition.api_version` are declared as
`Literal["opensdl.dev/v0alpha1"]`, and both models set `extra="forbid"`. Together those two facts
mean:

- a document declaring any other `apiVersion` is rejected rather than dispatched;
- a document containing any field a given release does not know is rejected rather than ignored;
- therefore an older reader cannot read a newer document, even when the only difference is an added
  optional field.

There is no version dispatch and no converter anywhere in the repository. `load_manifest` parses YAML
and validates one model. The consequence is that a future `v0alpha2` cannot be introduced additively:
it requires a loader that inspects `apiVersion` before validation and a converter for each supported
prior version. That work does not exist and is not scheduled.

### Generated schemas are not identified

The 16 files under `packages/schemas/jsonschema/` are produced by
`uv run --locked python scripts/generate-schemas.py`. None of them contains `$id`, `$schema`, or any
version field, so a consumer holding one has no way to say which schema it is or which release
produced it.

The CI drift check compares committed bytes against freshly generated bytes with
`filecmp.cmp(..., shallow=False)`. It answers one question: were the schemas regenerated? It does not
compare a schema against its predecessor. Removing a required field from a public model passes CI as
long as the schemas were regenerated in the same commit.

Making these schemas useful as contracts requires an `$id` per schema, a `$schema` declaration, and a
comparison against the previously released schema rather than against the working tree.

### A run's workflow of record is pinned by digest

`RunCreated` embeds the whole workflow definition the run was asked to execute and, beside it, the
canonical-JSON SHA-256 of that embedded document as `workflowDigest`. The canonicalisation is
`opensdl_core.canonical_json` — sorted keys, no separator whitespace, ASCII escapes — the same one
the twin binding uses, so any reader holding `RunCreated.payload.workflow` can recompute the digest
and check it.

Resuming a run means presenting that same document. A submission carrying any other workflow is
refused with a `LifecycleError` naming both digests, which the HTTP API reports as `409`. This
closes the second half of a defect whose first half — resubmitting over a `completed` or `aborted`
run — was closed by lifecycle enforcement: a `failed` or `intervention_required` run could still be
resumed with a different step list, and the resulting run's own record described work it had not
done.

A run recorded before `workflowDigest` existed carries the workflow document without the digest.
Its digest is recomputed from that document, so such a run is neither refused nor exempted.

The path for a repaired workflow is `supersedes`. It mints a new run that names the run it replaces,
records `supersedes` in the new run's `RunCreated`, and appends `RunSuperseded` to the replaced run
naming the replacement, its workflow digest, and the operator making the claim. The replaced run's
state, outputs, tasks and operator are untouched: it remains the record of what was submitted then.
`supersedes` cannot be combined with a `run_id` that already names a run, because that submission is
a resume and superseding exists precisely to leave the old record alone.

Recorded as decision **4** in the [repository audit](../development/audit-2026-08-05.md).

### A run is claimed once

Moving a run to `running` is one conditional `UPDATE` at the store, over the states the declared
machine permits a start from — `planned`, `queued`, `paused`, `intervention_required`, `failed`.
`running` is not one of them and never was, but `validate_run_transition` returns early when the
current and target states are equal, so a check-then-act through `update_run` let two callers both
observe `running` and both proceed. Exactly one caller now wins, and the bound is the store's rather
than the process's, so it holds across controllers and both supported backends.

A run left `running` by a stopped controller is therefore not directly resumable. Reconciliation
moves it to `intervention_required` — where a person establishes what the equipment did — and that
is what `opensdl doctor --reconcile` and `opensdl run` already perform.

This is one instance of a class the repository has not finished with: the backlog's item on
trustworthy multi-user leases, run ownership and concurrent submission tests covers the rest,
including `acquire_leases`, which still checks every lease and then writes them in two passes.

### The optimizer contract is exchanged as schema'd documents

`CampaignProblem`, `Suggestion` and `CampaignObservation` are what an optimizer plugin is configured
with, returns, and is given back. Each is also written into the durable event stream. They are typed
models with generated schemas, and the event payloads are their own serialisation rather than a
hand-written mapping beside them, so a consumer validating a recorded document and a plugin author
reading the schema are looking at the same thing.

`CampaignObservation` and `Suggestion` spell the recorded document in camelCase — `runId`,
`constraintViolations`, `acquisitionFunction`, `evidenceRunIds` — because that is what the campaign
event stream already used. Python attribute names are unchanged, and both spellings validate.

`IterationDecision` deliberately has no schema. Nothing serialises one: the runner writes a
`Decision` plus loose keys into `DecisionRecorded` and projection reads that back, so a published
schema would describe a document no writer produces. `Objective`, `SearchSpace`, `Parameter` and the
two constraint types are components rather than documents and appear as `$defs`. `CampaignRecord`
and `CampaignResult` live in `opensdl-runtime`, which `opensdl-schemas` may not import; the campaign
read model is served over HTTP and carries the same guarantee the rest of that API does, which is
none.

Recorded as **B7** in the [repository audit](../development/audit-2026-08-05.md).

### Capability versions are recorded but never used

`CapabilityDefinition.version` and `WorkflowDefinition.version` exist and default to `0.1.0`. A
workflow step names a capability by identifier only, so it cannot request a version, and nothing in
the runtime reads `CapabilityDefinition.version`. Only `workflow.version` is read, and only to stamp
it onto the run record. Changing a capability's input or output schema is therefore invisible to
every workflow that already uses it.

### The database schema upgrades through Alembic

`Database.initialize()` runs the migration history. Alembic is the only writer of the schema: it
creates a store that does not exist, and it moves one that does. So a laboratory is upgraded when it
is opened for writing, whether or not anyone asks. `opensdl migrate` is the explicit form, with
`--check` reporting pending revisions without applying them; it wraps
`opensdl_controller.migrate.plan` and `opensdl_controller.migrate.upgrade`, which are what exists
until that command lands in `packages/cli`.

A store created before this was true carries the declared tables and no `alembic_version`. It is
**adopted** rather than rejected — stamped at the revision its contents correspond to, then upgraded
from there — so a laboratory that has already run keeps working without an operator running
`alembic stamp` by hand. Nothing is dropped and nothing is recreated.

This replaces `create_all()` plus a hand-written `"0001"` row in a `schema_versions` table. That
value was never compared against anything and was not Alembic's `alembic_version`, so the shipped
revision was unreachable from any command, and the two paths had already diverged: `create_all()`
honours `index=True` and revision `0001` created no indexes, so the same release shipped two schemas
differing by 23 indexes. `tests/integration/test_migrations.py` now compares the database Alembic
produces against `Base.metadata` with the same comparison `alembic revision --autogenerate` uses, so
that class of divergence fails a test rather than shipping.

What this does **not** give you: there is still no cross-version test suite, so nothing verifies
that a release reads data written by its predecessor beyond the schema comparison above, and no
downgrade is supported as a data-preserving operation. Back up before upgrading OpenSDL.

Recorded as **E1** in the [repository audit](../development/audit-2026-08-05.md).

## Announcing a breaking change

A change is breaking when a laboratory that worked against the previous release stops working
without editing its own files. Renaming or removing a manifest field, a capability identifier, a CLI
flag, an HTTP route, an SDK method, a schema property, or a database column is breaking. Adding an
optional manifest or twin field is also breaking, for the reason given above.

From this policy forward, a breaking change is recorded in `CHANGELOG.md` under a `Breaking` heading
in the release entry, naming the surface, the previous behavior, the new behavior, and the action a
laboratory must take.

### Unreleased breaking changes

These are the events created since the policy was written. Each is also in `CHANGELOG.md`.

| Surface | Previously | Now | What a laboratory does |
|---|---|---|---|
| Manifest values containing `${env:...}` | Passed through as literal text | Resolved from the environment, or refused when the variable is unset or empty | Set the variable, or write the value if the text was meant literally — it can no longer be expressed |
| `CapabilityDefinition.retry_safety` | Did not exist; any failed dispatch was repeated within `max_retries` | Defaults to `not_repeatable`, which forbids automatic repeats | Declare the retry safety each capability actually has; a simulator or pure computation declares `repeatable` |
| `max_retries` above zero | Accepted on any capability | Refused when the same definition declares `retry_safety: not_repeatable` | Declare a retry safety that permits repeats, or set `max_retries: 0` |
| A task that times out | Recorded `failed`, and a resume re-dispatched it | Recorded `intervention_required` unless the capability declares `repeatable`, and the run over it likewise | Nothing for a `repeatable` capability. Otherwise a person establishes what the equipment did and submits the remaining work as a new run |
| A store behind a destructive revision | Migrated silently on any write | Refused, with `opensdl migrate` as the opt-in; `0002` is exempted by name because every laboratory passes through it | Back the store up and run `opensdl migrate` |
| A `deny` rule an earlier `allow` fully covers | Loaded and never fired | Refused at load with both rules named | Give the deny a lower priority number than the allow, or narrow the allow |
| `DecisionRecorded` event | Written after the run, only for a successful iteration, carrying its score; `evidence_run_ids` named the run it caused | Written before the run, for every proposed candidate, carrying acquisition provenance and no score; `evidence_run_ids` names the runs it rested on | Nothing — projection reads both forms |
| Campaign event types | Five types | Adds `CampaignIterationCompleted` and `CampaignCandidateRejected` | Nothing, unless you consume the event stream by type |
| Optimizer contract location | Imported from `opensdl_runtime` | Defined in `opensdl_core`; `opensdl_runtime` re-exports every name | Nothing. Change a plugin's dependency to `opensdl-core` to stop pulling in the execution stack |
| `CampaignDefinition` | Declared the stopping rules only | Adds `objectives`, `search_space`, the constraints, `batch_size` and `max_parallel_runs`, and refuses a definition declaring both `objectives` and a non-default `score_output`/`minimize` | Nothing, unless a definition sets both — state the direction and output path on each objective instead |
| Running one `campaign_id` twice | Emitted a second `CampaignStarted` and restarted iteration numbering at zero | Refused, naming `resume=True` | Pass `resume=True` to continue, or a new identifier to start fresh |
| Campaign event types | Seven types | Adds `CampaignResumed` | Nothing, unless you consume the stream by type |
| Manifest values containing `${anything-else:...}` | Passed through as literal text | Refused, naming `env:` as the only implemented provider | Remove the prefix or set `env:` |
| `${...}` anywhere under `spec.policy` | Passed through as literal text | Refused | Write the policy value in the manifest |
| `schema_versions` table | Created and stamped `"0001"` | Dropped by revision `0002`; `alembic_version` records the version | Nothing. Migration is automatic |
| `opensdl_storage.db_models.SchemaVersionRow` | Public mapped class | Removed | Read `alembic_version` through `opensdl_storage.current_revision` |
| `Database.initialize()` | `create_all()`, returned `None` | Runs migrations, returns `SchemaUpgrade` | Nothing. The return value is additive |
| Alembic environment location | `database/env.py`, `database/versions/` | `opensdl_storage/migrations/`, shipped in the wheel | Nothing, unless you drive Alembic through your own `alembic.ini` — point `script_location` at `opensdl_storage:migrations` |
| Resuming a non-terminal run with a different workflow | Executed the submitted steps under the original run, whose `RunCreated` kept describing the original workflow | Refused, naming both canonical digests | Resume with the workflow the run recorded, or submit the repaired workflow with `supersedes=` — a new run that names the one it replaces |
| Resuming a run recorded `running` | Accepted, so two callers could both enter and both dispatch its steps | Refused; starting is one conditional write and `running` is not a state a run may start from | Reconcile first — `opensdl doctor --reconcile`, or `system.start(reconcile=True)`, which `opensdl run` already does |
| `RunCreated` payload | `workflow`, and `context` when a twin is configured | Adds `workflowDigest`, and `supersedes` when the run replaces another | Nothing — the new keys are additive |
| `RunStarted` payload | Empty | Carries `operatorId`: the operator that submitted this start, which is not always the run's owner | Nothing — the event is additive |
| `RunSuperseded` event | Did not exist | Appended to a run that a later run declared it replaces | Nothing, unless you consume the event stream by type |
| `CampaignObservation`, `Suggestion` | Frozen dataclasses with no schema | Pydantic models with generated schemas; keyword construction, `extra="forbid"`, `dict` rather than `Mapping` fields, non-negative `iteration` and `batch` | Construct by keyword; catch `pydantic.ValidationError` where you caught `ValueError` or `TypeError` |
| `CampaignCompleted.payload.best` | A hand-written mapping carrying a derived `feasible` flag | The observation's own serialisation: same keys, plus `constraintViolations`, `suggestion` and `batch`, minus `feasible` | Read `constraintViolations` — `feasible` was `not constraintViolations`, over violations the payload did not carry |

The announcement window depends on the release line:

- **Before 1.0**, the window is one release. A breaking change may appear in the next release with no
  prior deprecation. The changelog entry is the only notice a laboratory receives.
- **After 1.0**, a breaking change to any surface in the table above appears only in a major release,
  and a removal is preceded by at least one minor release in which the previous form still works and
  announces its own removal.

## What a deprecation looks like

No deprecation mechanism is implemented today. The shape below is the intended one, and each entry
names what currently blocks it.

| Surface | Deprecation form | Blocked by |
|---|---|---|
| Python API | The old name keeps working and emits `DeprecationWarning` naming the replacement and the removing release. | Nothing. This is available now and unused. |
| Manifest and twin fields | Both spellings validate for the window; the loader normalizes the old one. | `extra="forbid"` with a `Literal` pin. Requires a version-dispatching loader. |
| Capability identifiers | The old identifier resolves to the new capability and the runtime records that it was rewritten. | No identifier aliasing exists. |
| CLI | The old command or flag keeps working, keeps its exit code, and prints a one-line notice on stderr. | Nothing. |
| HTTP API | The old route keeps working alongside the new one for the window. | Nothing, though the absence of a version prefix makes parallel routes awkward. |
| Database | Every schema change ships an Alembic revision that upgrades in place. | Nothing. This is how the schema now moves. |

A deprecation is only meaningful if the removal is announced with it. A deprecation notice that does
not name the release that removes the surface is not a deprecation.

## What a laboratory should pin

A laboratory repository generated by `opensdl init` does not pin OpenSDL by default. Its
`pyproject.toml` declares floors such as `opensdl-cli>=0.1.0a0` with no upper bound, so a future
breaking release satisfies every generated laboratory. Change that before the first real run.

1. **Pin exact framework versions.** Replace the generated `>=` floors with `==` pins, or add an
   upper bound. Given that pre-1.0 releases may break any contract, `==` is the honest choice.
2. **Commit a lockfile that resolves elsewhere.** `uv.lock` is not in the generated `.gitignore`, so
   it will be committed. If it was produced against a local wheelhouse, it records that directory as
   a registry and no other clone can resolve it. Point the laboratory at a real index or a committed
   artifact source before treating the lockfile as portable.
3. **Pin local adapters by path, not by version.** A `[tool.uv.sources]` path entry with
   `editable = true` keeps a laboratory-owned adapter in step with the repository it lives in. See
   [add an adapter](../guides/add-adapter.md).
4. **Keep the manifest `apiVersion` explicit.** It is already required and already a literal; leaving
   it in the file makes the rejection legible when a future release changes it.
5. **Record the twin `revision` and scene digest** with any run whose projection you intend to
   replay. This alpha does not retain historical twin definitions, so a stored run replays only while
   its binding is still current. See [lab-specific digital twins](../architecture/digital-twin.md).
6. **Keep a copy of the JSON Schemas you validate against.** They are not identified or published, so
   the only durable copy is the one you keep.
7. **Back up the database before upgrading OpenSDL.** The schema upgrades in place through
   Alembic, and a laboratory is upgraded when it is opened for writing, but there is no rollback
   and no cross-version data test.
8. **Supply credentials as `${env:NAME}`, not as text.** A reference that does not resolve is an
   error at load, so a laboratory learns about a misspelled variable in the loader rather than at
   an instrument. See [configuration](configuration.md#secret-references).
9. **Re-run `opensdl validate`, the laboratory's own tests, and one simulated workflow after every
   upgrade.** This is the only compatibility check that exists today, and it is the laboratory's to
   run.

## Known limitations

| Limitation | Consequence | Work implied |
|---|---|---|
| `apiVersion` is a `Literal` pin with `extra="forbid"` on both the manifest and the twin | No additive change is possible; an older reader rejects a newer document | A version-dispatching loader and a converter per supported prior version |
| Generated schemas carry no `$id`, `$schema`, or version | A consumer cannot identify the schema it holds | Schema identity and a published location |
| The schema drift check is byte-for-byte against the working tree | Removing a required field passes CI | Compare each schema against the last released schema and classify the difference |
| `scripts/check-version.py` compares strings only | A malformed or non-monotonic version passes | Parse as PEP 440, check monotonicity, require a matching changelog entry and tag |
| No cross-version test suite | Nothing verifies that a release reads its predecessor's data | The compatibility suite that 1.0 is conditional on |
| No `DeprecationWarning` anywhere | Every change is effectively a removal without notice | Adopt the deprecation forms above, starting with the Python surfaces that are unblocked |
| Generated dependency floors have no upper bound | A future breaking release satisfies every generated laboratory | Pin in the generator template |

These are tracked as **E1**, **E2**, and **E3** in the
[repository audit](../development/audit-2026-08-05.md).
