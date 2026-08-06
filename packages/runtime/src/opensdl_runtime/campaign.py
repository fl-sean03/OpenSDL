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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field, computed_field

from opensdl_core import Decision, EventRecord, OpenSDLModel, WorkflowDefinition, new_id
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


class CampaignState(StrEnum):
    """What the event stream says about a campaign, and nothing more.

    `RUNNING` means a start was recorded and a completion was not. A live campaign and a campaign
    whose controller died mid-loop produce exactly that, and the events cannot distinguish them:
    there is no heartbeat and no campaign record to reconcile. `recover_incomplete_runs` reconciles
    the runs a dead controller left behind; it has no campaign analogue.
    """

    RUNNING = "running"
    COMPLETED = "completed"


class CampaignIterationState(StrEnum):
    """Whether an iteration is still in flight, produced a score, or was recorded as failed."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CampaignIterationRecord(OpenSDLModel):
    """One iteration as the event stream recorded it."""

    iteration: int = Field(ge=0)
    candidate: dict[str, Any] = Field(default_factory=dict)
    state: CampaignIterationState = CampaignIterationState.RUNNING
    #: The run this iteration launched. `None` only when the submission was rejected before the
    #: runtime created a run, so there is nothing for the identifier to point at.
    run_id: str | None = None
    score: float | None = None
    error: str | None = None


class CampaignRecord(OpenSDLModel):
    """A campaign reconstructed from its events.

    Every field comes from an event the campaign emitted. There is no campaigns table, and this is
    not a substitute for one: it is a reading of the record rather than a second place that could
    disagree with it. What it cannot report is anything the events do not carry — whether the
    process is alive, what the optimizer's internal state was, or what a campaign that never
    emitted `CampaignStarted` intended.
    """

    campaign_id: str
    state: CampaignState
    operator_id: str
    environment: str
    workflow_id: str
    workflow_version: str = "0.1.0"
    max_iterations: int = 0
    score_output: str = "score"
    minimize: bool = True
    target_score: float | None = None
    max_consecutive_failures: int = 0
    max_duration_seconds: float | None = None
    iteration_id_input: str | None = None
    base_inputs: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stop_reason: CampaignStopReason | None = None
    stop_detail: str = ""
    iterations: list[CampaignIterationRecord] = Field(default_factory=list)
    #: The best scoring iteration. While a campaign is running this is the best so far, which is
    #: what an operator watching one wants; once it completes it is the one the campaign recorded.
    best: CampaignIterationRecord | None = None

    @computed_field
    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.iterations if item.state is CampaignIterationState.SUCCEEDED)

    @computed_field
    @property
    def failed(self) -> int:
        return sum(1 for item in self.iterations if item.state is CampaignIterationState.FAILED)

    @computed_field
    @property
    def running(self) -> int:
        return sum(1 for item in self.iterations if item.state is CampaignIterationState.RUNNING)


def project_campaign(campaign_id: str, events: Sequence[EventRecord]) -> CampaignRecord:
    """Reconstruct one campaign from the events it emitted, in the order they were recorded."""

    started = next((event for event in events if event.type == "CampaignStarted"), None)
    if started is None:
        raise KeyError(campaign_id)
    header = started.payload
    iterations: dict[int, CampaignIterationRecord] = {}
    completed: EventRecord | None = None
    for event in events:
        if event.type == "CampaignIterationStarted":
            index = int(event.payload["iteration"])
            iterations[index] = CampaignIterationRecord(
                iteration=index,
                candidate=dict(event.payload.get("candidate") or {}),
                run_id=event.payload.get("runId"),
                state=CampaignIterationState.RUNNING,
            )
        elif event.type == "DecisionRecorded":
            decision = event.payload.get("decision") or {}
            index = int(decision.get("iteration", -1))
            current = iterations.get(index)
            if current is not None:
                iterations[index] = current.model_copy(
                    update={
                        "state": CampaignIterationState.SUCCEEDED,
                        "score": event.payload.get("score"),
                    }
                )
        elif event.type == "CampaignIterationFailed":
            index = int(event.payload["iteration"])
            current = iterations.get(index)
            if current is not None:
                iterations[index] = current.model_copy(
                    update={
                        "state": CampaignIterationState.FAILED,
                        "error": event.payload.get("error"),
                        "run_id": event.payload.get("runId") or current.run_id,
                    }
                )
        elif event.type == "CampaignCompleted":
            completed = event

    ordered = [iterations[index] for index in sorted(iterations)]
    minimize = bool(header.get("minimize", True))
    return CampaignRecord(
        campaign_id=campaign_id,
        state=CampaignState.COMPLETED if completed is not None else CampaignState.RUNNING,
        operator_id=str(header.get("operatorId") or started.actor_id),
        environment=str(header.get("environment") or ""),
        workflow_id=str(header.get("workflowId") or ""),
        workflow_version=str(header.get("workflowVersion") or "0.1.0"),
        max_iterations=int(header.get("maxIterations") or 0),
        score_output=str(header.get("scoreOutput") or "score"),
        minimize=minimize,
        target_score=header.get("targetScore"),
        max_consecutive_failures=int(header.get("maxConsecutiveFailures") or 0),
        max_duration_seconds=header.get("maxDurationSeconds"),
        iteration_id_input=header.get("iterationIdInput"),
        base_inputs=dict(header.get("baseInputs") or {}),
        started_at=started.occurred_at,
        completed_at=completed.occurred_at if completed is not None else None,
        stop_reason=(
            CampaignStopReason(completed.payload["stopReason"]) if completed is not None else None
        ),
        stop_detail=str(completed.payload.get("stopDetail", "")) if completed is not None else "",
        iterations=ordered,
        best=_best_iteration(ordered, minimize),
    )


def _best_iteration(
    iterations: Sequence[CampaignIterationRecord],
    minimize: bool,
) -> CampaignIterationRecord | None:
    scored = [item for item in iterations if item.score is not None]
    if not scored:
        return None
    chooser = min if minimize else max
    return chooser(scored, key=lambda item: item.score if item.score is not None else 0.0)


#: How many of the newest events `CampaignReader.active` reads to find campaigns still in flight.
#: A running campaign is emitting events, so the newest events are where it is; a campaign whose
#: last event is older than this window is not reported active. The window exists because
#: `list_events` can filter by campaign but not by event type, so finding campaigns at all is a
#: scan rather than a query.
ACTIVE_CAMPAIGN_SCAN_LIMIT = 500


class CampaignReader:
    """Reads campaigns back out of the event store.

    A campaign has no table and no row: reading one is a projection of its events. Reading a single
    campaign is indexed and cheap. Listing every campaign is a scan of the whole event log, because
    the store can filter events by campaign identifier but not by type, so there is no query that
    returns "the campaigns". `active` bounds that cost by looking only at the newest events.
    """

    def __init__(self, repositories: RepositoryStore) -> None:
        self.repositories = repositories

    def get(self, campaign_id: str) -> CampaignRecord:
        """Project one campaign, or raise `KeyError` if nothing was ever recorded under its id."""
        return project_campaign(
            campaign_id,
            self.repositories.list_events(campaign_id=campaign_id, limit=None),
        )

    #: The two events that bound a campaign. Listing asks for these rather than reading every
    #: event ever recorded, because run and task events now carry a campaign id too and a
    #: campaign of a hundred runs contributes thousands of events that say nothing about
    #: whether it started or finished.
    LIFECYCLE_EVENT_TYPES = ("CampaignStarted", "CampaignCompleted")

    def list(self) -> list[CampaignRecord]:
        """Every campaign the store has a lifecycle event for, newest first."""
        grouped: dict[str, list[EventRecord]] = {}
        for event in self.repositories.list_events(types=self.LIFECYCLE_EVENT_TYPES, limit=None):
            if event.campaign_id is not None:
                grouped.setdefault(event.campaign_id, []).append(event)
        return _projected(
            (campaign_id, grouped[campaign_id]) for campaign_id in reversed(list(grouped))
        )

    def active(self, *, scan_limit: int = ACTIVE_CAMPAIGN_SCAN_LIMIT) -> list[CampaignRecord]:
        """Campaigns whose newest events include a start and no completion, newest first."""
        recent = self.repositories.list_events(limit=scan_limit, newest_first=True)
        candidates = dict.fromkeys(
            event.campaign_id for event in recent if event.campaign_id is not None
        )
        records = _projected(
            (campaign_id, self.repositories.list_events(campaign_id=campaign_id, limit=None))
            for campaign_id in candidates
        )
        return [record for record in records if record.state is CampaignState.RUNNING]


def _projected(
    grouped: Iterable[tuple[str, Sequence[EventRecord]]],
) -> list[CampaignRecord]:
    """Project each campaign, skipping any with no `CampaignStarted` to project from.

    An identifier can reach here from a run or task event alone — a campaign whose very first
    write failed, say — and a campaign nothing declared is not a campaign to report.
    """
    records: list[CampaignRecord] = []
    for campaign_id, events in grouped:
        try:
            records.append(project_campaign(campaign_id, events))
        except KeyError:
            continue
    return records


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
