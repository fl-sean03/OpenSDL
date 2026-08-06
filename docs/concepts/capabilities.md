# Capabilities

A capability is a semantic operation that an executor can perform. Executors include instruments, robots, humans, compute systems, analysis routines, optimizers, and simulators.

A capability definition includes its identifier, version, executor type, input and output schemas, resource requirements, side effects, risk class, timeout, retries, retry safety, cancellation support, and simulation status.

Two of those fields are declared but not yet acted on. `version` is recorded and never read: a
workflow step names a capability by identifier only and cannot request a version. `supports_cancellation`
has no reader in the runtime. See [compatibility and versioning](../reference/compatibility.md).

Workflows use the capability identifier. Adapters own vendor or transport details. This allows the same workflow to use a simulator, staging device, or production integration through configuration.

## Retry safety

A capability declares what the runtime may do when it dispatched an operation and cannot establish
whether the dispatch took effect. That is the only moment the question is asked, and it is the moment
the runtime used to guess — differently in two places.

| `retry_safety` | Repeat a failed dispatch? | A timed-out task is recorded |
|---|---|---|
| `repeatable` | Yes, within `max_retries` | `failed`, and so resumable |
| `repeatable_if_not_dispatched` | Only on proof that nothing was dispatched | `intervention_required` |
| `not_repeatable` | Never | `intervention_required` |

**The default is `not_repeatable`.** A definition that says nothing has told the runtime nothing, and
the only reading of nothing that cannot cause an incident is the strictest one. A simulator or a pure
computation should declare `repeatable`; a capability that moves, dispenses or heats should not.

Declaring `max_retries` above zero together with `not_repeatable` is refused when the definition is
constructed. The two fields are one statement, and a runtime that silently resolved the contradiction
is how a declared budget becomes a surprise at an instrument.

`repeatable_if_not_dispatched` needs evidence or it collapses into one of the other two. That evidence
is `NotDispatchedError`, which an adapter raises when the command provably never left the client — a
refused connection, a rejected handshake. Nothing verifies the claim; it is the adapter's statement
about its own transport. A timeout is never such evidence: the runtime stopped waiting, which
establishes nothing about the equipment.

This is the retry safety [SAFETY.md](https://github.com/fl-sean03/OpenSDL/blob/main/SAFETY.md)
requires an operational adapter to define. It could not be expressed before.

## Adapter contract

An adapter exposes capability definitions, execution, health, `start` and `close` lifecycle hooks,
and conformance cases. The registry calls `start` and `close` around the process lifetime. Public
adapters are discovered through the `opensdl.adapters` entry-point group. See
[add an adapter](../guides/add-adapter.md) for the full path from generation to a running workflow.

`CapabilityAdapter` also declares `abort(request_id)`, which is **reserved and not wired**. The
runtime has no cancellation path, so nothing calls it and the base implementation returns `False`.
An adapter that implements it is writing code that will not run until a cancellation path exists.
Do not treat it as a stop mechanism, and do not let a laboratory's ability to halt an operation
depend on it. A physical stop comes from the deployment's own protective systems. See
[SAFETY.md](https://github.com/fl-sean03/OpenSDL/blob/main/SAFETY.md).

Explicit cancellation and abort receipts are v0.2 work on the
[roadmap](https://github.com/fl-sean03/OpenSDL/blob/main/ROADMAP.md).
