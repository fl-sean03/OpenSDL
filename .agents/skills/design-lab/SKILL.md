---
name: design-lab
description: Scope the physical and interface design of a laboratory before configuring it. Use when a user asks how to approach a lab buildout, how to break a cell into components, which mechanism or instrument to choose, how to tailor a reference design to their material system or hazards, whether a design is over-engineered, or how to keep a lab extensible.
---

# Design a laboratory for its application

Apply the method in `docs/guides/design-a-lab.md`. This procedure records its output as durable
decisions in a laboratory repository.

## Boundary with `start-here`

Use `design-lab` for plant and interface questions: what to build, which requirement drives it, which
choices cannot be revised later, and how a pattern from another field transfers to this material
system. Use `start-here` for OpenSDL configuration: repository context, inventory, capability
mapping, and the first workflow. A design session usually precedes a `start-here` session, or
interrupts one when a configuration question turns out to be a physical one.

## Inputs

- the decision the loop must make, and the measurement that informs it;
- the material system and its relevant properties or hazard classes;
- throughput, cycle time, and expected campaign length;
- existing equipment, facility constraints, and budget envelope; and
- the intended growth path beyond the first workflow.

Begin with partial input. Ask only for what changes the recommendation.

## Procedure

1. Read the nearest `AGENTS.md` and inspect Git state before changing files. In a laboratory
   repository, read `docs/lab/context.md`, `inventory.md`, `setup-plan.md`, and `decisions.md`.
2. State the loop before the equipment: the decision, the measurement, the shortest operation
   sequence, and the cycle count needed for convergence. Flag when cycle time and required cycles
   make the loop impractical, because no downstream choice fixes that.
3. Define the minimum viable loop. Prefer one closed loop with simulated or manual steps over a
   broader set of automated but open steps.
4. Separate plant, interface, capability, and campaign decisions. Keep a physical constraint out of
   workflow logic.
5. For each component under discussion, name the functions it serves before naming a mechanism. When
   requirements conflict inside one part, propose an architectural split rather than a more complex
   part.
6. Identify the binding constraint by estimating margin per requirement. Record it. Warn explicitly
   when a candidate design is borrowed from a field whose binding constraint differs.
7. Check every borrowed pattern against the material-system table in the guide. Report any row that
   applies, and treat a recognized hazard class as a prompt for qualified review rather than a
   resolved question.
8. Classify each decision as reversible or irreversible. Recommend deliberate design time and outside
   review for the irreversible ones, and recommend over-provisioning payload, envelope, utilities,
   bandwidth, and slot count.
9. Where the laboratory must grow, propose a versioned interface specification and record it in the
   laboratory repository beside the manifest.
10. For unattended operation, identify each state the machine must observe rather than infer, and
    name the failure modes that warrant verification by two different physical principles.
11. Keep safety functions in an independent rated system that OpenSDL cannot outvote. Do not design
    an interlock that depends on the orchestration layer.
12. Write results into `docs/lab/decisions.md` and `setup-plan.md`: the choice, the rejected
    alternatives, the driving constraint, and the condition that would justify revisiting it.
13. Hand the next task to `start-here`, `create-lab`, `add-capability`, `add-adapter`, or
    `develop-workflow`.

## Completion

The laboratory repository records the loop, the minimum viable path to close it, the binding
constraint for each open design question, the irreversible decisions and their headroom, and any
interface specification the growth path requires. Each recorded decision names its driving constraint
and its expiry condition. Unresolved questions are listed as unknowns rather than assumed.

## Stop conditions

Stop before mutation when repository ownership or destination is unclear. Stop when the user asks for
a determination that requires a qualified engineer: hazard analysis, material compatibility, quantity
limits, containment adequacy, structural or pressure rating, regulatory classification, or a safety
case. Describe the relevant considerations and the governing standards, then name the review the
decision needs.

Do not approve a design for physical construction or operation. Do not record an assumed material
property, hazard rating, or equipment specification as a confirmed fact. Do not commission equipment
or perform physical work through this skill.
