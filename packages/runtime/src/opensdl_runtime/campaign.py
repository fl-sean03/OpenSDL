"""Closed-loop campaign execution.

A campaign is the one path OpenSDL runs unattended, so everything here assumes nobody is watching.
The environment and the operator are stated by the caller rather than defaulted, because a silent
default writes a false provenance record and evaluates policy against an environment the laboratory
never declared. A failed iteration is recorded and fed back to the optimizer rather than thrown,
because a clogged tip or an off-scale reading is routine in a laboratory and is information. Every
campaign records why it stopped, because "budget exhausted" and "target reached" are different
outcomes and the log has to say which one happened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from opensdl_core import Decision, EventRecord, WorkflowDefinition, new_id
from opensdl_storage import RepositoryStore

from .engine import ReferenceRuntime


class CampaignObservationStatus(StrEnum):
    """Whether an iteration produced a usable score."""

    SUCCEEDED = "succeeded"
    #: The workflow failed, or it completed and produced no usable score. Either way the candidate
    #: was attempted: physical work may have happened and the attempt is part of the record.
    FAILED = "failed"


class CampaignStopReason(StrEnum):
    """Why the loop stopped. Recorded on ``CampaignCompleted`` and on :class:`CampaignResult`."""

    #: The iteration budget was spent.
    MAX_ITERATIONS = "max_iterations"
    #: The optimizer proposed no further candidate.
    OPTIMIZER_EXHAUSTED = "optimizer_exhausted"
    #: An observation reached the configured target score.
    TARGET_REACHED = "target_reached"
    #: Failure was systematic rather than routine: the consecutive-failure limit was reached.
    FAILURE_LIMIT = "failure_limit"
    #: The wall-clock budget was spent.
    TIME_BUDGET_EXHAUSTED = "time_budget_exhausted"


@dataclass(frozen=True)
class CampaignObservation:
    """One attempted iteration.

    A failed attempt is an observation, not an absence of one: it carries the candidate that was
    tried and the error it produced, so an optimizer can avoid re-proposing it and an operator can
    see what the campaign did.
    """

    iteration: int
    candidate: dict[str, Any]
    score: float | None = None
    run_id: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    status: CampaignObservationStatus = CampaignObservationStatus.SUCCEEDED
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status is CampaignObservationStatus.SUCCEEDED:
            if self.score is None:
                raise ValueError("a succeeded observation must carry the score it produced")
            if self.error is not None:
                raise ValueError("a succeeded observation cannot carry an error")
            return
        if self.score is not None:
            raise ValueError("a failed observation has no score")
        if not self.error:
            raise ValueError("a failed observation must record why it failed")

    @property
    def succeeded(self) -> bool:
        return self.status is CampaignObservationStatus.SUCCEEDED


class Optimizer(Protocol):
    """Candidate source for a campaign.

    ``history`` holds every attempt in order, failures included. An optimizer that filters history
    down to successes will propose a failing candidate forever.
    """

    def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None: ...

    def observe(self, observation: CampaignObservation) -> None: ...


@dataclass
class CampaignResult:
    campaign_id: str
    stop_reason: CampaignStopReason
    stop_detail: str = ""
    history: list[CampaignObservation] = field(default_factory=list)
    best: CampaignObservation | None = None

    @property
    def successes(self) -> list[CampaignObservation]:
        return [item for item in self.history if item.succeeded]

    @property
    def failures(self) -> list[CampaignObservation]:
        return [item for item in self.history if not item.succeeded]


class CampaignRunner:
    def __init__(self, runtime: ReferenceRuntime, repositories: RepositoryStore) -> None:
        self.runtime = runtime
        self.repositories = repositories

    async def run(
        self,
        workflow: WorkflowDefinition,
        optimizer: Optimizer,
        *,
        environment: str,
        operator_id: str,
        base_inputs: dict[str, Any] | None = None,
        score_output: str = "score",
        max_iterations: int = 10,
        minimize: bool = True,
        target_score: float | None = None,
        max_consecutive_failures: int = 3,
        max_duration_seconds: float | None = None,
        iteration_id_input: str | None = None,
        campaign_id: str | None = None,
    ) -> CampaignResult:
        """Run a closed loop until a stopping rule fires, and record why it stopped.

        ``environment`` and ``operator_id`` are required: policy is evaluated against them and the
        run record preserves them, so the caller must state the environment its manifest declares
        rather than inherit a default that would make the provenance record false.

        The control arguments below ``operator_id`` mirror :class:`opensdl_core.CampaignDefinition`
        field for field, including defaults.
        """

        if not environment.strip():
            raise ValueError(
                "campaign environment must name the environment the laboratory manifest declares; "
                "policy is evaluated against it and every run records it"
            )
        if not operator_id.strip():
            raise ValueError(
                "campaign operator_id must name the operator accountable for the campaign; "
                "policy is evaluated against it and every run records it"
            )
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1")
        if max_duration_seconds is not None and max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")

        campaign_id = campaign_id or new_id("campaign")
        history: list[CampaignObservation] = []
        consecutive_failures = 0
        started_at = time.monotonic()
        stop_reason = CampaignStopReason.MAX_ITERATIONS
        stop_detail = f"ran the configured budget of {max_iterations} iterations"
        self.repositories.append_event(
            EventRecord(
                type="CampaignStarted",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={
                    "workflowId": workflow.id,
                    "workflowVersion": workflow.version,
                    "environment": environment,
                    "operatorId": operator_id,
                    "maxIterations": max_iterations,
                    "scoreOutput": score_output,
                    "minimize": minimize,
                    "targetScore": target_score,
                    "maxConsecutiveFailures": max_consecutive_failures,
                    "maxDurationSeconds": max_duration_seconds,
                    "iterationIdInput": iteration_id_input,
                    "baseInputs": dict(base_inputs or {}),
                },
            )
        )
        for iteration in range(max_iterations):
            elapsed = time.monotonic() - started_at
            if max_duration_seconds is not None and elapsed >= max_duration_seconds:
                stop_reason = CampaignStopReason.TIME_BUDGET_EXHAUSTED
                stop_detail = (
                    f"{elapsed:.3f}s of the {max_duration_seconds:g}s budget were spent before "
                    f"iteration {iteration}"
                )
                break
            candidate = optimizer.suggest(history)
            if candidate is None:
                stop_reason = CampaignStopReason.OPTIMIZER_EXHAUSTED
                stop_detail = f"the optimizer proposed no candidate for iteration {iteration}"
                break
            observation = await self._run_iteration(
                workflow=workflow,
                campaign_id=campaign_id,
                iteration=iteration,
                candidate=candidate,
                base_inputs=base_inputs,
                score_output=score_output,
                operator_id=operator_id,
                environment=environment,
                iteration_id_input=iteration_id_input,
            )
            history.append(observation)
            optimizer.observe(observation)
            if not observation.succeeded:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    stop_reason = CampaignStopReason.FAILURE_LIMIT
                    stop_detail = (
                        f"{consecutive_failures} consecutive iterations failed, so the failure is "
                        f"systematic rather than routine; last error: {observation.error}"
                    )
                    break
                continue
            consecutive_failures = 0
            decision = Decision(
                campaign_id=campaign_id,
                iteration=iteration,
                selected=candidate,
                rationale=f"optimizer selected candidate for iteration {iteration}",
                evidence_run_ids=[observation.run_id] if observation.run_id else [],
            )
            self.repositories.append_event(
                EventRecord(
                    type="DecisionRecorded",
                    actor_id=operator_id,
                    run_id=observation.run_id,
                    campaign_id=campaign_id,
                    payload={
                        "decision": decision.model_dump(mode="json"),
                        "score": observation.score,
                    },
                )
            )
            if target_score is not None and _reaches(observation.score, target_score, minimize):
                stop_reason = CampaignStopReason.TARGET_REACHED
                stop_detail = (
                    f"iteration {iteration} scored {observation.score} against a target of "
                    f"{target_score} ({'minimizing' if minimize else 'maximizing'})"
                )
                break

        successes = [item for item in history if item.succeeded]
        best = None
        if successes:
            best = min(successes, key=_score_of) if minimize else max(successes, key=_score_of)
        self.repositories.append_event(
            EventRecord(
                type="CampaignCompleted",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={
                    "iterations": len(history),
                    "succeeded": len(successes),
                    "failed": len(history) - len(successes),
                    "stopReason": stop_reason.value,
                    "stopDetail": stop_detail,
                    "best": _observation_json(best),
                },
            )
        )
        return CampaignResult(
            campaign_id=campaign_id,
            stop_reason=stop_reason,
            stop_detail=stop_detail,
            history=history,
            best=best,
        )

    async def _run_iteration(
        self,
        *,
        workflow: WorkflowDefinition,
        campaign_id: str,
        iteration: int,
        candidate: dict[str, Any],
        base_inputs: dict[str, Any] | None,
        score_output: str,
        operator_id: str,
        environment: str,
        iteration_id_input: str | None,
    ) -> CampaignObservation:
        """Execute one candidate and return what happened, successfully or not."""

        inputs = dict(base_inputs or {})
        inputs.update(candidate)
        # The run identifier is minted here rather than by the runtime so the campaign can name the
        # run in its own event stream before dispatch, and can still name it when the submission
        # fails — which is the one case the run's own events cannot cover, because there are none.
        # Every run and task event the iteration goes on to emit also carries the campaign id, so a
        # single query by campaign returns the execution history and not only the decisions.
        run_id = new_id("run")
        if iteration_id_input is not None:
            inputs.setdefault(iteration_id_input, f"{campaign_id}-{iteration:03d}")
        self.repositories.append_event(
            EventRecord(
                type="CampaignIterationStarted",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={
                    "iteration": iteration,
                    "candidate": candidate,
                    "runId": run_id,
                    "environment": environment,
                },
            )
        )
        try:
            run = await self.runtime.run_workflow(
                workflow,
                inputs,
                operator_id=operator_id,
                environment=environment,
                run_id=run_id,
                campaign_id=campaign_id,
            )
            score = float(_get_path(run.outputs, score_output))
        except Exception as exc:
            error = _describe(exc)
            submitted = self.repositories.get_run(run_id)
            self.repositories.append_event(
                EventRecord(
                    type="CampaignIterationFailed",
                    actor_id=operator_id,
                    # Only claim the run once it exists: a submission rejected before the runtime
                    # created a run leaves nothing for this identifier to point at.
                    run_id=run_id if submitted is not None else None,
                    campaign_id=campaign_id,
                    payload={
                        "iteration": iteration,
                        "candidate": candidate,
                        "runId": run_id,
                        "runState": submitted.state.value if submitted is not None else None,
                        "error": error,
                        "errorType": type(exc).__name__,
                    },
                )
            )
            return CampaignObservation(
                iteration=iteration,
                candidate=candidate,
                run_id=run_id if submitted is not None else None,
                status=CampaignObservationStatus.FAILED,
                error=error,
            )
        return CampaignObservation(
            iteration=iteration,
            candidate=candidate,
            score=score,
            run_id=run.id,
            outputs=run.outputs,
        )


def _get_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"campaign score output not found: {path}")
        current = current[segment]
    return current


def _describe(exc: Exception) -> str:
    """Render an exception the way the run record does, without ``KeyError``'s extra quoting."""

    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc) or type(exc).__name__


def _score_of(observation: CampaignObservation) -> float:
    if observation.score is None:  # pragma: no cover - guarded by CampaignObservation
        raise ValueError("a succeeded observation always carries a score")
    return observation.score


def _reaches(score: float | None, target: float, minimize: bool) -> bool:
    if score is None:  # pragma: no cover - only successes are compared to the target
        return False
    return score <= target if minimize else score >= target


def _observation_json(value: CampaignObservation | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "iteration": value.iteration,
        "candidate": value.candidate,
        "score": value.score,
        "runId": value.run_id,
        "outputs": value.outputs,
        "status": value.status.value,
        "error": value.error,
    }
