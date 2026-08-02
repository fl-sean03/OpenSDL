from __future__ import annotations

from opensdl_core import ValidationError, WorkflowDefinition, WorkflowStep


def validate_workflow_graph(workflow: WorkflowDefinition) -> None:
    step_ids = [step.id for step in workflow.steps]
    if len(set(step_ids)) != len(step_ids):
        raise ValidationError("workflow step identifiers must be unique")
    known = set(step_ids)
    for step in workflow.steps:
        missing = set(step.depends_on) - known
        if missing:
            raise ValidationError(f"step {step.id} depends on unknown steps: {sorted(missing)}")
        if step.id in step.depends_on:
            raise ValidationError(f"step {step.id} cannot depend on itself")
    topological_layers(workflow)


def topological_layers(workflow: WorkflowDefinition) -> list[list[WorkflowStep]]:
    remaining = {step.id: step for step in workflow.steps}
    completed: set[str] = set()
    layers: list[list[WorkflowStep]] = []
    while remaining:
        ready = sorted(
            [step for step in remaining.values() if set(step.depends_on) <= completed],
            key=lambda step: step.id,
        )
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise ValidationError(f"workflow contains a dependency cycle involving: {cycle}")
        layers.append(ready)
        for step in ready:
            remaining.pop(step.id)
            completed.add(step.id)
    return layers
