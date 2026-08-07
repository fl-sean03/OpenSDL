# CLI reference

The current command groups are:

```text
opensdl version
opensdl init
opensdl validate
opensdl doctor
opensdl migrate
opensdl run
opensdl inspect
opensdl events
opensdl export
opensdl propagate
opensdl serve-api
opensdl serve-mcp
opensdl campaign start
opensdl campaign list
opensdl campaign inspect
opensdl capability list
opensdl capability create
opensdl adapter create
opensdl domain-pack create
opensdl schema generate
opensdl twin validate
opensdl twin project
```

Run `opensdl COMMAND --help` or `opensdl GROUP COMMAND --help` for current arguments and options.

## Failures and exit codes

A failure is reported as one line on stderr with an exit code that says what kind of failure it was,
so a supervising script can tell a refusal from a crash without parsing prose. `--traceback`, or
`OPENSDL_TRACEBACK=1`, restores the full traceback.

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Internal error — a defect worth reporting |
| 2 | Usage error |
| 3 | Invalid input, manifest, workflow, or result |
| 4 | Not found: a path, a run, a capability, an adapter plugin |
| 5 | Denied by policy |
| 6 | A required resource is unregistered or already leased |
| 7 | A declared timeout elapsed |
| 8 | Refused: the recorded state does not allow the request |
| 9 | The laboratory ran and could not finish |

## Commands that read and commands that write

`validate`, `doctor`, `inspect`, `events`, `export`, `capability list`, `campaign list`,
`campaign inspect`, `migrate --check`, and `twin project` compose the
laboratory read-only. They will not create a store, seed capabilities, or reconcile runs, and reading
a laboratory that has never run reports that rather than creating an empty one.

`doctor --reconcile` is the exception and it writes. It moves every run left `running` by a stopped
controller to `intervention_required` and releases its leases, then reports what it moved. That is
recovery after a controller stopped, not a health check — running it while work is in flight destroys
the record of the run in flight.

Inputs accepted by `opensdl run` may be provided as an inline JSON object or as `@path/to/inputs.json`.

## Resuming a run, and replacing one

`opensdl run --run-id ID` against a run that already exists is a **resume**, not a resubmission. The
run's `RunCreated` recorded the workflow it was asked to execute and a digest of that document, and
a resume must present the same document. Anything else exits `8` naming both digests: running new
steps under an existing identifier would leave the run's own record describing work it did not do,
attributed to whoever submitted it originally.

A repaired workflow is therefore a new run, and `--supersedes ID` is how it is submitted:

```bash
opensdl run workflow.yaml --supersedes run_0f3c...   # mints a new run naming the one it replaces
```

The link is recorded on both runs — `supersedes` in the new run's `RunCreated`, a `RunSuperseded`
event on the replaced run — so an operator reading the run that failed finds what became of it.
Nothing about the replaced run changes.

A run recorded `running` cannot be claimed at all; `opensdl run` reconciles first, which moves such
a run to `intervention_required` where a person establishes what the equipment did.
