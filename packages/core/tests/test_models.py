import pytest
from pydantic import ValidationError as PydanticValidationError

from opensdl_core import (
    ExecutorType,
    Quantity,
    RiskClass,
    RunState,
    TaskState,
    CapabilityDefinition,
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
