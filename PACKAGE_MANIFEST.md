# Package manifest

**Project:** OpenSDL  
**Version:** `0.1.0a0`  
**Prepared:** 2026-08-02  
**Repository files:** 290  
**Installable workspace members:** 21

This archive contains the complete executable alpha source repository: reusable packages, deployable applications, reference adapters, scientific domain packs, generated project templates, schemas, database migrations, examples, tests, scripts, documentation, and repository automation.

## Major contents

| Area | Purpose |
|---|---|
| `packages/` | Core contracts, schemas, capability system, policy, workflows, storage, simulation, runtime, provenance, operator interfaces, SDK, and CLI |
| `apps/` | Thin controller composition root and HTTP API |
| `adapters/` | Simulated laboratory, local numerical compute, grid optimizer, and structured human-task extensions |
| `domain-packs/` | Materials, chemistry, and physics extension models |
| `examples/` | Complete closed-loop and computation-only reference laboratories |
| `database/` | Alembic configuration and initial relational migration |
| `tests/` | Integration, end-to-end, and adapter-conformance tests |
| `.agents/skills/` | Executable repository-development procedures built around the public CLI |
| `docs/` | Getting started, architecture, concepts, guides, research landscape, and API/CLI/configuration reference |

## Installable components

- `opensdl-adapter-grid-optimizer==0.1.0a0` — `adapters/grid-optimizer`
- `opensdl-adapter-human-task==0.1.0a0` — `adapters/human-task`
- `opensdl-adapter-local-compute==0.1.0a0` — `adapters/local-compute`
- `opensdl-adapter-simulated-lab==0.1.0a0` — `adapters/simulated-lab`
- `opensdl-api==0.1.0a0` — `apps/api`
- `opensdl-controller==0.1.0a0` — `apps/controller`
- `opensdl-domain-chemistry==0.1.0a0` — `domain-packs/chemistry`
- `opensdl-domain-materials==0.1.0a0` — `domain-packs/materials`
- `opensdl-domain-physics==0.1.0a0` — `domain-packs/physics`
- `opensdl-capabilities==0.1.0a0` — `packages/capabilities`
- `opensdl-cli==0.1.0a0` — `packages/cli`
- `opensdl-core==0.1.0a0` — `packages/core`
- `opensdl-operators==0.1.0a0` — `packages/operators`
- `opensdl-policy==0.1.0a0` — `packages/policy`
- `opensdl-provenance==0.1.0a0` — `packages/provenance`
- `opensdl-runtime==0.1.0a0` — `packages/runtime`
- `opensdl-schemas==0.1.0a0` — `packages/schemas`
- `opensdl-sdk==0.1.0a0` — `packages/sdk`
- `opensdl-simulation==0.1.0a0` — `packages/simulation`
- `opensdl-storage==0.1.0a0` — `packages/storage`
- `opensdl-workflows==0.1.0a0` — `packages/workflows`

## Verification artifacts

- [`VALIDATION.md`](VALIDATION.md) records what was executed and what remains unvalidated.
- [`REPO_TREE.txt`](REPO_TREE.txt) lists the complete clean repository tree.
- [`package-manifest.json`](package-manifest.json) contains machine-readable file hashes and component metadata.
- [`SHA256SUMS`](SHA256SUMS) verifies every file in the archive except the checksum file itself.

The archive intentionally excludes virtual environments, lock-resolution caches, test caches, bytecode, editable-install metadata, build directories, wheels, databases, artifact stores, and executed-run state.
