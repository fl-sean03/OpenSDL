import pytest

from opensdl_adapter_local_compute import LocalComputeAdapter
from opensdl_capabilities import CapabilityRegistry
from opensdl_core import ValidationError, WorkflowDefinition, WorkflowStep
from opensdl_policy import PolicyEngine
from opensdl_runtime import ReferenceRuntime
from opensdl_storage import Database, LocalArtifactStore, Repositories


def build_runtime(tmp_path):
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    registry.register(LocalComputeAdapter())
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path, repositories),
    )
    return runtime, repositories


@pytest.mark.asyncio
async def test_workflow_executes_and_persists(tmp_path) -> None:
    runtime, repositories = build_runtime(tmp_path)
    workflow = WorkflowDefinition(
        id="distance",
        name="Distance",
        input_schema={
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "array", "items": {"type": "number"}},
                "b": {"type": "array", "items": {"type": "number"}},
            },
        },
        steps=[
            WorkflowStep(
                id="score",
                capability="compute.euclidean_distance",
                inputs={"a": "${inputs.a}", "b": "${inputs.b}"},
            )
        ],
        outputs={"score": "${steps.score.output.distance}"},
    )
    run = await runtime.run_workflow(workflow, {"a": [0, 0], "b": [3, 4]})
    assert run.outputs["score"] == 5
    assert repositories.list_tasks(run.id)[0].outputs["distance"] == 5
    assert repositories.list_events(run_id=run.id)[-1].type == "RunCompleted"


@pytest.mark.asyncio
async def test_runtime_rejects_invalid_capability_inputs(tmp_path) -> None:
    runtime, _ = build_runtime(tmp_path)
    with pytest.raises(ValidationError, match="compute.quadratic input"):
        await runtime.execute_capability(
            "compute.quadratic",
            {"x": "not-a-number", "a": 1, "b": 0, "c": 0},
        )


@pytest.mark.asyncio
async def test_direct_capability_execution_returns_complete_output(tmp_path) -> None:
    runtime, _ = build_runtime(tmp_path)
    run = await runtime.execute_capability(
        "compute.quadratic",
        {"x": 2, "a": 1, "b": 0, "c": -1},
    )
    assert run.outputs["result"] == {"value": 3.0}
