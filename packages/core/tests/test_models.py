import pytest
from pydantic import ValidationError as PydanticValidationError

from opensdl_core import (
    CapabilityDefinition,
    ExecutorType,
    Quantity,
    RiskClass,
    RunRecord,
    RunState,
    TaskState,
    validate_run_id,
    validate_run_transition,
    validate_task_transition,
)


def test_quantity_requires_unit() -> None:
    with pytest.raises(PydanticValidationError):
        Quantity(value=1.0, unit=" ")


def test_capability_contract_round_trip() -> None:
    capability = CapabilityDefinition(
        id="sim.measure_mass",
        name="Measure mass",
        executor_type=ExecutorType.SIMULATOR,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_class=RiskClass.R0,
    )
    assert CapabilityDefinition.model_validate_json(capability.model_dump_json()) == capability


def test_lifecycle_rejects_invalid_transition() -> None:
    validate_run_transition(RunState.PLANNED, RunState.RUNNING)
    validate_task_transition(TaskState.PENDING, TaskState.RUNNING)
    with pytest.raises(Exception):
        validate_run_transition(RunState.COMPLETED, RunState.RUNNING)


@pytest.mark.parametrize(
    "run_id",
    ["a", "run-1", "Run.2026_08-03", "r" + "a" * 79],
)
def test_run_ids_accept_portable_caller_values(run_id: str) -> None:
    assert validate_run_id(run_id) == run_id
    assert RunRecord(id=run_id, workflow_id="test").id == run_id


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        ".",
        "..",
        "-run",
        "_run",
        "/run",
        "run/../escape",
        r"run\..\escape",
        " run",
        "run id",
        "run\tvalue",
        "éclair",
        "r" + "a" * 80,
    ],
)
def test_run_ids_reject_path_unsafe_or_nonportable_values(run_id: str) -> None:
    with pytest.raises(ValueError, match="run ID"):
        validate_run_id(run_id)
    with pytest.raises(PydanticValidationError):
        RunRecord(id=run_id, workflow_id="test")
