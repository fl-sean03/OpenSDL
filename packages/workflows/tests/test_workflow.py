import pytest

from opensdl_core import WorkflowDefinition, WorkflowStep
from opensdl_workflows import resolve_mapping, topological_layers


def test_layers_and_resolution() -> None:
    workflow = WorkflowDefinition(id="demo", name="Demo", steps=[
        WorkflowStep(id="a", capability="x"),
        WorkflowStep(id="b", capability="y", depends_on=["a"]),
    ])
    assert [[s.id for s in layer] for layer in topological_layers(workflow)] == [["a"], ["b"]]
    resolved = resolve_mapping({"v":"${steps.a.output.value}"}, {}, {"a":{"value":4}})
    assert resolved["v"] == 4


def test_cycle_rejected() -> None:
    workflow = WorkflowDefinition(id="bad", name="Bad", steps=[
        WorkflowStep(id="a", capability="x", depends_on=["b"]),
        WorkflowStep(id="b", capability="y", depends_on=["a"]),
    ])
    with pytest.raises(Exception):
        topological_layers(workflow)
