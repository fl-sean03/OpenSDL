# Capabilities

A capability is a semantic operation that an executor can perform. Executors include instruments, robots, humans, compute systems, analysis routines, optimizers, and simulators.

A capability definition includes its identifier, version, executor type, input and output schemas, resource requirements, side effects, risk class, timeout, retries, cancellation support, and simulation status.

Workflows use the capability identifier. Adapters own vendor or transport details. This allows the same workflow to use a simulator, staging device, or production integration through configuration.

## Adapter contract

An adapter exposes definitions, execution, health, lifecycle, abort behavior, and conformance cases. Public adapters are discovered through the `opensdl.adapters` entry-point group.
