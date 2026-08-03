---
name: add-capability
description: Add a typed OpenSDL capability contract and propagate it through adapters, schemas, and tests. Use when introducing or changing an executable laboratory operation.
---

# Add a capability

## Inputs

- namespaced capability identifier
- display name
- destination directory, default `capabilities`

## Procedure

1. Run `.agents/skills/add-capability/run.sh CAPABILITY_ID "DISPLAY NAME" [DESTINATION]`.
2. Define typed inputs, outputs, units, resources, side effects, risk class, timeout, retries, and
   simulator status.
3. Implement the contract in at least one simulator-capable adapter.
4. Add valid, invalid, workflow, and conformance cases.
5. Regenerate public schemas and inspect propagation impact.
6. Run focused tests and repository validation.

## Completion

The contract is namespaced, typed, implemented, exported where public, and covered through
simulation and conformance tests.

## Stop conditions

Stop if the operation lacks a semantic boundary, unit contract, risk class, or failure model. Move
runtime lifecycle changes into the core or runtime design before adding the capability.
