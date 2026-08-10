"""Contract tests for the closed loop.

The campaign is the one path OpenSDL runs unattended, so these tests are written around what an
unattended loop has to guarantee: it executes where the caller said it does, it survives a routine
failure, it stops for a stated reason, and it stays domain-neutral.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any

import pytest

from opensdl_capabilities import CapabilityAdapter, CapabilityRegistry
from opensdl_core import (
    AuthorizationEffect,
    CampaignDefinition,
    CapabilityDefinition,
    EventRecord,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    Resource,
    RunState,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowStep,
)
from opensdl_policy import PolicyEngine, PolicyRule
from opensdl_runtime import ReferenceRuntime
from opensdl_runtime.campaign import (
    _trailing_failures,
    BatchOptimizer,
    CampaignIterationState,
    CampaignObservation,
    CampaignObservationStatus,
    CampaignProblem,
    CampaignReader,
    CampaignRunner,
    CampaignState,
    CampaignStopReason,
    CandidateConstraint,
    ConfigurableOptimizer,
    Objective,
    ObjectiveValue,
    Optimizer,
    OutcomeConstraint,
    Parameter,
    ParameterKind,
    SearchSpace,
    StatefulOptimizer,
    Suggestion,
)
from opensdl_storage import Database, LocalArtifactStore, Repositories


#: Outputs every probe capability produces. `cost` moves against `score` so a two-objective search
#: has a real trade-off, `sigma` is a measured uncertainty, and `pressure` is a quantity an outcome
#: constraint can bound.
PROBE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["score"],
    "properties": {
        "score": {"type": "number"},
        "cost": {"type": "number"},
        "sigma": {"type": "number"},
        "pressure": {"type": "number"},
    },
}


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
        self.in_flight = 0
        self.max_in_flight = 0

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
                output_schema=PROBE_OUTPUT_SCHEMA,
                simulator_available=True,
            ),
            CapabilityDefinition(
                id="test.score_exclusive",
                name="Score a candidate on the one bench",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["x"],
                    "properties": {"x": {"type": "number"}},
                },
                output_schema=PROBE_OUTPUT_SCHEMA,
                required_resources=["probe-bench"],
                simulator_available=True,
            ),
            # Declares a timeout and, by omission, the strict retry safety. A probe that stops
            # answering therefore leaves the task — and the run over it — recorded as
            # `intervention_required`: the runtime stopped waiting and established nothing about
            # the equipment. It is what a campaign resume has to refuse to walk past.
            CapabilityDefinition(
                id="test.score_unanswering",
                name="Score a candidate on equipment that can stop answering",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["x"],
                    "properties": {"x": {"type": "number"}},
                },
                output_schema=PROBE_OUTPUT_SCHEMA,
                timeout_seconds=0.02,
                simulator_available=True,
            ),
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        import asyncio

        self.calls.append(dict(request.inputs))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            value = float(request.inputs["x"])
            if value in self.fail_on:
                raise RuntimeError(f"simulated instrument failure at x={value:g}")
            return ExecutionResult(
                request_id=request.request_id,
                output={
                    "score": value,
                    "cost": 10.0 - value,
                    "sigma": round(0.1 * value, 6),
                    "pressure": 2.0 * value,
                },
            )
        finally:
            self.in_flight -= 1


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


def probe_workflow(
    *,
    capability: str = "test.score",
    outputs: dict[str, str] | None = None,
) -> WorkflowDefinition:
    """A one-step workflow that publishes whichever probe outputs the test needs."""

    return WorkflowDefinition(
        id="campaign-probe",
        name="Campaign probe",
        input_schema={
            "type": "object",
            "required": ["x"],
            "properties": {"x": {}},
            "additionalProperties": False,
        },
        steps=[WorkflowStep(id="score", capability=capability, inputs={"x": "${inputs.x}"})],
        outputs=outputs
        or {
            "score": "${steps.score.output.score}",
            "cost": "${steps.score.output.cost}",
            "sigma": "${steps.score.output.sigma}",
            "pressure": "${steps.score.output.pressure}",
        },
    )


def build_campaign(
    tmp_path,
    adapter: ScoreAdapter,
    *,
    policy: PolicyEngine | None = None,
    repositories: Repositories | None = None,
) -> tuple[CampaignRunner, Repositories]:
    if repositories is None:
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
    # Every candidate was decided on, including the one that went on to fail; two of the three
    # completed.
    assert types.count("DecisionRecorded") == 3
    assert types.count("CampaignIterationCompleted") == 2
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


# ---------------------------------------------------------------------------
# What the decision record has to say.
#
# A decision is made before the work it causes, from the evidence that existed when it was made.
# Recording it afterwards, naming the run it caused as its evidence, and describing it with a
# template string leaves a record that contains no decision.
# ---------------------------------------------------------------------------


def _decisions(repositories: Repositories, campaign_id: str) -> list[dict[str, Any]]:
    return [
        event.payload["decision"]
        for event in repositories.list_events(campaign_id=campaign_id, limit=None)
        if event.type == "DecisionRecorded"
    ]


@pytest.mark.asyncio
async def test_the_decision_is_recorded_before_the_run_it_selected(tmp_path) -> None:
    """A decision recorded after its run is a record of an outcome, not of a choice."""

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    ordered = [
        (
            event.type,
            event.payload.get("iteration", event.payload.get("decision", {}).get("iteration")),
        )
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type in {"DecisionRecorded", "CampaignIterationStarted"}
    ]
    assert ordered == [
        ("DecisionRecorded", 0),
        ("CampaignIterationStarted", 0),
        ("DecisionRecorded", 1),
        ("CampaignIterationStarted", 1),
    ]


@pytest.mark.asyncio
async def test_the_decision_names_the_runs_it_was_based_on(tmp_path) -> None:
    """`evidence_run_ids` naming the run a decision caused inverts the provenance direction."""

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    decisions = _decisions(repositories, result.campaign_id)
    assert decisions[0]["evidence_run_ids"] == []
    assert decisions[1]["evidence_run_ids"] == [result.history[0].run_id]


@pytest.mark.asyncio
async def test_a_decision_is_recorded_for_a_candidate_that_went_on_to_fail(tmp_path) -> None:
    """The decision that led to a failure is the one a failure analysis needs to read."""

    runner, repositories = build_campaign(tmp_path, ScoreAdapter(fail_on={2.0}))

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
    )

    decisions = _decisions(repositories, result.campaign_id)
    assert [item["iteration"] for item in decisions] == [0, 1, 2]
    assert [item["selected"] for item in decisions] == [{"x": 3.0}, {"x": 2.0}, {"x": 1.0}]


@pytest.mark.asyncio
async def test_the_rationale_says_what_the_decision_was_based_on(tmp_path) -> None:
    """An optimizer that supplies no reasoning still gets a rationale that is not a template."""

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 2.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    rationale = _decisions(repositories, result.campaign_id)[1]["rationale"]
    assert "1 prior observation" in rationale


# ---------------------------------------------------------------------------
# The optional half of the optimizer contract.
#
# `GridOptimizer` and `ListOptimizer` above are the two-method form and must keep working
# untouched. Everything below is exercised by one test-only optimizer that implements every
# optional part at once, because a contract nobody has implemented end to end is a guess.
# ---------------------------------------------------------------------------


class ScriptedOptimizer:
    """A test-only optimizer that exercises every optional part of the contract.

    It does not optimize: it replays a scripted plan of batches. What it proves is that the
    protocol can carry a batch, be told the problem the campaign declared, attach a prediction with
    an uncertainty, name its acquisition function and value, identify its model, narrow its own
    evidence, and expose its state — and that the runner carries all of it into the durable record.
    """

    def __init__(
        self,
        plan: list[list[dict[str, Any]]],
        *,
        acquisition_function: str = "qEI",
        evidence_run_ids: tuple[str, ...] | None = None,
    ) -> None:
        self.plan = plan
        self.acquisition_function = acquisition_function
        self.evidence_run_ids = evidence_run_ids
        self.problem: CampaignProblem | None = None
        self.observed: list[CampaignObservation] = []
        self.requested: list[int] = []
        self.threads: list[int] = []

    def configure(self, problem: CampaignProblem) -> None:
        self.problem = problem

    def suggest_batch(
        self,
        history: list[CampaignObservation],
        *,
        count: int,
    ) -> list[Suggestion] | None:
        self.threads.append(threading.get_ident())
        self.requested.append(count)
        batch = len(self.requested) - 1
        if batch >= len(self.plan):
            return None
        return [
            Suggestion(
                parameters=dict(parameters),
                predictions={
                    "score": ObjectiveValue(value=float(parameters["x"]), uncertainty=0.25),
                },
                acquisition=round(1.0 / (1.0 + float(parameters["x"])), 6),
                acquisition_function=self.acquisition_function,
                model={"name": "scripted", "version": "1", "fitted_on": len(history)},
                rationale=f"scripted batch {batch} position {position}",
                evidence_run_ids=self.evidence_run_ids,
            )
            for position, parameters in enumerate(self.plan[batch])
        ]

    def suggest(self, history: list[CampaignObservation]) -> Suggestion | None:
        proposed = self.suggest_batch(history, count=1)
        return proposed[0] if proposed else None

    def observe(self, observation: CampaignObservation) -> None:
        self.observed.append(observation)

    def state(self) -> dict[str, Any]:
        return {"model": "scripted/1", "observations": len(self.observed)}


def objectives_for(*names: str) -> list[Objective]:
    declared = {
        "score": Objective(name="score", output="score", minimize=True, uncertainty_output="sigma"),
        "cost": Objective(name="cost", output="cost", minimize=True),
    }
    return [declared[name] for name in names]


@pytest.mark.asyncio
async def test_a_two_method_optimizer_still_satisfies_the_protocol(tmp_path) -> None:
    """The published contract is `suggest` and `observe`, and nothing was added to it."""

    assert isinstance(ListOptimizer([]), Optimizer)
    assert not isinstance(ListOptimizer([]), BatchOptimizer)
    assert not isinstance(ListOptimizer([]), ConfigurableOptimizer)
    assert not isinstance(ListOptimizer([]), StatefulOptimizer)

    scripted = ScriptedOptimizer([[{"x": 1.0}]])
    assert isinstance(scripted, Optimizer)
    assert isinstance(scripted, BatchOptimizer)
    assert isinstance(scripted, ConfigurableOptimizer)
    assert isinstance(scripted, StatefulOptimizer)

    runner, _ = build_campaign(tmp_path, ScoreAdapter())
    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )
    assert result.stop_reason is CampaignStopReason.OPTIMIZER_EXHAUSTED or result.successes


# --- 1. Batch and parallel suggestion ---------------------------------------


@pytest.mark.asyncio
async def test_a_batch_optimizer_is_asked_for_a_batch_and_every_candidate_runs(tmp_path) -> None:
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    optimizer = ScriptedOptimizer([[{"x": 3.0}, {"x": 2.0}], [{"x": 1.0}, {"x": 4.0}]])

    result = await runner.run(
        scoring_workflow(),
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=4,
        batch_size=2,
    )

    assert optimizer.requested == [2, 2]
    assert [item.iteration for item in result.history] == [0, 1, 2, 3]
    assert [item.candidate["x"] for item in result.history] == [3.0, 2.0, 1.0, 4.0]
    assert [item.batch for item in result.history] == [0, 0, 1, 1]
    assert len(repositories.list_runs()) == 4
    record = CampaignReader(repositories).get(result.campaign_id)
    assert record.batch_size == 2
    assert [item.decision.batch_index for item in record.iterations if item.decision] == [
        0,
        1,
        0,
        1,
    ]


@pytest.mark.asyncio
async def test_a_batch_is_truncated_to_the_iteration_budget_that_remains(tmp_path) -> None:
    """The iteration budget bounds physical work, so an oversized batch is cut, not honoured."""

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    optimizer = ScriptedOptimizer([[{"x": 3.0}, {"x": 2.0}, {"x": 1.0}]])

    result = await runner.run(
        scoring_workflow(),
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        batch_size=4,
    )

    assert optimizer.requested == [2]
    assert len(result.history) == 2
    assert len(adapter.calls) == 2
    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS


@pytest.mark.asyncio
async def test_a_batch_runs_one_candidate_at_a_time_unless_the_campaign_says_otherwise(
    tmp_path,
) -> None:
    """Proposing a batch and executing it in parallel are separate declarations.

    How many candidates an optimizer proposes jointly is a property of the method. How many runs
    the laboratory can have in flight is a property of the laboratory, and it defaults to one.
    """

    adapter = ScoreAdapter(delay_seconds=0.02)
    runner, _ = build_campaign(tmp_path, adapter)

    await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 3.0}, {"x": 2.0}, {"x": 1.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
        batch_size=3,
    )

    assert adapter.max_in_flight == 1


@pytest.mark.asyncio
async def test_a_declared_parallelism_runs_the_batch_concurrently(tmp_path) -> None:
    adapter = ScoreAdapter(delay_seconds=0.02)
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 3.0}, {"x": 2.0}, {"x": 1.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
        batch_size=3,
        max_parallel_runs=3,
    )

    assert adapter.max_in_flight == 3
    assert [item.iteration for item in result.history] == [0, 1, 2]
    assert [item.candidate["x"] for item in result.history] == [3.0, 2.0, 1.0]
    assert len(result.successes) == 3
    assert {run.id for run in repositories.list_runs()} == {
        item.run_id for item in result.history if item.run_id
    }


@pytest.mark.asyncio
async def test_parallel_candidates_contending_for_one_instrument_are_recorded_as_failures(
    tmp_path,
) -> None:
    """The honest limit of parallel execution: the runner does not schedule around a lease.

    Two candidates needing the same exclusive instrument are dispatched together, and the loser
    fails on the lease. It is recorded as an attempted iteration, because a lease failure is a
    laboratory fact and not a framework error.
    """

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    repositories.upsert_resource(Resource(id="probe-bench", name="Probe bench", type="simulator"))

    result = await runner.run(
        probe_workflow(
            capability="test.score_exclusive", outputs={"score": "${steps.score.output.score}"}
        ),
        ScriptedOptimizer([[{"x": 3.0}, {"x": 2.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        batch_size=2,
        max_parallel_runs=2,
    )

    assert len(result.failures) == 1
    assert "resources busy" in (result.failures[0].error or "")


# --- 2. Multi-objective and constraints -------------------------------------


@pytest.mark.asyncio
async def test_two_objectives_produce_a_pareto_front_and_a_best_by_the_primary(tmp_path) -> None:
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        probe_workflow(),
        ScriptedOptimizer([[{"x": 3.0}, {"x": 1.0}, {"x": 2.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=3,
        batch_size=3,
        objectives=objectives_for("score", "cost"),
    )

    assert [item.objectives["score"].value for item in result.history] == [3.0, 1.0, 2.0]
    assert [item.objectives["cost"].value for item in result.history] == [7.0, 9.0, 8.0]
    # score falls as cost rises, so every point is non-dominated.
    assert {item.iteration for item in result.pareto_front} == {0, 1, 2}
    assert result.best is not None and result.best.candidate == {"x": 1.0}
    record = CampaignReader(repositories).get(result.campaign_id)
    assert record.problem is not None
    assert [item.name for item in record.problem.objectives] == ["score", "cost"]
    assert record.iterations[0].objectives["cost"].value == 7.0


@pytest.mark.asyncio
async def test_a_candidate_outside_the_declared_space_is_refused_before_anything_is_leased(
    tmp_path,
) -> None:
    """A bad candidate reached `RunCreated`, `PolicyEvaluated` and `TaskStarted` before rejection."""

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 9.0}], [{"x": 1.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        search_space=SearchSpace(parameters=[Parameter.continuous("x", 0.0, 5.0)]),
    )

    rejected = result.history[0]
    assert rejected.status is CampaignObservationStatus.REJECTED
    assert rejected.run_id is None
    assert not rejected.feasible
    assert any("9" in item and "x" in item for item in rejected.constraint_violations)
    assert [call["x"] for call in adapter.calls] == [1.0]
    assert len(repositories.list_runs()) == 1
    types = [
        event.type for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
    ]
    assert types.count("CampaignCandidateRejected") == 1
    # The decision was still made and is still recorded; only the work was refused.
    assert types.count("DecisionRecorded") == 2
    record = CampaignReader(repositories).get(result.campaign_id)
    assert record.iterations[0].state is CampaignIterationState.REJECTED
    assert record.rejected == 1


@pytest.mark.asyncio
async def test_a_declared_candidate_constraint_is_enforced_before_the_run(tmp_path) -> None:
    """The reference example encodes `blue = 1 - red` by construction. This declares it."""

    adapter = ScoreAdapter()
    runner, _ = build_campaign(tmp_path, adapter)
    space = SearchSpace(
        parameters=[Parameter.continuous("x", 0.0, 1.0), Parameter.continuous("y", 0.0, 1.0)]
    )
    workflow = WorkflowDefinition(
        id="campaign-probe",
        name="Campaign probe",
        input_schema={
            "type": "object",
            "required": ["x", "y"],
            "properties": {"x": {}, "y": {}},
            "additionalProperties": False,
        },
        steps=[WorkflowStep(id="score", capability="test.score", inputs={"x": "${inputs.x}"})],
        outputs={"score": "${steps.score.output.score}"},
    )

    result = await runner.run(
        workflow,
        ScriptedOptimizer([[{"x": 0.3, "y": 0.3}], [{"x": 0.25, "y": 0.75}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        search_space=space,
        candidate_constraints=[
            CandidateConstraint(
                name="fractions-sum-to-one", weights={"x": 1.0, "y": 1.0}, lower=1.0, upper=1.0
            )
        ],
    )

    assert result.history[0].status is CampaignObservationStatus.REJECTED
    assert "fractions-sum-to-one" in (result.history[0].error or "")
    assert result.history[1].status is CampaignObservationStatus.SUCCEEDED
    assert [call["x"] for call in adapter.calls] == [0.25]


@pytest.mark.asyncio
async def test_an_infeasible_result_is_recorded_scored_and_excluded_from_best(tmp_path) -> None:
    """A run that violated an outcome constraint happened, produced data, and cannot win."""

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        probe_workflow(),
        ScriptedOptimizer([[{"x": 1.0}, {"x": 3.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        batch_size=2,
        objectives=objectives_for("score"),
        outcome_constraints=[
            OutcomeConstraint(name="pressure-limit", output="pressure", lower=5.0)
        ],
        target_score=2.0,
    )

    infeasible = result.history[0]
    assert infeasible.status is CampaignObservationStatus.SUCCEEDED
    assert infeasible.score == 1.0
    assert not infeasible.feasible
    assert "pressure-limit" in " ".join(infeasible.constraint_violations)
    # The lower score is infeasible, so the feasible higher score is the best the campaign has.
    assert result.best is not None and result.best.candidate == {"x": 3.0}
    # And an infeasible observation does not reach a target.
    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
    record = CampaignReader(repositories).get(result.campaign_id)
    assert record.iterations[0].feasible is False
    assert record.best is not None and record.best.iteration == 1


@pytest.mark.asyncio
async def test_an_optimizer_that_only_proposes_refused_candidates_stops(tmp_path) -> None:
    """A rejected candidate consumes the budget, so a broken optimizer cannot loop forever."""

    adapter = ScoreAdapter()
    runner, _ = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 9.0}], [{"x": 8.0}], [{"x": 7.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=10,
        max_consecutive_failures=2,
        search_space=SearchSpace(parameters=[Parameter.continuous("x", 0.0, 5.0)]),
    )

    assert result.stop_reason is CampaignStopReason.FAILURE_LIMIT
    assert len(result.history) == 2
    assert adapter.calls == []


# --- 3 and 4. The declared problem reaches the optimizer, with uncertainty ---


@pytest.mark.asyncio
async def test_the_optimizer_is_told_the_problem_the_campaign_declared(tmp_path) -> None:
    """The search space is the framework's, not the plugin's private configuration."""

    runner, _ = build_campaign(tmp_path, ScoreAdapter())
    optimizer = ScriptedOptimizer([[{"x": 1.0}]])
    space = SearchSpace(parameters=[Parameter.continuous("x", 0.0, 5.0)])

    await runner.run(
        probe_workflow(),
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
        search_space=space,
        objectives=objectives_for("score", "cost"),
        outcome_constraints=[
            OutcomeConstraint(name="pressure-limit", output="pressure", upper=9.0)
        ],
    )

    assert optimizer.problem is not None
    assert [item.name for item in optimizer.problem.objectives] == ["score", "cost"]
    assert optimizer.problem.space.parameters[0].upper == 5.0
    assert optimizer.problem.outcome_constraints[0].name == "pressure-limit"
    assert optimizer.problem.primary.name == "score"


@pytest.mark.asyncio
async def test_measured_and_predicted_uncertainty_both_reach_the_record(tmp_path) -> None:
    """Core carries uncertainty on `Quantity` and `Observation`; the closed loop now does too."""

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        probe_workflow(),
        ScriptedOptimizer([[{"x": 2.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
        objectives=objectives_for("score"),
    )

    observed = result.history[0].objectives["score"]
    assert observed.value == 2.0
    assert observed.uncertainty == 0.2
    record = CampaignReader(repositories).get(result.campaign_id)
    iteration = record.iterations[0]
    assert iteration.objectives["score"].uncertainty == 0.2
    assert iteration.decision is not None
    assert iteration.decision.predictions["score"].value == 2.0
    assert iteration.decision.predictions["score"].uncertainty == 0.25


# --- 5. Acquisition provenance ----------------------------------------------


@pytest.mark.asyncio
async def test_the_decision_record_carries_the_reasoning_that_produced_it(tmp_path) -> None:
    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 3.0}, {"x": 1.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
        batch_size=2,
    )

    events = [
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "DecisionRecorded"
    ]
    assert [event.payload["acquisitionFunction"] for event in events] == ["qEI", "qEI"]
    assert events[0].payload["acquisition"] == 0.25
    assert events[0].payload["model"]["name"] == "scripted"
    assert events[0].payload["predictions"]["score"] == {"value": 3.0, "uncertainty": 0.25}
    assert events[0].payload["batchSize"] == 2
    assert "scripted batch 0 position 0" in events[0].payload["decision"]["rationale"]

    record = CampaignReader(repositories).get(result.campaign_id)
    decision = record.iterations[1].decision
    assert decision is not None
    assert decision.acquisition_function == "qEI"
    assert decision.model["fitted_on"] == 0
    assert decision.batch_index == 1


@pytest.mark.asyncio
async def test_an_optimizer_may_narrow_the_evidence_its_decision_rests_on(tmp_path) -> None:
    """A trust-region method uses a subset of history, and the record should say which subset."""

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 3.0}], [{"x": 1.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    decisions = _decisions(repositories, result.campaign_id)
    assert decisions[1]["evidence_run_ids"] == [result.history[0].run_id]

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())
    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 3.0}], [{"x": 1.0}]], evidence_run_ids=("run-elsewhere",)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )
    decisions = _decisions(repositories, result.campaign_id)
    assert decisions[1]["evidence_run_ids"] == ["run-elsewhere"]


# --- 6. The proposal step does not hold the event loop ----------------------


@pytest.mark.asyncio
async def test_a_synchronous_suggest_runs_off_the_event_loop_thread(tmp_path) -> None:
    """A GP refit inside `suggest` held the only loop in the process, so nothing else moved."""

    runner, _ = build_campaign(tmp_path, ScoreAdapter())
    optimizer = ScriptedOptimizer([[{"x": 1.0}]])

    await runner.run(
        scoring_workflow(),
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )

    assert optimizer.threads
    assert threading.get_ident() not in optimizer.threads


@pytest.mark.asyncio
async def test_an_optimizer_that_must_await_can_declare_its_methods_async(tmp_path) -> None:
    class AwaitingOptimizer:
        def __init__(self) -> None:
            self.loops: list[int] = []
            self.observed: list[CampaignObservation] = []

        async def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None:
            import asyncio

            self.loops.append(id(asyncio.get_running_loop()))
            await asyncio.sleep(0)
            return {"x": 1.0} if not history else None

        async def observe(self, observation: CampaignObservation) -> None:
            self.observed.append(observation)

    import asyncio

    runner, _ = build_campaign(tmp_path, ScoreAdapter())
    optimizer = AwaitingOptimizer()

    result = await runner.run(
        scoring_workflow(),
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    assert optimizer.loops == [id(asyncio.get_running_loop())] * 2
    assert len(optimizer.observed) == 1
    assert result.stop_reason is CampaignStopReason.OPTIMIZER_EXHAUSTED


# --- The seam left for campaign resume (B4) ---------------------------------


@pytest.mark.asyncio
async def test_an_optimizer_that_holds_state_has_it_preserved_with_the_campaign(tmp_path) -> None:
    """Resume is not implemented. Preserving the state a resume would need is.

    Nothing reads this back yet, which is exactly the gap `B4` names. What this makes true is that
    the state exists in the durable record rather than only in a process that has exited.
    """

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ScriptedOptimizer([[{"x": 3.0}], [{"x": 1.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    assert completed.payload["optimizerState"] == {"model": "scripted/1", "observations": 2}
    record = CampaignReader(repositories).get(result.campaign_id)
    assert record.optimizer_state == {"model": "scripted/1", "observations": 2}


@pytest.mark.asyncio
async def test_an_optimizer_whose_state_cannot_be_read_does_not_lose_the_campaign(
    tmp_path,
) -> None:
    class BrokenState(ListOptimizer):
        def state(self) -> dict[str, Any]:
            raise RuntimeError("the surrogate is not serialisable")

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        BrokenState(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )

    assert len(result.successes) == 1
    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    assert completed.payload["optimizerState"] is None
    assert "not serialisable" in completed.payload["optimizerStateError"]


# --- The declared problem validates itself ----------------------------------


def test_a_search_space_reports_every_way_a_candidate_leaves_it() -> None:
    space = SearchSpace(
        parameters=[
            Parameter.continuous("temperature", 20.0, 80.0),
            Parameter.integer("replicates", 1, 3),
            Parameter.categorical("solvent", ["water", "ethanol"]),
        ]
    )

    assert space.violations({"temperature": 50.0, "replicates": 2, "solvent": "water"}) == []
    assert space.violations({"temperature": 90.0, "replicates": 2, "solvent": "water"})
    assert space.violations({"temperature": 50.0, "replicates": 2.5, "solvent": "water"})
    assert space.violations({"temperature": 50.0, "replicates": 2, "solvent": "acetone"})
    assert space.violations({"temperature": 50.0, "replicates": 2})
    assert space.violations(
        {"temperature": 50.0, "replicates": 2, "solvent": "water", "stir": True}
    )
    # A campaign that declares no space validates nothing, which is how the two-method form runs.
    assert SearchSpace().violations({"anything": object()}) == []


def test_a_parameter_cannot_declare_a_domain_it_does_not_have() -> None:
    with pytest.raises(ValueError):
        Parameter.continuous("x", 5.0, 1.0)
    with pytest.raises(ValueError):
        Parameter.categorical("x", [])
    with pytest.raises(ValueError):
        Parameter(name="x", kind=ParameterKind.CONTINUOUS)


def test_a_candidate_constraint_bounds_a_linear_combination() -> None:
    constraint = CandidateConstraint(
        name="sum-to-one", weights={"a": 1.0, "b": 1.0}, lower=1.0, upper=1.0
    )

    assert constraint.violation({"a": 0.25, "b": 0.75}) is None
    assert constraint.violation({"a": 0.1, "b": 0.9}) is None
    assert constraint.violation({"a": 0.5, "b": 0.4}) is not None
    assert constraint.violation({"a": 0.5}) is not None
    with pytest.raises(ValueError):
        CandidateConstraint(name="unbounded", weights={"a": 1.0})


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


#: Fields of `CampaignDefinition` that deliberately have no `CampaignRunner.run` argument.
#: Identity is a property of the document; the reference fields name what the runner is handed as
#: an object, because the runner receives an optimizer already constructed and how to construct one
#: is a property of the definition rather than an argument.
DEFINITION_ONLY_FIELDS = {
    "id",
    "name",
    "objective",
    "metadata",
    "workflow_id",
    "optimizer",
    "optimizer_config",
}

#: `CampaignRunner.run` arguments that deliberately have no `CampaignDefinition` field.
#: `workflow` and `optimizer` are the objects the reference fields above name. The submission
#: facts come from the laboratory manifest and the operator, not from a stored search: a definition
#: that asserted its own environment could assert one its laboratory never declared. `resume` is a
#: property of one invocation — whether *this* call continues an existing campaign — and a stored
#: document that declared it would mean something different on every run.
RUNNER_ONLY_ARGUMENTS = {
    "self",
    "workflow",
    "optimizer",
    "environment",
    "operator_id",
    "campaign_id",
    "resume",
}


def _is_empty(value: object) -> bool:
    """Whether a default means "nothing declared", however the two sides spell it."""

    return value is None or value == () or value == [] or value == {} or value == SearchSpace()


def test_the_campaign_definition_and_the_runner_do_not_drift() -> None:
    """`CampaignDefinition` is the published schema for what `CampaignRunner.run` accepts.

    Checked in both directions. The forward direction — every definition field has a runner
    argument — is what the first version of this test asserted, and it cannot see the failure that
    actually happened: `objectives`, `search_space` and both constraint lists were added to the
    runner with no field on the definition, so a stored definition could not describe a real
    campaign and no test noticed. Anything either side gains from here has to be named in one of
    the two exclusion sets above, with the reason written down.
    """

    parameters = inspect.signature(CampaignRunner.run).parameters
    fields = CampaignDefinition.model_fields

    checked = 0
    for name, model_field in fields.items():
        if name in DEFINITION_ONLY_FIELDS:
            continue
        assert name in parameters, f"CampaignDefinition.{name} has no CampaignRunner.run argument"
        default = parameters[name].default
        declared = model_field.get_default(call_default_factory=True)
        if not (_is_empty(default) and _is_empty(declared)):
            assert default == declared, f"default for {name} differs between definition and runner"
        checked += 1
    assert checked == len(fields) - len(DEFINITION_ONLY_FIELDS)

    for name in parameters:
        if name in RUNNER_ONLY_ARGUMENTS:
            continue
        assert name in fields, (
            f"CampaignRunner.run takes {name!r} and CampaignDefinition cannot declare it, so a "
            "stored campaign definition cannot describe a campaign that uses it"
        )

    assert {"environment", "operator_id"} <= set(parameters)
    assert not {"environment", "operator_id", "campaign_id"} & set(fields)
    assert DEFINITION_ONLY_FIELDS <= set(fields)
    assert RUNNER_ONLY_ARGUMENTS <= set(parameters)


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


# ---------------------------------------------------------------------------
# Reading a campaign back.
#
# A campaign has no table and no record of its own: its state lives entirely in the events it
# emitted. Reconstructing it from those events is the only reading that cannot disagree with what
# happened, and it is what makes a campaign reachable from an interface at all.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_finished_campaign_is_reconstructed_from_its_events(tmp_path) -> None:
    adapter = ScoreAdapter(fail_on={2.0})
    runner, repositories = build_campaign(tmp_path, adapter)

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(3.0, 2.0, 1.0)),
        environment="production",
        operator_id="operator/alice",
        max_iterations=3,
        target_score=1.5,
        base_inputs={},
    )

    record = CampaignReader(repositories).get(result.campaign_id)

    assert record.campaign_id == result.campaign_id
    assert record.state is CampaignState.COMPLETED
    assert record.environment == "production"
    assert record.operator_id == "operator/alice"
    assert record.workflow_id == "campaign-probe"
    assert record.max_iterations == 3
    assert record.target_score == 1.5
    assert record.minimize is True
    assert record.score_output == "score"
    assert record.stop_reason is CampaignStopReason.TARGET_REACHED
    assert "target" in record.stop_detail
    assert record.started_at is not None
    assert record.completed_at is not None
    assert [item.iteration for item in record.iterations] == [0, 1, 2]
    assert [item.state for item in record.iterations] == [
        CampaignIterationState.SUCCEEDED,
        CampaignIterationState.FAILED,
        CampaignIterationState.SUCCEEDED,
    ]
    assert [item.candidate for item in record.iterations] == [{"x": 3.0}, {"x": 2.0}, {"x": 1.0}]
    assert [item.score for item in record.iterations] == [3.0, None, 1.0]
    assert record.iterations[1].error is not None
    assert "simulated instrument failure" in record.iterations[1].error
    assert record.succeeded == 2
    assert record.failed == 1
    assert record.best is not None and record.best.candidate == {"x": 1.0}
    # Every iteration names the run it launched, so the execution history is one query away.
    launched = {item.run_id for item in record.iterations}
    assert launched == {run.id for run in repositories.list_runs()}


@pytest.mark.asyncio
async def test_a_campaign_with_no_recorded_completion_reads_as_running(tmp_path) -> None:
    """A controller that died mid-campaign leaves exactly this, and so does a live campaign.

    The events cannot tell the two apart, and the record does not pretend otherwise: it reports
    what was recorded, which is a start with no completion.
    """

    _, repositories = build_campaign(tmp_path, ScoreAdapter())
    repositories.append_event(
        EventRecord(
            type="CampaignStarted",
            actor_id="operator/alice",
            campaign_id="campaign-live",
            payload={
                "workflowId": "campaign-probe",
                "workflowVersion": "0.1.0",
                "environment": "production",
                "operatorId": "operator/alice",
                "maxIterations": 4,
                "scoreOutput": "score",
                "minimize": True,
                "targetScore": None,
                "maxConsecutiveFailures": 3,
                "maxDurationSeconds": None,
                "iterationIdInput": "sample_id",
                "baseInputs": {"total_mass_g": 5.0},
            },
        )
    )
    repositories.append_event(
        EventRecord(
            type="CampaignIterationStarted",
            actor_id="operator/alice",
            campaign_id="campaign-live",
            payload={
                "iteration": 0,
                "candidate": {"x": 1.0},
                "runId": "run-live",
                "environment": "production",
            },
        )
    )

    record = CampaignReader(repositories).get("campaign-live")

    assert record.state is CampaignState.RUNNING
    assert record.stop_reason is None
    assert record.completed_at is None
    assert record.base_inputs == {"total_mass_g": 5.0}
    assert record.iteration_id_input == "sample_id"
    assert [item.state for item in record.iterations] == [CampaignIterationState.RUNNING]
    assert record.iterations[0].run_id == "run-live"


def test_a_campaign_nothing_recorded_is_not_invented(tmp_path) -> None:
    _, repositories = build_campaign(tmp_path, ScoreAdapter())

    with pytest.raises(KeyError):
        CampaignReader(repositories).get("campaign-that-never-ran")


@pytest.mark.asyncio
async def test_campaigns_are_listed_newest_first_and_only_once(tmp_path) -> None:
    runner, repositories = build_campaign(tmp_path, ScoreAdapter())
    first = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )
    second = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(2.0)),
        environment="simulation",
        operator_id="operator/bob",
        max_iterations=1,
    )

    listed = CampaignReader(repositories).list()

    assert [item.campaign_id for item in listed] == [second.campaign_id, first.campaign_id]
    assert [item.operator_id for item in listed] == ["operator/bob", "operator/alice"]
    assert all(item.state is CampaignState.COMPLETED for item in listed)


@pytest.mark.asyncio
async def test_only_a_campaign_without_a_completion_is_reported_active(tmp_path) -> None:
    runner, repositories = build_campaign(tmp_path, ScoreAdapter())
    finished = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )
    repositories.append_event(
        EventRecord(
            type="CampaignStarted",
            actor_id="operator/bob",
            campaign_id="campaign-live",
            payload={
                "workflowId": "campaign-probe",
                "workflowVersion": "0.1.0",
                "environment": "simulation",
                "operatorId": "operator/bob",
                "maxIterations": 2,
                "scoreOutput": "score",
                "minimize": True,
                "targetScore": None,
                "maxConsecutiveFailures": 3,
                "maxDurationSeconds": None,
                "iterationIdInput": None,
                "baseInputs": {},
            },
        )
    )

    active = CampaignReader(repositories).active()

    assert [item.campaign_id for item in active] == ["campaign-live"]
    assert finished.campaign_id not in {item.campaign_id for item in active}


class DyingOptimizer:
    """Proposes from a list and then stops answering, the way a dying controller process does.

    A campaign that is interrupted is interrupted somewhere, and the place that is hardest to
    resume from is between "the work was done" and "the record says so". Raising out of `suggest`
    reproduces the easier half of that — a campaign with a start, some completed iterations, and no
    completion — without touching the runner's internals.
    """

    def __init__(self, candidates: list[dict[str, Any]], *, die_after: int) -> None:
        self.candidates = [dict(item) for item in candidates]
        self.die_after = die_after
        self.proposed = 0

    def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None:
        if self.proposed >= self.die_after:
            raise RuntimeError("the controller process went away")
        tried = [item.candidate for item in history]
        for candidate in self.candidates:
            if candidate not in tried:
                self.proposed += 1
                return dict(candidate)
        return None

    def observe(self, observation: CampaignObservation) -> None:
        return None


class SurrogateOptimizer:
    """An optimizer with something to restore: a fitted count it cannot rebuild from history."""

    def __init__(self, candidates: list[dict[str, Any]], *, version: str = "1") -> None:
        self.candidates = [dict(item) for item in candidates]
        self.version = version
        self.fits = 0
        self.observed: list[CampaignObservation] = []
        self.configured: CampaignProblem | None = None
        self.loaded: dict[str, Any] | None = None

    def configure(self, problem: CampaignProblem) -> None:
        self.configured = problem

    def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None:
        tried = [item.candidate for item in history]
        for candidate in self.candidates:
            if candidate not in tried:
                return dict(candidate)
        return None

    def observe(self, observation: CampaignObservation) -> None:
        self.observed.append(observation)
        self.fits += 1

    def state(self) -> dict[str, Any]:
        return {"fits": self.fits, "version": self.version}

    def load_state(self, state: dict[str, Any]) -> None:
        if state.get("version") != self.version:
            raise ValueError(f"state was fitted by version {state.get('version')}")
        self.loaded = dict(state)
        self.fits = int(state["fits"])


class InterruptedEventStore(Repositories):
    """A store whose campaign event write fails once, after the run it describes has finished.

    This is the interruption that matters: the laboratory did the work, the run record says so,
    and the campaign's own record of the outcome was never written. A resume that trusted only its
    own events would re-dispatch a candidate that has already been through the equipment.
    """

    def __init__(self, database: Database, *, event_type: str, iteration: int) -> None:
        super().__init__(database)
        self.event_type = event_type
        self.iteration = iteration
        self.raised = False

    def append_event(self, event: EventRecord) -> EventRecord:
        if (
            not self.raised
            and event.type == self.event_type
            and event.payload.get("iteration") == self.iteration
        ):
            self.raised = True
            raise RuntimeError("the event store went away before the outcome was recorded")
        return super().append_event(event)


def campaign_events(repositories: Repositories, campaign_id: str, type_: str) -> list[EventRecord]:
    return [
        event
        for event in repositories.list_events(campaign_id=campaign_id, limit=None)
        if event.type == type_
    ]


@pytest.mark.asyncio
async def test_a_second_campaign_under_the_same_identifier_is_refused(tmp_path) -> None:
    """Re-running one is not resuming it: it restarts iteration numbering under the same name.

    Without this the second invocation emits a second `CampaignStarted`, numbers its iterations
    from zero again, and `(campaign_id, iteration)` stops identifying a decision.
    """

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    await runner.run(
        workflow,
        ListOptimizer(candidates(1.0, 2.0)),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_once",
        max_iterations=2,
    )

    with pytest.raises(ValueError, match="resume=True"):
        await runner.run(
            workflow,
            ListOptimizer(candidates(1.0, 2.0)),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_once",
            max_iterations=2,
        )

    assert len(campaign_events(repositories, "campaign_once", "CampaignStarted")) == 1
    assert [call["x"] for call in adapter.calls] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_resuming_a_campaign_nothing_recorded_is_refused(tmp_path) -> None:
    """A typo in the identifier would otherwise silently start a fresh campaign under it."""

    runner, _ = build_campaign(tmp_path, ScoreAdapter())

    with pytest.raises(ValueError, match="no campaign is recorded"):
        await runner.run(
            scoring_workflow(),
            ListOptimizer(candidates(1.0)),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_typo",
            max_iterations=1,
            resume=True,
        )


@pytest.mark.asyncio
async def test_resume_requires_the_identifier_of_the_campaign_being_resumed(tmp_path) -> None:
    runner, _ = build_campaign(tmp_path, ScoreAdapter())

    with pytest.raises(ValueError, match="campaign_id"):
        await runner.run(
            scoring_workflow(),
            ListOptimizer(candidates(1.0)),
            environment="simulation",
            operator_id="operator/alice",
            max_iterations=1,
            resume=True,
        )


@pytest.mark.asyncio
async def test_an_interrupted_campaign_resumes_without_repeating_completed_work(tmp_path) -> None:
    """The failure this exists to prevent: a resumed campaign putting a sample through twice.

    The first process runs two of four iterations and dies. The second is a different optimizer
    object with no memory of any of it, and it has to learn what was done from the record the
    laboratory kept — not from a caller's account of it.
    """

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0, 4.0)

    with pytest.raises(RuntimeError, match="went away"):
        await runner.run(
            workflow,
            DyingOptimizer(plan, die_after=2),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_interrupted",
            max_iterations=4,
        )
    assert [call["x"] for call in adapter.calls] == [1.0, 2.0]
    interrupted = CampaignReader(repositories).get("campaign_interrupted")
    assert interrupted.state is CampaignState.RUNNING

    optimizer = ListOptimizer(plan)
    result = await runner.run(
        workflow,
        optimizer,
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_interrupted",
        max_iterations=4,
        resume=True,
    )

    # Each candidate reached the equipment exactly once, across both processes.
    assert [call["x"] for call in adapter.calls] == [1.0, 2.0, 3.0, 4.0]
    assert [item.candidate["x"] for item in result.history] == [1.0, 2.0, 3.0, 4.0]
    assert [item.iteration for item in result.history] == [0, 1, 2, 3]
    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
    assert result.best is not None and result.best.candidate == {"x": 1.0}

    # The two iterations the first process ran were replayed into the new optimizer, because it
    # had no state to restore and would otherwise be searching from nothing.
    assert [item.candidate["x"] for item in optimizer.observed] == [1.0, 2.0, 3.0, 4.0]

    decisions = campaign_events(repositories, "campaign_interrupted", "DecisionRecorded")
    numbered = [event.payload["decision"]["iteration"] for event in decisions]
    assert numbered == [0, 1, 2, 3], "a resumed campaign must not restart iteration numbering"
    assert len(campaign_events(repositories, "campaign_interrupted", "CampaignStarted")) == 1
    assert len(campaign_events(repositories, "campaign_interrupted", "CampaignResumed")) == 1

    projected = CampaignReader(repositories).get("campaign_interrupted")
    assert projected.state is CampaignState.COMPLETED
    assert projected.succeeded == 4
    assert projected.resume_count == 1
    assert projected.resumed_at is not None


@pytest.mark.asyncio
async def test_a_resume_recovers_an_outcome_the_dying_controller_never_recorded(tmp_path) -> None:
    """The run finished; the campaign's record of it did not. Resume reads the run, not a guess.

    Reconstructing history from campaign events alone would show this iteration still running and
    its candidate untried, so a stateless optimizer would propose it again and the laboratory would
    repeat work it has already done.
    """

    database = Database("sqlite:///:memory:")
    database.initialize()
    store = InterruptedEventStore(database, event_type="CampaignIterationCompleted", iteration=1)
    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter, repositories=store)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0)

    with pytest.raises(RuntimeError, match="event store went away"):
        await runner.run(
            workflow,
            ListOptimizer(plan),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_halfrecorded",
            max_iterations=3,
        )
    assert [call["x"] for call in adapter.calls] == [1.0, 2.0]
    stranded = CampaignReader(repositories).get("campaign_halfrecorded")
    assert stranded.iterations[1].state is CampaignIterationState.RUNNING

    result = await runner.run(
        workflow,
        ListOptimizer(plan),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_halfrecorded",
        max_iterations=3,
        resume=True,
    )

    assert [call["x"] for call in adapter.calls] == [1.0, 2.0, 3.0]
    assert [item.candidate["x"] for item in result.history] == [1.0, 2.0, 3.0]
    recovered = result.history[1]
    assert recovered.succeeded and recovered.score == 2.0
    assert recovered.outputs == {"score": 2.0}

    projected = CampaignReader(repositories).get("campaign_halfrecorded")
    assert projected.iterations[1].state is CampaignIterationState.SUCCEEDED
    assert projected.iterations[1].score == 2.0
    catchup = campaign_events(repositories, "campaign_halfrecorded", "CampaignIterationCompleted")
    assert [event.payload["iteration"] for event in catchup] == [0, 1, 2]
    assert [event.payload.get("recovered", False) for event in catchup] == [False, True, False]


@pytest.mark.asyncio
async def test_a_resume_refuses_to_continue_over_a_run_whose_outcome_is_unknown(tmp_path) -> None:
    """A campaign resume must not launder what the run layer refused to launder.

    The probe stopped answering, so the runtime cancelled its wait and recorded that it does not
    know whether the equipment acted. `run_workflow` will not re-dispatch that task; a campaign
    that resumed over it and carried on unattended would be granting itself an acknowledgement the
    run layer does not offer.
    """

    adapter = ScoreAdapter(delay_seconds=5.0)
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = probe_workflow(
        capability="test.score_unanswering", outputs={"score": "${steps.score.output.score}"}
    )

    stalled = await runner.run(
        workflow,
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_ambiguous",
        max_iterations=1,
    )
    assert stalled.failures
    run_id = stalled.history[0].run_id
    assert run_id is not None
    assert repositories.get_run(run_id).state is RunState.INTERVENTION_REQUIRED  # pyright: ignore[reportOptionalMemberAccess]

    with pytest.raises(WorkflowExecutionError) as refused:
        await runner.run(
            workflow,
            ListOptimizer(candidates(1.0, 2.0)),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_ambiguous",
            max_iterations=2,
            resume=True,
        )

    message = str(refused.value)
    assert "campaign_ambiguous" in message
    assert run_id in message
    assert RunState.INTERVENTION_REQUIRED.value in message
    assert len(adapter.calls) == 1, "the refusal must happen before anything is dispatched"
    assert not campaign_events(repositories, "campaign_ambiguous", "CampaignResumed")


@pytest.mark.asyncio
async def test_a_stateless_optimizer_resumes_by_replaying_what_happened(tmp_path) -> None:
    """A grid has no model to restore, and resume does not require one."""

    from opensdl_adapter_grid_optimizer import GridOptimizer

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    grid = {"parameters": {"x": [1.0, 2.0, 3.0]}}

    first = await runner.run(
        workflow,
        GridOptimizer(grid),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_grid",
        max_iterations=1,
    )
    assert first.stop_reason is CampaignStopReason.MAX_ITERATIONS

    resumed = GridOptimizer(grid)
    result = await runner.run(
        workflow,
        resumed,
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_grid",
        max_iterations=3,
        resume=True,
    )

    assert [call["x"] for call in adapter.calls] == [1.0, 2.0, 3.0]
    assert [item.iteration for item in result.history] == [0, 1, 2]
    assert result.optimizer_state is None
    # `configure` still ran: a resumed campaign checks the grid against the declared space exactly
    # as a fresh one does, and an optimizer that cannot restore state is not thereby unconfigured.
    assert resumed.problem is not None
    started = campaign_events(repositories, "campaign_grid", "CampaignResumed")[0]
    assert started.payload["optimizerStateRestored"] is False
    assert "recorded no optimizer state" in started.payload["optimizerStateDetail"]


@pytest.mark.asyncio
async def test_a_resumable_optimizer_is_given_back_the_state_it_recorded(tmp_path) -> None:
    """What replay cannot recover: a fitted model, a trust region, an RNG stream."""

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0)

    first = SurrogateOptimizer(plan)
    completed = await runner.run(
        workflow,
        first,
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_surrogate",
        max_iterations=2,
    )
    assert completed.optimizer_state == {"fits": 2, "version": "1"}

    second = SurrogateOptimizer(plan)
    result = await runner.run(
        workflow,
        second,
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_surrogate",
        max_iterations=3,
        resume=True,
    )

    assert second.loaded == {"fits": 2, "version": "1"}
    assert second.configured is not None
    # The two recorded iterations were restored as state, so they are not also replayed through
    # `observe`: an optimizer that counted both would have fitted every observation twice.
    assert [item.candidate["x"] for item in second.observed] == [3.0]
    assert second.fits == 3
    assert result.optimizer_state == {"fits": 3, "version": "1"}
    resumed = campaign_events(repositories, "campaign_surrogate", "CampaignResumed")[0]
    assert resumed.payload["optimizerStateRestored"] is True


@pytest.mark.asyncio
async def test_state_the_optimizer_cannot_load_refuses_the_resume(tmp_path) -> None:
    """A campaign that quietly carried on with an unfitted model would be a different search.

    It would run under the same identifier, against the same record, and nothing in the log would
    say the model behind the second half was not the model behind the first.
    """

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0)

    await runner.run(
        workflow,
        SurrogateOptimizer(plan, version="1"),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_stale",
        max_iterations=2,
    )

    with pytest.raises(ValueError) as refused:
        await runner.run(
            workflow,
            SurrogateOptimizer(plan, version="2"),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_stale",
            max_iterations=3,
            resume=True,
        )

    message = str(refused.value)
    assert "campaign_stale" in message
    assert "state was fitted by version 1" in message
    assert len(adapter.calls) == 2, "nothing may be dispatched under a state that did not load"
    assert not campaign_events(repositories, "campaign_stale", "CampaignResumed")


@pytest.mark.asyncio
async def test_state_recorded_by_a_different_optimizer_is_refused(tmp_path) -> None:
    """`state()` is unvalidated caller data on the way back in, so its author is checked."""

    class OtherSurrogate(SurrogateOptimizer):
        pass

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0)

    await runner.run(
        workflow,
        SurrogateOptimizer(plan),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_swapped",
        max_iterations=2,
    )

    with pytest.raises(ValueError) as refused:
        await runner.run(
            workflow,
            OtherSurrogate(plan),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_swapped",
            max_iterations=3,
            resume=True,
        )

    message = str(refused.value)
    assert "SurrogateOptimizer" in message and "OtherSurrogate" in message
    assert not campaign_events(repositories, "campaign_swapped", "CampaignResumed")


@pytest.mark.asyncio
async def test_a_resumed_campaign_that_has_spent_its_budget_stops_without_dispatching(
    tmp_path,
) -> None:
    """`max_iterations` is the budget for the campaign identifier, not for the invocation."""

    adapter = ScoreAdapter()
    runner, _ = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()

    await runner.run(
        workflow,
        ListOptimizer(candidates(1.0, 2.0)),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_spent",
        max_iterations=2,
    )

    result = await runner.run(
        workflow,
        ListOptimizer(candidates(1.0, 2.0)),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_spent",
        max_iterations=2,
        resume=True,
    )

    assert len(adapter.calls) == 2
    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
    assert [item.iteration for item in result.history] == [0, 1]


@pytest.mark.asyncio
async def test_a_resumed_campaign_carries_its_failure_streak_across_the_restart(tmp_path) -> None:
    """A restart that reset the streak would keep an unattended loop failing past its own limit."""

    adapter = ScoreAdapter(fail_on={1.0, 2.0, 3.0})
    runner, _ = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0, 4.0)

    with pytest.raises(RuntimeError, match="went away"):
        await runner.run(
            workflow,
            DyingOptimizer(plan, die_after=2),
            environment="simulation",
            operator_id="operator/alice",
            campaign_id="campaign_streak",
            max_iterations=4,
            max_consecutive_failures=3,
        )

    result = await runner.run(
        workflow,
        ListOptimizer(plan),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_streak",
        max_iterations=4,
        max_consecutive_failures=3,
        resume=True,
    )

    assert result.stop_reason is CampaignStopReason.FAILURE_LIMIT
    assert [item.candidate["x"] for item in result.history] == [1.0, 2.0, 3.0]
    assert len(result.failures) == 3


@pytest.mark.asyncio
async def test_a_resume_re_reads_the_stopping_rules_against_what_already_happened(
    tmp_path,
) -> None:
    """A campaign that already reached its target does not do more physical work on a restart.

    The stopping rules are declared for the campaign, and the replayed history is the campaign's
    history, so a resume evaluates them against it exactly as the live loop would have. Only the
    wall-clock budget is exempt, because the time a dead campaign spent is not time it worked.
    """

    adapter = ScoreAdapter()
    runner, _ = build_campaign(tmp_path, adapter)
    workflow = scoring_workflow()
    plan = candidates(1.0, 2.0, 3.0)

    first = await runner.run(
        workflow,
        ListOptimizer(plan),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_reached",
        max_iterations=3,
        target_score=1.5,
    )
    assert first.stop_reason is CampaignStopReason.TARGET_REACHED
    assert [call["x"] for call in adapter.calls] == [1.0]

    result = await runner.run(
        workflow,
        ListOptimizer(plan),
        environment="simulation",
        operator_id="operator/alice",
        campaign_id="campaign_reached",
        max_iterations=3,
        target_score=1.5,
        resume=True,
    )

    assert result.stop_reason is CampaignStopReason.TARGET_REACHED
    assert "1.0 against a target of 1.5" in result.stop_detail
    assert [call["x"] for call in adapter.calls] == [1.0]
    assert [item.iteration for item in result.history] == [0]


@pytest.mark.asyncio
async def test_the_recorded_best_is_the_observation_s_own_serialisation(tmp_path) -> None:
    """`CampaignCompleted.payload["best"]` was hand-rolled and matched no published schema.

    It is now `CampaignObservation.model_dump(mode="json", by_alias=True)`, so the durable record
    and `campaign-observation.schema.json` describe one document, and a reader can validate the
    event payload back into the model an optimizer was handed.
    """

    runner, repositories = build_campaign(tmp_path, ScoreAdapter())

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(2.0, 1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=2,
    )

    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    recorded = completed.payload["best"]
    assert result.best is not None
    assert recorded == result.best.model_dump(mode="json", by_alias=True)
    assert CampaignObservation.model_validate(recorded) == result.best
    # The keys the hand-rolled form wrote, minus the flag it derived and plus what it dropped.
    assert {
        "iteration",
        "candidate",
        "score",
        "runId",
        "outputs",
        "status",
        "error",
        "objectives",
    } <= set(recorded)
    assert recorded["constraintViolations"] == []
    # What proposed the winning candidate, which the hand-rolled form dropped entirely.
    assert recorded["suggestion"]["parameters"] == recorded["candidate"]
    assert recorded["batch"] == result.best.batch
    assert "feasible" not in recorded


@pytest.mark.asyncio
async def test_a_campaign_that_found_nothing_records_no_best(tmp_path) -> None:
    runner, repositories = build_campaign(tmp_path, ScoreAdapter(fail_on={1.0}))

    result = await runner.run(
        scoring_workflow(),
        ListOptimizer(candidates(1.0)),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=1,
    )

    completed = next(
        event
        for event in repositories.list_events(campaign_id=result.campaign_id, limit=None)
        if event.type == "CampaignCompleted"
    )
    assert result.best is None
    assert completed.payload["best"] is None


@pytest.mark.asyncio
async def test_losing_a_race_for_an_instrument_does_not_stop_the_campaign(tmp_path) -> None:
    """A laboratory that completed a candidate is working, whatever else contended for the bench.

    Every non-succeeding observation used to count toward `max_consecutive_failures`, so a
    laboratory asked to run more at once than it owns stopped on its first batch and reported the
    failure as systematic. Four candidates against one exclusive instrument reached the default
    limit of three immediately, having measured one candidate out of eight, and named a cause an
    operator would go looking for in the instrument or the chemistry.
    """

    adapter = ScoreAdapter()
    runner, repositories = build_campaign(tmp_path, adapter)
    repositories.upsert_resource(Resource(id="probe-bench", name="Probe bench", type="simulator"))

    result = await runner.run(
        probe_workflow(
            capability="test.score_exclusive", outputs={"score": "${steps.score.output.score}"}
        ),
        ScriptedOptimizer(
            [
                [{"x": 1.0}, {"x": 2.0}, {"x": 3.0}, {"x": 4.0}],
                [{"x": 5.0}, {"x": 6.0}, {"x": 7.0}, {"x": 8.0}],
            ]
        ),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=8,
        batch_size=4,
        max_parallel_runs=4,
    )

    assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
    # Both batches got a candidate through, so both are laboratories that worked.
    assert len(result.successes) == 2
    assert all("resources busy" in (item.error or "") for item in result.failures)


@pytest.mark.asyncio
async def test_a_batch_that_completes_nothing_still_stops_the_campaign(tmp_path) -> None:
    """The stop rule has to keep working, or the fix above has traded one failure for another.

    Nothing succeeding is what "systematic" means. Every attempt in a batch that got nothing
    through still counts, so a genuinely failing laboratory stops exactly as promptly as it did
    before — three failed attempts, whether they arrive one batch at a time or all at once.
    """

    adapter = ScoreAdapter(fail_on={1.0, 2.0, 3.0, 4.0})
    runner, _ = build_campaign(tmp_path, adapter)

    result = await runner.run(
        probe_workflow(),
        ScriptedOptimizer([[{"x": 1.0}, {"x": 2.0}, {"x": 3.0}, {"x": 4.0}]]),
        environment="simulation",
        operator_id="operator/alice",
        max_iterations=8,
        batch_size=4,
        max_parallel_runs=4,
    )

    assert result.stop_reason is CampaignStopReason.FAILURE_LIMIT
    assert "systematic rather than routine" in result.stop_detail
    assert result.successes == []


def test_the_trailing_failure_count_a_resume_rebuilds_is_read_per_batch(tmp_path) -> None:
    """A resume must reach the same count the loop itself would have, or it stops early.

    Counting observations rather than batches here would let a restart inherit a limit the running
    campaign had already reset, and stop a campaign the loop was willing to continue.
    """

    def observation(iteration: int, batch: int, *, succeeded: bool) -> CampaignObservation:
        return CampaignObservation(
            iteration=iteration,
            candidate={"x": float(iteration)},
            batch=batch,
            score=1.0 if succeeded else None,
            status=(
                CampaignObservationStatus.SUCCEEDED
                if succeeded
                else CampaignObservationStatus.FAILED
            ),
            error=None if succeeded else "resources busy: ['bench']",
        )

    # One batch, one winner and three losers: the laboratory worked, so nothing trails.
    served = [
        observation(0, 0, succeeded=True),
        observation(1, 0, succeeded=False),
        observation(2, 0, succeeded=False),
        observation(3, 0, succeeded=False),
    ]
    assert _trailing_failures(served) == 0

    # A batch that got nothing through counts every attempt in it.
    dead = served + [observation(index, 1, succeeded=False) for index in range(4, 8)]
    assert _trailing_failures(dead) == 4

    # And an earlier working batch still ends the count.
    assert _trailing_failures(dead + [observation(8, 2, succeeded=True)]) == 0
