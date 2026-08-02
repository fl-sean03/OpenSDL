---
name: create-lab
description: Initialize a separate organization laboratory with pinned versions, simulations, policy, and validation. Use when bootstrapping a concrete lab repository from OpenSDL.
---

# Create an organization laboratory

1. Run `uv run --locked opensdl init PATH --name NAME --owner OWNER`.
2. Pin OpenSDL and adapter versions.
3. Replace the simulator manifest with the organization inventory incrementally.
4. Add local adapters and simulations before connecting equipment.
5. Add deployment-specific policy, secrets, tests, and validation evidence.
6. Keep the organization repository separate from the public framework.
