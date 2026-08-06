"""Contract tests for the closed loop.

The campaign is the one path OpenSDL runs unattended, so these tests are written around what an
unattended loop has to guarantee: it executes where the caller said it does, it survives a routine
failure, it stops for a stated reason, and it stays domain-neutral.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from opensdl_capabilities import CapabilityAdapter, CapabilityRegistry
from opensdl_core import (
    AuthorizationEffect,
    CampaignDefinition,
    CapabilityDefinition,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    RunState,
    WorkflowDefinition,
    WorkflowStep,
)
from opensdl_policy import PolicyEngine, PolicyRule
from opensdl_runtime import ReferenceRuntime
from opensdl_runtime.campaign import (
    CampaignObservation,
    CampaignObservationStatus,
    CampaignRunner,
    CampaignStopReason,
)
from opensdl_storage import Database, LocalArtifactStore, Repositories


class ScoreAdapter(CapabilityAdapter):
    """Scores a candidate by returning ``x``, and fails for the candidates it is told to fail on."""

    name = "campaign-probe"

    def __init__(
        self,
        *,
        fail_on: set[float] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        super().__init__()
        self.fail_on = fail_on or set()
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, Any]] = []

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.score",
                name="Score a candidate",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["x"],
                    "properties": {"x": {"type": "number"}},
                },
                output_schema={
                    "type": "object",
                    "required": ["score"],
                    "properties": {"score": {"type": "number"}},
                },
                simulator_available=True,
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        import asyncio

        self.calls.append(dict(request.inputs))
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        value = float(request.inputs["x"])
        if value in self.fail_on:
            raise RuntimeError(f"simulated instrument failure at x={value:g}")
        return ExecutionResult(request_id=request.request_id, output={"score": value})


class ListOptimizer:
    """Proposes each candidate once, skipping any already in history, and records observations."""

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = [dict(item) for item in candidates]
        self.observed: list[CampaignObservation] = []

    def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None:
        tried = [item.candidate for item in history]
        for candidate in self.candidates:
            if candidate not in tried:
                return dict(candidate)
        return None

    def observe(self, observation: CampaignObservation) -> None:
        self.observed.append(observation)


def scoring_workflow(*, inputs: tuple[str, ...] = ("x",)) -> WorkflowDefinition:
    """A workflow that accepts exactly the inputs it declares, as the generated template teaches."""

    return WorkflowDefinition(
        id="campaign-probe",
        name="Campaign probe",
        input_schema={
            "type": "object",
            "required": ["x"],
            "properties": {name: {} for name in inputs},
            "additionalProperties": False,
        },
        steps=[WorkflowStep(id="score", capability="test.score", inputs={"x": "${inputs.x}"})],
        outputs={"score": "${steps.score.output.score}"},
    )


def build_campaign(
    tmp_path,
    adapter: ScoreAdapter,
    *,
    policy: PolicyEngine | None = None,
) -> tuple[CampaignRunner, Repositories]:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    registry.register(adapter)
    runtime = ReferenceRuntime(
        registry,
        repositories,
        policy or PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path, repositories),
    )
    return CampaignRunner(runtime, repositories), repositories


def candidates(*values: float) -> list[dict[str, Any]]:
    return [{"x": value} for value in values]


@pytest.mark.asyncio
async def test_campaign_requires_an_explicit_environment_and_operator(tmp_path) -> None:
    """A default environment is a fail-open default on the one unattended path."""

    runner, _ = build_campaign(tmp_path, ScoreAdapter())
    workflow = scoring_workflow()
    optimizer = ListOptimizer(candidates(1.0))

    with pytest.raises(TypeError):
        await runner.run(workflow, optimizer, operator_id="operator/alice")  # pyright: ignore[reportCallIssue]

    with pytest.raises(TypeError):
        await runner.run(workflow, optimizer, environment="production")  # pyright: ignore[reportCallIssue]


@pytest.mark.asyncio
async def test_campaign_rejects_a_blank_environment_or_operator(tmp_path) -> None:
    runner, _ = build_campaign(tmp_path, ScoreAdapter())
    workflow = scoring_workflow()
    optimizer = ListOptimizer(candidates(1.0))

    with pytest.raises(ValueError, match="environment"):
        await runner.run(workflow, optimizer, environment="  ", operator_id="operator/alice")
    with pytest.raises(ValueError, match="operator_id"):
        await runner.run(workflow, optimizer, environment="production", operator_id="")


@pytest.mark.asyncio
async def test_campaign_executes_in_the_environment_it_was_given(tmp_path) -> None:
    """The runs, the policy decision, and the campaign record must agree on the environment."""

    adapter = ScoreAdapter()
    policy = PolicyEngine(
        rules=[
            PolicyRule(
                id="production-only",
                effect=AuthorizationEffect.ALLOW,
                capability="*",
                environments=["production"],
                reason="this laboratory declares environment: production",
            )
        ],
        default_effect="deny",
    )
    runner, repositories = build_campaign(tmp_path, adapter, policy=policy)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(2.0, 1.0)),
        environment="production",
        operator_id="software/campaign",
        max_iterations=2,
    )

    assert [item.status for item in result.history] == [
        CampaignObservationStatus.SUCCEEDED,
        CampaignObservationStatus.SUCCEEDED,
    ]
    assert {run.environment for run in repositories.list_runs()} == {"production"}
    started = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id)
        if event.type == "CampaignStarted"
    )
    assert started.payload["environment"] == "production"
    assert started.payload["operatorId"] == "software/campaign"


@pytest.mark.asyncio
async def test_campaign_injects_no_domain_specific_input_by_default(tmp_path) -> None:
    """A compute-only workflow that follows the generated `additionalProperties: false` template."""

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )

    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
    assert [item.status for item in result.history] == [CampaignObservationStatus.SUCCEEDED]
    assert [run.inputs for run in repositories.list_runs()] == [{"x": 1.0}]


@pytest.mark.asyncio
async def test_iteration_id_input_names_the_input_that_receives_the_identifier(tmp_path) -> None:
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(inputs=("x", "specimen")),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
        iteration_id_input="specimen",
    )

    run = repositories.list_runs()[0]
    assert run.inputs == {"x": 1.0, "specimen": f"{result.campaign_id}-000"}


@pytest.mark.asyncio
async def test_a_failed_iteration_is_recorded_and_the_campaign_continues(tmp_path) -> None:
    adapter = ScoreAdapter(fail_on={2.0})
    optimizer = ListOptimizer(candidates(3.0, 2.0, 1.0))
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
    )

    assert [item.status.value for item in result.history] == ["succeeded", "failed", "succeeded"]
    failure = result.history[1]
    assert failure.candidate == {"x": 2.0}
    assert failure.score is None
    assert failure.error is not None and "simulated instrument failure" in failure.error
    assert failure.run_id is not None
    assert result.best is not None and result.best.candidate == {"x": 1.0}
    assert [item.candidate for item in optimizer.observed] == [{"x": 3.0}, {"x": 2.0}, {"x": 1.0}]
    states = {run.id: run.state for run in repositories.list_runs()}
    assert states[failure.run_id] == RunState.FAILED
    events = repositories.list_events(campaign_id=result.campaign_id, limit=None)
    types = [event.type for event in events]
    assert types.count("CampaignIterationFailed") == 1
    assert types.count("DecisionRecorded") == 2
    completed = next(event for event in events if event.type == "CampaignCompleted")
    assert completed.payload["succeeded"] == 2
    assert completed.payload["failed"] == 1


@pytest.mark.asyncio
async def test_a_failed_candidate_is_not_suggested_again(tmp_path) -> None:
    """A failure that never reaches history is a candidate the optimizer proposes forever."""

    adapter = ScoreAdapter(fail_on={1.0})
    runner, _ = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0, 2.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=5,
    )

    assert [item.candidate for item in result.history] == [{"x": 1.0}, {"x": 2.0}]
    assert result.stop_reason is CampaignStopReason.OPTIMIZER_EXHAUSTED
    assert [call["x"] for call in adapter.calls] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_systematic_failure_stops_the_campaign_and_preserves_the_record(tmp_path) -> None:
    adapter = ScoreAdapter(fail_on={1.0, 2.0, 3.0})
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0, 2.0, 3.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
        max_consecutive_failures=2,
    )

    assert result.stop_reason is CampaignStopReason.FAILURE_LIMIT
    assert len(result.history) == 2
    assert result.failures == result.history
    assert result.best is None
    assert len(adapter.calls) == 2
    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    assert completed.payload["stopReason"] == "failure_limit"
    assert "systematic" in completed.payload["stopDetail"]


@pytest.mark.asyncio
async def test_a_missing_score_is_a_failed_observation_not_a_crash(tmp_path) -> None:
    """The run completed and the physical work happened; only the score was unusable."""

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        score_output="absorbance.mean",
        max_iterations=1,
    )

    observation = result.history[0]
    assert observation.status is CampaignObservationStatus.FAILED
    assert observation.error == "campaign score output not found: absorbance.mean"
    assert observation.run_id is not None
    assert repositories.list_runs()[0].state == RunState.COMPLETED
    failed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignIterationFailed"
    )
    assert failed.payload["runState"] == "completed"
    assert failed.payload["errorType"] == "KeyError"


@pytest.mark.asyncio
async def test_reaching_the_target_score_stops_the_campaign(tmp_path) -> None:
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 1.0, 2.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
        target_score=1.5,
    )

    assert result.stop_reason is CampaignStopReason.TARGET_REACHED
    assert len(result.history) == 2
    assert [call["x"] for call in adapter.calls] == [3.0, 1.0]
    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    assert completed.payload["stopReason"] == "target_reached"


@pytest.mark.asyncio
async def test_exhausting_the_iteration_budget_is_distinguishable_from_converging(
    tmp_path,
) -> None:
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        target_score=0.0,
    )

    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
    assert len(result.history) == 2
    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    assert completed.payload["stopReason"] == "max_iterations"


@pytest.mark.asyncio
async def test_the_wall_clock_budget_stops_the_campaign(tmp_path) -> None:
    adapter = ScoreAdapter(delay_seconds=0.05)
    runner, _ = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
        max_duration_seconds=0.01,
    )

    assert result.stop_reason is CampaignStopReason.TIME_BUDGET_EXHAUSTED
    assert len(result.history) == 1
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_campaign_events_name_every_run_the_campaign_launched(tmp_path) -> None:
    """After a campaign, one query has to say what it did — including the runs that failed."""

    adapter = ScoreAdapter(fail_on={2.0})
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
    )

    events = repositories.list_events(campaign_id=result.campaign_id, limit=None)
    named = {
        event.payload["runId"]
        for event in events
        if event.type in {"CampaignIterationStarted", "CampaignIterationFailed"}
    }
    assert named == {run.id for run in repositories.list_runs()}
    assert len(named) == 3


@pytest.mark.asyncio
async def test_run_and_task_events_are_reachable_from_each_campaign_run(tmp_path) -> None:
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )

    started = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignIterationStarted"
    )
    run_events = repositories.list_events(run_id=started.payload["runId"], limit=None)
    assert [event.type for event in run_events][:2] == ["RunCreated", "RunStarted"]


def test_an_observation_cannot_claim_a_state_it_is_not_in() -> None:
    with pytest.raises(ValueError, match="must carry the score"):
        CampaignObservation(iteration=0, candidate={"x": 1.0})
    with pytest.raises(ValueError, match="has no score"):
        CampaignObservation(
            iteration=0,
            candidate={"x": 1.0},
            score=1.0,
            status=CampaignObservationStatus.FAILED,
            error="boom",
        )
    with pytest.raises(ValueError, match="must record why it failed"):
        CampaignObservation(
            iteration=0,
            candidate={"x": 1.0},
            status=CampaignObservationStatus.FAILED,
        )


def test_the_campaign_definition_and_the_runner_do_not_drift() -> None:
    """`CampaignDefinition` is the published schema for what `CampaignRunner.run` accepts.

    Identity fields (`id`, `name`, `objective`, `metadata`) and the two reference fields the runner
    takes as objects rather than names (`workflow_id`, `optimizer`) are excluded. Submission facts —
    `environment`, `operator_id`, `campaign_id` — are deliberately absent from the definition: they
    come from the laboratory manifest and the operator, not from the declared search.
    """

    excluded = {"id", "name", "objective", "metadata", "workflow_id", "optimizer"}
    parameters = inspect.signature(CampaignRunner.run).parameters
    checked = 0
    for name, model_field in CampaignDefinition.model_fields.items():
        if name in excluded:
            continue
        assert name in parameters, f"CampaignDefinition.{name} has no CampaignRunner.run argument"
        default = parameters[name].default
        declared = model_field.get_default(call_default_factory=True)
        # `base_inputs` is the one place the two spell "nothing" differently.
        if default is None and declared == {}:
            checked += 1
            continue
        assert default == declared, f"default for {name} differs between definition and runner"
        checked += 1
    assert checked == len(CampaignDefinition.model_fields) - len(excluded)
    assert {"environment", "operator_id"} <= set(parameters)
    assert not {"environment", "operator_id", "campaign_id"} & set(CampaignDefinition.model_fields)


@pytest.mark.asyncio
async def test_run_and_task_events_carry_the_campaign_that_launched_them(tmp_path) -> None:
    """A campaign is only auditable if the events of its runs answer to it.

    Before this, a query by campaign returned the three campaign event types and no execution
    history at all, so "what did this campaign actually do?" had no answer short of reading
    decision payloads for run identifiers and then fetching each run separately.
    """

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())
    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )

    types = {
        event.type for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
    }
    assert {"RunCreated", "RunStarted", "TaskStarted", "TaskSucceeded", "RunCompleted"} <= types
