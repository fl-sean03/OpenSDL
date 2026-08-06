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
