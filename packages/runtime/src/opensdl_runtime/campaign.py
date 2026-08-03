from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from opensdl_core import Decision, EventRecord, WorkflowDefinition, new_id
from opensdl_storage import RepositoryStore

from .engine import ReferenceRuntime


@dataclass(frozen=True)
class CampaignObservation:
    iteration: int
    candidate: dict[str, Any]
    score: float
    run_id: str
    outputs: dict[str, Any]


class Optimizer(Protocol):
    def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None: ...
    def observe(self, observation: CampaignObservation) -> None: ...


@dataclass
class CampaignResult:
    campaign_id: str
    history: list[CampaignObservation] = field(default_factory=list)
    best: CampaignObservation | None = None


class CampaignRunner:
    def __init__(self, runtime: ReferenceRuntime, repositories: RepositoryStore) -> None:
        self.runtime = runtime
        self.repositories = repositories

    async def run(
        self,
        workflow: WorkflowDefinition,
        optimizer: Optimizer,
        *,
        base_inputs: dict[str, Any] | None = None,
        score_output: str = "score",
        max_iterations: int = 10,
        minimize: bool = True,
        operator_id: str = "software/campaign",
        environment: str = "simulation",
        campaign_id: str | None = None,
    ) -> CampaignResult:
        campaign_id = campaign_id or new_id("campaign")
        history: list[CampaignObservation] = []
        self.repositories.append_event(
            EventRecord(
                type="CampaignStarted",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={"workflowId": workflow.id, "maxIterations": max_iterations},
            )
        )
        for iteration in range(max_iterations):
            candidate = optimizer.suggest(history)
            if candidate is None:
                break
            inputs = dict(base_inputs or {})
            inputs.update(candidate)
            inputs.setdefault("sample_id", f"{campaign_id}-{iteration:03d}")
            run = await self.runtime.run_workflow(
                workflow, inputs, operator_id=operator_id, environment=environment
            )
            score = float(_get_path(run.outputs, score_output))
            observation = CampaignObservation(
                iteration=iteration,
                candidate=candidate,
                score=score,
                run_id=run.id,
                outputs=run.outputs,
            )
            history.append(observation)
            optimizer.observe(observation)
            decision = Decision(
                campaign_id=campaign_id,
                iteration=iteration,
                selected=candidate,
                rationale=f"optimizer selected candidate for iteration {iteration}",
                evidence_run_ids=[run.id],
            )
            self.repositories.append_event(
                EventRecord(
                    type="DecisionRecorded",
                    actor_id=operator_id,
                    run_id=run.id,
                    campaign_id=campaign_id,
                    payload={"decision": decision.model_dump(mode="json"), "score": score},
                )
            )
        best = None
        if history:
            best = (
                min(history, key=lambda item: item.score)
                if minimize
                else max(history, key=lambda item: item.score)
            )
        self.repositories.append_event(
            EventRecord(
                type="CampaignCompleted",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={"iterations": len(history), "best": _observation_json(best)},
            )
        )
        return CampaignResult(campaign_id=campaign_id, history=history, best=best)


def _get_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"campaign score output not found: {path}")
        current = current[segment]
    return current


def _observation_json(value: CampaignObservation | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "iteration": value.iteration,
        "candidate": value.candidate,
        "score": value.score,
        "runId": value.run_id,
        "outputs": value.outputs,
    }
