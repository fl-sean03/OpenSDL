---
name: add-capability
description: Add a typed OpenSDL capability contract and propagate it through adapters, schemas, and tests. Use when introducing or changing an executable laboratory operation.
---

# Add a capability

1. Generate the contract with `uv run --locked opensdl capability create`.
2. Define typed input and output schemas, units, resources, side effects, risk class, timeout, retries, and simulator status.
3. Implement it in an adapter.
4. Add workflow and conformance coverage.
5. Regenerate JSON Schemas and review propagation impact.
