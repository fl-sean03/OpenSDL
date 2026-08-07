import hashlib

import pytest
from pydantic import ValidationError as PydanticValidationError

from opensdl_core import (
    STARTABLE_RUN_STATES,
    CampaignDefinition,
    CapabilityDefinition,
    ExecutorType,
    LifecycleError,
    Quantity,
    RetrySafety,
    RiskClass,
    RunRecord,
    RunState,
    TaskState,
    canonical_digest,
    canonical_json,
    validate_run_id,
    validate_run_transition,
    validate_task_transition,
)
from opensdl_core.lifecycle import RUN_TRANSITIONS


def test_quantity_requires_unit() -> None:
    with pytest.raises(PydanticValidationError):
        Quantity(value=1.0, unit=" ")


def capability_definition(**overrides: object) -> CapabilityDefinition:
    fields: dict[str, object] = {
        "id": "sim.measure_mass",
        "name": "Measure mass",
        "executor_type": ExecutorType.SIMULATOR,
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "risk_class": RiskClass.R0,
    }
    fields.update(overrides)
    return CapabilityDefinition(**fields)  # pyright: ignore[reportArgumentType]


def test_capability_contract_round_trip() -> None:
    capability = capability_definition(retry_safety=RetrySafety.REPEATABLE_IF_NOT_DISPATCHED)
    assert CapabilityDefinition.model_validate_json(capability.model_dump_json()) == capability


def test_an_undeclared_capability_is_not_repeatable() -> None:
    """Silence about retry safety must not read as permission to repeat a physical action.

    The runtime cannot infer whether repeating an operation is safe, which is the whole reason
    this field exists. A definition that says nothing has told it nothing, and the only reading
    of nothing that cannot cause an incident is the strictest one.
    """
    assert capability_definition().retry_safety is RetrySafety.NOT_REPEATABLE


def test_a_capability_cannot_declare_a_retry_budget_it_calls_unsafe() -> None:
    """`max_retries` and `retry_safety` are one statement, so they cannot contradict each other.

    A definition asking for three automatic attempts while declaring that repeating it is never
    safe is a contract the runtime cannot honour either way round. Refusing it at construction
    means the author finds out where they wrote it, rather than discovering at an instrument that
    the budget they declared was quietly ignored.
    """
    with pytest.raises(PydanticValidationError, match="retry_safety"):
        capability_definition(retry_safety=RetrySafety.NOT_REPEATABLE, max_retries=3)

    # Both other declarations can honour a budget: one repeats freely, the other repeats on proof
    # that nothing was dispatched.
    assert (
        capability_definition(retry_safety=RetrySafety.REPEATABLE, max_retries=3).max_retries == 3
    )
    assert (
        capability_definition(
            retry_safety=RetrySafety.REPEATABLE_IF_NOT_DISPATCHED, max_retries=3
        ).max_retries
        == 3
    )


def campaign_definition(**overrides: object) -> CampaignDefinition:
    fields: dict[str, object] = {
        "id": "campaign.color",
        "name": "Match a target color",
        "objective": "minimize distance to the target RGB",
        "workflow_id": "color-mix-and-score",
        "optimizer": "grid",
    }
    fields.update(overrides)
    return CampaignDefinition(**fields)  # pyright: ignore[reportArgumentType]


def test_campaign_definition_declares_every_stopping_rule() -> None:
    definition = campaign_definition(
        target_score=0.5,
        max_consecutive_failures=2,
        max_duration_seconds=3600,
        iteration_id_input="sample_id",
    )
    assert CampaignDefinition.model_validate_json(definition.model_dump_json()) == definition
    assert campaign_definition().max_consecutive_failures == 3
    assert campaign_definition().target_score is None
    assert campaign_definition().max_duration_seconds is None
    # Domain-neutral by default: nothing is injected into a computational workflow's inputs.
    assert campaign_definition().iteration_id_input is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_iterations": 0},
        {"max_consecutive_failures": 0},
        {"max_duration_seconds": 0},
        # A campaign definition cannot assert where it runs or who runs it: those come from the
        # laboratory manifest and the caller, and a stored default would make them a claim.
        {"environment": "production"},
        {"operator_id": "software/campaign"},
    ],
)
def test_campaign_definition_rejects_budgets_and_claims_it_cannot_honor(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(PydanticValidationError):
        campaign_definition(**overrides)


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


def test_startable_states_are_read_off_the_declared_machine() -> None:
    """Not a second list. `RUNNING` is absent because the machine already said so."""

    assert STARTABLE_RUN_STATES == {
        state for state, targets in RUN_TRANSITIONS.items() if RunState.RUNNING in targets
    }
    assert RunState.RUNNING not in STARTABLE_RUN_STATES
    assert STARTABLE_RUN_STATES == {
        RunState.PLANNED,
        RunState.QUEUED,
        RunState.PAUSED,
        RunState.INTERVENTION_REQUIRED,
        RunState.FAILED,
    }


def test_validate_run_transition_treats_running_to_running_as_a_no_op() -> None:
    """The escape hatch `STARTABLE_RUN_STATES` exists to work around, stated as a fact."""

    validate_run_transition(RunState.RUNNING, RunState.RUNNING)
    assert RunState.RUNNING not in RUN_TRANSITIONS[RunState.RUNNING]


def test_a_canonical_digest_ignores_key_order_and_separator_style() -> None:
    left = {"b": [1, 2], "a": {"y": None, "x": 1}}
    right = {"a": {"x": 1, "y": None}, "b": [1, 2]}

    assert canonical_digest(left) == canonical_digest(right)
    assert canonical_json(left) == b'{"a":{"x":1,"y":null},"b":[1,2]}'
    assert canonical_digest(left) != canonical_digest({"b": [2, 1], "a": {"x": 1, "y": None}})


def test_a_canonical_digest_is_stable_and_reproducible_from_the_document() -> None:
    document = {"id": "w", "steps": [{"id": "one", "capability": "sim.mix"}]}

    assert canonical_digest(document) == hashlib.sha256(canonical_json(document)).hexdigest()
    assert canonical_digest(document) == (
        "51e87ed597614733e9ce37f4b71f1240cf418169a9bead3eca263a5551fe15da"
    )
