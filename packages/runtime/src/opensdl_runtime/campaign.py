"""Closed-loop campaign execution.

A campaign is the one path OpenSDL runs unattended, so everything here assumes nobody is watching.
The environment and the operator are stated by the caller rather than defaulted, because a silent
default writes a false provenance record and evaluates policy against an environment the laboratory
never declared. A failed iteration is recorded and fed back to the optimizer rather than thrown,
because a clogged tip or an off-scale reading is routine in a laboratory and is information. Every
campaign records why it stopped, because "budget exhausted" and "target reached" are different
outcomes and the log has to say which one happened.

**The contract an optimizer implements is not here.** `Optimizer`, `CampaignObservation`,
`CampaignProblem` and everything they are built from live in `opensdl_core.campaign`, so publishing
a BoTorch or Ax optimizer costs a dependency on `opensdl-core` rather than on the whole execution
stack. Every one of those names is re-exported below, so an import that named this module keeps
working. What is genuinely here is execution: the runner, the result, and the projection of a
campaign from the events it emitted.

A campaign runs for weeks, so it can be interrupted, and `run(resume=True)` continues one from its
own record rather than from a caller's memory of it. What that has to be careful about is stated on
`CampaignRunner.run`; the short version is that a resumed campaign never re-dispatches a candidate
whose run already completed, never continues over a run whose physical outcome is unknown, and
never silently becomes a different search under the same identifier.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, computed_field

from opensdl_core import (
    BatchOptimizer,
    CampaignObservation,
    CampaignObservationStatus,
    CampaignProblem,
    CandidateConstraint,
    ConfigurableOptimizer,
    Decision,
    EventRecord,
    IterationDecision,
    Objective,
    ObjectiveValue,
    OpenSDLModel,
    Optimizer,
    OutcomeConstraint,
    Parameter,
    ParameterKind,
    ResumableOptimizer,
    RunRecord,
    RunState,
    SearchSpace,
    StatefulOptimizer,
    Suggestion,
    WorkflowDefinition,
    WorkflowExecutionError,
    new_id,
)
from opensdl_storage import RepositoryStore

from .engine import ReferenceRuntime

#: Everything this module exports. The first block is the contract, which now lives in
#: `opensdl_core.campaign` so that an optimizer plugin does not have to depend on storage, policy,
#: workflows and SQLAlchemy to implement two methods. It is re-exported by name, rather than left
#: to be an accident of the import above, so an existing `from opensdl_runtime.campaign import ...`
#: keeps resolving and so removing one of these is a decision rather than a tidy-up.
__all__ = [
    "BatchOptimizer",
    "CampaignObservation",
    "CampaignObservationStatus",
    "CampaignProblem",
    "CandidateConstraint",
    "ConfigurableOptimizer",
    "IterationDecision",
    "Objective",
    "ObjectiveValue",
    "Optimizer",
    "OutcomeConstraint",
    "Parameter",
    "ParameterKind",
    "ResumableOptimizer",
    "SearchSpace",
    "StatefulOptimizer",
    "Suggestion",
    "ACTIVE_CAMPAIGN_SCAN_LIMIT",
    "CampaignIterationRecord",
    "CampaignIterationState",
    "CampaignReader",
    "CampaignRecord",
    "CampaignResult",
    "CampaignRunner",
    "CampaignState",
    "CampaignStopReason",
    "project_campaign",
]


#: Run states that establish what physically happened, so a campaign resume may read an outcome off
#: them. Every other state — `intervention_required` above all, but equally a run still recorded as
#: `running` because the controller died holding it — leaves the physical outcome unknown, and a
#: resume refuses rather than continuing over it. This is the same rule `UNRESUMABLE_TASK_STATES`
#: applies one layer down, read at the layer that decides whether to keep going unattended.
_ESTABLISHED_RUN_STATES = frozenset({RunState.COMPLETED, RunState.FAILED})


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


@dataclass
class CampaignResult:
    campaign_id: str
    stop_reason: CampaignStopReason
    stop_detail: str = ""
    history: list[CampaignObservation] = field(default_factory=list)
    best: CampaignObservation | None = None
    #: What the campaign declared it was searching. `None` only on a hand-built result.
    problem: CampaignProblem | None = None
    #: What the optimizer knew when the campaign stopped, if it was able to say.
    optimizer_state: dict[str, Any] | None = None

    @property
    def successes(self) -> list[CampaignObservation]:
        return [item for item in self.history if item.succeeded]

    @property
    def failures(self) -> list[CampaignObservation]:
        """Iterations the laboratory attempted and did not complete usefully."""
        return [item for item in self.history if item.status is CampaignObservationStatus.FAILED]

    @property
    def rejected(self) -> list[CampaignObservation]:
        """Candidates the campaign refused to submit. No physical work was attempted."""
        return [item for item in self.history if item.status is CampaignObservationStatus.REJECTED]

    @property
    def feasible(self) -> list[CampaignObservation]:
        return [item for item in self.successes if item.feasible]

    @property
    def pareto_front(self) -> list[CampaignObservation]:
        """The non-dominated feasible observations, by every declared objective.

        With one objective this is the single best point. It is a reading of the record, not a
        recommendation: the campaign does not choose among a front.
        """
        candidates = self.feasible
        if self.problem is None or len(self.problem.objectives) < 2:
            return [item for item in candidates if item is self.best] if self.best else []
        return [
            item
            for item in candidates
            if not any(
                _dominates(other, item, self.problem.objectives)
                for other in candidates
                if other is not item
            )
        ]


@dataclass(frozen=True)
class _Planned:
    """One candidate the campaign has committed to, before it knows whether it will run."""

    iteration: int
    batch: int
    position: int
    batch_size: int
    suggestion: Suggestion
    #: Minted before dispatch so the campaign can name the run in its own stream, and can still
    #: name it when the submission fails — the one case the run's own events cannot cover.
    run_id: str

    @property
    def candidate(self) -> dict[str, Any]:
        return self.suggestion.parameters


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
        objectives: Sequence[Objective] | None = None,
        search_space: SearchSpace | None = None,
        candidate_constraints: Sequence[CandidateConstraint] = (),
        outcome_constraints: Sequence[OutcomeConstraint] = (),
        batch_size: int = 1,
        max_parallel_runs: int = 1,
        resume: bool = False,
    ) -> CampaignResult:
        """Run a closed loop until a stopping rule fires, and record why it stopped.

        ``environment`` and ``operator_id`` are required: policy is evaluated against them and the
        run record preserves them, so the caller must state the environment its manifest declares
        rather than inherit a default that would make the provenance record false.

        ``resume`` continues the campaign already recorded under ``campaign_id`` instead of
        starting a new one. A campaign runs for weeks, so the process that started it is not
        necessarily the process that finishes it, and the framework had restart reconciliation for
        the thirty-second thing and none for the three-week thing. What resume guarantees:

        - **History comes from the record, not from the caller.** Every observation is
          reconstructed from the campaign's own events and the runs they name, so an optimizer with
          no memory of the first process resumes knowing what the laboratory did.
        - **Completed work is not repeated.** An iteration whose run finished is restored as the
          success it was, including the case where the controller died between the run completing
          and the campaign recording it — the run record is the authority, and the missing campaign
          event is written on the way through.
        - **An unknown physical outcome stops the resume.** If any iteration names a run whose
          recorded state does not establish what happened — `intervention_required`, or any state
          that is not terminal — the resume is refused rather than continued over. The run layer
          refuses to re-dispatch such a task; a campaign that carried on unattended past it would
          be granting itself an acknowledgement the framework does not yet offer.
        - **Iteration numbering continues.** ``(campaign_id, iteration)`` identifies one decision
          for the life of the campaign, across any number of restarts.
        - **``max_iterations`` is the budget for the campaign, not for the invocation.** A resumed
          campaign that has already spent it stops immediately without dispatching anything.
          ``max_duration_seconds`` is the exception: it bounds this invocation, because the time a
          campaign spent dead is not time it spent working.

        Restoring what the optimizer learned is optional and additive. A campaign is resumable
        without it: `ResumableOptimizer.load_state` is used when the optimizer offers it and state
        was recorded, and otherwise the reconstructed observations are replayed through `observe`,
        which is all a grid or any other stateless method needs. When state is restored the
        observations are *not* also replayed, because the state already contains them.
        `state()` is unvalidated data on the way back in, so a resume refuses — before dispatching
        anything — when the recorded state was produced by a different optimizer class or when
        `load_state` rejects it. Continuing would run a differently-behaving search under an
        identifier that already names one.

        Every argument except ``workflow``, ``optimizer`` and the submission facts mirrors a
        :class:`opensdl_core.CampaignDefinition` field, name and default alike, and a test asserts
        it in both directions — so a stored definition can describe any campaign this method can
        run. ``objectives`` replaces the ``score_output`` / ``minimize`` / ``target_score`` triple
        with a list; supplying both a non-default triple and ``objectives`` is refused rather than
        silently resolved, except that ``target_score`` fills the primary objective's target when
        the objective declares none. The definition resolves those arguments through the same
        :meth:`opensdl_core.CampaignProblem.declare`, so the two cannot disagree.

        ``batch_size`` is how many candidates the optimizer is asked for at once — a property of
        the method. ``max_parallel_runs`` is how many of them execute at the same time — a property
        of the laboratory — and it defaults to one, so a campaign that adds a batch does not
        silently start running its instruments concurrently.
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
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_parallel_runs < 1:
            raise ValueError("max_parallel_runs must be at least 1")

        problem = CampaignProblem.declare(
            objectives=objectives,
            score_output=score_output,
            minimize=minimize,
            target_score=target_score,
            space=search_space,
            candidate_constraints=candidate_constraints,
            outcome_constraints=outcome_constraints,
        )
        if resume and campaign_id is None:
            raise ValueError(
                "resume needs the campaign_id of the campaign being resumed; without it there is "
                "nothing to continue and a new campaign would be started under a new identifier"
            )
        # A minted identifier cannot already name a campaign, so only a caller-supplied one is
        # looked up. That lookup is what makes running the same identifier twice an error rather
        # than a second campaign wearing the first one's name.
        supplied_id = campaign_id
        campaign_id = campaign_id or new_id("campaign")
        recorded = self._recorded(campaign_id) if supplied_id is not None else None
        if recorded is not None and not resume:
            raise ValueError(
                f"campaign {campaign_id} is already recorded with {len(recorded.iterations)} "
                f"iteration(s) and state '{recorded.state.value}'. Running it again would emit a "
                "second CampaignStarted and number its iterations from zero, so "
                "(campaign_id, iteration) would no longer identify one decision. Pass resume=True "
                "to continue it, or a new campaign_id to start a new one."
            )
        if resume and recorded is None:
            raise ValueError(
                f"no campaign is recorded under {campaign_id}, so there is nothing to resume. "
                "Check the identifier, or start the campaign without resume=True."
            )

        history: list[CampaignObservation] = []
        catchup: list[EventRecord] = []
        iteration = 0
        batch = 0
        if recorded is not None:
            history, catchup = self._replay(recorded, problem=problem, operator_id=operator_id)
            iteration = max((item.iteration for item in history), default=-1) + 1
            batch = max((item.batch for item in history), default=-1) + 1
        consecutive_failures = _trailing_failures(history)
        discarded = 0
        started_at = time.monotonic()
        stop_reason = CampaignStopReason.MAX_ITERATIONS
        stop_detail = f"ran the configured budget of {max_iterations} iterations"
        header = {
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
            "problem": problem.model_dump(mode="json"),
            "batchSize": batch_size,
            "maxParallelRuns": max_parallel_runs,
        }
        if not resume:
            self.repositories.append_event(
                EventRecord(
                    type="CampaignStarted",
                    actor_id=operator_id,
                    campaign_id=campaign_id,
                    payload=header,
                )
            )
        if isinstance(optimizer, ConfigurableOptimizer):
            await _call(optimizer.configure, problem)

        if recorded is not None:
            # Everything that can refuse the resume has refused by now, and the optimizer is
            # configured, so this is the first write: the resume is committed before the events
            # that catch its record up to what the laboratory actually did.
            restored, detail = await _restore_state(optimizer, recorded, campaign_id)
            self.repositories.append_event(
                EventRecord(
                    type="CampaignResumed",
                    actor_id=operator_id,
                    campaign_id=campaign_id,
                    payload={
                        **header,
                        "resumedFromIterations": len(history),
                        "nextIteration": iteration,
                        "nextBatch": batch,
                        "recoveredIterations": [
                            int(event.payload["iteration"]) for event in catchup
                        ],
                        "consecutiveFailures": consecutive_failures,
                        "optimizerStateRestored": restored,
                        "optimizerStateDetail": detail,
                    },
                )
            )
            for event in catchup:
                self.repositories.append_event(event)
            if not restored:
                # The only way an optimizer that cannot restore state learns what already
                # happened. An optimizer that did restore state has these observations in it
                # already, and replaying them would fit every one of them twice.
                for observation in history:
                    await _call(optimizer.observe, observation)

        resume_stop = (
            _already_stopped(
                history,
                problem,
                consecutive_failures=consecutive_failures,
                max_consecutive_failures=max_consecutive_failures,
            )
            if recorded is not None
            else None
        )
        while resume_stop is None and iteration < max_iterations:
            elapsed = time.monotonic() - started_at
            if max_duration_seconds is not None and elapsed >= max_duration_seconds:
                stop_reason = CampaignStopReason.TIME_BUDGET_EXHAUSTED
                stop_detail = (
                    f"{elapsed:.3f}s of the {max_duration_seconds:g}s budget were spent before "
                    f"iteration {iteration}"
                )
                break
            requested = min(batch_size, max_iterations - iteration)
            proposed = await self._propose(optimizer, history, requested)
            if not proposed:
                stop_reason = CampaignStopReason.OPTIMIZER_EXHAUSTED
                stop_detail = f"the optimizer proposed no candidate for iteration {iteration}"
                break
            # The iteration budget is what bounds physical work, so an optimizer that proposes more
            # than the campaign asked for has the surplus cut rather than honoured.
            discarded += max(0, len(proposed) - requested)
            accepted = proposed[:requested]
            evidence = tuple(item.run_id for item in history if item.run_id)
            planned = [
                _Planned(
                    iteration=iteration + position,
                    batch=batch,
                    position=position,
                    batch_size=len(accepted),
                    suggestion=suggestion,
                    run_id=new_id("run"),
                )
                for position, suggestion in enumerate(accepted)
            ]
            iteration += len(planned)
            batch += 1
            for item in planned:
                self._record_decision(
                    item,
                    campaign_id=campaign_id,
                    operator_id=operator_id,
                    evidence=evidence,
                    history_size=len(history),
                )
            observations = await self._run_batch(
                planned,
                workflow=workflow,
                campaign_id=campaign_id,
                problem=problem,
                base_inputs=base_inputs,
                operator_id=operator_id,
                environment=environment,
                iteration_id_input=iteration_id_input,
                max_parallel_runs=max_parallel_runs,
            )
            history.extend(observations)
            for observation in observations:
                await _call(optimizer.observe, observation)

            stopped = False
            for observation in observations:
                if not observation.succeeded:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        stop_reason = CampaignStopReason.FAILURE_LIMIT
                        stop_detail = (
                            f"{consecutive_failures} consecutive iterations failed, so the failure "
                            f"is systematic rather than routine; last error: {observation.error}"
                        )
                        stopped = True
                        break
                    continue
                consecutive_failures = 0
                if _reaches_targets(observation, problem):
                    stop_reason = CampaignStopReason.TARGET_REACHED
                    stop_detail = _target_detail(observation, problem)
                    stopped = True
                    break
            if stopped:
                break

        if resume_stop is not None:
            stop_reason, stop_detail = resume_stop
        best = _best_observation(history, problem)
        state, state_error = await _read_state(optimizer)
        result = CampaignResult(
            campaign_id=campaign_id,
            stop_reason=stop_reason,
            stop_detail=stop_detail,
            history=history,
            best=best,
            problem=problem,
            optimizer_state=state,
        )
        self.repositories.append_event(
            EventRecord(
                type="CampaignCompleted",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={
                    "iterations": len(history),
                    "succeeded": len(result.successes),
                    "failed": len(result.failures),
                    "rejected": len(result.rejected),
                    "infeasible": len(result.successes) - len(result.feasible),
                    "discardedProposals": discarded,
                    "stopReason": stop_reason.value,
                    "stopDetail": stop_detail,
                    # The observation's own serialisation, so this payload and
                    # `campaign-observation.schema.json` describe one document. It used to be a
                    # hand-written mapping that dropped the constraint violations, the proposal
                    # and the batch, and carried a `feasible` flag derived from the violations it
                    # had just dropped.
                    "best": best.model_dump(mode="json", by_alias=True) if best else None,
                    "pareto": [item.iteration for item in result.pareto_front],
                    "optimizerState": state,
                    "optimizerStateError": state_error,
                    # Which optimizer produced that state. A resume compares it against the
                    # optimizer it was handed and refuses a mismatch rather than loading one
                    # method's model into another's.
                    "optimizerType": _optimizer_type(optimizer),
                },
            )
        )
        return result

    def _recorded(self, campaign_id: str) -> CampaignRecord | None:
        """The campaign already recorded under this identifier, or `None` if there is none."""

        try:
            return CampaignReader(self.repositories).get(campaign_id)
        except KeyError:
            return None

    def _replay(
        self,
        recorded: CampaignRecord,
        *,
        problem: CampaignProblem,
        operator_id: str,
    ) -> tuple[list[CampaignObservation], list[EventRecord]]:
        """Rebuild what a campaign did, from its own events and the runs those events name.

        Returns the reconstructed history and the events that bring the campaign's record up to
        date with the run record — the outcomes a controller that died mid-iteration never wrote.
        Refuses, before returning anything, if any iteration names a run whose recorded state does
        not establish what physically happened.

        The run record is consulted for every iteration that names a run, not only for the ones
        the campaign left open, because the campaign's own view of an iteration and the run's own
        state are written by different code at different moments and a resume is exactly the
        moment they can disagree.
        """

        runs: dict[str, RunRecord | None] = {}
        for item in recorded.iterations:
            if item.run_id is not None and item.run_id not in runs:
                runs[item.run_id] = self.repositories.get_run(item.run_id)

        for item in recorded.iterations:
            run = runs.get(item.run_id) if item.run_id is not None else None
            if run is None or run.state in _ESTABLISHED_RUN_STATES:
                continue
            raise WorkflowExecutionError(
                f"cannot resume campaign {recorded.campaign_id}: iteration {item.iteration} ran "
                f"{run.id}, which is recorded as '{run.state.value}', so OpenSDL does not know "
                "whether the physical work happened. Recorded run error: "
                f"{run.error or 'none recorded'}. Continuing the campaign unattended over that "
                "would grant it an acknowledgement the run layer refuses to grant: "
                "`run_workflow` will not re-dispatch that run either. A human must establish what "
                "the equipment did. OpenSDL has no operation for acknowledging an intervention "
                "yet, so record the finding outside the campaign and submit the remaining search "
                "as a new campaign."
            )

        history: list[CampaignObservation] = []
        catchup: list[EventRecord] = []
        for item in recorded.iterations:
            run = runs.get(item.run_id) if item.run_id is not None else None
            observation, event = _restated(
                item,
                run,
                problem=problem,
                campaign_id=recorded.campaign_id,
                operator_id=operator_id,
            )
            history.append(observation)
            if event is not None:
                catchup.append(event)
        return history, catchup

    async def _propose(
        self,
        optimizer: Optimizer,
        history: list[CampaignObservation],
        count: int,
    ) -> list[Suggestion]:
        """Ask the optimizer for up to `count` candidates, whatever shape it answers in."""

        supplied = list(history)
        if isinstance(optimizer, BatchOptimizer):
            proposed = await _call(optimizer.suggest_batch, supplied, count=count)
        else:
            proposed = await _call(optimizer.suggest, supplied)
        if proposed is None:
            return []
        if isinstance(proposed, Suggestion | Mapping):
            proposed = [proposed]
        return [_as_suggestion(item) for item in proposed]

    def _record_decision(
        self,
        planned: _Planned,
        *,
        campaign_id: str,
        operator_id: str,
        evidence: tuple[str, ...],
        history_size: int,
    ) -> None:
        """Record the choice before the work it causes, from the evidence that produced it."""

        suggestion = planned.suggestion
        based_on = (
            list(suggestion.evidence_run_ids)
            if suggestion.evidence_run_ids is not None
            else list(evidence)
        )
        decision = Decision(
            campaign_id=campaign_id,
            iteration=planned.iteration,
            selected=dict(planned.candidate),
            rationale=suggestion.rationale or _default_rationale(planned, history_size),
            evidence_run_ids=based_on,
        )
        self.repositories.append_event(
            EventRecord(
                type="DecisionRecorded",
                actor_id=operator_id,
                # The run this decision causes does not exist yet, and for a candidate the campaign
                # goes on to refuse it never will. It is named in the payload, as
                # `CampaignIterationStarted` has always named it, rather than claimed on the event.
                campaign_id=campaign_id,
                payload={
                    "decision": decision.model_dump(mode="json"),
                    "runId": planned.run_id,
                    "acquisition": suggestion.acquisition,
                    "acquisitionFunction": suggestion.acquisition_function,
                    "predictions": {
                        name: value.model_dump(mode="json")
                        for name, value in suggestion.predictions.items()
                    },
                    "model": dict(suggestion.model),
                    "batch": planned.batch,
                    "batchIndex": planned.position,
                    "batchSize": planned.batch_size,
                },
            )
        )

    async def _run_batch(
        self,
        planned: Sequence[_Planned],
        *,
        workflow: WorkflowDefinition,
        campaign_id: str,
        problem: CampaignProblem,
        base_inputs: dict[str, Any] | None,
        operator_id: str,
        environment: str,
        iteration_id_input: str | None,
        max_parallel_runs: int,
    ) -> list[CampaignObservation]:
        """Refuse what the problem forbids, run the rest, and return them in iteration order."""

        settled: list[CampaignObservation | None] = [None] * len(planned)
        pending: list[tuple[int, _Planned]] = []
        for index, item in enumerate(planned):
            violations = problem.violations(item.candidate)
            if violations:
                settled[index] = self._reject(
                    item,
                    violations,
                    campaign_id=campaign_id,
                    operator_id=operator_id,
                )
            else:
                pending.append((index, item))

        if pending:
            limiter = asyncio.Semaphore(max_parallel_runs)

            async def _dispatch(index: int, item: _Planned) -> None:
                async with limiter:
                    settled[index] = await self._run_iteration(
                        item,
                        workflow=workflow,
                        campaign_id=campaign_id,
                        problem=problem,
                        base_inputs=base_inputs,
                        operator_id=operator_id,
                        environment=environment,
                        iteration_id_input=iteration_id_input,
                    )

            await asyncio.gather(*[_dispatch(index, item) for index, item in pending])
        return [item for item in settled if item is not None]

    def _reject(
        self,
        planned: _Planned,
        violations: list[str],
        *,
        campaign_id: str,
        operator_id: str,
    ) -> CampaignObservation:
        """Refuse a candidate before it becomes a run, a policy decision, or a held resource."""

        error = "; ".join(violations)
        self.repositories.append_event(
            EventRecord(
                type="CampaignCandidateRejected",
                actor_id=operator_id,
                campaign_id=campaign_id,
                payload={
                    "iteration": planned.iteration,
                    "candidate": dict(planned.candidate),
                    "violations": violations,
                    "batch": planned.batch,
                },
            )
        )
        return CampaignObservation(
            iteration=planned.iteration,
            candidate=dict(planned.candidate),
            status=CampaignObservationStatus.REJECTED,
            error=error,
            constraint_violations=tuple(violations),
            suggestion=planned.suggestion,
            batch=planned.batch,
        )

    async def _run_iteration(
        self,
        planned: _Planned,
        *,
        workflow: WorkflowDefinition,
        campaign_id: str,
        problem: CampaignProblem,
        base_inputs: dict[str, Any] | None,
        operator_id: str,
        environment: str,
        iteration_id_input: str | None,
    ) -> CampaignObservation:
        """Execute one candidate and return what happened, successfully or not."""

        iteration = planned.iteration
        candidate = dict(planned.candidate)
        inputs = dict(base_inputs or {})
        inputs.update(candidate)
        # Every run and task event the iteration emits carries the campaign id, so a single query
        # by campaign returns the execution history and not only the decisions.
        run_id = planned.run_id
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
                    "batch": planned.batch,
                    "batchIndex": planned.position,
                    "batchSize": planned.batch_size,
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
            values = problem.measure(run.outputs)
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
                        "batch": planned.batch,
                    },
                )
            )
            return CampaignObservation(
                iteration=iteration,
                candidate=candidate,
                run_id=run_id if submitted is not None else None,
                status=CampaignObservationStatus.FAILED,
                error=error,
                suggestion=planned.suggestion,
                batch=planned.batch,
            )
        violations = problem.infeasibilities(run.outputs)
        score = values[problem.primary.name].value
        self.repositories.append_event(
            EventRecord(
                type="CampaignIterationCompleted",
                actor_id=operator_id,
                run_id=run.id,
                campaign_id=campaign_id,
                payload={
                    "iteration": iteration,
                    "runId": run.id,
                    "score": score,
                    "objectives": {
                        name: value.model_dump(mode="json") for name, value in values.items()
                    },
                    "constraintViolations": violations,
                    "batch": planned.batch,
                },
            )
        )
        return CampaignObservation(
            iteration=iteration,
            candidate=candidate,
            score=score,
            run_id=run.id,
            outputs=run.outputs,
            objectives=values,
            constraint_violations=tuple(violations),
            suggestion=planned.suggestion,
            batch=planned.batch,
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
    """Whether an iteration is still in flight, produced a score, failed, or was never submitted."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    #: The campaign refused the candidate before submitting it. No run exists.
    REJECTED = "rejected"


class CampaignIterationRecord(OpenSDLModel):
    """One iteration as the event stream recorded it."""

    iteration: int = Field(ge=0)
    candidate: dict[str, Any] = Field(default_factory=dict)
    state: CampaignIterationState = CampaignIterationState.RUNNING
    #: The run this iteration launched. `None` when the submission was rejected before the runtime
    #: created a run, and when the campaign refused the candidate outright.
    run_id: str | None = None
    score: float | None = None
    error: str | None = None
    #: Every declared objective the run reported, with its measured uncertainty.
    objectives: dict[str, ObjectiveValue] = Field(default_factory=dict)
    #: Why this iteration is infeasible, or why the candidate was refused.
    constraint_violations: list[str] = Field(default_factory=list)
    decision: IterationDecision | None = None
    batch: int = 0

    @computed_field
    @property
    def feasible(self) -> bool:
        return not self.constraint_violations


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
    #: What the campaign declared it was searching. `None` for a campaign recorded before the
    #: declaration existed; the scalar fields above are then the whole statement of the objective.
    problem: CampaignProblem | None = None
    batch_size: int = 1
    max_parallel_runs: int = 1
    started_at: datetime | None = None
    #: When this campaign was last resumed, and how many times it has been. A campaign that ran in
    #: one process reports `None` and zero.
    resumed_at: datetime | None = None
    resume_count: int = 0
    completed_at: datetime | None = None
    stop_reason: CampaignStopReason | None = None
    stop_detail: str = ""
    #: What the optimizer knew when the campaign stopped, if it was able to say, and which
    #: optimizer knew it. A resume hands the state back to an optimizer that can take it and
    #: refuses when `optimizer_type` names a different one.
    optimizer_state: dict[str, Any] | None = None
    optimizer_type: str = ""
    iterations: list[CampaignIterationRecord] = Field(default_factory=list)
    #: The best scoring feasible iteration. While a campaign is running this is the best so far,
    #: which is what an operator watching one wants; once it completes it is the one it recorded.
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
    def rejected(self) -> int:
        return sum(1 for item in self.iterations if item.state is CampaignIterationState.REJECTED)

    @computed_field
    @property
    def running(self) -> int:
        return sum(1 for item in self.iterations if item.state is CampaignIterationState.RUNNING)


def project_campaign(campaign_id: str, events: Sequence[EventRecord]) -> CampaignRecord:
    """Reconstruct one campaign from the events it emitted, in the order they were recorded.

    Two forms of the record are read. A campaign recorded before decisions moved ahead of the runs
    they cause marked success with a scored `DecisionRecorded`; a campaign recorded since marks it
    with `CampaignIterationCompleted`, and its `DecisionRecorded` carries the reasoning instead of
    an outcome. An event log is a record of what happened, so both are projected rather than one
    being declared wrong after the fact.

    A `CampaignResumed` restates the header — a resumed campaign may be given a larger budget than
    the one it started with — and puts the campaign back into `RUNNING`, because a campaign that
    completed and was then resumed has not completed.
    """

    started = next((event for event in events if event.type == "CampaignStarted"), None)
    if started is None:
        raise KeyError(campaign_id)
    header: dict[str, Any] = dict(started.payload)
    iterations: dict[int, CampaignIterationRecord] = {}

    def _update(index: int, **changes: Any) -> None:
        current = iterations.get(index) or CampaignIterationRecord(iteration=index)
        iterations[index] = current.model_copy(update=changes)

    completed: EventRecord | None = None
    resumed: EventRecord | None = None
    resume_count = 0
    for event in events:
        payload = event.payload
        if event.type == "CampaignResumed":
            header = {**header, **payload}
            completed = None
            resumed = event
            resume_count += 1
        elif event.type == "CampaignIterationStarted":
            _update(
                int(payload["iteration"]),
                candidate=dict(payload.get("candidate") or {}),
                run_id=payload.get("runId"),
                state=CampaignIterationState.RUNNING,
                batch=int(payload.get("batch") or 0),
            )
        elif event.type == "DecisionRecorded":
            decision = payload.get("decision") or {}
            index = int(decision.get("iteration", -1))
            changes: dict[str, Any] = {
                "candidate": dict(decision.get("selected") or {}),
                "decision": _iteration_decision(payload, decision),
            }
            if "score" in payload:
                # The pre-decision-reordering form: the decision was written after the run and
                # carried its score, so it is also the only record that the iteration succeeded.
                changes["state"] = CampaignIterationState.SUCCEEDED
                changes["score"] = payload.get("score")
            _update(index, **changes)
        elif event.type == "CampaignIterationCompleted":
            _update(
                int(payload["iteration"]),
                state=CampaignIterationState.SUCCEEDED,
                score=payload.get("score"),
                run_id=payload.get("runId"),
                objectives={
                    name: ObjectiveValue.model_validate(value)
                    for name, value in (payload.get("objectives") or {}).items()
                },
                constraint_violations=list(payload.get("constraintViolations") or []),
            )
        elif event.type == "CampaignCandidateRejected":
            violations = list(payload.get("violations") or [])
            _update(
                int(payload["iteration"]),
                state=CampaignIterationState.REJECTED,
                candidate=dict(payload.get("candidate") or {}),
                constraint_violations=violations,
                error="; ".join(violations),
                batch=int(payload.get("batch") or 0),
            )
        elif event.type == "CampaignIterationFailed":
            index = int(payload["iteration"])
            current = iterations.get(index)
            _update(
                index,
                state=CampaignIterationState.FAILED,
                error=payload.get("error"),
                run_id=payload.get("runId") or (current.run_id if current else None),
            )
        elif event.type == "CampaignCompleted":
            completed = event

    ordered = [iterations[index] for index in sorted(iterations) if index >= 0]
    minimize = bool(header.get("minimize", True))
    problem = CampaignProblem.model_validate(header["problem"]) if header.get("problem") else None
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
        problem=problem,
        batch_size=int(header.get("batchSize") or 1),
        max_parallel_runs=int(header.get("maxParallelRuns") or 1),
        started_at=started.occurred_at,
        resumed_at=resumed.occurred_at if resumed is not None else None,
        resume_count=resume_count,
        completed_at=completed.occurred_at if completed is not None else None,
        stop_reason=(
            CampaignStopReason(completed.payload["stopReason"]) if completed is not None else None
        ),
        stop_detail=str(completed.payload.get("stopDetail", "")) if completed is not None else "",
        optimizer_state=completed.payload.get("optimizerState") if completed is not None else None,
        optimizer_type=(
            str(completed.payload.get("optimizerType") or "") if completed is not None else ""
        ),
        iterations=ordered,
        best=_best_iteration(ordered, problem, minimize),
    )


def _iteration_decision(payload: dict[str, Any], decision: dict[str, Any]) -> IterationDecision:
    return IterationDecision(
        rationale=str(decision.get("rationale") or ""),
        acquisition=payload.get("acquisition"),
        acquisition_function=str(payload.get("acquisitionFunction") or ""),
        predictions={
            name: ObjectiveValue.model_validate(value)
            for name, value in (payload.get("predictions") or {}).items()
        },
        model=dict(payload.get("model") or {}),
        evidence_run_ids=list(decision.get("evidence_run_ids") or []),
        batch=int(payload.get("batch") or 0),
        batch_index=int(payload.get("batchIndex") or 0),
        batch_size=int(payload.get("batchSize") or 1),
    )


def _best_iteration(
    iterations: Sequence[CampaignIterationRecord],
    problem: CampaignProblem | None,
    minimize: bool,
) -> CampaignIterationRecord | None:
    """The best feasible iteration by the primary objective. Infeasible points cannot win."""

    objective = problem.primary if problem is not None else None
    name = objective.name if objective is not None else ""
    smaller_is_better = objective.minimize if objective is not None else minimize
    scored = [item for item in iterations if item.score is not None and item.feasible]
    if not scored:
        return None
    chooser = min if smaller_is_better else max

    def _value(item: CampaignIterationRecord) -> float:
        measured = item.objectives.get(name)
        if measured is not None:
            return measured.value
        return item.score if item.score is not None else 0.0

    return chooser(scored, key=_value)


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

    #: The events that bound a campaign. Listing asks for these rather than reading every event
    #: ever recorded, because run and task events now carry a campaign id too and a campaign of a
    #: hundred runs contributes thousands of events that say nothing about whether it started or
    #: finished. `CampaignResumed` is one of them: a campaign that completed and was then resumed
    #: is running again, and a listing that could not see the resume would report it finished.
    LIFECYCLE_EVENT_TYPES = ("CampaignStarted", "CampaignResumed", "CampaignCompleted")

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


async def _call(method: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Call an optimizer method without letting it hold the loop that runs the laboratory.

    A coroutine function is awaited here, because awaiting is what it asked for. Anything else runs
    on a worker thread: a surrogate refit inside a synchronous `suggest` otherwise blocks every
    timeout, lease and event write in the process, which is the same failure `AdapterExecutor` was
    built for in `opensdl_capabilities.execution`.

    It deliberately does not reuse that machinery. `AdapterExecutor` exists so the runtime can
    *abandon* a call it has stopped waiting for, and it keys a persistent loop by adapter name and
    speaks in `ExecutionRequest`. An abandoned optimizer is a different thing entirely: it is left
    mid-mutation and then asked for the next candidate, so there is nothing here that is safe to
    abandon, and a thread cannot be cancelled anyway. The runner never calls an optimizer
    concurrently with itself, but consecutive calls may land on different threads, so an optimizer
    holding thread-affine state must say so by being `async def`.
    """

    if inspect.iscoroutinefunction(method):
        return await method(*args, **kwargs)
    outcome = await asyncio.to_thread(method, *args, **kwargs)
    if inspect.isawaitable(outcome):
        return await outcome
    return outcome


async def _read_state(optimizer: Optimizer) -> tuple[dict[str, Any] | None, str | None]:
    """Preserve what the optimizer learned, or record why it could not be preserved.

    A model that will not serialise is a real and common answer, and it must not cost the campaign
    its result at the last step: everything the laboratory did is already recorded by this point.
    """

    if not isinstance(optimizer, StatefulOptimizer):
        return None, None
    try:
        return await _call(optimizer.state), None
    except Exception as exc:
        return None, _describe(exc)


def _optimizer_type(optimizer: object) -> str:
    """Name the class behind an optimizer, so recorded state can be traced to what produced it."""

    kind = type(optimizer)
    return f"{kind.__module__}.{kind.__qualname__}"


async def _restore_state(
    optimizer: Optimizer,
    recorded: CampaignRecord,
    campaign_id: str,
) -> tuple[bool, str]:
    """Hand back what a previous process recorded, or say why the resume proceeds without it.

    Returns whether state was restored and a sentence for the record. Raises when the state exists
    and cannot be restored safely — a different optimizer class, or a `load_state` that rejects the
    payload. Both mean the resumed campaign would search differently from the campaign whose
    identifier and record it is continuing, and the honest place to stop is before anything is
    dispatched rather than after.
    """

    current = _optimizer_type(optimizer)
    state = recorded.optimizer_state
    if state is None:
        return False, (
            "the campaign recorded no optimizer state, so the recorded observations were "
            "replayed instead"
        )
    if not isinstance(optimizer, ResumableOptimizer):
        return False, (
            f"{current} does not implement load_state, so the state recorded by "
            f"{recorded.optimizer_type or 'the previous process'} was left alone and the recorded "
            "observations were replayed instead"
        )
    if recorded.optimizer_type and recorded.optimizer_type != current:
        raise ValueError(
            f"cannot resume campaign {campaign_id}: its optimizer state was recorded by "
            f"{recorded.optimizer_type} and this resume was handed {current}. Loading one "
            "method's state into another would run a different search under an identifier that "
            "already names one. Resume with the optimizer that recorded the state, or start a new "
            "campaign."
        )
    try:
        await _call(optimizer.load_state, dict(state))
    except Exception as exc:
        raise ValueError(
            f"cannot resume campaign {campaign_id}: {current}.load_state rejected the state "
            f"recorded when the campaign last stopped: {_describe(exc)}. Nothing has been "
            "dispatched. Resume with an optimizer that can read that state, or start a new "
            "campaign rather than continuing this one with a differently-behaving method."
        ) from exc
    return True, f"restored the optimizer state recorded by {current}"


def _trailing_failures(history: Sequence[CampaignObservation]) -> int:
    """The unbroken run of unsuccessful attempts at the end of a history.

    The consecutive-failure limit is a statement about the laboratory, not about one process, so a
    restart that reset this count would let an unattended loop fail past the limit it declared.
    """

    count = 0
    for observation in reversed(history):
        if observation.succeeded:
            break
        count += 1
    return count


def _already_stopped(
    history: Sequence[CampaignObservation],
    problem: CampaignProblem,
    *,
    consecutive_failures: int,
    max_consecutive_failures: int,
) -> tuple[CampaignStopReason, str] | None:
    """Whether the replayed record already satisfies a stopping rule this invocation declares.

    A resume evaluates the same rules against the same history the live loop would have, so a
    campaign that already reached its target does not quietly do more physical work because a new
    process started. Only `max_duration_seconds` is exempt, and it is exempt because the wall clock
    a dead campaign consumed is not work it did.
    """

    if consecutive_failures >= max_consecutive_failures:
        last = history[-1] if history else None
        return (
            CampaignStopReason.FAILURE_LIMIT,
            f"{consecutive_failures} consecutive iterations had already failed when the campaign "
            f"was resumed, so the failure is systematic rather than routine; last error: "
            f"{last.error if last else 'none recorded'}",
        )
    for observation in history:
        if observation.succeeded and _reaches_targets(observation, problem):
            return CampaignStopReason.TARGET_REACHED, _target_detail(observation, problem)
    return None


def _restated(
    item: CampaignIterationRecord,
    run: RunRecord | None,
    *,
    problem: CampaignProblem,
    campaign_id: str,
    operator_id: str,
) -> tuple[CampaignObservation, EventRecord | None]:
    """One recorded iteration as an observation, plus the event that never got written.

    An iteration the campaign left open is settled from the run it named, because the run record
    is what the laboratory actually did and the campaign's silence is only what a dying process
    failed to say. Settling it emits the missing outcome event, so the next reader of this campaign
    sees the finished iteration rather than repeating this reconstruction.
    """

    suggestion = item.decision.as_suggestion(item.candidate) if item.decision else None
    common: dict[str, Any] = {
        "iteration": item.iteration,
        "candidate": dict(item.candidate),
        "suggestion": suggestion,
        "batch": item.batch,
    }
    # An iteration whose run row is gone names no run, exactly as the live path does for a
    # submission that was refused before the runtime created one.
    named_run = run.id if run is not None else None
    if item.state is CampaignIterationState.SUCCEEDED and item.score is not None:
        return (
            CampaignObservation(
                **common,
                score=item.score,
                run_id=named_run,
                outputs=dict(run.outputs) if run is not None else {},
                objectives=dict(item.objectives),
                constraint_violations=tuple(item.constraint_violations),
            ),
            None,
        )
    if item.state is CampaignIterationState.SUCCEEDED:
        # Recorded as a success with no score. Nothing can be inferred from that, and inventing a
        # score would put a number the laboratory never produced into the optimizer's history.
        return (
            CampaignObservation(
                **common,
                run_id=named_run,
                status=CampaignObservationStatus.FAILED,
                error="the campaign recorded this iteration as succeeded without a score",
            ),
            None,
        )
    if item.state is CampaignIterationState.REJECTED:
        return (
            CampaignObservation(
                **common,
                status=CampaignObservationStatus.REJECTED,
                error=item.error or "; ".join(item.constraint_violations) or "candidate refused",
                constraint_violations=tuple(item.constraint_violations),
            ),
            None,
        )
    if item.state is CampaignIterationState.FAILED:
        return (
            CampaignObservation(
                **common,
                run_id=named_run,
                status=CampaignObservationStatus.FAILED,
                error=item.error or "the campaign recorded a failure with no error",
            ),
            None,
        )

    # Left open by a process that did not survive to record the outcome.
    if run is None:
        return _recovered_failure(
            common,
            campaign_id=campaign_id,
            operator_id=operator_id,
            run_id=None,
            error=(
                "the campaign was interrupted before the run was created, so nothing was "
                "dispatched for this iteration"
            ),
        )
    if run.state is RunState.FAILED:
        return _recovered_failure(
            common,
            campaign_id=campaign_id,
            operator_id=operator_id,
            run_id=run.id,
            error=run.error or "the run failed and recorded no error",
        )
    try:
        values = problem.measure(run.outputs)
    except (KeyError, TypeError, ValueError) as exc:
        return _recovered_failure(
            common,
            campaign_id=campaign_id,
            operator_id=operator_id,
            run_id=run.id,
            error=_describe(exc),
        )
    violations = problem.infeasibilities(run.outputs)
    score = values[problem.primary.name].value
    return (
        CampaignObservation(
            **common,
            score=score,
            run_id=run.id,
            outputs=dict(run.outputs),
            objectives=values,
            constraint_violations=tuple(violations),
        ),
        EventRecord(
            type="CampaignIterationCompleted",
            actor_id=operator_id,
            run_id=run.id,
            campaign_id=campaign_id,
            payload={
                "iteration": item.iteration,
                "runId": run.id,
                "score": score,
                "objectives": {
                    name: value.model_dump(mode="json") for name, value in values.items()
                },
                "constraintViolations": violations,
                "batch": item.batch,
                "recovered": True,
            },
        ),
    )


def _recovered_failure(
    common: dict[str, Any],
    *,
    campaign_id: str,
    operator_id: str,
    run_id: str | None,
    error: str,
) -> tuple[CampaignObservation, EventRecord]:
    """Settle an interrupted iteration whose run establishes that it did not produce a score."""

    return (
        CampaignObservation(
            **common,
            run_id=run_id,
            status=CampaignObservationStatus.FAILED,
            error=error,
        ),
        EventRecord(
            type="CampaignIterationFailed",
            actor_id=operator_id,
            run_id=run_id,
            campaign_id=campaign_id,
            payload={
                "iteration": common["iteration"],
                "candidate": common["candidate"],
                "runId": run_id,
                "error": error,
                "batch": common["batch"],
                "recovered": True,
            },
        ),
    )


def _as_suggestion(proposed: Any) -> Suggestion:
    """Accept the two-method form's bare dictionary and the richer form alike."""

    if isinstance(proposed, Suggestion):
        return proposed
    if isinstance(proposed, Mapping):
        return Suggestion(parameters=dict(proposed))
    raise TypeError(
        "an optimizer must propose a parameter mapping or a Suggestion, "
        f"not {type(proposed).__name__}"
    )


def _dominates(
    left: CampaignObservation,
    right: CampaignObservation,
    objectives: Sequence[Objective],
) -> bool:
    """Whether `left` is at least as good everywhere and strictly better somewhere."""

    strictly_better = False
    for objective in objectives:
        here, there = left.objective(objective.name), right.objective(objective.name)
        if here is None or there is None:  # pragma: no cover - successes carry every objective
            return False
        if objective.minimize:
            if here > there:
                return False
            strictly_better = strictly_better or here < there
        else:
            if here < there:
                return False
            strictly_better = strictly_better or here > there
    return strictly_better


def _best_observation(
    history: Sequence[CampaignObservation],
    problem: CampaignProblem,
) -> CampaignObservation | None:
    eligible = [item for item in history if item.succeeded and item.feasible]
    if not eligible:
        return None
    primary = problem.primary
    chooser = min if primary.minimize else max
    return chooser(eligible, key=lambda item: item.objective(primary.name) or 0.0)


def _reaches_targets(observation: CampaignObservation, problem: CampaignProblem) -> bool:
    """Whether one feasible observation met every target the campaign declared."""

    targeted = [item for item in problem.objectives if item.target is not None]
    if not targeted or not observation.feasible:
        return False
    for objective in targeted:
        value = observation.objective(objective.name)
        target = objective.target
        if value is None or target is None:  # pragma: no cover - guarded above
            return False
        if value > target if objective.minimize else value < target:
            return False
    return True


def _target_detail(observation: CampaignObservation, problem: CampaignProblem) -> str:
    reached = [
        f"{item.name} {observation.objective(item.name)} against a target of {item.target} "
        f"({'minimizing' if item.minimize else 'maximizing'})"
        for item in problem.objectives
        if item.target is not None
    ]
    return f"iteration {observation.iteration} scored " + ", ".join(reached)


def _default_rationale(planned: _Planned, history_size: int) -> str:
    """Say what the decision rested on, for an optimizer that declared no reasoning of its own."""

    plural = "" if history_size == 1 else "s"
    based = f"{history_size} prior observation{plural}"
    if planned.batch_size > 1:
        return (
            f"optimizer proposed candidate {planned.position + 1} of {planned.batch_size} in "
            f"batch {planned.batch} for iteration {planned.iteration}, from {based}"
        )
    return f"optimizer proposed the candidate for iteration {planned.iteration} from {based}"


def _describe(exc: BaseException) -> str:
    """Render an exception the way the run record does, without ``KeyError``'s extra quoting."""

    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc) or type(exc).__name__
