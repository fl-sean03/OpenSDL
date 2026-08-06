---
name: start-here
description: Establish or resume an OpenSDL laboratory through a normal agent conversation. Use when a user says start here, set up or configure my lab, plan a new lab or cell, describe existing equipment, continue a lab build, or turn a laboratory idea into a simulator-first implementation plan.
---

# Start or resume a laboratory

## Inputs

- intended laboratory outcome or first useful workflow
- existing, planned, or hybrid setup
- repository or proposed destination
- known equipment, compute, manual work, samples, data, and locations
- relevant constraints, hazards, and available evidence

Begin with partial input. Ask for only the highest-value missing information.

## Procedure

1. Read the nearest `AGENTS.md`. Inspect the worktree, branch, recent commits, and current directory
   before changing files.
2. Determine whether the user is in this framework repository, a generated laboratory repository,
   or an uninitialized destination.
3. When a separate lab repository is needed, collect its name, owner, and destination. Use
   `create-lab` only after the destination is confirmed and safe.
4. In a lab repository, read `docs/lab/context.md`, `inventory.md`, `setup-plan.md`, and
   `decisions.md` when present. Then read `opensdl.yaml` and only the workflows needed for the task.
5. Classify the setup as existing, greenfield, or hybrid. Identify the first outcome before trying
   to inventory the entire laboratory.
6. Update the shared lab files with confirmed facts, evidence, assumptions, unknowns, constraints,
   and decisions. Keep the product-wide work list in `docs/development/backlog.md`.
7. Track inventory evidence, integration, and visual-twin state separately. An inventory entry is
   not authority to execute equipment.
8. Map the first workflow to resources, typed capabilities, simulators, manual steps, data, tests,
   and gaps. Prefer one complete simulation path over a broad incomplete configuration.
9. Update executable manifests or workflows only from confirmed information and supported
   contracts. Run `opensdl validate` for any executable file changed.
10. Record any custom 3D request in the lab setup plan with its purpose, source evidence,
    dimensions, and target workflow. An agent can build the tailored Blender scene directly in the
    laboratory repository. OpenSDL currently has no dedicated digital-twin command and intentionally
    has no model catalog.
11. Hand the next task to `create-lab`, `orient-lab`, `design-lab`, `add-capability`, `add-adapter`,
    `develop-workflow`, `add-domain-pack`, or `debug-run` as appropriate. Use `design-lab` when the
    open question is physical or interface design rather than OpenSDL configuration.

Do not run `doctor`, capability listing, inspection, or event queries merely for onboarding. They
read without writing and will not create a store that is not there, but they report operational
evidence rather than declared configuration, which is a different question from setting a
laboratory up. Never pass `doctor --reconcile` during onboarding: it moves running runs to
`intervention_required` and releases their leases.

## Completion

The repository contains enough confirmed shared context for a fresh agent to continue. The first
workflow has a capability and gap map. Any executable changes validate, and the next skill or
future dependency is explicit.

## Stop conditions

Stop before mutation when repository ownership or the destination is unclear. Stop when sources
conflict, secrets or unintended facility details would enter Git, or a required typed operation is
missing. Do not commission equipment or perform physical work through this skill.
