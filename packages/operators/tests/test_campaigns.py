"""Starting a campaign from outside bespoke Python.

`CampaignLauncher` is the write half of the campaign surface. It is tested here rather than
through the gateway on purpose: the gateway is the boundary a read-only laboratory serves, and a
campaign start does not belong on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opensdl_capabilities import CapabilityAdapter, CapabilityRegistry, PLUGIN_ALLOWLIST_ENV
from opensdl_capabilities.plugins import PluginNotAllowedError
from opensdl_core import (
    CapabilityDefinition,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    WorkflowDefinition,
    WorkflowStep,
)
from opensdl_operators import CampaignLauncher
from opensdl_policy import PolicyEngine
from opensdl_runtime import CampaignState, Parameter, ReferenceRuntime, SearchSpace
from opensdl_storage import Database, LocalArtifactStore, Repositories


class ScoreAdapter(CapabilityAdapter):
    name = "launcher-probe"

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.score",
                name="Score",
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
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            request_id=request.request_id,
            output={"score": float(request.inputs["x"])},
        )


def scoring_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="launcher-probe",
        name="Launcher probe",
        input_schema={
            "type": "object",
            "required": ["x"],
            "properties": {"x": {}},
            "additionalProperties": False,
        },
        steps=[WorkflowStep(id="score", capability="test.score", inputs={"x": "${inputs.x}"})],
        outputs={"score": "${steps.score.output.score}"},
    )


def build_launcher(tmp_path: Path) -> tuple[CampaignLauncher, Repositories]:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    registry.register(ScoreAdapter())
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path, repositories),
    )
    return CampaignLauncher(runtime, repositories), repositories


def candidates() -> dict[str, Any]:
    return {"candidates": [{"x": 3.0}, {"x": 1.0}, {"x": 2.0}]}


@pytest.mark.asyncio
async def test_the_launcher_runs_a_campaign_and_returns_its_record(tmp_path: Path) -> None:
    launcher, repositories = build_launcher(tmp_path)

    record = await launcher.run(
        scoring_workflow(),
        environment="production",
        operator_id="operator/alice",
        optimizer="grid",
        optimizer_config=candidates(),
        max_iterations=3,
    )

    assert record.state is CampaignState.COMPLETED
    assert record.environment == "production"
    assert record.operator_id == "operator/alice"
    assert record.succeeded == 3
    assert record.best is not None and record.best.candidate == {"x": 1.0}
    assert {run.environment for run in repositories.list_runs()} == {"production"}


@pytest.mark.asyncio
async def test_the_launcher_carries_the_declared_problem_and_the_batch_through(
    tmp_path: Path,
) -> None:
    """Starting a campaign from outside Python must not be where the new contract stops."""

    launcher, repositories = build_launcher(tmp_path)

    record = await launcher.run(
        scoring_workflow(),
        environment="simulation",
        operator_id="operator/alice",
        optimizer="grid",
        optimizer_config=candidates(),
        max_iterations=3,
        batch_size=3,
        search_space=SearchSpace(parameters=[Parameter.continuous("x", 0.0, 5.0)]),
    )

    assert record.batch_size == 3
    assert record.problem is not None
    assert record.problem.space.parameters[0].upper == 5.0
    assert [item.batch for item in record.iterations] == [0, 0, 0]
    assert record.succeeded == 3
    # One batch of three, so the optimizer was asked once.
    proposals = [
        event
        for event in repositories.list_events(campaign_id=record.campaign_id, limit=None)
        if event.type == "DecisionRecorded"
    ]
    assert [event.payload["batchSize"] for event in proposals] == [3, 3, 3]


@pytest.mark.asyncio
async def test_a_grid_outside_the_declared_space_stops_before_any_run(tmp_path: Path) -> None:
    """`configure` runs before the loop, so a misconfigured sweep never reaches an instrument."""

    launcher, repositories = build_launcher(tmp_path)

    with pytest.raises(ValueError, match="leaves the search space"):
        await launcher.run(
            scoring_workflow(),
            environment="simulation",
            operator_id="operator/alice",
            optimizer="grid",
            optimizer_config=candidates(),
            search_space=SearchSpace(parameters=[Parameter.continuous("x", 0.0, 2.0)]),
        )

    assert repositories.list_runs() == []


@pytest.mark.asyncio
async def test_an_unknown_optimizer_is_reported_before_anything_is_recorded(
    tmp_path: Path,
) -> None:
    launcher, repositories = build_launcher(tmp_path)

    with pytest.raises(LookupError, match="grid"):
        await launcher.run(
            scoring_workflow(),
            environment="simulation",
            operator_id="operator/alice",
            optimizer="bayesian",
        )

    assert repositories.list_events(limit=None) == []


@pytest.mark.asyncio
async def test_the_deployment_allowlist_constrains_the_optimizer_it_will_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An optimizer is code this process imports and then lets choose what the laboratory does.

    It is authorized by the same environment allowlist as an adapter, and for the same reason: a
    name on a command line is not an authorization.
    """
    launcher, _ = build_launcher(tmp_path)
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, "simulated-lab")

    with pytest.raises(PluginNotAllowedError):
        await launcher.run(
            scoring_workflow(),
            environment="simulation",
            operator_id="operator/alice",
            optimizer="grid",
            optimizer_config=candidates(),
        )
