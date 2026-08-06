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
an index at all.

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
- No migration is guaranteed to exist for any contract change, and none exists for the database
  schema at all.
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
| Twin `apiVersion` | `TwinDefinition` in `opensdl-twin` | Pinned to `opensdl.dev/v0alpha1`. No second version exists. |
| Generated JSON Schemas | `packages/schemas/jsonschema/`, 13 files | Regenerated on every model change. No identity, no version, no compatibility check. |
| Capability contracts | `CapabilityDefinition` and the identifiers adapters declare | No guarantee. Identifiers are plain strings and there is no registry. |
| Adapter plugin interface | `CapabilityAdapter`, entry-point group `opensdl.adapters` | No guarantee. Abstract methods may be added. |
| Optimizer plugin interface | `Optimizer` protocol in `opensdl-runtime`, group `opensdl.optimizers` | No guarantee. It is `suggest(history)` and `observe(observation)` with no state contract, so an optimizer that must persist a surrogate model has nowhere to put it. |
| Domain-pack interface | `get_pack()`, group `opensdl.domain_packs` | No guarantee. The return value is an untyped mapping. |
| CLI | `opensdl` commands and options | No guarantee. Output is human-readable text and JSON with no declared shape. |
| HTTP API | 15 routes in `opensdl-api` | No guarantee. No version prefix, no content negotiation, no authentication. |
| Python SDK | `OpenSDLClient` in `opensdl` | No guarantee. It is a thin wrapper over the HTTP routes and moves with them. |
| Database schema | `opensdl-storage` models and `database/versions/` | No guarantee and no upgrade path. See below. |

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

The 13 files under `packages/schemas/jsonschema/` are produced by
`uv run --locked python scripts/generate-schemas.py`. None of them contains `$id`, `$schema`, or any
version field, so a consumer holding one has no way to say which schema it is or which release
produced it.

The CI drift check compares committed bytes against freshly generated bytes with
`filecmp.cmp(..., shallow=False)`. It answers one question: were the schemas regenerated? It does not
compare a schema against its predecessor. Removing a required field from a public model passes CI as
long as the schemas were regenerated in the same commit.

Making these schemas useful as contracts requires an `$id` per schema, a `$schema` declaration, and a
comparison against the previously released schema rather than against the working tree.

### Capability versions are recorded but never used

`CapabilityDefinition.version` and `WorkflowDefinition.version` exist and default to `0.1.0`. A
workflow step names a capability by identifier only, so it cannot request a version, and nothing in
the runtime reads `CapabilityDefinition.version`. Only `workflow.version` is read, and only to stamp
it onto the run record. Changing a capability's input or output schema is therefore invisible to
every workflow that already uses it.

### The database schema has no upgrade path

`Database.initialize()` calls SQLAlchemy `create_all()` and inserts the literal string `"0001"` into
a `schema_versions` table. `create_all()` is `CREATE TABLE IF NOT EXISTS`: it creates missing tables
and never alters an existing one. The stamped value is never compared against anything, and it is not
Alembic's `alembic_version` table, so the shipped Alembic revision under `database/versions/` is
unreachable from the CLI.

An existing laboratory's database therefore cannot be upgraded by any documented command. This is
tracked as **E1** in the [repository audit](../development/audit-2026-08-05.md).

## Announcing a breaking change

A change is breaking when a laboratory that worked against the previous release stops working
without editing its own files. Renaming or removing a manifest field, a capability identifier, a CLI
flag, an HTTP route, an SDK method, a schema property, or a database column is breaking. Adding an
optional manifest or twin field is also breaking, for the reason given above.

From this policy forward, a breaking change is recorded in `CHANGELOG.md` under a `Breaking` heading
in the release entry, naming the surface, the previous behavior, the new behavior, and the action a
laboratory must take. No release has followed this policy yet, so no such heading exists.

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
| Database | Every schema change ships an Alembic revision that upgrades in place. | `create_all()` bypasses Alembic entirely. |

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
7. **Back up the database before upgrading OpenSDL.** There is no migration path and no rollback.
8. **Re-run `opensdl validate`, the laboratory's own tests, and one simulated workflow after every
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
| `create_all()` bypasses Alembic | No laboratory database can be upgraded | An `opensdl migrate` command and an Alembic-stamped initialization path |
| No `DeprecationWarning` anywhere | Every change is effectively a removal without notice | Adopt the deprecation forms above, starting with the Python surfaces that are unblocked |
| Generated dependency floors have no upper bound | A future breaking release satisfies every generated laboratory | Pin in the generator template |

These are tracked as **E1**, **E2**, and **E3** in the
[repository audit](../development/audit-2026-08-05.md).
