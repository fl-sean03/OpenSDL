"""Closed-loop campaign execution.

A campaign is the one path OpenSDL runs unattended, so everything here assumes nobody is watching.
The environment and the operator are stated by the caller rather than defaulted, because a silent
default writes a false provenance record and evaluates policy against an environment the laboratory
never declared. A failed iteration is recorded and fed back to the optimizer rather than thrown,
because a clogged tip or an off-scale reading is routine in a laboratory and is information. Every
campaign records why it stopped, because "budget exhausted" and "target reached" are different
outcomes and the log has to say which one happened.

The optimizer contract is two required methods, `suggest` and `observe`, and four optional
capabilities an optimizer may add one at a time. A grid sweep implements the two and nothing else.
A Bayesian method needs more than a scalar score and a bare candidate dictionary, so each of the
following is expressible without becoming ceremony for the method that does not need it:

- **A batch.** `BatchOptimizer.suggest_batch` proposes several candidates at once, which is what
  q-EI and any laboratory with more than one reactor requires. How many are proposed and how many
  run at the same time are separate declarations: `batch_size` is a property of the method,
  `max_parallel_runs` is a property of the laboratory, and it defaults to one.
- **A declared problem.** `CampaignProblem` states the objectives, the search space, and the
  feasibility constraints, and the campaign declares it rather than the plugin hiding it in private
  configuration. That is what lets the framework refuse a candidate outside the space *before* a
  run is created, a policy decision is taken, or a resource is leased.
  `ConfigurableOptimizer.configure` hands the same declaration to the optimizer, so there is one
  statement of the problem rather than two that can disagree.
- **Uncertainty.** An objective carries a measured uncertainty and a `Suggestion` carries a
  predicted one, spelled the way `Quantity` and `Observation` already spell it in core.
- **Acquisition provenance.** A `Suggestion` carries the acquisition value and function, the model
  that produced it, and the runs it rested on. The decision is recorded *before* the run it causes,
  because that is when it was made, and `evidence_run_ids` names the runs it was based on rather
  than the run it caused.

An optimizer method may be `async def`, and a synchronous one runs on a worker thread: a surrogate
refit inside `suggest` otherwise holds the only event loop in the process and stalls every timeout,
lease and event write in the laboratory.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import Field, computed_field, model_validator

from opensdl_core import Decision, EventRecord, OpenSDLModel, WorkflowDefinition, new_id
from opensdl_storage import RepositoryStore

from .engine import ReferenceRuntime


class CampaignObservationStatus(StrEnum):
    """Whether an iteration produced a usable score."""

    SUCCEEDED = "succeeded"
    #: The workflow failed, or it completed and produced no usable score. Either way the candidate
    #: was attempted: physical work may have happened and the attempt is part of the record.
    FAILED = "failed"
    #: The campaign refused the candidate before submitting it, because it left the declared search
    #: space or broke a declared constraint. Nothing was leased and nothing was consumed, which is
    #: why this is not a failure: no physical work was attempted.
    REJECTED = "rejected"


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


class ObjectiveValue(OpenSDLModel):
    """A number and how sure the campaign is of it.

    Used for a measured objective and for a predicted one, because core already spells uncertainty
    this way on `Quantity` and `Observation` and a third spelling would help nobody.
    """

    value: float
    uncertainty: float | None = Field(default=None, ge=0)


class Objective(OpenSDLModel):
    """One thing the campaign is searching for, and where a run reports it."""

    name: str
    #: Dotted path into the run outputs, as `score_output` has always been.
    output: str
    minimize: bool = True
    #: Stop once a feasible observation reaches this value. `None` searches the whole budget.
    target: float | None = None
    #: Dotted path to the measured uncertainty of this objective. Declared, so a run that does not
    #: report it is an error rather than a silently dropped column.
    uncertainty_output: str | None = None


class ParameterKind(StrEnum):
    CONTINUOUS = "continuous"
    INTEGER = "integer"
    CATEGORICAL = "categorical"


class Parameter(OpenSDLModel):
    """One dimension of the search space.

    A parameter states its own domain so the framework can check a candidate against it. Use the
    constructors rather than the raw fields: they are the three combinations that are complete.
    """

    name: str
    kind: ParameterKind
    lower: float | None = None
    upper: float | None = None
    choices: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def _domain_is_complete(self) -> Parameter:
        if self.kind is ParameterKind.CATEGORICAL:
            if not self.choices:
                raise ValueError(f"categorical parameter {self.name} declares no choices")
            if self.lower is not None or self.upper is not None:
                raise ValueError(f"categorical parameter {self.name} cannot declare bounds")
            return self
        if self.choices:
            raise ValueError(f"{self.kind.value} parameter {self.name} cannot declare choices")
        if self.lower is None or self.upper is None:
            raise ValueError(f"{self.kind.value} parameter {self.name} must declare both bounds")
        if self.lower > self.upper:
            raise ValueError(f"parameter {self.name} declares a lower bound above its upper bound")
        return self

    @classmethod
    def continuous(cls, name: str, lower: float, upper: float) -> Parameter:
        return cls(name=name, kind=ParameterKind.CONTINUOUS, lower=lower, upper=upper)

    @classmethod
    def integer(cls, name: str, lower: int, upper: int) -> Parameter:
        return cls(name=name, kind=ParameterKind.INTEGER, lower=lower, upper=upper)

    @classmethod
    def categorical(cls, name: str, choices: Sequence[Any]) -> Parameter:
        return cls(name=name, kind=ParameterKind.CATEGORICAL, choices=list(choices))

    def violation(self, value: Any) -> str | None:
        """Say how `value` leaves this parameter's domain, or `None` if it does not."""

        if self.kind is ParameterKind.CATEGORICAL:
            if value in self.choices:
                return None
            return f"{self.name}={value!r} is not one of {self.choices!r}"
        number = _as_number(value)
        if number is None:
            return f"{self.name}={value!r} is not a number"
        if self.kind is ParameterKind.INTEGER and not float(number).is_integer():
            return f"{self.name}={value!r} is not an integer"
        lower, upper = self.lower, self.upper
        if lower is None or upper is None:  # pragma: no cover - the validator requires both
            return None
        if number < lower or number > upper:
            return f"{self.name}={value!r} is outside [{lower:g}, {upper:g}]"
        return None


class SearchSpace(OpenSDLModel):
    """The parameters a campaign is searching, declared by the campaign rather than the plugin.

    An empty space validates nothing, which is how a campaign written against the two-method
    optimizer contract keeps running unchanged.
    """

    parameters: list[Parameter] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_are_unique(self) -> SearchSpace:
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("a search space cannot declare the same parameter twice")
        return self

    def violations(self, candidate: Mapping[str, Any]) -> list[str]:
        """Every way `candidate` leaves this space, in declaration order then by extra name."""

        if not self.parameters:
            return []
        found: list[str] = []
        declared = {parameter.name for parameter in self.parameters}
        for parameter in self.parameters:
            if parameter.name not in candidate:
                found.append(f"the candidate declares no value for {parameter.name}")
                continue
            reason = parameter.violation(candidate[parameter.name])
            if reason is not None:
                found.append(reason)
        found.extend(
            f"{name} is not a parameter the search space declares"
            for name in candidate
            if name not in declared
        )
        return found


class CandidateConstraint(OpenSDLModel):
    """A linear feasibility requirement on the parameters, checked before anything is leased.

    Linear rather than an arbitrary predicate because a constraint has to survive being written
    down: a callable cannot be stored in a campaign definition, sent over an interface, or read
    back out of the record. Sum-to-one, a budget, and an ordering are all linear. A requirement
    that is not is expressed by the search space or refused by the optimizer.
    """

    name: str
    weights: dict[str, float]
    lower: float | None = None
    upper: float | None = None
    #: Floating-point slack. An equality constraint is `lower == upper`, and `0.1 + 0.9` is not
    #: exactly `1.0` in binary.
    tolerance: float = Field(default=1e-9, ge=0)
    description: str = ""

    @model_validator(mode="after")
    def _is_bounded(self) -> CandidateConstraint:
        if not self.weights:
            raise ValueError(f"candidate constraint {self.name} weights no parameter")
        if self.lower is None and self.upper is None:
            raise ValueError(
                f"candidate constraint {self.name} bounds nothing: declare lower, upper, or both"
            )
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError(f"candidate constraint {self.name} declares an empty interval")
        return self

    def violation(self, candidate: Mapping[str, Any]) -> str | None:
        total = 0.0
        for name, weight in self.weights.items():
            value = _as_number(candidate.get(name))
            if value is None:
                return f"{self.name}: the candidate carries no numeric {name}"
            total += weight * value
        if self.lower is not None and total < self.lower - self.tolerance:
            return f"{self.name}: {total:g} is below {self.lower:g}"
        if self.upper is not None and total > self.upper + self.tolerance:
            return f"{self.name}: {total:g} is above {self.upper:g}"
        return None


class OutcomeConstraint(OpenSDLModel):
    """A feasibility requirement on what a run produced, checked once it has produced it.

    An observation that breaks one is still an observation: the work happened, the numbers are
    real, and an optimizer doing constrained search needs them. It is excluded from the best and
    cannot reach a target, and nothing else about it changes.
    """

    name: str
    #: Dotted path into the run outputs.
    output: str
    lower: float | None = None
    upper: float | None = None
    description: str = ""

    @model_validator(mode="after")
    def _is_bounded(self) -> OutcomeConstraint:
        if self.lower is None and self.upper is None:
            raise ValueError(
                f"outcome constraint {self.name} bounds nothing: declare lower, upper, or both"
            )
        return self

    def violation(self, outputs: Mapping[str, Any]) -> str | None:
        try:
            raw = _get_path(dict(outputs), self.output)
        except KeyError:
            return (
                f"{self.name}: the run reported no {self.output}, "
                "so feasibility cannot be established"
            )
        value = _as_number(raw)
        if value is None:
            return f"{self.name}: {self.output}={raw!r} is not a number"
        if self.lower is not None and value < self.lower:
            return f"{self.name}: {self.output}={value:g} is below {self.lower:g}"
        if self.upper is not None and value > self.upper:
            return f"{self.name}: {self.output}={value:g} is above {self.upper:g}"
        return None


class CampaignProblem(OpenSDLModel):
    """What a campaign declared it is searching: the objectives, the space, and feasibility.

    This is the framework's copy, not the plugin's. It is checked against every candidate before
    the candidate becomes a run, and it is handed to an optimizer that asks for it, so the search
    space is stated once.
    """

    objectives: list[Objective]
    space: SearchSpace = Field(default_factory=SearchSpace)
    candidate_constraints: list[CandidateConstraint] = Field(default_factory=list)
    outcome_constraints: list[OutcomeConstraint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _objectives_are_declared(self) -> CampaignProblem:
        if not self.objectives:
            raise ValueError("a campaign must declare at least one objective")
        names = [objective.name for objective in self.objectives]
        if len(names) != len(set(names)):
            raise ValueError("a campaign cannot declare the same objective twice")
        return self

    @property
    def primary(self) -> Objective:
        """The objective a single `best` is chosen by. Multi-objective results are the front."""
        return self.objectives[0]

    def violations(self, candidate: Mapping[str, Any]) -> list[str]:
        """Every reason this candidate must not be submitted, checked before anything is leased."""

        found = self.space.violations(candidate)
        found.extend(
            reason
            for reason in (
                constraint.violation(candidate) for constraint in self.candidate_constraints
            )
            if reason is not None
        )
        return found

    def infeasibilities(self, outputs: Mapping[str, Any]) -> list[str]:
        """Every outcome constraint the finished run broke."""

        return [
            reason
            for reason in (constraint.violation(outputs) for constraint in self.outcome_constraints)
            if reason is not None
        ]


@dataclass(frozen=True)
class Suggestion:
    """One proposal, and the reasoning that produced it.

    Everything but `parameters` is optional. An optimizer with nothing to say returns a plain
    dictionary and the runner wraps it; an optimizer that fitted a model says what it predicted,
    how sure it was, which acquisition function ranked the candidate, and which model did it. That
    is what turns `Decision.rationale` from a template string into a decision record.
    """

    parameters: dict[str, Any]
    #: Predicted objective values keyed by objective name, with the uncertainty of the prediction.
    predictions: Mapping[str, ObjectiveValue] = field(default_factory=dict)
    #: The acquisition value this candidate was ranked by. For a jointly optimized batch such as
    #: q-EI this is the value of the batch, repeated, with `acquisition_function` naming it.
    acquisition: float | None = None
    acquisition_function: str = ""
    #: Whatever identifies the model that proposed this: name, version, kernel, seed, fit size.
    model: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""
    #: The runs this proposal rested on. `None` means the history the runner supplied, which is the
    #: honest default; a trust-region or windowed method states the subset it actually used.
    evidence_run_ids: tuple[str, ...] | None = None


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
    #: Every declared objective this run reported, with its measured uncertainty. `score` is the
    #: primary objective's value and stays the scalar view of the same thing.
    objectives: Mapping[str, ObjectiveValue] = field(default_factory=dict)
    #: Why this observation is infeasible: a broken outcome constraint, or — for a rejected
    #: candidate — the reason the campaign refused to submit it.
    constraint_violations: tuple[str, ...] = ()
    #: What proposed this candidate, so an optimizer can compare its prediction to the outcome.
    suggestion: Suggestion | None = None
    #: Which proposed batch this candidate came from. Zero for a campaign that never batches.
    batch: int = 0

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
        if self.status is CampaignObservationStatus.REJECTED and self.run_id is not None:
            raise ValueError("a rejected candidate was never submitted, so it names no run")

    @property
    def succeeded(self) -> bool:
        return self.status is CampaignObservationStatus.SUCCEEDED

    @property
    def attempted(self) -> bool:
        """Whether the laboratory was asked to do the work. A rejected candidate was not."""
        return self.status is not CampaignObservationStatus.REJECTED

    @property
    def feasible(self) -> bool:
        """Whether every declared constraint held. A campaign that declares none is all feasible."""
        return not self.constraint_violations


@runtime_checkable
class Optimizer(Protocol):
    """Candidate source for a campaign. Two methods, and nothing else is required.

    ``history`` holds every attempt in order, failures and rejections included. An optimizer that
    filters history down to successes will propose a failing candidate forever.

    `suggest` may return a plain parameter dictionary, as it always has, or a `Suggestion` carrying
    the reasoning behind it. Either method may be declared `async def`; a synchronous one is run on
    a worker thread so that a surrogate refit does not hold the laboratory's event loop.
    """

    def suggest(
        self, history: list[CampaignObservation]
    ) -> dict[str, Any] | Suggestion | None | Awaitable[dict[str, Any] | Suggestion | None]: ...

    def observe(self, observation: CampaignObservation) -> None | Awaitable[None]: ...


@runtime_checkable
class BatchOptimizer(Protocol):
    """An optimizer that can propose several candidates at once.

    `count` is how many the campaign has budget for, never more. Returning fewer is meaningful and
    allowed; returning more is truncated, because the iteration budget is what bounds physical
    work. When an optimizer implements this the runner uses it for every proposal, including
    batches of one, so there is one code path rather than two that can disagree.
    """

    def suggest_batch(
        self, history: list[CampaignObservation], *, count: int
    ) -> (
        Sequence[dict[str, Any] | Suggestion]
        | None
        | Awaitable[Sequence[dict[str, Any] | Suggestion] | None]
    ): ...


@runtime_checkable
class ConfigurableOptimizer(Protocol):
    """An optimizer that is told the problem the campaign declared, once, before the loop.

    This is what stops the search space from living in two places. It is also where a future
    campaign resume restores optimizer state, because it is already the one hook that runs before
    the first proposal.
    """

    def configure(self, problem: CampaignProblem) -> None | Awaitable[None]: ...


@runtime_checkable
class StatefulOptimizer(Protocol):
    """An optimizer that can hand out what it learned.

    The runner reads this once, when the campaign stops, and records it. Nothing restores it: a
    campaign resume, and the matching `load_state`, is a separate piece of work. What this makes
    true today is that a fitted model's state survives the process that fitted it.
    """

    def state(self) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


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
    ) -> CampaignResult:
        """Run a closed loop until a stopping rule fires, and record why it stopped.

        ``environment`` and ``operator_id`` are required: policy is evaluated against them and the
        run record preserves them, so the caller must state the environment its manifest declares
        rather than inherit a default that would make the provenance record false.

        The control arguments from ``base_inputs`` to ``iteration_id_input`` mirror
        :class:`opensdl_core.CampaignDefinition` field for field, including defaults.

        The arguments below ``campaign_id`` declare the problem and the throughput, and have no
        field on that definition yet. ``objectives`` replaces the ``score_output`` / ``minimize`` /
        ``target_score`` triple with a list; supplying both a non-default triple and ``objectives``
        is refused rather than silently resolved, except that ``target_score`` fills the primary
        objective's target when the objective declares none.

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

        problem = _declare(
            objectives=objectives,
            score_output=score_output,
            minimize=minimize,
            target_score=target_score,
            search_space=search_space,
            candidate_constraints=candidate_constraints,
            outcome_constraints=outcome_constraints,
        )
        campaign_id = campaign_id or new_id("campaign")
        history: list[CampaignObservation] = []
        consecutive_failures = 0
        discarded = 0
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
                    "problem": problem.model_dump(mode="json"),
                    "batchSize": batch_size,
                    "maxParallelRuns": max_parallel_runs,
                },
            )
        )
        if isinstance(optimizer, ConfigurableOptimizer):
            await _call(optimizer.configure, problem)

        iteration = 0
        batch = 0
        while iteration < max_iterations:
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
                    "best": _observation_json(best),
                    "pareto": [item.iteration for item in result.pareto_front],
                    "optimizerState": state,
                    "optimizerStateError": state_error,
                },
            )
        )
        return result

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
            values = _measure(run.outputs, problem)
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


class IterationDecision(OpenSDLModel):
    """Why this candidate was chosen, as the optimizer stated it at the time.

    Everything here is optional because an optimizer that ranks nothing has nothing to declare.
    What is never optional is `rationale` and `evidence_run_ids`: the runner writes a sentence and
    names the runs the proposal rested on even when the optimizer says nothing at all.
    """

    rationale: str = ""
    acquisition: float | None = None
    acquisition_function: str = ""
    predictions: dict[str, ObjectiveValue] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)
    evidence_run_ids: list[str] = Field(default_factory=list)
    batch: int = 0
    batch_index: int = 0
    batch_size: int = 1


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
    completed_at: datetime | None = None
    stop_reason: CampaignStopReason | None = None
    stop_detail: str = ""
    #: What the optimizer knew when the campaign stopped, if it was able to say. Nothing restores
    #: it yet; it is recorded so that a resume has something to restore from.
    optimizer_state: dict[str, Any] | None = None
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
    """

    started = next((event for event in events if event.type == "CampaignStarted"), None)
    if started is None:
        raise KeyError(campaign_id)
    header = started.payload
    iterations: dict[int, CampaignIterationRecord] = {}

    def _update(index: int, **changes: Any) -> None:
        current = iterations.get(index) or CampaignIterationRecord(iteration=index)
        iterations[index] = current.model_copy(update=changes)

    completed: EventRecord | None = None
    for event in events:
        payload = event.payload
        if event.type == "CampaignIterationStarted":
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
        completed_at=completed.occurred_at if completed is not None else None,
        stop_reason=(
            CampaignStopReason(completed.payload["stopReason"]) if completed is not None else None
        ),
        stop_detail=str(completed.payload.get("stopDetail", "")) if completed is not None else "",
        optimizer_state=completed.payload.get("optimizerState") if completed is not None else None,
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


def _declare(
    *,
    objectives: Sequence[Objective] | None,
    score_output: str,
    minimize: bool,
    target_score: float | None,
    search_space: SearchSpace | None,
    candidate_constraints: Sequence[CandidateConstraint],
    outcome_constraints: Sequence[OutcomeConstraint],
) -> CampaignProblem:
    """Build the declared problem from either the scalar arguments or the objective list."""

    if objectives is None:
        declared = [
            Objective(
                name=score_output,
                output=score_output,
                minimize=minimize,
                target=target_score,
            )
        ]
    else:
        if score_output != "score" or minimize is not True:
            raise ValueError(
                "a campaign that declares objectives states minimize and the output path on each "
                "one; score_output and minimize describe a single objective and cannot also apply"
            )
        declared = [item.model_copy(deep=True) for item in objectives]
        if not declared:
            raise ValueError("a campaign must declare at least one objective")
        if target_score is not None and declared[0].target is None:
            declared[0] = declared[0].model_copy(update={"target": target_score})
    return CampaignProblem(
        objectives=declared,
        space=search_space or SearchSpace(),
        candidate_constraints=list(candidate_constraints),
        outcome_constraints=list(outcome_constraints),
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


def _measure(outputs: dict[str, Any], problem: CampaignProblem) -> dict[str, ObjectiveValue]:
    """Read every declared objective out of the run, with the uncertainty it declared."""

    measured: dict[str, ObjectiveValue] = {}
    for objective in problem.objectives:
        value = float(_get_path(outputs, objective.output))
        uncertainty = None
        if objective.uncertainty_output is not None:
            uncertainty = float(_get_path(outputs, objective.uncertainty_output))
        measured[objective.name] = ObjectiveValue(value=value, uncertainty=uncertainty)
    return measured


def _objective_of(observation: CampaignObservation, name: str) -> float | None:
    measured = observation.objectives.get(name)
    if measured is not None:
        return measured.value
    return observation.score


def _dominates(
    left: CampaignObservation,
    right: CampaignObservation,
    objectives: Sequence[Objective],
) -> bool:
    """Whether `left` is at least as good everywhere and strictly better somewhere."""

    strictly_better = False
    for objective in objectives:
        here, there = _objective_of(left, objective.name), _objective_of(right, objective.name)
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
    return chooser(eligible, key=lambda item: _objective_of(item, primary.name) or 0.0)


def _reaches_targets(observation: CampaignObservation, problem: CampaignProblem) -> bool:
    """Whether one feasible observation met every target the campaign declared."""

    targeted = [item for item in problem.objectives if item.target is not None]
    if not targeted or not observation.feasible:
        return False
    for objective in targeted:
        value = _objective_of(observation, objective.name)
        target = objective.target
        if value is None or target is None:  # pragma: no cover - guarded above
            return False
        if value > target if objective.minimize else value < target:
            return False
    return True


def _target_detail(observation: CampaignObservation, problem: CampaignProblem) -> str:
    reached = [
        f"{item.name} {_objective_of(observation, item.name)} against a target of {item.target} "
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


def _as_number(value: Any) -> float | None:
    """A real number, or `None`. `bool` is an `int` in Python and is not a measurement."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _get_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"campaign score output not found: {path}")
        current = current[segment]
    return current


def _describe(exc: BaseException) -> str:
    """Render an exception the way the run record does, without ``KeyError``'s extra quoting."""

    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc) or type(exc).__name__


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
        "objectives": {
            name: measured.model_dump(mode="json") for name, measured in value.objectives.items()
        },
        "feasible": value.feasible,
    }
