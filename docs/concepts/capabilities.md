# Capabilities

A capability is a semantic operation that an executor can perform. Executors include instruments, robots, humans, compute systems, analysis routines, optimizers, and simulators.

A capability definition includes its identifier, version, executor type, input and output schemas, resource requirements, side effects, risk class, timeout, retries, cancellation support, and simulation status.

Two of those fields are declared but not yet acted on. `version` is recorded and never read: a
workflow step names a capability by identifier only and cannot request a version. `supports_cancellation`
has no reader in the runtime. See [compatibility and versioning](../reference/compatibility.md).

Workflows use the capability identifier. Adapters own vendor or transport details. This allows the same workflow to use a simulator, staging device, or production integration through configuration.

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
