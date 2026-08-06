import pytest
from pydantic import ValidationError as PydanticValidationError

from opensdl_core import (
    CapabilityDefinition,
    ExecutorType,
    LifecycleError,
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
    ("current", "target"),
    [
        # Run resume re-enters RUNNING from every non-terminal recorded state.
        (RunState.PLANNED, RunState.RUNNING),
        (RunState.QUEUED, RunState.RUNNING),
        (RunState.PAUSED, RunState.RUNNING),
        (RunState.INTERVENTION_REQUIRED, RunState.RUNNING),
        (RunState.FAILED, RunState.RUNNING),
        # Terminal outcomes of an active run.
        (RunState.RUNNING, RunState.COMPLETED),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.RUNNING, RunState.INTERVENTION_REQUIRED),
        # recover_incomplete_runs() reconciles ABORTING runs as well as RUNNING ones.
        (RunState.ABORTING, RunState.INTERVENTION_REQUIRED),
    ],
)
def test_run_transitions_the_runtime_performs_are_declared_valid(
    current: RunState, target: RunState
) -> None:
    validate_run_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TaskState.PENDING, TaskState.WAITING_FOR_RESOURCES),
        (TaskState.PENDING, TaskState.FAILED),
        (TaskState.WAITING_FOR_RESOURCES, TaskState.RUNNING),
        (TaskState.WAITING_FOR_RESOURCES, TaskState.FAILED),
        (TaskState.RUNNING, TaskState.SUCCEEDED),
        (TaskState.RUNNING, TaskState.RETRYING),
        (TaskState.RUNNING, TaskState.FAILED),
        (TaskState.RUNNING, TaskState.INTERVENTION_REQUIRED),
        # A retried attempt can succeed, and can be cancelled or reconciled while active.
        (TaskState.RETRYING, TaskState.SUCCEEDED),
        (TaskState.RETRYING, TaskState.FAILED),
        (TaskState.RETRYING, TaskState.INTERVENTION_REQUIRED),
        # Resuming a failed run re-leases the step's resources before dispatching it again.
        (TaskState.FAILED, TaskState.WAITING_FOR_RESOURCES),
        (TaskState.FAILED, TaskState.RUNNING),
    ],
)
def test_task_transitions_the_runtime_performs_are_declared_valid(
    current: TaskState, target: TaskState
) -> None:
    validate_task_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.COMPLETED, RunState.RUNNING),
        (RunState.ABORTED, RunState.RUNNING),
        (RunState.ABORTING, RunState.RUNNING),
        (RunState.COMPLETED, RunState.FAILED),
        (RunState.ABORTED, RunState.COMPLETED),
    ],
)
def test_terminal_runs_cannot_be_restarted(current: RunState, target: RunState) -> None:
    with pytest.raises(LifecycleError):
        validate_run_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TaskState.SUCCEEDED, TaskState.RUNNING),
        (TaskState.SUCCEEDED, TaskState.WAITING_FOR_RESOURCES),
        (TaskState.CANCELLED, TaskState.RUNNING),
        (TaskState.CANCELLED, TaskState.WAITING_FOR_RESOURCES),
        (TaskState.INTERVENTION_REQUIRED, TaskState.WAITING_FOR_RESOURCES),
        (TaskState.INTERVENTION_REQUIRED, TaskState.SUCCEEDED),
    ],
)
def test_settled_tasks_cannot_be_redispatched(current: TaskState, target: TaskState) -> None:
    with pytest.raises(LifecycleError):
        validate_task_transition(current, target)


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
