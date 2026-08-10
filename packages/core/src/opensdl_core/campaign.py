"""The closed-loop contract: what a campaign searches, and what an optimizer has to implement.

This is the extension point a self-driving-laboratory framework most needs third parties to write,
so it lives where a third party can reach it. It is declarations and protocols — a campaign's
objectives, its search space, its feasibility constraints, one attempted iteration, one proposal,
and the methods an optimizer offers — and it executes nothing. Publishing a BoTorch or Ax optimizer
against it means depending on `opensdl-core` and pydantic, not on the laboratory's storage, policy
and workflow machinery.

The execution side — `CampaignRunner`, the result and the projection of a campaign from its events
— lives in `opensdl-runtime`, which re-exports every name here so existing imports keep working.

The optimizer contract is two required methods, `suggest` and `observe`, and five optional
capabilities an optimizer may add one at a time. A grid sweep implements the two and nothing else.
A Bayesian method needs more than a scalar score and a bare candidate dictionary, so each of the
following is expressible without becoming ceremony for the method that does not need it:

- **A batch.** `BatchOptimizer.suggest_batch` proposes several candidates at once, which is what
  q-EI and any laboratory with more than one reactor requires.
- **A declared problem.** `CampaignProblem` states the objectives, the search space, and the
  feasibility constraints, and the campaign declares it rather than the plugin hiding it in private
  configuration. That is what lets the framework refuse a candidate outside the space *before* a
  run is created, a policy decision is taken, or a resource is leased.
  `ConfigurableOptimizer.configure` hands the same declaration to the optimizer, so there is one
  statement of the problem rather than two that can disagree.
- **Uncertainty.** An objective carries a measured uncertainty and a `Suggestion` carries a
  predicted one, spelled the way `Quantity` and `Observation` already spell it.
- **Acquisition provenance.** A `Suggestion` carries the acquisition value and function, the model
  that produced it, and the runs it rested on.
- **Surviving a restart.** `StatefulOptimizer.state` hands out what the optimizer learned and
  `ResumableOptimizer.load_state` takes it back, so a fitted surrogate outlives the process that
  fitted it. They are separate protocols, and separate from `ConfigurableOptimizer`, because
  `runtime_checkable` `isinstance` requires *every* member of a protocol: bundling `load_state`
  with `configure` would silently stop an optimizer that only configures from being configured.

An optimizer method may be `async def`, and the runner runs a synchronous one on a worker thread: a
surrogate refit inside `suggest` otherwise holds the only event loop in the process and stalls every
timeout, lease and event write in the laboratory.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from .models import OpenSDLModel

#: The two models an optimizer plugin exchanges with the campaign are also written into the durable
#: event stream, and that stream is camelCase. The alias generator applies the stream's spelling to
#: the recorded document while leaving the Python surface — and every existing keyword argument in
#: the repository and in a third-party plugin — as it was. A per-field `alias=` would have done the
#: same for the four fields that need it, and would have renamed the constructor's parameters with
#: them; this way the two spellings cannot drift apart and no call site changes.
#:
#: `frozen=True` preserves what the frozen dataclasses gave: a proposal an optimizer handed over
#: cannot be edited by the code that records it, and neither can an observation it was given.
CONTRACT_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=True,
    populate_by_name=True,
    alias_generator=to_camel,
    frozen=True,
)


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


class ObjectiveValue(OpenSDLModel):
    """A number and how sure the campaign is of it.

    Used for a measured objective and for a predicted one, because `Quantity` and `Observation`
    already spell uncertainty this way and a third spelling would help nobody.
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
        number = as_number(value)
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
            value = as_number(candidate.get(name))
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
    #: The exact value the output must carry, for a criterion that is not a measurement. A solver
    #: reporting whether it converged, and an instrument reporting whether it trusts a datum, are
    #: the cases `lower` and `upper` cannot express at all. Floats are deliberately excluded:
    #: exact equality on a measured quantity is almost never what a criterion means, and `lower`
    #: with `upper` says the intended thing.
    equals: bool | int | str | None = None
    description: str = ""

    @model_validator(mode="after")
    def _is_bounded(self) -> OutcomeConstraint:
        bounded = self.lower is not None or self.upper is not None
        if bounded and self.equals is not None:
            raise ValueError(
                f"outcome constraint {self.name} declares both a bound and an exact value: "
                "a criterion is one or the other"
            )
        if not bounded and self.equals is None:
            raise ValueError(
                f"outcome constraint {self.name} bounds nothing: declare lower, upper, or equals"
            )
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError(f"outcome constraint {self.name} declares an empty interval")
        return self

    def violation(self, outputs: Mapping[str, Any]) -> str | None:
        try:
            raw = read_path(dict(outputs), self.output)
        except KeyError:
            return (
                f"{self.name}: the run reported no {self.output}, "
                "so feasibility cannot be established"
            )
        if self.equals is not None:
            if matches_exactly(raw, self.equals):
                return None
            return f"{self.name}: {self.output}={raw!r} is not {self.equals!r}"
        value = as_number(raw)
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

    @classmethod
    def declare(
        cls,
        *,
        objectives: Sequence[Objective] | None = None,
        score_output: str = "score",
        minimize: bool = True,
        target_score: float | None = None,
        space: SearchSpace | None = None,
        candidate_constraints: Sequence[CandidateConstraint] = (),
        outcome_constraints: Sequence[OutcomeConstraint] = (),
    ) -> CampaignProblem:
        """Build the declared problem from either the scalar arguments or the objective list.

        One implementation, used by `CampaignDefinition` and by `CampaignRunner.run`, so a stored
        definition and a direct call cannot resolve the same arguments differently. `objectives`
        replaces the `score_output` / `minimize` / `target_score` triple; supplying both a
        non-default triple and `objectives` is refused rather than silently resolved, except that
        `target_score` fills the primary objective's target when the objective declares none.
        """

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
                    "a campaign that declares objectives states minimize and the output path on "
                    "each one; score_output and minimize describe a single objective and cannot "
                    "also apply"
                )
            declared = [item.model_copy(deep=True) for item in objectives]
            if not declared:
                raise ValueError("a campaign must declare at least one objective")
            if target_score is not None and declared[0].target is None:
                declared[0] = declared[0].model_copy(update={"target": target_score})
        return cls(
            objectives=declared,
            space=space or SearchSpace(),
            candidate_constraints=list(candidate_constraints),
            outcome_constraints=list(outcome_constraints),
        )

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

    def measure(self, outputs: Mapping[str, Any]) -> dict[str, ObjectiveValue]:
        """Read every declared objective out of a finished run, with the uncertainty it declared.

        It lives with the declaration rather than with the runner because a resumed campaign reads
        a run recorded by an earlier process the same way the live loop reads a fresh one.
        """

        measured: dict[str, ObjectiveValue] = {}
        for objective in self.objectives:
            value = float(read_path(dict(outputs), objective.output))
            uncertainty = None
            if objective.uncertainty_output is not None:
                uncertainty = float(read_path(dict(outputs), objective.uncertainty_output))
            measured[objective.name] = ObjectiveValue(value=value, uncertainty=uncertainty)
        return measured


class CampaignDefinition(OpenSDLModel):
    """Declarative description of a closed loop: what to search, and when to stop searching.

    Every field below `optimizer_config` names a `CampaignRunner.run` keyword argument and carries
    the same default, and a test asserts that in both directions. The submission facts — which
    environment the work runs in, which operator is accountable for it, which campaign identifier
    it writes under, and whether this invocation resumes an existing campaign — are deliberately
    absent: they come from the laboratory manifest and the caller, so a stored definition can never
    assert an environment its laboratory did not declare, and cannot declare "resume" as though it
    were a property of the search.
    """

    id: str
    name: str
    objective: str
    workflow_id: str
    optimizer: str
    #: Configuration handed to the optimizer plugin when it is constructed. Without it a
    #: stored definition names an optimizer it cannot configure, so a campaign file would
    #: always need a companion argument to be executable.
    optimizer_config: dict[str, Any] = Field(default_factory=dict)
    base_inputs: dict[str, Any] = Field(default_factory=dict)
    score_output: str = "score"
    max_iterations: int = Field(default=10, gt=0)
    minimize: bool = True
    #: Stop once an observation reaches this score. `None` searches the whole budget.
    target_score: float | None = None
    #: Stop once this many iterations fail in a row: failure has stopped being routine.
    max_consecutive_failures: int = Field(default=3, ge=1)
    #: Wall-clock budget, checked before each iteration. `None` is unbounded.
    max_duration_seconds: float | None = Field(default=None, gt=0)
    #: Workflow input that receives a unique per-iteration identifier, for laboratories whose
    #: workflows need one (a sample, a specimen, a plate well). `None` injects nothing, which is
    #: what a computational workflow needs.
    iteration_id_input: str | None = None
    #: The objectives this campaign searches. `None` falls back to the `score_output` /
    #: `minimize` / `target_score` triple, which states exactly one objective.
    objectives: list[Objective] | None = None
    #: The parameters, so the framework can refuse a candidate before anything is leased.
    search_space: SearchSpace | None = None
    candidate_constraints: list[CandidateConstraint] = Field(default_factory=list)
    outcome_constraints: list[OutcomeConstraint] = Field(default_factory=list)
    #: How many candidates the optimizer is asked for at once — a property of the method.
    batch_size: int = Field(default=1, ge=1)
    #: How many of them execute at the same time — a property of the laboratory.
    max_parallel_runs: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _problem_is_declared_once(self) -> CampaignDefinition:
        """Refuse at load what the runner would refuse at start, in the same words."""
        self.problem()
        return self

    def problem(self) -> CampaignProblem:
        """The problem this definition declares, resolved exactly as `CampaignRunner.run` does."""

        return CampaignProblem.declare(
            objectives=self.objectives,
            score_output=self.score_output,
            minimize=self.minimize,
            target_score=self.target_score,
            space=self.search_space,
            candidate_constraints=self.candidate_constraints,
            outcome_constraints=self.outcome_constraints,
        )


class Suggestion(OpenSDLModel):
    """One proposal, and the reasoning that produced it.

    Everything but `parameters` is optional. An optimizer with nothing to say returns a plain
    dictionary and the runner wraps it; an optimizer that fitted a model says what it predicted,
    how sure it was, which acquisition function ranked the candidate, and which model did it. That
    is what turns `Decision.rationale` from a template string into a decision record.

    It is a model rather than a frozen dataclass because it crosses a process boundary in both
    directions: a plugin returns one, and the campaign writes it into the durable event stream
    inside the observation it produced. `frozen=True` keeps what the dataclass gave — a proposal
    an optimizer handed over cannot be edited afterwards by the code recording it.

    The camelCase spelling is the campaign event stream's, applied by generator rather than field by
    field so the two cannot drift. An optimizer author writes `acquisition_function=`; only the
    recorded document says `acquisitionFunction`, and both validate.
    """

    model_config = CONTRACT_CONFIG

    parameters: dict[str, Any]
    #: Predicted objective values keyed by objective name, with the uncertainty of the prediction.
    predictions: dict[str, ObjectiveValue] = Field(default_factory=dict)
    #: The acquisition value this candidate was ranked by. For a jointly optimized batch such as
    #: q-EI this is the value of the batch, repeated, with `acquisition_function` naming it.
    acquisition: float | None = None
    acquisition_function: str = ""
    #: Whatever identifies the model that proposed this: name, version, kernel, seed, fit size.
    model: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    #: The runs this proposal rested on. `None` means the history the runner supplied, which is the
    #: honest default; a trust-region or windowed method states the subset it actually used.
    evidence_run_ids: tuple[str, ...] | None = None


class CampaignObservation(OpenSDLModel):
    """One attempted iteration.

    A failed attempt is an observation, not an absence of one: it carries the candidate that was
    tried and the error it produced, so an optimizer can avoid re-proposing it and an operator can
    see what the campaign did.

    This is what an optimizer plugin is handed, and what a campaign records as the best iteration
    it found, so it is a typed model with a generated schema rather than a dataclass serialised by
    hand into keys no schema described. `feasible` stays a property and is deliberately not part of
    the serialised form: it is `not constraint_violations`, and the recorded document now carries
    the violations themselves.
    """

    model_config = CONTRACT_CONFIG

    iteration: int = Field(ge=0)
    candidate: dict[str, Any]
    score: float | None = None
    run_id: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    status: CampaignObservationStatus = CampaignObservationStatus.SUCCEEDED
    error: str | None = None
    #: Every declared objective this run reported, with its measured uncertainty. `score` is the
    #: primary objective's value and stays the scalar view of the same thing.
    objectives: dict[str, ObjectiveValue] = Field(default_factory=dict)
    #: Why this observation is infeasible: a broken outcome constraint, or — for a rejected
    #: candidate — the reason the campaign refused to submit it.
    constraint_violations: tuple[str, ...] = ()
    #: What proposed this candidate, so an optimizer can compare its prediction to the outcome.
    suggestion: Suggestion | None = None
    #: Which proposed batch this candidate came from. Zero for a campaign that never batches.
    batch: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _status_and_outcome_agree(self) -> CampaignObservation:
        if self.status is CampaignObservationStatus.SUCCEEDED:
            if self.score is None:
                raise ValueError("a succeeded observation must carry the score it produced")
            if self.error is not None:
                raise ValueError("a succeeded observation cannot carry an error")
            return self
        if self.score is not None:
            raise ValueError("a failed observation has no score")
        if not self.error:
            raise ValueError("a failed observation must record why it failed")
        if self.status is CampaignObservationStatus.REJECTED and self.run_id is not None:
            raise ValueError("a rejected candidate was never submitted, so it names no run")
        return self

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

    def objective(self, name: str) -> float | None:
        """This observation's value for one declared objective, falling back to the score."""

        measured = self.objectives.get(name)
        if measured is not None:
            return measured.value
        return self.score


class IterationDecision(OpenSDLModel):
    """Why this candidate was chosen, as the optimizer stated it at the time.

    The read side of `Suggestion`: what the event record preserved of a proposal. Everything here
    is optional because an optimizer that ranks nothing has nothing to declare. What is never
    optional is `rationale` and `evidence_run_ids`: the runner writes a sentence and names the runs
    the proposal rested on even when the optimizer says nothing at all.
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

    def as_suggestion(self, candidate: Mapping[str, Any]) -> Suggestion:
        """Rebuild the proposal this record preserved, for a campaign replaying its own history."""

        return Suggestion(
            parameters=dict(candidate),
            predictions=dict(self.predictions),
            acquisition=self.acquisition,
            acquisition_function=self.acquisition_function,
            model=dict(self.model),
            rationale=self.rationale,
            evidence_run_ids=tuple(self.evidence_run_ids),
        )


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

    This is what stops the search space from living in two places.
    """

    def configure(self, problem: CampaignProblem) -> None | Awaitable[None]: ...


@runtime_checkable
class StatefulOptimizer(Protocol):
    """An optimizer that can hand out what it learned.

    The runner reads this once, when the campaign stops, and records it, so a fitted model's state
    survives the process that fitted it. Handing it back is `ResumableOptimizer`.
    """

    def state(self) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


@runtime_checkable
class ResumableOptimizer(Protocol):
    """An optimizer that can be given back the state a previous process recorded.

    Called once on a resumed campaign, after `configure` and before the first proposal, with the
    state recorded when the campaign last stopped. Optional on purpose: a grid has no model, and a
    resumed campaign replays its recorded observations regardless, so an optimizer that cannot
    restore state still resumes. What this adds is the state that cannot be recovered by replay —
    a fitted surrogate, a trust region, an RNG stream.

    Raising is the right answer to state this optimizer cannot use. The runner refuses the resume
    rather than continuing under the same campaign identifier with an optimizer that silently
    behaves differently.
    """

    def load_state(self, state: dict[str, Any]) -> None | Awaitable[None]: ...


def as_number(value: Any) -> float | None:
    """A real number, or `None`. `bool` is an `int` in Python and is not a measurement."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def matches_exactly(value: Any, expected: bool | int | str) -> bool:
    """Exact equality that keeps `bool`, `int` and `str` apart.

    `True == 1` and `False == 0` in Python, so a plain `==` would let a criterion declaring
    `equals: true` be satisfied by an output of `1`, and one declaring `equals: 1` be satisfied by
    `True`. A criterion says which of those it means, and a run that reported the other one has
    not met it.
    """

    if isinstance(expected, bool) or isinstance(value, bool):
        return isinstance(value, bool) and isinstance(expected, bool) and value is expected
    if isinstance(expected, str) or isinstance(value, str):
        return isinstance(value, str) and isinstance(expected, str) and value == expected
    return isinstance(value, int) and value == expected


def read_path(value: Mapping[str, Any], path: str) -> Any:
    """Follow a dotted path into a run's outputs, raising `KeyError` naming the whole path."""

    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"campaign score output not found: {path}")
        current = current[segment]
    return current
